#!/usr/bin/env python3
"""
Brand Logo Gap Report

Identifies brands in ad cards that don't have logos yet.
Useful for prioritizing which brands need logos added to the database.
"""

import json
import sys
import requests
import re
import os
from pathlib import Path

BRAND_LOGO_DB_PATH = Path(os.getenv("BRAND_LOGO_DB_PATH", "output/brand_logos/brand_logo_database.json"))
BRAND_LEXICON_PATH = Path(os.getenv("BRAND_LEXICON_PATH", "config/brands.json"))


def brand_slug(name: str) -> str:
    """Normalize to DB's underscore keys"""
    return re.sub(r'[^a-z0-9]+', '_', (name or '').lower()).strip('_')


def load_logo_db():
    """Load brand logo database"""
    if BRAND_LOGO_DB_PATH.is_file():
        return json.loads(BRAND_LOGO_DB_PATH.read_text()).get("brands", {})
    return {}


def load_lex():
    """Load brand lexicon and create token mapping"""
    out = {"by_token": {}}
    if not BRAND_LEXICON_PATH.is_file():
        return out
    arr = json.loads(BRAND_LEXICON_PATH.read_text())
    for e in arr:
        name = (e.get("name") or "").strip()
        toks = {re.sub(r'[^a-z0-9]+', '', name.lower())}
        for s in e.get("synonyms") or []:
            toks.add(re.sub(r'[^a-z0-9]+', '', (s or '').lower()))
        for t in toks:
            out["by_token"][t] = name
    return out


def canon(lex, raw):
    """Canonicalize brand name via lexicon"""
    if not raw:
        return None
    tok = re.sub(r'[^a-z0-9]+', '', raw.lower())
    return lex["by_token"].get(tok, raw)


def main():
    if len(sys.argv) < 4:
        print("Usage: python3 tools/brand_logo_gap_report.py API_BASE RETAILER CLIENT")
        print("\nExample:")
        print("  python3 tools/brand_logo_gap_report.py http://localhost:5006 instacart blue_bunny")
        sys.exit(1)
    
    api, retailer, client = sys.argv[1:4]
    
    print(f"Fetching cards for {retailer}/{client}...")
    data = requests.get(f"{api}/api/ads/cards?retailer={retailer}&client={client}&page_size=500").json()
    cards = data.get("cards", [])
    print(f"Found {len(cards)} cards\n")
    
    lex = load_lex()
    db = load_logo_db()
    seen = {}
    
    for c in cards:
        b = c.get("brand") or ""
        b = canon(lex, b)
        # Filter out ad types and placeholders
        b = b if b and b.lower() not in {"unknown", "display ad", "shoppable display ad", "shoppable video ad"} else None
        if not b:
            continue
        slug = brand_slug(b)
        has = slug in db
        if slug not in seen:
            seen[slug] = {"brand": b, "has_logo": has, "count": 0}
        seen[slug]["count"] += 1
    
    missing = [v for v in seen.values() if not v["has_logo"]]
    
    print(json.dumps({
        "retailer": retailer,
        "client": client,
        "total": len(seen),
        "missing": len(missing),
        "coverage_pct": ((len(seen) - len(missing)) / len(seen) * 100.0) if seen else 0.0,
        "brands_missing": sorted(missing, key=lambda x: -x["count"])
    }, indent=2))


if __name__ == "__main__":
    main()
