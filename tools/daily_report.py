#!/usr/bin/env python3
"""
daily_report.py — Generate a daily summary of scraper runs.

For a given date (default: yesterday) prints:

  OVERVIEW
    Total runs: successful / failed
    Per-retailer: runs + ad-type breakdown

  DETAIL
    Each schedule: times it was due vs times a run JSON was produced

Usage:
    python3 tools/daily_report.py                    # yesterday
    python3 tools/daily_report.py --date 2026-03-01  # specific date
    python3 tools/daily_report.py --html             # HTML output
    python3 tools/daily_report.py --out report.html  # write to file
"""

import argparse
import glob
import json
import os
import re
import smtplib
import sys
from collections import defaultdict, Counter
from datetime import date, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# Project root is one level up from this file
ROOT = Path(__file__).resolve().parent.parent
SCHEDULES_DIR = ROOT / "schedules"
OUTPUT_DIR    = ROOT / "output"
LOGS_DIR      = ROOT / "logs"

RETAILERS = ["amazon", "walmart", "target", "instacart", "kroger"]

# ── Helpers ────────────────────────────────────────────────────────────────

def _ts_to_dt(ts: str) -> datetime | None:
    """Parse ISO timestamp from run JSON to datetime."""
    if not ts:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S", "%Y%m%d%H%M%S"):
        try:
            return datetime.strptime(ts.rstrip("Z"), fmt.rstrip("Z"))
        except ValueError:
            pass
    return None


def _run_id_to_dt(run_id: str) -> datetime | None:
    """Extract datetime from run_id / filename timestamp (14-digit or with underscores)."""
    m = re.search(r'(\d{14})', run_id)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y%m%d%H%M%S")
        except ValueError:
            pass
    # YYYY-MM-DD_HH-MM-SS in filename
    m2 = re.search(r'(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})', run_id)
    if m2:
        try:
            return datetime.strptime(m2.group(1), "%Y-%m-%d_%H-%M-%S")
        except ValueError:
            pass
    return None


def _run_dt(data: dict, filename: str) -> datetime | None:
    """Best-effort datetime for a run JSON."""
    ts = data.get("timestamp") or data.get("run_id") or ""
    dt = _ts_to_dt(ts)
    if dt:
        return dt
    return _run_id_to_dt(filename)


def _is_success(data: dict) -> bool:
    """Heuristic: a run has content if it has any ads OR any slots."""
    return bool(data.get("ads") or data.get("slots"))


def _ad_type_counts(data: dict) -> Counter:
    """Count ad_type occurrences across slots[] (preferred) or ads[]."""
    slots = data.get("slots") or []
    if slots:
        return Counter(s.get("ad_type", "Unknown") for s in slots)
    ads = data.get("ads") or []
    return Counter(a.get("type") or a.get("ad_type", "Unknown") for a in ads)


# ── Schedule loading ───────────────────────────────────────────────────────

def _load_schedules() -> list[dict]:
    """
    Load all schedule JSONs from schedules/ and legacy output/ locations.
    Returns list of dicts: {retailer, client, keywords, days, times}.
    """
    schedules = []

    # New-style schedules/
    for p in sorted(SCHEDULES_DIR.glob("*.json")):
        if p.name in ("master_schedule.json",):
            continue
        try:
            with open(p) as f:
                raw = json.load(f)
            times = []
            for t in raw.get("times", []):
                if isinstance(t, str) and re.match(r'\d{2}:\d{2}', t):
                    times.append(t)
                elif isinstance(t, (list, tuple)) and len(t) >= 2:
                    hh, mm = int(t[0]), int(t[1])
                    ap = str(t[2]).upper() if len(t) >= 3 else ""
                    if ap == "PM" and hh != 12:
                        hh += 12
                    elif ap == "AM" and hh == 12:
                        hh = 0
                    times.append(f"{hh:02d}:{mm:02d}")
            days = [str(d).strip().lower() for d in raw.get("days", [])]
            schedules.append({
                "retailer":  raw.get("retailer", "").strip().lower(),
                "client":    raw.get("client", "").strip(),
                "keywords":  raw.get("keywords", []),
                "days":      days,
                "times":     sorted(set(times)),
                "enabled":   raw.get("enabled", True),
                "source":    str(p),
            })
        except Exception:
            pass

    # Legacy output/<retailer>/<client>/schedule_config.json
    for p in glob.glob(str(OUTPUT_DIR / "*" / "*" / "schedule_config.json")):
        try:
            with open(p) as f:
                raw = json.load(f)
            parts = Path(p).parts
            retailer = parts[-3].lower()
            client   = parts[-2]
            times = []
            if "schedule" in raw and isinstance(raw["schedule"], dict):
                for day_times in raw["schedule"].values():
                    for t in day_times:
                        if isinstance(t, str):
                            times.append(t)
                        elif isinstance(t, (list, tuple)):
                            hh, mm = int(t[0]), int(t[1])
                            ap = str(t[2]).upper() if len(t) >= 3 else ""
                            if ap == "PM" and hh != 12: hh += 12
                            elif ap == "AM" and hh == 12: hh = 0
                            times.append(f"{hh:02d}:{mm:02d}")
                days = list(raw["schedule"].keys())
            else:
                for t in raw.get("times", []):
                    if isinstance(t, str):
                        times.append(t)
                    elif isinstance(t, (list, tuple)):
                        hh, mm = int(t[0]), int(t[1])
                        ap = str(t[2]).upper() if len(t) >= 3 else ""
                        if ap == "PM" and hh != 12: hh += 12
                        elif ap == "AM" and hh == 12: hh = 0
                        times.append(f"{hh:02d}:{mm:02d}")
                days = [str(d).strip().lower() for d in raw.get("days", [])]
            schedules.append({
                "retailer":  raw.get("retailer", retailer).strip().lower(),
                "client":    raw.get("client", client).strip(),
                "keywords":  raw.get("keywords", []),
                "days":      days,
                "times":     sorted(set(times)),
                "enabled":   raw.get("enabled", True),
                "source":    str(p),
            })
        except Exception:
            pass

    return schedules


