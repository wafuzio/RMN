"""Run tracking and delta detection for ad capture sessions.

Each capture run is recorded in a SQLite database at:
    ~/.config/cli-web-walmart/runs.db

This enables:
- Listing past capture runs
- Comparing two runs to detect new/dropped/changed ads
- Scheduling recurring captures
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path.home() / ".config" / "cli-web-walmart" / "runs.db"


# ── Schema ────────────────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    query       TEXT NOT NULL,
    url         TEXT NOT NULL,
    page        INTEGER DEFAULT 1,
    timestamp   TEXT NOT NULL,       -- ISO-8601 UTC
    output_dir  TEXT,
    status      TEXT DEFAULT 'complete',  -- complete | failed | partial
    item_count  INTEGER DEFAULT 0,
    ad_count    INTEGER DEFAULT 0,
    banner_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ad_fingerprints (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL REFERENCES runs(run_id),
    ad_type     TEXT NOT NULL,    -- sponsored_product | banner | video | shelf
    fingerprint TEXT NOT NULL,    -- SHA-256 of canonical ad fields
    ad_uuid     TEXT,
    item_id     TEXT,
    template_id TEXT,
    slot_name   TEXT,
    first_seen  TEXT NOT NULL,    -- ISO-8601 UTC
    raw_json    TEXT              -- full ad dict as JSON
);

CREATE INDEX IF NOT EXISTS idx_fingerprint ON ad_fingerprints(fingerprint);
CREATE INDEX IF NOT EXISTS idx_run_id      ON ad_fingerprints(run_id);

CREATE TABLE IF NOT EXISTS schedules (
    schedule_id  TEXT PRIMARY KEY,
    query        TEXT NOT NULL,
    interval_sec INTEGER NOT NULL,   -- seconds between runs
    output_dir   TEXT NOT NULL,
    last_run     TEXT,               -- ISO-8601 UTC or NULL
    next_run     TEXT NOT NULL,      -- ISO-8601 UTC
    enabled      INTEGER DEFAULT 1,
    options      TEXT DEFAULT '{}'   -- JSON: limit, page, etc.
);
"""


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class RunRecord:
    run_id: str
    query: str
    url: str
    page: int
    timestamp: str
    output_dir: str
    status: str = "complete"
    item_count: int = 0
    ad_count: int = 0
    banner_count: int = 0

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "query": self.query,
            "url": self.url,
            "page": self.page,
            "timestamp": self.timestamp,
            "output_dir": self.output_dir,
            "status": self.status,
            "item_count": self.item_count,
            "ad_count": self.ad_count,
            "banner_count": self.banner_count,
        }


@dataclass
class AdDelta:
    """Diff between two runs."""
    run_a: str
    run_b: str
    new_ads: list[dict] = field(default_factory=list)       # in B, not in A
    dropped_ads: list[dict] = field(default_factory=list)   # in A, not in B
    unchanged: int = 0

    def to_dict(self) -> dict:
        return {
            "run_a": self.run_a,
            "run_b": self.run_b,
            "new_ads": self.new_ads,
            "dropped_ads": self.dropped_ads,
            "new_count": len(self.new_ads),
            "dropped_count": len(self.dropped_ads),
            "unchanged": self.unchanged,
        }


@dataclass
class ScheduleRecord:
    schedule_id: str
    query: str
    interval_sec: int
    output_dir: str
    next_run: str
    last_run: Optional[str] = None
    enabled: bool = True
    options: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "schedule_id": self.schedule_id,
            "query": self.query,
            "interval_sec": self.interval_sec,
            "interval_human": _human_interval(self.interval_sec),
            "output_dir": self.output_dir,
            "next_run": self.next_run,
            "last_run": self.last_run,
            "enabled": self.enabled,
            "options": self.options,
        }


# ── Database layer ────────────────────────────────────────────────────────────

