# AGENTS.md

## Purpose

This file is the working guide for coding agents making changes in this repository. It summarizes the project shape, the main commands, and the constraints that matter when editing code here.

## Project Overview

`yt-learner` is a Discord-first MVP that turns a YouTube URL into structured markdown learning notes.

The runtime is split into two long-lived processes:

- `yt-learner-discord` receives Discord messages and slash commands, validates requests, and enqueues jobs.
- `yt-learner-worker` claims queued jobs from SQLite, runs the extraction pipeline, and posts results back to Discord.

Normal behavior depends on both processes running. If only the Discord bot is running, jobs will enqueue but not complete.

## Repo Map

- `app/` contains the application code.
- `app/discord_bot.py` is the Discord entrypoint.
- `app/worker.py` is the worker entrypoint.
- `app/job_queue.py` contains the SQLite-backed queue.
- `app/pipeline.py` contains the shared processing pipeline.
- `app/storage.py`, `app/transcript.py`, `app/extractor.py`, and related modules support persistence and extraction.
- `tests/` contains pytest coverage for the current behavior.
- `docs/adr/` contains architectural decisions.
- `scripts/service.sh` wraps `systemd` operations used by the Makefile.
- `outputs/` stores generated markdown artifacts.
- `data/` contains local runtime data such as the database path when configured that way.

## Common Commands

Setup and dependency sync:

```bash
uv sync
```

Run tests:

```bash
uv run pytest
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

Run both processes locally:

```bash
make run-all
```

Check service configuration:

```bash
make check
```

Manage services:

```bash
make service-install
make service-restart
make service-status
make service-logs
make service-stop
```

Service-specific targets are also available for `bot`, `worker`, and `scheduler`.

## Environment

Copy `.env.example` to `.env` and fill in the required values before local runs.

Required values:

- `OPENAI_API_KEY`
- `DISCORD_BOT_TOKEN`

Common optional values:

- `DISCORD_ALLOWED_CHANNEL_ID`
- `DISCORD_ALLOWED_USER_ID`
- `DISCORD_OUTPUT_DIR`
- `YOUTUBE_LEARNER_DB_PATH`
- `OPENAI_MODEL`
- `YOUTUBE_LEARNER_MAX_TRANSCRIPT_CHARS`
- `OTEL_EXPORTER_OTLP_ENDPOINT`
- `OTEL_EXPORTER_OTLP_PROTOCOL`
- `OTEL_RESOURCE_ATTRIBUTES`

## Working Rules for Agents

- Keep edits targeted and consistent with the current two-process architecture.
- Prefer extending existing modules over introducing duplicate abstractions.
- Treat the bot, queue, worker, and pipeline boundaries as intentional unless the task explicitly changes them.
- Add or update tests when behavior changes.
- Keep setup and run instructions aligned with `README.md`, `Makefile`, and `pyproject.toml`.
- Avoid changing `systemd` unit files or service scripts unless the task is specifically about deployment or operations.
- Preserve local artifact behavior unless the task requires a storage or output-format change.

## Change Expectations

- If you change user-visible behavior, update tests first or alongside the code change.
- If you change setup, commands, or environment variables, update `README.md` and any affected examples.
- If you change architectural direction, add or update an ADR in `docs/adr/`.
