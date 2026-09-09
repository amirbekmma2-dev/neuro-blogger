#!/bin/bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE="neuro-blogger"
PID_FILE="$DIR/.pid"
LOG="$DIR/logs/bot.log"
PY="$DIR/.venv/bin/python"
# Облако 24/7: Render webhook. Локальный start конфликтует с webhook — не гоняй оба.

start_bg() {
  mkdir -p "$DIR/logs"
  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "already running pid $(cat "$PID_FILE")"
    return
  fi
  cd "$DIR"
  nohup "$PY" bot.py >>"$LOG" 2>&1 &
  echo $! >"$PID_FILE"
  echo "started pid $(cat "$PID_FILE")"
}

stop_bg() {
  if [[ -f "$PID_FILE" ]]; then
    kill "$(cat "$PID_FILE")" 2>/dev/null || true
    rm -f "$PID_FILE"
  fi
  pkill -f "$DIR/bot.py" 2>/dev/null || true
  echo "stopped"
}

case "${1:-}" in
  start)
    if command -v systemctl >/dev/null && sudo -n true 2>/dev/null; then
      sudo cp "$DIR/neuro-blogger.service" /etc/systemd/system/
      sudo systemctl daemon-reload
      sudo systemctl start "$SERVICE"
      echo "systemd started"
    else
      start_bg
    fi
    ;;
  stop)
    sudo systemctl stop "$SERVICE" 2>/dev/null || true
    stop_bg
    ;;
  restart)
    "$0" stop
    sleep 1
    "$0" start
    ;;
  status)
    if command -v systemctl >/dev/null; then
      sudo systemctl status "$SERVICE" --no-pager || true
    fi
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "pid $(cat "$PID_FILE") alive"
    else
      echo "not running (nohup)"
    fi
    ;;
  logs)
    tail -n 80 "$LOG"
    ;;
  *)
    echo "usage: $0 start|stop|restart|status|logs"
    exit 1
    ;;
esac
