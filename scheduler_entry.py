#!/usr/bin/env python3
"""
Scheduler entry wrapper that enforces a single-instance scheduler using an
exclusive fcntl lock and a PID file. It then launches scheduler_daemon.py
and keeps the lock until the child exits.

Lock path and PID path live under ${SCRAPER_HOME}/logs/ (or project_root/logs).
"""
import os
import sys
import time
import atexit
import signal
import subprocess
from pathlib import Path

# fcntl is POSIX-only (macOS/Linux). This solution targets those platforms.
try:
    import fcntl  # type: ignore
except Exception as e:
    print(f"❌ fcntl not available on this platform: {e}")
    sys.exit(1)


def get_root() -> Path:
    scraper_home = os.environ.get("SCRAPER_HOME")
    if scraper_home:
        return Path(scraper_home).resolve()
    # fallback to project dir (this file's parent)
    return Path(__file__).resolve().parent


def ensure_logs_dir(root: Path) -> Path:
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    return logs


def write_pid(pid_file: Path):
    pid_file.write_text(str(os.getpid()), encoding="utf-8")


def remove_file_silent(p: Path):
    try:
        if p.exists():
            p.unlink()
    except Exception:
        pass


def acquire_lock(lock_file: Path):
    # Open lock file and acquire exclusive, non-blocking lock
    f = open(lock_file, "w")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("⚠️ Scheduler already running (lock held). Exiting.")
        f.close()
        sys.exit(2)
    return f


def main():
    root = get_root()
    logs = ensure_logs_dir(root)
    lock_path = logs / "scheduler.lock"
    pid_path = logs / "scheduler.pid"

    # Acquire single-instance lock
    lock_fp = acquire_lock(lock_path)

    # Write PID file and register cleanup
    write_pid(pid_path)

    def cleanup(*_):
        remove_file_silent(pid_path)
        try:
            fcntl.flock(lock_fp.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            lock_fp.close()
        except Exception:
            pass

    atexit.register(cleanup)
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    # Launch the actual scheduler daemon and wait
    project_dir = Path(__file__).resolve().parent
    daemon_path = project_dir / "scheduler_daemon.py"

    if not daemon_path.exists():
        print(f"❌ scheduler_daemon.py not found at {daemon_path}")
        sys.exit(1)

    print(f"✅ Single-instance lock acquired at: {lock_path}")
    print(f"📝 PID file: {pid_path}")
    print(f"🚀 Starting scheduler daemon: {daemon_path}")

    # Prefer .venv Python for all subprocesses
    venv_python = project_dir / ".venv" / "bin" / "python3"
    python_exec = str(venv_python) if venv_python.exists() else sys.executable
    cmd = [python_exec, str(daemon_path)]
    try:
        proc = subprocess.Popen(cmd, cwd=str(project_dir))
        # Wait for child to exit while holding the lock
        ret = proc.wait()
        print(f"ℹ️ Scheduler daemon exited with code {ret}")
        sys.exit(ret)
    except Exception as e:
        print(f"❌ Failed to start scheduler daemon: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
