#!/usr/bin/env python3
"""
Migrate logos from web/static/brand-logos/ to output/brand_logos/
and update brand_logo_database.json
"""

import json
import shutil
from pathlib import Path
from datetime import datetime, timezone

SCOUT_DIR = Path("web/static/brand-logos")
LOGOS_DIR = Path("output/brand_logos")
LOGOS_DB = Path("output/brand_logos/brand_logo_database.json")
SCOUT_INDEX = Path("web/static/brand-logos/index.json")


def load_database():
    if LOGOS_DB.exists():
        return json.loads(LOGOS_DB.read_text())
    return {"brands": {}, "metadata": {"last_updated": None, "total_brands": 0}}


def save_database(db):
    db["metadata"]["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db["metadata"]["total_brands"] = len(db["brands"])
    
    # Sort alphabetically
    sorted_brands = dict(sorted(db["brands"].items(), key=lambda x: x[0].lower()))
    db["brands"] = sorted_brands
    
    LOGOS_DB.write_text(json.dumps(db, indent=2, ensure_ascii=False))


def normalize_brand_key(brand):
    return brand.lower().replace("'", "").replace("&", "and").replace(".", "").replace(" ", "_").strip()


def main():
    if not SCOUT_INDEX.exists():
        print("❌ No LogoScout index found at web/static/brand-logos/index.json")
        return
    
    scout_index = json.loads(SCOUT_INDEX.read_text())
    db = load_database()
    
    migrated = 0
    skipped = 0
    
    print("🔄 Migrating LogoScout logos to main database...")
    print()
    
    for slug, entry in scout_index.items():
        brand = entry.get("brand")
        file = entry.get("file")
        
        if not brand or not file:
            continue
        
        brand_key = normalize_brand_key(brand)
        
        # Skip if already in database
        if brand_key in db["brands"]:
            print(f"✓ {brand}: already in database")
            skipped += 1
            continue
        
        # Check if file exists
        source_path = SCOUT_DIR / file
        if not source_path.exists():
            print(f"⚠️  {brand}: file not found ({file})")
            continue
        
        # Copy file to main logos directory
        dest_path = LOGOS_DIR / file
        shutil.copy2(source_path, dest_path)
        
        # Add to database
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        notes = entry.get("notes", {})
        
        db["brands"][brand_key] = {
            "logo_file": file,
            "retailers": [],  # Will be populated by scrapers
            "first_seen": timestamp,
            "last_seen": timestamp,
            "last_updated": timestamp,
            "source": notes.get("source", "logoscout"),
            "metadata": notes
        }
        
        print(f"✅ {brand}: migrated ({file})")
        migrated += 1
    
    # Save database
    save_database(db)
    
    print()
    print(f"✅ Migration complete!")
    print(f"   Migrated: {migrated} logos")
    print(f"   Skipped: {skipped} (already in database)")
    print(f"   Total brands in database: {len(db['brands'])}")
    print()
    print(f"💡 You can now delete web/static/brand-logos/ if desired")


if __name__ == "__main__":
    main()
