.PHONY: sync test check run-bot run-worker run-scheduler run-all \
	service-install service-restart service-status service-logs service-stop \
	service-install-bot service-restart-bot service-status-bot service-logs-bot service-stop-bot \
	service-install-worker service-restart-worker service-status-worker service-logs-worker service-stop-worker \
	service-install-scheduler service-restart-scheduler service-status-scheduler service-logs-scheduler service-stop-scheduler

sync:
	uv sync

test:
	uv run pytest

check:
	./scripts/service.sh check

run-bot:
	uv run yt-learner-discord

run-worker:
	uv run yt-learner-worker

run-scheduler:
	uv run yt-learner-scheduler

run-all:
	(sh -c 'trap "kill 0" INT TERM EXIT; $(MAKE) run-bot & $(MAKE) run-worker & wait')

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

service-install-scheduler:
	./scripts/service.sh install scheduler

service-restart-scheduler:
	./scripts/service.sh restart scheduler

service-status-scheduler:
	./scripts/service.sh status scheduler

service-logs-scheduler:
	./scripts/service.sh logs scheduler

service-stop-scheduler:
	./scripts/service.sh stop scheduler
