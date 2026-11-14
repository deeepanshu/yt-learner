from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from app.pipeline import AnsweredVideoQuestion, ProcessedVideo
from app.trilium import TriliumClient, TriliumError


class FakeEtapi:
    def __init__(self) -> None:
        self.notes: dict[str, dict[str, object]] = {}
        self.contents: dict[str, str] = {}
        self.labels: dict[str, dict[str, str]] = {}
        self.next_id = 1
        self.server: HTTPServer | None = None
        self.thread: threading.Thread | None = None

    def __enter__(self) -> "FakeEtapi":
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path != "/etapi/notes":
                    self._send(404, {"message": "not found"})
                    return
                query = parse_qs(parsed.query)
                search = (query.get("search") or [""])[0]
                match = None
                for note_id, labels in outer.labels.items():
                    for name, value in labels.items():
                        if search == f'#{name}="{value}"':
                            match = note_id
                            break
                results = [{"noteId": match}] if match else []
                self._send(200, {"results": results})

            def do_POST(self) -> None:
                body = self._read_json()
                if self.path == "/etapi/create-note":
                    note_id = f"note{outer.next_id}"
                    outer.next_id += 1
                    outer.notes[note_id] = {
                        "noteId": note_id,
                        "title": body["title"],
                        "parentNoteId": body["parentNoteId"],
                    }
                    outer.contents[note_id] = body["content"]
                    outer.labels[note_id] = {}
                    self._send(201, {"note": {"noteId": note_id}, "branch": {}})
                    return
                if self.path == "/etapi/attributes":
                    outer.labels.setdefault(body["noteId"], {})[body["name"]] = body["value"]
                    self._send(201, body)
                    return
                self._send(404, {"message": "not found"})

            def do_PUT(self) -> None:
                prefix = "/etapi/notes/"
                suffix = "/content"
                if not self.path.startswith(prefix) or not self.path.endswith(suffix):
                    self._send(404, {"message": "not found"})
                    return
                note_id = self.path[len(prefix) : -len(suffix)]
                length = int(self.headers.get("Content-Length", "0"))
                outer.contents[note_id] = self.rfile.read(length).decode("utf-8")
                self.send_response(204)
                self.end_headers()

            def do_PATCH(self) -> None:
                prefix = "/etapi/notes/"
                if not self.path.startswith(prefix) or self.path.endswith("/content"):
                    self._send(404, {"message": "not found"})
                    return
                note_id = self.path[len(prefix) :]
                body = self._read_json()
                outer.notes[note_id]["title"] = body["title"]
                self._send(200, {"noteId": note_id, "title": body["title"]})

            def log_message(self, format: str, *args) -> None:
                return

            def _read_json(self) -> dict[str, object]:
                length = int(self.headers.get("Content-Length", "0"))
                return json.loads(self.rfile.read(length).decode("utf-8"))

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
        return f"http://{host}:{port}/etapi"


def make_client(fake: FakeEtapi) -> TriliumClient:
    return TriliumClient(
        base_url=fake.url,
        token="secret",
        parent_note_id="parentNote",
        ui_url="https://trilium.example",
    )


def test_publish_video_notes_creates_labeled_html_note() -> None:
    with FakeEtapi() as fake:
        published = make_client(fake).publish_video_notes(
            ProcessedVideo(
                learning_record_id=1,
                video_id="abc123xyz89",
                title="Demo",
                url="https://www.youtube.com/watch?v=abc123xyz89",
                filename="demo.md",
                markdown="# Learned\n\n- point",
                reused_existing=False,
            )
        )

    assert published.note_id == "note1"
    assert published.url == "https://trilium.example/#note1"
    assert fake.notes["note1"]["title"] == "Demo"
    assert fake.notes["note1"]["parentNoteId"] == "parentNote"
    assert fake.labels["note1"]["ytLearnerVideoId"] == "abc123xyz89"
    assert '<a href="https://www.youtube.com/watch?v=abc123xyz89">' in fake.contents["note1"]
    assert "<h1>Learned</h1>" in fake.contents["note1"]
    assert "<li>point</li>" in fake.contents["note1"]


def test_publish_video_notes_updates_existing_note() -> None:
    with FakeEtapi() as fake:
        client = make_client(fake)
        first = client.publish_video_notes(
            ProcessedVideo(
                learning_record_id=1,
                video_id="abc123xyz89",
                title="Old",
                url="https://www.youtube.com/watch?v=abc123xyz89",
                filename="demo.md",
                markdown="# Old",
                reused_existing=False,
            )
        )
        second = client.publish_video_notes(
            ProcessedVideo(
                learning_record_id=1,
                video_id="abc123xyz89",
                title="New title",
                url="https://www.youtube.com/watch?v=abc123xyz89",
                filename="demo.md",
                markdown="# New",
                reused_existing=True,
            )
        )

    assert first.note_id == second.note_id
    assert list(fake.notes) == ["note1"]
    assert fake.notes["note1"]["title"] == "New title"
    assert "<h1>New</h1>" in fake.contents["note1"]


def test_publish_question_answer_creates_child_note() -> None:
    with FakeEtapi() as fake:
        client = make_client(fake)
        video = client.publish_video_notes(
            ProcessedVideo(
                learning_record_id=1,
                video_id="abc123xyz89",
                title="Demo",
                url="https://www.youtube.com/watch?v=abc123xyz89",
                filename="demo.md",
                markdown="# Learned",
                reused_existing=False,
            )
        )
        answer = client.publish_question_answer(
            AnsweredVideoQuestion(
                learning_record_id=1,
                video_id="abc123xyz89",
                title="Demo",
                url="https://www.youtube.com/watch?v=abc123xyz89",
                markdown="Because of retries.",
            ),
            question="Why did it fail?",
        )

    assert answer.note_id == "note2"
    assert fake.notes["note2"]["parentNoteId"] == video.note_id
    assert fake.notes["note2"]["title"] == "Q: Why did it fail?"
    assert "Because of retries." in fake.contents["note2"]


def test_publish_video_notes_raises_on_http_error() -> None:
    client = TriliumClient(
        base_url="http://127.0.0.1:1/etapi",
        token="secret",
        parent_note_id="parentNote",
    )
    try:
        client.publish_video_notes(
            ProcessedVideo(
                learning_record_id=1,
                video_id="abc123xyz89",
                title="Demo",
                url="https://www.youtube.com/watch?v=abc123xyz89",
                filename="demo.md",
                markdown="# Learned",
                reused_existing=False,
            )
        )
    except TriliumError as exc:
        assert "failed" in str(exc)
    else:
        raise AssertionError("expected TriliumError")
