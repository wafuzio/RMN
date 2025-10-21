#!/usr/bin/env python3
"""
Shared schedule loader, validator, and index builder.
Used by daemon, GUI, and CLI tools for consistent schedule handling.
"""
from __future__ import annotations
import json
import re
import hashlib
import os
import glob
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

DAY_MAP = {
    'mon': 'monday', 'tue': 'tuesday', 'wed': 'wednesday',
    'thu': 'thursday', 'thur': 'thursday', 'fri': 'friday',
    'sat': 'saturday', 'sun': 'sunday'
}
DAY_SET = set(DAY_MAP.values())

ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

# Optional timezone support (Python 3.9+)
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None


def slug(s: str) -> str:
    """Convert string to safe filename slug"""
    s = s.strip().lower().replace(" ", "_")
    return "".join(ch if (ch.isalnum() or ch in "-_") else "_" for ch in s)


def is_hhmm(s: str) -> bool:
    """Check if string is valid HH:MM format"""
    return bool(re.fullmatch(r"\d{2}:\d{2}", s))


def validate_hhmm(s: str) -> str:
    """Validate and normalize time to HH:MM 24-hour format"""
    if not is_hhmm(s):
        raise ValueError(f"Invalid time '{s}' (expected HH:MM 24h)")
    h, m = map(int, s.split(":"))
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"Invalid time '{s}' (range)")
    return f"{h:02d}:{m:02d}"


def normalize_days(days: List[str]) -> List[str]:
    """Normalize day names to lowercase full names"""
    res = []
    for d in days:
        s = str(d).strip().lower()
        s = DAY_MAP.get(s[:3], s)
        if s not in DAY_SET:
            raise ValueError(f"Invalid day '{d}'")
        res.append(s)
    # Stable uniqueness - sort by day order
    day_order = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    return sorted(set(res), key=lambda x: day_order.index(x) if x in day_order else 99)


def now_in_tz(tz: Optional[str] = None) -> datetime:
    """Get current time in specified timezone (or system timezone if None)"""
    if not tz or not ZoneInfo:
        return datetime.now()
    try:
        return datetime.now(ZoneInfo(tz))
    except Exception:
        return datetime.now()


