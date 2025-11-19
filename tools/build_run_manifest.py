#!/usr/bin/env python3
"""
Build run manifest for fast metadata-based queries.

Creates a lightweight JSON index of all runs with per-run metadata:
- retailer, client, run_id, timestamp, keyword, ad_count
- Enables counting and pagination without loading cards

Usage:
    python3 tools/build_run_manifest.py
"""
from __future__ import annotations
import json
import re
import time
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT_ROOT / "output"
CACHE = PROJECT_ROOT / "cache"
CACHE.mkdir(exist_ok=True)
MANIFEST = CACHE / "run_manifest.json"
MANIFEST_TMP = CACHE / "run_manifest.json.tmp"


def iso(dt: datetime) -> str:
    """Convert datetime to ISO 8601 Z format."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_run_id(name: str) -> str | None:
    """Extract run_id from filename or directory name."""
    m = re.search(r"(20\d{12})", name)
    return m.group(1) if m else None


def list_run_jsons() -> list[Path]:
    """Find all run JSON files in output directory."""
    return list(OUTPUT.glob("**/runs/**/*.json"))


def count_ads_in_doc(doc: dict) -> int:
    """Count ads in canonical or legacy JSON structure."""
    # Canonical structure
    if isinstance(doc.get("ads"), list):
        return len(doc["ads"])
    
    # Legacy structure: {"results": [{"ads": [...]}]}
    total = 0
    for blk in doc.get("results", []):
        total += len(blk.get("ads", []))
    return total


def parse_ts(doc: dict, f: Path) -> str:
    """Extract and normalize timestamp to ISO Z format."""
    ts = doc.get("timestamp") or doc.get("ts") or doc.get("time")
    
    if ts:
        try:
            # Already ISO Z
            if ts.endswith("Z"):
                datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
                return ts
            # ISO without Z
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            pass
    
    # Fallback to run_id
    rid = doc.get("run_id") or get_run_id(f.name) or get_run_id(f.parent.name)
    if rid:
        try:
            dt = datetime.strptime(rid, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            return iso(dt)
        except Exception:
            pass
    
    # Last resort: file mtime
    return iso(datetime.utcfromtimestamp(f.stat().st_mtime).replace(tzinfo=timezone.utc))


def infer_parts(f: Path) -> tuple[str, str]:
    """Extract retailer and client from file path."""
    # output/<retailer>/<client>/runs/...
    parts = f.parts
    try:
        i = parts.index("output")
        return parts[i+1], parts[i+2]
    except (ValueError, IndexError):
        return "unknown", "unknown"


def build_manifest():
    """Build run manifest from all JSON files."""
    start = time.time()
    rows = []
    daily_totals = {}  # retailer -> client -> day -> total
    
    print(f"🔍 Scanning for run JSON files...")
    json_files = list_run_jsons()
    print(f"📁 Found {len(json_files)} files to process")
    
    for jf in json_files:
        try:
            doc = json.loads(jf.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"⚠️  Skipping malformed file {jf.name}: {e}")
            continue
        
        retailer, client = infer_parts(jf)
        keyword = doc.get("keyword") or doc.get("search_term") or ""
        run_id = doc.get("run_id") or get_run_id(jf.name) or get_run_id(jf.parent.name) or ""
        ts = parse_ts(doc, jf)
        day = ts[:10]
        ad_count = count_ads_in_doc(doc)
        rel = str(jf.relative_to(OUTPUT))

        rows.append({
            "retailer": retailer,
            "client": client,
            "json_path": rel,
            "run_id": run_id,
            "timestamp": ts,
            "day": day,
            "keyword": keyword,
            "ad_count": ad_count
        })

        # Update daily totals
        d1 = daily_totals.setdefault(retailer, {}).setdefault(client, {}).setdefault(day, 0)
        daily_totals[retailer][client][day] = d1 + ad_count

    # Sort runs newest first
    rows.sort(key=lambda r: r["timestamp"], reverse=True)

    # Atomic write: write to temp file then rename
    manifest_data = {
        "built_at": iso(datetime.utcnow().replace(tzinfo=timezone.utc)),
        "runs": rows,
        "daily_totals": daily_totals
    }
    
    MANIFEST_TMP.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    MANIFEST_TMP.replace(MANIFEST)  # Atomic on POSIX

    elapsed = time.time() - start
    print(f"✅ Manifest: {len(rows)} runs, wrote {MANIFEST} in {elapsed:.2f}s")
    
    # Summary stats
    total_ads = sum(r["ad_count"] for r in rows)
    retailers = len(set(r["retailer"] for r in rows))
    clients = len(set((r["retailer"], r["client"]) for r in rows))
    print(f"📊 Stats: {total_ads} ads across {retailers} retailers, {clients} clients")


if __name__ == "__main__":
    build_manifest()
