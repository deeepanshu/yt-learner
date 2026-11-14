from __future__ import annotations

from dataclasses import dataclass

from app.channel_watches import WatchRepository
from app.config import Settings
from app.job_queue import JobQueue
from app.outline import OutlineError, PublishedNote
from app.pipeline import ProcessedVideo
from app.worker import WorkerService


@dataclass
class StubProcessor:
    result: ProcessedVideo

    async def process_video(self, video_url: str, requested_by: str, extra_prompt: str | None = None) -> ProcessedVideo:
        return self.result


class FakePublisher:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.videos: list[ProcessedVideo] = []

    def publish_video_notes(self, result: ProcessedVideo) -> PublishedNote:
        if self.fail:
            raise OutlineError("api down")
        self.videos.append(result)
        return PublishedNote(note_id="note1", url="https://outline.example/doc/note1")

    def publish_question_answer(self, result, *, question: str) -> PublishedNote:
        raise AssertionError("question publish should not run")


def dummy_settings(database_url: str) -> Settings:
    return Settings(
        ollama_api_key="key",
        ollama_model="test-model",
        database_url=database_url,
        outline_url="http://outline.example",
        outline_api_key="token",
        outline_collection_id="collection",
        outline_ui_url="https://outline.example",
    )


def test_worker_publishes_notes_to_outline(database_url) -> None:
    repository = WatchRepository(database_url)
    queue = JobQueue(database_url)
    subscription = repository.add_or_update_subscription(
        youtube_channel_id="UC12345678901234567890",
        youtube_channel_ref="https://www.youtube.com/channel/UC12345678901234567890",
        youtube_channel_title="AI Channel",
    )
    job = queue.enqueue_summarize_video(
        video_url="https://www.youtube.com/watch?v=abc123xyz",
        requested_by="youtube-channel-scheduler",
        source="youtube_channel_scheduler",
    )
    repository.record_discovered_video(
        subscription_id=subscription.id,
        video_id="abc123xyz",
        video_url=job.video_url,
        title="Demo",
        published_at=None,
    )
    repository.mark_video_enqueued(
        subscription_id=subscription.id,
        video_id="abc123xyz",
        queued_job_id=job.id,
    )

    processor = StubProcessor(
        result=ProcessedVideo(
            learning_record_id=77,
            video_id="abc123xyz",
            title="Demo",
            url=job.video_url,
            filename="result.md",
            markdown="# Learned",
            reused_existing=False,
        )
    )
    publisher = FakePublisher()
    service = WorkerService(
        settings=dummy_settings(database_url),
        queue=queue,
        processor=processor,
        note_publisher=publisher,
        watch_repository=repository,
    )

    completed = run_async(service.run_next_job())

    assert completed is not None
    assert completed.status == "done"
    assert completed.learning_record_id == 77
    discovered = repository.list_discovered_videos(subscription_id=subscription.id)
    assert discovered[0].learning_record_id == 77
    assert publisher.videos[0].markdown == "# Learned"


def test_worker_fails_job_when_outline_publish_fails(database_url) -> None:
    queue = JobQueue(database_url)
    job = queue.enqueue_summarize_video(
        video_url="https://www.youtube.com/watch?v=abc123xyz",
        requested_by="youtube-channel-scheduler",
        source="youtube_channel_scheduler",
    )
    processor = StubProcessor(
        result=ProcessedVideo(
            learning_record_id=77,
            video_id="abc123xyz",
            title="Demo",
            url=job.video_url,
            filename="result.md",
            markdown="# Learned",
            reused_existing=False,
        )
    )
    service = WorkerService(
        settings=dummy_settings(database_url),
        queue=queue,
        processor=processor,
        note_publisher=FakePublisher(fail=True),
    )

    completed = run_async(service.run_next_job())

    assert completed is not None
    assert completed.status == "failed"
    assert completed.error == "I could not save the notes to Outline. Please try again later."


def run_async(awaitable):
    import asyncio

    return asyncio.run(awaitable)
