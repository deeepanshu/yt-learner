from __future__ import annotations

import argparse
import asyncio
import logging
import time
from typing import Protocol

from app.channel_watches import WatchRepository
from app.config import Settings, load_settings
from app.extractor import ExtractionError, LearningExtractor
from app.job_queue import TASK_SUMMARIZE_VIDEO, Job, JobQueue
from app.pipeline import ProcessedVideo, VideoProcessor
from app.storage import OutputStore
from app.telemetry import NoopTelemetry, configure_logging, configure_telemetry
from app.transcript import TranscriptFetchError, TranscriptUnavailableError, UnsupportedVideoError
from app.outline import NotePublisher, OutlineError, build_outline_client

LOGGER = logging.getLogger(__name__)


class ProcessorProtocol(Protocol):
    async def process_video(
        self,
        video_url: str,
        requested_by: str,
        extra_prompt: str | None = None,
    ) -> ProcessedVideo: ...


class WorkerService:
    def __init__(
        self,
        *,
        settings: Settings,
        queue: JobQueue,
        processor: ProcessorProtocol,
        note_publisher: NotePublisher,
        watch_repository: WatchRepository | None = None,
        telemetry=None,
    ) -> None:
        self.settings = settings
        self.queue = queue
        self.processor = processor
        self.note_publisher = note_publisher
        self.watch_repository = watch_repository
        self.telemetry = telemetry or NoopTelemetry()

    async def run_next_job(self) -> Job | None:
        job = self.queue.claim_next_job()
        if job is None:
            return None
        LOGGER.info(
            "worker_job_claimed job_id=%s source=%s requested_by=%s video_url=%s attempt=%s",
            job.id,
            job.source,
            job.requested_by,
            job.video_url,
            job.attempts,
        )

        started = time.perf_counter()
        try:
            if job.task_type != TASK_SUMMARIZE_VIDEO:
                raise RuntimeError(f"Unsupported job task type: {job.task_type}")
            return await self._run_summarize_job(job, started)
        except Exception as exc:
            failed_job = self.queue.mark_failed(job.id, error=self._error_text(exc))
            self.telemetry.record_job_processed(
                source=job.source,
                status="failed",
                duration_seconds=time.perf_counter() - started,
                error_type=type(exc).__name__,
            )
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
        published = self.note_publisher.publish_video_notes(result)
        done_job = self.queue.mark_done(
            job.id,
            learning_record_id=result.learning_record_id,
            result_filename=result.filename,
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
            "worker_job_done job_id=%s source=%s learning_record_id=%s reused_existing=%s filename=%s outline_document_id=%s duration_seconds=%.3f",
            job.id,
            job.source,
            result.learning_record_id,
            result.reused_existing,
            result.filename,
            published.note_id,
            time.perf_counter() - started,
        )
        return done_job

    async def run_forever(self, *, poll_interval_seconds: float = 2.0) -> None:
        while True:
            job = await self.run_next_job()
            if job is None:
                await asyncio.sleep(poll_interval_seconds)

    def _error_text(self, exc: Exception) -> str:
        if isinstance(exc, TranscriptUnavailableError):
            return "I could not fetch an English transcript for this video."
        if isinstance(exc, TranscriptFetchError):
            return "I could not fetch the transcript right now. Please try again later."
        if isinstance(exc, UnsupportedVideoError):
            return "The video looks private, unavailable, or unsupported."
        if isinstance(exc, OutlineError):
            return "I could not save the notes to Outline. Please try again later."
        if isinstance(exc, ExtractionError):
            return "The extraction failed while calling Ollama. The transcript was saved for debugging."
        return "The extraction failed while calling Ollama. Try again later."

    def _log_failure(self, job: Job, exc: Exception) -> None:
        if isinstance(exc, ExtractionError):
            LOGGER.exception("Ollama extraction failure for job %s", job.id)
            return
        if isinstance(exc, OutlineError):
            LOGGER.exception("Outline publish failure for job %s", job.id)
            return
        LOGGER.exception("Unhandled processing failure for job %s", job.id)


def build_processor(settings: Settings) -> VideoProcessor:
    store = OutputStore(settings.database_url)
    extractor = LearningExtractor(
        api_key=settings.ollama_api_key,
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        max_transcript_chars=settings.max_transcript_chars,
    )
    return VideoProcessor(store=store, extractor=extractor)


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
    queue = JobQueue(settings.database_url)
    processor = build_processor(settings)
    watch_repository = WatchRepository(settings.database_url)
    note_publisher = build_outline_client(settings)
    service = WorkerService(
        settings=settings,
        queue=queue,
        processor=processor,
        note_publisher=note_publisher,
        watch_repository=watch_repository,
        telemetry=configure_telemetry("yt-learner-worker"),
    )
    if args.run_once:
        asyncio.run(service.run_next_job())
        return 0
    asyncio.run(service.run_forever())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
