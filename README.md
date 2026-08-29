# yt-learner

Discord-first MVP for turning YouTube URLs and watched YouTube channel uploads into structured markdown learning notes.

## Setup

1. Install `uv`.
2. Create the project environment with `uv sync`.
3. Copy `.env.example` to `.env` and fill in the required values.
4. In the Discord developer portal, enable the `MESSAGE CONTENT INTENT` for the bot if you want plain URL messages to work.
5. Invite the bot to your server.
6. Run migrations with `uv run yt-learner-migrate`.
7. Run the bot with `uv run yt-learner-discord`.
8. Run the worker with `uv run yt-learner-worker`.
9. Run the scheduler manually with `uv run yt-learner-scheduler` when you want a one-off poll during development.

Local tests need Postgres:

```bash
make test-db
make test
```

## Docker Deployment

Docker Compose is the default deployment path.

The deployed runtime keeps the current process split:

- `discord`: accepts Discord messages and slash commands, validates input, and enqueues jobs
- `worker`: claims queued jobs from Postgres, runs the extraction pipeline, and posts results back to Discord
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

The app still has two long-lived app processes and one scheduled process:

- `yt-learner-discord`: accepts Discord messages and slash commands, validates input, and enqueues jobs
- `yt-learner-worker`: claims queued jobs from Postgres, runs the extraction pipeline, and posts the result back to Discord
- `yt-learner-scheduler`: runs channel discovery on a daily wall-clock schedule and enqueues new work

In normal deployment all three containers should be running. If only the bot is running, jobs will queue but never complete. If only the worker is running, existing queued jobs will still process, but you will not be able to add or remove watches from Discord. If the scheduler is not running, watched channels will stop enqueueing new uploads.

Access policy:

- anyone in a server where the bot is installed can use `/learn` or plain YouTube URL messages
- direct messages to the bot are ignored
- if `DISCORD_ALLOWED_CHANNEL_ID` is set, manual learning requests are limited to that one channel
- watched channel management is server-only and requires Discord `Manage Server` permission

## Environment

Required values in `.env`:

- `OPENAI_API_KEY`
- `DISCORD_BOT_TOKEN`
- `DATABASE_URL`

Optional values:

- `DISCORD_ALLOWED_USER_ID` (legacy; not required for server-wide access)
- `OPENAI_MODEL`
- `DISCORD_ALLOWED_CHANNEL_ID`
- `YOUTUBE_LEARNER_MAX_TRANSCRIPT_CHARS`
- `OTEL_EXPORTER_OTLP_ENDPOINT`
- `OTEL_EXPORTER_OTLP_PROTOCOL`
- `OTEL_RESOURCE_ATTRIBUTES`
- `YT_LEARNER_SCHEDULER_TIMEZONE`
- `YT_LEARNER_SCHEDULER_HOUR`
- `YT_LEARNER_SCHEDULER_MINUTE`

Compose pins OTEL to `http://otel-collector:4318`. Do not use `localhost` from inside the app containers.

## MCP Server

`yt-learner` exposes one read-only tool, `get_youtube_transcript`, which returns English YouTube transcripts. It accepts watch, shorts, embed, and `youtu.be` URLs, or an 11-character video ID. Results contain the canonical URL, video ID, plain text, and timestamped segments.

### Local stdio

Use this only with local MCP hosts such as Claude Code or Cursor:

```bash
make run-mcp
```

### ChatGPT: Cloudflare Access-protected HTTP

ChatGPT needs a public HTTPS Streamable HTTP endpoint. The `mcp` Compose service listens only on the Pi loopback interface; Cloudflare Tunnel is the only public ingress.

Set these values in the production `.env`:

```text
MCP_PUBLIC_URL=https://ytlearner.deepanshujain.me/yt/api/mcp
MCP_ACCESS_ISSUER_URL=<the exact iss claim from Cloudflare Access tokens>
MCP_ACCESS_JWKS_URL=<the Access application JWKS endpoint>
MCP_ACCESS_AUDIENCE=<the Access application AUD tag>
MCP_PATH=/yt/api/mcp
# Optional. Required OAuth scopes, space-separated.
MCP_ACCESS_REQUIRED_SCOPES=
MCP_BIND_HOST=127.0.0.1
MCP_HOST_PORT=3002
```

Deploy the Compose stack, then configure Cloudflare:

1. Route `ytlearner.deepanshujain.me` through Cloudflare Tunnel to `http://127.0.0.1:3002`.
2. Create an Access MCP application for `https://ytlearner.deepanshujain.me/yt/api/mcp`.
3. Enable managed OAuth and restrict its Access policy to your identity.
4. Set the exact issuer, JWKS URL, and application AUD tag Cloudflare gives that application in `.env`.
5. In ChatGPT developer mode, add `https://ytlearner.deepanshujain.me/yt/api/mcp` as the custom MCP endpoint and complete the Access OAuth flow.

The HTTP server validates every bearer token's RS256 signature, issuer, audience, and expiry before it dispatches a tool. The MCP SDK serves protected-resource metadata under `/.well-known/oauth-protected-resource/`; the app also respects `MCP_PATH` (default `/mcp`, set to `/yt/api/mcp` here). Do not replace Access managed OAuth with a generic browser-login rule.

The same endpoint works with any remote MCP host that supports Streamable HTTP and OAuth discovery. ChatGPT custom MCP apps require a supported plan and developer mode.

English transcripts only, same constraint as the Discord worker. Videos without captions, private/unavailable videos, or YouTube-blocked requests return a tool error.

## Watched Channels

Use Discord slash commands to manage watched YouTube channels:

- `/watch add <youtube_channel> <discord_channel>`
- `/watch list`
- `/watch remove <youtube_channel_or_watch_id>`

Behavior:

- the first sync for a newly watched YouTube channel is bootstrap-only and does not backfill existing uploads
- later uploads are discovered from the YouTube channel feed and enqueued once
- discovered video ids are stored in Postgres, so restarts do not re-enqueue the same upload
- each watched YouTube channel has its own Discord destination, and multiple watched channels may share the same destination

The scheduler container runs discovery once per day at `8:00 AM` Bangkok time. It only enqueues jobs; `yt-learner-worker` still needs to be running to process them.

Supported watch inputs:

- `https://www.youtube.com/channel/<channel_id>`
- `@handle`
- raw YouTube channel ids that start with `UC`

## Observability

`yt-learner` exports metrics and logs over OTLP. The collector forwards logs to Loki and metrics to Prometheus.

Service names:

- `yt-learner-discord`
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
- Run both bot and worker locally with `make run-all`.
- Apply migrations with `uv run yt-learner-migrate`.
- Build the Docker image with `make docker-build`.
- Start the Docker deployment with `make docker-up`.

## Current Scope

- Manual YouTube URL processing through Discord messages or `/learn`
- Watched YouTube channel scheduling through `/watch`
- Postgres-backed durable job queue in `app.job_queue`
- Postgres-backed watch, source, and note persistence
- MCP transcript service: local stdio plus Cloudflare Access-protected Streamable HTTP for ChatGPT
- Notes stored as `learning_records.markdown` and sent to Discord as attachments

## Notes

- Existing notes are reused by video ID.
- If transcript fetch succeeds but OpenAI extraction fails, the transcript is stored in `debug_artifacts`.
- Discord replies immediately with a queued job ID for manual requests; the worker posts the completion or failure message later.
- Channel watches use public YouTube feeds in v1 and do not require a YouTube Data API key.
