.PHONY: sync test check run-bot run-worker run-scheduler run-all \
	docker-build docker-up docker-down docker-restart docker-logs docker-ps docker-run-scheduler

sync:
	uv sync

test:
	uv run pytest

check:
	uv run yt-learner-discord --check-config

run-bot:
	uv run yt-learner-discord

run-worker:
	uv run yt-learner-worker

run-scheduler:
	uv run yt-learner-scheduler

run-all:
	(sh -c 'trap "kill 0" INT TERM EXIT; $(MAKE) run-bot & $(MAKE) run-worker & wait')

docker-build:
	docker compose build discord

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

docker-restart:
	docker compose up -d --build --force-recreate

docker-logs:
	docker compose logs -f

docker-ps:
	docker compose ps

docker-run-scheduler:
	docker compose run --rm scheduler yt-learner-scheduler
