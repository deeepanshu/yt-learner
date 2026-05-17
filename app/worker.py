from __future__ import annotations

import argparse
import asyncio
import logging

import discord

from app.config import Settings, load_settings
from app.discord_bot import build_processor
from app.extractor import ExtractionError
from app.job_queue import Job, JobQueue
from app.pipeline import ProcessedVideo, VideoProcessor
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
    ) -> None:
        self.settings = settings
        self.queue = queue
        self.processor = processor
        self.discord_client = discord_client

    async def run_next_job(self) -> Job | None:
        job = self.queue.claim_next_job()
        if job is None:
            return None

        try:
            result = await self.processor.process_video(job.video_url, requested_by=job.requested_by)
        except Exception as exc:
            failed_job = self.queue.mark_failed(job.id, error=self._error_text(exc))
            await self._safe_notify_failure(failed_job)
            self._log_failure(job, exc)
            return failed_job

        done_job = self.queue.mark_done(job.id, result_path=str(result.output_path))
        await self._safe_notify_success(done_job, result)
        return done_job

    async def run_forever(self, *, poll_interval_seconds: float = 2.0) -> None:
        await self.discord_client.wait_until_ready()
        while not self.discord_client.is_closed():
            job = await self.run_next_job()
            if job is None:
                await asyncio.sleep(poll_interval_seconds)

    async def _notify_success(self, job: Job, result: ProcessedVideo) -> None:
        channel = await self._resolve_channel(job)
        if channel is None:
            return
        prefix = "Reused existing notes" if result.reused_existing else "Done"
        await channel.send(
            content=f"{prefix} for job #{job.id}: {result.title}",
            file=discord.File(result.output_path),
        )

    async def _notify_failure(self, job: Job) -> None:
        channel = await self._resolve_channel(job)
        if channel is None:
            return
        await channel.send(f"Job #{job.id} failed: {job.error}")

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
    logging.basicConfig(level=logging.INFO)
    settings = load_settings()
    queue = JobQueue(settings.db_path)
    processor = build_processor(settings)

    if args.run_once:
        client = discord.Client(intents=discord.Intents.none())
        service = WorkerService(
            settings=settings,
            queue=queue,
            processor=processor,
            discord_client=client,
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
        )
    )
    bot.service.discord_client = bot
    bot.run(settings.discord_bot_token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
