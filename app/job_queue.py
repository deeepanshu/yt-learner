from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

TASK_SUMMARIZE_VIDEO = "summarize_video"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


@dataclass(frozen=True)
class Job:
    id: int
    task_type: str
    source: str
    requested_by: str
    input_data: dict[str, Any]
    status: str
    priority: int
    attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    learning_record_id: int | None
    result_path: str | None
    error: str | None

    @property
    def video_url(self) -> str:
        return str(self.input_data["video_url"])

    @property
    def reply_channel_id(self) -> int | None:
        raw = self.input_data.get("reply_channel_id")
        if raw is None:
            return None
        return int(raw)

    @property
    def reply_message_id(self) -> int | None:
        raw = self.input_data.get("reply_message_id")
        if raw is None:
            return None
        return int(raw)


class JobQueue:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def enqueue_summarize_video(
        self,
        *,
        video_url: str,
        requested_by: str,
        source: str,
        reply_channel_id: int | None,
        reply_message_id: int | None = None,
        priority: int = 0,
    ) -> Job:
        created_at = utc_now()
        input_data = {
            "video_url": video_url,
            "reply_channel_id": reply_channel_id,
            "reply_message_id": reply_message_id,
        }
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO jobs (
                    task_type,
                    source,
                    requested_by,
                    input_json,
                    status,
                    priority,
                    attempts,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    TASK_SUMMARIZE_VIDEO,
                    source,
                    requested_by,
                    json.dumps(input_data),
                    STATUS_QUEUED,
                    priority,
                    0,
                    _serialize_timestamp(created_at),
                ),
            )
            job_id = int(cursor.lastrowid)
        return self.get_job(job_id)

    def get_job(self, job_id: int) -> Job:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise LookupError(f"Job {job_id} does not exist")
        return self._row_to_job(row)

    def claim_next_job(self) -> Job | None:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT * FROM jobs
                WHERE status = ?
                ORDER BY priority DESC, id ASC
                LIMIT 1
                """,
                (STATUS_QUEUED,),
            ).fetchone()
            if row is None:
                conn.commit()
                return None

            started_at = utc_now()
            attempts = int(row["attempts"]) + 1
            conn.execute(
                """
                UPDATE jobs
                SET status = ?, attempts = ?, started_at = ?, error = NULL
                WHERE id = ?
                """,
                (
                    STATUS_RUNNING,
                    attempts,
                    _serialize_timestamp(started_at),
                    int(row["id"]),
                ),
            )
            conn.commit()
        return self.get_job(int(row["id"]))

    def mark_done(self, job_id: int, *, learning_record_id: int, result_path: str) -> Job:
        finished_at = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = ?, finished_at = ?, learning_record_id = ?, result_path = ?, error = NULL
                WHERE id = ?
                """,
                (STATUS_DONE, _serialize_timestamp(finished_at), learning_record_id, result_path, job_id),
            )
        return self.get_job(job_id)

    def mark_failed(self, job_id: int, *, error: str) -> Job:
        finished_at = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = ?, finished_at = ?, error = ?
                WHERE id = ?
                """,
                (STATUS_FAILED, _serialize_timestamp(finished_at), error, job_id),
            )
        return self.get_job(job_id)

    def update_reply_message_id(self, job_id: int, *, reply_message_id: int) -> Job:
        job = self.get_job(job_id)
        input_data = dict(job.input_data)
        input_data["reply_message_id"] = reply_message_id
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET input_json = ?
                WHERE id = ?
                """,
                (json.dumps(input_data), job_id),
            )
        return self.get_job(job_id)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    input_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 0,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    learning_record_id INTEGER,
                    result_path TEXT,
                    error TEXT
                )
                """
            )
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(jobs)").fetchall()
            }
            if "learning_record_id" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN learning_record_id INTEGER")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_status_priority_id ON jobs(status, priority DESC, id ASC)"
            )

    def _row_to_job(self, row: sqlite3.Row) -> Job:
        return Job(
            id=int(row["id"]),
            task_type=str(row["task_type"]),
            source=str(row["source"]),
            requested_by=str(row["requested_by"]),
            input_data=json.loads(str(row["input_json"])),
            status=str(row["status"]),
            priority=int(row["priority"]),
            attempts=int(row["attempts"]),
            created_at=_parse_timestamp(row["created_at"]) or utc_now(),
            started_at=_parse_timestamp(row["started_at"]),
            finished_at=_parse_timestamp(row["finished_at"]),
            learning_record_id=row["learning_record_id"],
            result_path=row["result_path"],
            error=row["error"],
        )
