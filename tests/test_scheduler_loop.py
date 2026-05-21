from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app import scheduler_loop


def test_next_run_after_returns_same_day_before_target_time() -> None:
    config = scheduler_loop.SchedulerLoopConfig(
        timezone_name="Asia/Bangkok",
        hour=8,
        minute=0,
    )

    current_time = datetime(2026, 5, 21, 0, 30, tzinfo=timezone.utc)

    assert scheduler_loop.next_run_after(current_time, config=config) == datetime(
        2026,
        5,
        21,
        1,
        0,
        tzinfo=timezone.utc,
    )


def test_next_run_after_rolls_to_next_day_at_target_time() -> None:
    config = scheduler_loop.SchedulerLoopConfig(
        timezone_name="Asia/Bangkok",
        hour=8,
        minute=0,
    )

    current_time = datetime(2026, 5, 21, 1, 0, tzinfo=timezone.utc)

    assert scheduler_loop.next_run_after(current_time, config=config) == datetime(
        2026,
        5,
        22,
        1,
        0,
        tzinfo=timezone.utc,
    )


def test_load_scheduler_loop_config_rejects_invalid_timezone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YT_LEARNER_SCHEDULER_TIMEZONE", "Not/A_Timezone")

    with pytest.raises(RuntimeError, match="valid IANA timezone"):
        scheduler_loop.load_scheduler_loop_config()
