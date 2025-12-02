#!/usr/bin/env python3
"""
Sync verified logos to brand_logo_database.json.

Scans the verified/ folder and ensures all logos are registered in the database.
Also touches files to update mtime for cache busting.

Run automatically during server restart or manually:
    python tools/sync_verified_logos.py
"""

import json
import os
import unicodedata
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
VERIFIED_DIR = PROJECT_ROOT / "output" / "brand_logos" / "verified"
DATABASE_PATH = PROJECT_ROOT / "output" / "brand_logos" / "brand_logo_database.json"


def normalize_brand_slug(filename: str) -> str:
    """Convert filename to slug format for database keys.
    
    IMPORTANT: Preserve hyphens vs underscores to match existing database keys.
    """
    # Remove extension
    slug = Path(filename).stem.lower()
    slug = unicodedata.normalize('NFD', slug)
    slug = ''.join(c for c in slug if unicodedata.category(c) != 'Mn')
    slug = slug.replace('&', 'and').replace("'", "").replace('.', '')
    # Keep hyphens and underscores as-is (don't convert hyphens to underscores)
    slug = ''.join(c for c in slug if c.isalnum() or c in '_-')
    return slug


def find_existing_entry(db, slug):
    """Find existing entry with either hyphen or underscore variant."""
    # Try exact match first
    if slug in db["brands"]:
        return slug, db["brands"][slug]
    
    # Try alternate variant (hyphen <-> underscore)
    alt_slug = slug.replace('-', '_') if '-' in slug else slug.replace('_', '-')
    if alt_slug in db["brands"]:
        return alt_slug, db["brands"][alt_slug]
    
    return None, None


def slug_to_brand_name(slug: str) -> str:
    """Convert slug back to a readable brand name."""
    # Replace underscores with spaces and title case
    return slug.replace('_', ' ').title()


def main():
    print("=== Verified Logo Sync ===")
    
    if not VERIFIED_DIR.exists():
        print(f"❌ Verified directory not found: {VERIFIED_DIR}")
        return
    
    # Load existing database
    if DATABASE_PATH.exists():
        with open(DATABASE_PATH, 'r') as f:
            db = json.load(f)
    else:
        db = {"brands": {}}
    
    if "brands" not in db:
        db["brands"] = {}
    
    # Scan verified folder
    logo_files = list(VERIFIED_DIR.glob("*"))
    logo_files = [f for f in logo_files if f.is_file() and f.suffix.lower() in ['.png', '.jpg', '.jpeg', '.svg', '.webp', '.gif']]
    
    added = 0
    updated = 0
    
    for logo_file in logo_files:
        slug = normalize_brand_slug(logo_file.name)
        rel_path = f"verified/{logo_file.name}"
        
        # Check if already in database (try both hyphen and underscore variants)
        existing_key, existing = find_existing_entry(db, slug)
        
        if existing:
            needs_update = False
            
            # Ensure brand_name exists (fix legacy entries)
            if "brand_name" not in existing:
                existing["brand_name"] = slug_to_brand_name(existing_key)
                needs_update = True
            
            # Update if path changed
            if existing.get("logo_file") != rel_path:
                existing["logo_file"] = rel_path
                existing["updated_at"] = datetime.now().isoformat()
                needs_update = True
            
            # CRITICAL: Mark as verified since it's in the verified folder
            if not existing.get("verified"):
                existing["verified"] = True
                existing["verified_at"] = datetime.now().isoformat()
                needs_update = True
            
            if needs_update:
                updated += 1
        else:
            # Add new entry - mark as verified since it's in verified folder
            db["brands"][slug] = {
                "brand_name": slug_to_brand_name(slug),
                "source": "verified_sync",
                "logo_file": rel_path,
                "verified": True,
                "verified_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            added += 1
        
        # Touch file to update mtime (cache busting)
        logo_file.touch()
    
    # Save database
    with open(DATABASE_PATH, 'w') as f:
        json.dump(db, f, indent=2)
    
    print(f"Scanned verified logos: {len(logo_files)}")
    print(f"Added to database: {added}")
    print(f"Updated in database: {updated}")
    print(f"Database file: {DATABASE_PATH}")


if __name__ == "__main__":
    main()
