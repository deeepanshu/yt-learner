from app.job_queue import STATUS_DONE, STATUS_FAILED, STATUS_RUNNING, STATUS_QUEUED, JobQueue


def test_enqueue_and_claim_job(tmp_path) -> None:
    queue = JobQueue(tmp_path / "jobs.sqlite3")

    queued = queue.enqueue_summarize_video(
        video_url="https://www.youtube.com/watch?v=abc123xyz",
        requested_by="user-1",
        source="discord_message",
        reply_channel_id=12345,
        reply_message_id=67890,
    )
    claimed = queue.claim_next_job()

    assert queued.status == STATUS_QUEUED
    assert claimed is not None
    assert claimed.id == queued.id
    assert claimed.status == STATUS_RUNNING
    assert claimed.attempts == 1
    assert claimed.video_url == "https://www.youtube.com/watch?v=abc123xyz"
    assert claimed.reply_channel_id == 12345
    assert claimed.reply_message_id == 67890
    assert claimed.guild_id is None
    assert claimed.extra_prompt is None


def test_mark_done_and_failed(tmp_path) -> None:
    queue = JobQueue(tmp_path / "jobs.sqlite3")

    first = queue.enqueue_summarize_video(
        video_url="https://www.youtube.com/watch?v=abc123xyz",
        requested_by="user-1",
        source="discord_message",
        reply_channel_id=None,
    )
    second = queue.enqueue_summarize_video(
        video_url="https://www.youtube.com/watch?v=def456uvw",
        requested_by="user-1",
        source="discord_message",
        reply_channel_id=None,
    )

    queue.claim_next_job()
    done = queue.mark_done(first.id, learning_record_id=12, result_path="/tmp/result.md")
    queue.claim_next_job()
    failed = queue.mark_failed(second.id, error="boom")

    assert done.status == STATUS_DONE
    assert done.learning_record_id == 12
    assert done.result_path == "/tmp/result.md"
    assert failed.status == STATUS_FAILED
    assert failed.error == "boom"


def test_enqueue_job_stores_extra_prompt(tmp_path) -> None:
    queue = JobQueue(tmp_path / "jobs.sqlite3")

    queued = queue.enqueue_summarize_video(
        video_url="https://www.youtube.com/watch?v=abc123xyz",
        requested_by="user-1",
        source="discord_slash_command",
        reply_channel_id=12345,
        guild_id="guild-1",
        extra_prompt="focus on deployment advice",
    )

    assert queued.guild_id == "guild-1"
    assert queued.extra_prompt == "focus on deployment advice"
    assert queue.get_job(queued.id).guild_id == "guild-1"
    assert queue.get_job(queued.id).extra_prompt == "focus on deployment advice"


def test_enqueue_answer_video_question(tmp_path) -> None:
    queue = JobQueue(tmp_path / "jobs.sqlite3")

    queued = queue.enqueue_answer_video_question(
        video_id="abc123xyz",
        question="What about deployment?",
        requested_by="user-1",
        source="discord_thread_question",
        reply_channel_id=2002,
        reply_message_id=3333,
        guild_id="guild-1",
    )

    assert queued.video_id == "abc123xyz"
    assert queued.question == "What about deployment?"
    assert queued.reply_channel_id == 2002
    assert queued.reply_message_id == 3333
    assert queued.guild_id == "guild-1"


def test_update_reply_message_id(tmp_path) -> None:
    queue = JobQueue(tmp_path / "jobs.sqlite3")

    queued = queue.enqueue_summarize_video(
        video_url="https://www.youtube.com/watch?v=abc123xyz",
        requested_by="user-1",
        source="discord_slash_command",
        reply_channel_id=12345,
    )

    updated = queue.update_reply_message_id(queued.id, reply_message_id=67890)

    assert updated.reply_message_id == 67890
