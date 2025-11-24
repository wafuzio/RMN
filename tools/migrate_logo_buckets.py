#!/usr/bin/env python3
"""One-time helper to split brand logos into verified/ and unverified/ buckets.

- Reads output/brand_logos/brand_logo_database.json
- Moves logo files into:
    output/brand_logos/verified/
    output/brand_logos/unverified/
  based on the per-brand "verified" flag (default: unverified)
- Normalizes logo_file in the DB to be a path relative to output/brand_logos,
  e.g. "verified/foo.png" or "unverified/bar.png" (no leading brand_logos/).

Run from the project root:
    python tools/migrate_logo_buckets.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGOS_ROOT = ROOT / "output" / "brand_logos"
DB_PATH = LOGOS_ROOT / "brand_logo_database.json"


def main() -> None:
    if not DB_PATH.exists():
        print(f"❌ Logo database not found: {DB_PATH}")
        return
    if not LOGOS_ROOT.exists():
        print(f"❌ Logo directory not found: {LOGOS_ROOT}")
        return

    data = json.loads(DB_PATH.read_text(encoding="utf-8"))
    brands = data.get("brands", {})

    verified_dir = LOGOS_ROOT / "verified"
    unverified_dir = LOGOS_ROOT / "unverified"
    verified_dir.mkdir(parents=True, exist_ok=True)
    unverified_dir.mkdir(parents=True, exist_ok=True)

    moved = 0
    missing = 0

    for brand_key, entry in brands.items():
        logo_file = (entry.get("logo_file", "") or "").strip()
        if not logo_file:
            continue

        # Normalize optional leading brand_logos/ prefix and treat the rest as
        # a path relative to LOGOS_ROOT.
        if logo_file.startswith("brand_logos/"):
            rel = logo_file.split("/", 1)[1]
        else:
            rel = logo_file

        src_path = (LOGOS_ROOT / rel).resolve()
        if not src_path.exists() or not src_path.is_file():
            missing += 1
            continue

        filename = src_path.name
        is_verified = bool(entry.get("verified", False))
        target_dir = verified_dir if is_verified else unverified_dir
        dest_rel = f"{'verified' if is_verified else 'unverified'}/{filename}"
        dest_path = target_dir / filename

        if dest_path == src_path:
            # Already in the correct bucket
            entry["logo_file"] = dest_rel
            continue

        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            src_path.rename(dest_path)
            moved += 1
            entry["logo_file"] = dest_rel
        except Exception as e:
            print(f"⚠️  Failed to move {src_path} → {dest_path}: {e}")

    data["brands"] = brands
    DB_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    print("✅ Migration complete")
    print(f"   Moved files: {moved}")
    print(f"   Missing files (not moved): {missing}")
    print(f"   DB updated: {DB_PATH}")


if __name__ == "__main__":
    main()
