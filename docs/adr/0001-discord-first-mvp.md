# ADR 0001: Build the MVP as a Discord bot with a shared extraction pipeline

## Status

Accepted

## Date

2026-05-17

## Context

The first version of `yt-learner` needs a low-friction interface for submitting a YouTube URL from a phone and receiving structured learning notes back. The earlier design exploration considered Telegram and WhatsApp, but the operational overhead differs substantially.

The MVP also needs to stay narrow enough that the extraction path can be validated before adding background channel watching, storage complexity, or multi-user workflows.

## Decision

The MVP will be implemented as a Discord bot with two invocation paths:

- Plain YouTube URL messages in DMs or explicitly allowed channels.
- A `/learn` slash command that accepts a YouTube URL.

Both paths will call the same shared application pipeline:

1. Parse the YouTube URL into a canonical video identifier.
2. Reuse an existing generated markdown file when present.
3. Fetch the transcript.
4. Run OpenAI extraction to generate structured learning notes.
5. Persist the markdown output locally.
6. Return the markdown file to Discord as an attachment.

The extraction pipeline will remain Discord-agnostic. Discord-specific concerns such as authorization, message parsing, status replies, and file upload stay in the Discord adapter.

## Consequences

### Positive

- Lower setup complexity than WhatsApp.
- No business phone number or template message workflow.
- A Raspberry Pi can host the bot as a long-running process.
- The shared pipeline can later support other adapters or a background watcher without redesign.
- Manual URL processing can be validated before taking on watcher and scheduling complexity.

### Negative

- The first release does not address automated channel watching.
- Discord introduces bot setup and slash-command registration work.
- The initial implementation is intentionally single-user and local-file based.

## Deferred Decisions

The following are explicitly out of scope for this ADR and are deferred:

- Channel watcher implementation.
- SQLite metadata storage.
- Multi-user support.
- Rich Discord UI interactions.
- Cloud deployment.
