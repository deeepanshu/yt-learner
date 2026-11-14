# AGENTS.md

## Purpose

This file is the working guide for coding agents making changes in this repository. It summarizes the project shape, the main commands, and the constraints that matter when editing code here.

## Project Overview

`yt-learner` turns watched YouTube channel uploads into structured markdown learning notes in Trilium.

The runtime is split into two long-lived processes and one scheduled process:

- `yt-learner-web` serves the Tailscale/LAN watch-management UI.
- `yt-learner-worker` claims queued jobs from Postgres, runs the extraction pipeline, and publishes notes to Trilium.
- `yt-learner-scheduler` polls watched YouTube channels on a wall-clock schedule.

Normal behavior depends on web, worker, and scheduler running. If only the watch UI is running, watches can change but jobs will not complete.

## Repo Map

- `app/` contains the application code.
- `app/web.py` is the watch-management UI.
- `app/worker.py` is the worker entrypoint.
- `app/job_queue.py` contains the Postgres-backed queue.
- `app/db.py` and `app/migrations/` contain connection helpers and SQL migrations.
- `app/pipeline.py` contains the shared processing pipeline.
- `app/storage.py` stores sources, notes, and debug transcripts in Postgres.
- `app/trilium.py` publishes notes to TriliumNext ETAPI.
- `app/mcp_server.py` is the local stdio MCP server for YouTube transcripts.
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

Run the watch UI locally:

```bash
make run-web
```

Run the worker locally:

```bash
make run-worker
```

Run one scheduler pass locally:

```bash
make run-scheduler
```

Run the local transcript MCP server:

```bash
make run-mcp
```

Run the public HTTP MCP service:

```bash
make run-mcp-http
```

The deployed `mcp` Compose service is a public Streamable HTTP transcript endpoint. Keep its port loopback-bound and route only through Cloudflare Tunnel. Add a Cloudflare WAF rate-limit rule before exposing it; ChatGPT needs no authentication.

Apply migrations:

```bash
uv run yt-learner-migrate
```

Run watch UI and worker locally:

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

- `OLLAMA_API_KEY`
- `OLLAMA_MODEL`
- `DATABASE_URL`
- `TRILIUM_ETAPI_URL`
- `TRILIUM_ETAPI_TOKEN`
- `TRILIUM_PARENT_NOTE_ID`

Common optional values:

- `TRILIUM_UI_URL`
- `WATCH_UI_HOST`
- `WATCH_UI_PORT`
- `OLLAMA_BASE_URL`
- `YOUTUBE_LEARNER_MAX_TRANSCRIPT_CHARS`
- `OTEL_EXPORTER_OTLP_ENDPOINT`
- `OTEL_EXPORTER_OTLP_PROTOCOL`
- `OTEL_RESOURCE_ATTRIBUTES`

## Working Rules for Agents

- Keep edits targeted and consistent with the current two-process architecture plus scheduler.
- Keep the Cloudflare Tunnel as the only remote ingress. The public transcript MCP must remain read-only, have no Family OS or Supabase identity dependency, and be protected by a Cloudflare WAF rate-limit rule. Do not expose the watch UI through Cloudflare.
- Prefer extending existing modules over introducing duplicate abstractions.
- Treat the web UI, queue, worker, and pipeline boundaries as intentional unless the task explicitly changes them.
- Postgres is the only application database. Do not reintroduce SQLite.
- Notes live in `learning_records.markdown` and are published to Trilium. Do not write note files to disk.
- Add or update tests when behavior changes. Tests require Postgres (`make test`).
- Keep setup and run instructions aligned with `README.md`, `Makefile`, and `pyproject.toml`.

## Change Expectations

- If you change user-visible behavior, update tests first or alongside the code change.
- If you change setup, commands, or environment variables, update `README.md` and any affected examples.
- If you change architectural direction, add or update an ADR in `docs/adr/`.
