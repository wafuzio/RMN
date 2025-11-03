#!/usr/bin/env python3
"""
Kroger Legacy-to-Canonical Migration Tool

Migrates old Kroger JSON files and renames legacy image files to canonical format.

Old filename format:
  - carousel_ice_cream_bar_2025-10-17_09-10-33_1.png
  - search_results_ice_cream_bar_2025-10-31_10-13-00.png

New canonical format:
  - kroger__brand__carousel__blue_bunny__ice_cream_bar__D2025-10-17_T09-10.33_1.png
  - kroger__brand__toa__blue_bunny__ice_cream_bar__D2025-10-31_T10-13.00_0.png

Usage:
  python3 tools/migrate_kroger_legacy_to_canonical.py --dry-run
  python3 tools/migrate_kroger_legacy_to_canonical.py --write --backup
  python3 tools/migrate_kroger_legacy_to_canonical.py --client blue_bunny --write
"""

import argparse
import json
import os
import re
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
KROGER_ROOT = ROOT / "output" / "kroger"

ALLOWED_FOLDERS = {"TOA", "Skyscraper", "Carousel", "Main", "runs"}

TYPE_MAP = {
    "toa": "TOA",
    "TOA": "TOA",
    "skyscraper": "Skyscraper",
    "Skyscraper": "Skyscraper",
    "carousel": "Carousel",
    "Carousel": "Carousel",
    "curatedcarousel": "Carousel",
    "CuratedCarousel": "Carousel",
}

ISO_TZ = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+\-]\d{2}:\d{2})$")

def to_iso_z_from_legacy(ts: str) -> Optional[str]:
    """Convert legacy timestamp to ISO Z format"""
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

def parse_legacy_filename(filename: str) -> Optional[Dict[str, str]]:
    """
    Parse old Kroger filename formats:
    - carousel_ice_cream_bar_2025-10-17_09-10-33_1.png
    - search_results_ice_cream_bar_2025-10-31_10-13-00.png
    
    Returns dict with: ad_type, keyword, timestamp, index
    """
    # Remove extension
    base = filename.rsplit('.', 1)[0]
    
    # Pattern 1: {adtype}_{keyword}_{YYYY-MM-DD}_{HH-MM-SS}_{index}
    m1 = re.match(r'^(carousel|toa|skyscraper)_(.+?)_(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})_(\d+)$', base, re.IGNORECASE)
    if m1:
        return {
            "ad_type": m1.group(1).lower(),
            "keyword": m1.group(2),
            "date": m1.group(3),
            "hour": m1.group(4),
            "minute": m1.group(5),
            "second": m1.group(6),
            "index": m1.group(7),
        }
    
    # Pattern 2: search_results_{keyword}_{YYYY-MM-DD}_{HH-MM-SS} (assume TOA)
    m2 = re.match(r'^search_results_(.+?)_(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})$', base)
    if m2:
        return {
            "ad_type": "toa",
            "keyword": m2.group(1),
            "date": m2.group(2),
            "hour": m2.group(3),
            "minute": m2.group(4),
            "second": m2.group(5),
            "index": "0",
        }
    
    return None

def build_canonical_filename(
    ad_type: str,
    brand: str,
    client: str,
    keyword: str,
    date: str,
    hour: str,
    minute: str,
    second: str,
    index: str,
    ext: str = ".png"
) -> str:
    """
    Build canonical Kroger filename:
    kroger__brand__adtype__client__keyword__DYYYY-MM-DD_THH-MM.SS_index.ext
    """
    ad_type_canonical = TYPE_MAP.get(ad_type.lower(), ad_type)
    brand_slug = brand.lower().replace(" ", "_").replace("'", "")
    keyword_slug = keyword.replace(" ", "_")
    
    return f"kroger__{brand_slug}__{ad_type_canonical.lower()}__{client}__{keyword_slug}__D{date}_T{hour}-{minute}.{second}_{index}{ext}"

