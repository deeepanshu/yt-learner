from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.extractor import ExtractionError
from app.metadata import VideoMetadata
from app.pipeline import VideoProcessor
from app.storage import OutputStore
from app.transcript import TranscriptData, TranscriptSegment


@dataclass
class StubExtractor:
    last_title: str | None = None

    async def render_markdown(self, payload) -> str:
        self.last_title = payload.title
        return f"# {payload.title}\n\nSource: {payload.url}\n"


@dataclass
class FailingExtractor:
    async def render_markdown(self, payload) -> str:
        raise ExtractionError("boom")


def test_process_video_uses_fetched_metadata_title(database_url, monkeypatch) -> None:
    transcript = TranscriptData(segments=[TranscriptSegment(start_seconds=0, text="hello")])
    monkeypatch.setattr("app.pipeline.fetch_transcript", lambda video_id: transcript)

    extractor = StubExtractor()
    processor = VideoProcessor(
        store=OutputStore(database_url),
        extractor=extractor,
        metadata_fetcher=lambda url: VideoMetadata(title="Real Video Title"),
    )

    result = run_async(
        processor.process_video("https://www.youtube.com/watch?v=abc123xyz", requested_by="user-1")
    )

    assert result.title == "Real Video Title"
    assert extractor.last_title == "Real Video Title"
    assert result.filename.endswith("__real-video-title__abc123xyz.md")
    assert result.markdown.startswith("# Real Video Title")


def test_process_video_reuses_existing_markdown_title(database_url, monkeypatch) -> None:
    store = OutputStore(database_url)
    store.save_markdown(
        title="Existing Human Title",
        video_id="abc123xyz",
        source_url="https://www.youtube.com/watch?v=abc123xyz",
        markdown="# Existing Human Title\n\nBody\n",
        requested_by="user-1",
        processed_at=datetime(2026, 5, 17, tzinfo=timezone.utc),
    )

    monkeypatch.setattr("app.pipeline.fetch_transcript", lambda video_id: None)

    processor = VideoProcessor(
        store=store,
        extractor=StubExtractor(),
        metadata_fetcher=lambda url: VideoMetadata(title="Ignored Title"),
    )

    result = run_async(
        processor.process_video(
            "https://www.youtube.com/watch?v=abc123xyz",
            requested_by="user-1",
        )
    )

    assert result.reused_existing is True
    assert result.title == "Existing Human Title"
    assert result.markdown == "# Existing Human Title\n\nBody\n"
    assert result.filename == "2026-05-17__existing-human-title__abc123xyz.md"


def test_process_video_saves_transcript_debug_on_extraction_failure(database_url, monkeypatch) -> None:
    transcript = TranscriptData(
        segments=[
            TranscriptSegment(start_seconds=0, text="line one"),
            TranscriptSegment(start_seconds=12, text="line two"),
        ]
    )
    monkeypatch.setattr("app.pipeline.fetch_transcript", lambda video_id: transcript)
    store = OutputStore(database_url)

    processor = VideoProcessor(
        store=store,
        extractor=FailingExtractor(),
        metadata_fetcher=lambda url: VideoMetadata(title="Debug Title"),
    )

    try:
        run_async(
            processor.process_video("https://www.youtube.com/watch?v=abc123xyz", requested_by="user-1")
        )
    except ExtractionError:
        pass
    else:
        raise AssertionError("Expected ExtractionError")

    debug = store.get_latest_debug_artifact(source_type="youtube_url", source_key="abc123xyz")
    assert debug is not None
    assert debug.body == "line one\nline two"


def run_async(awaitable):
    import asyncio

    return asyncio.run(awaitable)
