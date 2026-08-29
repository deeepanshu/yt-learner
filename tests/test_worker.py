from __future__ import annotations

from dataclasses import dataclass

from app.channel_watches import WatchRepository
from app.config import Settings
from app.job_queue import JobQueue
from app.pipeline import ProcessedVideo
from app.worker import WorkerService


@dataclass
class StubProcessor:
    result: ProcessedVideo

    async def process_video(self, video_url: str, requested_by: str, extra_prompt: str | None = None) -> ProcessedVideo:
        return self.result


class FakePartialMessage:
    def __init__(self, channel: "FakeChannel", message_id: int) -> None:
        self.channel = channel
        self.id = message_id

    async def edit(self, *, content=None, attachments=None):
        file = attachments[0] if attachments else None
        self.channel.messages.append((content, file, None, None))


class FakeChannel:
    def __init__(self) -> None:
        self.messages = []

    def get_partial_message(self, message_id: int):
        return FakePartialMessage(self, message_id)

    async def send(self, content=None, file=None, reference=None, mention_author=None):
        self.messages.append((content, file, reference, mention_author))


class FakeDiscordClient:
    def __init__(self, channel: FakeChannel) -> None:
        self.channel = channel

    async def fetch_channel(self, channel_id: int):
        return self.channel


def test_worker_marks_scheduled_video_as_indexed(database_url) -> None:
    repository = WatchRepository(database_url)
    queue = JobQueue(database_url)
    subscription = repository.add_or_update_subscription(
        guild_id="guild-1",
        youtube_channel_id="UC12345678901234567890",
        youtube_channel_ref="https://www.youtube.com/channel/UC12345678901234567890",
        youtube_channel_title="AI Channel",
        discord_channel_id=1001,
    )
    job = queue.enqueue_summarize_video(
        video_url="https://www.youtube.com/watch?v=abc123xyz",
        requested_by="youtube-channel-scheduler",
        source="youtube_channel_scheduler",
        reply_channel_id=subscription.discord_channel_id,
        reply_message_id=2222,
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
    channel = FakeChannel()
    service = WorkerService(
        settings=Settings(
            openai_api_key="key",
            discord_bot_token="token",
            database_url=database_url,
            discord_allowed_user_id=None,
        ),
        queue=queue,
        processor=processor,
        discord_client=FakeDiscordClient(channel),
        watch_repository=repository,
    )

    completed = run_async(service.run_next_job())

    assert completed is not None
    assert completed.learning_record_id == 77
    discovered = repository.list_discovered_videos(subscription_id=subscription.id)
    assert discovered[0].learning_record_id == 77
    assert channel.messages[0][0] == "Done: Demo"
    assert channel.messages[0][1] is not None


def run_async(awaitable):
    import asyncio

    return asyncio.run(awaitable)
