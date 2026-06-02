from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


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


@dataclass(frozen=True)
class LearningThread:
    id: int
    guild_id: str
    parent_channel_id: int
    source_type: str
    source_key: str
    thread_id: int
    title: str
    created_at: datetime
    updated_at: datetime

    @property
    def video_id(self) -> str:
        return self.source_key
