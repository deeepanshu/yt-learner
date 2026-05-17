from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.extractor import ExtractionError, ExtractionInput, LearningExtractor
from app.metadata import VideoMetadataError, fetch_video_metadata
from app.storage import OutputStore
from app.transcript import fetch_transcript
from app.youtube_urls import parse_youtube_url


@dataclass(frozen=True)
class ProcessedVideo:
    learning_record_id: int
    video_id: str
    title: str
    url: str
    output_path: Path
    reused_existing: bool


class VideoProcessor:
    def __init__(
        self,
        *,
        store: OutputStore,
        extractor: LearningExtractor,
        metadata_fetcher=fetch_video_metadata,
    ) -> None:
        self.store = store
        self.extractor = extractor
        self.metadata_fetcher = metadata_fetcher

    async def process_video(self, video_url: str, requested_by: str) -> ProcessedVideo:
        parsed = parse_youtube_url(video_url)
        existing = self.store.find_existing_learning_record(
            source_type="youtube_url",
            source_key=parsed.video_id,
        )
        if existing is not None:
            return ProcessedVideo(
                learning_record_id=existing.id,
                video_id=parsed.video_id,
                title=existing.title,
                url=parsed.canonical_url,
                output_path=existing.artifact_path,
                reused_existing=True,
            )

        try:
            metadata = self.metadata_fetcher(parsed.canonical_url)
            title = metadata.title
        except VideoMetadataError:
            title = f"youtube-video-{parsed.video_id}"

        transcript = fetch_transcript(parsed.video_id)
        try:
            markdown = await self.extractor.render_markdown(
                ExtractionInput(title=title, url=parsed.canonical_url, transcript=transcript)
            )
        except ExtractionError:
            self.store.save_transcript_debug(
                title=title,
                video_id=parsed.video_id,
                transcript_text=transcript.text,
            )
            raise
        stored = self.store.save_markdown(
            title=title,
            video_id=parsed.video_id,
            source_url=parsed.canonical_url,
            markdown=markdown,
            requested_by=requested_by,
        )
        return ProcessedVideo(
            learning_record_id=stored.learning_record_id,
            video_id=parsed.video_id,
            title=title,
            url=parsed.canonical_url,
            output_path=stored.path,
            reused_existing=stored.reused_existing,
        )
