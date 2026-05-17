from dataclasses import dataclass

from app.discord_bot import LearnerBot, extract_youtube_url


@dataclass
class DummySettings:
    discord_allowed_user_id: str | None = None
    allowed_channel_id: str | None = None


class DummyQueue:
    def __init__(self) -> None:
        self.calls = []

    def enqueue_summarize_video(self, **kwargs):
        self.calls.append(kwargs)
        return type("Job", (), {"id": 7})()


def test_extract_youtube_url_from_plain_message() -> None:
    content = "check this out https://www.youtube.com/watch?v=abc123xyz thanks"
    assert extract_youtube_url(content) == "https://www.youtube.com/watch?v=abc123xyz"


def test_extract_youtube_url_from_parenthesized_message() -> None:
    content = "(https://youtu.be/abc123xyz)"
    assert extract_youtube_url(content) == "https://youtu.be/abc123xyz"


def test_extract_youtube_url_returns_none_when_missing() -> None:
    assert extract_youtube_url("hello world") is None


def test_enqueue_job_uses_queue_and_formats_reply() -> None:
    queue = DummyQueue()
    bot = LearnerBot(settings=DummySettings(), queue=queue)

    job = bot._enqueue_job(
        video_url="https://www.youtube.com/watch?v=abc123xyz",
        requested_by="42",
        source="discord_message",
        reply_channel_id=999,
    )

    assert job.id == 7
    assert queue.calls == [
        {
            "video_url": "https://www.youtube.com/watch?v=abc123xyz",
            "requested_by": "42",
            "source": "discord_message",
            "reply_channel_id": 999,
        }
    ]
    assert bot._queued_text(7, "https://www.youtube.com/watch?v=abc123xyz") == (
        "Queued job #7 for https://www.youtube.com/watch?v=abc123xyz"
    )


def test_server_scoped_auth_helpers() -> None:
    bot = LearnerBot(settings=DummySettings(), queue=DummyQueue())

    guild_message = type("Message", (), {"guild": object()})()
    dm_message = type("Message", (), {"guild": None})()
    guild_interaction = type("Interaction", (), {"guild_id": 123, "channel": object()})()
    dm_interaction = type("Interaction", (), {"guild_id": None, "channel": object()})()

    assert bot._is_allowed_message(guild_message) is True
    assert bot._is_allowed_message(dm_message) is False
    assert bot._is_allowed_interaction(guild_interaction) is True
    assert bot._is_allowed_interaction(dm_interaction) is False
