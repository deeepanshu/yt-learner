from __future__ import annotations

from dataclasses import dataclass

from youtube_transcript_api import (
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnplayable,
    VideoUnavailable,
    YouTubeTranscriptApi,
)


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


def fetch_transcript(video_id: str) -> TranscriptData:
    api = YouTubeTranscriptApi()
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
