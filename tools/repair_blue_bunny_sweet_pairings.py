#!/usr/bin/env python3
"""Repair Blue Bunny TOA ads that appear as Unknown.

Scope:
- Retailer: kroger
- Any client (bomb_pop and others) under output/kroger/**/runs
- Only TOA ads whose `message` exactly matches:
    "Serve Up Sweet Pairings. Top holiday treats with deliciously soft scoops. Shop Now."

For those ads, this script will:
- Ensure `advertisers = ["Blue Bunny"]`
- Ensure `brand = "Blue Bunny"`
- If image_path / toa_image_path / skyscraper_image_path contains `__unknown__`,
  rename the file on disk to use `__blue_bunny__` and update the JSON path.

Run from project root:
    python tools/repair_blue_bunny_sweet_pairings.py
"""

import json
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = PROJECT_ROOT / "output" / "kroger"

TARGET_MESSAGE = "Serve Up Sweet Pairings. Top holiday treats with deliciously soft scoops. Shop Now."
OLD_TOKEN = "__unknown__"
NEW_TOKEN = "__blue_bunny__"  # matches filename_utils.sanitize_component("Blue Bunny")


def fix_ad(ad: Dict[str, Any], client_dir: Path) -> int:
    """Apply Blue Bunny repair to a single ad.

    Returns number of fields modified.
    """
    modified = 0

    if ad.get("type") != "TOA":
        return 0

    if ad.get("message") != TARGET_MESSAGE:
        return 0

    # Advertisers
    advertisers = ad.get("advertisers")
    if advertisers != ["Blue Bunny"]:
        ad["advertisers"] = ["Blue Bunny"]
        modified += 1

    # Brand
    if ad.get("brand") != "Blue Bunny":
        ad["brand"] = "Blue Bunny"
        modified += 1

    # Paths
    def _fix_path_field(field_name: str) -> None:
        nonlocal modified
        path = ad.get(field_name)
        if not isinstance(path, str):
            return
        if OLD_TOKEN not in path:
            return

        new_rel = path.replace(OLD_TOKEN, NEW_TOKEN)
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

    total_fields = 0
    total_files = 0

    for client_dir in sorted(p for p in OUTPUT_ROOT.iterdir() if p.is_dir()):
        runs_dir = client_dir / "runs"
        if not runs_dir.is_dir():
            continue

        client_changed = 0

        for json_path in sorted(runs_dir.glob("run_results_*.json")):
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
            except Exception:
                continue

            file_changes = 0

            # Per-run shape: top-level ads
            top_ads = data.get("ads")
            if isinstance(top_ads, list):
                for ad in top_ads:
                    file_changes += fix_ad(ad, client_dir)

            # Aggregated shape: results[].ads[]
            for result in data.get("results") or []:
                ads = result.get("ads") or []
                for ad in ads:
                    file_changes += fix_ad(ad, client_dir)

            if file_changes:
                try:
                    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                    total_fields += file_changes
                    total_files += 1
                    client_changed += file_changes
                    print(f"{json_path}: fixed {file_changes} fields")
                except Exception as e:
                    print(f"⚠️ Failed to write {json_path}: {e}")

        if client_changed:
            print(f"Client {client_dir.name}: total fields fixed {client_changed}")

    print(f"\nOverall fields fixed: {total_fields} across {total_files} JSON files")


if __name__ == "__main__":
    main()
