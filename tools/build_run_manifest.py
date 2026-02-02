#!/usr/bin/env python3
"""
Build run manifest for fast metadata-based queries.

Creates a lightweight JSON index of all runs with per-run metadata:
- retailer, client, run_id, timestamp, keyword, ad_count
- Pre-computed brand counts for fast brand gallery loading
- Enables counting and pagination without loading cards

Usage:
    python3 tools/build_run_manifest.py
"""
from __future__ import annotations
import json
import re
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT = PROJECT_ROOT / "output"
CACHE = PROJECT_ROOT / "cache"
CACHE.mkdir(exist_ok=True)
MANIFEST = CACHE / "run_manifest.json"
MANIFEST_TMP = CACHE / "run_manifest.json.tmp"
# Import brand utilities for normalization
try:
    from utils.brand_utils import normalize_brand_for_matching
    from core.brands import canonicalize as canonicalize_brand, is_blacklisted
except ImportError:
    # Fallback if imports fail
    def normalize_brand_for_matching(s):
        return s.lower().replace(" ", "_").replace("-", "_") if s else ""
    def canonicalize_brand(s):
        return s
    def is_blacklisted(s):
        return False


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


def extract_brands_from_doc(doc: dict) -> list[str]:
    """Extract all brand names from ads in a document."""
    brands = []
    
    # Get ads list (canonical or legacy)
    ads = doc.get("ads", [])
    if not ads:
        for blk in doc.get("results", []):
            ads.extend(blk.get("ads", []))
    
    for ad in ads:
        # Try multiple fields for brand name
        advertisers = ad.get("advertisers") or []
        if not advertisers:
            brand = ad.get("brand") or ad.get("advertiser")
            if brand:
                advertisers = [brand]
        
        for adv in advertisers:
            if adv and adv != "Unknown" and not is_blacklisted(adv):
                brands.append(adv)
    
    return brands


