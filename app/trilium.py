from __future__ import annotations

import html
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Protocol

import markdown as markdown_lib

from app.config import Settings
from app.pipeline import AnsweredVideoQuestion, ProcessedVideo

VIDEO_ID_LABEL = "ytLearnerVideoId"
MAX_NOTE_TITLE_CHARS = 200


class TriliumError(Exception):
    pass


@dataclass(frozen=True)
class PublishedNote:
    note_id: str
    url: str | None


class NotePublisher(Protocol):
    def publish_video_notes(self, result: ProcessedVideo) -> PublishedNote: ...

    def publish_question_answer(
        self,
        result: AnsweredVideoQuestion,
        *,
        question: str,
    ) -> PublishedNote: ...


def render_note_html(markdown_text: str, *, source_url: str) -> str:
    body = markdown_lib.markdown(
        markdown_text,
        extensions=["extra", "sane_lists", "nl2br"],
    )
    escaped_url = html.escape(source_url, quote=True)
    return f'<p><a href="{escaped_url}">{html.escape(source_url)}</a></p>\n{body}'


def format_note_title(title: str) -> str:
    cleaned = " ".join(title.split()) or "YouTube video"
    if len(cleaned) <= MAX_NOTE_TITLE_CHARS:
        return cleaned
    return cleaned[: MAX_NOTE_TITLE_CHARS - 3].rstrip() + "..."


def format_question_title(question: str) -> str:
    cleaned = " ".join(question.split()) or "Question"
    return format_note_title(f"Q: {cleaned}")


class TriliumClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        parent_note_id: str,
        ui_url: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.parent_note_id = parent_note_id
        self.ui_url = ui_url.rstrip("/") if ui_url else None
        self.timeout_seconds = timeout_seconds

    def publish_video_notes(self, result: ProcessedVideo) -> PublishedNote:
        content = render_note_html(result.markdown, source_url=result.url)
        title = format_note_title(result.title)
        existing = self._find_note_id(VIDEO_ID_LABEL, result.video_id)
        if existing is not None:
            self._put_content(existing, content)
            self._patch_title(existing, title)
            return self._published(existing)
        note_id = self._create_note(self.parent_note_id, title, content)
        self._add_label(note_id, VIDEO_ID_LABEL, result.video_id)
        return self._published(note_id)

    def publish_question_answer(
        self,
        result: AnsweredVideoQuestion,
        *,
        question: str,
    ) -> PublishedNote:
        parent_id = self._find_note_id(VIDEO_ID_LABEL, result.video_id)
        if parent_id is None:
            parent_id = self._create_note(
                self.parent_note_id,
                format_note_title(result.title),
                render_note_html("", source_url=result.url),
            )
            self._add_label(parent_id, VIDEO_ID_LABEL, result.video_id)
        note_id = self._create_note(
            parent_id,
            format_question_title(question),
            render_note_html(result.markdown, source_url=result.url),
        )
        return self._published(note_id)

    def _published(self, note_id: str) -> PublishedNote:
        url = f"{self.ui_url}/#{note_id}" if self.ui_url else None
        return PublishedNote(note_id=note_id, url=url)

    def _find_note_id(self, label: str, value: str) -> str | None:
        query = urllib.parse.urlencode(
            {
                "search": f'#{label}="{value}"',
                "ancestorNoteId": self.parent_note_id,
                "fastSearch": "true",
                "limit": "1",
            }
        )
        payload = self._request("GET", f"/notes?{query}", expected=(200,))
        if not isinstance(payload, dict):
            return None
        results = payload.get("results") or []
        if not results:
            return None
        note_id = results[0].get("noteId")
        return str(note_id) if note_id else None

    def _create_note(self, parent_note_id: str, title: str, content: str) -> str:
        payload = self._request(
            "POST",
            "/create-note",
            json_body={
                "parentNoteId": parent_note_id,
                "title": title,
                "type": "text",
                "content": content,
            },
            expected=(201,),
        )
        if not isinstance(payload, dict):
            raise TriliumError("Trilium create-note returned a non-object response")
        note = payload.get("note") or {}
        note_id = note.get("noteId") if isinstance(note, dict) else None
        if not note_id:
            raise TriliumError("Trilium create-note response missing noteId")
        return str(note_id)

    def _add_label(self, note_id: str, name: str, value: str) -> None:
        self._request(
            "POST",
            "/attributes",
            json_body={
                "noteId": note_id,
                "type": "label",
                "name": name,
                "value": value,
                "isInheritable": False,
            },
            expected=(201,),
        )

    def _put_content(self, note_id: str, content: str) -> None:
        encoded_id = urllib.parse.quote(note_id, safe="")
        self._request(
            "PUT",
            f"/notes/{encoded_id}/content",
            raw_body=content.encode("utf-8"),
            content_type="text/plain",
            expected=(204,),
        )

    def _patch_title(self, note_id: str, title: str) -> None:
        encoded_id = urllib.parse.quote(note_id, safe="")
        self._request(
            "PATCH",
            f"/notes/{encoded_id}",
            json_body={"title": title},
            expected=(200,),
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        raw_body: bytes | None = None,
        content_type: str | None = None,
        expected: tuple[int, ...],
    ) -> object | None:
        url = f"{self.base_url}{path}"
        headers = {
            "Authorization": self.token,
            "Accept": "application/json",
        }
        data: bytes | None = None
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif raw_body is not None:
            data = raw_body
            headers["Content-Type"] = content_type or "text/plain"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                status = int(response.status)
                body = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise TriliumError(f"Trilium ETAPI {method} {path} failed: {exc.code} {detail}") from exc
        except urllib.error.URLError as exc:
            raise TriliumError(f"Trilium ETAPI {method} {path} failed: {exc.reason}") from exc
        if status not in expected:
            raise TriliumError(f"Trilium ETAPI {method} {path} returned {status}")
        if not body:
            return None
        return json.loads(body.decode("utf-8"))


def build_trilium_client(settings: Settings) -> TriliumClient:
    return TriliumClient(
        base_url=settings.trilium_etapi_url,
        token=settings.trilium_etapi_token,
        parent_note_id=settings.trilium_parent_note_id,
        ui_url=settings.trilium_ui_url,
    )
