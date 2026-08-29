from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.db import as_datetime, connect


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


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
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

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
        with connect(self.database_url) as conn:
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
                VALUES (%s, %s, %s, %s, %s, TRUE, %s, %s)
                ON CONFLICT (guild_id, youtube_channel_id)
                DO UPDATE SET
                    youtube_channel_ref = excluded.youtube_channel_ref,
                    youtube_channel_title = excluded.youtube_channel_title,
                    discord_channel_id = excluded.discord_channel_id,
                    is_active = TRUE,
                    updated_at = excluded.updated_at
                RETURNING *
                """,
                (
                    guild_id,
                    youtube_channel_id,
                    youtube_channel_ref,
                    youtube_channel_title,
                    discord_channel_id,
                    timestamp,
                    timestamp,
                ),
            ).fetchone()
        if row is None:
            raise RuntimeError("Unable to create watched channel")
        return self._row_to_watched_channel(row)

    def list_subscriptions(self, *, guild_id: str, active_only: bool = True) -> list[WatchedChannel]:
        query = """
            SELECT * FROM watched_channels
            WHERE guild_id = %s
        """
        params: list[object] = [guild_id]
        if active_only:
            query += " AND is_active"
        query += " ORDER BY youtube_channel_title ASC, id ASC"

        with connect(self.database_url) as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_watched_channel(row) for row in rows]

    def get_active_subscriptions(self) -> list[WatchedChannel]:
        with connect(self.database_url) as conn:
            rows = conn.execute(
                """
                SELECT * FROM watched_channels
                WHERE is_active
                ORDER BY id ASC
                """
            ).fetchall()
        return [self._row_to_watched_channel(row) for row in rows]

    def deactivate_subscription_by_id(self, *, guild_id: str, subscription_id: int) -> WatchedChannel | None:
        timestamp = utc_now()
        with connect(self.database_url) as conn:
            row = conn.execute(
                """
                UPDATE watched_channels
                SET is_active = FALSE, updated_at = %s
                WHERE guild_id = %s AND id = %s AND is_active
                RETURNING *
                """,
                (timestamp, guild_id, subscription_id),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_watched_channel(row)

    def deactivate_subscription_by_channel_id(
        self, *, guild_id: str, youtube_channel_id: str
    ) -> WatchedChannel | None:
        timestamp = utc_now()
        with connect(self.database_url) as conn:
            row = conn.execute(
                """
                UPDATE watched_channels
                SET is_active = FALSE, updated_at = %s
                WHERE guild_id = %s AND youtube_channel_id = %s AND is_active
                RETURNING *
                """,
                (timestamp, guild_id, youtube_channel_id),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_watched_channel(row)

    def mark_bootstrap_complete(self, subscription_id: int) -> None:
        timestamp = utc_now()
        with connect(self.database_url) as conn:
            conn.execute(
                """
                UPDATE watched_channels
                SET bootstrap_completed_at = %s, updated_at = %s
                WHERE id = %s
                """,
                (timestamp, timestamp, subscription_id),
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
        with connect(self.database_url) as conn:
            row = conn.execute(
                """
                INSERT INTO watched_channel_videos (
                    watched_channel_id,
                    video_id,
                    video_url,
                    title,
                    published_at,
                    discovered_at
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (watched_channel_id, video_id) DO NOTHING
                RETURNING id
                """,
                (
                    subscription_id,
                    video_id,
                    video_url,
                    title,
                    published_at,
                    timestamp,
                ),
            ).fetchone()
        return row is not None

    def mark_video_enqueued(self, *, subscription_id: int, video_id: str, queued_job_id: int) -> None:
        with connect(self.database_url) as conn:
            conn.execute(
                """
                UPDATE watched_channel_videos
                SET queued_job_id = %s
                WHERE watched_channel_id = %s AND video_id = %s
                """,
                (queued_job_id, subscription_id, video_id),
            )

    def mark_video_indexed_by_job(self, *, queued_job_id: int, learning_record_id: int) -> None:
        with connect(self.database_url) as conn:
            conn.execute(
                """
                UPDATE watched_channel_videos
                SET learning_record_id = %s
                WHERE queued_job_id = %s
                """,
                (learning_record_id, queued_job_id),
            )

    def mark_video_existing_learning(
        self, *, subscription_id: int, video_id: str, learning_record_id: int
    ) -> None:
        with connect(self.database_url) as conn:
            conn.execute(
                """
                UPDATE watched_channel_videos
                SET learning_record_id = %s
                WHERE watched_channel_id = %s AND video_id = %s
                """,
                (learning_record_id, subscription_id, video_id),
            )

    def list_discovered_videos(self, *, subscription_id: int) -> list[WatchedVideo]:
        with connect(self.database_url) as conn:
            rows = conn.execute(
                """
                SELECT * FROM watched_channel_videos
                WHERE watched_channel_id = %s
                ORDER BY discovered_at ASC, id ASC
                """,
                (subscription_id,),
            ).fetchall()
        return [self._row_to_watched_video(row) for row in rows]

    def _row_to_watched_channel(self, row: dict[str, object]) -> WatchedChannel:
        return WatchedChannel(
            id=int(row["id"]),
            guild_id=str(row["guild_id"]),
            youtube_channel_id=str(row["youtube_channel_id"]),
            youtube_channel_ref=str(row["youtube_channel_ref"]),
            youtube_channel_title=str(row["youtube_channel_title"]),
            discord_channel_id=int(row["discord_channel_id"]),
            is_active=bool(row["is_active"]),
            bootstrap_completed_at=as_datetime(row["bootstrap_completed_at"]),
            created_at=as_datetime(row["created_at"]) or utc_now(),
            updated_at=as_datetime(row["updated_at"]) or utc_now(),
        )

    def _row_to_watched_video(self, row: dict[str, object]) -> WatchedVideo:
        queued_job_id = row["queued_job_id"]
        learning_record_id = row["learning_record_id"]
        return WatchedVideo(
            id=int(row["id"]),
            watched_channel_id=int(row["watched_channel_id"]),
            video_id=str(row["video_id"]),
            video_url=str(row["video_url"]),
            title=str(row["title"]),
            published_at=as_datetime(row["published_at"]),
            discovered_at=as_datetime(row["discovered_at"]) or utc_now(),
            queued_job_id=int(queued_job_id) if queued_job_id is not None else None,
            learning_record_id=int(learning_record_id) if learning_record_id is not None else None,
        )
