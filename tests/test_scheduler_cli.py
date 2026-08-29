from __future__ import annotations

import asyncio

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


def test_run_scheduler_once_uses_current_queue_and_store(monkeypatch, database_url) -> None:
    settings = type(
        "Settings",
        (),
        {
            "database_url": database_url,
        },
    )()

    monkeypatch.setattr(scheduler_cli, "load_settings", lambda: settings)
    monkeypatch.setattr(scheduler_cli, "ChannelScheduler", FakeScheduler)

    result = asyncio.run(scheduler_cli.run_scheduler_once())

    assert result == 0
    assert FakeScheduler.init_args is not None
    assert FakeScheduler.init_args["queue"].database_url == settings.database_url
    assert FakeScheduler.init_args["watch_repository"].database_url == settings.database_url
    assert FakeScheduler.init_args["store"].database_url == settings.database_url
