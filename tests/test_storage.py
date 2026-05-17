from datetime import datetime, timezone

from app.storage import OutputStore, slugify


def test_slugify() -> None:
    assert slugify("Hello, World!") == "hello-world"


def test_save_and_reuse_existing(tmp_path) -> None:
    store = OutputStore(tmp_path)
    processed_at = datetime(2026, 5, 17, tzinfo=timezone.utc)

    first = store.save_markdown(
        title="Demo Video",
        video_id="abc123",
        markdown="# Demo",
        processed_at=processed_at,
    )
    second = store.save_markdown(
        title="Demo Video",
        video_id="abc123",
        markdown="# Demo again",
        processed_at=processed_at,
    )

    assert first.reused_existing is False
    assert second.reused_existing is True
    assert first.path.name == "2026-05-17__demo-video__abc123.md"
    assert second.path == first.path
