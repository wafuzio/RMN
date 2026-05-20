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


def _first_uuid(url: str | None) -> str | None:
    """Extract the first UUID from a CDN URL, used as a creative fingerprint."""
    if not url:
        return None
    m = re.search(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        url,
        re.IGNORECASE,
    )
    return m.group(0).lower() if m else None


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


def extract_fingerprints_from_doc(doc: dict) -> list[tuple[str, str]]:
    """Return (fingerprint_key, brand) pairs for ads that have an identified brand.

    Fingerprints are keyed by CDN asset UUIDs (logo_url, image_url) and
    normalized href paths.  They let us propagate known brand names to
    structurally identical ads scraped later where the brand field is null.
    """
    pairs: list[tuple[str, str]] = []
    ads = doc.get("ads", [])
    if not ads:
        for blk in doc.get("results", []):
            ads.extend(blk.get("ads", []))

    for ad in ads:
        brand = ad.get("brand") or ad.get("advertiser") or ""
        if not brand or brand == "Unknown" or is_blacklisted(brand):
            continue

        canonical = canonicalize_brand(brand) or brand

        logo_uuid = _first_uuid(ad.get("logo_url"))
        if logo_uuid:
            pairs.append((f"logo:{logo_uuid}", canonical))

        img_uuid = _first_uuid(ad.get("image_url"))
        if img_uuid:
            pairs.append((f"img:{img_uuid}", canonical))

        href_raw = (ad.get("href") or "").split("?")[0].strip("/").lower()
        if href_raw and len(href_raw) > 12:
            pairs.append((f"href:{href_raw}", canonical))

    return pairs


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


def _rebuild_aggregates(rows: list) -> tuple[dict, dict, dict, dict, dict]:
    """Recompute daily_totals and brand summaries from an in-memory rows list."""
    daily_totals: dict = {}
    brand_counts: dict = {}
    brand_counts_by_client: dict = {}
    brand_display: dict = {}

    for row in rows:
        retailer = row["retailer"]
        client = row["client"]
        day = row["day"]
        ad_count = row["ad_count"]

        d1 = daily_totals.setdefault(retailer, {}).setdefault(client, {}).setdefault(day, 0)
        daily_totals[retailer][client][day] = d1 + ad_count

        for brand_name in row.get("brands", []):
            canonical = canonicalize_brand(brand_name) or brand_name
            norm_key = normalize_brand_for_matching(canonical)
            if not norm_key:
                continue
            brand_display.setdefault(norm_key, canonical)
            brand_counts.setdefault(retailer, {}).setdefault(norm_key, 0)
            brand_counts[retailer][norm_key] += 1
            brand_counts_by_client.setdefault(retailer, {}).setdefault(client, {}).setdefault(norm_key, 0)
            brand_counts_by_client[retailer][client][norm_key] += 1

    return daily_totals, brand_counts, brand_counts_by_client, brand_display