# ── Run discovery ──────────────────────────────────────────────────────────

def _find_runs_for_date(target_date: date) -> list[dict]:
    """
    Scan output/<retailer>/<client>/runs/run_results_*.json and return all
    runs whose timestamp falls on target_date.
    """
    runs = []
    date_str = target_date.strftime("%Y%m%d")   # 14-digit ts prefix
    date_str2 = target_date.strftime("%Y-%m-%d") # hyphenated

    pattern = str(OUTPUT_DIR / "**" / "run_results_*.json")
    for fpath in glob.glob(pattern, recursive=True):
        if "legacy_backup" in fpath:
            continue
        basename = os.path.basename(fpath)
        # Quick filter: date must appear somewhere in filename
        if date_str not in basename and date_str2 not in basename:
            continue
        try:
            with open(fpath) as f:
                data = json.load(f)
        except Exception:
            continue

        dt = _run_dt(data, basename)
        if dt is None or dt.date() != target_date:
            continue

        # Always derive retailer from path — the JSON "retailer" field is
        # wrong in many Walmart/Instacart files (recorded as "kroger").
        parts = Path(fpath).parts
        try:
            out_idx  = parts.index("output")
            retailer = parts[out_idx + 1].lower()
            client   = parts[out_idx + 2]
        except (ValueError, IndexError):
            retailer = data.get("retailer", "unknown").lower()
            client   = data.get("client", "unknown")

        runs.append({
            "retailer": retailer,
            "client":   data.get("client") or client,
            "keyword":  data.get("keyword") or data.get("search_term") or "",
            "dt":       dt,
            "success":  _is_success(data),
            "ad_types": _ad_type_counts(data),
            "path":     fpath,
        })

    return sorted(runs, key=lambda r: r["dt"])


# ── Log-based failure extraction ───────────────────────────────────────────

def _find_log_failures(target_date: date) -> list[dict]:
    """
    Parse scheduler_daemon.log for FAIL lines on the target date.
    Returns list of {retailer, client, keyword, hhmm, msg}.
    """
    log_path = LOGS_DIR / "scheduler_daemon.log"
    if not log_path.exists():
        return []

    failures = []
    date_prefix = target_date.strftime("%Y-%m-%d")

    # Pattern: "2026-03-02 08:03:00,845 - ERROR - [walmart] FAIL keyword 'x' for Client: rc=1"
    fail_re = re.compile(
        r'^(' + re.escape(date_prefix) + r' \d{2}:\d{2}).*?ERROR.*?\[(\w+)\].*?FAIL.*?(?:keyword\s+[\'"]([^\'"]*)[\'"])?\s*for\s+([^:]+)',
        re.IGNORECASE
    )

    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if date_prefix not in line[:12]:
                    continue
                m = fail_re.match(line.strip())
                if m:
                    ts_str, retailer, kw, client = m.groups()
                    hhmm = ts_str.split(" ")[1][:5]
                    failures.append({
                        "retailer": retailer.lower(),
                        "client":   (client or "").strip(),
                        "keyword":  (kw or "").strip(),
                        "hhmm":     hhmm,
                        "msg":      line.strip(),
                    })
    except Exception:
        pass

    return failures


# ── Report assembly ────────────────────────────────────────────────────────

