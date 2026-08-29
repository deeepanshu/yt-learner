from __future__ import annotations

import os
from dataclasses import dataclass

from youtube_transcript_api import (
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnplayable,
    VideoUnavailable,
    YouTubeTranscriptApi,
)
from youtube_transcript_api.proxies import WebshareProxyConfig


class TranscriptError(RuntimeError):
    """Base transcript failure."""


class TranscriptUnavailableError(TranscriptError):
    """No supported transcript is available."""


class UnsupportedVideoError(TranscriptError):
    """Video is private, unavailable, or unsupported."""


class TranscriptFetchError(TranscriptError):
    """Transcript fetch failed for a transient or network-related reason."""


@dataclass(frozen=True)
class TranscriptSegment:
    start_seconds: int
    text: str


@dataclass(frozen=True)
class TranscriptData:
    segments: list[TranscriptSegment]

    @property
    def text(self) -> str:
        return "\n".join(segment.text for segment in self.segments)


def _transcript_api() -> YouTubeTranscriptApi:
    username = os.getenv("YT_LEARNER_WEBSHARE_PROXY_USERNAME", "").strip()
    password = os.getenv("YT_LEARNER_WEBSHARE_PROXY_PASSWORD", "").strip()
    if bool(username) != bool(password):
        raise TranscriptFetchError(
            "Set both YT_LEARNER_WEBSHARE_PROXY_USERNAME and "
            "YT_LEARNER_WEBSHARE_PROXY_PASSWORD, or neither"
        )
    if not username:
        return YouTubeTranscriptApi()
    return YouTubeTranscriptApi(
        proxy_config=WebshareProxyConfig(
            proxy_username=username,
            proxy_password=password,
        )
    )


def fetch_transcript(video_id: str) -> TranscriptData:
    api = _transcript_api()
    try:
        fetched = api.fetch(video_id, languages=["en"])
    except (NoTranscriptFound, TranscriptsDisabled) as exc:
        raise TranscriptUnavailableError("No English transcript is available") from exc
    except (VideoUnavailable, VideoUnplayable) as exc:
        raise UnsupportedVideoError("Video is unavailable or private") from exc
    except RequestBlocked as exc:
        raise TranscriptFetchError("Transcript fetch was blocked by YouTube") from exc

    segments = [
        TranscriptSegment(
            start_seconds=int(item.start),
            text=item.text.strip(),
        )
        for item in fetched
        if item.text.strip()
    ]
    return TranscriptData(segments=segments)
