from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from app.db import as_datetime, connect


def slugify(value: str, *, fallback: str = "video") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return cleaned or fallback


@dataclass(frozen=True)
class StoredDocument:
    learning_record_id: int
    filename: str
    markdown: str
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
    filename: str
    markdown: str
    requested_by: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class DebugArtifact:
    id: int
    source_type: str
    source_key: str
    artifact_type: str
    filename: str
    body: str
    created_at: datetime


class OutputStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def find_existing_learning_record(
        self,
        *,
        source_type: str,
        source_key: str,
        record_type: str = "notes",
    ) -> LearningRecord | None:
        with connect(self.database_url) as conn:
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
                    lr.filename,
                    lr.markdown,
                    lr.requested_by,
                    lr.created_at,
                    lr.updated_at
                FROM learning_records AS lr
                JOIN sources AS s ON s.id = lr.source_id
                WHERE s.source_type = %s AND s.source_key = %s AND lr.record_type = %s
                """,
                (source_type, source_key, record_type),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_learning_record(row)

    def build_output_filename(
        self,
        *,
        title: str,
        video_id: str,
        processed_at: datetime | None = None,
        filename_suffix: str | None = None,
    ) -> str:
        timestamp = (processed_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
        suffix = f"__{slugify(filename_suffix)}" if filename_suffix else ""
        return f"{timestamp}__{slugify(title)}__{video_id}{suffix}.md"

    def save_markdown(
        self,
        *,
        title: str,
        video_id: str,
        source_url: str,
        markdown: str,
        requested_by: str,
        processed_at: datetime | None = None,
        record_type: str = "notes",
        filename_suffix: str | None = None,
    ) -> StoredDocument:
        existing = self.find_existing_learning_record(
            source_type="youtube_url",
            source_key=video_id,
            record_type=record_type,
        )
        if existing is not None:
            return StoredDocument(
                learning_record_id=existing.id,
                filename=existing.filename,
                markdown=existing.markdown,
                title=existing.title,
                reused_existing=True,
            )

        processed_timestamp = processed_at or datetime.now(timezone.utc)
        filename = self.build_output_filename(
            title=title,
            video_id=video_id,
            processed_at=processed_timestamp,
            filename_suffix=filename_suffix,
        )
        learning_record_id = self._upsert_learning_record(
            source_type="youtube_url",
            source_key=video_id,
            source_ref=source_url,
            record_type=record_type,
            title=title,
            filename=filename,
            markdown=markdown,
            requested_by=requested_by,
            processed_at=processed_timestamp,
        )
        return StoredDocument(
            learning_record_id=learning_record_id,
            filename=filename,
            markdown=markdown,
            title=title,
            reused_existing=False,
        )

    def save_transcript(
        self,
        *,
        title: str,
        video_id: str,
        source_url: str,
        transcript_text: str,
        requested_by: str,
        processed_at: datetime | None = None,
    ) -> StoredDocument:
        processed_timestamp = processed_at or datetime.now(timezone.utc)
        filename = f"{processed_timestamp.strftime('%Y-%m-%d')}__{slugify(title)}__{video_id}.transcript.txt"
        existing = self.find_existing_learning_record(
            source_type="youtube_url",
            source_key=video_id,
            record_type="transcript",
        )
        if existing is not None:
            return StoredDocument(
                learning_record_id=existing.id,
                filename=existing.filename,
                markdown=existing.markdown,
                title=existing.title,
                reused_existing=True,
            )
        learning_record_id = self._upsert_learning_record(
            source_type="youtube_url",
            source_key=video_id,
            source_ref=source_url,
            record_type="transcript",
            title=title,
            filename=filename,
            markdown=transcript_text,
            requested_by=requested_by,
            processed_at=processed_timestamp,
        )
        return StoredDocument(
            learning_record_id=learning_record_id,
            filename=filename,
            markdown=transcript_text,
            title=title,
            reused_existing=False,
        )

    def find_transcript_text(self, video_id: str) -> str | None:
        record = self.find_existing_learning_record(
            source_type="youtube_url",
            source_key=video_id,
            record_type="transcript",
        )
        if record is None:
            return None
        return record.markdown

    def save_transcript_debug(
        self,
        *,
        title: str,
        video_id: str,
        transcript_text: str,
        processed_at: datetime | None = None,
    ) -> DebugArtifact:
        timestamp = processed_at or datetime.now(timezone.utc)
        filename = f"{timestamp.strftime('%Y-%m-%d')}__{slugify(title)}__{video_id}.transcript.txt"
        with connect(self.database_url) as conn:
            row = conn.execute(
                """
                INSERT INTO debug_artifacts (
                    source_type,
                    source_key,
                    artifact_type,
                    filename,
                    body,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                ("youtube_url", video_id, "transcript", filename, transcript_text, timestamp),
            ).fetchone()
        if row is None:
            raise RuntimeError("Unable to save debug artifact")
        return self._row_to_debug_artifact(row)

    def get_latest_debug_artifact(
        self,
        *,
        source_type: str,
        source_key: str,
        artifact_type: str = "transcript",
    ) -> DebugArtifact | None:
        with connect(self.database_url) as conn:
            row = conn.execute(
                """
                SELECT *
                FROM debug_artifacts
                WHERE source_type = %s AND source_key = %s AND artifact_type = %s
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (source_type, source_key, artifact_type),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_debug_artifact(row)

    def _upsert_learning_record(
        self,
        *,
        source_type: str,
        source_key: str,
        source_ref: str,
        record_type: str,
        title: str,
        filename: str,
        markdown: str,
        requested_by: str,
        processed_at: datetime,
    ) -> int:
        with connect(self.database_url) as conn:
            source_row = conn.execute(
                """
                INSERT INTO sources (source_type, source_key, source_ref, title, created_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (source_type, source_key)
                DO UPDATE SET
                    source_ref = excluded.source_ref,
                    title = excluded.title
                RETURNING id
                """,
                (source_type, source_key, source_ref, title, processed_at),
            ).fetchone()
            if source_row is None:
                raise RuntimeError("Unable to upsert source")
            source_id = int(source_row["id"])
            record_row = conn.execute(
                """
                INSERT INTO learning_records (
                    source_id,
                    record_type,
                    title,
                    filename,
                    markdown,
                    requested_by,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_id, record_type)
                DO UPDATE SET
                    title = excluded.title,
                    filename = excluded.filename,
                    markdown = excluded.markdown,
                    requested_by = excluded.requested_by,
                    updated_at = excluded.updated_at
                RETURNING id
                """,
                (
                    source_id,
                    record_type,
                    title,
                    filename,
                    markdown,
                    requested_by,
                    processed_at,
                    processed_at,
                ),
            ).fetchone()
        if record_row is None:
            raise RuntimeError("Unable to upsert learning record")
        return int(record_row["id"])

    def _row_to_learning_record(self, row: dict[str, object]) -> LearningRecord:
        requested_by = row["requested_by"]
        return LearningRecord(
            id=int(row["id"]),
            source_id=int(row["source_id"]),
            source_type=str(row["source_type"]),
            source_key=str(row["source_key"]),
            source_ref=str(row["source_ref"]),
            record_type=str(row["record_type"]),
            title=str(row["title"]),
            filename=str(row["filename"]),
            markdown=str(row["markdown"]),
            requested_by=str(requested_by) if requested_by is not None else None,
            created_at=as_datetime(row["created_at"]) or datetime.now(timezone.utc),
            updated_at=as_datetime(row["updated_at"]) or datetime.now(timezone.utc),
        )

    def _row_to_debug_artifact(self, row: dict[str, object]) -> DebugArtifact:
        return DebugArtifact(
            id=int(row["id"]),
            source_type=str(row["source_type"]),
            source_key=str(row["source_key"]),
            artifact_type=str(row["artifact_type"]),
            filename=str(row["filename"]),
            body=str(row["body"]),
            created_at=as_datetime(row["created_at"]) or datetime.now(timezone.utc),
        )