def extract_brands_by_type(doc: dict) -> dict[str, list[str]]:
    """Extract brand names grouped by ad type.
    
    Returns: {ad_type: [brand1, brand2, ...], ...}
    """
    brands_by_type = {}
    
    # Get ads list (canonical or legacy)
    ads = doc.get("ads", [])
    if not ads:
        for blk in doc.get("results", []):
            ads.extend(blk.get("ads", []))
    
    for ad in ads:
        # Get ad type
        ad_type = ad.get("type") or ad.get("ad_type") or "Main"
        
        # Try multiple fields for brand name
        advertisers = ad.get("advertisers") or []
        if not advertisers:
            brand = ad.get("brand") or ad.get("advertiser")
            if brand:
                advertisers = [brand]
        
        for adv in advertisers:
            if adv and adv != "Unknown" and not is_blacklisted(adv):
                if ad_type not in brands_by_type:
                    brands_by_type[ad_type] = []
                brands_by_type[ad_type].append(adv)
    
    return brands_by_type


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
    
    # Brand aggregation: retailer -> normalized_key -> {display_name, count}
    brand_counts = {}  # retailer -> norm_key -> count
    brand_counts_by_client = {}  # retailer -> client -> norm_key -> count
    brand_display = {}  # norm_key -> display_name (canonical)
    
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

        # Extract brands for this run (store canonical names)
        run_brands = extract_brands_from_doc(doc)
        # Canonicalize brand names for consistency
        canonical_brands = []
        for b in run_brands:
            cb = canonicalize_brand(b) or b
            if cb and cb != "Unknown":
                canonical_brands.append(cb)
        
        # Extract brands grouped by ad type (for type-filtered queries)
        raw_brands_by_type = extract_brands_by_type(doc)
        canonical_brands_by_type = {}
        for ad_type, brands_list in raw_brands_by_type.items():
            canonical_brands_by_type[ad_type] = []
            for b in brands_list:
                cb = canonicalize_brand(b) or b
                if cb and cb != "Unknown":
                    canonical_brands_by_type[ad_type].append(cb)
        
        rows.append({
            "retailer": retailer,
            "client": client,
            "json_path": rel,
            "run_id": run_id,
            "timestamp": ts,
            "day": day,
            "keyword": keyword,
            "ad_count": ad_count,
            "brands": canonical_brands,  # Per-run brand list for date-filtered queries
            "brands_by_type": canonical_brands_by_type  # Per-run brands grouped by ad type
        })

        # Update daily totals
        d1 = daily_totals.setdefault(retailer, {}).setdefault(client, {}).setdefault(day, 0)
        daily_totals[retailer][client][day] = d1 + ad_count
        
        # Extract and count brands
        brands = extract_brands_from_doc(doc)
        for brand_name in brands:
            # Canonicalize and normalize
            canonical = canonicalize_brand(brand_name) or brand_name
            norm_key = normalize_brand_for_matching(canonical)
            
            if not norm_key:
                continue
            
            # Track display name (prefer canonical)
            if norm_key not in brand_display:
                brand_display[norm_key] = canonical
            
            # Count per retailer
            if retailer not in brand_counts:
                brand_counts[retailer] = {}
            if norm_key not in brand_counts[retailer]:
                brand_counts[retailer][norm_key] = 0
            brand_counts[retailer][norm_key] += 1
            
            # Count per retailer+client
            if retailer not in brand_counts_by_client:
                brand_counts_by_client[retailer] = {}
            if client not in brand_counts_by_client[retailer]:
                brand_counts_by_client[retailer][client] = {}
            if norm_key not in brand_counts_by_client[retailer][client]:
                brand_counts_by_client[retailer][client][norm_key] = 0
            brand_counts_by_client[retailer][client][norm_key] += 1

    # Sort runs newest first
    rows.sort(key=lambda r: r["timestamp"], reverse=True)
    
    # Build brand summary: retailer -> [{brand, count}, ...]
    brand_summary = {}
    for retailer, counts in brand_counts.items():
        total = sum(counts.values())
        brand_list = []
        for norm_key, count in sorted(counts.items(), key=lambda x: x[1], reverse=True):
            brand_list.append({
                "brand": brand_display.get(norm_key, norm_key),
                "count": count,
                "percentage": round((count / total) * 100, 1) if total > 0 else 0
            })
        brand_summary[retailer] = brand_list

    # Build client-level brand summary: retailer -> client -> [{brand, count}, ...]
    brands_by_client = {}
    for retailer, clients_data in brand_counts_by_client.items():
        brands_by_client[retailer] = {}
        for client, counts in clients_data.items():
            total = sum(counts.values())
            brand_list = []
            for norm_key, count in sorted(counts.items(), key=lambda x: x[1], reverse=True):
                brand_list.append({
                    "brand": brand_display.get(norm_key, norm_key),
                    "count": count,
                    "percentage": round((count / total) * 100, 1) if total > 0 else 0
                })
            brands_by_client[retailer][client] = brand_list

    # Atomic write: write to temp file then rename
    manifest_data = {
        "built_at": iso(datetime.utcnow().replace(tzinfo=timezone.utc)),
        "runs": rows,
        "daily_totals": daily_totals,
        "brands": brand_summary,  # Pre-computed brand counts per retailer
        "brands_by_client": brands_by_client  # Pre-computed brand counts per retailer+client
    }
    
    MANIFEST_TMP.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    MANIFEST_TMP.replace(MANIFEST)  # Atomic on POSIX

    elapsed = time.time() - start
    print(f"✅ Manifest: {len(rows)} runs, wrote {MANIFEST} in {elapsed:.2f}s")
    
    # Summary stats
    total_ads = sum(r["ad_count"] for r in rows)
    retailers = len(set(r["retailer"] for r in rows))
    clients = len(set((r["retailer"], r["client"]) for r in rows))
    total_brands = len(brand_display)
    print(f"📊 Stats: {total_ads} ads, {total_brands} brands across {retailers} retailers, {clients} clients")


if __name__ == "__main__":
    build_manifest()
