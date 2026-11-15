from __future__ import annotations

import html
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.parse import urlparse
from urllib.request import urlopen


YOUTUBE_DATA_API_BASE_URL = "https://www.googleapis.com/youtube/v3"
YOUTUBE_DATA_API_KEY_ENV = "YOUTUBE_DATA_API_KEY"
CHANNEL_ID_PATTERN = re.compile(r'"channelId":"(UC[\w-]{20,})"')
TITLE_META_PATTERN = re.compile(r'<meta\s+property="og:title"\s+content="([^"]+)"', re.IGNORECASE)
TITLE_TAG_PATTERN = re.compile(r"<title>([^<]+)</title>", re.IGNORECASE)
EXTERNAL_ID_PATTERN = re.compile(r'"externalId":"(UC[\w-]{20,})"')
OG_URL_PATTERN = re.compile(r'<meta\s+property="og:url"\s+content="https://www\.youtube\.com/channel/(UC[\w-]{20,})"', re.IGNORECASE)
LOGGER = logging.getLogger(__name__)


class YouTubeChannelError(RuntimeError):
    """Raised when a channel cannot be resolved or fetched."""


@dataclass(frozen=True)
class ResolvedYouTubeChannel:
    channel_id: str
    title: str
    canonical_url: str


@dataclass(frozen=True)
class ChannelFeedVideo:
    video_id: str
    title: str
    video_url: str
    published_at: datetime | None


class YouTubeDataClient:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key.strip()
        if not self.api_key:
            raise YouTubeChannelError(f"{YOUTUBE_DATA_API_KEY_ENV} is required for channel discovery")

    @classmethod
    def from_environment(cls) -> YouTubeDataClient:
        return cls(os.getenv(YOUTUBE_DATA_API_KEY_ENV, ""))

    def fetch_channel_feeds(
        self, channel_ids: list[str]
    ) -> dict[str, tuple[str, list[ChannelFeedVideo]]]:
        unique_channel_ids = list(dict.fromkeys(channel_ids))
        if not unique_channel_ids:
            return {}

        response = self._request_json(
            "channels",
            {
                "part": "snippet,contentDetails",
                "id": ",".join(unique_channel_ids),
            },
        )
        channels_by_id = {
            str(resource.get("id", "")): resource
            for resource in response.get("items", [])
            if isinstance(resource, dict) and resource.get("id")
        }
        feeds: dict[str, tuple[str, list[ChannelFeedVideo]]] = {}
        for channel_id in unique_channel_ids:
            resource = channels_by_id.get(channel_id)
            if resource is None:
                LOGGER.warning("youtube_api_channel_not_found channel_id=%s", channel_id)
                continue
            try:
                feeds[channel_id] = self._fetch_uploads(resource, channel_id=channel_id)
            except YouTubeChannelError:
                LOGGER.exception("youtube_api_uploads_fetch_failed channel_id=%s", channel_id)
        return feeds

    def fetch_channel_feed(self, channel_id: str) -> tuple[str, list[ChannelFeedVideo]]:
        feeds = self.fetch_channel_feeds([channel_id])
        feed = feeds.get(channel_id)
        if feed is None:
            raise YouTubeChannelError(f"Unable to fetch YouTube channel {channel_id}")
        return feed

    def _fetch_uploads(
        self, resource: dict[str, object], *, channel_id: str
    ) -> tuple[str, list[ChannelFeedVideo]]:
        snippet = resource.get("snippet")
        content_details = resource.get("contentDetails")
        if not isinstance(snippet, dict) or not isinstance(content_details, dict):
            raise YouTubeChannelError(f"YouTube API returned incomplete channel data for {channel_id}")
        related_playlists = content_details.get("relatedPlaylists")
        if not isinstance(related_playlists, dict):
            raise YouTubeChannelError(f"YouTube API returned no uploads playlist for {channel_id}")
        uploads_playlist_id = str(related_playlists.get("uploads", "")).strip()
        if not uploads_playlist_id:
            raise YouTubeChannelError(f"YouTube API returned no uploads playlist for {channel_id}")

        response = self._request_json(
            "playlistItems",
            {
                "part": "snippet,contentDetails",
                "playlistId": uploads_playlist_id,
                "maxResults": "50",
            },
        )
        videos: list[ChannelFeedVideo] = []
        for item in response.get("items", []):
            if not isinstance(item, dict):
                continue
            item_snippet = item.get("snippet")
            item_content_details = item.get("contentDetails")
            if not isinstance(item_snippet, dict) or not isinstance(item_content_details, dict):
                continue
            video_id = str(item_content_details.get("videoId", "")).strip()
            if not video_id:
                continue
            title = str(item_snippet.get("title", "")).strip() or video_id
            published_at = _parse_video_datetime(
                str(
                    item_content_details.get("videoPublishedAt")
                    or item_snippet.get("publishedAt")
                    or ""
                )
            )
            videos.append(
                ChannelFeedVideo(
                    video_id=video_id,
                    title=title,
                    video_url=f"https://www.youtube.com/watch?v={video_id}",
                    published_at=published_at,
                )
            )
        title = str(snippet.get("title", "")).strip() or channel_id
        LOGGER.info(
            "youtube_api_channel_fetch_succeeded channel_id=%s video_count=%s title=%r",
            channel_id,
            len(videos),
            title,
        )
        return title, videos

    def _request_json(self, resource: str, params: dict[str, str]) -> dict[str, object]:
        request_url = f"{YOUTUBE_DATA_API_BASE_URL}/{resource}?{urlencode({**params, 'key': self.api_key})}"
        try:
            with urlopen(request_url, timeout=10) as response:
                payload = json.loads(response.read())
        except HTTPError as exc:
            LOGGER.warning("youtube_api_request_failed resource=%s status=%s", resource, exc.code)
            raise YouTubeChannelError(f"YouTube API request failed for {resource}") from exc
        except (OSError, TypeError, ValueError) as exc:
            LOGGER.warning("youtube_api_request_failed resource=%s error=%s", resource, exc)
            raise YouTubeChannelError(f"Unable to fetch YouTube API resource {resource}") from exc
        if not isinstance(payload, dict):
            raise YouTubeChannelError(f"YouTube API returned invalid data for {resource}")
        return payload


