# SOPS + age Secret Management Plan

## Status

Proposed design for moving `yt-learner` away from committed secret file paths and plaintext env files while keeping the Docker Compose workflow lightweight.

## Goals

- Keep the public repository free of secret values.
- Avoid committing personal host paths such as `/home/deepanshu/secrets/...`.
- Avoid paid or heavy infrastructure such as 1Password, Vault, or a custom secrets service.
- Support both Docker Compose deployment and local `uv run` commands.
- Keep the runtime model simple: secrets are injected by the host before the app starts.

## Non-goals

- This is not a sidecar, agent, or separate service running inside Docker.
- This does not provide dynamic/leased secrets like Vault.
- This does not hide secrets from a user with root access or Docker daemon access on the host.

## Recommended Shape

Use `SOPS` with `age` encryption. Store encrypted secrets outside the public repository, and inject them into commands at runtime.

```text
RPi host
├── /home/deepanshu/.config/sops/age/keys.txt     # private age key, never committed
└── /home/deepanshu/secrets/yt-shared.enc.env     # encrypted SOPS env file, outside repo

public yt-learner repo
├── docker-compose.yml                            # committed, no secret file paths
├── Makefile                                      # committed, no secret file paths
└── docs/designs/sops-age-secret-management.md
```

The encrypted file can contain shared secrets for `yt-learner` and other local projects, for example:

```dotenv
OPENAI_API_KEY=...
DISCORD_BOT_TOKEN=...
```

Only the encrypted form is stored on disk. The age private key is the bootstrap secret that can decrypt it.

## Docker Compose Integration

Prefer committing only expected environment variable names in `docker-compose.yml`:

```yaml
services:
  discord:
    environment:
      OPENAI_API_KEY: ${OPENAI_API_KEY:?missing}
      DISCORD_BOT_TOKEN: ${DISCORD_BOT_TOKEN:?missing}
```

Then start Docker Compose through `sops exec-env`:

```bash
SECRETS_FILE=/home/deepanshu/secrets/yt-shared.enc.env \
  sops exec-env "$SECRETS_FILE" 'docker compose up -d --build'
```

`SOPS` decrypts the encrypted env file, exposes the values to the `docker compose` process, and Compose passes them into the containers.

Important Compose behavior:

- `${VAR:?missing}` fails early if a required variable is missing.
- Compose variable interpolation happens on the host before containers are created.
- The public Compose file reveals variable names, but not secret values or private file paths.
- Do not put the encrypted secret file path in `docker-compose.yml` for public repos.

### Why Not Put the SOPS File in Compose?

Do not make the encrypted SOPS file an `env_file` entry in the committed Compose file:

```yaml
# Avoid this in a public repo.
env_file:
  - /home/deepanshu/secrets/yt-shared.enc.env
```

That has two problems:

1. `env_file` expects plaintext dotenv content. It does not decrypt SOPS files, so containers would receive encrypted values or fail to parse the file.
2. The public repo would expose the private host path and secret-management layout.

Docker Compose `secrets:` has a similar tradeoff for this use case: it still needs a source file path, and that source must be plaintext by the time Docker reads it. That can work for Swarm or a private deployment repository, but it does not solve the public-repo path exposure problem.

If Compose-specific secret wiring is desired, keep it in an uncommitted override file, for example `compose.private.yml`, and run:

```bash
sops exec-env "$SECRETS_FILE" 'docker compose -f docker-compose.yml -f compose.private.yml up -d --build'
```

For this public repo, the preferred committed contract is only env var names in Compose plus host-side `sops exec-env` injection.

## Local `uv run` Integration

The same secret file can run local commands:

```bash
SECRETS_FILE=/home/deepanshu/secrets/yt-shared.enc.env \
  sops exec-env "$SECRETS_FILE" 'uv run yt-learner-discord'
```

Worker example:

