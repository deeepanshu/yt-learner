from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from psycopg.types.json import Jsonb

from app.db import apply_migrations, connect


def _parse_timestamp(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value))


def _read_markdown(path_value: object) -> str:
    if not path_value:
        return ""
    path = Path(str(path_value))
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def import_sqlite(sqlite_path: Path, database_url: str) -> None:
    apply_migrations(database_url)
    sqlite = sqlite3.connect(sqlite_path)
    sqlite.row_factory = sqlite3.Row

    with connect(database_url) as pg:
        source_id_map: dict[int, int] = {}
        for row in sqlite.execute("SELECT * FROM sources ORDER BY id"):
            inserted = pg.execute(
                """
                INSERT INTO sources (source_type, source_key, source_ref, title, created_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (source_type, source_key) DO UPDATE SET
                    source_ref = excluded.source_ref,
                    title = excluded.title
                RETURNING id
                """,
                (
                    row["source_type"],
                    row["source_key"],
                    row["source_ref"],
                    row["title"],
                    _parse_timestamp(row["created_at"]) or datetime.now(timezone.utc),
                ),
            ).fetchone()
            if inserted is not None:
                source_id_map[int(row["id"])] = int(inserted["id"])

        for row in sqlite.execute("SELECT * FROM learning_records ORDER BY id"):
            source_id = source_id_map.get(int(row["source_id"]))
            if source_id is None:
                continue
            markdown = _read_markdown(row["artifact_path"])
            filename = Path(str(row["artifact_path"])).name if row["artifact_path"] else "notes.md"
            pg.execute(
                """
                INSERT INTO learning_records (
                    source_id, record_type, title, filename, markdown, requested_by, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_id, record_type) DO UPDATE SET
                    title = excluded.title,
                    filename = excluded.filename,
                    markdown = excluded.markdown,
                    requested_by = excluded.requested_by,
                    updated_at = excluded.updated_at
                """,
                (
                    source_id,
                    row["record_type"],
                    row["title"],
                    filename,
                    markdown,
                    row["requested_by"],
                    _parse_timestamp(row["created_at"]) or datetime.now(timezone.utc),
                    _parse_timestamp(row["updated_at"]) or datetime.now(timezone.utc),
                ),
            )

        watch_id_map: dict[int, int] = {}
        try:
            watch_rows = sqlite.execute("SELECT * FROM watched_channels ORDER BY id").fetchall()
        except sqlite3.OperationalError:
            watch_rows = []
        for row in watch_rows:
            inserted = pg.execute(
                """
                INSERT INTO watched_channels (
                    guild_id, youtube_channel_id, youtube_channel_ref, youtube_channel_title,
                    discord_channel_id, is_active, bootstrap_completed_at, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (guild_id, youtube_channel_id) DO UPDATE SET
                    youtube_channel_ref = excluded.youtube_channel_ref,
                    youtube_channel_title = excluded.youtube_channel_title,
                    discord_channel_id = excluded.discord_channel_id,
                    is_active = excluded.is_active,
                    bootstrap_completed_at = excluded.bootstrap_completed_at,
                    updated_at = excluded.updated_at
                RETURNING id
                """,
                (
                    row["guild_id"],
                    row["youtube_channel_id"],
                    row["youtube_channel_ref"],
                    row["youtube_channel_title"],
                    int(row["discord_channel_id"]),
                    bool(row["is_active"]),
                    _parse_timestamp(row["bootstrap_completed_at"]),
                    _parse_timestamp(row["created_at"]) or datetime.now(timezone.utc),
                    _parse_timestamp(row["updated_at"]) or datetime.now(timezone.utc),
                ),
            ).fetchone()
            if inserted is not None:
                watch_id_map[int(row["id"])] = int(inserted["id"])

        try:
            video_rows = sqlite.execute("SELECT * FROM watched_channel_videos ORDER BY id").fetchall()
        except sqlite3.OperationalError:
            video_rows = []
        for row in video_rows:
            watched_channel_id = watch_id_map.get(int(row["watched_channel_id"]))
            if watched_channel_id is None:
                continue
            pg.execute(
                """
                INSERT INTO watched_channel_videos (
                    watched_channel_id, video_id, video_url, title, published_at,
                    discovered_at, queued_job_id, learning_record_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (watched_channel_id, video_id) DO NOTHING
                """,
                (
                    watched_channel_id,
                    row["video_id"],
                    row["video_url"],
                    row["title"],
                    _parse_timestamp(row["published_at"]),
                    _parse_timestamp(row["discovered_at"]) or datetime.now(timezone.utc),
                    row["queued_job_id"],
                    row["learning_record_id"],
                ),
            )

        try:
            thread_rows = sqlite.execute("SELECT * FROM discord_threads ORDER BY id").fetchall()
        except sqlite3.OperationalError:
            thread_rows = []
        for row in thread_rows:
            pg.execute(
                """
                INSERT INTO discord_threads (
                    guild_id, parent_channel_id, purpose, source_type, source_key,
                    thread_id, title, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (guild_id, parent_channel_id, purpose, source_type, source_key)
                DO NOTHING
                """,
                (
                    row["guild_id"],
                    int(row["parent_channel_id"]),
                    row["purpose"],
                    row["source_type"],
                    row["source_key"],
                    int(row["thread_id"]),
                    row["title"],
                    _parse_timestamp(row["created_at"]) or datetime.now(timezone.utc),
                    _parse_timestamp(row["updated_at"]) or datetime.now(timezone.utc),
                ),
            )

        try:
            job_rows = sqlite.execute("SELECT * FROM jobs ORDER BY id").fetchall()
        except sqlite3.OperationalError:
            job_rows = []
        for row in job_rows:
            status = str(row["status"])
            if status in {"queued", "running"}:
                continue
            input_data = json.loads(str(row["input_json"]))
            result_filename = None
            if row["result_path"]:
                result_filename = Path(str(row["result_path"])).name
            pg.execute(
                """
                INSERT INTO jobs (
                    task_type, source, requested_by, input_json, status, priority, attempts,
                    created_at, started_at, finished_at, learning_record_id, result_filename, error
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    row["task_type"],
                    row["source"],
                    row["requested_by"],
                    Jsonb(input_data),
                    status,
                    int(row["priority"]),
                    int(row["attempts"]),
                    _parse_timestamp(row["created_at"]) or datetime.now(timezone.utc),
                    _parse_timestamp(row["started_at"]),
                    _parse_timestamp(row["finished_at"]),
                    row["learning_record_id"],
                    result_filename,
                    row["error"],
                ),
            )

    sqlite.close()


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Import a yt-learner SQLite database into Postgres.")
    parser.add_argument("sqlite_path", type=Path)
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", "").strip(),
        help="Postgres URL. Defaults to DATABASE_URL.",
    )
    args = parser.parse_args()
    if not args.database_url:
        raise RuntimeError("Missing DATABASE_URL")
    import_sqlite(args.sqlite_path.expanduser().resolve(), args.database_url)
    print("import complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
