# ADR 0010: Deliver learning notes to Outline

## Status

Accepted

## Date

2026-11-14

## Context

The notes service moved from Trilium to self-hosted Outline. yt-learner already stores generated markdown in Postgres and needs a durable external publisher with an authenticated write API.

## Decision

Publish learning notes to Outline over its API before marking a job done.

- `OUTLINE_URL` points to the LAN service (`http://outline.lab:3000`).
- `OUTLINE_API_KEY` is an Outline personal API key held by Komodo secrets.
- `OUTLINE_COLLECTION_ID` identifies the target collection by URL ID or UUID.
- Channel documents are created at the collection root; video documents are nested under their channel document.
- Each video document contains a stable `yt-learner-video:<youtube video id>` marker. Republishing searches for that marker and updates the existing document.
- The Outline client resolves a collection URL ID to its UUID before creating documents.
- The extraction pipeline remains independent of the publisher.

## Consequences

- Notes are visible in Outline and preserve idempotent worker retries.
- Outline is now a required worker dependency.
- Existing Trilium notes are not migrated or modified by yt-learner.
- The older Trilium delivery ADRs remain historical records; this ADR supersedes their delivery decision.
