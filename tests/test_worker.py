from __future__ import annotations

from dataclasses import dataclass

from app.channel_watches import WatchRepository
from app.config import Settings
from app.job_queue import JobQueue
from app.pipeline import ProcessedVideo
from app.storage import OutputStore
from app.worker import WorkerService


@dataclass
class StubProcessor:
    result: ProcessedVideo
    last_extra_prompt: str | None = None

    async def process_video(
        self,
        video_url: str,
        requested_by: str,
        extra_prompt: str | None = None,
    ) -> ProcessedVideo:
        self.last_extra_prompt = extra_prompt
        return self.result


class FakeChannel:
    def __init__(self) -> None:
        self.messages: list[tuple[str | None, object | None, object | None, bool | None]] = []

    def get_partial_message(self, message_id: int) -> object:
        return f"partial:{message_id}"

    async def send(
        self,
        content: str | None = None,
        *,
        file: object | None = None,
        reference: object | None = None,
        mention_author: bool | None = None,
    ) -> object:
        self.messages.append((content, file, reference, mention_author))
        return object()


class FakeDiscordClient:
    def __init__(self, channel: FakeChannel) -> None:
        self.channel = channel

    async def fetch_channel(self, channel_id: int, /) -> object:
        return self.channel

    async def fetch_user(self, user_id: int, /) -> object:
        return self.channel

    async def wait_until_ready(self) -> None:
        return None

    def is_closed(self) -> bool:
        return True


def test_worker_marks_scheduled_video_as_indexed(tmp_path) -> None:
    db_path = tmp_path / "data" / "yt_learner.sqlite3"
    output_root = tmp_path / "outputs"
    result_path = output_root / "result.md"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text("# Learned", encoding="utf-8")

    repository = WatchRepository(db_path)
    queue = JobQueue(db_path)
    store = OutputStore(output_root, db_path)
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
            output_path=result_path,
            reused_existing=False,
        )
    )
    channel = FakeChannel()
    service = WorkerService(
        settings=Settings(
            openai_api_key="key",
            discord_bot_token="token",
            discord_allowed_user_id=None,
            discord_output_dir=output_root,
            db_path=db_path,
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
    assert channel.messages[0][0] == f"Done for job #{job.id}: Demo"
    assert channel.messages[0][1] is not None
    assert channel.messages[0][2] == "partial:2222"
    assert channel.messages[0][3] is False
    assert processor.last_extra_prompt is None


def test_worker_passes_extra_prompt_to_processor(tmp_path) -> None:
    db_path = tmp_path / "data" / "yt_learner.sqlite3"
    output_root = tmp_path / "outputs"
    result_path = output_root / "result.md"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text("# Learned", encoding="utf-8")

    queue = JobQueue(db_path)
    job = queue.enqueue_summarize_video(
        video_url="https://www.youtube.com/watch?v=abc123xyz",
        requested_by="user-1",
        source="discord_slash_command",
        reply_channel_id=1001,
        extra_prompt="focus on deployment advice",
    )
    processor = StubProcessor(
        result=ProcessedVideo(
            learning_record_id=77,
            video_id="abc123xyz",
            title="Demo",
            url=job.video_url,
            output_path=result_path,
            reused_existing=False,
        )
    )

    service = WorkerService(
        settings=Settings(
            openai_api_key="key",
            discord_bot_token="token",
            discord_allowed_user_id=None,
            discord_output_dir=output_root,
            db_path=db_path,
        ),
        queue=queue,
        processor=processor,
        discord_client=FakeDiscordClient(FakeChannel()),
    )

    run_async(service.run_next_job())

    assert processor.last_extra_prompt == "focus on deployment advice"


def run_async(awaitable):
    import asyncio

    return asyncio.run(awaitable)
