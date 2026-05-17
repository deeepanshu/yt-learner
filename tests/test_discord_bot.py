from dataclasses import dataclass

from app.discord_bot import LearnerBot, extract_youtube_url


@dataclass
class DummySettings:
    discord_allowed_user_id: str | None = None
    allowed_channel_id: str | None = None


class DummyQueue:
    def __init__(self) -> None:
        self.calls = []
        self.reply_updates = []

    def enqueue_summarize_video(self, **kwargs):
        self.calls.append(kwargs)
        return type("Job", (), {"id": 7})()

    def update_reply_message_id(self, job_id: int, *, reply_message_id: int):
        self.reply_updates.append((job_id, reply_message_id))
        return type("Job", (), {"id": job_id})()


class DummyWatchRepository:
    def __init__(self) -> None:
        self.by_id_calls = []
        self.by_channel_calls = []
        self.by_id_result = None
        self.by_channel_result = None

    def deactivate_subscription_by_id(self, **kwargs):
        self.by_id_calls.append(kwargs)
        return self.by_id_result

    def deactivate_subscription_by_channel_id(self, **kwargs):
        self.by_channel_calls.append(kwargs)
        return self.by_channel_result


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
    bot = LearnerBot(settings=DummySettings(), queue=queue, watch_repository=DummyWatchRepository())

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
            "reply_message_id": None,
        }
    ]
    assert bot._queued_text(7, "https://www.youtube.com/watch?v=abc123xyz") == (
        "Queued job #7 for https://www.youtube.com/watch?v=abc123xyz"
    )


def test_server_scoped_auth_helpers() -> None:
    bot = LearnerBot(settings=DummySettings(), queue=DummyQueue(), watch_repository=DummyWatchRepository())

    guild_message = type("Message", (), {"guild": object()})()
    dm_message = type("Message", (), {"guild": None})()
    guild_interaction = type("Interaction", (), {"guild_id": 123, "channel": object()})()
    dm_interaction = type("Interaction", (), {"guild_id": None, "channel": object()})()
    admin_interaction = type(
        "Interaction",
        (),
        {"user": type("User", (), {"guild_permissions": type("Perms", (), {"manage_guild": True})()})()},
    )()
    non_admin_interaction = type(
        "Interaction",
        (),
        {"user": type("User", (), {"guild_permissions": type("Perms", (), {"manage_guild": False})()})()},
    )()

    assert bot._is_allowed_message(guild_message) is True
    assert bot._is_allowed_message(dm_message) is False
    assert bot._is_allowed_interaction(guild_interaction) is True
    assert bot._is_allowed_interaction(dm_interaction) is False
    assert bot._is_admin_interaction(admin_interaction) is True
    assert bot._is_admin_interaction(non_admin_interaction) is False


def test_remove_subscription_by_watch_id() -> None:
    watch_repository = DummyWatchRepository()
    watch_repository.by_id_result = type("Watch", (), {"youtube_channel_title": "AI Channel"})()
    bot = LearnerBot(settings=DummySettings(), queue=DummyQueue(), watch_repository=watch_repository)

    removed = bot._remove_subscription(guild_id="123", raw_reference="42")

    assert removed is watch_repository.by_id_result
    assert watch_repository.by_id_calls == [{"guild_id": "123", "subscription_id": 42}]
    assert watch_repository.by_channel_calls == []


def test_remove_subscription_by_channel_reference(monkeypatch) -> None:
    watch_repository = DummyWatchRepository()
    watch_repository.by_channel_result = type("Watch", (), {"youtube_channel_title": "AI Channel"})()
    bot = LearnerBot(settings=DummySettings(), queue=DummyQueue(), watch_repository=watch_repository)

    monkeypatch.setattr(
        "app.discord_bot.resolve_youtube_channel",
        lambda raw: type("Resolved", (), {"channel_id": "UC12345678901234567890"})(),
    )

    removed = bot._remove_subscription(guild_id="123", raw_reference="@example")

    assert removed is watch_repository.by_channel_result
    assert watch_repository.by_channel_calls == [
        {"guild_id": "123", "youtube_channel_id": "UC12345678901234567890"}
    ]


def test_format_subscription_list() -> None:
    bot = LearnerBot(settings=DummySettings(), queue=DummyQueue(), watch_repository=DummyWatchRepository())
    subscriptions = [
        type("Watch", (), {"id": 1, "youtube_channel_title": "AI", "discord_channel_id": 11})(),
        type("Watch", (), {"id": 2, "youtube_channel_title": "Robotics", "discord_channel_id": 22})(),
    ]

    formatted = bot._format_subscription_list(subscriptions)

    assert formatted == "#1 AI -> <#11>\n#2 Robotics -> <#22>"
