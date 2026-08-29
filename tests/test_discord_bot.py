from typing import cast

import discord

from app.channel_watches import DiscordThreadRepository, WatchRepository
from app.config import Settings
from app.discord_bot import LearnerBot, extract_youtube_url, normalize_extra_prompt
from app.job_queue import JobQueue


def dummy_settings() -> Settings:
    return Settings(
        openai_api_key="key",
        discord_bot_token="token",
        database_url="postgres://yt_learner:yt_learner@127.0.0.1:55432/yt_learner_test",
        discord_allowed_user_id=None,
    )


def make_bot(
    *,
    queue: "DummyQueue | None" = None,
    watch_repository: "DummyWatchRepository | None" = None,
    discord_thread_repository: "DummyDiscordThreadRepository | None" = None,
) -> LearnerBot:
    return LearnerBot(
        settings=dummy_settings(),
        queue=cast(JobQueue, queue or DummyQueue()),
        watch_repository=cast(WatchRepository, watch_repository or DummyWatchRepository()),
        discord_thread_repository=cast(
            DiscordThreadRepository,
            discord_thread_repository or DummyDiscordThreadRepository(),
        ),
    )


class DummyQueue:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.reply_updates: list[tuple[int, int]] = []

    def enqueue_summarize_video(self, **kwargs):
        self.calls.append(kwargs)
        return type("Job", (), {"id": 7})()

    def update_reply_message_id(self, job_id: int, *, reply_message_id: int):
        self.reply_updates.append((job_id, reply_message_id))
        return type("Job", (), {"id": job_id})()

    def enqueue_answer_video_question(self, **kwargs):
        self.calls.append(kwargs)
        return type("Job", (), {"id": 9})()


class DummyDiscordThreadRecord:
    video_id = "abc123xyz"
    guild_id = "guild-1"


class DummyDiscordThreadRepository:
    def __init__(self) -> None:
        self.thread_record: object | None = None

    def find_thread_by_thread_id(self, thread_id: int):
        return self.thread_record


class FakeQuestionChannel:
    id = 2002

    def __init__(self) -> None:
        self.sent: list[tuple[str | None, object | None, bool | None]] = []

    async def send(self, content=None, reference=None, mention_author=None):
        self.sent.append((content, reference, mention_author))
        return type("Message", (), {"id": 4444})()


class DummyWatchRepository:
    def __init__(self) -> None:
        self.by_id_calls: list[dict[str, object]] = []
        self.by_channel_calls: list[dict[str, object]] = []
        self.by_id_result: object | None = None
        self.by_channel_result: object | None = None

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
    bot = make_bot(queue=queue)

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
            "guild_id": None,
            "extra_prompt": None,
        }
    ]
    assert bot._learning_status_text("https://www.youtube.com/watch?v=abc123xyz", None) == (
        "Learning from https://www.youtube.com/watch?v=abc123xyz"
    )
    assert bot._learning_status_text(
        "https://www.youtube.com/watch?v=abc123xyz",
        "focus on deployment advice",
    ) == "Checking 'focus on deployment advice' from https://www.youtube.com/watch?v=abc123xyz"


def test_enqueue_job_forwards_normalized_extra_prompt() -> None:
    queue = DummyQueue()
    bot = make_bot(queue=queue)

    bot._enqueue_job(
        video_url="https://www.youtube.com/watch?v=abc123xyz",
        requested_by="42",
        source="discord_slash_command",
        reply_channel_id=999,
        guild_id="guild-1",
        extra_prompt="  focus   on deployment advice  ",
    )

    assert queue.calls[0]["guild_id"] == "guild-1"
    assert queue.calls[0]["extra_prompt"] == "focus on deployment advice"


def test_normalize_extra_prompt_handles_empty_values() -> None:
    assert normalize_extra_prompt(None) is None
    assert normalize_extra_prompt("   ") is None


def test_thread_question_is_enqueued() -> None:
    queue = DummyQueue()
    discord_threads = DummyDiscordThreadRepository()
    discord_threads.thread_record = DummyDiscordThreadRecord()
    bot = make_bot(queue=queue, discord_thread_repository=discord_threads)
    channel = FakeQuestionChannel()
    message = type(
        "Message",
        (),
        {
            "content": "What did they say about deployment?",
            "id": 3333,
            "channel": channel,
            "author": type("User", (), {"id": 42})(),
            "guild": type("Guild", (), {"id": "guild-1"})(),
        },
    )()

    handled = run_async(bot._maybe_enqueue_thread_question(cast(discord.Message, message)))

    assert handled is True
    assert queue.calls == [
        {
            "video_id": "abc123xyz",
            "question": "What did they say about deployment?",
            "requested_by": "42",
            "source": "discord_thread_question",
            "reply_channel_id": 2002,
            "reply_message_id": 3333,
            "guild_id": "guild-1",
        }
    ]
    assert queue.reply_updates == [(9, 4444)]
    assert channel.sent == [("Thinking...", message, False)]


def run_async(awaitable):
    import asyncio

    return asyncio.run(awaitable)


def test_server_scoped_auth_helpers() -> None:
    bot = make_bot()

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

    assert bot._is_allowed_message(cast(discord.Message, guild_message)) is True
    assert bot._is_allowed_message(cast(discord.Message, dm_message)) is False
    assert bot._is_allowed_interaction(cast(discord.Interaction, guild_interaction)) is True
    assert bot._is_allowed_interaction(cast(discord.Interaction, dm_interaction)) is False
    assert bot._is_admin_interaction(cast(discord.Interaction, admin_interaction)) is True
    assert bot._is_admin_interaction(cast(discord.Interaction, non_admin_interaction)) is False


def test_remove_subscription_by_watch_id() -> None:
    watch_repository = DummyWatchRepository()
    watch_repository.by_id_result = type("Watch", (), {"youtube_channel_title": "AI Channel"})()
    bot = make_bot(watch_repository=watch_repository)

    removed = bot._remove_subscription(guild_id="123", raw_reference="42")

    assert removed is watch_repository.by_id_result
    assert watch_repository.by_id_calls == [{"guild_id": "123", "subscription_id": 42}]
    assert watch_repository.by_channel_calls == []


def test_remove_subscription_by_channel_reference(monkeypatch) -> None:
    watch_repository = DummyWatchRepository()
    watch_repository.by_channel_result = type("Watch", (), {"youtube_channel_title": "AI Channel"})()
    bot = make_bot(watch_repository=watch_repository)

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
    bot = make_bot()
    subscriptions = [
        type("Watch", (), {"id": 1, "youtube_channel_title": "AI", "discord_channel_id": 11})(),
        type("Watch", (), {"id": 2, "youtube_channel_title": "Robotics", "discord_channel_id": 22})(),
    ]

    formatted = bot._format_subscription_list(subscriptions)

    assert formatted == "#1 AI -> <#11>\n#2 Robotics -> <#22>"
