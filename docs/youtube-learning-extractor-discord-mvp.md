# YouTube Learning Extractor Discord MVP

**Date:** 2026-05-17
**Status:** Draft implementation design

---

## TL;DR

Build the first version of the YouTube Learning Extractor as a Discord bot instead of Telegram or WhatsApp. The MVP supports two invocation paths:

1. Paste a plain YouTube URL into a Discord DM or private channel.
2. Use `/learn url:<youtube-url>` for an explicit command.

Both paths call the same shared extraction pipeline: parse video ID, fetch transcript, ask OpenAI for structured learning notes, save a markdown file locally, and return the markdown as a Discord attachment.

Channel watching, `/watch add`, `/watch list`, and `/latest` are intentionally deferred until the manual URL workflow is reliable.

---

## Why Discord

WhatsApp is inconvenient for this use case because the official Cloud API requires a WhatsApp Business/API setup, a registered API phone number, public webhook handling, and template rules for proactive messages. Using a personal WhatsApp number through unofficial automation would be brittle and risky.

Discord is simpler:

- No business phone number.
- No approved message templates.
- No 24-hour messaging window.
- No public HTTPS webhook required.
- The Raspberry Pi can run a persistent bot process.
- Later, the bot can proactively post channel-watcher results into a private Discord channel.

Daily user experience stays simple: send a YouTube URL from the phone and receive a learning note back.

---

## MVP Scope

### In Scope

- Discord bot process running on Raspberry Pi.
- Plain YouTube URL detection in allowed Discord locations.
- `/learn url:<youtube-url>` slash command.
- Whitelist by Discord user ID.
- Transcript fetch using `youtube-transcript-api`.
- OpenAI structured extraction.
- Markdown output saved locally.
- Markdown file returned as a Discord attachment.
- Basic error replies for invalid URL, missing transcript, private video, and OpenAI failure.
- `systemd` service for always-on execution.

### Out of Scope

- Channel watcher.
- `/watch add`.
- `/watch list`.
- `/latest`.
- Multi-user support.
- Rich Discord UI buttons.
- Web dashboard.
- Full job queue.
- Cloud deployment.

---

## Invocation Model

### 1. Plain YouTube URL

User sends:

```text
https://youtube.com/watch?v=abc123
```

Bot behavior:

1. Check sender is allowed.
2. Detect YouTube URL in the message.
3. Reply with a short processing message.
4. Process the video.
5. Upload the markdown output as an attachment.

Expected UX:

```text
DJ:
https://youtube.com/watch?v=abc123

Bot:
Processing: <video title>

Bot:
Done: <video title>
Attachment: <video-title>.md
```

### 2. Slash Command

User sends:

```text
/learn url:https://youtube.com/watch?v=abc123
```

Bot behavior is the same as the plain URL path. The slash command is useful when the bot should only act on explicit requests or when a server channel contains other YouTube links that should be ignored.

---

## Architecture

```text
Discord DM/private channel
        |
        v
discord_bot.py
  - plain URL listener
  - /learn slash command
  - allowed user check
        |
        v
job_queue.py
  - create SQLite job
  - return job ID quickly
        |
        v
worker.py
  - claim queued job
  - retry failed job when appropriate
        |
        v
pipeline.py
  - parse video ID
  - dedupe/reuse existing output if present
  - fetch transcript
  - run extraction
  - save markdown
        |
        +--> youtube_urls.py
        +--> transcript.py
        +--> extractor.py
        +--> storage.py
        |
        v
Discord response
  - queued/processing/done status text
  - markdown attachment
```

The important design rule: both invocation paths create the same `summarize_video` job. The worker calls the same `process_video(...)` function. Discord-specific behavior should stay in the Discord adapter, queue mechanics should stay in the job layer, and learning extraction should stay in the pipeline.

The queue should exist from the first implementation, but it should stay simple: one SQLite database and one local worker process. Avoid Redis, Celery, or distributed workers until the tool actually needs concurrency across machines.

---

## Proposed File Structure

```text
yt-learner/
  app/
    discord_bot.py          # Discord bot, URL listener, /learn command
    worker.py               # Single local worker that claims queued jobs
    job_queue.py            # SQLite-backed persistent queue
    pipeline.py             # Shared process_video(video_url, requested_by)
    youtube_urls.py         # URL parsing and video ID extraction
    transcript.py           # youtube-transcript-api wrapper
    extractor.py            # OpenAI prompt and structured JSON generation
    renderer.py             # Convert structured extraction result to markdown
    storage.py              # Output paths, dedupe checks, metadata, SQLite path
    config.py               # Env/config loading
  outputs/
    .gitkeep
  data/
    .gitkeep
  yt-learner-discord.service
  yt-learner-worker.service
  .env.example
  README.md
  requirements.txt
```

