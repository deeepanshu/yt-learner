from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    discord_bot_token: str
    database_url: str
    discord_allowed_user_id: str | None
    openai_model: str = "gpt-4o-mini"
    allowed_channel_id: str | None = None
    max_transcript_chars: int | None = None


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _optional_int(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {name} must be an integer") from exc


def load_environment_file() -> None:
    dotenv = importlib.import_module("dotenv")
    dotenv.load_dotenv(dotenv_path=Path(".env"), override=False)


def load_settings() -> Settings:
    load_environment_file()
    return Settings(
        openai_api_key=_required("OPENAI_API_KEY"),
        discord_bot_token=_required("DISCORD_BOT_TOKEN"),
        database_url=_required("DATABASE_URL"),
        discord_allowed_user_id=os.getenv("DISCORD_ALLOWED_USER_ID", "").strip() or None,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
        allowed_channel_id=os.getenv("DISCORD_ALLOWED_CHANNEL_ID", "").strip() or None,
        max_transcript_chars=_optional_int("YOUTUBE_LEARNER_MAX_TRANSCRIPT_CHARS"),
    )
