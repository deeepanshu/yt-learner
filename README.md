# yt-learner

Discord-first MVP for turning YouTube URLs and watched YouTube channel uploads into structured markdown learning notes.

## Setup

1. Install `uv`.
2. Create the project environment with `uv sync`.
3. Copy `.env.example` to `.env` and fill in the required values.
4. In the Discord developer portal, enable the `MESSAGE CONTENT INTENT` for the bot if you want plain URL messages to work.
5. Invite the bot to your server.
6. Run the bot with `uv run yt-learner-discord`.
7. Run the worker with `uv run yt-learner-worker`.
8. Run the scheduler manually with `uv run yt-learner-scheduler` or install the cron entry shown below.

## Runtime Model

The app runs as two long-lived processes:

- `yt-learner-discord`: accepts Discord messages and slash commands, validates input, and enqueues jobs
- `yt-learner-worker`: claims queued jobs from SQLite, runs the extraction pipeline, and posts the result back to Discord

Channel discovery is run separately through `yt-learner-scheduler`, which is intended to be triggered by cron.

Both services should be running in normal deployment. If only the bot is running, jobs will queue but never complete. If only the worker is running, existing queued jobs will still process, but you will not be able to add or remove watches from Discord.

Access policy:

- anyone in a server where the bot is installed can use `/learn` or plain YouTube URL messages
- direct messages to the bot are ignored
- if `DISCORD_ALLOWED_CHANNEL_ID` is set, manual learning requests are limited to that one channel
- watched channel management is server-only and requires Discord `Manage Server` permission

## Environment

Required values in `.env`:

- `OPENAI_API_KEY`
- `DISCORD_BOT_TOKEN`

Optional values:

- `DISCORD_ALLOWED_USER_ID` (legacy; not required for server-wide access)
- `DISCORD_OUTPUT_DIR`
- `YOUTUBE_LEARNER_DB_PATH`
- `OPENAI_MODEL`
- `DISCORD_ALLOWED_CHANNEL_ID`
- `YOUTUBE_LEARNER_MAX_TRANSCRIPT_CHARS`
- `OTEL_EXPORTER_OTLP_ENDPOINT`
- `OTEL_EXPORTER_OTLP_PROTOCOL`
- `OTEL_RESOURCE_ATTRIBUTES`

## Watched Channels

Use Discord slash commands to manage watched YouTube channels:

- `/watch add <youtube_channel> <discord_channel>`
- `/watch list`
- `/watch remove <youtube_channel_or_watch_id>`

Behavior:

- the first sync for a newly watched YouTube channel is bootstrap-only and does not backfill existing uploads
- later uploads are discovered from the YouTube channel feed and enqueued once
- discovered video ids are stored in SQLite, so restarts do not re-enqueue the same upload
- each watched YouTube channel has its own Discord destination, and multiple watched channels may share the same destination

Managed scheduler cron entry:

```cron
CRON_TZ=Asia/Bangkok 0 8 * * * cd /home/deepanshu/projects/yt-learner && /home/deepanshu/.local/bin/uv run yt-learner-scheduler
```

`make service-install` and the other top-level `make service-*` commands manage this cron entry for you. By default it runs discovery once per day at 8:00 AM Bangkok time and writes output to `data/yt-learner-scheduler.log`. The scheduler only enqueues jobs; `yt-learner-worker` still needs to be running to process them.

Supported watch inputs:

- `https://www.youtube.com/channel/<channel_id>`
- `@handle`
- raw YouTube channel ids that start with `UC`

## Observability

`yt-learner` can export metrics and logs to any OpenTelemetry-compatible collector. If you want Loki, the recommended shape is:

- `yt-learner-discord` and `yt-learner-worker` emit OTLP metrics and OTLP logs
- an OpenTelemetry Collector or Grafana Alloy receives those signals
- the collector forwards logs to Loki and metrics to the backend you prefer

Recommended entries in `/home/deepanshu/.env`:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=http://localhost:4318/v1/logs
OTEL_RESOURCE_ATTRIBUTES=deployment.environment=prod
```

Service names are set automatically:

- `yt-learner-discord`
- `yt-learner-worker`

Metric names:

- `yt_learner_discord_jobs_enqueued_total`
- `yt_learner_worker_jobs_processed_total`
- `yt_learner_worker_job_processing_duration_seconds`

The bot exports job enqueue counts. The worker exports job completion/failure counts and processing duration.

Logging behavior:

- when `OTEL_EXPORTER_OTLP_ENDPOINT` is set, both services continue writing normal process logs and also export them over OTLP
- `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` is optional and only needed when your collector exposes logs on a different URL than the shared OTLP endpoint
- OpenTelemetry resource attributes such as `deployment.environment=prod` are attached to both logs and metrics, which makes them usable as Loki labels after collector-side mapping

The application intentionally does not talk to Loki directly. OTLP keeps the app backend-agnostic and lets the collector handle Loki-specific routing, relabeling, and buffering.

## Development

- Run tests with `uv run pytest`.
- Add dependencies with `uv add <package>`.
- Add dev dependencies with `uv add --dev <package>`.
- Run both bot and worker locally with `make run-all`.
- Run the bot locally with `make run-bot`.
- Run the worker locally with `make run-worker`.
- Run one scheduler pass locally with `make run-scheduler`.

## Service Management

The repo includes a wrapper script for the bot, worker, and scheduler:

- `make service-install` installs and restarts both services and installs the scheduler cron entry
- `make service-restart` restarts both services and refreshes the scheduler cron entry
- `make service-status` shows status for both services and the scheduler cron entry
- `make service-logs` shows recent logs for both services and the scheduler log file
- `make service-stop` stops both services and removes the scheduler cron entry

You can also target one service at a time:

- `make service-restart-bot`
- `make service-status-bot`
- `make service-logs-bot`
- `make service-restart-worker`
- `make service-status-worker`
- `make service-logs-worker`
- `make service-stop-worker`
- `make service-install-scheduler`
- `make service-restart-scheduler`
- `make service-status-scheduler`
- `make service-logs-scheduler`
- `make service-stop-scheduler`

## Deployment

- The included `yt-learner-discord.service` and `yt-learner-worker.service` units assume the project lives at `/home/pi/yt-learner`.
- Update `WorkingDirectory` or the `uv` path in that unit if your Raspberry Pi uses a different layout.
- The repo includes `scripts/service.sh` as a thin wrapper around the `systemd` commands for both services.
- Watched-channel polling is managed by `scripts/service.sh`, which installs a user crontab entry for the scheduler.

## Current Scope

- Manual YouTube URL processing through Discord messages or `/learn`
- Watched YouTube channel scheduling through `/watch`
- SQLite-backed durable job queue in `app.job_queue`
- SQLite-backed watch and discovered-video persistence
- Separate worker execution in `app.worker`
- Shared processing pipeline in `app.pipeline`
- Local markdown output in `outputs/`

## Notes

- Existing markdown files are reused by video ID.
- If transcript fetch succeeds but OpenAI extraction fails, the transcript is saved locally as a debug artifact.
- Discord replies immediately with a queued job ID for manual requests; the worker posts the completion or failure message later.
- Channel watches use public YouTube feeds in v1 and do not require a YouTube Data API key.
