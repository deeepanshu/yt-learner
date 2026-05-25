from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.scheduler_cli import run_scheduler_once
from app.telemetry import configure_logging

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SchedulerLoopConfig:
    timezone_name: str
    hour: int
    minute: int


def load_scheduler_loop_config() -> SchedulerLoopConfig:
    timezone_name = os.getenv("YT_LEARNER_SCHEDULER_TIMEZONE", "Asia/Bangkok").strip() or "Asia/Bangkok"
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(
            f"Environment variable YT_LEARNER_SCHEDULER_TIMEZONE is not a valid IANA timezone: {timezone_name}"
        ) from exc

    try:
        hour = int(os.getenv("YT_LEARNER_SCHEDULER_HOUR", "8").strip() or "8")
        minute = int(os.getenv("YT_LEARNER_SCHEDULER_MINUTE", "0").strip() or "0")
    except ValueError as exc:
        raise RuntimeError(
            "Environment variables YT_LEARNER_SCHEDULER_HOUR and YT_LEARNER_SCHEDULER_MINUTE must be integers"
        ) from exc
    if hour < 0 or hour > 23:
        raise RuntimeError("Environment variable YT_LEARNER_SCHEDULER_HOUR must be between 0 and 23")
    if minute < 0 or minute > 59:
        raise RuntimeError("Environment variable YT_LEARNER_SCHEDULER_MINUTE must be between 0 and 59")

    return SchedulerLoopConfig(
        timezone_name=timezone_name,
        hour=hour,
        minute=minute,
    )


def next_run_after(current_time: datetime, *, config: SchedulerLoopConfig) -> datetime:
    if current_time.tzinfo is None:
        raise ValueError("current_time must be timezone-aware")

    local_timezone = ZoneInfo(config.timezone_name)
    local_now = current_time.astimezone(local_timezone)
    next_local_run = local_now.replace(
        hour=config.hour,
        minute=config.minute,
        second=0,
        microsecond=0,
    )
    if local_now >= next_local_run:
        next_local_run += timedelta(days=1)
    return next_local_run.astimezone(timezone.utc)


def run_scheduler_loop(
    *,
    config: SchedulerLoopConfig,
    now_fn=datetime.now,
    sleep_fn=time.sleep,
    run_once=run_scheduler_once,
) -> None:
    LOGGER.info(
        "scheduler_loop_started timezone=%s hour=%s minute=%s",
        config.timezone_name,
        config.hour,
        config.minute,
    )
    while True:
        current_time = now_fn(timezone.utc)
        next_run_at = next_run_after(current_time, config=config)
        sleep_seconds = max(0.0, (next_run_at - current_time).total_seconds())
        LOGGER.info(
            "scheduler_loop_sleeping next_run_at=%s sleep_seconds=%.3f",
            next_run_at.isoformat(),
            sleep_seconds,
        )
        sleep_fn(sleep_seconds)
        LOGGER.info("scheduler_loop_run_started")
        try:
            exit_code = asyncio.run(run_once())
        except Exception:
            LOGGER.exception("scheduler_loop_run_failed")
            continue
        LOGGER.info("scheduler_loop_run_finished exit_code=%s", exit_code)


def main() -> int:
    configure_logging("yt-learner-scheduler")
    config = load_scheduler_loop_config()
    run_scheduler_loop(config=config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
