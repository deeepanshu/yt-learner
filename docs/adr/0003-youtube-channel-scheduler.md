# ADR 0003: Add YouTube Channel Scheduling Inside the Existing Worker and Persist Seen Uploads in SQLite

## Status

Accepted

## Date

2026-05-17

## Context

The initial MVP supported manual `/learn` requests and plain YouTube URLs sent to Discord. The next requirement is to watch selected YouTube channels, learn from new uploads automatically, and post the result into topic-specific Discord channels.

That creates four design questions:

1. Should scheduling run in the Discord bot process or the worker process?
2. Where should watched-channel configuration live?
3. How should Discord routing work when different YouTube channels map to different topics?
4. How should the system prevent duplicate indexing across restarts and repeated feed polls?

The existing runtime already separates request intake from long-running work:

- `yt-learner-discord` handles Discord interactions and job creation
- `yt-learner-worker` handles background execution and delivery

The project also already uses SQLite for durable queue state and learning-record metadata.

## Decision

The scheduler will be added to the existing worker process and will reuse the current queue-and-worker pipeline rather than introducing a third long-lived process or a direct processing path.

Configuration and state will be stored in SQLite:

- `watched_channels` stores watched YouTube channels per Discord guild
- `watched_channel_videos` stores discovered uploads per watched channel

Watched channels will be managed from Discord through admin slash commands, not environment variables. Each watched YouTube channel stores its own Discord destination channel, which allows multiple subscriptions to share one destination or route to different topic channels without adding a separate topic model.

Bootstrap behavior is conservative:

- when a watched channel is added, the current feed entries are marked as seen
- those bootstrap entries are not backfilled into the queue
- only later unseen uploads are enqueued

Discovery uses YouTube’s public channel feed in v1 instead of the YouTube Data API.

## Consequences

### Positive

- Scheduling stays inside the existing two-process architecture.
- All scheduled uploads reuse the current durable queue, worker notifications, and markdown generation flow.
- SQLite prevents duplicate enqueueing across worker restarts and repeated polls.
- Discord-based subscription management avoids redeploying to change watched channels.
- Per-subscription Discord routing is enough for topic-based delivery without a new abstraction layer.
- The feature ships without a YouTube API key or quota dependency.

### Negative

- Feed discovery depends on public YouTube channel/feed behavior rather than an official authenticated API.
- Bootstrap skips historical uploads, so backfill needs a future explicit feature.
- The worker now owns both job execution and periodic feed polling, which increases its responsibilities.
- Watched channel resolution from handles and non-`/channel/` URLs depends on parsing public channel pages.

## Rejected Alternatives

### Environment Variable Channel Lists

Rejected because the user wants to provide and change watched channels operationally through Discord, not by editing deployment config and restarting services.

### A Separate Scheduler Process

Rejected because the worker already exists to own durable background behavior. A separate process would duplicate queue access, lifecycle management, and deployment work for little benefit in this MVP.

### Topic Group Tables

Rejected for v1 because per-subscription Discord routing already supports many-to-one topic channel mapping. A separate topic model would add extra schema and commands before there is evidence it is needed.

### Immediate Backfill on First Watch

Rejected because first-sync backfill could create a large unreviewed queue and surprise the operator. Conservative bootstrap is safer for the first version.

## Follow-Up

Implementation should include:

- admin `/watch add`, `/watch list`, and `/watch remove` commands
- worker-side channel polling on a configurable interval
- SQLite persistence for watched channels and discovered uploads
- restart-safe dedupe before queueing

Future iterations can add explicit backfill, better channel resolution, or a YouTube Data API integration if public-feed limitations become operationally significant.
