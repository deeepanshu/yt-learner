from app.channel_watches import VideoThreadRepository


def test_save_and_find_video_thread(tmp_path) -> None:
    repository = VideoThreadRepository(tmp_path / "data" / "yt_learner.sqlite3")

    saved = repository.save_thread(
        guild_id="guild-1",
        parent_channel_id=1001,
        video_id="abc123xyz",
        thread_id=2002,
        title="Video Title",
    )
    found = repository.find_thread(
        guild_id="guild-1",
        parent_channel_id=1001,
        video_id="abc123xyz",
    )

    assert found == saved
    assert found is not None
    assert found.thread_id == 2002
    assert found.title == "Video Title"


def test_save_thread_updates_existing_mapping(tmp_path) -> None:
    repository = VideoThreadRepository(tmp_path / "data" / "yt_learner.sqlite3")

    first = repository.save_thread(
        guild_id="guild-1",
        parent_channel_id=1001,
        video_id="abc123xyz",
        thread_id=2002,
        title="Old Title",
    )
    updated = repository.save_thread(
        guild_id="guild-1",
        parent_channel_id=1001,
        video_id="abc123xyz",
        thread_id=3003,
        title="New Title",
    )

    assert updated.id == first.id
    assert updated.thread_id == 3003
    assert updated.title == "New Title"
