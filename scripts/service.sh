#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="yt-learner-discord"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_FILE="$ROOT_DIR/yt-learner-discord.service"
SYSTEMD_FILE="/etc/systemd/system/$SERVICE_NAME.service"
UV_BIN="${UV_BIN:-/home/deepanshu/.local/bin/uv}"

usage() {
  cat <<'EOF'
Usage: ./scripts/service.sh <command>

Commands:
  check     Validate app config locally
  install   Copy the service file into systemd, reload, enable, and restart
  restart   Restart the service and show status
  status    Show service status
  logs      Tail service logs
  stop      Stop the service
EOF
}

require_repo_root() {
  cd "$ROOT_DIR"
}

check() {
  require_repo_root
  "$UV_BIN" run yt-learner-discord --check-config
}

install() {
  require_repo_root
  check
  sudo cp "$SERVICE_FILE" "$SYSTEMD_FILE"
  sudo systemctl daemon-reload
  sudo systemctl enable "$SERVICE_NAME"
  sudo systemctl restart "$SERVICE_NAME"
  sudo systemctl status "$SERVICE_NAME" --no-pager
}

restart() {
  sudo systemctl restart "$SERVICE_NAME"
  sudo systemctl status "$SERVICE_NAME" --no-pager
}

status() {
  systemctl status "$SERVICE_NAME" --no-pager
}

logs() {
  journalctl -u "$SERVICE_NAME" -f
}

stop() {
  sudo systemctl stop "$SERVICE_NAME"
}

main() {
  command="${1:-}"
  case "$command" in
    check) check ;;
    install) install ;;
    restart) restart ;;
    status) status ;;
    logs) logs ;;
    stop) stop ;;
    *) usage; exit 1 ;;
  esac
}

main "$@"
