# ADR 0004: Run Watched-Channel Polling from Cron and Keep the Worker Focused on Queued Jobs

## Status

Accepted

## Date

2026-05-18

## Context

The first watched-channel scheduler implementation ran inside the long-lived worker process on a fixed interval. That made polling time relative to worker startup rather than to an explicit wall-clock schedule.

For operators, a setting like "every 24 hours" was ambiguous in practice. It meant "24 hours after the worker last polled" rather than "at a predictable time of day." Restarting the worker also reset the next polling time.

The project already has a durable queue and a separate worker process for running queued jobs, so only the discovery trigger needs a more predictable schedule.

## Decision

Watched-channel polling will move to a dedicated run-once CLI command, `yt-learner-scheduler`, intended to be invoked by cron.

The scheduler command will:

- load settings
- read active watched channels from SQLite
- poll YouTube feeds once
- enqueue summarize jobs into the existing SQLite queue
- exit

The long-lived worker will no longer own periodic feed polling. It will remain responsible for:

- claiming queued jobs
- running the extraction pipeline
- writing output artifacts
- posting Discord notifications

## Consequences

### Positive

- Polling happens at explicit wall-clock times controlled by cron.
- Restarting the worker no longer changes the next scheduled discovery time.
- Discovery and processing continue to share the existing queue and dedupe behavior.
- The worker process has a narrower and clearer responsibility.

### Negative

- Scheduling now depends on external cron configuration.
- If cron is misconfigured or the scheduled command does not run, watched channels will not be polled.

