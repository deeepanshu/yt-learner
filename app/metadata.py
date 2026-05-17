from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.request import urlopen


class VideoMetadataError(RuntimeError):
    """Raised when video metadata cannot be fetched."""


@dataclass(frozen=True)
class VideoMetadata:
    title: str
    author_name: str | None = None


def fetch_video_metadata(video_url: str) -> VideoMetadata:
    query = urlencode({"url": video_url, "format": "json"})
    request_url = f"https://www.youtube.com/oembed?{query}"

    try:
        with urlopen(request_url, timeout=10) as response:
            payload = json.load(response)
    except Exception as exc:
        raise VideoMetadataError("Unable to fetch YouTube metadata") from exc

    title = str(payload.get("title", "")).strip()
    if not title:
        raise VideoMetadataError("YouTube metadata did not include a title")

    author_name = str(payload.get("author_name", "")).strip() or None
    return VideoMetadata(title=title, author_name=author_name)
