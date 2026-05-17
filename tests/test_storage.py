from datetime import datetime, timezone
import sqlite3

from app.storage import OutputStore, slugify


def test_slugify() -> None:
    assert slugify("Hello, World!") == "hello-world"


def test_save_and_reuse_existing(tmp_path) -> None:
    store = OutputStore(tmp_path / "outputs", tmp_path / "data" / "yt_learner.sqlite3")
    processed_at = datetime(2026, 5, 17, tzinfo=timezone.utc)

    first = store.save_markdown(
        title="Demo Video",
        video_id="abc123",
        source_url="https://www.youtube.com/watch?v=abc123",
        markdown="# Demo",
        requested_by="user-1",
        processed_at=processed_at,
    )
    second = store.save_markdown(
        title="Demo Video",
        video_id="abc123",
        source_url="https://www.youtube.com/watch?v=abc123",
        markdown="# Demo again",
        requested_by="user-1",
        processed_at=processed_at,
    )

    assert first.reused_existing is False
    assert second.reused_existing is True
    assert first.path.name == "2026-05-17__demo-video__abc123.md"
    assert second.path == first.path
    assert second.learning_record_id == first.learning_record_id

    conn = sqlite3.connect(tmp_path / "data" / "yt_learner.sqlite3")
    source_row = conn.execute(
        "SELECT source_type, source_key, source_ref, title FROM sources"
    ).fetchone()
    record_row = conn.execute(
        "SELECT title, artifact_path, requested_by FROM learning_records"
    ).fetchone()
    conn.close()

    assert source_row == (
        "youtube_url",
        "abc123",
        "https://www.youtube.com/watch?v=abc123",
        "Demo Video",
    )
    assert record_row == (
        "Demo Video",
        str(first.path),
        "user-1",
    )
