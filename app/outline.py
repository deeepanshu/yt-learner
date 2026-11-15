from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from app.pipeline import ProcessedVideo

MAX_DOCUMENT_TITLE_CHARS = 100
VIDEO_MARKER_PREFIX = "<!-- yt-learner-video:"
CHANNEL_MARKER_PREFIX = "<!-- yt-learner-channel:"


class OutlineError(Exception):
    pass


@dataclass(frozen=True)
class PublishedNote:
    note_id: str
    url: str | None


class NotePublisher(Protocol):
    def publish_video_notes(self, result: ProcessedVideo) -> PublishedNote: ...


def format_document_title(title: str) -> str:
    cleaned = " ".join(title.split()) or "YouTube video"
    if len(cleaned) <= MAX_DOCUMENT_TITLE_CHARS:
        return cleaned
    return cleaned[: MAX_DOCUMENT_TITLE_CHARS - 3].rstrip() + "..."


def _video_text(result: ProcessedVideo) -> str:
    markdown = _remove_duplicate_title_heading(result.markdown, result.title)
    markdown = _remove_generated_metadata(markdown, result.url)
    return (
        f"[Watch on YouTube]({result.url})\n\n"
        f"{markdown}\n\n"
        f"{VIDEO_MARKER_PREFIX}{result.video_id} -->"
    )


def _remove_generated_metadata(markdown: str, source_url: str) -> str:
    lines = markdown.lstrip("\n").splitlines()
    if lines and lines[0].strip() == f"Source: {source_url}":
        lines.pop(0)
    if lines and lines[0].strip().startswith("Processed: "):
        lines.pop(0)
    while lines and not lines[0].strip():
        lines.pop(0)
    return "\n".join(lines).rstrip()


def _remove_duplicate_title_heading(markdown: str, title: str) -> str:
    body = markdown.lstrip("\n")
    first_line, separator, remainder = body.partition("\n")
    normalized_heading = " ".join(first_line.removeprefix("# ").split())
    normalized_title = " ".join(title.split())
    if first_line.startswith("# ") and normalized_heading == normalized_title:
        return remainder.lstrip("\n").rstrip()
    return markdown.rstrip()


def _channel_text(channel_title: str) -> str:
    return f"{CHANNEL_MARKER_PREFIX}{channel_title} -->"


class OutlineClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        collection_id: str,
        ui_url: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        api_base = base_url.rstrip("/")
        self.api_base = api_base if api_base.endswith("/api") else f"{api_base}/api"
        self.token = token
        self.collection_id = collection_id
        self.ui_url = ui_url.rstrip("/") if ui_url else None
        self.timeout_seconds = timeout_seconds
        self._resolved_collection_id: str | None = None

    def publish_video_notes(self, result: ProcessedVideo) -> PublishedNote:
        collection_id = self._get_collection_id()
        existing = self._find_document(f"{VIDEO_MARKER_PREFIX}{result.video_id}", collection_id)
        title = format_document_title(result.title)
        text = _video_text(result)
        if existing is not None:
            document = self._update_document(existing, title=title, text=text)
        else:
            parent_id = self._ensure_channel_document(result.channel_title, collection_id)
            document = self._create_document(
                collection_id=collection_id,
                parent_document_id=parent_id,
                title=title,
                text=text,
            )
        return self._published(document)

    def _get_collection_id(self) -> str:
        if self._resolved_collection_id is not None:
            return self._resolved_collection_id
        payload = self._request("collections.list", {"limit": 100})
        collections = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(collections, list):
            raise OutlineError("Outline collections.list response missing data")
        for collection in collections:
            if not isinstance(collection, dict):
                continue
            if str(collection.get("id")) == self.collection_id or str(collection.get("urlId")) == self.collection_id:
                resolved = collection.get("id")
                if resolved:
                    self._resolved_collection_id = str(resolved)
                    return self._resolved_collection_id
        raise OutlineError(f"Outline collection not found: {self.collection_id}")

    def _find_document(self, query: str, collection_id: str) -> str | None:
        payload = self._request(
            "documents.search",
            {"query": query, "collectionId": collection_id, "limit": 100},
        )
        results = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            raise OutlineError("Outline documents.search response missing data")
        for result in results:
            if not isinstance(result, dict):
                continue
            document = result.get("document")
            if not isinstance(document, dict) or not document.get("id"):
                continue
            if query not in str(document.get("text", "")):
                continue
            return str(document["id"])
        return None

    def _ensure_channel_document(self, channel_title: str | None, collection_id: str) -> str | None:
        name = " ".join((channel_title or "").split()) or "Unknown channel"
        marker = f"{CHANNEL_MARKER_PREFIX}{name}"
        existing = self._find_document(marker, collection_id)
        if existing is not None:
            return existing
        document = self._create_document(
            collection_id=collection_id,
            title=format_document_title(name),
            text=_channel_text(name),
        )
        return str(document["id"])

    def _create_document(
        self,
        *,
        collection_id: str,
        title: str,
        text: str,
        parent_document_id: str | None = None,
    ) -> dict[str, object]:
        body: dict[str, object] = {
            "collectionId": collection_id,
            "title": title,
            "text": text,
            "publish": True,
        }
        if parent_document_id is not None:
            body["parentDocumentId"] = parent_document_id
        payload = self._request("documents.create", body)
        document = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(document, dict) or not document.get("id"):
            raise OutlineError("Outline documents.create response missing document id")
        return document

    def _update_document(self, document_id: str, *, title: str, text: str) -> dict[str, object]:
        payload = self._request(
            "documents.update",
            {"id": document_id, "title": title, "text": text, "publish": True},
        )
        document = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(document, dict) or not document.get("id"):
            raise OutlineError("Outline documents.update response missing document id")
        return document

    def _published(self, document: dict[str, object]) -> PublishedNote:
        note_id = str(document["id"])
        url_id = document.get("urlId")
        url = f"{self.ui_url}/doc/{url_id or note_id}" if self.ui_url else None
        return PublishedNote(note_id=note_id, url=url)

    def _request(self, method: str, body: dict[str, object]) -> dict[str, object]:
        request = urllib.request.Request(
            f"{self.api_base}/{method}",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                # The internal URL is HTTP, but Outline is configured to enforce
                # HTTPS at the public proxy. Avoid a 301 that changes POST to GET.
                "X-Forwarded-Proto": "https",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                status = int(response.status)
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise OutlineError(f"Outline API {method} failed: {exc.code} {detail}") from exc
        except urllib.error.URLError as exc:
            raise OutlineError(f"Outline API {method} failed: {exc.reason}") from exc
        if status not in (200, 201):
            raise OutlineError(f"Outline API {method} returned {status}")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise OutlineError(f"Outline API {method} returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise OutlineError(f"Outline API {method} returned a non-object response")
        if payload.get("ok") is False:
            raise OutlineError(f"Outline API {method} failed: {payload.get('error', 'unknown error')}")
        return payload


def build_outline_client(settings) -> OutlineClient:
    return OutlineClient(
        base_url=settings.outline_url,
        token=settings.outline_api_key,
        collection_id=settings.outline_collection_id,
        ui_url=settings.outline_ui_url,
    )
