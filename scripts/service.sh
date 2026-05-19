#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UV_BIN="${UV_BIN:-/home/deepanshu/.local/bin/uv}"
DISCORD_SERVICE_NAME="yt-learner-discord"
WORKER_SERVICE_NAME="yt-learner-worker"
SCHEDULER_TARGET_NAME="yt-learner-scheduler"
DISCORD_SERVICE_FILE="$ROOT_DIR/$DISCORD_SERVICE_NAME.service"
WORKER_SERVICE_FILE="$ROOT_DIR/$WORKER_SERVICE_NAME.service"
SCHEDULER_LOG_FILE="$ROOT_DIR/data/yt-learner-scheduler.log"
CRON_TIMEZONE="${YT_LEARNER_SCHEDULER_TIMEZONE:-Asia/Bangkok}"
CRON_SCHEDULE="${YT_LEARNER_SCHEDULER_CRON:-0 8 * * *}"
CRON_COMMAND="cd $ROOT_DIR && $UV_BIN run yt-learner-scheduler >> $SCHEDULER_LOG_FILE 2>&1"
CRON_ENTRY="CRON_TZ=$CRON_TIMEZONE $CRON_SCHEDULE $CRON_COMMAND"

usage() {
  cat <<'EOF'
Usage: ./scripts/service.sh <command> [discord|worker|scheduler|all]

Commands:
  check     Validate app config locally
  install   Install systemd service(s) or scheduler cron, then show status
  restart   Restart systemd service(s) or refresh scheduler cron, then show status
  status    Show service status or installed scheduler cron entry
  logs      Tail service logs or scheduler log file
  stop      Stop systemd service(s) or remove scheduler cron entry
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
    scheduler)
      SERVICES=("$SCHEDULER_TARGET_NAME")
      ;;
    all)
      SERVICES=("$DISCORD_SERVICE_NAME" "$WORKER_SERVICE_NAME" "$SCHEDULER_TARGET_NAME")
      ;;
    *)
      echo "Unknown service target: $target" >&2
      usage
      exit 1
      ;;
  esac
}

ensure_scheduler_log_dir() {
  mkdir -p "$(dirname "$SCHEDULER_LOG_FILE")"
}

install_scheduler_cron() {
  ensure_scheduler_log_dir
  current_crontab="$(crontab -l 2>/dev/null || true)"
  filtered_crontab="$(printf '%s\n' "$current_crontab" | grep -F -v "$UV_BIN run yt-learner-scheduler" || true)"
  if [ -n "$filtered_crontab" ]; then
    printf '%s\n%s\n' "$filtered_crontab" "$CRON_ENTRY" | crontab -
  else
    printf '%s\n' "$CRON_ENTRY" | crontab -
  fi
}

remove_scheduler_cron() {
  current_crontab="$(crontab -l 2>/dev/null || true)"
  filtered_crontab="$(printf '%s\n' "$current_crontab" | grep -F -v "$UV_BIN run yt-learner-scheduler" || true)"
  if [ -n "$filtered_crontab" ]; then
    printf '%s\n' "$filtered_crontab" | crontab -
  else
    crontab -r 2>/dev/null || true
  fi
}

show_scheduler_status() {
  current_crontab="$(crontab -l 2>/dev/null || true)"
  matched_entry="$(printf '%s\n' "$current_crontab" | grep -F "$UV_BIN run yt-learner-scheduler" || true)"
  if [ -n "$matched_entry" ]; then
    echo "scheduler cron installed:"
    printf '%s\n' "$matched_entry"
    echo "scheduler log file: $SCHEDULER_LOG_FILE"
  else
    echo "scheduler cron not installed"
  fi
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
    if [ "$service_name" = "$SCHEDULER_TARGET_NAME" ]; then
      install_scheduler_cron
      show_scheduler_status
      continue
    fi
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
    if [ "$service_name" = "$SCHEDULER_TARGET_NAME" ]; then
      install_scheduler_cron
      show_scheduler_status
      continue
    fi
    sudo systemctl restart "$service_name"
    sudo systemctl status "$service_name" --no-pager
  done
}

status() {
  resolve_services "${1:-all}"
  for service_name in "${SERVICES[@]}"; do
    if [ "$service_name" = "$SCHEDULER_TARGET_NAME" ]; then
      show_scheduler_status
      continue
    fi
    systemctl status "$service_name" --no-pager
  done
}

logs() {
  resolve_services "${1:-all}"
  for service_name in "${SERVICES[@]}"; do
    if [ "$service_name" = "$SCHEDULER_TARGET_NAME" ]; then
      ensure_scheduler_log_dir
      if [ "${#SERVICES[@]}" -gt 1 ]; then
        echo "===== $service_name ====="
        tail -n 40 "$SCHEDULER_LOG_FILE" 2>/dev/null || true
      else
        touch "$SCHEDULER_LOG_FILE"
        tail -f "$SCHEDULER_LOG_FILE"
      fi
      continue
    fi
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
    if [ "$service_name" = "$SCHEDULER_TARGET_NAME" ]; then
      remove_scheduler_cron
      continue
    fi
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
