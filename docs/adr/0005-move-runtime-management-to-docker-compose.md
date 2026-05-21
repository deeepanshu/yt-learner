# ADR 0005: Move Runtime Management from systemd and Cron to Docker Compose

## Status

Proposed

## Date

2026-05-21

## Context

The current deployment model mixes three host-managed runtime mechanisms:

- `systemd` for `yt-learner-discord`
- `systemd` for `yt-learner-worker`
- user `cron` for `yt-learner-scheduler`

That layout works, but it creates avoidable operational friction for this project.

The repository currently ships:

- two `systemd` unit files
- a wrapper script that shells out to `sudo systemctl`
- a cron installation flow for the scheduler
- Make targets that are tied to those host-level tools

For a small single-host application, that means deployment depends on host-specific service configuration and elevated permissions to install or update the long-lived processes. Even routine application changes require interacting with `/etc/systemd/system` or the host crontab.

The runtime architecture itself is already clean and should be preserved:

- `yt-learner-discord` accepts Discord requests and enqueues jobs
- `yt-learner-worker` processes queued jobs from SQLite
- `yt-learner-scheduler` runs discovery on a wall-clock schedule and enqueues new work

The main issue is not process separation. The issue is that process management is coupled to host service managers.

## Decision

The default deployment model will move to Docker Compose.

The application will run as separate containers that preserve the current runtime boundaries:

- one container for `yt-learner-discord`
- one container for `yt-learner-worker`
- one container for `yt-learner-scheduler`

The Docker-based deployment will:

- build from a single project image
- load configuration from environment variables or an env file
- mount persistent storage for SQLite data
- mount persistent storage for generated markdown outputs
- configure restart behavior in Compose rather than `systemd`
- run the scheduler on an explicit `8:00 AM Asia/Bangkok` schedule inside the containerized deployment

SQLite will remain the persistence layer for now. The database file will live on a mounted volume so container restarts or image rebuilds do not lose queue state, watch configuration, or dedupe records.

Repo-managed `systemd` unit files and the service wrapper script will no longer be the primary deployment path once the Docker implementation is complete. They may be kept temporarily during migration, but Docker Compose becomes the documented and supported default.

## Consequences

### Positive

- Deployment no longer depends on copying unit files into `/etc/systemd/system`.
- Day-to-day app operations no longer require repo-driven `sudo systemctl` usage.
- Bot, worker, and scheduler lifecycle management become consistent across local and hosted environments.
- Rebuilds and rollouts become simpler because all runtime configuration is defined in versioned project files.
- SQLite and generated outputs remain persistent through mounted volumes.
- The existing application boundaries stay intact, so this is an operational migration rather than an architectural rewrite.

### Negative

- The host still needs Docker or a compatible container runtime installed and configured.
- Operators still need some form of host-level permission to install or manage Docker the first time.
- Containerized scheduling adds an implementation choice, such as a dedicated scheduler image/command or a cron-style helper inside the scheduler container.
- SQLite remains a single-host storage choice and is not appropriate for horizontal scaling.

## Rejected Alternatives

### Keep systemd and Cron as the Long-Term Default

Rejected because the current host-managed approach adds unnecessary deployment friction for a three-process application that maps cleanly to containers.

### Collapse Everything into One Container and One Process

Rejected because the existing separation between Discord intake, queued execution, and scheduled discovery is useful and already reflected in the codebase.

### Move Straight to Postgres During the Docker Migration

Rejected for now because the immediate problem is runtime management, not SQLite correctness. Replacing the database at the same time would expand scope and increase migration risk.

## Follow-Up

Implementation should include:

- a project Dockerfile
- a Compose file for `discord`, `worker`, and `scheduler`
- persistent mounts for `data/` and `outputs/`
- documented env-file usage
- replacement Make targets or commands for build, start, stop, logs, and restart
- README updates that make Docker Compose the primary deployment path

The migration should be delivered in a separate implementation change after this ADR is reviewed.
