from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


SHARED_ENV_PATHS = (
    Path("/home/deepanshu/config/shared.env"),
    Path("/home/deepanshu/config/shared.secrets.env"),
)


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    discord_bot_token: str
    discord_allowed_user_id: str | None
    discord_output_dir: Path
    db_path: Path
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


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = value.strip().strip('"').strip("'")
    return values


def load_environment_files() -> None:
    values: dict[str, str] = {}
    for env_path in (*SHARED_ENV_PATHS, Path(".env")):
        values.update(_read_env_file(env_path))
    for key, value in values.items():
        os.environ.setdefault(key, value)


def load_settings() -> Settings:
    load_environment_files()
    output_dir = Path(os.getenv("DISCORD_OUTPUT_DIR", "./outputs")).expanduser().resolve()
    db_path = Path(os.getenv("YOUTUBE_LEARNER_DB_PATH", "./data/yt_learner.sqlite3")).expanduser().resolve()
    return Settings(
        openai_api_key=_required("OPENAI_API_KEY"),
        discord_bot_token=_required("DISCORD_BOT_TOKEN"),
        discord_allowed_user_id=os.getenv("DISCORD_ALLOWED_USER_ID", "").strip() or None,
        discord_output_dir=output_dir,
        db_path=db_path,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
        allowed_channel_id=os.getenv("DISCORD_ALLOWED_CHANNEL_ID", "").strip() or None,
        max_transcript_chars=_optional_int("YOUTUBE_LEARNER_MAX_TRANSCRIPT_CHARS"),
    )
