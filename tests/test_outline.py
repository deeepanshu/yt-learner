from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from app.outline import OutlineClient, OutlineError
from app.pipeline import ProcessedVideo


class FakeOutline:
    def __init__(self) -> None:
        self.documents: dict[str, dict[str, object]] = {}
        self.next_id = 1
        self.server: HTTPServer | None = None
        self.thread: threading.Thread | None = None

    def __enter__(self) -> "FakeOutline":
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                if self.path == "/api/collections.list":
                    self._send(200, {"ok": True, "data": [{"id": "collection-uuid", "urlId": "FuBlx35cfL"}]})
                    return
                if self.path == "/api/documents.search":
                    query = body["query"]
                    matches = [
                        {"document": document}
                        for document in outer.documents.values()
                        if query in str(document["text"])
                    ]
                    self._send(200, {"ok": True, "data": matches})
                    return
                if self.path == "/api/documents.create":
                    document_id = f"document-{outer.next_id}"
                    outer.next_id += 1
                    document = {
                        "id": document_id,
                        "urlId": f"url-{outer.next_id}",
                        **body,
                    }
                    outer.documents[document_id] = document
                    self._send(200, {"ok": True, "data": document})
                    return
                if self.path == "/api/documents.update":
                    document = outer.documents[body["id"]]
                    document.update({key: value for key, value in body.items() if key != "id"})
                    self._send(200, {"ok": True, "data": document})
                    return
                self._send(404, {"ok": False, "error": "not found"})

            def log_message(self, format: str, *args) -> None:
                return

            def _send(self, status: int, payload: dict[str, object]) -> None:
                encoded = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        assert self.server is not None
        self.server.shutdown()
        self.server.server_close()
        if self.thread is not None:
            self.thread.join(timeout=2)

    @property
    def url(self) -> str:
        assert self.server is not None
        host, port = self.server.server_address
        return f"http://{host}:{port}"


def make_client(fake: FakeOutline) -> OutlineClient:
    return OutlineClient(
        base_url=fake.url,
        token="secret",
        collection_id="FuBlx35cfL",
        ui_url="https://outline.example",
    )


def video(title: str = "Demo", markdown: str = "# Learned") -> ProcessedVideo:
    return ProcessedVideo(
        learning_record_id=1,
        video_id="abc123xyz89",
        title=title,
        url="https://www.youtube.com/watch?v=abc123xyz89",
        filename="demo.md",
        markdown=markdown,
        reused_existing=False,
        channel_title="AI Engineer",
    )


def test_publish_video_notes_creates_channel_and_video() -> None:
    with FakeOutline() as fake:
        published = make_client(fake).publish_video_notes(video())

    assert published.note_id == "document-2"
    assert published.url == "https://outline.example/doc/url-3"
    channel = fake.documents["document-1"]
    note = fake.documents["document-2"]
    assert channel["title"] == "AI Engineer"
    assert note["title"] == "Demo"
    assert note["collectionId"] == "collection-uuid"
    assert note["parentDocumentId"] == "document-1"
    assert "[Watch on YouTube]" in note["text"]
    assert "yt-learner-video:abc123xyz89" in note["text"]


def test_publish_video_notes_updates_existing_document() -> None:
    with FakeOutline() as fake:
        client = make_client(fake)
        first = client.publish_video_notes(video())
        second = client.publish_video_notes(video(title="New title", markdown="# New"))

    assert first.note_id == second.note_id == "document-2"
    assert fake.documents["document-2"]["title"] == "New title"
    assert "# New" in fake.documents["document-2"]["text"]


def test_outline_error_is_raised_for_api_error() -> None:
    client = OutlineClient(
        base_url="http://127.0.0.1:1",
        token="secret",
        collection_id="FuBlx35cfL",
    )
    try:
        client.publish_video_notes(video())
    except OutlineError as exc:
        assert "failed" in str(exc)
    else:
        raise AssertionError("expected OutlineError")