def find_image_path_from_keys(ad: Dict[str, Any]) -> Optional[str]:
    """Find existing image_path in ad data"""
    path = ad.get("image_path") or ad.get("screenshot")
    if path:
        return path
    # Legacy type-specific fields
    for k, v in ad.items():
        if k.endswith("_image_path") and isinstance(v, str) and v:
            return v
    return None

def normalize_ad_type(ad_type: Optional[str]) -> Optional[str]:
    if not ad_type or not isinstance(ad_type, str):
        return None
    return TYPE_MAP.get(ad_type, ad_type)

def migrate_images_in_folder(
    folder_path: Path,
    client: str,
    ad_type: str,
    write: bool,
    backup: bool
) -> Tuple[int, int]:
    """
    Rename legacy image files to canonical format.
    Returns (total_files, renamed_files)
    """
    if not folder_path.exists():
        return (0, 0)
    
    total = 0
    renamed = 0
    
    for file in folder_path.iterdir():
        if not file.is_file():
            continue
        if file.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp', '.mp4'}:
            continue
        
        # Skip if already canonical
        if file.name.startswith("kroger__"):
            continue
        
        total += 1
        
        # Parse legacy filename
        parsed = parse_legacy_filename(file.name)
        if not parsed:
            print(f"  ⚠️  Could not parse: {file.name}")
            continue
        
        # Build canonical filename (use "unknown" as brand for now)
        new_name = build_canonical_filename(
            ad_type=parsed["ad_type"],
            brand="unknown",  # Will be updated by reconciliation tool later
            client=client,
            keyword=parsed["keyword"],
            date=parsed["date"],
            hour=parsed["hour"],
            minute=parsed["minute"],
            second=parsed["second"],
            index=parsed["index"],
            ext=file.suffix
        )
        
        new_path = folder_path / new_name
        
        if not write:
            print(f"  DRY-RUN: {file.name} -> {new_name}")
            renamed += 1
            continue
        
        # Backup if requested
        if backup:
            bak = file.with_suffix(file.suffix + ".bak")
            if not bak.exists():
                shutil.copy2(file, bak)
        
        # Rename
        file.rename(new_path)
        print(f"  ✅ RENAMED: {file.name} -> {new_name}")
        renamed += 1
    
    return (total, renamed)

def build_ad(
    run_id: str,
    idx: int,
    ad: Dict[str, Any],
    client_root: Path,
) -> Dict[str, Any]:
    """Build canonical ad object"""
    raw_type = ad.get("type") or ad.get("ad_type")
    ad_type = normalize_ad_type(raw_type)
    
    # Prefer existing local path
    image_path = find_image_path_from_keys(ad)
    
    # Normalize fields
    brand = ad.get("brand") or ad.get("advertiser")
    advertisers = ad.get("advertisers", [])
    if not advertisers and brand:
        advertisers = [brand]
    
    ad_obj: Dict[str, Any] = {
        "id": f"kroger-{run_id}-{idx}",
        "type": ad_type,
        "brand": brand if isinstance(brand, str) else None,
        "advertisers": advertisers if isinstance(advertisers, list) else [],
        "brand_logo": None,
        "title": ad.get("title"),
        "description": ad.get("description"),
        "cta": ad.get("cta"),
        "href": ad.get("href"),
        "image_url": ad.get("image_url") or ad.get("img"),
        "image_path": image_path if isinstance(image_path, str) else None,
        "products": ad.get("products", []),
        "metadata": {
            "slot": ad.get("slot") or ad.get("pos"),
            "raw_text": ad.get("text") or ad.get("message"),
        },
    }
    
    # Sanity: ensure image_path, if present, starts with allowed folder
    if ad_obj["image_path"]:
        folder = ad_obj["image_path"].split("/", 1)[0]
        if folder not in ALLOWED_FOLDERS:
            ad_obj["metadata"]["note"] = f"unexpected_folder:{folder}"
    
    return ad_obj