def build_report(target_date: date) -> dict:
    """
    Assemble all data for the report. Returns a structured dict.
    """
    day_name = target_date.strftime("%A").lower()  # e.g. "monday"

    all_schedules = _load_schedules()
    # Only schedules active on target_date's weekday
    active = [
        s for s in all_schedules
        if s.get("retailer") and s.get("enabled", True) and day_name in s.get("days", [])
    ]

    runs       = _find_runs_for_date(target_date)
    log_fails  = _find_log_failures(target_date)

    # ── Overview ──────────────────────────────────────────────────────────
    total      = len(runs)
    successful = sum(1 for r in runs if r["success"])
    failed_runs = [r for r in runs if not r["success"]]

    # Per-retailer breakdown
    by_retailer = defaultdict(lambda: {"success": 0, "failed": 0, "ad_types": Counter()})
    for r in runs:
        key = r["retailer"]
        if r["success"]:
            by_retailer[key]["success"] += 1
        else:
            by_retailer[key]["failed"]  += 1
        by_retailer[key]["ad_types"] += r["ad_types"]

    # ── Schedule vs actual detail ──────────────────────────────────────────
    # Build a lookup: (retailer_lower, client_lower, keyword_lower) → sorted run times
    run_index = defaultdict(list)
    for r in runs:
        key = (r["retailer"], r["client"].lower(), r["keyword"].lower())
        run_index[key].append(r)

    schedule_rows = []
    seen_rows = set()
    for sched in active:
        retailer = sched["retailer"]
        client   = sched["client"]
        keywords = sched["keywords"]
        times    = sched["times"]   # scheduled HH:MM slots

        for kw in (keywords if keywords else [""]):
            row_key = (retailer, client.lower(), kw.lower(), tuple(sorted(times)))
            if row_key in seen_rows:
                continue
            seen_rows.add(row_key)
            lookup = (retailer, client.lower(), kw.lower())
            actual_runs = run_index.get(lookup, [])

            # Match each scheduled time to the nearest actual run (within 30 min)
            slots_detail = []
            used = set()
            for sched_time in sorted(times):
                sh, sm = map(int, sched_time.split(":"))
                sched_min = sh * 60 + sm
                best_run = None
                best_diff = 999
                for idx, ar in enumerate(actual_runs):
                    if idx in used:
                        continue
                    am = ar["dt"].hour * 60 + ar["dt"].minute
                    diff = abs(am - sched_min)
                    if diff < best_diff and diff <= 30:
                        best_diff = diff
                        best_run = (idx, ar)
                if best_run:
                    used.add(best_run[0])
                    ar = best_run[1]
                    slots_detail.append({
                        "scheduled": sched_time,
                        "actual":    ar["dt"].strftime("%H:%M"),
                        "status":    "ok" if ar["success"] else "empty",
                        "ad_types":  ar["ad_types"],
                        "keyword":   kw or ar["keyword"],
                    })
                else:
                    # Check log failures for this slot
                    fail_match = next(
                        (f for f in log_fails
                         if f["retailer"] == retailer
                         and client.lower() in f["client"].lower()
                         and abs(int(f["hhmm"].split(":")[0])*60 + int(f["hhmm"].split(":")[1]) - sched_min) <= 30),
                        None
                    )
                    slots_detail.append({
                        "scheduled": sched_time,
                        "actual":    fail_match["hhmm"] if fail_match else None,
                        "status":    "failed" if fail_match else "missing",
                        "ad_types":  Counter(),
                        "keyword":   kw,
                    })

            # Any extra runs not matched to a scheduled slot
            for idx, ar in enumerate(actual_runs):
                if idx not in used:
                    slots_detail.append({
                        "scheduled": None,
                        "actual":    ar["dt"].strftime("%H:%M"),
                        "status":    "unscheduled_ok" if ar["success"] else "unscheduled_empty",
                        "ad_types":  ar["ad_types"],
                        "keyword":   kw or ar["keyword"],
                    })

            schedule_rows.append({
                "retailer": retailer,
                "client":   client,
                "keyword":  kw,
                "times":    times,
                "slots":    slots_detail,
            })

    return {
        "date":          target_date.isoformat(),
        "date_end":      target_date.isoformat(),
        "day_name":      day_name.capitalize(),
        "total":         total,
        "successful":    successful,
        "failed":        total - successful,
        "by_retailer":   dict(by_retailer),
        "schedule_rows": schedule_rows,
        "log_failures":  log_fails,
        "daily_series":  {target_date.isoformat(): {"total": total, "successful": successful,
                          "by_retailer": {r: {"success": v["success"], "failed": v["failed"]}
                                          for r, v in by_retailer.items()}}},
    }


def build_report_range(start: date, end: date, retailer_filter: str = "") -> dict:
    """
    Aggregate runs across [start, end] inclusive.
    retailer_filter: if set, only include that retailer in by_retailer + schedule_rows.
    Returns same structure as build_report() but with multi-day data.
    """
    all_runs       = []
    all_log_fails  = []
    daily_series   = {}
    all_schedules  = _load_schedules()

    d = start
    while d <= end:
        day_runs  = _find_runs_for_date(d)
        day_fails = _find_log_failures(d)
        all_runs.extend(day_runs)
        all_log_fails.extend(day_fails)

        day_total = len(day_runs)
        day_ok    = sum(1 for r in day_runs if r["success"])
        by_r = {}
        for r in day_runs:
            if retailer_filter and r["retailer"] != retailer_filter:
                continue
            by_r.setdefault(r["retailer"], {"success": 0, "failed": 0})
            if r["success"]: by_r[r["retailer"]]["success"] += 1
            else:            by_r[r["retailer"]]["failed"]  += 1
        daily_series[d.isoformat()] = {
            "total": day_total, "successful": day_ok,
            "by_retailer": by_r,
        }
        d += timedelta(days=1)

    if retailer_filter:
        all_runs = [r for r in all_runs if r["retailer"] == retailer_filter]

    total      = len(all_runs)
    successful = sum(1 for r in all_runs if r["success"])

    by_retailer = defaultdict(lambda: {"success": 0, "failed": 0, "ad_types": Counter()})
    for r in all_runs:
        key = r["retailer"]
        if r["success"]: by_retailer[key]["success"] += 1
        else:            by_retailer[key]["failed"]  += 1
        by_retailer[key]["ad_types"] += r["ad_types"]

    # Schedule detail: show each active schedule for any day in the range,
    # collapsed — show total ok/missing/failed counts per slot position
    run_index = defaultdict(list)
    for r in all_runs:
        key = (r["retailer"], r["client"].lower(), r["keyword"].lower())
        run_index[key].append(r)

    schedule_rows = []
    seen_rows = set()
    seen_days = set((start + timedelta(days=i)).strftime("%A").lower()
                    for i in range((end - start).days + 1))

    for sched in all_schedules:
        if not sched.get("retailer") or not sched.get("enabled", True):
            continue
        if retailer_filter and sched["retailer"] != retailer_filter:
            continue
        if not any(day in seen_days for day in sched.get("days", [])):
            continue

        retailer = sched["retailer"]
        client   = sched["client"]
        keywords = sched["keywords"]
        times    = sched["times"]

        for kw in (keywords if keywords else [""]):
            row_key = (retailer, client.lower(), kw.lower(), tuple(sorted(times)))
            if row_key in seen_rows:
                continue
            seen_rows.add(row_key)
            lookup      = (retailer, client.lower(), kw.lower())
            actual_runs = run_index.get(lookup, [])
            ok    = sum(1 for r in actual_runs if r["success"])
            empty = sum(1 for r in actual_runs if not r["success"])

            # Count how many scheduled slots (days × times) were expected
            days_in_range = sum(
                1 for i in range((end - start).days + 1)
                if (start + timedelta(days=i)).strftime("%A").lower() in sched.get("days", [])
            )
            expected = days_in_range * len(times)
            matched  = min(ok + empty, expected)
            missing  = max(0, expected - matched)

            at = Counter()
            for r in actual_runs:
                if r["success"]:
                    at += r["ad_types"]

            schedule_rows.append({
                "retailer": retailer,
                "client":   client,
                "keyword":  kw,
                "times":    times,
                "ok":       ok,
                "empty":    empty,
                "missing":  missing,
                "expected": expected,
                "ad_types": dict(at),
                "slots":    [],   # not used in range view
            })

    label_start = start.strftime("%b %-d")
    label_end   = end.strftime("%b %-d, %Y")
    label = f"{label_start} – {label_end}" if start != end else start.strftime("%b %-d, %Y")

    return {
        "date":          start.isoformat(),
        "date_end":      end.isoformat(),
        "day_name":      label,
        "total":         total,
        "successful":    successful,
        "failed":        total - successful,
        "by_retailer":   dict(by_retailer),
        "schedule_rows": schedule_rows,
        "log_failures":  all_log_fails,
        "daily_series":  daily_series,
    }


