from app.job_queue import STATUS_DONE, STATUS_FAILED, STATUS_RUNNING, STATUS_QUEUED, JobQueue


def test_enqueue_and_claim_job(database_url) -> None:
    queue = JobQueue(database_url)

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


def test_mark_done_and_failed(database_url) -> None:
    queue = JobQueue(database_url)

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
    done = queue.mark_done(first.id, learning_record_id=12, result_filename="result.md")
    queue.claim_next_job()
    failed = queue.mark_failed(second.id, error="boom")

    assert done.status == STATUS_DONE
    assert done.learning_record_id == 12
    assert done.result_filename == "result.md"
    assert failed.status == STATUS_FAILED
    assert failed.error == "boom"


def test_update_reply_message_id(database_url) -> None:
    queue = JobQueue(database_url)

    queued = queue.enqueue_summarize_video(
        video_url="https://www.youtube.com/watch?v=abc123xyz",
        requested_by="user-1",
        source="discord_slash_command",
        reply_channel_id=12345,
    )

    updated = queue.update_reply_message_id(queued.id, reply_message_id=67890)

    assert updated.reply_message_id == 67890
