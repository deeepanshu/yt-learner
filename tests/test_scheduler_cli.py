from __future__ import annotations

import asyncio
from pathlib import Path

from app import scheduler_cli


class FakeScheduler:
    init_args = None

    def __init__(self, *, watch_repository, queue, store) -> None:
        type(self).init_args = {
            "watch_repository": watch_repository,
            "queue": queue,
            "store": store,
        }

    async def poll_once(self):
        return type(
            "Result",
            (),
            {
                "subscriptions_polled": 2,
                "videos_seen": 3,
                "jobs_enqueued": 1,
            },
        )()


def test_run_scheduler_once_uses_current_queue_and_store(monkeypatch, tmp_path: Path) -> None:
    settings = type(
        "Settings",
        (),
        {
            "db_path": tmp_path / "data" / "yt_learner.sqlite3",
            "discord_output_dir": tmp_path / "outputs",
        },
    )()

    monkeypatch.setattr(scheduler_cli, "load_settings", lambda: settings)
    monkeypatch.setattr(scheduler_cli, "ChannelScheduler", FakeScheduler)

    result = asyncio.run(scheduler_cli.run_scheduler_once())

    assert result == 0
    assert FakeScheduler.init_args is not None
    assert FakeScheduler.init_args["queue"].db_path == settings.db_path
    assert FakeScheduler.init_args["watch_repository"].db_path == settings.db_path
    assert FakeScheduler.init_args["store"].db_path == settings.db_path
    assert FakeScheduler.init_args["store"].root == settings.discord_output_dir