def available_date_range() -> tuple[date, date]:
    """Return (earliest_date, latest_date) found across all run JSONs."""
    earliest = date.today()
    latest   = date(2020, 1, 1)
    pattern  = str(OUTPUT_DIR / "**" / "run_results_*.json")
    for fpath in glob.glob(pattern, recursive=True):
        if "legacy_backup" in fpath:
            continue
        m = re.search(r'(\d{14})', os.path.basename(fpath))
        if not m:
            continue
        try:
            d = datetime.strptime(m.group(1)[:8], "%Y%m%d").date()
            if d < earliest: earliest = d
            if d > latest:   latest   = d
        except ValueError:
            pass
    return earliest, latest


# ── Text renderer ──────────────────────────────────────────────────────────

STATUS_ICON = {
    "ok":                "✅",
    "empty":             "⚠️ ",
    "failed":            "❌",
    "missing":           "🔴 missing",
    "unscheduled_ok":    "✅ extra",
    "unscheduled_empty": "⚠️  extra",
}

def render_text(report: dict) -> str:
    lines = []
    sep = "─" * 72

    lines.append(f"\n{'═'*72}")
    lines.append(f"  DAILY SCRAPER REPORT  —  {report['date']}  ({report['day_name']})")
    lines.append(f"{'═'*72}\n")

    # ── Overview ──
    lines.append("OVERVIEW")
    lines.append(sep)
    s, f, t = report["successful"], report["failed"], report["total"]
    lines.append(f"  Total runs     : {t}")
    lines.append(f"  Successful     : {s}  ({'100' if t==0 else f'{s*100//t}'}%)")
    lines.append(f"  Failed / empty : {f}")
    lines.append("")

    # Per-retailer
    lines.append("BY RETAILER")
    lines.append(sep)
    for retailer in RETAILERS:
        rv = report["by_retailer"].get(retailer)
        if not rv:
            continue
        rs, rf = rv["success"], rv["failed"]
        lines.append(f"  {retailer.upper():<12}  {rs} ok  {rf} empty/failed")
        at = rv["ad_types"]
        if at:
            breakdown = "  ".join(f"{k}: {v}" for k, v in sorted(at.items()))
            lines.append(f"               ↳ {breakdown}")
    lines.append("")

    # ── Detail ──
    lines.append("SCHEDULE DETAIL")
    lines.append(sep)

    current_retailer = None
    for row in sorted(report["schedule_rows"],
                      key=lambda r: (r["retailer"], r["client"], r["keyword"])):
        retailer = row["retailer"]
        if retailer != current_retailer:
            lines.append(f"\n  [{retailer.upper()}]")
            current_retailer = retailer

        kw_label = f'"{row["keyword"]}"' if row["keyword"] else "(all keywords)"
        lines.append(f"    {row['client']}  ·  {kw_label}")
        lines.append(f"    {'Sched':>6}  {'Actual':>6}  Status   Ad Types")

        for sl in row["slots"]:
            icon = STATUS_ICON.get(sl["status"], "?")
            sched_s  = sl["scheduled"] or " N/A "
            actual_s = sl["actual"]    or "  —  "
            at_str   = "  ".join(f"{k}:{v}" for k, v in sorted(sl["ad_types"].items())) if sl["ad_types"] else ""
            lines.append(f"    {sched_s:>6}  {actual_s:>6}  {icon:<8} {at_str}")
        lines.append("")

    # Log failures not already surfaced in schedule detail
    covered = set()
    for row in report["schedule_rows"]:
        for sl in row["slots"]:
            if sl["status"] in ("failed", "missing") and sl["actual"]:
                covered.add((row["retailer"], row["client"].lower(), sl["actual"]))
    extra_fails = [
        lf for lf in report["log_failures"]
        if (lf["retailer"], lf["client"].lower(), lf["hhmm"]) not in covered
    ]
    if extra_fails:
        lines.append("ADDITIONAL LOG FAILURES")
        lines.append(sep)
        for lf in extra_fails:
            lines.append(f"  {lf['hhmm']}  [{lf['retailer']}]  {lf['client']}  kw={lf['keyword'] or '?'}")
        lines.append("")

    return "\n".join(lines)


