#!/usr/bin/env python3
"""
Scheduler entry wrapper that enforces a single running instance and supports
centralized operation via SCRAPER_HOME.

- Acquires an exclusive non-blocking fcntl file lock at {SCRAPER_HOME|.}/logs/scheduler.lock
- Writes PID to {SCRAPER_HOME|.}/logs/scheduler.pid
- Executes the existing scheduler_daemon.py as __main__

This avoids invasive changes to scheduler_daemon.py while reliably preventing
accidental duplicate daemons from GUI launches or multiple hosts.
"""
import atexit
import os
import sys
import fcntl
from pathlib import Path

ROOT = Path(os.getenv("SCRAPER_HOME") or Path(__file__).parent.resolve())
LOGS = ROOT / "logs"
LOGS.mkdir(parents=True, exist_ok=True)
LOCK_PATH = LOGS / "scheduler.lock"
PID_PATH = LOGS / "scheduler.pid"

# Acquire exclusive, non-blocking lock
_lock_f = open(LOCK_PATH, "w")
try:
    fcntl.flock(_lock_f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    print("[scheduler] Already running (lock held). Exiting.")
    sys.exit(0)

# Write PID for status tooling/GUI
PID_PATH.write_text(str(os.getpid()))

@atexit.register
def _release_lock_and_cleanup():
    try:
        fcntl.flock(_lock_f.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass
    try:
        _lock_f.close()
    except Exception:
        pass
    try:
        if PID_PATH.exists():
            PID_PATH.unlink()
    except Exception:
        pass

# Execute the original daemon under this guarded process context
DAEMON_FILE = Path(__file__).parent / "scheduler_daemon.py"
if not DAEMON_FILE.exists():
    print(f"[scheduler] scheduler_daemon.py not found at {DAEMON_FILE}")
    sys.exit(1)

code = compile(DAEMON_FILE.read_text(), str(DAEMON_FILE), "exec")
# Run as if invoked as a script
__name__ = "__main__"
exec_globals = {"__name__": "__main__", "__file__": str(DAEMON_FILE)}
exec(code, exec_globals)