class RunStore:
    """SQLite-backed store for run records, ad fingerprints, and schedules."""

    def __init__(self, db_path: Path = DB_PATH):
        self._path = db_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.executescript(_DDL)

    # ── Runs ──────────────────────────────────────────────────────────────────

    def save_run(self, run: RunRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO runs
                   (run_id, query, url, page, timestamp, output_dir,
                    status, item_count, ad_count, banner_count)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (run.run_id, run.query, run.url, run.page, run.timestamp,
                 run.output_dir, run.status, run.item_count,
                 run.ad_count, run.banner_count),
            )

    def get_run(self, run_id: str) -> Optional[RunRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return _row_to_run(row) if row else None

    def list_runs(self, query: Optional[str] = None, limit: int = 50) -> list[RunRecord]:
        with self._connect() as conn:
            if query:
                rows = conn.execute(
                    "SELECT * FROM runs WHERE query LIKE ? ORDER BY timestamp DESC LIMIT ?",
                    (f"%{query}%", limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM runs ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [_row_to_run(r) for r in rows]

    # ── Ad fingerprints ───────────────────────────────────────────────────────

    def save_fingerprints(self, run_id: str, ads: list[dict], ad_type: str) -> None:
        now = _now_iso()
        rows = []
        for ad in ads:
            fp = _fingerprint(ad)
            rows.append((
                run_id,
                ad_type,
                fp,
                ad.get("adUuid") or ad.get("ad_uuid"),
                ad.get("usItemId") or ad.get("item_id"),
                ad.get("templateId") or ad.get("template_id"),
                ad.get("slotName") or ad.get("slot_name"),
                now,
                json.dumps(ad, default=str)[:4096],  # cap stored JSON size
            ))
        with self._connect() as conn:
            conn.executemany(
                """INSERT INTO ad_fingerprints
                   (run_id, ad_type, fingerprint, ad_uuid, item_id,
                    template_id, slot_name, first_seen, raw_json)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                rows,
            )

    def get_fingerprints(self, run_id: str) -> set[str]:
        """Return set of ad fingerprints for a given run."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT fingerprint FROM ad_fingerprints WHERE run_id = ?",
                (run_id,),
            ).fetchall()
        return {r["fingerprint"] for r in rows}

    def get_ads_by_fingerprints(self, run_id: str, fingerprints: set[str]) -> list[dict]:
        """Fetch full ad records matching given fingerprints for a run."""
        if not fingerprints:
            return []
        placeholders = ",".join("?" * len(fingerprints))
        with self._connect() as conn:
            rows = conn.execute(
                f"""SELECT * FROM ad_fingerprints
                    WHERE run_id = ? AND fingerprint IN ({placeholders})""",
                (run_id, *fingerprints),
            ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            try:
                d["raw"] = json.loads(d.get("raw_json") or "{}")
            except Exception:
                d["raw"] = {}
            result.append(d)
        return result

    # ── Delta ─────────────────────────────────────────────────────────────────

    def compute_delta(self, run_id_a: str, run_id_b: str) -> AdDelta:
        """Compare two runs — find new, dropped, and unchanged ads."""
        fps_a = self.get_fingerprints(run_id_a)
        fps_b = self.get_fingerprints(run_id_b)

        new_fps = fps_b - fps_a
        dropped_fps = fps_a - fps_b
        unchanged = len(fps_a & fps_b)

        new_ads = self.get_ads_by_fingerprints(run_id_b, new_fps)
        dropped_ads = self.get_ads_by_fingerprints(run_id_a, dropped_fps)

        return AdDelta(
            run_a=run_id_a,
            run_b=run_id_b,
            new_ads=new_ads,
            dropped_ads=dropped_ads,
            unchanged=unchanged,
        )

    # ── Schedules ─────────────────────────────────────────────────────────────

    def save_schedule(self, sched: ScheduleRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO schedules
                   (schedule_id, query, interval_sec, output_dir,
                    last_run, next_run, enabled, options)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (sched.schedule_id, sched.query, sched.interval_sec,
                 sched.output_dir, sched.last_run, sched.next_run,
                 int(sched.enabled), json.dumps(sched.options)),
            )

    def list_schedules(self, enabled_only: bool = False) -> list[ScheduleRecord]:
        with self._connect() as conn:
            if enabled_only:
                rows = conn.execute(
                    "SELECT * FROM schedules WHERE enabled=1 ORDER BY next_run"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM schedules ORDER BY next_run"
                ).fetchall()
        return [_row_to_sched(r) for r in rows]

    def get_due_schedules(self) -> list[ScheduleRecord]:
        """Return schedules whose next_run is now or in the past."""
        now = _now_iso()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM schedules WHERE enabled=1 AND next_run <= ?",
                (now,),
            ).fetchall()
        return [_row_to_sched(r) for r in rows]

    def update_schedule_after_run(self, schedule_id: str) -> None:
        """Update last_run and compute next_run after a schedule fires."""
        now = _now_iso()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT interval_sec FROM schedules WHERE schedule_id = ?",
                (schedule_id,),
            ).fetchone()
            if row:
                interval = row["interval_sec"]
                next_run = _iso_from_ts(time.time() + interval)
                conn.execute(
                    "UPDATE schedules SET last_run=?, next_run=? WHERE schedule_id=?",
                    (now, next_run, schedule_id),
                )

    def delete_schedule(self, schedule_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM schedules WHERE schedule_id=?", (schedule_id,)
            )
        return cursor.rowcount > 0


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_run_id(query: str) -> str:
    """Generate a unique run ID: timestamp + query slug."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    slug = re.sub(r"[^\w]", "_", query.lower())[:20].strip("_")
    return f"{ts}_{slug}"


def _fingerprint(ad: dict) -> str:
    """Stable hash of the ad's identity fields."""
    key_parts = [
        str(ad.get("adUuid") or ""),
        str(ad.get("usItemId") or ad.get("item_id") or ""),
        str(ad.get("templateId") or ""),
        str(ad.get("offerId") or ""),
    ]
    key = "|".join(key_parts)
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_from_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _row_to_run(row: sqlite3.Row) -> RunRecord:
    return RunRecord(
        run_id=row["run_id"],
        query=row["query"],
        url=row["url"],
        page=row["page"],
        timestamp=row["timestamp"],
        output_dir=row["output_dir"],
        status=row["status"],
        item_count=row["item_count"],
        ad_count=row["ad_count"],
        banner_count=row["banner_count"],
    )


def _row_to_sched(row: sqlite3.Row) -> ScheduleRecord:
    return ScheduleRecord(
        schedule_id=row["schedule_id"],
        query=row["query"],
        interval_sec=row["interval_sec"],
        output_dir=row["output_dir"],
        next_run=row["next_run"],
        last_run=row["last_run"],
        enabled=bool(row["enabled"]),
        options=json.loads(row["options"] or "{}"),
    )


def _human_interval(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


