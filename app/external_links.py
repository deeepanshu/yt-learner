from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.db import as_datetime, connect

OUTLINE_PROVIDER = "outline"
YOUTUBE_CHANNEL_SOURCE = "youtube_channel"
YOUTUBE_VIDEO_SOURCE = "youtube_video"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ExternalDocumentLink:
    provider: str
    source_type: str
    source_key: str
    remote_id: str
    created_at: datetime
    updated_at: datetime


class ExternalDocumentLinkStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def get(self, *, provider: str, source_type: str, source_key: str) -> ExternalDocumentLink | None:
        with connect(self.database_url) as conn:
            row = conn.execute(
                """
                SELECT *
                FROM external_document_links
                WHERE provider = %s AND source_type = %s AND source_key = %s
                """,
                (provider, source_type, source_key),
            ).fetchone()
        return self._row_to_link(row) if row is not None else None

    def save(
        self,
        *,
        provider: str,
        source_type: str,
        source_key: str,
        remote_id: str,
    ) -> ExternalDocumentLink:
        timestamp = utc_now()
        with connect(self.database_url) as conn:
            row = conn.execute(
                """
                INSERT INTO external_document_links (
                    provider, source_type, source_key, remote_id, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (provider, source_type, source_key)
                DO UPDATE SET remote_id = excluded.remote_id, updated_at = excluded.updated_at
                RETURNING *
                """,
                (provider, source_type, source_key, remote_id, timestamp, timestamp),
            ).fetchone()
        if row is None:
            raise RuntimeError("Unable to save external document link")
        return self._row_to_link(row)

    def delete(self, *, provider: str, source_type: str, source_key: str) -> None:
        with connect(self.database_url) as conn:
            conn.execute(
                """
                DELETE FROM external_document_links
                WHERE provider = %s AND source_type = %s AND source_key = %s
                """,
                (provider, source_type, source_key),
            )

    def _row_to_link(self, row: dict[str, object]) -> ExternalDocumentLink:
        return ExternalDocumentLink(
            provider=str(row["provider"]),
            source_type=str(row["source_type"]),
            source_key=str(row["source_key"]),
            remote_id=str(row["remote_id"]),
            created_at=as_datetime(row["created_at"]) or utc_now(),
            updated_at=as_datetime(row["updated_at"]) or utc_now(),
        )
