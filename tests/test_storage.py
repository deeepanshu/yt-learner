from datetime import datetime, timezone

from app.storage import OutputStore, slugify


def test_slugify() -> None:
    assert slugify("Hello, World!") == "hello-world"


def test_save_and_reuse_existing(database_url) -> None:
    store = OutputStore(database_url)
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

    record = store.find_existing_learning_record(source_type="youtube_url", source_key="abc123")

    assert first.reused_existing is False
    assert second.reused_existing is True
    assert first.filename == "2026-05-17__demo-video__abc123.md"
    assert second.filename == first.filename
    assert second.markdown == "# Demo"
    assert second.learning_record_id == first.learning_record_id
    assert record is not None
    assert record.markdown == "# Demo"
    assert record.requested_by == "user-1"
    assert record.source_ref == "https://www.youtube.com/watch?v=abc123"
