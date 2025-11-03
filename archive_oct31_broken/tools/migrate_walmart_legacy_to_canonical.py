#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
WALMART_ROOT = ROOT / "output" / "walmart"

ALLOWED_FOLDERS = {"SBA", "SBV", "Tile_Takeover", "Main", "runs"}

TYPE_MAP = {
    "sba": "SBA",
    "SBA": "SBA",
    "sbv": "SBV",
    "SBV": "SBV",
    "tile_takeover": "Tile_Takeover",
    "Tile_Takeover": "Tile_Takeover",
}

ISO_TZ = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+\-]\d{2}:\d{2})$")

def to_iso_z_from_legacy(ts: str) -> Optional[str]:
    # Accept "YYYY-MM-DD_HH-MM-SS" or "YYYY-MM-DD HH:MM:SS"
    m = re.match(r"^(\d{4}-\d{2}-\d{2})[_ ](\d{2})-(\d{2})-(\d{2})$", ts)
    if m:
        ymd, hh, mm, ss = m.group(1), m.group(2), m.group(3), m.group(4)
        dt = datetime.fromisoformat(f"{ymd}T{hh}:{mm}:{ss}")
        return dt.replace(tzinfo=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    m2 = re.match(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}):(\d{2}):(\d{2})$", ts)
    if m2:
        ymd, hh, mm, ss = m2.group(1), m2.group(2), m2.group(3), m2.group(4)
        dt = datetime.fromisoformat(f"{ymd}T{hh}:{mm}:{ss}")
        return dt.replace(tzinfo=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return None

def legacy_dt_token_for_filenames(ts: str) -> Optional[str]:
    # Convert "YYYY-MM-DD_HH-MM-SS" -> "DYYYY-MM-DD_THH-MM.SS" for filename matching
    m = re.match(r"^(\d{4}-\d{2}-\d{2})[_ ](\d{2})-(\d{2})-(\d{2})$", ts)
    if not m:
        return None
    ymd, hh, mm, ss = m.group(1), m.group(2), m.group(3), m.group(4)
    return f"D{ymd}_T{hh}-{mm}.{ss}"

def find_image_path_from_keys(ad: Dict[str, Any]) -> Optional[str]:
    # Canonical first
    path = ad.get("image_path") or ad.get("screenshot")
    if path:
        return path
    # Legacy type-specific fields (e.g., sba_image_path)
    for k, v in ad.items():
        if k.endswith("_image_path") and isinstance(v, str) and v:
            return v
    return None

def normalize_ad_type(ad_type: Optional[str]) -> Optional[str]:
    if not ad_type or not isinstance(ad_type, str):
        return None
    return TYPE_MAP.get(ad_type, ad_type)

def build_ad(
    run_id: str,
    idx: int,
    ad: Dict[str, Any],
    client_root: Path,
    legacy_ts_token: Optional[str],
) -> Dict[str, Any]:
    raw_type = ad.get("type")
    ad_type = normalize_ad_type(raw_type)  # SBA|SBV|Tile_Takeover or passthrough

    # Prefer existing local path; do not guess aggressively
    image_path = find_image_path_from_keys(ad)

    # Normalize fields
    brand = ad.get("advertiser")
    href = ad.get("href")
    image_url = ad.get("img")
    slot = ad.get("pos")
    raw_text = ad.get("text")

    ad_obj: Dict[str, Any] = {
        "id": f"walmart-{run_id}-{idx}",
        "type": ad_type,
        "brand": brand if isinstance(brand, str) else None,
        "brand_logo": None,
        "title": None,
        "description": None,
        "cta": None,
        "href": href if isinstance(href, str) else None,
        "image_url": image_url if isinstance(image_url, str) else None,
        "image_path": image_path if isinstance(image_path, str) else None,
        "products": [],
        "metadata": {
            "slot": slot if isinstance(slot, int) else None,
            "raw_text": raw_text if isinstance(raw_text, str) else None,
        },
    }

    # Sanity: ensure image_path, if present, starts with allowed folder
    if ad_obj["image_path"]:
        folder = ad_obj["image_path"].split("/", 1)[0]
        if folder not in ALLOWED_FOLDERS:
            # Leave as-is but note in metadata
            ad_obj["metadata"]["note"] = f"unexpected_folder:{folder}"

    return ad_obj

def migrate_file(p: Path, write: bool, backup: bool) -> Tuple[bool, str]:
    """
    Returns (changed, message)
    """
    try:
        data = json.loads(p.read_text())
    except Exception as e:
        return (False, f"SKIP: invalid JSON {p}: {e}")

    # Detect already-canonical runs (top-level ads[] and 14-digit run_id)
    if isinstance(data.get("ads"), list) and isinstance(data.get("run_id"), str) and len(data["run_id"]) == 14:
        return (False, f"SKIP: appears canonical already {p}")

    # Derive run_id and client from path: .../<client>/runs/<run_id>/run_results_*.json
    run_dir = p.parent
    runs_dir = run_dir.parent
    client_dir = runs_dir.parent
    run_id = run_dir.name
    client = client_dir.name

    # Keyword (prefer 'keyword')
    keyword = data.get("keyword") or data.get("search_term") or ""

    # Timestamp: convert to ISO Z (prefer top-level; fallback: results[0].timestamp)
    legacy_ts = data.get("timestamp")
    if not legacy_ts and isinstance(data.get("results"), list) and data["results"]:
        legacy_ts = data["results"][0].get("timestamp")

    iso_ts = to_iso_z_from_legacy(legacy_ts) if legacy_ts else None
    if not iso_ts:
        # Fallback to run_id if parseable
        try:
            dt = datetime.strptime(run_id, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            iso_ts = dt.isoformat(timespec="seconds").replace("+00:00", "Z")
        except Exception:
            iso_ts = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    legacy_token = legacy_dt_token_for_filenames(legacy_ts) if legacy_ts else None

    # Flatten ads from results[].ads[]
    ads: List[Dict[str, Any]] = []
    for r in data.get("results", []):
        for ad in r.get("ads", []):
            ads.append(
                build_ad(
                    run_id=run_id,
                    idx=len(ads) + 1,
                    ad=ad,
                    client_root=client_dir,
                    legacy_ts_token=legacy_token,
                )
            )

    canon = {
        "retailer": "walmart",
        "client": client,
        "keyword": keyword,
        "timestamp": iso_ts,
        "run_id": run_id,
        "ads": ads,
    }

    # No write: just report
    if not write:
        return (True, f"DRY-RUN: would migrate {p} -> canonical schema (ads={len(ads)})")

    # Backup
    if backup:
        bak = p.with_suffix(p.suffix + ".bak")
        if not bak.exists():
            bak.write_text(p.read_text())

    # Overwrite in place with canonical payload
    p.write_text(json.dumps(canon, indent=2, ensure_ascii=False))
    return (True, f"MIGRATED: {p} (ads={len(ads)})")

def main():
    ap = argparse.ArgumentParser(description="Migrate legacy Walmart run JSONs to canonical schema.")
    ap.add_argument("--write", action="store_true", help="Write changes in place (default is dry-run)")
    ap.add_argument("--backup", action="store_true", help="Write .bak alongside originals when --write is set")
    ap.add_argument("--limit", type=int, default=0, help="Limit number of files to process (0=all)")
    args = ap.parse_args()

    if not WALMART_ROOT.exists():
        print("No output/walmart directory found.")
        return

    jsons = sorted(WALMART_ROOT.glob("*/runs/*/run_results_*.json"))
    total = 0
    changed = 0
    for p in jsons:
        total += 1
        ch, msg = migrate_file(p, write=args.write, backup=args.backup)
        print(msg)
        if ch:
            changed += 1
        if args.limit and changed >= args.limit:
            break

    print(f"Done. Files scanned={total}, changed={changed}, mode={'WRITE' if args.write else 'DRY-RUN'}.")

if __name__ == "__main__":
    main()
