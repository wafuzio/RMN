#!/usr/bin/env python3
"""
Scrape Monitor — checks scheduled vs. actual scrape coverage.

Usage:
    python3 tools/scrape_monitor.py                     # report for today
    python3 tools/scrape_monitor.py --days 7            # report for past 7 days
    python3 tools/scrape_monitor.py --date 2026-03-01   # specific date
    python3 tools/scrape_monitor.py --json              # machine-readable output
    python3 tools/scrape_monitor.py --fix-locks         # remove stale lock files

Outputs a table of expected vs. completed scrapes per retailer/client/date,
highlighting any missed windows.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# --- project root ---
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schedules.schedules_lib import scan_schedules, Schedule

SCRAPER_HOME = Path(os.environ.get("SCRAPER_HOME", str(ROOT)))
OUTPUT_DIR = SCRAPER_HOME / "output"
LOGS_DIR = SCRAPER_HOME / "logs"


# ---------------------------------------------------------------------------
# Run discovery helpers
# ---------------------------------------------------------------------------

def _run_dirs_for(retailer: str, client_dir: str) -> List[Path]:
    """Return all timestamped run directories for a retailer/client, newest first."""
    base = Path(client_dir)
    if not base.exists():
        return []
    dirs = sorted(
        [d for d in base.iterdir() if d.is_dir() and d.name.isdigit() and len(d.name) == 14],
        reverse=True,
    )
    return dirs


def _run_dirs_for_date(retailer: str, client_dir: str, date_str: str) -> List[Path]:
    """Return run dirs whose timestamp matches the given YYYY-MM-DD date."""
    compact = date_str.replace("-", "")  # 20260302
    return [d for d in _run_dirs_for(retailer, client_dir) if d.name.startswith(compact)]


def _amazon_runs_for_date(client_dir: str, date_str: str) -> List[Dict]:
    """Amazon stores runs under output/amazon/<client>/runs/ as JSON files."""
    runs_dir = Path(client_dir) / "runs"
    if not runs_dir.exists():
        return []
    compact = date_str.replace("-", "")
    results = []
    for f in runs_dir.glob("*.json"):
        if compact in f.name:
            try:
                data = json.loads(f.read_text())
                results.append({"file": f, "keyword": data.get("keyword"), "timestamp": data.get("timestamp"), "retailer": "amazon"})
            except Exception:
                pass
    return results


def _instacart_runs_for_date(client_dir: str, date_str: str) -> List[Dict]:
    """Instacart stores runs as JSON files directly under the client dir."""
    base = Path(client_dir)
    if not base.exists():
        return []
    compact = date_str.replace("-", "")
    results = []
    for f in base.glob("*.json"):
        if compact in f.name or compact in f.stem:
            try:
                data = json.loads(f.read_text())
                if data.get("timestamp"):
                    results.append({"file": f, "keyword": data.get("keyword"), "timestamp": data.get("timestamp"), "retailer": "instacart"})
            except Exception:
                pass
    # Also scan timestamped subdirs
    for d in base.iterdir():
        if d.is_dir() and d.name.startswith(compact):
            for f in d.glob("*.json"):
                try:
                    data = json.loads(f.read_text())
                    if data.get("timestamp"):
                        results.append({"file": f, "keyword": data.get("keyword"), "timestamp": data.get("timestamp"), "retailer": "instacart"})
                except Exception:
                    pass
    return results


def _walmart_kroger_target_runs_for_date(retailer: str, client_dir: str, date_str: str) -> List[Dict]:
    """Walmart/Kroger/Target store runs in timestamped dirs with run_report.json."""
    results = []
    for d in _run_dirs_for_date(retailer, client_dir, date_str):
        rr = d / "run_report.json"
        if rr.exists():
            try:
                data = json.loads(rr.read_text())
                results.append({
                    "dir": d,
                    "keyword": data.get("keyword"),
                    "timestamp": data.get("started_at"),
                    "outcome": data.get("outcome"),
                    "retailer": retailer,
                })
            except Exception:
                pass
        else:
            # Count the dir itself as a run attempt
            results.append({
                "dir": d,
                "keyword": None,
                "timestamp": _dir_to_iso(d.name),
                "outcome": "unknown",
                "retailer": retailer,
            })
    return results


def _dir_to_iso(dirname: str) -> str:
    """Convert 14-digit dirname YYYYMMDDHHMMSS → ISO timestamp."""
    try:
        return datetime.strptime(dirname, "%Y%m%d%H%M%S").isoformat()
    except Exception:
        return dirname


def get_runs_for_date(schedule: Schedule, date_str: str) -> List[Dict]:
    """Return all run records for a given schedule on a given date."""
    retailer = schedule.retailer
    client_dir = _resolve_client_dir(retailer, schedule.client)
    if not client_dir:
        return []  # no output dir found for this schedule

    if retailer == "amazon":
        return _amazon_runs_for_date(client_dir, date_str)
    elif retailer == "instacart":
        runs = _instacart_runs_for_date(client_dir, date_str)
        if not runs:
            runs = _walmart_kroger_target_runs_for_date(retailer, client_dir, date_str)
        return runs
    else:
        return _walmart_kroger_target_runs_for_date(retailer, client_dir, date_str)


def _slug(s: str) -> str:
    s = s.strip().lower().replace(" ", "_")
    return "".join(ch if (ch.isalnum() or ch in "-_") else "_" for ch in s)


# Cache for resolved client dirs to avoid repeated filesystem scans
_client_dir_cache: Dict[str, Optional[str]] = {}


def _resolve_client_dir(retailer: str, client_name: str) -> Optional[str]:
    """
    Resolve the actual output directory for a retailer/client, handling
    case differences between schedule slugs and scraper-created dir names.
    e.g. schedule client='Community Coffee' → dir 'Community_Coffee' or 'community_coffee'
    """
    cache_key = f"{retailer}:{client_name}"
    if cache_key in _client_dir_cache:
        return _client_dir_cache[cache_key]

    base = OUTPUT_DIR / retailer
    if not base.exists():
        _client_dir_cache[cache_key] = None
        return None

    # Build a lower-slug → actual-name map for all dirs
    dir_map = {
        _slug(d.name): d.name
        for d in base.iterdir() if d.is_dir()
    }

    slug_key = _slug(client_name)
    actual = dir_map.get(slug_key)
    result = str(base / actual) if actual else None
    _client_dir_cache[cache_key] = result
    return result


# ---------------------------------------------------------------------------
# Expected-run calculation
# ---------------------------------------------------------------------------

def expected_slots_for_date(schedule: Schedule, date_str: str) -> List[str]:
    """
    Return list of expected HH:MM slots for the schedule on the given date.
    For today, only returns slots whose time has already passed (+ grace period).
    Returns [] if the schedule is not active that day.
    """
    if not schedule.enabled:
        return []
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return []
    day_name = dt.strftime("%A").lower()
    if day_name not in schedule.days:
        return []

    today_str = datetime.now().strftime("%Y-%m-%d")
    if date_str == today_str:
        # Only count slots that have already passed (with 30-min grace period)
        now_min = datetime.now().hour * 60 + datetime.now().minute
        grace = 30  # minutes after scheduled slot before calling it missed
        passed = [t for t in schedule.times
                  if (int(t.split(":")[0]) * 60 + int(t.split(":")[1])) + grace <= now_min]
        return passed

    return list(schedule.times)


# ---------------------------------------------------------------------------
# Coverage analysis
# ---------------------------------------------------------------------------

def analyze_coverage(schedules: List[Schedule], dates: List[str]) -> List[Dict]:
    """
    For each (schedule, date), compare expected slots vs actual runs.
    Returns list of result dicts.
    """
    results = []
    for s in schedules:
        for date_str in dates:
            slots = expected_slots_for_date(s, date_str)
            if not slots:
                continue  # not scheduled that day

            runs = get_runs_for_date(s, date_str)
            n_keywords = len(s.keywords)
            n_runs = len(runs)

            # Determine status
            if n_runs == 0:
                status = "MISSED"
            elif n_runs < n_keywords * len(slots):
                status = "PARTIAL"
            else:
                status = "OK"

            # Check for failures in runs
            failures = [r for r in runs if r.get("outcome") not in (None, "success", "ok", "unknown")]

            results.append({
                "retailer": s.retailer,
                "client": s.client,
                "date": date_str,
                "expected_slots": slots,
                "expected_runs": n_keywords * len(slots),
                "actual_runs": n_runs,
                "status": status,
                "failures": len(failures),
                "keywords": s.keywords,
                "schedule_id": s.id,
                "source": s.source_path,
            })
    return results


# ---------------------------------------------------------------------------
# Lock file audit
# ---------------------------------------------------------------------------

def find_stale_locks(max_age_sec: int = 3600) -> List[Dict]:
    """Find lock files older than max_age_sec seconds."""
    stale = []
    now = time.time()
    for lock in OUTPUT_DIR.rglob("*/locks/run.lock"):
        age = now - lock.stat().st_mtime
        if age > max_age_sec:
            stale.append({
                "path": str(lock),
                "age_hours": round(age / 3600, 1),
                "retailer": lock.parts[-4] if len(lock.parts) >= 4 else "?",
                "client": lock.parts[-3] if len(lock.parts) >= 3 else "?",
            })
    return stale


def remove_stale_locks(max_age_sec: int = 3600) -> int:
    """Remove stale lock files. Returns count removed."""
    locks = find_stale_locks(max_age_sec)
    removed = 0
    for l in locks:
        try:
            Path(l["path"]).unlink()
            print(f"  Removed stale lock: {l['path']} (age {l['age_hours']}h)")
            removed += 1
        except Exception as e:
            print(f"  Failed to remove {l['path']}: {e}")
    return removed


# ---------------------------------------------------------------------------
# Log analysis helpers
# ---------------------------------------------------------------------------

def parse_scheduler_log(since: Optional[datetime] = None) -> Dict:
    """Parse scheduler_daemon.log for success/fail/timeout counts per retailer."""
    log_path = LOGS_DIR / "scheduler_daemon.log"
    if not log_path.exists():
        return {}

    stats: Dict[str, Dict[str, int]] = {}
    cutoff = since.isoformat()[:19] if since else "0000"

    with open(log_path, "r", errors="replace") as f:
        for line in f:
            ts = line[:19]
            if ts < cutoff:
                continue
            if "SUCCESS keyword" in line:
                retailer = _extract_retailer(line)
                _bump(stats, retailer, "success")
            elif "FAIL keyword" in line or "FAILED keyword" in line:
                retailer = _extract_retailer(line)
                _bump(stats, retailer, "fail")
            elif "TIMEOUT keyword" in line:
                retailer = _extract_retailer(line)
                _bump(stats, retailer, "timeout")
            elif "Unsupported retailer" in line:
                retailer = _extract_retailer(line)
                _bump(stats, retailer, "unsupported")
            elif "Job budget" in line and "exceeded" in line:
                retailer = _extract_retailer(line)
                _bump(stats, retailer, "budget_exceeded")
            elif "Concurrency cap reached" in line:
                _bump(stats, "global", "concurrency_cap")

    return stats


def _extract_retailer(line: str) -> str:
    import re
    m = re.search(r"\[(\w+)\]", line)
    return m.group(1).lower() if m else "unknown"


def _bump(d: Dict, key: str, sub: str):
    d.setdefault(key, {}).setdefault(sub, 0)
    d[key][sub] += 1


# ---------------------------------------------------------------------------
# Profile health check
# ---------------------------------------------------------------------------

_CHROME_PROFILES = Path.home() / "ChromeProfiles"

PROFILE_ENV_MAP = {
    "amazon": ["AMAZON_PROFILE_DIR", "AMZ_PROFILE_DIR"],
    "instacart": ["INSTACART_PROFILE_DIR"],
    "kroger": [],  # kroger scraper hardcodes ~/ChromeProfiles/kroger_clean_profile
    "walmart": ["WALMART_PROFILE_DIR"],
    "target": ["TARGET_PROFILE_DIR"],
}

PROFILE_FALLBACK = {
    "amazon": _CHROME_PROFILES / "amazon",
    "instacart": _CHROME_PROFILES / "instacart",
    "kroger": _CHROME_PROFILES / "kroger_clean_profile",
    "walmart": _CHROME_PROFILES / "walmart",
    "target": ROOT / "profiles" / "target",
}

POISONED_PROFILE_MARKERS = [
    "corrupted",
    ".corrupted",
    "CAPTCHA",
    "captcha",
    "blocked",
]

PROFILE_REQUIRED_PATHS = {
    "default": ["Default/Cookies", "Default/Login Data"],
}

PROFILE_MAX_AGE_DAYS = 90  # Flag if Default/Cookies not modified in this many days


def check_profile_health() -> List[Dict]:
    """
    Check all retailer browser profiles for:
    - Existence
    - Poisoned/corrupted markers
    - Cookie freshness
    Returns list of status dicts.
    """
    results = []
    for retailer, env_vars in PROFILE_ENV_MAP.items():
        # Resolve profile path
        profile_dir = None
        for ev in env_vars:
            v = os.environ.get(ev)
            if v:
                profile_dir = Path(v)
                break
        if profile_dir is None:
            profile_dir = PROFILE_FALLBACK[retailer]

        status = {
            "retailer": retailer,
            "profile_dir": str(profile_dir),
            "exists": profile_dir.exists(),
            "poisoned": False,
            "poison_reason": "",
            "cookies_exist": False,
            "cookies_age_days": None,
            "login_data_exists": False,
            "overall": "UNKNOWN",
            "notes": [],
        }

        if not profile_dir.exists():
            status["overall"] = "MISSING"
            status["notes"].append(f"Profile directory not found: {profile_dir}")
            results.append(status)
            continue

        # Check for poisoned/corrupted markers in profile dir name or parent
        dir_str = str(profile_dir).lower()
        for marker in POISONED_PROFILE_MARKERS:
            if marker.lower() in dir_str:
                status["poisoned"] = True
                status["poison_reason"] = f"Marker '{marker}' in path"
                status["notes"].append(f"POISONED: path contains '{marker}'")
                break

        # Check for corrupted sibling dirs (e.g. target.corrupted.*)
        parent = profile_dir.parent
        poisoned_siblings = [
            d for d in parent.iterdir()
            if d.is_dir() and any(m.lower() in d.name.lower() for m in POISONED_PROFILE_MARKERS)
        ]
        if poisoned_siblings:
            status["notes"].append(f"Poisoned backups found: {[d.name for d in poisoned_siblings]}")

        # Check Cookies file
        cookies_path = profile_dir / "Default" / "Cookies"
        if cookies_path.exists():
            status["cookies_exist"] = True
            age = (time.time() - cookies_path.stat().st_mtime) / 86400
            status["cookies_age_days"] = round(age, 1)
            if age > PROFILE_MAX_AGE_DAYS:
                status["notes"].append(f"Cookies stale: {round(age)} days old (>{PROFILE_MAX_AGE_DAYS}d)")
        else:
            status["notes"].append("Default/Cookies missing — profile may not be logged in")

        # Check Login Data
        login_path = profile_dir / "Default" / "Login Data"
        status["login_data_exists"] = login_path.exists()
        if not login_path.exists():
            status["notes"].append("Default/Login Data missing")

        # Overall health
        if status["poisoned"]:
            status["overall"] = "POISONED"
        elif not status["cookies_exist"]:
            status["overall"] = "NOT_LOGGED_IN"
        elif status["cookies_age_days"] and status["cookies_age_days"] > PROFILE_MAX_AGE_DAYS:
            status["overall"] = "STALE"
        elif status["notes"]:
            status["overall"] = "WARN"
        else:
            status["overall"] = "OK"

        results.append(status)

    return results


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

STATUS_COLORS = {
    "OK": "\033[32m",      # green
    "PARTIAL": "\033[33m", # yellow
    "MISSED": "\033[31m",  # red
    "POISONED": "\033[31m",
    "NOT_LOGGED_IN": "\033[31m",
    "STALE": "\033[33m",
    "WARN": "\033[33m",
    "MISSING": "\033[31m",
    "UNKNOWN": "\033[90m",
}
RESET = "\033[0m"


def _colored(text: str, status: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"{STATUS_COLORS.get(status, '')}{text}{RESET}"


def print_coverage_report(results: List[Dict], show_ok: bool = False):
    missed = [r for r in results if r["status"] == "MISSED"]
    partial = [r for r in results if r["status"] == "PARTIAL"]
    ok = [r for r in results if r["status"] == "OK"]

    total = len(results)
    print(f"\n{'='*70}")
    print(f"  SCRAPE COVERAGE REPORT  |  {total} schedule-days evaluated")
    print(f"{'='*70}")
    print(f"  {_colored(f'OK:      {len(ok)}/{total}', 'OK')}")
    print(f"  {_colored(f'PARTIAL: {len(partial)}/{total}', 'PARTIAL')}")
    print(f"  {_colored(f'MISSED:  {len(missed)}/{total}', 'MISSED')}")
    print()

    # Group by date
    from collections import defaultdict
    by_date: Dict[str, List[Dict]] = defaultdict(list)
    for r in results:
        if r["status"] != "OK" or show_ok:
            by_date[r["date"]].append(r)

    for date_str in sorted(by_date.keys()):
        rows = by_date[date_str]
        if not rows:
            continue
        print(f"  Date: {date_str}")
        print(f"  {'Retailer':<12} {'Client':<22} {'Status':<10} {'Runs':<10} {'Expected':<10} {'Slots'}")
        print(f"  {'-'*80}")
        for r in sorted(rows, key=lambda x: (x["status"], x["retailer"], x["client"])):
            slots_str = ", ".join(r["expected_slots"])
            runs_str = f"{r['actual_runs']}/{r['expected_runs']}"
            status_disp = _colored(r["status"], r["status"])
            failures_note = f"  ({r['failures']} failure(s))" if r["failures"] else ""
            print(f"  {r['retailer']:<12} {r['client'][:22]:<22} {status_disp:<20} {runs_str:<10} {r['expected_runs']:<10} {slots_str}{failures_note}")
        print()


def print_log_stats(stats: Dict, since: Optional[datetime] = None):
    since_str = since.strftime("%Y-%m-%d %H:%M") if since else "all time"
    print(f"\n{'='*70}")
    print(f"  SCHEDULER LOG STATS  (since {since_str})")
    print(f"{'='*70}")
    if not stats:
        print("  No data found.")
        return
    for retailer in sorted(stats.keys()):
        s = stats[retailer]
        ok = s.get("success", 0)
        fail = s.get("fail", 0) + s.get("timeout", 0)
        total_kw = ok + fail
        rate = f"{ok}/{total_kw}" if total_kw else "0/0"
        extras = []
        if s.get("unsupported"):
            extras.append(_colored(f"unsupported={s['unsupported']}", "MISSED"))
        if s.get("budget_exceeded"):
            extras.append(_colored(f"budget_exceeded={s['budget_exceeded']}", "PARTIAL"))
        if s.get("concurrency_cap"):
            extras.append(f"concurrency_cap={s['concurrency_cap']}")
        extras_str = "  " + "  ".join(extras) if extras else ""
        status = "OK" if fail == 0 and ok > 0 else ("PARTIAL" if fail > 0 else "MISSED")
        print(f"  {retailer:<12}  success={_colored(str(ok), 'OK')}  fail/timeout={_colored(str(fail), 'MISSED' if fail > 0 else 'OK')}  ({rate} keywords){extras_str}")
    print()


def print_profile_report(health: List[Dict]):
    print(f"\n{'='*70}")
    print(f"  PROFILE HEALTH CHECK")
    print(f"{'='*70}")
    for h in health:
        status = h["overall"]
        print(f"  {h['retailer']:<12}  [{_colored(status, status)}]  {h['profile_dir']}")
        for note in h["notes"]:
            print(f"               ↳ {note}")
    print()


def print_stale_locks(locks: List[Dict]):
    if not locks:
        print("\n  No stale lock files found.")
        return
    print(f"\n{'='*70}")
    print(f"  STALE LOCK FILES ({len(locks)} found)")
    print(f"{'='*70}")
    for l in locks:
        print(f"  {_colored(l['path'], 'MISSED')}  (age: {l['age_hours']}h)")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Scrape coverage monitor and health checker")
    ap.add_argument("--days", type=int, default=1, help="Number of past days to analyze (default: 1 = today)")
    ap.add_argument("--date", help="Specific date to analyze (YYYY-MM-DD)")
    ap.add_argument("--retailer", help="Filter to a specific retailer")
    ap.add_argument("--client", help="Filter to a specific client")
    ap.add_argument("--show-ok", action="store_true", help="Also show OK schedules in coverage report")
    ap.add_argument("--json", action="store_true", dest="json_out", help="Output JSON instead of human-readable")
    ap.add_argument("--fix-locks", action="store_true", help="Remove stale lock files and exit")
    ap.add_argument("--profiles-only", action="store_true", help="Only run profile health check")
    ap.add_argument("--coverage-only", action="store_true", help="Only run coverage check")
    ap.add_argument("--lock-max-age-hours", type=float, default=1.0, help="Max age for lock files in hours (default: 1.0)")
    args = ap.parse_args()

    # Fix stale locks mode
    if args.fix_locks:
        max_age = int(args.lock_max_age_hours * 3600)
        locks = find_stale_locks(max_age)
        if not locks:
            print("No stale locks found.")
        else:
            print(f"Found {len(locks)} stale lock(s):")
            removed = remove_stale_locks(max_age)
            print(f"Removed {removed} lock(s).")
        return

    # Load all schedules
    schedules = scan_schedules(SCRAPER_HOME)

    # Apply filters
    if args.retailer:
        schedules = [s for s in schedules if s.retailer == args.retailer.lower()]
    if args.client:
        schedules = [s for s in schedules if args.client.lower() in s.client.lower()]

    # Build date list
    if args.date:
        dates = [args.date]
    else:
        today = datetime.now().date()
        dates = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(args.days - 1, -1, -1)]

    # Profile health
    profile_health = check_profile_health()

    # Stale locks
    lock_max_age = int(args.lock_max_age_hours * 3600)
    stale_locks = find_stale_locks(lock_max_age)

    # Log stats for the window
    since_dt = datetime.now() - timedelta(days=args.days)
    log_stats = parse_scheduler_log(since=since_dt)

    if not args.profiles_only:
        # Coverage analysis
        coverage = analyze_coverage(schedules, dates)

    if args.json_out:
        out = {
            "generated_at": datetime.now().isoformat(),
            "dates": dates,
            "coverage": coverage if not args.profiles_only else [],
            "profile_health": profile_health,
            "stale_locks": stale_locks,
            "log_stats": log_stats,
        }
        print(json.dumps(out, indent=2, default=str))
        return

    print(f"\n  Retail Ad Monitor — Scrape Health Check")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Checking: {len(schedules)} schedule(s)  |  Dates: {', '.join(dates)}")

    # Profile report (always shown)
    print_profile_report(profile_health)

    # Stale locks
    if stale_locks:
        print_stale_locks(stale_locks)
        print(f"  Run with --fix-locks to remove stale lock files.\n")

    if not args.profiles_only:
        # Log stats
        print_log_stats(log_stats, since=since_dt)

        # Coverage
        print_coverage_report(coverage, show_ok=args.show_ok)

        # Summary of issues
        missed = [r for r in coverage if r["status"] == "MISSED"]
        partial = [r for r in coverage if r["status"] == "PARTIAL"]
        profile_issues = [h for h in profile_health if h["overall"] not in ("OK",)]

        if missed or partial or profile_issues or stale_locks:
            print("  ACTION ITEMS:")
            for h in profile_issues:
                print(f"    [PROFILE] {h['retailer']}: {h['overall']} — {'; '.join(h['notes'])}")
            for r in missed:
                print(f"    [MISSED]  {r['retailer']}/{r['client']} on {r['date']} (slots: {', '.join(r['expected_slots'])})")
            for r in partial:
                print(f"    [PARTIAL] {r['retailer']}/{r['client']} on {r['date']} — {r['actual_runs']}/{r['expected_runs']} runs")
            if stale_locks:
                print(f"    [LOCKS]   {len(stale_locks)} stale lock file(s) — run: python3 tools/scrape_monitor.py --fix-locks")
            print()
        else:
            print(f"  {_colored('All clear — no issues found.', 'OK')}\n")


if __name__ == "__main__":
    main()
