from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError, PyJWTError
from mcp.server.auth.provider import AccessToken, TokenVerifier

_ALLOWED_ALGORITHMS = ["ES256", "RS256", "EdDSA"]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SupabaseMcpSettings:
    public_url: str
    supabase_url: str
    issuer_url: str
    jwks_url: str
    audience: str
    path: str
    port: int
    required_scopes: list[str]

    @classmethod
    def from_environment(cls) -> SupabaseMcpSettings:
        public_url = _required("MCP_PUBLIC_URL").rstrip("/")
        supabase_url = _required("SUPABASE_URL").rstrip("/")
        issuer_url = f"{supabase_url}/auth/v1"
        jwks_url = f"{issuer_url}/.well-known/jwks.json"
        audience = os.getenv("MCP_JWT_AUDIENCE", "").strip()
        path = _path(os.getenv("MCP_PATH", "/mcp"))
        port = _port(os.getenv("MCP_PORT", "3003"))
        required_scopes = _scopes(os.getenv("MCP_REQUIRED_SCOPES", ""))
        return cls(
            public_url=public_url,
            supabase_url=supabase_url,
            issuer_url=issuer_url,
            jwks_url=jwks_url,
            audience=audience,
            path=path,
            port=port,
            required_scopes=required_scopes,
        )


class SupabaseTokenVerifier(TokenVerifier):
    def __init__(self, settings: SupabaseMcpSettings, *, jwk_client: PyJWKClient | None = None) -> None:
        self.settings = settings
        self.jwk_client = jwk_client or PyJWKClient(settings.jwks_url)

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            claims = await asyncio.to_thread(self._decode, token)
        except (PyJWKClientError, PyJWTError, ValueError) as exc:
            logger.warning("Rejected Supabase MCP bearer token: %s", type(exc).__name__)
            return None

        client_id = str(claims.get("client_id") or claims.get("azp") or self.settings.audience)
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
        options: dict[str, Any] = {}
        kwargs: dict[str, Any] = {"algorithms": _ALLOWED_ALGORITHMS, "issuer": self.settings.issuer_url}
        if self.settings.audience:
            kwargs["audience"] = self.settings.audience
        else:
            options["verify_aud"] = False
        claims = jwt.decode(token, signing_key.key, options=options, **kwargs)
        if not isinstance(claims, dict):
            raise ValueError("Supabase token payload must be an object")
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
