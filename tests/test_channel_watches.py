from app.channel_watches import WatchRepository


def test_add_list_and_deactivate_subscription(tmp_path) -> None:
    repository = WatchRepository(tmp_path / "data" / "yt_learner.sqlite3")

    first = repository.add_or_update_subscription(
        guild_id="guild-1",
        youtube_channel_id="UC12345678901234567890",
        youtube_channel_ref="https://www.youtube.com/channel/UC12345678901234567890",
        youtube_channel_title="AI Channel",
        discord_channel_id=1001,
    )
    second = repository.add_or_update_subscription(
        guild_id="guild-1",
        youtube_channel_id="UC09876543210987654321",
        youtube_channel_ref="https://www.youtube.com/channel/UC09876543210987654321",
        youtube_channel_title="Robotics Channel",
        discord_channel_id=1002,
    )

    listed = repository.list_subscriptions(guild_id="guild-1")
    removed = repository.deactivate_subscription_by_id(guild_id="guild-1", subscription_id=first.id)
    active = repository.get_active_subscriptions()

    assert [subscription.id for subscription in listed] == [first.id, second.id]
    assert removed is not None
    assert removed.id == first.id
    assert [subscription.id for subscription in active] == [second.id]


def test_reactivate_existing_subscription_updates_route(tmp_path) -> None:
    repository = WatchRepository(tmp_path / "data" / "yt_learner.sqlite3")

    original = repository.add_or_update_subscription(
        guild_id="guild-1",
        youtube_channel_id="UC12345678901234567890",
        youtube_channel_ref="https://www.youtube.com/channel/UC12345678901234567890",
        youtube_channel_title="AI Channel",
        discord_channel_id=1001,
    )
    repository.deactivate_subscription_by_channel_id(
        guild_id="guild-1",
        youtube_channel_id="UC12345678901234567890",
    )

    updated = repository.add_or_update_subscription(
        guild_id="guild-1",
        youtube_channel_id="UC12345678901234567890",
        youtube_channel_ref="https://www.youtube.com/channel/UC12345678901234567890",
        youtube_channel_title="AI Channel",
        discord_channel_id=2002,
    )

    assert updated.id == original.id
    assert updated.discord_channel_id == 2002
    assert updated.is_active is True


def test_record_discovered_video_is_idempotent(tmp_path) -> None:
    repository = WatchRepository(tmp_path / "data" / "yt_learner.sqlite3")
    subscription = repository.add_or_update_subscription(
        guild_id="guild-1",
        youtube_channel_id="UC12345678901234567890",
        youtube_channel_ref="https://www.youtube.com/channel/UC12345678901234567890",
        youtube_channel_title="AI Channel",
        discord_channel_id=1001,
    )

    first = repository.record_discovered_video(
        subscription_id=subscription.id,
        video_id="abc123xyz",
        video_url="https://www.youtube.com/watch?v=abc123xyz",
        title="Demo",
        published_at=None,
    )
    second = repository.record_discovered_video(
        subscription_id=subscription.id,
        video_id="abc123xyz",
        video_url="https://www.youtube.com/watch?v=abc123xyz",
        title="Demo",
        published_at=None,
    )

    videos = repository.list_discovered_videos(subscription_id=subscription.id)

    assert first is True
    assert second is False
    assert len(videos) == 1