```bash
SECRETS_FILE=/home/deepanshu/secrets/yt-shared.enc.env \
  sops exec-env "$SECRETS_FILE" 'uv run yt-learner-worker'
```

Scheduler example:

```bash
SECRETS_FILE=/home/deepanshu/secrets/yt-shared.enc.env \
  sops exec-env "$SECRETS_FILE" 'uv run yt-learner-scheduler'
```

## Makefile Pattern

If Makefile targets are added, do not hardcode the secret path. Require it from the shell:

```makefile
require-secrets-file:
	@test -n "$$SECRETS_FILE" || (echo "Set SECRETS_FILE to an encrypted SOPS env file" && exit 1)

sops-docker-up: require-secrets-file
	sops exec-env "$$SECRETS_FILE" 'docker compose up -d --build'

sops-docker-restart: require-secrets-file
	sops exec-env "$$SECRETS_FILE" 'docker compose up -d --build --force-recreate'

sops-run-bot: require-secrets-file
	sops exec-env "$$SECRETS_FILE" 'uv run yt-learner-discord'

sops-run-worker: require-secrets-file
	sops exec-env "$$SECRETS_FILE" 'uv run yt-learner-worker'
```

Usage:

```bash
export SECRETS_FILE=/home/deepanshu/secrets/yt-shared.enc.env
make sops-docker-up
```

This keeps the actual filename and path out of GitHub.

## Initial Setup Commands

Install tools on the RPi:

```bash
sudo apt install age
# Install sops from the official GitHub release or distro package if available.
```

Create the age key:

```bash
mkdir -p ~/.config/sops/age
chmod 700 ~/.config/sops/age
age-keygen -o ~/.config/sops/age/keys.txt
chmod 600 ~/.config/sops/age/keys.txt
```

Capture the public recipient printed by `age-keygen`, which looks like:

```text
age1...
```

Create or edit the encrypted env file:

```bash
mkdir -p /home/deepanshu/secrets
chmod 700 /home/deepanshu/secrets

export SOPS_AGE_RECIPIENTS='age1...'
sops /home/deepanshu/secrets/yt-shared.enc.env
```

Inside the editor, add normal dotenv entries. SOPS writes the encrypted version back to disk.

## Secret Sharing Between Projects

If `yt-learner` and `expense-tracker` truly share a secret, keep it in the shared encrypted file. If a secret should be independently revocable or separately billed, create project-specific encrypted files instead.

Recommended split:

```text
/home/deepanshu/secrets/shared.enc.env             # truly shared secrets
/home/deepanshu/secrets/yt-learner.enc.env         # yt-learner-only secrets
/home/deepanshu/secrets/expense-tracker.enc.env    # expense-tracker-only secrets
```

For multiple files, either create a small uncommitted wrapper script on the host or merge the required project secrets into one project-specific encrypted env file. Avoid putting these paths in public repo files.

## Security Notes

- SOPS protects secrets at rest, not after they are injected into a running process.
- Docker environment variables can often be viewed by users with Docker daemon access.
- Back up the age private key securely; without it, the encrypted file cannot be decrypted.
- If the age private key is exposed, rotate affected secrets and create a new key.
- Keep real secret files, decrypted temp files, and private keys out of all repos.

## Migration Plan

1. Create the age key on the RPi.
2. Create `/home/deepanshu/secrets/yt-shared.enc.env` with current required secrets.
3. Change Compose to consume required secrets from host environment variables instead of committed `env_file` paths.
4. Add Makefile targets that use `sops exec-env` and require `SECRETS_FILE` from the shell.
5. Test local commands with `sops exec-env`.
6. Test Docker deployment with `sops exec-env "$SECRETS_FILE" 'docker compose up -d --build --force-recreate'`.
7. Remove any now-unused plaintext env files from the host after confirming the deployment works.

## Recommendation

Use SOPS + age as a host-side runtime secret injector. Keep encrypted secret files outside public repos, keep the private age key locked down, and commit only variable names needed by the app.
