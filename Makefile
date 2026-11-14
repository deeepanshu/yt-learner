.PHONY: sync test test-db check run-web run-worker run-scheduler run-mcp run-mcp-http run-all \
	docker-build docker-up docker-down docker-restart docker-logs docker-ps docker-run-scheduler

TEST_DATABASE_URL ?= postgres://yt_learner:yt_learner@127.0.0.1:55432/yt_learner_test

sync:
	uv sync

test-db:
	docker compose -f docker-compose.test.yml up -d --wait

test: test-db
	TEST_DATABASE_URL=$(TEST_DATABASE_URL) uv run pytest

check:
	uv run yt-learner-web --check-config

run-web:
	uv run yt-learner-web

run-worker:
	uv run yt-learner-worker

run-scheduler:
	uv run yt-learner-scheduler

run-mcp:
	uv run python -m app.mcp_server

run-mcp-http:
	uv run python -m app.mcp_server --http

run-all:
	(sh -c 'trap "kill 0" INT TERM EXIT; $(MAKE) run-web & $(MAKE) run-worker & wait')

docker-build:
	docker compose build web

docker-up:
	docker compose --profile migrate run --rm migrate
	docker compose up -d --build

docker-down:
	docker compose down

docker-restart:
	docker compose --profile migrate run --rm migrate
	docker compose up -d --build --force-recreate

docker-logs:
	docker compose logs -f

docker-ps:
	docker compose ps

docker-run-scheduler:
	docker compose run --rm scheduler yt-learner-scheduler
