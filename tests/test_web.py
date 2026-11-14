from __future__ import annotations

from starlette.testclient import TestClient

from app.channel_watches import WatchRepository
from app.config import Settings
from app.web import create_app
from app.youtube_channels import ResolvedYouTubeChannel, YouTubeChannelError


def dummy_settings(database_url: str) -> Settings:
    return Settings(
        ollama_api_key="key",
        ollama_model="test-model",
        database_url=database_url,
        trilium_etapi_url="http://trilium.example/etapi",
        trilium_etapi_token="token",
        trilium_parent_note_id="parentNote",
    )


def resolve_ai(_raw: str) -> ResolvedYouTubeChannel:
    return ResolvedYouTubeChannel(
        channel_id="UC12345678901234567890",
        title="AI Channel",
        canonical_url="https://www.youtube.com/channel/UC12345678901234567890",
    )


def test_watch_ui_lists_empty_state(database_url) -> None:
    app = create_app(settings=dummy_settings(database_url), resolve_channel=resolve_ai)
    response = TestClient(app).get("/ui/")
    assert response.status_code == 200
    assert "No watched channels yet" in response.text


def test_root_redirects_to_ui(database_url) -> None:
    app = create_app(settings=dummy_settings(database_url), resolve_channel=resolve_ai)
    response = TestClient(app, follow_redirects=False).get("/")
    assert response.status_code == 303
    assert response.headers["location"] == "/ui/"


def test_watch_ui_adds_and_removes_channel(database_url) -> None:
    app = create_app(settings=dummy_settings(database_url), resolve_channel=resolve_ai)
    client = TestClient(app)

    added = client.post("/ui/watches", data={"channel": "@ai"}, follow_redirects=True)
    assert added.status_code == 200
    assert "Watching AI Channel" in added.text
    assert "UC12345678901234567890" in added.text

    subscription = WatchRepository(database_url).list_subscriptions()[0]
    removed = client.post(f"/ui/watches/{subscription.id}/delete", follow_redirects=True)
    assert removed.status_code == 200
    assert "Stopped watching AI Channel" in removed.text
    assert "No watched channels yet" in removed.text


def test_watch_ui_shows_resolve_error(database_url) -> None:
    def explode(_raw: str) -> ResolvedYouTubeChannel:
        raise YouTubeChannelError("nope")

    app = create_app(settings=dummy_settings(database_url), resolve_channel=explode)
    response = TestClient(app).post("/ui/watches", data={"channel": "nope"}, follow_redirects=True)
    assert "I could not resolve that YouTube channel." in response.text
