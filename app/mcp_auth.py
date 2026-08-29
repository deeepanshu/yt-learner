from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError, PyJWTError
from mcp.server.auth.provider import AccessToken, TokenVerifier


@dataclass(frozen=True)
class CloudflareAccessSettings:
    public_url: str
    issuer_url: str
    jwks_url: str
    audience: str
    path: str
    port: int
    required_scopes: list[str]

    @classmethod
    def from_environment(cls) -> CloudflareAccessSettings:
        public_url = _required("MCP_PUBLIC_URL").rstrip("/")
        issuer_url = _required("MCP_ACCESS_ISSUER_URL").rstrip("/")
        jwks_url = _required("MCP_ACCESS_JWKS_URL")
        audience = _required("MCP_ACCESS_AUDIENCE")
        path = _path(os.getenv("MCP_PATH", "/mcp"))
        port = _port(os.getenv("MCP_PORT", "3002"))
        required_scopes = _scopes(os.getenv("MCP_ACCESS_REQUIRED_SCOPES", ""))
        return cls(
            public_url=public_url,
            issuer_url=issuer_url,
            jwks_url=jwks_url,
            audience=audience,
            path=path,
            port=port,
            required_scopes=required_scopes,
        )


class CloudflareAccessTokenVerifier(TokenVerifier):
    def __init__(self, settings: CloudflareAccessSettings, *, jwk_client: PyJWKClient | None = None) -> None:
        self.settings = settings
        self.jwk_client = jwk_client or PyJWKClient(settings.jwks_url)

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            claims = await asyncio.to_thread(self._decode, token)
        except (PyJWKClientError, PyJWTError, ValueError):
            return None

        client_id = str(claims.get("azp") or claims.get("client_id") or self.settings.audience)
        subject = claims.get("sub")
        expires_at = claims.get("exp")
        return AccessToken(
            token=token,
            client_id=client_id,
            scopes=_scopes(claims.get("scope", "")),
            expires_at=expires_at if isinstance(expires_at, int) else None,
            subject=subject if isinstance(subject, str) else None,
            claims=claims,
        )

    def _decode(self, token: str) -> dict[str, Any]:
        signing_key = self.jwk_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=self.settings.audience,
            issuer=self.settings.issuer_url,
        )
        if not isinstance(claims, dict):
            raise ValueError("Cloudflare Access token payload must be an object")
        return claims


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _port(raw: str) -> int:
    try:
        port = int(raw)
    except ValueError as exc:
        raise RuntimeError("Environment variable MCP_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise RuntimeError("Environment variable MCP_PORT must be between 1 and 65535")
    return port

def _path(raw: str) -> str:
    path = raw.strip().rstrip("/")
    if not path.startswith("/"):
        raise RuntimeError("Environment variable MCP_PATH must start with /")
    return path


def _scopes(raw: object) -> list[str]:
    if isinstance(raw, str):
        return [scope for scope in raw.split() if scope]
    if isinstance(raw, list) and all(isinstance(scope, str) for scope in raw):
        return raw
    return []
