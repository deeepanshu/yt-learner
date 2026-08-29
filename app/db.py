from __future__ import annotations

from datetime import datetime, timezone
from importlib import resources

import psycopg
from psycopg.rows import dict_row

Row = dict[str, object]


def connect(database_url: str) -> psycopg.Connection:
    return psycopg.connect(database_url, row_factory=dict_row)


def apply_migrations(database_url: str) -> None:
    migration_root = resources.files("app.migrations")
    files = sorted(
        path for path in migration_root.iterdir() if path.name.endswith(".sql")
    )
    with connect(database_url) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        applied = {
            str(row["filename"])
            for row in conn.execute("SELECT filename FROM schema_migrations").fetchall()
        }
        for path in files:
            if path.name in applied:
                continue
            for statement in _statements(path.read_text(encoding="utf-8")):
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_migrations (filename) VALUES (%s)",
                (path.name,),
            )


def as_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    return datetime.fromisoformat(str(value))


def _statements(script: str) -> list[str]:
    return [part.strip() for part in script.split(";") if part.strip()]
