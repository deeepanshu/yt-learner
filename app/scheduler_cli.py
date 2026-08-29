from __future__ import annotations

import asyncio
import logging
import time

from app.channel_watches import WatchRepository
from app.config import load_settings
from app.job_queue import JobQueue
from app.scheduler import ChannelScheduler
from app.storage import OutputStore
from app.telemetry import NoopTelemetry, configure_logging, configure_telemetry

LOGGER = logging.getLogger(__name__)


async def run_scheduler_once(telemetry=None) -> int:
    telemetry = telemetry or NoopTelemetry()
    settings = load_settings()
    queue = JobQueue(settings.database_url)
    watch_repository = WatchRepository(settings.database_url)
    store = OutputStore(settings.database_url)
    scheduler = ChannelScheduler(
        watch_repository=watch_repository,
        queue=queue,
        store=store,
    )
    started = time.perf_counter()
    try:
        result = await scheduler.poll_once()
    except Exception:
        telemetry.record_scheduler_run(
            status="failed",
            duration_seconds=time.perf_counter() - started,
        )
        raise
    telemetry.record_scheduler_run(
        status="ok",
        duration_seconds=time.perf_counter() - started,
        subscriptions_polled=result.subscriptions_polled,
        videos_seen=result.videos_seen,
        jobs_enqueued=result.jobs_enqueued,
    )
    LOGGER.info(
        "scheduler_cli_poll_finished subscriptions_polled=%s videos_seen=%s jobs_enqueued=%s",
        result.subscriptions_polled,
        result.videos_seen,
        result.jobs_enqueued,
    )
    return 0


def main() -> int:
    configure_logging("yt-learner-scheduler")
    telemetry = configure_telemetry("yt-learner-scheduler")
    return asyncio.run(run_scheduler_once(telemetry))


if __name__ == "__main__":
    raise SystemExit(main())
