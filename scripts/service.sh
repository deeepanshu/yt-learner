#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UV_BIN="${UV_BIN:-/home/deepanshu/.local/bin/uv}"
DISCORD_SERVICE_NAME="yt-learner-discord"
WORKER_SERVICE_NAME="yt-learner-worker"
DISCORD_SERVICE_FILE="$ROOT_DIR/$DISCORD_SERVICE_NAME.service"
WORKER_SERVICE_FILE="$ROOT_DIR/$WORKER_SERVICE_NAME.service"

usage() {
  cat <<'EOF'
Usage: ./scripts/service.sh <command> [discord|worker|all]

Commands:
  check     Validate app config locally
  install   Copy service file(s) into systemd, reload, enable, and restart
  restart   Restart service(s) and show status
  status    Show service status
  logs      Tail service logs
  stop      Stop service(s)
EOF
}

require_repo_root() {
  cd "$ROOT_DIR"
}

resolve_services() {
  target="${1:-all}"
  case "$target" in
    discord)
      SERVICES=("$DISCORD_SERVICE_NAME")
      ;;
    worker)
      SERVICES=("$WORKER_SERVICE_NAME")
      ;;
    all)
      SERVICES=("$DISCORD_SERVICE_NAME" "$WORKER_SERVICE_NAME")
      ;;
    *)
      echo "Unknown service target: $target" >&2
      usage
      exit 1
      ;;
  esac
}

service_file_for() {
  service_name="$1"
  case "$service_name" in
    "$DISCORD_SERVICE_NAME") echo "$DISCORD_SERVICE_FILE" ;;
    "$WORKER_SERVICE_NAME") echo "$WORKER_SERVICE_FILE" ;;
    *)
      echo "Unknown service name: $service_name" >&2
      exit 1
      ;;
  esac
}

check() {
  require_repo_root
  "$UV_BIN" run yt-learner-discord --check-config
}

install() {
  require_repo_root
  resolve_services "${1:-all}"
  check
  sudo systemctl daemon-reload
  for service_name in "${SERVICES[@]}"; do
    service_file="$(service_file_for "$service_name")"
    sudo cp "$service_file" "/etc/systemd/system/$service_name.service"
    sudo systemctl enable "$service_name"
    sudo systemctl restart "$service_name"
    sudo systemctl status "$service_name" --no-pager
  done
}

restart() {
  resolve_services "${1:-all}"
  for service_name in "${SERVICES[@]}"; do
    sudo systemctl restart "$service_name"
    sudo systemctl status "$service_name" --no-pager
  done
}

status() {
  resolve_services "${1:-all}"
  for service_name in "${SERVICES[@]}"; do
    systemctl status "$service_name" --no-pager
  done
}

logs() {
  resolve_services "${1:-all}"
  for service_name in "${SERVICES[@]}"; do
    if [ "${#SERVICES[@]}" -gt 1 ]; then
      echo "===== $service_name ====="
      journalctl -u "$service_name" -n 40 --no-pager
    else
      journalctl -u "$service_name" -f
    fi
  done
}

stop() {
  resolve_services "${1:-all}"
  for service_name in "${SERVICES[@]}"; do
    sudo systemctl stop "$service_name"
  done
}

main() {
  command="${1:-}"
  target="${2:-all}"
  case "$command" in
    check) check ;;
    install) install "$target" ;;
    restart) restart "$target" ;;
    status) status "$target" ;;
    logs) logs "$target" ;;
    stop) stop "$target" ;;
    *) usage; exit 1 ;;
  esac
}

main "$@"