def migrate_file(p: Path, write: bool, backup: bool) -> Tuple[bool, str]:
    """
    Migrate a single JSON file to canonical format.
    Returns (changed, message)
    """
    try:
        data = json.loads(p.read_text())
    except Exception as e:
        return (False, f"SKIP: invalid JSON {p}: {e}")
    
    # Detect already-canonical runs
    if isinstance(data.get("ads"), list) and isinstance(data.get("run_id"), str):
        return (False, f"SKIP: appears canonical already {p}")
    
    # Derive run_id and client from path
    run_dir = p.parent
    runs_dir = run_dir.parent
    client_dir = runs_dir.parent
    run_id = run_dir.name
    client = client_dir.name
    
    # Keyword
    keyword = data.get("keyword") or data.get("search_term") or ""
    
    # Timestamp: convert to ISO Z
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
                )
            )
    
    canon = {
        "retailer": "kroger",
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
    ap = argparse.ArgumentParser(description="Migrate legacy Kroger run JSONs and images to canonical schema.")
    ap.add_argument("--write", action="store_true", help="Write changes in place (default is dry-run)")
    ap.add_argument("--backup", action="store_true", help="Write .bak alongside originals when --write is set")
    ap.add_argument("--client", type=str, help="Process only this client (default: all clients)")
    ap.add_argument("--limit", type=int, default=0, help="Limit number of files to process (0=all)")
    ap.add_argument("--images-only", action="store_true", help="Only rename image files, skip JSON migration")
    ap.add_argument("--json-only", action="store_true", help="Only migrate JSON files, skip image renaming")
    args = ap.parse_args()
    
    if not KROGER_ROOT.exists():
        print("No output/kroger directory found.")
        return
    
    # Get list of clients to process
    if args.client:
        clients = [KROGER_ROOT / args.client]
        if not clients[0].exists():
            print(f"Client directory not found: {clients[0]}")
            return
    else:
        clients = [d for d in KROGER_ROOT.iterdir() if d.is_dir()]
    
    print("=" * 60)
    print("Kroger Legacy-to-Canonical Migration Tool")
    print("=" * 60)
    print(f"Mode: {'WRITE' if args.write else 'DRY-RUN'}")
    print(f"Backup: {'YES' if args.backup else 'NO'}")
    print(f"Clients: {len(clients)}")
    print("=" * 60)
    
    total_json = 0
    migrated_json = 0
    total_images = 0
    renamed_images = 0
    
    for client_dir in sorted(clients):
        client = client_dir.name
        print(f"\n📁 Client: {client}")
        
        # Migrate images in ad type folders
        if not args.json_only:
            for folder_name in ["TOA", "Skyscraper", "Carousel", "Main"]:
                folder_path = client_dir / folder_name
                if folder_path.exists():
                    print(f"  📂 {folder_name}/")
                    t, r = migrate_images_in_folder(folder_path, client, folder_name, args.write, args.backup)
                    total_images += t
                    renamed_images += r
        
        # Migrate JSON files
        if not args.images_only:
            jsons = sorted(client_dir.glob("runs/*/run_results_*.json"))
            for p in jsons:
                total_json += 1
                ch, msg = migrate_file(p, write=args.write, backup=args.backup)
                if ch:
                    print(f"  {msg}")
                    migrated_json += 1
                if args.limit and migrated_json >= args.limit:
                    break
    
    print("\n" + "=" * 60)
    print("Migration Summary")
    print("=" * 60)
    print(f"JSON files scanned: {total_json}")
    print(f"JSON files migrated: {migrated_json}")
    print(f"Image files scanned: {total_images}")
    print(f"Image files renamed: {renamed_images}")
    print(f"Mode: {'WRITE' if args.write else 'DRY-RUN'}")
    print("=" * 60)

if __name__ == "__main__":
    main()