# ── HTML renderer ──────────────────────────────────────────────────────────

def render_html(report: dict) -> str:
    s, f, t = report["successful"], report["failed"], report["total"]
    pct = f"{s*100//t}%" if t else "—"

    STATUS_BADGE = {
        "ok":                '<span class="badge ok">✅ ok</span>',
        "empty":             '<span class="badge warn">⚠ empty</span>',
        "failed":            '<span class="badge fail">✗ failed</span>',
        "missing":           '<span class="badge miss">— missing</span>',
        "unscheduled_ok":    '<span class="badge ok">✅ extra</span>',
        "unscheduled_empty": '<span class="badge warn">⚠ extra/empty</span>',
    }

    def at_html(at: Counter) -> str:
        if not at:
            return '<span class="none">—</span>'
        return " ".join(
            f'<span class="tag">{k} <b>{v}</b></span>'
            for k, v in sorted(at.items())
        )

    retailer_rows = ""
    for retailer in RETAILERS:
        rv = report["by_retailer"].get(retailer)
        if not rv:
            continue
        rs, rf = rv["success"], rv["failed"]
        at_str = at_html(rv["ad_types"])
        retailer_rows += f"""
        <tr>
          <td class="rname">{retailer}</td>
          <td class="num">{rs + rf}</td>
          <td class="num ok">{rs}</td>
          <td class="num fail">{rf}</td>
          <td class="adtypes">{at_str}</td>
        </tr>"""

    detail_html = ""
    current_retailer = None
    for row in sorted(report["schedule_rows"],
                      key=lambda r: (r["retailer"], r["client"], r["keyword"])):
        retailer = row["retailer"]
        if retailer != current_retailer:
            if current_retailer is not None:
                detail_html += "</tbody></table></div>"
            detail_html += f'<div class="retailer-block"><h3>{retailer.upper()}</h3>'
            detail_html += """<table class="detail-table">
              <thead><tr>
                <th>Client</th><th>Keyword</th>
                <th>Scheduled</th><th>Actual</th>
                <th>Status</th><th>Ad Types</th>
              </tr></thead><tbody>"""
            current_retailer = retailer

        kw_label = row["keyword"] or "<em>all</em>"
        for sl in row["slots"]:
            badge    = STATUS_BADGE.get(sl["status"], sl["status"])
            sched_s  = sl["scheduled"] or "—"
            actual_s = sl["actual"]    or "—"
            detail_html += f"""
            <tr class="row-{sl['status']}">
              <td>{row['client']}</td>
              <td>{kw_label}</td>
              <td class="time">{sched_s}</td>
              <td class="time">{actual_s}</td>
              <td>{badge}</td>
              <td class="adtypes">{at_html(sl['ad_types'])}</td>
            </tr>"""

    if current_retailer:
        detail_html += "</tbody></table></div>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Daily Report — {report['date']}</title>
