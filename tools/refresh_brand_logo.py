#!/usr/bin/env python3
"""
Refresh a brand logo across the entire system.

Usage:
    python tools/refresh_brand_logo.py "Brand Name"
    python tools/refresh_brand_logo.py "Vital Proteins"

This script:
1. Verifies the logo exists in verified/ folder
2. Updates brand_logo_database.json to point to the correct file
3. Touches the file to update mtime (busts server cache)
4. Prints instructions for frontend cache clearing
"""

import sys
import json
import os
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
VERIFIED_DIR = PROJECT_ROOT / "output" / "brand_logos" / "verified"
DATABASE_PATH = PROJECT_ROOT / "output" / "brand_logos" / "brand_logo_database.json"


def normalize_brand_slug(brand: str) -> str:
    """Convert brand name to slug format for database keys."""
    import unicodedata
    slug = brand.lower()
    slug = unicodedata.normalize('NFD', slug)
    slug = ''.join(c for c in slug if unicodedata.category(c) != 'Mn')
    slug = slug.replace('&', 'and').replace("'", "").replace('.', '')
    slug = slug.replace(' ', '_').replace('-', '_')
    slug = ''.join(c for c in slug if c.isalnum() or c == '_')
    return slug


def find_logo_file(brand: str) -> Path | None:
    """Find logo file in verified folder matching brand name."""
    slug = normalize_brand_slug(brand)
    
    for ext in ['.png', '.jpg', '.jpeg', '.svg', '.webp', '.gif']:
        candidate = VERIFIED_DIR / f"{slug}{ext}"
        if candidate.exists():
            return candidate
    
    # Try case-insensitive search
    for f in VERIFIED_DIR.iterdir():
        if f.is_file():
            file_slug = normalize_brand_slug(f.stem)
            if file_slug == slug:
                return f
    
    return None


def update_database(brand: str, logo_file: Path) -> bool:
    """Update brand_logo_database.json with the logo file."""
    slug = normalize_brand_slug(brand)
    rel_path = f"verified/{logo_file.name}"
    
    # Load existing database
    if DATABASE_PATH.exists():
        with open(DATABASE_PATH, 'r') as f:
            db = json.load(f)
    else:
        db = {"brands": {}}
    
    # Update or create entry
    if "brands" not in db:
        db["brands"] = {}
    
    db["brands"][slug] = {
        "brand_name": brand,
        "source": "manual_refresh",
        "logo_file": rel_path,
        "updated_at": datetime.now().isoformat()
    }
    
    # Save
    with open(DATABASE_PATH, 'w') as f:
        json.dump(db, f, indent=2)
    
    return True


def touch_file(path: Path):
    """Update file mtime to bust caches."""
    path.touch()


def main():
    if len(sys.argv) < 2:
        print("Usage: python tools/refresh_brand_logo.py 'Brand Name'")
        sys.exit(1)
    
    brand = sys.argv[1]
    print(f"\n🔄 Refreshing logo for: {brand}")
    print("=" * 50)
    
    # 1. Find logo file
    logo_file = find_logo_file(brand)
    if not logo_file:
        print(f"❌ No logo found in {VERIFIED_DIR}")
        print(f"   Expected filename like: {normalize_brand_slug(brand)}.png")
        sys.exit(1)
    
    print(f"✅ Found logo: {logo_file.name}")
    
    # 2. Touch file to update mtime (busts ETag cache)
    old_mtime = logo_file.stat().st_mtime
    touch_file(logo_file)
    new_mtime = logo_file.stat().st_mtime
    print(f"✅ Updated mtime: {old_mtime:.0f} → {new_mtime:.0f}")
    
    # 3. Update database
    if update_database(brand, logo_file):
        print(f"✅ Updated brand_logo_database.json")
    
    # 4. Instructions
    print("\n" + "=" * 50)
    print("📋 Next steps:")
    print("   1. Hard refresh browser (Cmd+Shift+R)")
    print("   2. Or open in incognito window")
    print("   3. Logo will auto-update within 24h for other users")
    print("\n✨ Done!")


if __name__ == "__main__":
    main()
