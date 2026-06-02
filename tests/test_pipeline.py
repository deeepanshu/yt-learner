from __future__ import annotations

from dataclasses import dataclass

from app.extractor import ExtractionError, ExtractionInput
from app.metadata import VideoMetadata
from app.pipeline import VideoProcessor
from app.storage import OutputStore
from app.transcript import TranscriptData, TranscriptSegment


@dataclass
class StubExtractor:
    last_title: str | None = None
    last_extra_prompt: str | None = None
    last_question: str | None = None

    async def render_markdown(self, payload: ExtractionInput) -> str:
        self.last_title = payload.title
        self.last_extra_prompt = payload.extra_prompt
        return f"# {payload.title}\n\nSource: {payload.url}\n"

    async def answer_question(
        self,
        *,
        title: str,
        url: str,
        transcript_text: str,
        question: str,
    ) -> str:
        self.last_title = title
        self.last_question = question
        return f"Answer: {question}"


@dataclass
class FailingExtractor:
    async def render_markdown(self, payload: ExtractionInput) -> str:
        raise ExtractionError("boom")

    async def answer_question(
        self,
        *,
        title: str,
        url: str,
        transcript_text: str,
        question: str,
    ) -> str:
        raise ExtractionError("boom")


def test_process_video_uses_fetched_metadata_title(tmp_path, monkeypatch) -> None:
    transcript = TranscriptData(segments=[TranscriptSegment(start_seconds=0, text="hello")])
    monkeypatch.setattr("app.pipeline.fetch_transcript", lambda video_id: transcript)

    extractor = StubExtractor()
    processor = VideoProcessor(
        store=OutputStore(tmp_path / "outputs", tmp_path / "data" / "yt_learner.sqlite3"),
        extractor=extractor,
        metadata_fetcher=lambda url: VideoMetadata(title="Real Video Title"),
    )

    result = run_async(
        processor.process_video("https://www.youtube.com/watch?v=abc123xyz", requested_by="user-1")
    )

    assert result.title == "Real Video Title"
    assert extractor.last_title == "Real Video Title"
    assert result.output_path.name.endswith("__real-video-title__abc123xyz.md")
    assert processor.store.find_transcript_text("abc123xyz") == "hello"


def test_process_video_reuses_existing_markdown_title(tmp_path, monkeypatch) -> None:
    store = OutputStore(tmp_path / "outputs", tmp_path / "data" / "yt_learner.sqlite3")
    existing = tmp_path / "outputs" / "2026-05-17__slug__abc123xyz.md"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text("# Existing Human Title\n\nBody\n", encoding="utf-8")

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
    assert result.output_path == existing


def test_process_video_creates_separate_prompted_artifact(tmp_path, monkeypatch) -> None:
    transcript = TranscriptData(segments=[TranscriptSegment(start_seconds=0, text="hello")])
    monkeypatch.setattr("app.pipeline.fetch_transcript", lambda video_id: transcript)

    store = OutputStore(tmp_path / "outputs", tmp_path / "data" / "yt_learner.sqlite3")
    extractor = StubExtractor()
    processor = VideoProcessor(
        store=store,
        extractor=extractor,
        metadata_fetcher=lambda url: VideoMetadata(title="Real Video Title"),
    )

    generic = run_async(
        processor.process_video("https://www.youtube.com/watch?v=abc123xyz", requested_by="user-1")
    )
    prompted = run_async(
        processor.process_video(
            "https://www.youtube.com/watch?v=abc123xyz",
            requested_by="user-1",
            extra_prompt="focus on deployment advice",
        )
    )

    assert generic.output_path != prompted.output_path
    assert generic.output_path.name.endswith("__real-video-title__abc123xyz.md")
    assert "__abc123xyz__prompt-" in prompted.output_path.name
    assert extractor.last_extra_prompt == "focus on deployment advice"
    assert prompted.reused_existing is False


def test_process_video_reuses_matching_prompted_artifact(tmp_path, monkeypatch) -> None:
    transcript = TranscriptData(segments=[TranscriptSegment(start_seconds=0, text="hello")])
    monkeypatch.setattr("app.pipeline.fetch_transcript", lambda video_id: transcript)

    extractor = StubExtractor()
    processor = VideoProcessor(
        store=OutputStore(tmp_path / "outputs", tmp_path / "data" / "yt_learner.sqlite3"),
        extractor=extractor,
        metadata_fetcher=lambda url: VideoMetadata(title="Real Video Title"),
    )

    first = run_async(
        processor.process_video(
            "https://www.youtube.com/watch?v=abc123xyz",
            requested_by="user-1",
            extra_prompt="focus on deployment advice",
        )
    )
    second = run_async(
        processor.process_video(
            "https://www.youtube.com/watch?v=abc123xyz",
            requested_by="user-2",
            extra_prompt="focus on deployment advice",
        )
    )

    assert second.reused_existing is True
    assert second.output_path == first.output_path


def test_answer_video_question_uses_saved_transcript(tmp_path, monkeypatch) -> None:
    store = OutputStore(tmp_path / "outputs", tmp_path / "data" / "yt_learner.sqlite3")
    store.save_markdown(
        title="Real Video Title",
        video_id="abc123xyz",
        source_url="https://www.youtube.com/watch?v=abc123xyz",
        markdown="# Real Video Title",
        requested_by="user-1",
    )
    store.save_transcript(
        title="Real Video Title",
        video_id="abc123xyz",
        source_url="https://www.youtube.com/watch?v=abc123xyz",
        transcript_text="saved transcript",
        requested_by="user-1",
    )
    extractor = StubExtractor()
    processor = VideoProcessor(
        store=store,
        extractor=extractor,
        metadata_fetcher=lambda url: VideoMetadata(title="Ignored Title"),
    )

    result = run_async(
        processor.answer_video_question(
            video_id="abc123xyz",
            question="What about deployment?",
            requested_by="user-2",
        )
    )

    assert result.title == "Real Video Title"
    assert result.markdown == "Answer: What about deployment?"
    assert extractor.last_question == "What about deployment?"


def test_process_video_saves_transcript_debug_on_extraction_failure(tmp_path, monkeypatch) -> None:
    transcript = TranscriptData(
        segments=[
            TranscriptSegment(start_seconds=0, text="line one"),
            TranscriptSegment(start_seconds=12, text="line two"),
        ]
    )
    monkeypatch.setattr("app.pipeline.fetch_transcript", lambda video_id: transcript)

    processor = VideoProcessor(
        store=OutputStore(tmp_path / "outputs", tmp_path / "data" / "yt_learner.sqlite3"),
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

    debug_files = list((tmp_path / "outputs").glob("*.transcript.txt"))
    assert len(debug_files) == 1
    assert debug_files[0].read_text(encoding="utf-8") == "line one\nline two"


def run_async(awaitable):
    import asyncio

    return asyncio.run(awaitable)
