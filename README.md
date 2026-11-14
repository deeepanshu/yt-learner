# yt-learner

Turns watched YouTube channel uploads into structured markdown learning notes in Trilium.

## Setup

1. Install `uv`.
2. Create the project environment with `uv sync`.
3. Copy `.env.example` to `.env` and fill in the required values.
4. Run migrations with `uv run yt-learner-migrate`.
5. Run the watch UI with `uv run yt-learner-web`.
6. Run the worker with `uv run yt-learner-worker`.
7. Run the scheduler manually with `uv run yt-learner-scheduler` when you want a one-off poll during development.

Local tests need Postgres:

```bash
make test-db
make test
```

## Docker Deployment

Docker Compose is the default deployment path.

The deployed runtime keeps the current process split:

- `web`: Tailscale/LAN UI for adding and removing YouTube channel watches. Do not put this on Cloudflare Tunnel.
- `worker`: claims queued jobs from Postgres, runs the extraction pipeline, and publishes notes to Trilium
- `scheduler`: waits until `8:00 AM` in `Asia/Bangkok`, runs one watched-channel poll, enqueues new jobs, and waits for the next day
- `migrate`: one-shot schema apply (`docker compose --profile migrate run --rm migrate`)

Services join the external `homelab` and `observability` networks. Postgres is `homelab-postgres`. Notes live in Postgres, not on a bind mount.

Standard Docker flow:

```bash
make docker-build
make docker-up
make docker-logs
```

If you want Compose to load a different env file, set `YT_LEARNER_ENV_FILE`, for example `YT_LEARNER_ENV_FILE=.env.prod make docker-up`.

Manual one-off scheduler run inside the containerized deployment:

```bash
make docker-run-scheduler
```

Useful operational commands:

- `make docker-down`
- `make docker-restart`
- `make docker-ps`

### Pi cutover from SQLite

On an existing homelab Postgres volume, init scripts will not run again. Create the database once:

```sh
POSTGRES_SUPERUSER_PASSWORD=… ./scripts/create-app-db.sh yt_learner
```

Save the printed `DATABASE_URL` into `~/projects/yt-learner/.env`, then import the old SQLite file if you still have it:

```sh
uv run python scripts/import-sqlite.py ./data/yt_learner.sqlite3
```

Also set `RPI_DEPLOY_SECRET` on `deeepanshu/yt-learner` to match the Pi manager.

## Runtime Model

The app has two long-lived app processes and one scheduled process:

- `yt-learner-web`: watch-management UI
- `yt-learner-worker`: claims queued jobs from Postgres, runs the extraction pipeline, and publishes the note to Trilium
- `yt-learner-scheduler`: runs channel discovery on a daily wall-clock schedule and enqueues new work

In normal deployment all three containers should be running. If only the watch UI is running, watches can change but jobs will never complete. If only the worker is running, existing queued jobs will still process, but you will not be able to add or remove watches. If the scheduler is not running, watched channels will stop enqueueing new uploads.

The watch UI is served at `/ui` on port `3004`. Public hostname is `https://ytlearner.deepanshujain.me/ui` via Cloudflare Tunnel; put Cloudflare Access on `/ui*` before using it from the internet.

## Environment

Required values in `.env`:

- `OLLAMA_API_KEY`
- `OLLAMA_MODEL`
- `DATABASE_URL`
- `TRILIUM_ETAPI_URL`
- `TRILIUM_ETAPI_TOKEN`
- `TRILIUM_PARENT_NOTE_ID`

Optional values:

- `TRILIUM_UI_URL`
- `WATCH_UI_HOST`
- `WATCH_UI_PORT`
- `WATCH_UI_BIND_HOST`
- `WATCH_UI_HOST_PORT`
- `OLLAMA_BASE_URL`
- `YOUTUBE_LEARNER_MAX_TRANSCRIPT_CHARS`
- `OTEL_EXPORTER_OTLP_ENDPOINT`
- `OTEL_EXPORTER_OTLP_PROTOCOL`
- `OTEL_RESOURCE_ATTRIBUTES`
- `YT_LEARNER_SCHEDULER_TIMEZONE`
- `YT_LEARNER_SCHEDULER_HOUR`
- `YT_LEARNER_SCHEDULER_MINUTE`

Compose pins OTEL to `http://otel.lab:4318` (Pi-hole record → observability CT). Do not use `localhost` from inside the app containers.

## MCP Server

`yt-learner` exposes one read-only tool, `get_youtube_transcript`, which returns English YouTube transcripts. It accepts watch, shorts, embed, and `youtu.be` URLs, or an 11-character video ID. Results contain the canonical URL, video ID, plain text, and timestamped segments.

### Local stdio

Use this only with local MCP hosts such as Claude Code or Cursor:

```bash
make run-mcp
```

### ChatGPT: public Streamable HTTP

ChatGPT connects directly to the public read-only MCP endpoint:

