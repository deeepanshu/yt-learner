from __future__ import annotations

import os

import pytest

from app.db import apply_migrations, connect

DEFAULT_TEST_DATABASE_URL = "postgres://yt_learner:yt_learner@127.0.0.1:55432/yt_learner_test"
TRUNCATE_SQL = """
TRUNCATE TABLE
    debug_artifacts,
    watched_channel_videos,
    watched_channels,
    jobs,
    learning_records,
    sources
RESTART IDENTITY CASCADE
"""


@pytest.fixture(scope="session")
def postgres_url() -> str:
    url = os.getenv("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    try:
        apply_migrations(url)
    except Exception as exc:
        pytest.fail(
            f"Postgres is required at {url}. Start it with `make test-db`. ({exc})"
        )
    return url


@pytest.fixture
def database_url(postgres_url: str) -> str:
    with connect(postgres_url) as conn:
        conn.execute(TRUNCATE_SQL)
    return postgres_url
