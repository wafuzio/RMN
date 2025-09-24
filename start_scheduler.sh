#!/usr/bin/env bash
set -euo pipefail

# Single central scheduler guard:
# By default, refuse to start from GUI or ad-hoc shells to prevent
# many machines spawning their own daemons. Explicitly opt-in by
# setting CENTRAL_SCHEDULER=1 on the host that should own the daemon.
if [[ "${CENTRAL_SCHEDULER:-0}" != "1" ]]; then
  echo "[scheduler] Refusing to start: CENTRAL_SCHEDULER=1 not set."
  echo "[scheduler] Start the single central scheduler with:"
  echo "[scheduler]   CENTRAL_SCHEDULER=1 SCRAPER_HOME=/shared/path ./start_scheduler.sh"
  exit 0
fi

# Optional: preflight lock check to provide fast feedback before launching Python.
LOCK_ROOT="${SCRAPER_HOME:-.}"
LOCK_DIR="${LOCK_ROOT%/}/logs"
mkdir -p "$LOCK_DIR"
LOCK_FILE="$LOCK_DIR/scheduler.lock"

python - <<'PY' "$LOCK_FILE"
import sys, fcntl
path = sys.argv[1]
with open(path, 'w') as f:
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Immediately release; the real lock is acquired in scheduler_entry.py
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except BlockingIOError:
        print("[scheduler] Already running (lock held).")
        sys.exit(1)
PY

# Launch via an entry wrapper that acquires a robust lock and writes a PID file
# before executing the existing scheduler_daemon.py.
python scheduler_entry.py
