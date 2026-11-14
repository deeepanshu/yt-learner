# ADR 0008: Retire Discord and manage watches over HTTP

## Status

Accepted

## Date

2026-11-14

## Context

Delivery already goes to Trilium (ADR 0007). Discord was still the command surface: `/learn`, URL messages, `/watch`, and worker status pings. `/learn` is not needed. Watches still need an operator UI.

## Decision

Remove Discord from the runtime.

- Replace `yt-learner-discord` with `yt-learner-web`, a Tailscale/LAN HTML UI for adding and removing YouTube channel watches.
- Do not put the watch UI on Cloudflare Tunnel.
- Scheduler discovers new uploads and enqueues summarize jobs.
- Worker publishes notes to Trilium and does not notify Discord.
- Drop `guild_id` and `discord_channel_id` from `watched_channels`. Drop `discord_threads`.
- Remove `/learn` and Discord thread questions.

## Consequences

### Positive

- One notes destination: Trilium.
- Watch management works without a Discord bot token.

### Negative

- No on-demand "learn this URL" path until a later UI exists.
- Watch UI is reachable on the published host port; keep it off public ingress.