SQLite should be used from the first version as a persistent job queue. It keeps Discord responses fast, gives crash recovery, and creates a clean path for future ad hoc task types and channel watching.

---

## Environment Variables

```env
OPENAI_API_KEY=
DISCORD_BOT_TOKEN=
DISCORD_ALLOWED_USER_ID=
DISCORD_OUTPUT_DIR=/home/pi/yt-learner/outputs
YOUTUBE_LEARNER_DB_PATH=/home/pi/yt-learner/data/yt_learner.sqlite3
OPENAI_MODEL=gpt-4o-mini
```

Optional later:

```env
DISCORD_ALLOWED_CHANNEL_ID=
YOUTUBE_LEARNER_MAX_TRANSCRIPT_CHARS=
```

---

## Processing Contract

Discord should not run video extraction inline. It should create a job and reply quickly.

Job creation contract:

```python
async def enqueue_summarize_video(
    video_url: str,
    requested_by: str,
    source: str,
) -> Job:
    ...
```

Worker contract:

```python
async def run_next_job() -> JobResult | None:
    ...
```

Pipeline contract:

```python
async def process_video(video_url: str, requested_by: str) -> ProcessedVideo:
    ...
```

Suggested result shape:

```python
@dataclass
class ProcessedVideo:
    video_id: str
    title: str
    url: str
    extraction_json_path: Path
    output_path: Path
    reused_existing: bool
```

The Discord adapter should only care about:

- what status message to send,
- the queued job ID,
- whether processing succeeded or failed,
- which file to attach when the worker finishes.

---

## Queue Model

Use a small SQLite table as the durable queue:

```text
jobs
- id
- task_type
- source
- requested_by
- input_json
- status
- priority
- attempts
- created_at
- started_at
- finished_at
- result_path
- error
```

Initial statuses:

```text
queued
running
done
failed
cancelled
```

Initial task type:

```text
summarize_video
```

Likely future task types:

```text
extract_action_items
make_flashcards
explain_concepts
summarize_channel_video
compare_two_videos
```

Initial execution model:

```text
Discord command/message
  -> validate user
  -> parse YouTube URL enough to reject obvious invalid input
  -> insert queued job
  -> reply "Queued"

Worker loop
  -> claim oldest queued job
  -> run task handler
  -> save structured JSON and rendered markdown
  -> update job as done/failed
  -> send Discord completion message with attachment
```

This is intentionally not a large queue system. SQLite is enough for one Raspberry Pi, one user, and jobs that can take minutes.

---

## Summarization Contract

Do not ask the model to directly write final markdown as the only source of truth. Ask it to return structured JSON first, then render markdown locally. This keeps outputs consistent and makes it easier to add future ad hoc task types.

Suggested extraction JSON shape:

```json
{
  "title": "Video title",
  "source_url": "https://youtube.com/watch?v=...",
  "channel": "Channel name",
  "duration_seconds": 3600,
  "tldr": [
    "Main idea 1",
    "Main idea 2"
  ],
  "why_it_matters": "Short explanation of why this video is useful.",
  "topics": [
    {
      "start_seconds": 0,
      "title": "Topic name",
      "summary": "What this section explains.",
      "key_points": [
        "Important detail",
        "Practical takeaway"
      ]
    }
  ],
  "key_concepts": [
    {
      "term": "Concept",
      "explanation": "Short explanation."
    }
  ],
  "actionable_takeaways": [
    "Something to try",
    "Decision or heuristic worth remembering"
  ],
  "questions_to_revisit": [
    "Question worth thinking about later"
  ],
  "glossary": [
    {
      "term": "Term",
      "definition": "Short definition."
    }
  ]
}
```

For long videos, use a two-pass process:

```text
transcript
  -> chunk by timestamp
  -> summarize each chunk into structured JSON
  -> merge chunk summaries into final structured JSON
  -> render markdown
```

The merge step should preserve timestamp anchors so the final markdown can link back to the exact video positions.

---

## Output Format

Save markdown as:

```text
outputs/YYYY-MM-DD__video-title__video-id.md
```

Markdown structure:

