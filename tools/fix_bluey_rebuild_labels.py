#!/usr/bin/env python3
"""Fix mislabelled Blue Buffalo ads that were tagged as Bluey during the 2025-11-24 15:30 replay.

Scope (narrow on purpose):
- Retailer: kroger
- Client: any (but primarily Proactiv)
- Only ads whose JSON image_path contains "D2025-11-24_T15-3"
- Only ads whose advertisers include "Bluey" OR whose image_path includes "__bluey__".

For those ads, this script will:
- Change advertisers entries "Bluey" -> "Blue Buffalo"
- If ad.brand == "Bluey", change it to "Blue Buffalo"
- If image_path contains "__bluey__", rename the PNG file on disk, replacing
  that segment with "__blue_buffalo__" (matching filename_utils.sanitize rules),
  and update image_path accordingly.

Run from project root:
    python tools/fix_bluey_rebuild_labels.py
"""

import json
import os
from pathlib import Path
from typing import Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = PROJECT_ROOT / "output" / "kroger"

TARGET_RUN_DATE_PREFIX = "D2025-11-24_T15-3"  # match D2025-11-24_T15-30.xx and D2025-11-24_T15-31.xx
OLD_TOKEN = "__bluey__"
NEW_TOKEN = "__blue_buffalo__"  # what filename_utils would produce for "Blue Buffalo"


def fix_ad(ad: Dict[str, Any], client_dir: Path) -> int:
    """Apply Bluey -> Blue Buffalo fix for a single ad.

    Returns 1 if the ad was modified, 0 otherwise.
    """
    modified = 0

    # Fix advertisers array
    advertisers = ad.get("advertisers")
    if isinstance(advertisers, list) and advertisers:
        new_advertisers = ["Blue Buffalo" if a == "Bluey" else a for a in advertisers]
        if new_advertisers != advertisers:
            ad["advertisers"] = new_advertisers
            modified += 1

    # Fix brand field
    if ad.get("brand") == "Bluey":
        ad["brand"] = "Blue Buffalo"
        modified += 1

    # Fix image_path / type-specific paths and rename files if needed
    def _fix_path_field(field_name: str) -> None:
        nonlocal modified
        path = ad.get(field_name)
        if not isinstance(path, str) or TARGET_RUN_DATE_PREFIX not in path:
            return
        if OLD_TOKEN not in path:
            return

        new_rel = path.replace(OLD_TOKEN, NEW_TOKEN)

        # Rename file on disk if present
        old_abs = client_dir / path
        new_abs = client_dir / new_rel
        try:
            if old_abs.is_file():
                new_abs.parent.mkdir(parents=True, exist_ok=True)
                old_abs.rename(new_abs)
        except Exception as e:
            print(f"    ⚠️ Failed to rename {old_abs} -> {new_abs}: {e}")

        ad[field_name] = new_rel
        modified += 1

    _fix_path_field("image_path")
    _fix_path_field("toa_image_path")
    _fix_path_field("skyscraper_image_path")

    return modified


def main() -> None:
    if not OUTPUT_ROOT.is_dir():
        print(f"No Kroger output directory at {OUTPUT_ROOT}")
        return

    total_ads_fixed = 0
    total_files_changed = 0

    for client_dir in sorted(p for p in OUTPUT_ROOT.iterdir() if p.is_dir()):
        runs_dir = client_dir / "runs"
        if not runs_dir.is_dir():
            continue

        client_fixed = 0

        for json_path in sorted(runs_dir.glob("run_results_*.json")):
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
            except Exception:
                continue

            file_modified = 0

            # Per-run shape: top-level ads
            top_ads = data.get("ads")
            if isinstance(top_ads, list):
                for ad in top_ads:
                    # Only touch ads that reference the target run-date prefix or have Bluey advertisers
                    img_path = ad.get("image_path", "")
                    advs = ad.get("advertisers") or []
                    if (TARGET_RUN_DATE_PREFIX in str(img_path)) or ("Bluey" in advs):
                        file_modified += fix_ad(ad, client_dir)

            # Aggregated shape: results[].ads[]
            for result in data.get("results") or []:
                ads = result.get("ads") or []
                for ad in ads:
                    img_path = ad.get("image_path", "")
                    advs = ad.get("advertisers") or []
                    if (TARGET_RUN_DATE_PREFIX in str(img_path)) or ("Bluey" in advs):
                        file_modified += fix_ad(ad, client_dir)

            if file_modified:
                try:
                    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                    total_files_changed += 1
                    total_ads_fixed += file_modified
                    client_fixed += file_modified
                    print(f"{json_path}: fixed {file_modified} fields")
                except Exception as e:
                    print(f"⚠️ Failed to write {json_path}: {e}")

        if client_fixed:
            print(f"Client {client_dir.name}: total fields fixed {client_fixed}")

    print(f"\nOverall fields fixed: {total_ads_fixed} across {total_files_changed} JSON files")


if __name__ == "__main__":
    main()
