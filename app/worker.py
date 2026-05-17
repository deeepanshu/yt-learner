from __future__ import annotations

import argparse
import asyncio
import logging
import time

import discord

from app.channel_watches import WatchRepository
from app.config import Settings, load_settings
from app.discord_bot import build_processor
from app.extractor import ExtractionError
from app.job_queue import Job, JobQueue
from app.pipeline import ProcessedVideo, VideoProcessor
from app.scheduler import ChannelScheduler
from app.telemetry import NoopTelemetry, configure_logging, configure_telemetry
from app.transcript import TranscriptFetchError, TranscriptUnavailableError, UnsupportedVideoError

LOGGER = logging.getLogger(__name__)


class WorkerService:
    def __init__(
        self,
        *,
        settings: Settings,
        queue: JobQueue,
        processor: VideoProcessor,
        discord_client: discord.Client,
        scheduler: ChannelScheduler | None = None,
        telemetry=None,
    ) -> None:
        self.settings = settings
        self.queue = queue
        self.processor = processor
        self.discord_client = discord_client
        self.scheduler = scheduler
        self.telemetry = telemetry or NoopTelemetry()

    async def run_next_job(self) -> Job | None:
        job = self.queue.claim_next_job()
        if job is None:
            return None
        LOGGER.info(
            "worker_job_claimed job_id=%s source=%s requested_by=%s reply_channel_id=%s video_url=%s attempt=%s",
            job.id,
            job.source,
            job.requested_by,
            job.reply_channel_id,
            job.video_url,
            job.attempts,
        )

        started = time.perf_counter()
        try:
            result = await self.processor.process_video(job.video_url, requested_by=job.requested_by)
        except Exception as exc:
            failed_job = self.queue.mark_failed(job.id, error=self._error_text(exc))
            self.telemetry.record_job_processed(
                source=job.source,
                status="failed",
                duration_seconds=time.perf_counter() - started,
                error_type=type(exc).__name__,
            )
            await self._safe_notify_failure(failed_job)
            self._log_failure(job, exc)
            LOGGER.info(
                "worker_job_failed job_id=%s source=%s error_type=%s user_message=%r duration_seconds=%.3f",
                job.id,
                job.source,
                type(exc).__name__,
                failed_job.error,
                time.perf_counter() - started,
            )
            return failed_job

        done_job = self.queue.mark_done(
            job.id,
            learning_record_id=result.learning_record_id,
            result_path=str(result.output_path),
        )
        if self.scheduler is not None:
            self.scheduler.watch_repository.mark_video_indexed_by_job(
                queued_job_id=job.id,
                learning_record_id=result.learning_record_id,
            )
        self.telemetry.record_job_processed(
            source=job.source,
            status="done",
            duration_seconds=time.perf_counter() - started,
            reused_existing=result.reused_existing,
        )
        LOGGER.info(
            "worker_job_done job_id=%s source=%s learning_record_id=%s reused_existing=%s output_path=%s duration_seconds=%.3f",
            job.id,
            job.source,
            result.learning_record_id,
            result.reused_existing,
            result.output_path,
            time.perf_counter() - started,
        )
        await self._safe_notify_success(done_job, result)
        return done_job

    async def run_forever(self, *, poll_interval_seconds: float = 2.0) -> None:
        await self.discord_client.wait_until_ready()
        next_scheduler_poll = 0.0
        while not self.discord_client.is_closed():
            now = time.monotonic()
            if self.scheduler is not None and now >= next_scheduler_poll:
                LOGGER.info(
                    "worker_scheduler_poll_due poll_interval_seconds=%s",
                    self.settings.scheduler_poll_interval_seconds,
                )
                await self.scheduler.poll_once()
                next_scheduler_poll = now + float(self.settings.scheduler_poll_interval_seconds)
            job = await self.run_next_job()
            if job is None:
                await asyncio.sleep(poll_interval_seconds)

    async def _notify_success(self, job: Job, result: ProcessedVideo) -> None:
        channel = await self._resolve_channel(job)
        if channel is None:
            LOGGER.info("worker_success_notification_skipped job_id=%s reason=no_channel", job.id)
            return
        prefix = "Reused existing notes" if result.reused_existing else "Done"
        LOGGER.info(
            "worker_success_notification_started job_id=%s attachment_path=%s channel_type=%s",
            job.id,
            result.output_path,
            type(channel).__name__,
        )
        reference = self._notification_reference(job, channel)
        await channel.send(
            content=f"{prefix} for job #{job.id}: {result.title}",
            file=discord.File(result.output_path),
            reference=reference,
            mention_author=False,
        )

    async def _notify_failure(self, job: Job) -> None:
        channel = await self._resolve_channel(job)
        if channel is None:
            LOGGER.info("worker_failure_notification_skipped job_id=%s reason=no_channel", job.id)
            return
        LOGGER.info("worker_failure_notification_started job_id=%s channel_type=%s", job.id, type(channel).__name__)
        await channel.send(
            f"Job #{job.id} failed: {job.error}",
            reference=self._notification_reference(job, channel),
            mention_author=False,
        )

    async def _safe_notify_success(self, job: Job, result: ProcessedVideo) -> None:
        try:
            await self._notify_success(job, result)
        except discord.DiscordException:
            LOGGER.exception("Unable to send success notification for job %s", job.id)

    async def _safe_notify_failure(self, job: Job) -> None:
        try:
            await self._notify_failure(job)
        except discord.DiscordException:
            LOGGER.exception("Unable to send failure notification for job %s", job.id)

    async def _resolve_channel(self, job: Job):
        if job.reply_channel_id is not None:
            try:
                return await self.discord_client.fetch_channel(job.reply_channel_id)
            except discord.DiscordException:
                LOGGER.exception("Unable to fetch reply channel for job %s", job.id)

        try:
            user = await self.discord_client.fetch_user(int(job.requested_by))
        except (ValueError, discord.DiscordException):
            LOGGER.exception("Unable to fetch fallback user for job %s", job.id)
            return None
        return user

    def _notification_reference(self, job: Job, channel):
        if job.reply_message_id is None or not hasattr(channel, "get_partial_message"):
            return None
        return channel.get_partial_message(job.reply_message_id)

    def _error_text(self, exc: Exception) -> str:
        if isinstance(exc, TranscriptUnavailableError):
            return "I could not fetch an English transcript for this video."
        if isinstance(exc, TranscriptFetchError):
            return "I could not fetch the transcript right now. Please try again later."
        if isinstance(exc, UnsupportedVideoError):
            return "The video looks private, unavailable, or unsupported."
        if isinstance(exc, ExtractionError):
            return "The extraction failed while calling OpenAI. The transcript was saved for debugging."
        return "The extraction failed while calling OpenAI. Try again later."

    def _log_failure(self, job: Job, exc: Exception) -> None:
        if isinstance(exc, ExtractionError):
            LOGGER.exception("OpenAI extraction failure for job %s", job.id)
            return
        LOGGER.exception("Unhandled processing failure for job %s", job.id)