def build_manifest(full: bool = False):
    """Build run manifest from all JSON files.

    Incremental mode (default):
      1. Load existing manifest rows keyed by json_path.
      2. Build the set of all paths currently on disk.
      3. REMOVE entries whose files no longer exist (deleted, moved, renamed).
      4. RE-PROCESS files whose mtime is newer than the last manifest build
         (new files, content changes, taxonomy reassignments, path changes).
      5. Rebuild aggregates (daily totals, brand counts) from the full in-memory
         row set — no extra I/O needed.

    Pass --full to ignore the existing manifest and reprocess everything.
    """
    start = time.time()

    # --- Load existing manifest for incremental mode ---
    existing_rows: dict = {}  # json_path -> row
    manifest_mtime: float = 0.0

    if not full and MANIFEST.exists():
        try:
            existing = json.loads(MANIFEST.read_text(encoding="utf-8"))
            for row in existing.get("runs", []):
                existing_rows[row["json_path"]] = row
            manifest_mtime = MANIFEST.stat().st_mtime
            print(f"📋 Loaded {len(existing_rows)} existing runs (incremental mode)")
        except Exception as e:
            print(f"⚠️  Could not load existing manifest, falling back to full rebuild: {e}")
            existing_rows = {}
            manifest_mtime = 0.0

    print(f"🔍 Scanning for run JSON files...")
    all_json_files = list_run_jsons()

    # Build a set of relative paths that currently exist on disk
    disk_rel_paths = {str(f.relative_to(OUTPUT)) for f in all_json_files}

    if manifest_mtime > 0:
        # Step 1: remove manifest entries for files that no longer exist on disk
        # (handles deletes, moves, taxonomy reassignments)
        before = len(existing_rows)
        existing_rows = {p: r for p, r in existing_rows.items() if p in disk_rel_paths}
        removed = before - len(existing_rows)
        if removed:
            print(f"🗑️  Removed {removed} stale entries (deleted/moved files)")

        # Step 2: re-process files that are new or have changed content since last build
        # 5-second overlap guards against clock skew at the boundary
        json_files = [f for f in all_json_files if f.stat().st_mtime >= manifest_mtime - 5]
        changed = len(json_files)
        print(f"📁 {len(all_json_files)} total files — {changed} new/changed, {removed} removed")

        # Nothing changed — skip the expensive rebuild entirely
        if changed == 0 and removed == 0:
            print(f"✅ Manifest already up to date ({len(existing_rows)} runs, no changes detected)")
            return
    else:
        json_files = all_json_files
        print(f"📁 Found {len(json_files)} files to process (full rebuild)")

    # Creative fingerprint accumulator: fp_key → canonical_brand.
    # Built incrementally as we scan files; merged into the manifest at the end.
    # On incremental rebuilds the existing manifest's fingerprints seed this dict
    # so previously-indexed fingerprints are preserved.
    _pending_fingerprints: dict[str, str] = {}
    if not full:
        existing_manifest = MANIFEST if MANIFEST.exists() else None
        if existing_manifest:
            try:
                old_mf = json.loads(existing_manifest.read_text(encoding="utf-8"))
                _pending_fingerprints.update(old_mf.get("creative_fingerprints", {}))
            except Exception:
                pass

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

        # Collect creative fingerprints (CDN UUIDs / hrefs → brand) for propagation.
        # These are accumulated into the global index built after all files are scanned.
        for fp_key, fp_brand in extract_fingerprints_from_doc(doc):
            # First writer wins — older runs set the canonical brand; newer ones
            # may have null brand and will benefit from the lookup.
            if fp_key not in _pending_fingerprints:
                _pending_fingerprints[fp_key] = fp_brand

        rel = str(jf.relative_to(OUTPUT))
        existing_rows[rel] = {
            "retailer": retailer,
            "client": client,
            "json_path": rel,
            "run_id": run_id,
            "timestamp": ts,
            "day": day,
            "keyword": keyword,
            "ad_count": ad_count,
            "brands": canonical_brands,
            "brands_by_type": canonical_brands_by_type,
        }

    # All rows (existing + newly processed), sorted newest first
    rows = list(existing_rows.values())
    rows.sort(key=lambda r: r["timestamp"], reverse=True)

    # Rebuild aggregates from the full in-memory rows list (fast — no I/O)
    daily_totals, brand_counts, brand_counts_by_client, brand_display = _rebuild_aggregates(rows)
    
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

    # Compute unknown-brand ad counts: runs with ads but no brands extracted.
    # These represent ads where the scraper couldn't identify the advertiser.
    unknown_ad_counts: dict = {}           # {retailer: total_unknown_ads}
    unknown_ad_counts_by_client: dict = {} # {retailer: {client: count}}
    for row in rows:
        if row.get("ad_count", 0) > 0 and not row.get("brands"):
            r = row["retailer"]
            c = row["client"]
            unknown_ad_counts[r] = unknown_ad_counts.get(r, 0) + row["ad_count"]
            unknown_ad_counts_by_client.setdefault(r, {})
            unknown_ad_counts_by_client[r][c] = unknown_ad_counts_by_client[r].get(c, 0) + row["ad_count"]

    # Atomic write: write to temp file then rename
    manifest_data = {
        "built_at": iso(datetime.utcnow().replace(tzinfo=timezone.utc)),
        "runs": rows,
        "daily_totals": daily_totals,
        "brands": brand_summary,              # Pre-computed brand counts per retailer
        "brands_by_client": brands_by_client, # Pre-computed brand counts per retailer+client
        "unknown_ad_counts": unknown_ad_counts,
        "unknown_ad_counts_by_client": unknown_ad_counts_by_client,
        "creative_fingerprints": _pending_fingerprints,  # {fp_key: canonical_brand}
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
    fp_count = len(_pending_fingerprints)
    print(f"📊 Stats: {total_ads} ads, {total_brands} brands across {retailers} retailers, {clients} clients")
    print(f"🔮 Creative fingerprints indexed: {fp_count}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Build run manifest")
    parser.add_argument("--full", action="store_true", help="Force full rebuild from scratch (ignores existing manifest)")
    args = parser.parse_args()
    build_manifest(full=args.full)
