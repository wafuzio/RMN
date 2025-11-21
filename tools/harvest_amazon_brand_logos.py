#!/usr/bin/env python3
"""Harvest Amazon brand logos from existing run_results JSONs.

This is a post-processing tool. It scans:

- output/amazon/**/runs/run_results_*.json

For each ad:
- Picks a brand name (prefer brand_canonical, then brand)
- Picks a logo/image URL (prefer brand_logo_url, then product_image_url, then image_url)
- Calls BrandLogoDatabase.add_brand_logo(brand, logo_url, retailer="amazon", metadata=...)

Usage:
    python3 tools/harvest_amazon_brand_logos.py
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, Optional

from brand_logo_database import BrandLogoDatabase

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "output" / "amazon"


def iter_run_results() -> Path:
    """Yield all Amazon run_results JSON paths under output/amazon/**/runs/"""
    if not OUTPUT_DIR.exists():
        return
    pattern = "**/runs/run_results_*.json"
    for path in OUTPUT_DIR.glob(pattern):
        if path.is_file():
            yield path


def load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️  Skipping malformed JSON {path}: {e}")
        return None


def pick_brand(ad: Dict[str, Any]) -> Optional[str]:
    """Choose a brand string for logo purposes.

    Priority:
    - brand_canonical
    - brand
    """
    brand_canon = ad.get("brand_canonical")
    brand = ad.get("brand") or None

    for cand in (brand_canon, brand):
        if cand and isinstance(cand, str) and cand.strip() and cand.strip().lower() != "unknown":
            return cand.strip()
    return None


def pick_logo_url(ad: Dict[str, Any]) -> Optional[str]:
    """Choose the best available logo/image URL for a brand.

    Priority:
    - brand_logo_url (explicit SB brand logo)
    - product_image_url (SBV product image)
    - image_url (generic image field, if ever populated)
    """
    for key in ("brand_logo_url", "product_image_url", "image_url"):
        val = ad.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def main() -> None:
    db = BrandLogoDatabase(str(PROJECT_ROOT))

    total_files = 0
    total_ads_seen = 0
    total_added = 0

    for json_path in iter_run_results():
        total_files += 1
        doc = load_json(json_path)
        if not doc:
            continue

        retailer = doc.get("retailer") or "amazon"
        if retailer != "amazon":
            continue

        client = doc.get("client") or "unknown"
        run_id = doc.get("run_id") or doc.get("ts") or "unknown"
        ads = doc.get("ads") or []

        rel_json = json_path.relative_to(PROJECT_ROOT).as_posix()

        for ad in ads:
            total_ads_seen += 1

            brand = pick_brand(ad)
            if not brand:
                continue

            logo_url = pick_logo_url(ad)
            if not logo_url:
                continue

            ad_type = ad.get("type") or "Unknown"
            subtype = ad.get("subtype") or None

            meta = {
                "retailer": retailer,
                "client": client,
                "run_id": run_id,
                "type": ad_type,
                "subtype": subtype,
                "source_json": rel_json,
            }

            ok = db.add_brand_logo(brand, logo_url, retailer=retailer, metadata=meta)
            if ok:
                total_added += 1

    print("=== Amazon Brand Logo Harvest ===")
    print(f"Scanned run_results files: {total_files}")
    print(f"Ads inspected: {total_ads_seen}")
    print(f"Logos added/updated: {total_added}")
    print(f"Database file: {db.db_file}")


if __name__ == "__main__":
    main()
