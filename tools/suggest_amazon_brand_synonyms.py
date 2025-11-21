#!/usr/bin/env python3
"""
Suggest new brand lexicon entries/synonyms based on Amazon runs.

Reads:
- output/brand_index.json (built by tools/build_brand_index.py)
- config/brands.json (canonical brand lexicon)

Prints a human-readable report of brand names that appear in Amazon runs
but are not currently present in the lexicon as either a canonical name
("name") or a synonym.

Usage:
    python3 tools/suggest_amazon_brand_synonyms.py
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Set

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BRAND_INDEX_PATH = PROJECT_ROOT / "output" / "brand_index.json"
BRANDS_CONFIG_PATH = PROJECT_ROOT / "config" / "brands.json"


def load_brand_index() -> Dict:
    if not BRAND_INDEX_PATH.exists():
        raise SystemExit(f"brand_index.json not found at {BRAND_INDEX_PATH}. Run tools/build_brand_index.py first.")
    with BRAND_INDEX_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_brands_config() -> list[dict]:
    if not BRANDS_CONFIG_PATH.exists():
        return []
    with BRANDS_CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalized_set_from_lexicon(brands_cfg: list[dict]) -> Set[str]:
    """Return a lowercase set of all known brand tokens (names + synonyms)."""
    known: Set[str] = set()
    for entry in brands_cfg:
        name = entry.get("name") or ""
        if name:
            known.add(name.strip().lower())
        for syn in entry.get("synonyms", []) or []:
            if syn:
                known.add(str(syn).strip().lower())
    return known


def main() -> None:
    brands_cfg = load_brands_config()
    known = normalized_set_from_lexicon(brands_cfg)

    data = load_brand_index()
    index = data.get("index", {})

    # Collect Amazon-only brands from the index keys
    amazon_brands: Dict[str, int] = {}
    for brand_key, entries in index.items():
        if not isinstance(entries, list):
            continue
        # Count only appearances where retailer == "amazon"
        count = sum(1 for e in entries if e.get("retailer") == "amazon")
        if count <= 0:
            continue
        amazon_brands[brand_key] = amazon_brands.get(brand_key, 0) + count

    # Filter to those not known in the lexicon
    unknown_amazon_brands = {
        b: c for b, c in amazon_brands.items() if b.strip().lower() not in known
    }

    # Sort by frequency descending
    sorted_unknown = sorted(unknown_amazon_brands.items(), key=lambda x: x[1], reverse=True)

    print("=== Amazon Brand Lexicon Suggestions ===")
    print(f"Known brands in config/brands.json: {len(brands_cfg)}")
    print(f"Amazon brands seen in brand_index: {len(amazon_brands)}")
    print(f"Amazon brands NOT in lexicon: {len(sorted_unknown)}")
    print()

    if not sorted_unknown:
        print("No unknown Amazon brands found. Lexicon already covers all observed brands.")
        return

    print("Top unknown Amazon brands (brand_key from brand_index → approx. occurrences):")
    print("(Use these to add new entries to config/brands.json as needed.)")
    print()

    for brand, count in sorted_unknown:
        print(f"- {brand}  →  {count} occurrences")


if __name__ == "__main__":
    main()
