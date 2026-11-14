# ADR 0007: Deliver learning notes to Trilium

## Status

Accepted

## Date

2026-11-14

## Context

`yt-learner` still takes work from Discord (`/learn`, URL messages, `/watch`). The worker posted the generated markdown back to Discord as an attachment, often in a per-video thread. Those notes belong in Trilium, which is the homelab notes store.

Official Obsidian/Discord Sync is not involved. TriliumNext on `pve-forge` exposes ETAPI.

## Decision

Keep Discord as the command and status surface. Change delivery:

1. The worker publishes learning notes to Trilium over ETAPI before marking a job done.
2. Video notes are text notes under `TRILIUM_PARENT_NOTE_ID`, labeled `ytLearnerVideoId=<youtube video id>`.
3. Reprocessing the same video updates that note in place.
4. Thread questions become child notes of the video note.
5. Discord receives a short "saved to Trilium" status, never the markdown attachment.

The extraction pipeline stays Discord-agnostic. Trilium HTTP details stay in `app/trilium.py`.

## Consequences

### Positive

- Notes land in the existing Trilium tree instead of Discord files.
- Idempotent republish on worker retry.
- Discord remains the phone-friendly trigger.

### Negative

- Worker now requires a reachable Trilium ETAPI token and parent note.
- New videos no longer get Discord learning threads, so in-thread follow-up questions only work on already-mapped threads.

## Deferred

- Mapping `/watch` destinations to per-channel Trilium notebooks.
- Removing Discord from the worker process entirely.
