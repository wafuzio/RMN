#!/bin/bash

# Kroger TOA Scraper - Single-Instance Scheduler Startup Script

set -euo pipefail

# Directory where this script lives (project directory)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Centralization gate: refuse to start unless CENTRAL_SCHEDULER=1
if [[ "${CENTRAL_SCHEDULER:-0}" != "1" ]]; then
  echo "Refusing to start: CENTRAL_SCHEDULER=1 is not set."
  echo "This prevents accidental starts from GUIs or non-central hosts."
  exit 0
fi

# Determine root for logs/lock (defaults to project dir)
ROOT_DIR="${SCRAPER_HOME:-$SCRIPT_DIR}"
LOGS_DIR="$ROOT_DIR/logs"
LOCK_FILE="$LOGS_DIR/scheduler.lock"
PID_FILE="$LOGS_DIR/scheduler.pid"

# Ensure logs directory exists
mkdir -p "$LOGS_DIR"

# Preflight: if a lock file already exists, hint and exit (wrapper will enforce anyway)
if [[ -f "$LOCK_FILE" ]]; then
  echo "Scheduler appears to be running (lock file present at $LOCK_FILE)."
  echo "If this is stale, remove it and try again."
  exit 1
fi

# Activate virtual environment if present
if [[ -f "$SCRIPT_DIR/.venv/bin/activate" ]]; then
  # shellcheck source=/dev/null
  source "$SCRIPT_DIR/.venv/bin/activate"
fi

echo "Starting single-instance Scheduler via wrapper..."
echo " SCRAPER_HOME = $ROOT_DIR"
echo " Logs         = $LOGS_DIR"
echo " Lock         = $LOCK_FILE"
echo " PID          = $PID_FILE"

cd "$SCRIPT_DIR"
# Use .venv Python explicitly to ensure all dependencies are available
if [[ -x "$SCRIPT_DIR/.venv/bin/python3" ]]; then
  exec "$SCRIPT_DIR/.venv/bin/python3" scheduler_entry.py
else
  echo "⚠️  .venv not found, falling back to system python3"
  exec python3 scheduler_entry.py
fi
