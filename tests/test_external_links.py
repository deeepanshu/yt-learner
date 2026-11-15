from __future__ import annotations

from app.external_links import ExternalDocumentLinkStore


def test_external_document_link_upsert_and_delete(database_url) -> None:
    store = ExternalDocumentLinkStore(database_url)

    saved = store.save(
        provider="outline",
        source_type="youtube_video",
        source_key="video-1",
        remote_id="outline-1",
    )
    assert saved.remote_id == "outline-1"
    assert store.get(
        provider="outline",
        source_type="youtube_video",
        source_key="video-1",
    ).remote_id == "outline-1"

    updated = store.save(
        provider="outline",
        source_type="youtube_video",
        source_key="video-1",
        remote_id="outline-2",
    )
    assert updated.remote_id == "outline-2"

    store.delete(provider="outline", source_type="youtube_video", source_key="video-1")
    assert store.get(
        provider="outline",
        source_type="youtube_video",
        source_key="video-1",
    ) is None
