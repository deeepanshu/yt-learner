# ADR 0002: Model Learning Records Separately from Sources and Keep Large Artifacts on Disk

## Status

Accepted

## Date

2026-05-17

## Context

The initial MVP started with a YouTube-specific flow that generated markdown files on disk and returned them to Discord. During implementation, the design evolved in two important ways:

1. Job execution moved to a SQLite-backed queue and worker model.
2. The product direction expanded beyond YouTube URLs to include other learnable inputs such as markdown files, PDFs, or pasted text.

Those changes create two modeling questions:

- Should the persistent domain model stay YouTube-specific or become source-agnostic?
- Should generated markdown be stored directly in SQLite or continue to live as a file artifact?

The current queue database is a good place for durable job state and metadata, but it is not automatically the best place for large generated blobs.

## Decision

The application will use a source-agnostic storage model:

- `sources` will represent the original input being learned from.
- `learning_records` will represent the derived learning artifact generated from that source.

The schema and naming should not assume that every source is a YouTube video. Source type should be explicit, for example:

- `youtube_url`
- `markdown_file`
- `pdf_file`
- `text`

Large generated artifacts such as markdown notes, transcript debug dumps, and future structured exports will remain on disk by default. SQLite will store metadata and references to those artifacts rather than the full markdown body.

In practice:

- job state lives in `jobs`
- source identity lives in `sources`
- derived learning metadata lives in `learning_records`
- large content lives on disk and is referenced by path

## Consequences

### Positive

- The domain model stays correct if inputs expand beyond YouTube.
- `learning_records` matches the product concept better than `yt_video_summary` or other format-specific names.
- SQLite remains small and focused on queue state, dedupe keys, and metadata lookups.
- Markdown files remain easy to inspect, back up, export, and recover manually.
- The design supports one source producing multiple learning artifacts later, such as notes, flashcards, or action-item extracts.

### Negative

- The system now has two persistence layers: SQLite for metadata and the filesystem for large artifacts.
- Artifact paths must be managed carefully so database rows do not point at missing files.
- Discord attachment delivery still depends on reading a file artifact at send time.

## Rejected Alternatives

### Store Markdown Directly in `jobs`

Rejected because `jobs` is an execution table, not the long-term domain model for learned content. Mixing queue state and large output blobs would make the table harder to evolve and reason about.

### Store Markdown Directly in SQLite

Rejected as the default because markdown is an artifact rather than relational state. SQLite can store large text, but doing so would grow the database quickly and make manual inspection and operational recovery less convenient for this MVP.

### Use a YouTube-Specific Table Such as `yt_video_summary`

Rejected because the product direction is no longer limited to YouTube URLs. A YouTube-specific primary table would create unnecessary rename or migration pressure once file-based and text-based sources are added.

## Follow-Up

Implementation should evolve toward:

- a `sources` table with source type, source reference, title, and dedupe fields
- a `learning_records` table with source linkage, artifact type, artifact path, and timestamps
- continued filesystem storage for markdown and debug artifacts

This ADR supersedes the earlier assumption that persistent output can remain modeled only as local markdown files keyed directly by video ID.
