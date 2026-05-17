SERVICE_NAME := yt-learner-discord

.PHONY: sync test check run service-install service-restart service-status service-logs service-stop

sync:
	uv sync

test:
	uv run pytest

check:
	./scripts/service.sh check

run:
	uv run yt-learner-discord

service-install:
	./scripts/service.sh install

service-restart:
	./scripts/service.sh restart

service-status:
	./scripts/service.sh status

service-logs:
	./scripts/service.sh logs

service-stop:
	./scripts/service.sh stop
