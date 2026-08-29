from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from psycopg.types.json import Jsonb

from app.db import as_datetime, connect

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

TASK_SUMMARIZE_VIDEO = "summarize_video"
TASK_ANSWER_VIDEO_QUESTION = "answer_video_question"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


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
    result_filename: str | None
    error: str | None

    @property
    def video_url(self) -> str:
        return str(self.input_data.get("video_url", ""))

    @property
    def video_id(self) -> str | None:
        raw = self.input_data.get("video_id")
        if raw is None:
            return None
        return str(raw)

    @property
    def question(self) -> str | None:
        raw = self.input_data.get("question")
        if not isinstance(raw, str):
            return None
        cleaned = raw.strip()
        return cleaned or None

    @property
    def reply_channel_id(self) -> int | None:
        raw = self.input_data.get("reply_channel_id")
        if raw is None:
            return None
        return int(raw)

    @property
    def guild_id(self) -> str | None:
        raw = self.input_data.get("guild_id")
        if raw is None:
            return None
        return str(raw)

    @property
    def reply_message_id(self) -> int | None:
        raw = self.input_data.get("reply_message_id")
        if raw is None:
            return None
        return int(raw)

    @property
    def extra_prompt(self) -> str | None:
        raw = self.input_data.get("extra_prompt")
        if not isinstance(raw, str):
            return None
        cleaned = raw.strip()
        return cleaned or None


class JobQueue:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def enqueue_summarize_video(
        self,
        *,
        video_url: str,
        requested_by: str,
        source: str,
        reply_channel_id: int | None,
        reply_message_id: int | None = None,
        guild_id: str | None = None,
        extra_prompt: str | None = None,
        priority: int = 0,
    ) -> Job:
        input_data = {
            "video_url": video_url,
            "reply_channel_id": reply_channel_id,
            "reply_message_id": reply_message_id,
            "guild_id": guild_id,
        }
        if extra_prompt is not None:
            input_data["extra_prompt"] = extra_prompt
        return self._enqueue_job(
            task_type=TASK_SUMMARIZE_VIDEO,
            requested_by=requested_by,
            source=source,
            input_data=input_data,
            priority=priority,
        )

    def enqueue_answer_video_question(
        self,
        *,
        video_id: str,
        question: str,
        requested_by: str,
        source: str,
        reply_channel_id: int | None,
        reply_message_id: int | None,
        guild_id: str | None,
        priority: int = 0,
    ) -> Job:
        return self._enqueue_job(
            task_type=TASK_ANSWER_VIDEO_QUESTION,
            requested_by=requested_by,
            source=source,
            input_data={
                "video_id": video_id,
                "question": question,
                "reply_channel_id": reply_channel_id,
                "reply_message_id": reply_message_id,
                "guild_id": guild_id,
            },
            priority=priority,
        )

    def _enqueue_job(
        self,
        *,
        task_type: str,
        requested_by: str,
        source: str,
        input_data: dict[str, Any],
        priority: int,
    ) -> Job:
        created_at = utc_now()
        with connect(self.database_url) as conn:
            row = conn.execute(
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
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    task_type,
                    source,
                    requested_by,
                    Jsonb(input_data),
                    STATUS_QUEUED,
                    priority,
                    0,
                    created_at,
                ),
            ).fetchone()
        if row is None:
            raise RuntimeError("Unable to enqueue job")
        return self._row_to_job(row)

    def get_job(self, job_id: int) -> Job:
        with connect(self.database_url) as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = %s", (job_id,)).fetchone()
        if row is None:
            raise LookupError(f"Job {job_id} does not exist")
        return self._row_to_job(row)

    def claim_next_job(self) -> Job | None:
        with connect(self.database_url) as conn:
            with conn.transaction():
                row = conn.execute(
                    """
                    SELECT * FROM jobs
                    WHERE status = %s
                    ORDER BY priority DESC, id ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                    """,
                    (STATUS_QUEUED,),
                ).fetchone()
                if row is None:
                    return None

                started_at = utc_now()
                attempts = int(row["attempts"]) + 1
                updated = conn.execute(
                    """
                    UPDATE jobs
                    SET status = %s, attempts = %s, started_at = %s, error = NULL
                    WHERE id = %s
                    RETURNING *
                    """,
                    (STATUS_RUNNING, attempts, started_at, int(row["id"])),
                ).fetchone()
        if updated is None:
            return None
        return self._row_to_job(updated)

    def mark_done(
        self,
        job_id: int,
        *,
        learning_record_id: int | None,
        result_filename: str,
    ) -> Job:
        finished_at = utc_now()
        with connect(self.database_url) as conn:
            row = conn.execute(
                """
                UPDATE jobs
                SET status = %s, finished_at = %s, learning_record_id = %s, result_filename = %s, error = NULL
                WHERE id = %s
                RETURNING *
                """,
                (STATUS_DONE, finished_at, learning_record_id, result_filename, job_id),
            ).fetchone()
        if row is None:
            raise LookupError(f"Job {job_id} does not exist")
        return self._row_to_job(row)

    def mark_failed(self, job_id: int, *, error: str) -> Job:
        finished_at = utc_now()
        with connect(self.database_url) as conn:
            row = conn.execute(
                """
                UPDATE jobs
                SET status = %s, finished_at = %s, error = %s
                WHERE id = %s
                RETURNING *
                """,
                (STATUS_FAILED, finished_at, error, job_id),
            ).fetchone()
        if row is None:
            raise LookupError(f"Job {job_id} does not exist")
        return self._row_to_job(row)

    def update_reply_message_id(self, job_id: int, *, reply_message_id: int) -> Job:
        job = self.get_job(job_id)
        input_data = dict(job.input_data)
        input_data["reply_message_id"] = reply_message_id
        with connect(self.database_url) as conn:
            row = conn.execute(
                """
                UPDATE jobs
                SET input_json = %s
                WHERE id = %s
                RETURNING *
                """,
                (Jsonb(input_data), job_id),
            ).fetchone()
        if row is None:
            raise LookupError(f"Job {job_id} does not exist")
        return self._row_to_job(row)

    def _row_to_job(self, row: dict[str, object]) -> Job:
        raw_input = row["input_json"]
        input_data = raw_input if isinstance(raw_input, dict) else {}
        learning_record_id = row["learning_record_id"]
        return Job(
            id=int(row["id"]),
            task_type=str(row["task_type"]),
            source=str(row["source"]),
            requested_by=str(row["requested_by"]),
            input_data=input_data,
            status=str(row["status"]),
            priority=int(row["priority"]),
            attempts=int(row["attempts"]),
            created_at=as_datetime(row["created_at"]) or utc_now(),
            started_at=as_datetime(row["started_at"]),
            finished_at=as_datetime(row["finished_at"]),
            learning_record_id=int(learning_record_id) if learning_record_id is not None else None,
            result_filename=str(row["result_filename"]) if row["result_filename"] is not None else None,
            error=str(row["error"]) if row["error"] is not None else None,
        )