```markdown
# <Video Title>

Source: <YouTube URL>
Channel: <Channel Name>
Duration: <Duration>
Processed: <timestamp>

## TL;DR

- Main idea
- Main idea

## Why It Matters

Short explanation of why this video is useful.

## Topic Map

### 00:00 - <Topic> ([link](https://youtube.com/watch?v=...&t=0s))

- Key point
- Practical takeaway

## Key Concepts

- Concept: explanation

## Actionable Notes

- Thing to try
- Tool, method, decision, or heuristic worth remembering

## Good Questions To Revisit

- Question

## Glossary

- Term: definition
```

Timestamp links should point back to the video position.

---

## Security

Minimum security for MVP:

- Only process requests from `DISCORD_ALLOWED_USER_ID`.
- Ignore all other users silently or reply with a short unauthorized message.
- Do not log OpenAI API keys or Discord tokens.
- Keep `.env` out of Git.

For a private single-user bot, this is enough to avoid random Discord users spending OpenAI credits.

---

## Error UX

Use short Discord replies:

```text
I could not find a YouTube URL in that message.
```

```text
I could not fetch an English transcript for this video.
```

```text
The video looks private, unavailable, or unsupported.
```

```text
The extraction failed while calling OpenAI. The transcript was not lost; try again later.
```

If the transcript fetch succeeds but OpenAI fails, save the raw transcript or partial metadata for debugging.

---

## Missing Decisions

The core shape is clear, but these decisions should be made before or during the first implementation slice:

- **Discord surface:** Use DMs only, one private server channel only, or both. DMs are simplest for personal use; a private channel gives better history and future channel-watcher output.
- **Message permissions:** Decide whether plain URL detection is allowed everywhere the bot can see messages, or only in DMs / `DISCORD_ALLOWED_CHANNEL_ID`.
- **Initial model:** Start with `gpt-4o-mini` for cost, but keep `OPENAI_MODEL` configurable.
- **Long-video threshold:** Decide when to switch from single-pass extraction to chunked two-pass extraction. A practical first threshold is transcript character count.
- **Metadata source:** Decide whether the MVP needs title/channel/duration from YouTube metadata or whether transcript-only plus video URL is acceptable for the first slice.
- **Duplicate behavior:** Decide whether an already-processed video should resend the existing markdown immediately or create a fresh job.
- **Queue status UX:** Decide whether Discord should only say `Queued` and `Done`, or support `status <job-id>` later.
- **Retry policy:** Decide how many attempts a failed job gets and which errors are retryable.
- **Cost guardrails:** Add a maximum transcript size or estimated token budget before calling OpenAI.
- **Retention:** Decide how long to keep markdown outputs, structured JSON, raw transcripts, and failed-job debug files.
- **Secrets setup:** Decide how `.env` is installed on the Raspberry Pi and how service logs avoid printing secrets.
- **Observability:** Decide the minimum logs needed for debugging: job ID, video ID, status transition, duration, and error class.
- **Local CLI fallback:** Decide whether to include a small CLI like `python -m app.cli summarize <url>` for debugging without Discord.

None of these block the design. The most important ones for the MVP are Discord surface, long-video threshold, duplicate behavior, retry policy, and cost guardrails.

---

## Implementation Plan

1. Create `yt-learner` project skeleton.
2. Implement SQLite queue schema and job helper.
3. Implement YouTube URL parsing.
4. Implement transcript fetch wrapper.
5. Implement OpenAI structured JSON extractor.
6. Implement markdown renderer.
7. Implement local output storage.
8. Implement worker loop for `summarize_video`.
9. Implement Discord bot plain URL listener.
10. Add `/learn` slash command.
11. Add allowed user ID check.
12. Add `.env.example`, README, and `systemd` units for bot and worker.
13. Test locally with one public YouTube video.
14. Move to Raspberry Pi and run as services.

---

## Future Phase: Channel Watcher

After the manual workflow is stable, add:

```text
/watch add <channel-url>
/watch list
/latest
```

Recommended implementation:

- Use YouTube channel RSS feeds first, not YouTube Data API.
- Store watched channels and processed videos in SQLite.
- Have the watcher enqueue `summarize_channel_video` or `summarize_video` jobs instead of processing videos inline.
- Run watcher through a `systemd` timer.
- Post processed summaries into a configured private Discord channel.

Future flow:

```text
systemd timer
  -> channel_watcher.py
  -> find new videos
  -> process_video(...)
  -> post markdown attachment to Discord
```

---

## Key Decision

Start with Discord manual mode only. Build the pipeline so channel watching can be added later without changing the extraction core.
