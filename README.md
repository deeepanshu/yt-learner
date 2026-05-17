# yt-learner

Discord-first MVP for turning a YouTube URL into structured markdown learning notes.

## Setup

1. Install `uv`.
2. Create the project environment with `uv sync`.
3. Copy `.env.example` to `.env` and fill in the required values.
4. In the Discord developer portal, enable the `MESSAGE CONTENT INTENT` for the bot if you want plain URL messages to work.
5. Invite the bot to your server or use it in DMs.
6. Run the bot with `uv run yt-learner-discord`.
7. Run the worker with `uv run yt-learner-worker`.

## Environment

Required values in `.env`:

- `OPENAI_API_KEY`
- `DISCORD_BOT_TOKEN`
- `DISCORD_ALLOWED_USER_ID`

Optional values:

- `DISCORD_OUTPUT_DIR`
- `YOUTUBE_LEARNER_DB_PATH`
- `OPENAI_MODEL`
- `DISCORD_ALLOWED_CHANNEL_ID`
- `YOUTUBE_LEARNER_MAX_TRANSCRIPT_CHARS`

## Development

- Run tests with `uv run pytest`.
- Add dependencies with `uv add <package>`.
- Add dev dependencies with `uv add --dev <package>`.
- Use `make service-install`, `make service-restart`, `make service-status`, and `make service-logs` to manage the bot service.
- The worker is a separate long-running process; deploy both services for normal operation.

## Deployment

- The included [yt-learner-discord.service](/home/deepanshu/projects/yt-learner/yt-learner-discord.service:1) and [yt-learner-worker.service](/home/deepanshu/projects/yt-learner/yt-learner-worker.service:1) units assume the project lives at `/home/pi/yt-learner`.
- Update `WorkingDirectory` or the `uv` path in that unit if your Raspberry Pi uses a different layout.
- The repo includes [scripts/service.sh](/home/deepanshu/projects/yt-learner/scripts/service.sh:1) as a thin wrapper around the `systemd` commands.

## Current Scope

- Manual YouTube URL processing through Discord messages or `/learn`.
- SQLite-backed durable job queue in `app.job_queue`.
- Separate worker execution in `app.worker`.
- Shared processing pipeline in `app.pipeline`.
- Local markdown output in `outputs/`.

## Notes

- Existing markdown files are reused by video ID.
- If transcript fetch succeeds but OpenAI extraction fails, the transcript is saved locally as a debug artifact.
- Discord now replies immediately with a queued job ID; the worker posts the completion or failure message later.
- Channel watching is not implemented yet.
