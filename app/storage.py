from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def slugify(value: str, *, fallback: str = "video") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return cleaned or fallback


@dataclass(frozen=True)
class StoredDocument:
    path: Path
    reused_existing: bool


class OutputStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def find_existing(self, video_id: str) -> Path | None:
        matches = sorted(self.root.glob(f"*__{video_id}.md"))
        return matches[0] if matches else None

    def read_markdown_title(self, path: Path) -> str | None:
        try:
            with path.open(encoding="utf-8") as handle:
                first_line = handle.readline().strip()
        except OSError:
            return None

        if first_line.startswith("# "):
            return first_line[2:].strip() or None
        return None

    def build_output_path(
        self,
        *,
        title: str,
        video_id: str,
        processed_at: datetime | None = None,
    ) -> Path:
        timestamp = (processed_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
        filename = f"{timestamp}__{slugify(title)}__{video_id}.md"
        return self.root / filename

    def save_markdown(
        self,
        *,
        title: str,
        video_id: str,
        markdown: str,
        processed_at: datetime | None = None,
    ) -> StoredDocument:
        existing = self.find_existing(video_id)
        if existing is not None:
            return StoredDocument(path=existing, reused_existing=True)

        output_path = self.build_output_path(
            title=title,
            video_id=video_id,
            processed_at=processed_at,
        )
        output_path.write_text(markdown, encoding="utf-8")
        return StoredDocument(path=output_path, reused_existing=False)

    def save_transcript_debug(
        self,
        *,
        title: str,
        video_id: str,
        transcript_text: str,
        processed_at: datetime | None = None,
    ) -> Path:
        timestamp = (processed_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
        filename = f"{timestamp}__{slugify(title)}__{video_id}.transcript.txt"
        output_path = self.root / filename
        output_path.write_text(transcript_text, encoding="utf-8")
        return output_path
