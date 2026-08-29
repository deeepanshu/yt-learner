from __future__ import annotations

import asyncio

from app.mcp_auth import CloudflareAccessSettings, CloudflareAccessTokenVerifier


class StubJwkClient:
    def get_signing_key_from_jwt(self, token: str) -> object:
        return type("SigningKey", (), {"key": "unused"})()


def test_cloudflare_access_settings_loads_environment(monkeypatch) -> None:
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://mcp.example.com/mcp/")
    monkeypatch.setenv("MCP_ACCESS_ISSUER_URL", "https://team.cloudflareaccess.com/")
    monkeypatch.setenv("MCP_ACCESS_JWKS_URL", "https://team.cloudflareaccess.com/certs")
    monkeypatch.setenv("MCP_ACCESS_AUDIENCE", "access-audience")
    monkeypatch.setenv("MCP_PORT", "3002")
    monkeypatch.setenv("MCP_ACCESS_REQUIRED_SCOPES", "openid profile")

    settings = CloudflareAccessSettings.from_environment()

    assert settings.public_url == "https://mcp.example.com/mcp"
    assert settings.issuer_url == "https://team.cloudflareaccess.com"
    assert settings.jwks_url == "https://team.cloudflareaccess.com/certs"
    assert settings.audience == "access-audience"
    assert settings.port == 3002
    assert settings.required_scopes == ["openid", "profile"]


def test_cloudflare_access_settings_rejects_missing_public_url(monkeypatch) -> None:
    monkeypatch.delenv("MCP_PUBLIC_URL", raising=False)

    try:
        CloudflareAccessSettings.from_environment()
    except RuntimeError as exc:
        assert str(exc) == "Missing required environment variable: MCP_PUBLIC_URL"
        return
    raise AssertionError("Expected RuntimeError")


def test_cloudflare_access_verifier_returns_claims(monkeypatch) -> None:
    settings = CloudflareAccessSettings(
        public_url="https://mcp.example.com/mcp",
        issuer_url="https://team.cloudflareaccess.com",
        jwks_url="https://team.cloudflareaccess.com/certs",
        audience="access-audience",
        path="/mcp",
        port=3002,
        required_scopes=[],
    )
    verifier = CloudflareAccessTokenVerifier(settings, jwk_client=StubJwkClient())
    monkeypatch.setattr(
        "app.mcp_auth.jwt.decode",
        lambda *args, **kwargs: {
            "azp": "chatgpt-client",
            "sub": "user-id",
            "exp": 1_800_000_000,
            "scope": "openid profile",
        },
    )

    token = asyncio.run(verifier.verify_token("signed-token"))

    assert token is not None
    assert token.client_id == "chatgpt-client"
    assert token.subject == "user-id"
    assert token.scopes == ["openid", "profile"]
    assert token.expires_at == 1_800_000_000


def test_cloudflare_access_verifier_rejects_invalid_token(monkeypatch) -> None:
    settings = CloudflareAccessSettings(
        public_url="https://mcp.example.com/mcp",
        issuer_url="https://team.cloudflareaccess.com",
        jwks_url="https://team.cloudflareaccess.com/certs",
        audience="access-audience",
        path="/mcp",
        port=3002,
        required_scopes=[],
    )
    verifier = CloudflareAccessTokenVerifier(settings, jwk_client=StubJwkClient())

    def fail(*args, **kwargs):
        import jwt

        raise jwt.InvalidTokenError("invalid")

    monkeypatch.setattr("app.mcp_auth.jwt.decode", fail)

    assert asyncio.run(verifier.verify_token("invalid-token")) is None
