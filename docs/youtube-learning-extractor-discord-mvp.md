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
  - status text
  - markdown attachment
```

The important design rule: both invocation paths call the same `process_video(...)` function. Discord-specific behavior should stay in the Discord adapter, not inside the extraction pipeline.

---

## Proposed File Structure

```text
yt-learner/
  app/
    discord_bot.py          # Discord bot, URL listener, /learn command
    pipeline.py             # Shared process_video(video_url, requested_by)
    youtube_urls.py         # URL parsing and video ID extraction
    transcript.py           # youtube-transcript-api wrapper
    extractor.py            # OpenAI prompt and structured markdown generation
    storage.py              # Output paths, dedupe checks, optional metadata JSON
    config.py               # Env/config loading
  outputs/
    .gitkeep
  yt-learner-discord.service
  .env.example
  README.md
  requirements.txt
```

SQLite can be skipped in the first version. A simple output file naming convention plus optional sidecar metadata JSON is enough for the MVP.

---

## Environment Variables

```env
OPENAI_API_KEY=
DISCORD_BOT_TOKEN=
DISCORD_ALLOWED_USER_ID=
DISCORD_OUTPUT_DIR=/home/pi/yt-learner/outputs
OPENAI_MODEL=gpt-4o-mini
```

Optional later:

```env
DISCORD_ALLOWED_CHANNEL_ID=
YOUTUBE_LEARNER_MAX_TRANSCRIPT_CHARS=
```

---

## Processing Contract

Target function:

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
    output_path: Path
    reused_existing: bool
```

The Discord adapter should only care about:

- what status message to send,
- whether processing succeeded,
- which file to attach.

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
Processed: <timestamp>

## Summary

...

## Topics

### <Topic> ([timestamp](https://youtube.com/watch?v=...&t=123s))

- Key point
- Subtopic
- Practical takeaway

## Actionable Notes

...
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

## Implementation Plan

1. Create `yt-learner` project skeleton.
2. Implement YouTube URL parsing.
3. Implement transcript fetch wrapper.
4. Implement OpenAI markdown extractor.
5. Implement local markdown storage.
6. Implement Discord bot plain URL listener.
7. Add `/learn` slash command.
8. Add allowed user ID check.
9. Add `.env.example`, README, and `systemd` unit.
10. Test locally with one public YouTube video.
11. Move to Raspberry Pi and run as a service.

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

