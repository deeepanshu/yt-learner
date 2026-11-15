from __future__ import annotations


from dotenv import load_dotenv

from app.channel_watches import WatchRepository
from app.config import load_settings
from app.external_links import (
    OUTLINE_PROVIDER,
    YOUTUBE_CHANNEL_SOURCE,
    YOUTUBE_VIDEO_SOURCE,
    ExternalDocumentLinkStore,
)
from app.outline import CHANNEL_MARKER_PREFIX, VIDEO_MARKER_PREFIX, build_outline_client
from app.storage import OutputStore


def main() -> int:
    load_dotenv()
    settings = load_settings()
    links = ExternalDocumentLinkStore(settings.database_url)
    outline = build_outline_client(settings)
    watches = WatchRepository(settings.database_url)
    store = OutputStore(settings.database_url)
    documents = outline.list_documents()

    def find_marker(marker: str) -> dict[str, object] | None:
        return next(
            (
                document
                for document in documents
                if marker in str(document.get("text", ""))
            ),
            None,
        )

    channel_count = 0
    video_count = 0
    for channel in watches.list_subscriptions(active_only=False):
        marker = f"{CHANNEL_MARKER_PREFIX}{channel.youtube_channel_title}"
        document = find_marker(marker)
        if document is None:
            continue
        links.save(
            provider=OUTLINE_PROVIDER,
            source_type=YOUTUBE_CHANNEL_SOURCE,
            source_key=channel.youtube_channel_id,
            remote_id=str(document["id"]),
        )
        outline.remove_legacy_marker(document, marker)
        channel_count += 1

    for video_id, _source_url in store.list_youtube_note_sources():
        marker = f"{VIDEO_MARKER_PREFIX}{video_id}"
        document = find_marker(marker)
        if document is None:
            continue
        links.save(
            provider=OUTLINE_PROVIDER,
            source_type=YOUTUBE_VIDEO_SOURCE,
            source_key=video_id,
            remote_id=str(document["id"]),
        )
        outline.remove_legacy_marker(document, marker)
        video_count += 1

    print(f"migrated Outline channel links: {channel_count}")
    print(f"migrated Outline video links: {video_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