```text
https://ytlearner.deepanshujain.me/yt/api/mcp
```

No OAuth, Supabase account, or Family OS identity is involved. The `mcp` Compose service remains loopback-bound on the Pi; Cloudflare Tunnel is the only public ingress.

Set these values in the production `.env`:

```text
MCP_PATH=/yt/api/mcp
MCP_PORT=3003
MCP_BIND_HOST=127.0.0.1
MCP_HOST_PORT=3003
```

Before exposing the endpoint, add a Cloudflare WAF rate-limit rule for:

```text
Path:     /yt/api/mcp (starts with)
Limit:    10 requests per 10 seconds per client IP
Action:   Block for 10 seconds
```

The zone is on the Cloudflare Free plan, which restricts rate-limit rules to a path-only expression (no hostname), a fixed 10-second counting period, and a 10-second mitigation timeout. The rule is zone-scoped, so the path match only applies to this zone's traffic. This prevents the public transcript endpoint becoming an abuseable YouTube proxy. The app itself does not handle user data or authentication.

### YouTube egress

YouTube can block the Pi's public IP. Configure a [Webshare Rotating Residential](https://www.webshare.io/) proxy to route only transcript requests through a rotating residential pool:

```text
YT_LEARNER_WEBSHARE_PROXY_USERNAME=<Webshare Proxy Username>
YT_LEARNER_WEBSHARE_PROXY_PASSWORD=<Webshare Proxy Password>
```

Buy Webshare's **Rotating Residential** product, not Proxy Server or Static Residential. Leave both values blank to use direct Pi egress. The app rejects partial credentials at request time rather than silently using direct egress.

In ChatGPT developer mode, add the URL above as a custom MCP endpoint and select **No authentication**.

The same endpoint works with any remote MCP host that supports Streamable HTTP without authentication.

English transcripts only, same constraint as the worker. Videos without captions, private/unavailable videos, or YouTube-blocked requests return a tool error.

## Watched Channels

Open `https://ytlearner.deepanshujain.me/ui` (Cloudflare Access) or `http://<host>:3004/ui` on Tailscale/LAN.

Behavior:

- the first sync for a newly watched YouTube channel is bootstrap-only and does not backfill existing uploads
- later uploads are discovered from the YouTube channel feed and enqueued once
- discovered video ids are stored in Postgres, so restarts do not re-enqueue the same upload
- notes always go to Trilium under `TRILIUM_PARENT_NOTE_ID`

The scheduler container runs discovery once per day at `8:00 AM` Bangkok time. It only enqueues jobs; `yt-learner-worker` still needs to be running to process them.

Supported watch inputs:

- `https://www.youtube.com/channel/<channel_id>`
- `@handle`
- raw YouTube channel ids that start with `UC`

## Observability

`yt-learner` exports metrics and logs over OTLP. The collector forwards logs to Loki and metrics to Prometheus.

Service names:

- `yt-learner-web`
- `yt-learner-scheduler`
- `yt-learner-worker`

Metric names (Prometheus adds the collector `app_` prefix):

- `yt_learner_discord_jobs_enqueued_total`
- `yt_learner_worker_jobs_processed_total`
- `yt_learner_worker_job_processing_duration_seconds`
- `yt_learner_scheduler_runs_total`
- `yt_learner_scheduler_run_duration_seconds`
- `yt_learner_scheduler_videos_seen_total`
- `yt_learner_scheduler_jobs_enqueued_total`

The dashboard `grafana/dashboards/yt-learner.json` is copied into Grafana on deploy.

## Development

- Run tests with `make test`.
- Add dependencies with `uv add <package>`.
- Add dev dependencies with `uv add --dev <package>`.
- Validate config locally with `make check`.
- Run the local transcript MCP server with `make run-mcp`.
- Run watch UI and worker locally with `make run-all`.
- Apply migrations with `uv run yt-learner-migrate`.
- Build the Docker image with `make docker-build`.
- Start the Docker deployment with `make docker-up`.

## Current Scope

- Watched YouTube channel scheduling through the watch UI
- Postgres-backed durable job queue in `app.job_queue`
- Postgres-backed watch, source, and note persistence
- MCP transcript service: local stdio plus Cloudflare Access-protected Streamable HTTP for ChatGPT
- Notes stored as `learning_records.markdown` and published to Trilium via ETAPI

## Notes

- Existing notes are reused by video ID.
- If transcript fetch succeeds but Ollama extraction fails, the transcript is stored in `debug_artifacts`.
- Channel watches use public YouTube feeds in v1 and do not require a YouTube Data API key.
- Create an ETAPI token in Trilium (Options → ETAPI) and a parent notebook, then set `TRILIUM_ETAPI_TOKEN` and `TRILIUM_PARENT_NOTE_ID`. Use the LAN URL `http://trilium.lab:8080/etapi`, not the public site.
