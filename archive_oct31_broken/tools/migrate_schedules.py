#!/usr/bin/env python3
"""
Migrate legacy schedule_config.json files from output/<retailer>/<client>/
to a new centralized schedules/ directory with normalized schema.
"""
import os
import json
import glob
import hashlib
from pathlib import Path
from datetime import datetime

ROOT = Path(os.environ.get("SCRAPER_HOME") or Path(__file__).resolve().parents[1])
OUT = ROOT / "output"
DEST = ROOT / "schedules"
DEST.mkdir(parents=True, exist_ok=True)

def slug(s: str) -> str:
    """Convert string to safe filename slug"""
    s = s.strip().lower().replace(" ", "_")
    return "".join(ch if (ch.isalnum() or ch in "-_") else "_" for ch in s)

def parse_time_12h(t):
    """Convert 12-hour time to 24-hour HH:MM format"""
    # Handle both "08:00" strings and [8, 0, "AM"] arrays
    if isinstance(t, str):
        if ":" in t:
            hh, mm = t.split(":")
            return f"{int(hh):02d}:{int(mm):02d}"
        return t
    
    hh = int(t[0])
    mm = int(t[1])
    ap = t[2].strip().upper() if len(t) >= 3 else None
    
    if ap == "AM":
        if hh == 12:
            hh = 0
    elif ap == "PM":
        if hh != 12:
            hh += 12
    
    return f"{hh:02d}:{mm:02d}"

def normalize_days(days):
    """Normalize day names to lowercase full names"""
    day_map = {
        'mon': 'monday', 'tue': 'tuesday', 'wed': 'wednesday',
        'thu': 'thursday', 'thur': 'thursday', 'fri': 'friday',
        'sat': 'saturday', 'sun': 'sunday'
    }
    out = []
    for d in days:
        s = str(d).strip().lower()
        # Try to match first 3 chars
        normalized = day_map.get(s[:3], s)
        out.append(normalized)
    return out

def norm_schedule(data, retailer_guess, client_guess):
    """Normalize a schedule config to the new schema"""
    retailer = slug(data.get("retailer", retailer_guess) or retailer_guess)
    client_raw = data.get("client", client_guess) or client_guess
    client = slug(client_raw)

    # Extract days/times from either old or new schema
    days, times = [], []
    
    if "schedule" in data and isinstance(data["schedule"], dict):
        # Old schema: {"schedule": {"monday": ["08:00", "12:00"], ...}}
        for d, ts in data["schedule"].items():
            days.append(d)
            for t in ts:
                times.append(parse_time_12h(t))
    else:
        # New schema: {"days": [...], "times": [[8, 0, "AM"], ...]}
        days = data.get("days", [])
        for t in data.get("times", []):
            times.append(parse_time_12h(t))

    days = sorted(set(normalize_days(days)))
    times = sorted(set(times))
    keywords = data.get("keywords", [])
    if not isinstance(keywords, list):
        keywords = [str(keywords)]

    # Build stable ID
    key = f"{retailer}|{client}|{','.join(keywords)}|{','.join(days)}|{','.join(times)}"
    dhash = hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]
    kw_slug = slug(keywords[0]) if keywords else "default"
    sched_id = f"{retailer}_{client}_{kw_slug}_{dhash}"

    now = datetime.utcnow().isoformat() + "Z"
    return {
        "id": sched_id,
        "retailer": retailer,
        "client": client_raw,  # Keep original client name for display
        "keywords": keywords,
        "days": days,
        "times": times,
        "enabled": True,
        "created_at": now,
        "updated_at": now,
    }

def main():
    """Migrate all legacy schedule files to new format"""
    master = {"schedules": [], "version": "1.0"}
    srcs = glob.glob(str(OUT / "*" / "*" / "schedule_config.json"))
    
    if not srcs:
        print("No legacy schedule_config.json files found under output/*/*/")
        print("Nothing to migrate.")
        return

    print(f"Found {len(srcs)} legacy schedule files to migrate...")
    
    for cfg in srcs:
        cfgp = Path(cfg)
        retailer_guess = cfgp.parents[1].name  # output/<retailer>/<client>/
        client_guess = cfgp.parent.name
        
        try:
            with open(cfg, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"⚠️  Skip {cfg}: {e}")
            continue

        sched = norm_schedule(data, retailer_guess, client_guess)
        
        # Create descriptive filename
        kw_part = slug(sched['keywords'][0]) if sched['keywords'] else 'default'
        fname = f"{sched['retailer']}__{sched['client']}__{kw_part}.json"
        dest = DEST / fname
        
        # Avoid overwrite: append hash if necessary
        if dest.exists():
            dest = DEST / f"{dest.stem}__{sched['id'][-8:]}.json"
        
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(sched, f, indent=2)
        
        print(f"✓ {cfg.replace(str(ROOT), '.')} → {dest.relative_to(ROOT)}")
        master["schedules"].append(sched)

    # Write master index
    master_path = DEST / "master_schedule.json"
    with open(master_path, "w", encoding="utf-8") as f:
        json.dump(master, f, indent=2)
    
    print(f"\n✅ Migration complete!")
    print(f"   Created {len(master['schedules'])} schedule files in schedules/")
    print(f"   Master index: {master_path.relative_to(ROOT)}")
    print(f"\n💡 Legacy files remain in output/ for backwards compatibility")
    print(f"   You can delete them after verifying the migration worked.")

if __name__ == "__main__":
    main()
