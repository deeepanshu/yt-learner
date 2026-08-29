from __future__ import annotations

from app.transcript import TranscriptFetchError, _transcript_api


def test_transcript_api_uses_direct_requests_without_proxy(monkeypatch) -> None:
    monkeypatch.delenv("YT_LEARNER_WEBSHARE_PROXY_USERNAME", raising=False)
    monkeypatch.delenv("YT_LEARNER_WEBSHARE_PROXY_PASSWORD", raising=False)
    seen: dict = {}

    def build_api(**kwargs):
        seen.update(kwargs)
        return object()

    monkeypatch.setattr("app.transcript.YouTubeTranscriptApi", build_api)

    assert _transcript_api() is not None
    assert seen == {}


def test_transcript_api_uses_webshare_when_both_credentials_exist(monkeypatch) -> None:
    monkeypatch.setenv("YT_LEARNER_WEBSHARE_PROXY_USERNAME", "proxy-user")
    monkeypatch.setenv("YT_LEARNER_WEBSHARE_PROXY_PASSWORD", "proxy-password")
    seen: dict = {}

    def build_api(**kwargs):
        seen.update(kwargs)
        return object()

    monkeypatch.setattr("app.transcript.YouTubeTranscriptApi", build_api)

    assert _transcript_api() is not None
    proxy = seen["proxy_config"]
    assert proxy.proxy_username == "proxy-user"
    assert proxy.proxy_password == "proxy-password"


def test_transcript_api_rejects_partial_webshare_credentials(monkeypatch) -> None:
    monkeypatch.setenv("YT_LEARNER_WEBSHARE_PROXY_USERNAME", "proxy-user")
    monkeypatch.delenv("YT_LEARNER_WEBSHARE_PROXY_PASSWORD", raising=False)

    try:
        _transcript_api()
    except TranscriptFetchError as exc:
        assert "Set both" in str(exc)
        return
    raise AssertionError("Expected TranscriptFetchError")
