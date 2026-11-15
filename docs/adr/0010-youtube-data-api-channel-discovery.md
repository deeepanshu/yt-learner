# ADR 0010: Use YouTube Data API for Channel Discovery

## Status

Accepted

## Date

2026-11-15

## Context

Watched-channel discovery used YouTube's public RSS endpoint:

`https://www.youtube.com/feeds/videos.xml?channel_id=<channel_id>`

YouTube intermittently returned HTTP 404 for valid channels, causing the daily scheduler to complete with zero subscriptions polled and zero jobs enqueued. The channel pages remained available, so the RSS response was not a reliable channel-existence signal.

## Decision

Use the public YouTube Data API v3 to discover uploads:

1. Batch the active channel IDs in one `channels.list` request with `part=snippet,contentDetails`.
2. Read each channel's `contentDetails.relatedPlaylists.uploads` playlist ID.
3. Fetch recent uploads with one `playlistItems.list` request per uploads playlist.
4. Map API results into the existing `ChannelFeedVideo` model.
5. Keep the existing Postgres deduplication, queue, bootstrap, worker, and Trilium flow unchanged.

The scheduler will resolve uploads playlist IDs during each run rather than persist them, avoiding stale API-data caching and avoiding a schema migration. The API key is supplied through `YOUTUBE_DATA_API_KEY` and must remain in deployment secrets.

## Consequences

### Positive

- Removes dependence on the failing public RSS endpoint.
- Uses an official, documented API for public channel data.
- One daily run for three channels uses four quota units: one batched `channels.list` call plus three `playlistItems.list` calls.
- Existing queue and deduplication behavior remains unchanged.

### Negative

- Requires a Google Cloud project, YouTube Data API v3 enablement, and an API key.
- API quota and YouTube API Services policies apply.
- Additional playlist pages consume additional quota units.
- API outages still require retries and degraded-run reporting.

## Rejected Alternatives

### Unofficial RSS Proxies

Rejected because they add an external dependency and do not provide a durable availability or policy boundary.

### Persistent Playlist-ID Cache

Rejected for the initial implementation because the quota cost of resolving three channels is negligible and avoiding persistent API-data caching is simpler to operate and audit.
