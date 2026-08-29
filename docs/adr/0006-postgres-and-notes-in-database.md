# ADR 0006: Move Relational State and Notes into Homelab Postgres

## Status

Accepted

## Date

2026-08-29

## Context

yt-learner stored jobs, watches, source metadata, and artifact paths in one SQLite file, with markdown notes and debug transcripts on disk. Homelab apps join shared Postgres on the `homelab` network. SQLite cannot participate in that stack, and a path pointer next to a Discord attachment is extra state the product does not use.

ADR 0002 kept large artifacts on disk because SQLite is a poor blob store and local files were convenient during the MVP. The product surface is Discord, not a local markdown workspace.

## Decision

Postgres is the only application database.

- `DATABASE_URL` is required. `YOUTUBE_LEARNER_DB_PATH` is removed.
- Schema lives in `app/migrations/` and is applied by `yt-learner-migrate`, not at process start.
- Job claim uses `SELECT … FOR UPDATE SKIP LOCKED`.
- Learning notes are stored as `learning_records.markdown`. Discord sends the body as an in-memory file attachment.
- Debug transcripts are stored in `debug_artifacts`.
- Markdown files are not a runtime store. Existing SQLite + `outputs/` data is imported once with `scripts/import-sqlite.py`.

This supersedes ADR 0002's default of filesystem artifacts. Source vs learning-record modeling from ADR 0002 still holds.

## Consequences

### Positive

- One backup target (`pg_dump`) for queue, watches, and notes.
- No stale `artifact_path` after container rebuilds.
- Matches the family-os homelab pattern: `DATABASE_URL`, migrate service, `homelab` network.

### Negative

- Local tests and development need Postgres.
- Existing Pi SQLite must be imported before cutover.
- `pg_dump` grows with note bodies.

## Rejected Alternatives

### Keep SQLite locally and Postgres in production

Rejected because dual backends hide SQL dialect bugs (claim locking, `ON CONFLICT`, timestamps).

### Keep notes on disk and only move metadata to Postgres

Rejected because the file is not a product surface; it only creates a second store to back up.
