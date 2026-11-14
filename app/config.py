from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_OLLAMA_BASE_URL = "https://ollama.com/v1"


@dataclass(frozen=True)
class Settings:
    ollama_api_key: str
    ollama_model: str
    database_url: str
    outline_url: str
    outline_api_key: str
    outline_collection_id: str
    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL
    max_transcript_chars: int | None = None
    outline_ui_url: str | None = None
    watch_ui_host: str = "0.0.0.0"
    watch_ui_port: int = 3004


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


def _optional_int_with_default(name: str, default: int) -> int:
    value = _optional_int(name)
    return default if value is None else value


def load_environment_file() -> None:
    dotenv = importlib.import_module("dotenv")
    dotenv.load_dotenv(dotenv_path=Path(".env"), override=False)


def load_settings() -> Settings:
    load_environment_file()
    return Settings(
        ollama_api_key=_required("OLLAMA_API_KEY"),
        ollama_model=_required("OLLAMA_MODEL"),
        database_url=_required("DATABASE_URL"),
        outline_url=_required("OUTLINE_URL"),
        outline_api_key=_required("OUTLINE_API_KEY"),
        outline_collection_id=_required("OUTLINE_COLLECTION_ID"),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL).strip() or DEFAULT_OLLAMA_BASE_URL,
        max_transcript_chars=_optional_int("YOUTUBE_LEARNER_MAX_TRANSCRIPT_CHARS"),
        outline_ui_url=os.getenv("OUTLINE_UI_URL", "").strip() or None,
        watch_ui_host=os.getenv("WATCH_UI_HOST", "0.0.0.0").strip() or "0.0.0.0",
        watch_ui_port=_optional_int_with_default("WATCH_UI_PORT", 3004),
    )
