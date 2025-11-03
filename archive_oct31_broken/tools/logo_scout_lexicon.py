#!/usr/bin/env python3
"""
LogoScout Lexicon - Fetch logos for all brands in config/brands.json

This scans your canonical brand lexicon and fetches missing logos,
ensuring every brand in your lexicon has a logo file.
"""

import json
import sys
from pathlib import Path

# Import LogoScout functions
sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.logo_scout import (
    load_database, save_database, normalize_brand_key,
    fetch_logo_for_brand, ensure_dirs
)

BRAND_LEXICON = Path("config/brands.json")


def main():
    if not BRAND_LEXICON.exists():
        print("❌ config/brands.json not found")
        return 1
    
    # Load lexicon
    lexicon = json.loads(BRAND_LEXICON.read_text())
    print(f"📚 Loaded {len(lexicon)} brands from config/brands.json")
    
    # Load logo database
    ensure_dirs()
    db = load_database()
    print(f"🖼️  Current database has {len(db['brands'])} logos")
    print()
    
    # Find brands without logos
    missing = []
    for entry in lexicon:
        brand = entry.get("name", "").strip()
        if not brand:
            continue
        
        brand_key = normalize_brand_key(brand)
        if brand_key not in db.get("brands", {}):
            missing.append(brand)
    
    print(f"🔍 Found {len(missing)} brands without logos:")
    for brand in missing[:10]:
        print(f"  - {brand}")
    if len(missing) > 10:
        print(f"  ... and {len(missing) - 10} more")
    print()
    
    if not missing:
        print("✅ All brands in lexicon have logos!")
        return 0
    
    # Fetch missing logos
    fetched = 0
    not_found = 0
    
    print("🎯 Fetching missing logos...")
    print()
    
    for brand in missing:
        print(f"→ {brand} ...", end=" ", flush=True)
        path, note = fetch_logo_for_brand(db, brand, retailer="lexicon")
        
        if path:
            print(f"✅ {path.name} [{note['source']}]")
            fetched += 1
        else:
            print(f"❌ not found")
            not_found += 1
    
    # Save database
    save_database(db)
    
    print()
    print("=" * 70)
    print(f"✅ Scan complete!")
    print(f"   Fetched: {fetched} new logos")
    print(f"   Not found: {not_found}")
    print(f"   Total logos in database: {len(db['brands'])}")
    print(f"   Coverage: {len(db['brands'])}/{len(lexicon)} ({len(db['brands'])/len(lexicon)*100:.1f}%)")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
