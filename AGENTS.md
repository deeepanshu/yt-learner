# AGENTS.md

## Purpose

This file is the working guide for coding agents making changes in this repository. It summarizes the project shape, the main commands, and the constraints that matter when editing code here.

## Project Overview

`yt-learner` is a Discord-first MVP that turns a YouTube URL into structured markdown learning notes.

The runtime is split into two long-lived processes and one scheduled process:

- `yt-learner-discord` receives Discord messages and slash commands, validates requests, and enqueues jobs.
- `yt-learner-worker` claims queued jobs from Postgres, runs the extraction pipeline, and posts results back to Discord.
- `yt-learner-scheduler` polls watched YouTube channels on a wall-clock schedule.

Normal behavior depends on bot and worker running. If only the Discord bot is running, jobs will enqueue but not complete.

## Repo Map

- `app/` contains the application code.
- `app/discord_bot.py` is the Discord entrypoint.
- `app/worker.py` is the worker entrypoint.
- `app/job_queue.py` contains the Postgres-backed queue.
- `app/db.py` and `app/migrations/` contain connection helpers and SQL migrations.
- `app/pipeline.py` contains the shared processing pipeline.
- `app/storage.py` stores sources, notes, and debug transcripts in Postgres.
- `tests/` contains pytest coverage for the current behavior.
- `docs/adr/` contains architectural decisions.
- `grafana/dashboards/` contains the app-owned Grafana dashboard.

## Common Commands

Setup and dependency sync:

```bash
uv sync
```

Run tests (starts local Postgres on port 55432):

```bash
make test
```

Run the Discord bot locally:

```bash
make run-bot
```

Run the worker locally:

```bash
make run-worker
```

Run one scheduler pass locally:

```bash
make run-scheduler
```

Apply migrations:

```bash
uv run yt-learner-migrate
```

Run both bot and worker locally:

```bash
make run-all
```

Check service configuration:

```bash
make check
```

Docker:

```bash
make docker-up
make docker-logs
```

## Environment

Copy `.env.example` to `.env` and fill in the required values before local runs.

Required values:

- `OPENAI_API_KEY`
- `DISCORD_BOT_TOKEN`
- `DATABASE_URL`

Common optional values:

- `DISCORD_ALLOWED_CHANNEL_ID`
- `DISCORD_ALLOWED_USER_ID`
- `OPENAI_MODEL`
- `YOUTUBE_LEARNER_MAX_TRANSCRIPT_CHARS`
- `OTEL_EXPORTER_OTLP_ENDPOINT`
- `OTEL_EXPORTER_OTLP_PROTOCOL`
- `OTEL_RESOURCE_ATTRIBUTES`

## Working Rules for Agents

- Keep edits targeted and consistent with the current two-process architecture plus scheduler.
- Prefer extending existing modules over introducing duplicate abstractions.
- Treat the bot, queue, worker, and pipeline boundaries as intentional unless the task explicitly changes them.
- Postgres is the only application database. Do not reintroduce SQLite.
- Notes live in `learning_records.markdown`, not on disk.
- Add or update tests when behavior changes. Tests require Postgres (`make test`).
- Keep setup and run instructions aligned with `README.md`, `Makefile`, and `pyproject.toml`.

## Change Expectations

- If you change user-visible behavior, update tests first or alongside the code change.
- If you change setup, commands, or environment variables, update `README.md` and any affected examples.
- If you change architectural direction, add or update an ADR in `docs/adr/`.
