from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


@dataclass(frozen=True)
class WatchedChannel:
    id: int
    guild_id: str
    youtube_channel_id: str
    youtube_channel_ref: str
    youtube_channel_title: str
    discord_channel_id: int
    is_active: bool
    bootstrap_completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class WatchedVideo:
    id: int
    watched_channel_id: int
    video_id: str
    video_url: str
    title: str
    published_at: datetime | None
    discovered_at: datetime
    queued_job_id: int | None
    learning_record_id: int | None


class WatchRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def add_or_update_subscription(
        self,
        *,
        guild_id: str,
        youtube_channel_id: str,
        youtube_channel_ref: str,
        youtube_channel_title: str,
        discord_channel_id: int,
    ) -> WatchedChannel:
        timestamp = utc_now()
        with self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO watched_channels (
                    guild_id,
                    youtube_channel_id,
                    youtube_channel_ref,
                    youtube_channel_title,
                    discord_channel_id,
                    is_active,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(guild_id, youtube_channel_id)
                DO UPDATE SET
                    youtube_channel_ref = excluded.youtube_channel_ref,
                    youtube_channel_title = excluded.youtube_channel_title,
                    discord_channel_id = excluded.discord_channel_id,
                    is_active = 1,
                    updated_at = excluded.updated_at
                RETURNING *
                """,
                (
                    guild_id,
                    youtube_channel_id,
                    youtube_channel_ref,
                    youtube_channel_title,
                    discord_channel_id,
                    _serialize_timestamp(timestamp),
                    _serialize_timestamp(timestamp),
                ),
            ).fetchone()
        if row is None:
            raise RuntimeError("Unable to create watched channel")
        return self._row_to_watched_channel(row)

    def list_subscriptions(self, *, guild_id: str, active_only: bool = True) -> list[WatchedChannel]:
        query = """
            SELECT * FROM watched_channels
            WHERE guild_id = ?
        """
        params: list[object] = [guild_id]
        if active_only:
            query += " AND is_active = 1"
        query += " ORDER BY youtube_channel_title ASC, id ASC"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_watched_channel(row) for row in rows]

    def get_active_subscriptions(self) -> list[WatchedChannel]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM watched_channels
                WHERE is_active = 1
                ORDER BY id ASC
                """
            ).fetchall()
        return [self._row_to_watched_channel(row) for row in rows]

    def deactivate_subscription_by_id(self, *, guild_id: str, subscription_id: int) -> WatchedChannel | None:
        timestamp = utc_now()
        with self._connect() as conn:
            row = conn.execute(
                """
                UPDATE watched_channels
                SET is_active = 0, updated_at = ?
                WHERE guild_id = ? AND id = ? AND is_active = 1
                RETURNING *
                """,
                (_serialize_timestamp(timestamp), guild_id, subscription_id),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_watched_channel(row)

    def deactivate_subscription_by_channel_id(
        self, *, guild_id: str, youtube_channel_id: str
    ) -> WatchedChannel | None:
        timestamp = utc_now()
        with self._connect() as conn:
            row = conn.execute(
                """
                UPDATE watched_channels
                SET is_active = 0, updated_at = ?
                WHERE guild_id = ? AND youtube_channel_id = ? AND is_active = 1
                RETURNING *
                """,
                (_serialize_timestamp(timestamp), guild_id, youtube_channel_id),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_watched_channel(row)

    def mark_bootstrap_complete(self, subscription_id: int) -> None:
        timestamp = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE watched_channels
                SET bootstrap_completed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    _serialize_timestamp(timestamp),
                    _serialize_timestamp(timestamp),
                    subscription_id,
                ),
            )

    def record_discovered_video(
        self,
        *,
        subscription_id: int,
        video_id: str,
        video_url: str,
        title: str,
        published_at: datetime | None,
    ) -> bool:
        timestamp = utc_now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO watched_channel_videos (
                    watched_channel_id,
                    video_id,
                    video_url,
                    title,
                    published_at,
                    discovered_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    subscription_id,
                    video_id,
                    video_url,
                    title,
                    _serialize_timestamp(published_at),
                    _serialize_timestamp(timestamp),
                ),
            )
        return int(cursor.rowcount) > 0

    def mark_video_enqueued(self, *, subscription_id: int, video_id: str, queued_job_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE watched_channel_videos
                SET queued_job_id = ?
                WHERE watched_channel_id = ? AND video_id = ?
                """,
                (queued_job_id, subscription_id, video_id),
            )

    def mark_video_indexed_by_job(self, *, queued_job_id: int, learning_record_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE watched_channel_videos
                SET learning_record_id = ?
                WHERE queued_job_id = ?
                """,
                (learning_record_id, queued_job_id),
            )

    def mark_video_existing_learning(
        self, *, subscription_id: int, video_id: str, learning_record_id: int
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE watched_channel_videos
                SET learning_record_id = ?
                WHERE watched_channel_id = ? AND video_id = ?
                """,
                (learning_record_id, subscription_id, video_id),
            )

    def list_discovered_videos(self, *, subscription_id: int) -> list[WatchedVideo]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM watched_channel_videos
                WHERE watched_channel_id = ?
                ORDER BY discovered_at ASC, id ASC
                """,
                (subscription_id,),
            ).fetchall()
        return [self._row_to_watched_video(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS watched_channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    youtube_channel_id TEXT NOT NULL,
                    youtube_channel_ref TEXT NOT NULL,
                    youtube_channel_title TEXT NOT NULL,
                    discord_channel_id INTEGER NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    bootstrap_completed_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(guild_id, youtube_channel_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS watched_channel_videos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    watched_channel_id INTEGER NOT NULL,
                    video_id TEXT NOT NULL,
                    video_url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    published_at TEXT,
                    discovered_at TEXT NOT NULL,
                    queued_job_id INTEGER,
                    learning_record_id INTEGER,
                    UNIQUE(watched_channel_id, video_id),
                    FOREIGN KEY(watched_channel_id) REFERENCES watched_channels(id)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_watched_channels_active
                ON watched_channels(is_active, id)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_watched_channel_videos_job
                ON watched_channel_videos(queued_job_id)
                """
            )

    def _row_to_watched_channel(self, row: sqlite3.Row) -> WatchedChannel:
        return WatchedChannel(
            id=int(row["id"]),
            guild_id=str(row["guild_id"]),
            youtube_channel_id=str(row["youtube_channel_id"]),
            youtube_channel_ref=str(row["youtube_channel_ref"]),
            youtube_channel_title=str(row["youtube_channel_title"]),
            discord_channel_id=int(row["discord_channel_id"]),
            is_active=bool(row["is_active"]),
            bootstrap_completed_at=_parse_timestamp(row["bootstrap_completed_at"]),
            created_at=_parse_timestamp(row["created_at"]) or utc_now(),
            updated_at=_parse_timestamp(row["updated_at"]) or utc_now(),
        )

    def _row_to_watched_video(self, row: sqlite3.Row) -> WatchedVideo:
        return WatchedVideo(
            id=int(row["id"]),
            watched_channel_id=int(row["watched_channel_id"]),
            video_id=str(row["video_id"]),
            video_url=str(row["video_url"]),
            title=str(row["title"]),
            published_at=_parse_timestamp(row["published_at"]),
            discovered_at=_parse_timestamp(row["discovered_at"]) or utc_now(),
            queued_job_id=row["queued_job_id"],
            learning_record_id=row["learning_record_id"],
        )
