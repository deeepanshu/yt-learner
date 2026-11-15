# ADR 0011: Store Outline Publication Links Explicitly

## Status

Accepted

## Context

Outline document identity was embedded in visible document Markdown as HTML comments. The publisher searched those markers through Outline full-text search to find channel folders and video notes. Outline search could return unrelated documents, and the markers were visible in the Outline editor.

The application needs a durable association between a YouTube source and its published Outline document, but the learning-domain records should not depend directly on Outline-specific columns.

## Decision

Store provider mappings in a separate `external_document_links` table:

- `provider=outline`, `source_type=youtube_channel`, `source_key=<YouTube channel ID>`, `remote_id=<Outline folder ID>`
- `provider=outline`, `source_type=youtube_video`, `source_key=<YouTube video ID>`, `remote_id=<Outline document ID>`

The Outline adapter consults this mapping before publishing. It uses exact source-URL search only as a recovery path when a mapping is absent, then saves the recovered remote ID. New Outline documents contain no synchronization markers or frontmatter.

The scheduler carries the YouTube channel ID through the queue and worker so scheduled videos always resolve the channel-folder mapping by stable source identity. Legacy jobs without that field recover the channel ID from `watched_channel_videos`.

## Consequences

### Positive

- Postgres remains authoritative for source identity and publication relationships.
- Outline bodies contain only user-facing note content.
- Normal updates use direct Outline document IDs, not full-text search.
- A deleted remote document can be recreated and remapped.
- Removing Outline later does not require changing learning-record schemas.

### Negative

- The application must run a schema migration and one-time legacy marker migration.
- Cross-system creation is not transactional; source-URL recovery handles a crash after remote creation but before mapping persistence.
- Manual UI jobs without a channel ID use a title-based fallback mapping until channel identity is resolved.
