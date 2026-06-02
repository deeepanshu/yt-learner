from __future__ import annotations

import argparse
import asyncio
import io
import logging
import time
from dataclasses import dataclass
from typing import Protocol, cast, runtime_checkable

import discord

from app.channel_watches import DiscordThreadRepository, WatchRepository
from app.config import Settings, load_settings
from app.discord_bot import build_processor
from app.extractor import ExtractionError
from app.job_queue import TASK_ANSWER_VIDEO_QUESTION, TASK_SUMMARIZE_VIDEO, Job, JobQueue
from app.pipeline import AnsweredVideoQuestion, ProcessedVideo, VideoProcessor
from app.telemetry import NoopTelemetry, configure_logging, configure_telemetry
from app.transcript import TranscriptFetchError, TranscriptUnavailableError, UnsupportedVideoError

LOGGER = logging.getLogger(__name__)
MAX_THREAD_TITLE_CHARS = 100
MAX_DISCORD_INLINE_MESSAGE_CHARS = 1900


def format_thread_title(title: str) -> str:
    cleaned = " ".join(title.split()) or "YouTube video"
    if len(cleaned) <= MAX_THREAD_TITLE_CHARS:
        return cleaned
    return cleaned[: MAX_THREAD_TITLE_CHARS - 3].rstrip() + "..."


class ProcessorProtocol(Protocol):
    async def process_video(
        self,
        video_url: str,
        requested_by: str,
        extra_prompt: str | None = None,
    ) -> ProcessedVideo: ...

    async def answer_video_question(
        self,
        *,
        video_id: str,
        question: str,
        requested_by: str,
    ) -> AnsweredVideoQuestion: ...


class DiscordMessageTarget(Protocol):
    async def send(
        self,
        content: str | None = None,
        *,
        file: discord.File | None = None,
        reference: object | None = None,
        mention_author: bool | None = None,
    ) -> object: ...


class EditableMessage(Protocol):
    async def edit(
        self,
        *,
        content: str | None = None,
        attachments: list[object] | None = None,
    ) -> object: ...


@runtime_checkable
class ThreadParentTarget(DiscordMessageTarget, Protocol):
    async def create_thread(
        self,
        *,
        name: str,
        type: discord.ChannelType | None = None,
    ) -> object: ...


@runtime_checkable
class PartialMessageTarget(Protocol):
    def get_partial_message(self, message_id: int) -> EditableMessage: ...


@dataclass(frozen=True)
class NotificationTarget:
    channel: DiscordMessageTarget
    use_reply_reference: bool


class DiscordClientProtocol(Protocol):
    async def fetch_channel(self, channel_id: int, /) -> object: ...

    async def fetch_user(self, user_id: int, /) -> object: ...

    async def wait_until_ready(self) -> None: ...

    def is_closed(self) -> bool: ...


