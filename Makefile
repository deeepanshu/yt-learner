.PHONY: sync test check run run-worker \
	service-install service-restart service-status service-logs service-stop \
	service-install-bot service-restart-bot service-status-bot service-logs-bot service-stop-bot \
	service-install-worker service-restart-worker service-status-worker service-logs-worker service-stop-worker

sync:
	uv sync

test:
	uv run pytest

check:
	./scripts/service.sh check

run:
	uv run yt-learner-discord

run-worker:
	uv run yt-learner-worker

service-install:
	./scripts/service.sh install all

service-restart:
	./scripts/service.sh restart all

service-status:
	./scripts/service.sh status all

service-logs:
	./scripts/service.sh logs all

service-stop:
	./scripts/service.sh stop all

service-install-bot:
	./scripts/service.sh install discord

service-restart-bot:
	./scripts/service.sh restart discord

service-status-bot:
	./scripts/service.sh status discord

service-logs-bot:
	./scripts/service.sh logs discord

service-stop-bot:
	./scripts/service.sh stop discord

service-install-worker:
	./scripts/service.sh install worker

service-restart-worker:
	./scripts/service.sh restart worker

service-status-worker:
	./scripts/service.sh status worker

service-logs-worker:
	./scripts/service.sh logs worker

service-stop-worker:
	./scripts/service.sh stop worker