<style>
  :root {{
    --bg: #0f1117; --surface: #1a1d27; --border: #2d2f3e;
    --text: #e2e4ef; --muted: #8b8fa8; --accent: #5b8cff;
    --ok: #3ecf8e; --warn: #f59e0b; --fail: #f87171; --miss: #6b7280;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font: 14px/1.6 'Inter', system-ui, sans-serif; padding: 32px; }}
  h1 {{ font-size: 22px; font-weight: 700; color: var(--accent); margin-bottom: 4px; }}
  h2 {{ font-size: 15px; font-weight: 600; color: var(--muted); text-transform: uppercase;
        letter-spacing: .08em; margin: 32px 0 12px; border-bottom: 1px solid var(--border); padding-bottom: 6px; }}
  h3 {{ font-size: 13px; font-weight: 600; color: var(--accent); margin: 18px 0 8px; text-transform: uppercase; }}
  .subtitle {{ color: var(--muted); font-size: 13px; margin-bottom: 32px; }}
  .cards {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 8px; }}
  .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
           padding: 18px 24px; min-width: 140px; }}
  .card .val {{ font-size: 32px; font-weight: 700; line-height: 1.1; }}
  .card .lbl {{ font-size: 12px; color: var(--muted); margin-top: 4px; }}
  .card.ok  .val {{ color: var(--ok); }}
  .card.fail .val {{ color: var(--fail); }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ text-align: left; padding: 8px 12px; color: var(--muted); font-weight: 500;
        background: var(--surface); border-bottom: 1px solid var(--border); }}
  td {{ padding: 7px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }}
  tr:last-child td {{ border-bottom: none; }}
  .rname {{ font-weight: 600; text-transform: capitalize; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .num.ok {{ color: var(--ok); }}
  .num.fail {{ color: var(--fail); }}
  .time {{ font-variant-numeric: tabular-nums; font-family: monospace; }}
  .tag {{ display: inline-block; background: #2a2d3e; border: 1px solid var(--border);
          border-radius: 4px; padding: 1px 6px; font-size: 11px; margin: 1px; }}
  .tag b {{ color: var(--accent); }}
  .badge {{ display: inline-block; border-radius: 4px; padding: 2px 8px;
            font-size: 11px; font-weight: 600; white-space: nowrap; }}
  .badge.ok   {{ background: #0d2e1e; color: var(--ok); }}
  .badge.warn {{ background: #2e1f08; color: var(--warn); }}
  .badge.fail {{ background: #2e0f0f; color: var(--fail); }}
  .badge.miss {{ background: #1a1d27; color: var(--miss); }}
  .none {{ color: var(--muted); }}
  .retailer-block {{ margin-bottom: 24px; }}
  .detail-table {{ background: var(--surface); border-radius: 8px; overflow: hidden;
                   border: 1px solid var(--border); }}
  .row-ok         {{ }}
  .row-empty      {{ background: #1e1906; }}
  .row-failed     {{ background: #1e0d0d; }}
  .row-missing    {{ background: #181a23; color: var(--muted); }}
  .adtypes        {{ max-width: 380px; }}
</style>
</head>
<body>
<h1>Daily Scraper Report</h1>
<p class="subtitle">{report['date']} &nbsp;·&nbsp; {report['day_name']}</p>

<h2>Overview</h2>
<div class="cards">
  <div class="card"><div class="val">{t}</div><div class="lbl">Total Runs</div></div>
  <div class="card ok"><div class="val">{s}</div><div class="lbl">Successful ({pct})</div></div>
  <div class="card fail"><div class="val">{f}</div><div class="lbl">Failed / Empty</div></div>
</div>

<h2>By Retailer</h2>
<table>
  <thead><tr>
    <th>Retailer</th><th>Total</th><th>OK</th><th>Fail</th><th>Ad Types Captured</th>
  </tr></thead>
  <tbody>{retailer_rows}</tbody>
</table>

<h2>Schedule Detail</h2>
{detail_html}

</body></html>"""


# ── Email-safe HTML renderer ───────────────────────────────────────────────
# Uses inline styles + light background so it works in Gmail, Outlook, Apple Mail.

def render_email_html(report: dict) -> str:
    s, f, t = report["successful"], report["failed"], report["total"]
    pct = f"{s*100//t}%" if t else "—"

    # Inline style constants
    C_BG        = "#f4f6f9"
    C_WHITE     = "#ffffff"
    C_BORDER    = "#e0e4ed"
    C_TEXT      = "#1a1d27"
    C_MUTED     = "#6b7280"
    C_ACCENT    = "#3b5bdb"
    C_OK        = "#1a7f4b"
    C_OK_BG     = "#d1fae5"
    C_WARN      = "#92400e"
    C_WARN_BG   = "#fef3c7"
    C_FAIL      = "#991b1b"
    C_FAIL_BG   = "#fee2e2"
    C_MISS      = "#4b5563"
    C_MISS_BG   = "#f3f4f6"
    C_ROW_EMPTY = "#fffbeb"
    C_ROW_FAIL  = "#fff1f2"
    C_ROW_MISS  = "#f9fafb"

    STATUS_BADGE = {
        "ok":                f'<span style="display:inline-block;background:{C_OK_BG};color:{C_OK};border-radius:4px;padding:2px 8px;font-size:11px;font-weight:600;white-space:nowrap">✅ ok</span>',
        "empty":             f'<span style="display:inline-block;background:{C_WARN_BG};color:{C_WARN};border-radius:4px;padding:2px 8px;font-size:11px;font-weight:600;white-space:nowrap">⚠ empty</span>',
        "failed":            f'<span style="display:inline-block;background:{C_FAIL_BG};color:{C_FAIL};border-radius:4px;padding:2px 8px;font-size:11px;font-weight:600;white-space:nowrap">✗ failed</span>',
        "missing":           f'<span style="display:inline-block;background:{C_MISS_BG};color:{C_MISS};border-radius:4px;padding:2px 8px;font-size:11px;font-weight:600;white-space:nowrap">— missing</span>',
        "unscheduled_ok":    f'<span style="display:inline-block;background:{C_OK_BG};color:{C_OK};border-radius:4px;padding:2px 8px;font-size:11px;font-weight:600;white-space:nowrap">✅ extra</span>',
        "unscheduled_empty": f'<span style="display:inline-block;background:{C_WARN_BG};color:{C_WARN};border-radius:4px;padding:2px 8px;font-size:11px;font-weight:600;white-space:nowrap">⚠ extra</span>',
    }

    ROW_BG = {
        "ok":                C_WHITE,
        "empty":             C_ROW_EMPTY,
        "failed":            C_ROW_FAIL,
        "missing":           C_ROW_MISS,
        "unscheduled_ok":    C_WHITE,
        "unscheduled_empty": C_ROW_EMPTY,
    }

    def at_html(at) -> str:
        if not at:
            return f'<span style="color:{C_MUTED}">—</span>'
        return " ".join(
            f'<span style="display:inline-block;background:#e8ecf5;border:1px solid {C_BORDER};border-radius:3px;padding:1px 5px;font-size:11px;margin:1px">{k} <b style="color:{C_ACCENT}">{v}</b></span>'
            for k, v in sorted(at.items())
        )

    td = f'style="padding:7px 12px;border-bottom:1px solid {C_BORDER};vertical-align:top;font-size:13px;color:{C_TEXT}"'
    th = f'style="text-align:left;padding:8px 12px;color:{C_MUTED};font-weight:600;font-size:12px;background:#f0f2f8;border-bottom:2px solid {C_BORDER};text-transform:uppercase;letter-spacing:.05em"'

    # ── Overview cards ──
    def card(val, label, color):
        return f'''<td style="width:33%;padding:0 8px 0 0">
          <div style="background:{C_WHITE};border:1px solid {C_BORDER};border-radius:8px;padding:16px 20px">
            <div style="font-size:30px;font-weight:700;color:{color};line-height:1.1">{val}</div>
            <div style="font-size:12px;color:{C_MUTED};margin-top:4px">{label}</div>
          </div></td>'''

    cards_html = f'''<table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px"><tr>
      {card(t, "Total Runs", C_TEXT)}
      {card(s, f"Successful ({pct})", C_OK)}
      {card(f, "Failed / Empty", C_FAIL)}
    </tr></table>'''

    # ── By retailer ──
    retailer_rows = ""
    for retailer in RETAILERS:
        rv = report["by_retailer"].get(retailer)
        if not rv:
            continue
        rs, rf = rv["success"], rv["failed"]
        fail_color = C_FAIL if rf > 0 else C_TEXT
        retailer_rows += f"""<tr style="background:{C_WHITE}">
          <td {td} style="padding:7px 12px;border-bottom:1px solid {C_BORDER};vertical-align:top;font-size:13px;color:{C_TEXT};font-weight:600;text-transform:capitalize">{retailer}</td>
          <td {td}>{rs + rf}</td>
          <td {td} style="padding:7px 12px;border-bottom:1px solid {C_BORDER};vertical-align:top;font-size:13px;color:{C_OK};font-weight:600">{rs}</td>
          <td {td} style="padding:7px 12px;border-bottom:1px solid {C_BORDER};vertical-align:top;font-size:13px;color:{fail_color};font-weight:600">{rf}</td>
          <td {td}>{at_html(rv["ad_types"])}</td>
        </tr>"""

    retailer_table = f'''<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;border:1px solid {C_BORDER};border-radius:8px;overflow:hidden;margin-bottom:32px">
      <thead><tr>
        <th {th}>Retailer</th><th {th}>Total</th>
        <th {th} style="text-align:left;padding:8px 12px;color:{C_OK};font-weight:600;font-size:12px;background:#f0f2f8;border-bottom:2px solid {C_BORDER};text-transform:uppercase;letter-spacing:.05em">OK</th>
        <th {th} style="text-align:left;padding:8px 12px;color:{C_FAIL};font-weight:600;font-size:12px;background:#f0f2f8;border-bottom:2px solid {C_BORDER};text-transform:uppercase;letter-spacing:.05em">Fail</th>
        <th {th}>Ad Types Captured</th>
      </tr></thead>
      <tbody>{retailer_rows}</tbody>
    </table>'''

    # ── Schedule detail ──
    detail_html = ""
    current_retailer = None
    for row in sorted(report["schedule_rows"],
                      key=lambda r: (r["retailer"], r["client"], r["keyword"])):
        retailer = row["retailer"]
        if retailer != current_retailer:
            if current_retailer is not None:
                detail_html += "</tbody></table></div>"
            detail_html += f'<div style="margin-bottom:24px"><p style="font-size:12px;font-weight:700;color:{C_ACCENT};text-transform:uppercase;letter-spacing:.08em;margin:0 0 8px 0">{retailer.upper()}</p>'
            detail_html += f'''<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;border:1px solid {C_BORDER};border-radius:8px;overflow:hidden;font-size:13px">
              <thead><tr>
                <th {th}>Client</th><th {th}>Keyword</th>
                <th {th}>Scheduled</th><th {th}>Actual</th>
                <th {th}>Status</th><th {th}>Ad Types</th>
              </tr></thead><tbody>'''
            current_retailer = retailer

        kw_label = row["keyword"] or "<em>all</em>"
        for sl in row["slots"]:
            badge  = STATUS_BADGE.get(sl["status"], sl["status"])
            row_bg = ROW_BG.get(sl["status"], C_WHITE)
            sched_s  = sl["scheduled"] or "—"
            actual_s = sl["actual"]    or "—"
            detail_html += f'''<tr style="background:{row_bg}">
              <td {td}>{row['client']}</td>
              <td {td}>{kw_label}</td>
              <td {td} style="padding:7px 12px;border-bottom:1px solid {C_BORDER};vertical-align:top;font-size:13px;color:{C_TEXT};font-family:monospace">{sched_s}</td>
              <td {td} style="padding:7px 12px;border-bottom:1px solid {C_BORDER};vertical-align:top;font-size:13px;color:{C_TEXT};font-family:monospace">{actual_s}</td>
              <td {td}>{badge}</td>
              <td {td}>{at_html(sl["ad_types"])}</td>
            </tr>'''

    if current_retailer:
        detail_html += "</tbody></table></div>"

    section_head = lambda title: f'<h2 style="font-size:13px;font-weight:700;color:{C_MUTED};text-transform:uppercase;letter-spacing:.08em;margin:28px 0 12px;padding-bottom:6px;border-bottom:2px solid {C_BORDER}">{title}</h2>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Daily Report — {report['date']}</title></head>
<body style="margin:0;padding:0;background:{C_BG};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif">
<div style="max-width:760px;margin:0 auto;padding:32px 16px">

  <h1 style="font-size:22px;font-weight:700;color:{C_ACCENT};margin:0 0 4px 0">Daily Scraper Report</h1>
  <p style="color:{C_MUTED};font-size:13px;margin:0 0 28px 0">{report['date']} &nbsp;·&nbsp; {report['day_name']}</p>

  {section_head("Overview")}
  {cards_html}

  {section_head("By Retailer")}
  {retailer_table}

  {section_head("Schedule Detail")}
  {detail_html}

</div>
</body></html>"""


# ── Notification ───────────────────────────────────────────────────────────

NOTIFY_CONFIG = ROOT / "config" / "notify.json"


def _load_notify_config() -> dict:
    if not NOTIFY_CONFIG.exists():
        return {}
    try:
        return json.loads(NOTIFY_CONFIG.read_text())
    except Exception as e:
        print(f"[notify] Could not load config: {e}", file=sys.stderr)
        return {}


def _should_send(report: dict, cfg: dict) -> tuple[bool, str]:
    """
    Decide whether to send based on config thresholds.
    Returns (should_send, reason).
    """
    send_cfg = cfg.get("send_on", {})
    if send_cfg.get("always", False):
        return True, "always"

    # Count total expected vs missed across all schedule rows
    total_expected = 0
    total_missing  = 0
    for row in report.get("schedule_rows", []):
        for sl in row.get("slots", []):
            total_expected += 1
            if sl["status"] in ("missing", "failed"):
                total_missing += 1

    if total_expected > 0:
        missing_pct = total_missing * 100 // total_expected
        threshold   = send_cfg.get("min_missing_pct", 10)
        if missing_pct >= threshold:
            return True, f"{missing_pct}% of slots missed/failed (threshold {threshold}%)"

    # Also send if there are any log-level failures
    if report.get("log_failures"):
        return True, f"{len(report['log_failures'])} log failure(s)"

    return False, "no issues above threshold"


def send_notification(report: dict, cfg: dict | None = None, dry_run: bool = False) -> bool:
    """
    Send the daily report as an HTML email.
    Returns True on success, False on failure/skip.
    """
    if cfg is None:
        cfg = _load_notify_config()

    email_cfg = cfg.get("email", {})
    if not email_cfg.get("enabled", False):
        print("[notify] Email disabled in config/notify.json")
        return False

    to_addrs = email_cfg.get("to_addrs", [])
    if not to_addrs:
        print("[notify] No to_addrs configured in config/notify.json", file=sys.stderr)
        return False

    should, reason = _should_send(report, cfg)
    if not should:
        print(f"[notify] Skipping email — {reason}")
        return False

    # Build subject with health summary
    total_expected = sum(1 for row in report["schedule_rows"] for _ in row["slots"])
    total_missing  = sum(
        1 for row in report["schedule_rows"]
        for sl in row["slots"] if sl["status"] in ("missing", "failed")
    )
    missing_pct = (total_missing * 100 // total_expected) if total_expected else 0

    # Tiered emoji + label based on how well it ran
    if total_missing == 0:
        status_emoji = "🟢"
        status_label = "All Clear"
    elif missing_pct <= 5:
        status_emoji = "🔵"
        status_label = "Nearly Perfect"
    elif missing_pct <= 15:
        status_emoji = "🟡"
        status_label = "Minor Issues"
    elif missing_pct <= 35:
        status_emoji = "🟠"
        status_label = "Degraded"
    else:
        status_emoji = "🔴"
        status_label = "Major Issues"

    prefix  = email_cfg.get("subject_prefix", "[RMN Scraper]")
    subject = (
        f"{prefix} {status_emoji} {status_label} — {report['date']} "
        f"({report['successful']}/{report['total']} runs ok"
        + (f", {missing_pct}% slots missed" if total_missing else "")
        + ")"
    )

    html_body  = render_email_html(report)
    text_body  = render_text(report)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = email_cfg.get("from_addr", email_cfg.get("smtp_user", ""))
    msg["To"]      = ", ".join(to_addrs)
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    if dry_run:
        print(f"[notify] DRY RUN — would send to: {', '.join(to_addrs)}")
        print(f"[notify] Subject: {subject}")
        print(f"[notify] Reason:  {reason}")
        return True

    host     = email_cfg.get("smtp_host", "smtp.gmail.com")
    port     = int(email_cfg.get("smtp_port", 587))
    user     = email_cfg.get("smtp_user", "")
    password = email_cfg.get("smtp_password", "")

    try:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            if user and password:
                server.login(user, password)
            server.sendmail(msg["From"], to_addrs, msg.as_string())
        print(f"[notify] Email sent → {', '.join(to_addrs)}  ({reason})")
        return True
    except Exception as e:
        print(f"[notify] SMTP error: {e}", file=sys.stderr)
        return False


# ── Entry point ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Daily scraper run report")
    parser.add_argument("--date", default=None,
                        help="Date to report on (YYYY-MM-DD). Default: yesterday.")
    parser.add_argument("--html",  action="store_true", help="Output HTML instead of text")
    parser.add_argument("--out",   default=None, help="Write output to file (auto-detects format from extension)")
    parser.add_argument("--email", action="store_true",
                        help="Send report as HTML email (uses config/notify.json)")
    parser.add_argument("--email-dry-run", action="store_true",
                        help="Show what email would be sent without actually sending it")
    args = parser.parse_args()

    if args.date:
        try:
            target = date.fromisoformat(args.date)
        except ValueError:
            print(f"Invalid date: {args.date}  (use YYYY-MM-DD)", file=sys.stderr)
            sys.exit(1)
    else:
        target = date.today() - timedelta(days=1)

    report = build_report(target)

    # Email notification
    if args.email or args.email_dry_run:
        send_notification(report, dry_run=args.email_dry_run)

    use_html = args.html or (args.out and args.out.endswith(".html"))
    output   = render_html(report) if use_html else render_text(report)

    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
        print(f"Written → {args.out}")
    elif not (args.email and not args.out):
        # Don't dump full text report to stdout when only emailing
        print(output)


if __name__ == "__main__":
    main()
