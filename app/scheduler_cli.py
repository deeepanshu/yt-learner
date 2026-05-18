from __future__ import annotations

import asyncio
import logging

from app.channel_watches import WatchRepository
from app.config import load_settings
from app.job_queue import JobQueue
from app.scheduler import ChannelScheduler
from app.storage import OutputStore
from app.telemetry import configure_logging

LOGGER = logging.getLogger(__name__)


async def run_scheduler_once() -> int:
    settings = load_settings()
    queue = JobQueue(settings.db_path)
    watch_repository = WatchRepository(settings.db_path)
    store = OutputStore(settings.discord_output_dir, settings.db_path)
    scheduler = ChannelScheduler(
        watch_repository=watch_repository,
        queue=queue,
        store=store,
    )
    result = await scheduler.poll_once()
    LOGGER.info(
        "scheduler_cli_poll_finished subscriptions_polled=%s videos_seen=%s jobs_enqueued=%s",
        result.subscriptions_polled,
        result.videos_seen,
        result.jobs_enqueued,
    )
    return 0


def main() -> int:
    configure_logging("yt-learner-scheduler")
    return asyncio.run(run_scheduler_once())


if __name__ == "__main__":
    raise SystemExit(main())