class WorkerBot(discord.Client):
    def __init__(self, *, service: WorkerService) -> None:
        super().__init__(intents=discord.Intents.none())
        self.service = service
        self._task: asyncio.Task[None] | None = None

    async def setup_hook(self) -> None:
        self._task = asyncio.create_task(self.service.run_forever())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the yt-learner worker.")
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Process one queued job if available and exit.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging("yt-learner-worker")
    settings = load_settings()
    queue = JobQueue(settings.db_path)
    processor = build_processor(settings)
    watch_repository = WatchRepository(settings.db_path)
    scheduler = ChannelScheduler(
        watch_repository=watch_repository,
        queue=queue,
        store=processor.store,
    )

    if args.run_once:
        client = discord.Client(intents=discord.Intents.none())
        telemetry = configure_telemetry("yt-learner-worker")
        service = WorkerService(
            settings=settings,
            queue=queue,
            processor=processor,
            discord_client=client,
            scheduler=scheduler,
            telemetry=telemetry,
        )

        async def _run_once() -> None:
            async with client:
                await client.login(settings.discord_bot_token)
                try:
                    await service.run_next_job()
                finally:
                    await client.close()

        asyncio.run(_run_once())
        return 0

    bot = WorkerBot(
        service=WorkerService(
            settings=settings,
            queue=queue,
            processor=processor,
            discord_client=None,  # type: ignore[arg-type]
            scheduler=scheduler,
            telemetry=configure_telemetry("yt-learner-worker"),
        )
    )
    bot.service.discord_client = bot
    bot.run(settings.discord_bot_token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
