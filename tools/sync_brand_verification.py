#!/usr/bin/env python3
"""
Sync Brand Verification Status

Syncs verification status from brand_logo_database.json to config/brands.json.
This ensures that when you verify a brand logo, the brand lexicon is also updated.

Run this after verifying logos via logo_verifier_gui.py to keep both files in sync.

Usage:
    python3 tools/sync_brand_verification.py
"""

import json
import re
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).parent.parent
BRAND_LEXICON = PROJECT_ROOT / "config" / "brands.json"
LOGO_DATABASE = PROJECT_ROOT / "output" / "brand_logos" / "brand_logo_database.json"


def normalize_brand_name(name: str) -> str:
    """Normalize brand name for matching (lowercase, no special chars)"""
    normalized = name.lower()
    normalized = normalized.replace("'", "").replace("'", "").replace("`", "")
    normalized = normalized.replace(".", "")
    normalized = normalized.replace(" & ", " and ").replace("&", " and ")
    normalized = " ".join(normalized.split())
    return normalized


def brand_to_slug(name: str) -> str:
    """Convert brand name to database slug format"""
    slug = name.lower()
    slug = slug.replace("'", "").replace("'", "").replace("`", "")
    slug = slug.replace(".", "")
    slug = slug.replace(" & ", " and ").replace("&", " and ")
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = slug.strip("_")
    return slug


def main():
    print("=== Brand Verification Sync ===\n")
    
    # Load brand lexicon
    if not BRAND_LEXICON.exists():
        print(f"❌ Brand lexicon not found: {BRAND_LEXICON}")
        return 1
    
    with open(BRAND_LEXICON, 'r', encoding='utf-8') as f:
        lexicon = json.load(f)
    
    print(f"📚 Loaded {len(lexicon)} brands from config/brands.json")
    
    # Load logo database
    if not LOGO_DATABASE.exists():
        print(f"❌ Logo database not found: {LOGO_DATABASE}")
        return 1
    
    with open(LOGO_DATABASE, 'r', encoding='utf-8') as f:
        logo_db = json.load(f)
    
    verified_in_db = sum(1 for b in logo_db.get("brands", {}).values() if b.get("verified"))
    print(f"🖼️  Loaded {len(logo_db.get('brands', {}))} brands from logo database ({verified_in_db} verified)")
    
    # Build lookup maps
    # Map normalized names and slugs to logo database entries
    logo_lookup = {}
    for slug, data in logo_db.get("brands", {}).items():
        brand_name = data.get("brand_name", "")
        if brand_name:
            normalized = normalize_brand_name(brand_name)
            logo_lookup[normalized] = data
        # Also index by slug
        logo_lookup[slug] = data
    
    # Sync verification status
    updated_count = 0
    already_verified = 0
    not_found = 0
    
    for brand in lexicon:
        brand_name = brand.get("name", "")
        if not brand_name:
            continue
        
        # Check if already verified in lexicon
        if brand.get("verified", False):
            already_verified += 1
            continue
        
        # Try to find in logo database
        normalized = normalize_brand_name(brand_name)
        slug = brand_to_slug(brand_name)
        
        logo_data = logo_lookup.get(normalized) or logo_lookup.get(slug)
        
        if logo_data and logo_data.get("verified"):
            # Update verification status
            brand["verified"] = True
            updated_count += 1
            print(f"✓ Verified: {brand_name}")
        elif not logo_data:
            not_found += 1
    
    # Save updated lexicon
    if updated_count > 0:
        # Sort alphabetically by name
        lexicon.sort(key=lambda x: x.get("name", "").lower())
        
        with open(BRAND_LEXICON, 'w', encoding='utf-8') as f:
            json.dump(lexicon, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Updated {updated_count} brands in config/brands.json")
    else:
        print(f"\n✅ No updates needed - all brands already in sync")
    
    # Summary
    print(f"\n📊 Summary:")
    print(f"   Already verified in lexicon: {already_verified}")
    print(f"   Newly verified from logo DB: {updated_count}")
    print(f"   Not found in logo DB: {not_found}")
    print(f"   Total verified in lexicon: {already_verified + updated_count}")
    
    return 0


if __name__ == "__main__":
    exit(main())
