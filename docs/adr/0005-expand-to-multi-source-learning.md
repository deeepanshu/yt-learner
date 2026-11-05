# ADR 0005: Expand from YouTube-Only Processing to Multi-Source Learning

## Status

Accepted

## Date

2026-05-18

## Context

`yt-learner` currently processes YouTube videos well:

- the Discord bot accepts manual requests and watched-channel events
- the queue stores durable job state in SQLite
- the worker claims jobs and runs the learning pipeline
- the pipeline fetches transcript content and generates markdown notes

That architecture is already suitable for more than YouTube, but the current execution path is still video-specific in a few important places:

- queue payloads assume `video_url`
- the worker calls a video-specific processor
- the pipeline is centered on transcript fetch and video metadata
- the extractor prompt assumes every source is a YouTube transcript

The product direction now extends beyond YouTube videos. The next target inputs are:

- news articles
- technical documentation pages

Those inputs introduce a new requirement: the system should learn from multiple source types without duplicating the queue, worker, storage, and Discord delivery logic for each source.

## Decision

The application will evolve from a YouTube-specific learning pipeline to a source-generic learning pipeline.

The existing runtime model remains in place:

- `yt-learner-discord` continues to validate requests and enqueue jobs
- `yt-learner-worker` continues to claim jobs, process them, and post results
- SQLite remains the durable store for jobs and source metadata
- markdown artifacts remain on disk

The main change is the processing contract.

### 1. Introduce a generic source request model

Queue payloads will no longer assume a single `video_url` field. Instead, queued work should identify:

- `source_type`
- `source_ref`
- reply metadata such as Discord channel and message ids

Examples of `source_type`:

- `youtube_url`
- `news_article`
- `technical_doc`

### 2. Replace the video-specific processor with source handlers

The processing layer should dispatch by source type through dedicated handlers.

Each handler is responsible for:

- validating and normalizing the incoming reference
- deriving a stable dedupe key
- fetching source content
- extracting metadata such as title and canonical URL
- converting the source into a normalized content payload for the extractor

The shared pipeline remains responsible for:

- dedupe lookup
- calling OpenAI
- storing markdown artifacts
- recording learning metadata

### 3. Normalize fetched content before extraction

The extractor should no longer depend on a YouTube transcript shape only.

Instead, source handlers should normalize content into a shared internal representation that includes:

- source identity
- title
- canonical URL
- source-specific metadata
- plain text body used for learning extraction

This keeps fetch and parse concerns separate from note generation.

### 4. Keep discovery separate from learning

The product has two different concerns:

- learning from a source reference supplied by a user
- discovering new sources automatically

The system should implement these in sequence, not at the same time.

The first extension milestone is manual URL learning:

- user submits a URL
- bot identifies source type
- queue stores a generic source-processing job
- worker processes the source and replies with notes

Automatic discovery is a later concern:

- news via RSS or Atom feeds
- technical docs via watched release notes, changelogs, or documentation indexes

Discovery should enqueue the same generic source-processing jobs used by manual requests.

## Consequences

### Positive

- The current bot, queue, worker, and storage architecture can be reused instead of duplicated.
- New source types can be added by introducing handlers rather than parallel pipelines.
- The learning product becomes aligned with the existing source-agnostic storage model.
- Automatic discovery can reuse the same processing path after manual URL support is stable.

### Negative

- The refactor touches core contracts in the queue and pipeline.
- Source-type routing and normalization introduce new abstraction boundaries that must stay simple.
- HTML extraction for news and docs is less reliable than YouTube transcript fetch and will require stronger error handling.
- The extractor prompt will need source-aware variants to keep output quality high.

## Rejected Alternatives

### Add a Separate Pipeline for Each Source Type

Rejected because it would duplicate queue handling, worker execution, storage, and Discord delivery logic. That would make future source expansion slower and harder to maintain.

### Add Automatic Discovery Before Manual URL Support

Rejected because discovery creates operational noise before the system can reliably learn from a single manually supplied article or document URL. Manual URL support is the safer first milestone.

### Keep One Shared YouTube-Oriented Prompt for All Sources

Rejected because news articles and technical docs require different extraction structure and emphasis. A single transcript-oriented prompt would reduce note quality and produce mismatched output.

## Rollout Plan

Implementation should proceed in phases:

1. Generalize the queue and pipeline contracts while preserving existing YouTube behavior.
2. Add manual URL learning for news articles and technical documentation pages.
3. Add source-aware extraction prompts and output structures.
4. Add discovery sources such as RSS feeds and watched documentation surfaces.

The first implementation milestone should not change scheduler behavior or watched YouTube channel behavior. It should focus on making `/learn <url>` source-generic while keeping the current Discord-first workflow intact.
