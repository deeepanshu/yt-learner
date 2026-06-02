from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.extractor import ExtractionError, ExtractionInput
from app.metadata import VideoMetadataError, fetch_video_metadata
from app.storage import OutputStore
from app.transcript import fetch_transcript
from app.youtube_urls import parse_youtube_url


def _prompt_hash(extra_prompt: str | None) -> str | None:
    if not extra_prompt:
        return None
    return hashlib.sha256(extra_prompt.encode("utf-8")).hexdigest()[:12]


class ExtractorProtocol(Protocol):
    async def render_markdown(self, payload: ExtractionInput) -> str: ...

    async def answer_question(
        self,
        *,
        title: str,
        url: str,
        transcript_text: str,
        question: str,
    ) -> str: ...


@dataclass(frozen=True)
class AnsweredVideoQuestion:
    learning_record_id: int | None
    video_id: str
    title: str
    url: str
    markdown: str


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
        extractor: ExtractorProtocol,
        metadata_fetcher=fetch_video_metadata,
    ) -> None:
        self.store = store
        self.extractor = extractor
        self.metadata_fetcher = metadata_fetcher

    async def answer_video_question(self, *, video_id: str, question: str, requested_by: str) -> AnsweredVideoQuestion:
        existing = self.store.find_existing_learning_record(
            source_type="youtube_url",
            source_key=video_id,
            record_type="notes",
        )
        url = f"https://www.youtube.com/watch?v={video_id}"
        if existing is not None:
            title = existing.title
            url = existing.source_ref
        else:
            try:
                metadata = self.metadata_fetcher(url)
                title = metadata.title
            except VideoMetadataError:
                title = f"youtube-video-{video_id}"

        transcript_text = self.store.find_transcript_text(video_id)
        if transcript_text is None:
            transcript = fetch_transcript(video_id)
            transcript_text = transcript.text
            self.store.save_transcript(
                title=title,
                video_id=video_id,
                source_url=url,
                transcript_text=transcript_text,
                requested_by=requested_by,
            )

        markdown = await self.extractor.answer_question(
            title=title,
            url=url,
            transcript_text=transcript_text,
            question=question,
        )
        return AnsweredVideoQuestion(
            learning_record_id=existing.id if existing is not None else None,
            video_id=video_id,
            title=title,
            url=url,
            markdown=markdown,
        )

    async def process_video(
        self,
        video_url: str,
        requested_by: str,
        extra_prompt: str | None = None,
    ) -> ProcessedVideo:
        parsed = parse_youtube_url(video_url)
        prompt_hash = _prompt_hash(extra_prompt)
        record_type = "notes" if prompt_hash is None else f"notes:prompt:{prompt_hash}"
        filename_suffix = None if prompt_hash is None else f"prompt-{prompt_hash}"
        existing = self.store.find_existing_learning_record(
            source_type="youtube_url",
            source_key=parsed.video_id,
            record_type=record_type,
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
        self.store.save_transcript(
            title=title,
            video_id=parsed.video_id,
            source_url=parsed.canonical_url,
            transcript_text=transcript.text,
            requested_by=requested_by,
        )
        try:
            markdown = await self.extractor.render_markdown(
                ExtractionInput(
                    title=title,
                    url=parsed.canonical_url,
                    transcript=transcript,
                    extra_prompt=extra_prompt,
                )
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
            record_type=record_type,
            filename_suffix=filename_suffix,
        )
        return ProcessedVideo(
            learning_record_id=stored.learning_record_id,
            video_id=parsed.video_id,
            title=title,
            url=parsed.canonical_url,
            output_path=stored.path,
            reused_existing=stored.reused_existing,
        )
