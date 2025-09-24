# Central Scheduler (Single Instance)

Prevent multiple machines or GUI launches from spawning duplicate schedulers and run one authoritative daemon.

## Why
- Many GUI launches or users starting the scheduler can create parallel daemons.
- This wrapper + script gating ensures a single instance and provides a shared lock/PID.

## What changed
- `start_scheduler.sh` now refuses to start unless `CENTRAL_SCHEDULER=1` is set.
- New `scheduler_entry.py` acquires an exclusive file lock at `${SCRAPER_HOME:-.}/logs/scheduler.lock` and writes a PID to `${SCRAPER_HOME:-.}/logs/scheduler.pid` before executing `scheduler_daemon.py`.
- Optional shared root via `SCRAPER_HOME` lets multiple hosts coordinate on the same lock/PID and share outputs.

## One-time setup
1) Pick a shared root (network volume or local path on the central host):
   - macOS: `/Volumes/RMN`
   - Linux: `/mnt/rmn`

2) On the host that will own the scheduler, start it explicitly:
```bash
export SCRAPER_HOME=/mnt/rmn
export CENTRAL_SCHEDULER=1
./start_scheduler.sh
```

3) On GUI machines:
- Point them at the same `SCRAPER_HOME` so their schedules/outputs land in the shared root.
- Do not set `CENTRAL_SCHEDULER`. If the GUI invokes `./start_scheduler.sh`, it will refuse to start (by design).

## Status checks
- PID file: `${SCRAPER_HOME:-.}/logs/scheduler.pid`
- If a second start is attempted, lock ownership prevents a duplicate and prints "Already running (lock held)."

## Notes
- This solution is POSIX-only (`fcntl`). For Windows support later, swap to a cross‑platform file lock (e.g., `portalocker`) and update the shell wrapper accordingly.
- If you previously launched `scheduler_daemon.py` directly, use `./start_scheduler.sh` instead so the guard is enforced.