def fetch_channel_feeds(
    channel_ids: list[str],
) -> dict[str, tuple[str, list[ChannelFeedVideo]]]:
    return YouTubeDataClient.from_environment().fetch_channel_feeds(channel_ids)


def fetch_channel_feed(channel_id: str) -> tuple[str, list[ChannelFeedVideo]]:
    return YouTubeDataClient.from_environment().fetch_channel_feed(channel_id)


def resolve_youtube_channel(reference: str) -> ResolvedYouTubeChannel:
    raw = reference.strip()
    LOGGER.info("youtube_channel_resolve_started raw_reference=%r", reference)
    if not raw:
        LOGGER.info("youtube_channel_resolve_failed reason=missing_reference raw_reference=%r", reference)
        raise YouTubeChannelError("Missing YouTube channel reference")

    if _looks_like_channel_id(raw):
        return _resolve_channel_id(raw, reference=reference, via="direct_channel_id")

    url = _normalize_channel_reference(raw)
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if path.startswith("/channel/"):
        channel_id = path.split("/", 2)[2].strip()
        if not _looks_like_channel_id(channel_id):
            LOGGER.info("youtube_channel_resolve_failed reason=unsupported_channel_path raw_reference=%r parsed_path=%r", reference, path)
            raise YouTubeChannelError("Unsupported YouTube channel reference")
        return _resolve_channel_id(channel_id, reference=reference, via="canonical_channel_url")

    page_html = _fetch_text(url)
    match = CHANNEL_ID_PATTERN.search(page_html) or EXTERNAL_ID_PATTERN.search(page_html) or OG_URL_PATTERN.search(page_html)
    if match is None:
        LOGGER.info("youtube_channel_resolve_failed reason=no_channel_id_in_page raw_reference=%r normalized_url=%s", reference, url)
        raise YouTubeChannelError("Unable to resolve YouTube channel ID")
    channel_id = match.group(1)
    title = _extract_page_title(page_html) or channel_id
    LOGGER.info("youtube_channel_resolve_succeeded raw_reference=%r channel_id=%s via=page_parse title=%r", reference, channel_id, title)
    return ResolvedYouTubeChannel(
        channel_id=channel_id,
        title=title,
        canonical_url=f"https://www.youtube.com/channel/{channel_id}",
    )


def _normalize_channel_reference(reference: str) -> str:
    if reference.startswith("@"):
        return f"https://www.youtube.com/{reference}"
    if reference.startswith("http://") or reference.startswith("https://"):
        return reference
    raise YouTubeChannelError("Unsupported YouTube channel reference")


def _resolve_channel_id(channel_id: str, *, reference: str, via: str) -> ResolvedYouTubeChannel:
    canonical_url = f"https://www.youtube.com/channel/{channel_id}"
    try:
        title, _ = fetch_channel_feed(channel_id)
        resolution_via = via
    except YouTubeChannelError:
        page_html = _fetch_text(canonical_url)
        title = _extract_page_title(page_html) or channel_id
        resolution_via = f"{via}_page_fallback"
    LOGGER.info(
        "youtube_channel_resolve_succeeded raw_reference=%r channel_id=%s via=%s title=%r",
        reference,
        channel_id,
        resolution_via,
        title,
    )
    return ResolvedYouTubeChannel(
        channel_id=channel_id,
        title=title,
        canonical_url=canonical_url,
    )


def _fetch_text(url: str) -> str:
    try:
        with urlopen(url, timeout=10) as response:
            return response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        raise YouTubeChannelError("Unable to fetch YouTube channel page") from exc


def _extract_page_title(page_html: str) -> str | None:
    meta_match = TITLE_META_PATTERN.search(page_html)
    if meta_match is not None:
        return html.unescape(meta_match.group(1)).strip() or None
    title_match = TITLE_TAG_PATTERN.search(page_html)
    if title_match is None:
        return None
    raw_title = html.unescape(title_match.group(1)).strip()
    return raw_title.removesuffix(" - YouTube").strip() or None


def _looks_like_channel_id(value: str) -> bool:
    return bool(re.fullmatch(r"UC[\w-]{20,}", value))


def _parse_video_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
