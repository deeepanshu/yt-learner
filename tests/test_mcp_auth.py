from __future__ import annotations

import asyncio

from app.mcp_auth import SupabaseMcpSettings, SupabaseTokenVerifier


class StubJwkClient:
    def get_signing_key_from_jwt(self, token: str) -> object:
        return type("SigningKey", (), {"key": "unused"})()


def _settings() -> SupabaseMcpSettings:
    return SupabaseMcpSettings(
        public_url="https://ytlearner.example.com/yt/api/mcp",
        supabase_url="https://project.supabase.co",
        issuer_url="https://project.supabase.co/auth/v1",
        jwks_url="https://project.supabase.co/auth/v1/.well-known/jwks.json",
        audience="authenticated",
        path="/yt/api/mcp",
        port=3003,
        required_scopes=[],
    )


def test_supabase_settings_loads_environment(monkeypatch) -> None:
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://ytlearner.example.com/yt/api/mcp/")
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co/")
    monkeypatch.setenv("MCP_PATH", "/yt/api/mcp")
    monkeypatch.setenv("MCP_PORT", "3003")

    settings = SupabaseMcpSettings.from_environment()

    assert settings.public_url == "https://ytlearner.example.com/yt/api/mcp"
    assert settings.issuer_url == "https://project.supabase.co/auth/v1"
    assert settings.jwks_url == "https://project.supabase.co/auth/v1/.well-known/jwks.json"
    assert settings.audience == "authenticated"
    assert settings.port == 3003


def test_supabase_settings_rejects_missing_supabase_url(monkeypatch) -> None:
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://ytlearner.example.com/yt/api/mcp")
    monkeypatch.delenv("SUPABASE_URL", raising=False)

    try:
        SupabaseMcpSettings.from_environment()
    except RuntimeError as exc:
        assert str(exc) == "Missing required environment variable: SUPABASE_URL"
        return
    raise AssertionError("Expected RuntimeError")


def test_supabase_verifier_returns_oauth_client_claims(monkeypatch) -> None:
    verifier = SupabaseTokenVerifier(_settings(), jwk_client=StubJwkClient())
    monkeypatch.setattr(
        "app.mcp_auth.jwt.decode",
        lambda *args, **kwargs: {
            "client_id": "chatgpt-mcp-client",
            "sub": "user-id",
            "exp": 1_800_000_000,
            "scope": "openid email",
        },
    )

    token = asyncio.run(verifier.verify_token("signed-token"))

    assert token is not None
    assert token.client_id == "chatgpt-mcp-client"
    assert token.subject == "user-id"
    assert token.scopes == ["openid", "email"]
    assert token.expires_at == 1_800_000_000


def test_supabase_verifier_rejects_invalid_token(monkeypatch) -> None:
    verifier = SupabaseTokenVerifier(_settings(), jwk_client=StubJwkClient())

    def fail(*args, **kwargs):
        import jwt

        raise jwt.InvalidTokenError("invalid")

    monkeypatch.setattr("app.mcp_auth.jwt.decode", fail)

    assert asyncio.run(verifier.verify_token("invalid-token")) is None


def test_supabase_verifier_passes_audience_and_issuer_to_decode(monkeypatch) -> None:
    verifier = SupabaseTokenVerifier(_settings(), jwk_client=StubJwkClient())
    seen: dict = {}

    def capture(*args, **kwargs):
        seen.update(kwargs)
        return {"sub": "u", "client_id": "c"}

    monkeypatch.setattr("app.mcp_auth.jwt.decode", capture)
    asyncio.run(verifier.verify_token("token"))

    assert seen["issuer"] == "https://project.supabase.co/auth/v1"
    assert seen["audience"] == "authenticated"
