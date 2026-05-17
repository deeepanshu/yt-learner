from __future__ import annotations

import html
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse
from urllib.request import urlopen

from app.youtube_urls import parse_youtube_url

YOUTUBE_FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
ATOM_NAMESPACE = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
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


def fetch_channel_feed(channel_id: str) -> tuple[str, list[ChannelFeedVideo]]:
    request_url = YOUTUBE_FEED_URL.format(channel_id=channel_id)
    LOGGER.info("youtube_feed_fetch_started channel_id=%s url=%s", channel_id, request_url)
    try:
        with urlopen(request_url, timeout=10) as response:
            payload = response.read()
    except Exception as exc:
        LOGGER.exception("youtube_feed_fetch_failed channel_id=%s url=%s", channel_id, request_url)
        raise YouTubeChannelError("Unable to fetch YouTube channel feed") from exc

    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise YouTubeChannelError("Unable to parse YouTube channel feed") from exc

    title_text = root.findtext("atom:title", namespaces=ATOM_NAMESPACE) or channel_id
    videos: list[ChannelFeedVideo] = []
    for entry in root.findall("atom:entry", ATOM_NAMESPACE):
        video_id = (entry.findtext("yt:videoId", namespaces=ATOM_NAMESPACE) or "").strip()
        link = entry.find("atom:link", ATOM_NAMESPACE)
        video_url = ""
        if link is not None:
            video_url = str(link.attrib.get("href", "")).strip()
        if not video_id or not video_url:
            continue
        title = (entry.findtext("atom:title", namespaces=ATOM_NAMESPACE) or video_id).strip()
        published_at = _parse_feed_datetime(entry.findtext("atom:published", namespaces=ATOM_NAMESPACE))
        videos.append(
            ChannelFeedVideo(
                video_id=video_id,
                title=title,
                video_url=parse_youtube_url(video_url).canonical_url,
                published_at=published_at,
            )
        )
    LOGGER.info("youtube_feed_fetch_succeeded channel_id=%s video_count=%s title=%r", channel_id, len(videos), title_text.strip() or channel_id)
    return title_text.strip() or channel_id, videos


def resolve_youtube_channel(reference: str) -> ResolvedYouTubeChannel:
    raw = reference.strip()
    LOGGER.info("youtube_channel_resolve_started raw_reference=%r", reference)
    if not raw:
        LOGGER.info("youtube_channel_resolve_failed reason=missing_reference raw_reference=%r", reference)
        raise YouTubeChannelError("Missing YouTube channel reference")

    if _looks_like_channel_id(raw):
        title, _ = fetch_channel_feed(raw)
        LOGGER.info("youtube_channel_resolve_succeeded raw_reference=%r channel_id=%s via=direct_channel_id title=%r", reference, raw, title)
        return ResolvedYouTubeChannel(
            channel_id=raw,
            title=title,
            canonical_url=f"https://www.youtube.com/channel/{raw}",
        )

    url = _normalize_channel_reference(raw)
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if path.startswith("/channel/"):
        channel_id = path.split("/", 2)[2].strip()
        if not _looks_like_channel_id(channel_id):
            LOGGER.info("youtube_channel_resolve_failed reason=unsupported_channel_path raw_reference=%r parsed_path=%r", reference, path)
            raise YouTubeChannelError("Unsupported YouTube channel reference")
        title, _ = fetch_channel_feed(channel_id)
        LOGGER.info("youtube_channel_resolve_succeeded raw_reference=%r channel_id=%s via=canonical_channel_url title=%r", reference, channel_id, title)
        return ResolvedYouTubeChannel(
            channel_id=channel_id,
            title=title,
            canonical_url=f"https://www.youtube.com/channel/{channel_id}",
        )

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


def _parse_feed_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
