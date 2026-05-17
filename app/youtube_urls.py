from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse


class InvalidYouTubeUrl(ValueError):
    """Raised when a URL is not a supported YouTube video URL."""


@dataclass(frozen=True)
class ParsedYouTubeUrl:
    video_id: str
    canonical_url: str


def parse_youtube_url(raw_url: str) -> ParsedYouTubeUrl:
    url = raw_url.strip()
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/")

    video_id: str | None = None

    if host == "youtu.be":
        video_id = path.lstrip("/") or None
    elif host in {"youtube.com", "m.youtube.com"}:
        if path == "/watch":
            query = parse_qs(parsed.query)
            video_id = query.get("v", [None])[0]
        elif path.startswith("/shorts/"):
            video_id = path.split("/", 2)[2]
        elif path.startswith("/embed/"):
            video_id = path.split("/", 2)[2]

    if not video_id:
        raise InvalidYouTubeUrl("Unsupported or invalid YouTube URL")

    video_id = video_id.strip()
    if not video_id:
        raise InvalidYouTubeUrl("Missing YouTube video ID")

    return ParsedYouTubeUrl(
        video_id=video_id,
        canonical_url=f"https://www.youtube.com/watch?v={video_id}",
    )
