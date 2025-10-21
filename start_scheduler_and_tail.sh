#!/usr/bin/env bash
set -euo pipefail

# ── Resolve project root ────────────────────────────────────────────────────────
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Pick Python: env override > venv > system
if [[ -n "${PYTHON_EXEC:-}" ]]; then
  PY="$PYTHON_EXEC"
elif [[ -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
else
  PY="python3"
fi

# Where output/ and logs/ live (default to project root)
SCRAPER_HOME="${SCRAPER_HOME:-$ROOT}"
LOG_DIR="$SCRAPER_HOME/logs"
DAEMON="$ROOT/scheduler_entry.py"

MAIN_LOG="$LOG_DIR/scheduler_daemon.log"
EXEC_LOG="$LOG_DIR/scheduler_execution_flow.log"

mkdir -p "$LOG_DIR"
# Ensure logs exist so tail -F never exits
: > "$MAIN_LOG"
: > "$EXEC_LOG"

# ── Show NEXT 5 scheduled runs (local time) ────────────────────────────────────
echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Next 5 Scheduled Runs (local time)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

"$PY" - <<'PY'
import os, json, glob, calendar
from datetime import datetime, timedelta, time
from pathlib import Path

root = os.environ.get("SCRAPER_HOME") or os.getcwd()
out_root = Path(root) / "output"

def parse_time_12h(t):
    # Accept "08:00" or ["8","00","AM"]
    if isinstance(t, str):
        hh, mm = t.split(":")
        return int(hh), int(mm)
    hh = int(t[0]); mm = int(t[1]); ap = t[2].strip().upper() if len(t) >= 3 else None
    if ap == "AM":
        if hh == 12: hh = 0
    elif ap == "PM":
        if hh != 12: hh += 12
    return hh, mm

def normalize_days(days):
    m = {'mon':'monday','tue':'tuesday','wed':'wednesday','thu':'thursday','thur':'thursday',
         'fri':'friday','sat':'saturday','sun':'sunday'}
    out = []
    for d in days:
        s = str(d).strip().lower()
        out.append(m.get(s[:3], s))
    return out

def next_occurrence(dayname, hh, mm):
    now = datetime.now()
    target_wd = list(calendar.day_name).index(dayname.capitalize())
    days_ahead = (target_wd - now.weekday()) % 7
    dt = datetime.combine(now.date() + timedelta(days=days_ahead), time(hh, mm))
    if dt <= now:
        dt += timedelta(days=7)
    return dt

events = []
# Scan output/<retailer>/<client>/schedule_config.json
for cfg in glob.glob(str(out_root / "*" / "*" / "schedule_config.json")):
    try:
        data = json.load(open(cfg, "r", encoding="utf-8"))
    except Exception:
        continue
    retailer = str(data.get("retailer","")).strip().lower() or "unknown"
    client = str(data.get("client","")).strip() or Path(cfg).parent.name
    # Two schemas: old {"schedule": {"monday":["08:00",...]}} vs new {"days":[],"times":[["8","00","AM"],...]}
    pairs = []
    if "schedule" in data and isinstance(data["schedule"], dict):
        for d, times in data["schedule"].items():
            for t in times:
                hh, mm = parse_time_12h(t)
                pairs.append((str(d).strip().lower(), hh, mm))
    else:
        days = normalize_days(data.get("days", []))
        times = data.get("times", [])
        for d in days:
            for t in times:
                hh, mm = parse_time_12h(t)
                pairs.append((d, hh, mm))
    for d, hh, mm in pairs:
        try:
            dt = next_occurrence(d, hh, mm)
            events.append((dt, retailer, client, f"{hh:02d}:{mm:02d}", cfg))
        except Exception:
            continue

events.sort(key=lambda x: x[0])
now = datetime.now()
if not events:
    print("No schedules found.")
else:
    print(f"Found {len(events)} future trigger(s). Showing next 5:\n")
    for dt, retailer, client, hhmm, cfg in events[:5]:
        delta = dt - now
        mins = int(delta.total_seconds() // 60)
        hours, mins = divmod(mins, 60)
        in_str = (f"{hours}h{mins:02d}m" if hours else f"{mins}m")
        when = dt.strftime("%a %Y-%m-%d %H:%M")
        print(f" • {when}  ({in_str})  [{retailer}]  {client}")
PY

echo
# ── Build commands for Terminal windows (daemon + tail) ────────────────────────
LAUNCH_CMD="cd \"$ROOT\"; export SCRAPER_HOME=\"$SCRAPER_HOME\"; if [ -f .venv/bin/activate ]; then source .venv/bin/activate; fi; \"$PY\" \"$DAEMON\""
TAIL_CMD="cd \"$ROOT\"; export SCRAPER_HOME=\"$SCRAPER_HOME\"; if [ -f .venv/bin/activate ]; then source .venv/bin/activate; fi; tail -n 200 -F \"$MAIN_LOG\" \"$EXEC_LOG\""

# Encode to avoid AppleScript quoting issues
LAUNCH_B64="$(printf %s "$LAUNCH_CMD" | base64)"
TAIL_B64="$(printf %s "$TAIL_CMD" | base64)"

# ── Open two Terminal windows: daemon + tail ──────────────────────────────────
osascript <<APPLESCRIPT
tell application "Terminal"
  activate
  do script "bash -lc \"echo $LAUNCH_B64 | base64 --decode | bash\""
  delay 0.3
  do script "bash -lc \"echo $TAIL_B64 | base64 --decode | bash\""
end tell
APPLESCRIPT

echo "Opened Terminal windows for scheduler and log tail."
echo "SCRAPER_HOME=$SCRAPER_HOME"
echo "Logs: $MAIN_LOG and $EXEC_LOG"
