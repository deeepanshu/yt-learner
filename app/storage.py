from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def slugify(value: str, *, fallback: str = "video") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return cleaned or fallback


@dataclass(frozen=True)
class StoredDocument:
    learning_record_id: int
    path: Path
    title: str
    reused_existing: bool


@dataclass(frozen=True)
class LearningRecord:
    id: int
    source_id: int
    source_type: str
    source_key: str
    source_ref: str
    record_type: str
    title: str
    artifact_path: Path
    requested_by: str | None
    created_at: datetime
    updated_at: datetime


def _serialize_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value)


class OutputStore:
    def __init__(self, root: Path, db_path: Path) -> None:
        self.root = root
        self.db_path = db_path
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def find_existing_learning_record(
        self,
        *,
        source_type: str,
        source_key: str,
        record_type: str = "notes",
    ) -> LearningRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    lr.id,
                    lr.source_id,
                    s.source_type,
                    s.source_key,
                    s.source_ref,
                    lr.record_type,
                    lr.title,
                    lr.artifact_path,
                    lr.requested_by,
                    lr.created_at,
                    lr.updated_at
                FROM learning_records AS lr
                JOIN sources AS s ON s.id = lr.source_id
                WHERE s.source_type = ? AND s.source_key = ? AND lr.record_type = ?
                """,
                (source_type, source_key, record_type),
            ).fetchone()

        if row is not None:
            record = self._row_to_learning_record(row)
            if record.artifact_path.exists():
                return record

        if source_type == "youtube_url":
            legacy_path = self._find_legacy_markdown(source_key)
            if legacy_path is None:
                return None
            return self._import_legacy_youtube_record(source_key=source_key, artifact_path=legacy_path)

        return None

    def find_existing(self, video_id: str) -> Path | None:
        record = self.find_existing_learning_record(source_type="youtube_url", source_key=video_id)
        if record is None:
            return None
        return record.artifact_path

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
        source_url: str,
        markdown: str,
        requested_by: str,
        processed_at: datetime | None = None,
    ) -> StoredDocument:
        existing = self.find_existing_learning_record(source_type="youtube_url", source_key=video_id)
        if existing is not None:
            return StoredDocument(
                learning_record_id=existing.id,
                path=existing.artifact_path,
                title=existing.title,
                reused_existing=True,
            )

        processed_timestamp = processed_at or datetime.now(timezone.utc)
        output_path = self.build_output_path(
            title=title,
            video_id=video_id,
            processed_at=processed_timestamp,
        )
        output_path.write_text(markdown, encoding="utf-8")
        learning_record_id = self._upsert_learning_record(
            source_type="youtube_url",
            source_key=video_id,
            source_ref=source_url,
            record_type="notes",
            title=title,
            artifact_path=output_path,
            requested_by=requested_by,
            processed_at=processed_timestamp,
        )
        return StoredDocument(
            learning_record_id=learning_record_id,
            path=output_path,
            title=title,
            reused_existing=False,
        )

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

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_type TEXT NOT NULL,
                    source_key TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    title TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(source_type, source_key)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS learning_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id INTEGER NOT NULL,
                    record_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    artifact_path TEXT NOT NULL,
                    requested_by TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(source_id, record_type),
                    FOREIGN KEY(source_id) REFERENCES sources(id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sources_type_key ON sources(source_type, source_key)"
            )

    def _upsert_learning_record(
        self,
        *,
        source_type: str,
        source_key: str,
        source_ref: str,
        record_type: str,
        title: str,
        artifact_path: Path,
        requested_by: str,
        processed_at: datetime,
    ) -> int:
        timestamp = _serialize_timestamp(processed_at)
        with self._connect() as conn:
            source_row = conn.execute(
                """
                INSERT INTO sources (source_type, source_key, source_ref, title, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_type, source_key)
                DO UPDATE SET
                    source_ref = excluded.source_ref,
                    title = excluded.title
                RETURNING id
                """,
                (source_type, source_key, source_ref, title, timestamp),
            ).fetchone()
            source_id = int(source_row["id"])
            record_row = conn.execute(
                """
                INSERT INTO learning_records (
                    source_id,
                    record_type,
                    title,
                    artifact_path,
                    requested_by,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id, record_type)
                DO UPDATE SET
                    title = excluded.title,
                    artifact_path = excluded.artifact_path,
                    requested_by = excluded.requested_by,
                    updated_at = excluded.updated_at
                RETURNING id
                """,
                (
                    source_id,
                    record_type,
                    title,
                    str(artifact_path),
                    requested_by,
                    timestamp,
                    timestamp,
                ),
            ).fetchone()
        return int(record_row["id"])

    def _find_legacy_markdown(self, video_id: str) -> Path | None:
        matches = sorted(self.root.glob(f"*__{video_id}.md"))
        return matches[0] if matches else None

    def _import_legacy_youtube_record(self, *, source_key: str, artifact_path: Path) -> LearningRecord | None:
        title = self.read_markdown_title(artifact_path) or artifact_path.stem
        record_id = self._upsert_learning_record(
            source_type="youtube_url",
            source_key=source_key,
            source_ref=f"https://www.youtube.com/watch?v={source_key}",
            record_type="notes",
            title=title,
            artifact_path=artifact_path,
            requested_by="legacy-import",
            processed_at=datetime.now(timezone.utc),
        )
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    lr.id,
                    lr.source_id,
                    s.source_type,
                    s.source_key,
                    s.source_ref,
                    lr.record_type,
                    lr.title,
                    lr.artifact_path,
                    lr.requested_by,
                    lr.created_at,
                    lr.updated_at
                FROM learning_records AS lr
                JOIN sources AS s ON s.id = lr.source_id
                WHERE lr.id = ?
                """,
                (record_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_learning_record(row)

    def _row_to_learning_record(self, row: sqlite3.Row) -> LearningRecord:
        return LearningRecord(
            id=int(row["id"]),
            source_id=int(row["source_id"]),
            source_type=str(row["source_type"]),
            source_key=str(row["source_key"]),
            source_ref=str(row["source_ref"]),
            record_type=str(row["record_type"]),
            title=str(row["title"]),
            artifact_path=Path(str(row["artifact_path"])),
            requested_by=row["requested_by"],
            created_at=_parse_timestamp(str(row["created_at"])),
            updated_at=_parse_timestamp(str(row["updated_at"])),
        )