class WorkerService:
    def __init__(
        self,
        *,
        settings: Settings,
        queue: JobQueue,
        processor: ProcessorProtocol,
        discord_client: DiscordClientProtocol,
        watch_repository: WatchRepository | None = None,
        discord_thread_repository: DiscordThreadRepository | None = None,
        telemetry=None,
    ) -> None:
        self.settings = settings
        self.queue = queue
        self.processor = processor
        self.discord_client = discord_client
        self.watch_repository = watch_repository
        self.discord_thread_repository = discord_thread_repository or DiscordThreadRepository(settings.db_path)
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
            if job.task_type == TASK_SUMMARIZE_VIDEO:
                return await self._run_summarize_job(job, started)
            if job.task_type == TASK_ANSWER_VIDEO_QUESTION:
                return await self._run_question_job(job, started)
            raise RuntimeError(f"Unsupported job task type: {job.task_type}")
        except Exception as exc:
            failed_job = self.queue.mark_failed(job.id, error=self._error_text(exc, job=job))
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

    async def _run_summarize_job(self, job: Job, started: float) -> Job:
        result = await self.processor.process_video(
            job.video_url,
            requested_by=job.requested_by,
            extra_prompt=job.extra_prompt,
        )
        done_job = self.queue.mark_done(
            job.id,
            learning_record_id=result.learning_record_id,
            result_path=str(result.output_path),
        )
        if self.watch_repository is not None:
            self.watch_repository.mark_video_indexed_by_job(
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

    async def _run_question_job(self, job: Job, started: float) -> Job:
        if job.video_id is None or job.question is None:
            raise RuntimeError("Question job is missing video_id or question")
        result = await self.processor.answer_video_question(
            video_id=job.video_id,
            question=job.question,
            requested_by=job.requested_by,
        )
        done_job = self.queue.mark_done(
            job.id,
            learning_record_id=result.learning_record_id,
            result_path="",
        )
        self.telemetry.record_job_processed(
            source=job.source,
            status="done",
            duration_seconds=time.perf_counter() - started,
            reused_existing=True,
        )
        LOGGER.info(
            "worker_question_job_done job_id=%s source=%s video_id=%s duration_seconds=%.3f",
            job.id,
            job.source,
            result.video_id,
            time.perf_counter() - started,
        )
        await self._safe_notify_question_answer(done_job, result)
        return done_job

    async def run_forever(self, *, poll_interval_seconds: float = 2.0) -> None:
        await self.discord_client.wait_until_ready()
        while not self.discord_client.is_closed():
            job = await self.run_next_job()
            if job is None:
                await asyncio.sleep(poll_interval_seconds)

    async def _notify_success(self, job: Job, result: ProcessedVideo) -> None:
        target = await self._resolve_success_target(job, result)
        if target is None:
            LOGGER.info("worker_success_notification_skipped job_id=%s reason=no_channel", job.id)
            return
        prefix = "Reused existing notes" if result.reused_existing else "Done"
        LOGGER.info(
            "worker_success_notification_started job_id=%s attachment_path=%s channel_type=%s",
            job.id,
            result.output_path,
            type(target.channel).__name__,
        )
        content = f"{prefix}: {result.title}"
        if target.use_reply_reference and await self._try_edit_status_message(
            job,
            content=content,
            file=discord.File(result.output_path),
        ):
            return

        reference = self._notification_reference(job, target.channel) if target.use_reply_reference else None
        await target.channel.send(
            content=content,
            file=discord.File(result.output_path),
            reference=reference,
            mention_author=False,
        )
        if not target.use_reply_reference:
            await self._try_edit_status_message(job, content=f"{content} — posted in the video thread.")

    async def _notify_question_answer(self, job: Job, result: AnsweredVideoQuestion) -> None:
        channel = await self._resolve_channel(job)
        if channel is None:
            LOGGER.info("worker_question_notification_skipped job_id=%s reason=no_channel", job.id)
            return
        if len(result.markdown) <= MAX_DISCORD_INLINE_MESSAGE_CHARS:
            if await self._try_edit_status_message(job, content=result.markdown):
                return
            await channel.send(
                result.markdown,
                reference=self._notification_reference(job, channel),
                mention_author=False,
            )
            return

        answer_file = discord.File(
            io.BytesIO(result.markdown.encode("utf-8")),
            filename=f"job-{job.id}-answer.md",
        )
        if await self._try_edit_status_message(
            job,
            content="Answer attached.",
            file=answer_file,
        ):
            return
        await channel.send(
            content="Answer attached.",
            file=answer_file,
            reference=self._notification_reference(job, channel),
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

    async def _safe_notify_question_answer(self, job: Job, result: AnsweredVideoQuestion) -> None:
        try:
            await self._notify_question_answer(job, result)
        except discord.DiscordException:
            LOGGER.exception("Unable to send question answer notification for job %s", job.id)

    async def _safe_notify_failure(self, job: Job) -> None:
        try:
            await self._notify_failure(job)
        except discord.DiscordException:
            LOGGER.exception("Unable to send failure notification for job %s", job.id)

    async def _resolve_success_target(self, job: Job, result: ProcessedVideo) -> NotificationTarget | None:
        if job.guild_id is None or job.reply_channel_id is None:
            channel = await self._resolve_channel(job)
            if channel is None:
                return None
            return NotificationTarget(channel=channel, use_reply_reference=True)

        existing = self.discord_thread_repository.find_thread(
            guild_id=job.guild_id,
            parent_channel_id=job.reply_channel_id,
            video_id=result.video_id,
        )
        if existing is not None:
            try:
                thread = await self.discord_client.fetch_channel(existing.thread_id)
                return NotificationTarget(channel=cast(DiscordMessageTarget, thread), use_reply_reference=False)
            except discord.DiscordException:
                LOGGER.exception("Unable to fetch existing Discord thread for job %s", job.id)

        parent = await self._resolve_channel(job)
        if parent is None:
            return None
        if not isinstance(parent, ThreadParentTarget):
            return NotificationTarget(channel=parent, use_reply_reference=True)

        thread_name = format_thread_title(result.title)
        try:
            thread = await parent.create_thread(name=thread_name, type=discord.ChannelType.public_thread)
        except discord.DiscordException:
            LOGGER.exception("Unable to create Discord thread for job %s", job.id)
            return NotificationTarget(channel=parent, use_reply_reference=True)
        thread_id = getattr(thread, "id", None)
        if thread_id is None:
            LOGGER.info("worker_discord_thread_untracked job_id=%s reason=missing_thread_id", job.id)
            return NotificationTarget(channel=cast(DiscordMessageTarget, thread), use_reply_reference=False)
        self.discord_thread_repository.save_thread(
            guild_id=job.guild_id,
            parent_channel_id=job.reply_channel_id,
            video_id=result.video_id,
            thread_id=int(thread_id),
            title=thread_name,
        )
        return NotificationTarget(channel=cast(DiscordMessageTarget, thread), use_reply_reference=False)

    async def _resolve_channel(self, job: Job) -> DiscordMessageTarget | None:
        if job.reply_channel_id is not None:
            try:
                return cast(DiscordMessageTarget, await self.discord_client.fetch_channel(job.reply_channel_id))
            except discord.DiscordException:
                LOGGER.exception("Unable to fetch reply channel for job %s", job.id)

        try:
            user = await self.discord_client.fetch_user(int(job.requested_by))
        except (ValueError, discord.DiscordException):
            LOGGER.exception("Unable to fetch fallback user for job %s", job.id)
            return None
        return cast(DiscordMessageTarget, user)

    async def _try_edit_status_message(
        self,
        job: Job,
        *,
        content: str,
        file: discord.File | None = None,
    ) -> bool:
        if job.reply_channel_id is None or job.reply_message_id is None:
            return False
        try:
            channel = await self.discord_client.fetch_channel(job.reply_channel_id)
        except discord.DiscordException:
            LOGGER.exception("Unable to fetch status channel for job %s", job.id)
            return False
        if not isinstance(channel, PartialMessageTarget):
            return False
        try:
            message = channel.get_partial_message(job.reply_message_id)
            if file is None:
                await message.edit(content=content)
            else:
                await message.edit(content=content, attachments=[file])
        except discord.DiscordException:
            LOGGER.exception("Unable to edit status message for job %s", job.id)
            return False
        return True

    def _notification_reference(self, job: Job, channel: object) -> object | None:
        if job.reply_message_id is None or not isinstance(channel, PartialMessageTarget):
            return None
        return channel.get_partial_message(job.reply_message_id)

    def _error_text(self, exc: Exception, *, job: Job | None = None) -> str:
        if isinstance(exc, TranscriptUnavailableError):
            return "I could not fetch an English transcript for this video."
        if isinstance(exc, TranscriptFetchError):
            return "I could not fetch the transcript right now. Please try again later."
        if isinstance(exc, UnsupportedVideoError):
            return "The video looks private, unavailable, or unsupported."
        if isinstance(exc, ExtractionError):
            if job is not None and job.task_type == TASK_ANSWER_VIDEO_QUESTION:
                return "I could not answer that question while calling OpenAI. Try again later."
            return "The extraction failed while calling OpenAI. The transcript was saved for debugging."
        return "The extraction failed while calling OpenAI. Try again later."

    def _log_failure(self, job: Job, exc: Exception) -> None:
        if isinstance(exc, ExtractionError):
            LOGGER.exception("OpenAI extraction failure for job %s", job.id)
            return
        LOGGER.exception("Unhandled processing failure for job %s", job.id)


class WorkerBot(discord.Client):
    def __init__(
        self,
        *,
        settings: Settings,
        queue: JobQueue,
        processor: ProcessorProtocol,
        watch_repository: WatchRepository | None = None,
        telemetry=None,
    ) -> None:
        super().__init__(intents=discord.Intents.none())
        self.service = WorkerService(
            settings=settings,
            queue=queue,
            processor=processor,
            discord_client=self,
            watch_repository=watch_repository,
            telemetry=telemetry,
        )
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

    if args.run_once:
        client = discord.Client(intents=discord.Intents.none())
        telemetry = configure_telemetry("yt-learner-worker")
        service = WorkerService(
            settings=settings,
            queue=queue,
            processor=processor,
            discord_client=client,
            watch_repository=watch_repository,
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
        settings=settings,
        queue=queue,
        processor=processor,
        watch_repository=watch_repository,
        telemetry=configure_telemetry("yt-learner-worker"),
    )
    bot.run(settings.discord_bot_token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