@dataclass
class Schedule:
    """Normalized schedule configuration"""
    id: str
    retailer: str
    client: str
    keywords: List[str]
    days: List[str]
    times: List[str]
    enabled: bool = True
    tz: str = ""  # Optional IANA timezone (e.g., America/Chicago)
    created_at: str = ""
    updated_at: str = ""
    source_path: str = ""  # Where it was loaded from
    output_dir: str = ""  # Derived: SCRAPER_HOME/output/<retailer>/<client_slug>

    @classmethod
    def load(cls, path: Path, scraper_home: Path) -> "Schedule":
        """Load and validate a schedule from JSON file"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        retailer = slug(data.get("retailer", ""))
        client_raw = data.get("client", "")
        client = slug(client_raw)
        
        if not retailer or not client:
            raise ValueError(f"retailer/client required in {path}")

        keywords = data.get("keywords", [])
        if not isinstance(keywords, list):
            keywords = [str(keywords)]
        keywords = [k for k in (kw.strip() for kw in keywords) if k]

        days = normalize_days(data.get("days", []))
        times = [validate_hhmm(t) for t in data.get("times", [])]
        
        if not days or not times:
            raise ValueError(f"days/times required in {path}")

        enabled = bool(data.get("enabled", True))
        tz = str(data.get("tz", "")).strip()

        created_at = data.get("created_at") or datetime.utcnow().strftime(ISO_FORMAT)
        updated_at = data.get("updated_at") or created_at

        sid = data.get("id")
        if not sid:
            # Generate a stable ID
            key = f"{retailer}|{client}|{','.join(keywords)}|{','.join(days)}|{','.join(times)}"
            dh = hashlib.sha1(key.encode()).hexdigest()[:8]
            kw_slug = slug(keywords[0]) if keywords else "default"
            sid = f"{retailer}_{client}_{kw_slug}_{dh}"

        output_dir = str(scraper_home / "output" / retailer / client)

        return cls(
            id=sid,
            retailer=retailer,
            client=client_raw or client,
            keywords=keywords,
            days=days,
            times=times,
            enabled=enabled,
            tz=tz,
            created_at=created_at,
            updated_at=updated_at,
            source_path=str(path),
            output_dir=output_dir
        )

    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return asdict(self)


def scan_schedules(scraper_home: Path) -> List[Schedule]:
    """
    Scan for all schedules in both new (schedules/) and legacy (output/) locations.
    Returns normalized Schedule objects.
    """
    sched_dir = scraper_home / "schedules"
    out_dir = scraper_home / "output"
    schedules: List[Schedule] = []

    # NEW: Scan schedules/ directory first (preferred)
    if sched_dir.exists():
        for p in sorted(sched_dir.glob("*.json")):
            if p.name == "master_schedule.json":
                continue  # Skip the generated index
            try:
                schedules.append(Schedule.load(p, scraper_home))
            except Exception as e:
                print(f"⚠️  Skip {p}: {e}")

    # LEGACY: Scan output/*/*/schedule_config.json for backwards compatibility
    for p in glob.glob(str(out_dir / "*" / "*" / "schedule_config.json")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                raw = json.load(f)
            
            # Convert legacy schema on the fly
            if "schedule" in raw and isinstance(raw["schedule"], dict):
                # Old format: {"schedule": {"monday": ["08:00", "12:00"], ...}}
                days, times = [], []
                for d, ts in raw["schedule"].items():
                    days.append(d)
                    for t in ts:
                        if isinstance(t, str):
                            times.append(t)
                        else:
                            # ["8", "00", "AM"] format
                            hh = int(t[0])
                            mm = int(t[1])
                            ap = (t[2] or "").upper() if len(t) >= 3 else ""
                            if ap == "AM":
                                if hh == 12:
                                    hh = 0
                            elif ap == "PM":
                                if hh != 12:
                                    hh += 12
                            times.append(f"{hh:02d}:{mm:02d}")
                data = {
                    "retailer": raw.get("retailer") or Path(p).parts[-3],
                    "client": raw.get("client") or Path(p).parts[-2],
                    "keywords": raw.get("keywords", []),
                    "days": days,
                    "times": times,
                    "enabled": True
                }
            else:
                # Newer legacy: {"days": [], "times": [[8, 0, "AM"], ...]}
                times = []
                for t in raw.get("times", []):
                    if isinstance(t, str):
                        times.append(t)
                    else:
                        hh = int(t[0])
                        mm = int(t[1])
                        ap = (t[2] or "").upper() if len(t) >= 3 else ""
                        if ap == "AM":
                            if hh == 12:
                                hh = 0
                        elif ap == "PM":
                            if hh != 12:
                                hh += 12
                        times.append(f"{hh:02d}:{mm:02d}")
                data = {
                    "retailer": raw.get("retailer") or Path(p).parts[-3],
                    "client": raw.get("client") or Path(p).parts[-2],
                    "keywords": raw.get("keywords", []),
                    "days": raw.get("days", []),
                    "times": times,
                    "enabled": raw.get("enabled", True)
                }
            
            # Create normalized Schedule object
            retailer_slug = slug(data["retailer"])
            client_slug = slug(data["client"])
            
            # Generate ID
            key = f"{retailer_slug}|{client_slug}|{','.join(data['keywords'])}|{','.join(data['days'])}|{','.join(data['times'])}"
            dh = hashlib.sha1(key.encode()).hexdigest()[:8]
            kw_slug = slug(data['keywords'][0]) if data['keywords'] else "default"
            sid = f"{retailer_slug}_{client_slug}_{kw_slug}_{dh}"
            
            now_iso = datetime.utcnow().strftime(ISO_FORMAT)
            
            s = Schedule(
                id=sid,
                retailer=retailer_slug,
                client=data["client"],
                keywords=data["keywords"],
                days=normalize_days(data["days"]),
                times=[validate_hhmm(t) for t in data["times"]],
                enabled=bool(data["enabled"]),
                tz="",
                created_at=now_iso,
                updated_at=now_iso,
                source_path=str(p),
                output_dir=str(scraper_home / "output" / retailer_slug / client_slug)
            )
            schedules.append(s)
        except Exception as e:
            print(f"⚠️  Skip legacy {p}: {e}")

    return schedules


def build_master_index(scraper_home: Path) -> Path:
    """
    Build master_schedule.json index from all schedules.
    Returns path to the generated index file.
    """
    schedules = scan_schedules(scraper_home)
    data = {
        "schedules": [s.to_dict() for s in schedules],
        "version": "1.0"
    }
    
    out = scraper_home / "schedules" / "master_schedule.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    
    return out


def detect_conflicts(schedules: List[Schedule], window_minutes: int = 5) -> List[tuple]:
    """
    Detect scheduling conflicts within a time window.
    Returns list of (schedule1, schedule2, conflict_reason) tuples.
    """
    conflicts = []
    
    for i, s1 in enumerate(schedules):
        if not s1.enabled:
            continue
        for s2 in schedules[i+1:]:
            if not s2.enabled:
                continue
            
            # Check if same retailer (Playwright conflict)
            if s1.retailer != s2.retailer:
                continue
            
            # Check for overlapping days
            common_days = set(s1.days) & set(s2.days)
            if not common_days:
                continue
            
            # Check for time conflicts (within window)
            for t1 in s1.times:
                h1, m1 = map(int, t1.split(":"))
                min1 = h1 * 60 + m1
                
                for t2 in s2.times:
                    h2, m2 = map(int, t2.split(":"))
                    min2 = h2 * 60 + m2
                    
                    if abs(min1 - min2) < window_minutes:
                        reason = f"Same retailer ({s1.retailer}), overlapping days ({common_days}), times within {window_minutes}min ({t1} vs {t2})"
                        conflicts.append((s1, s2, reason))
    
    return conflicts
