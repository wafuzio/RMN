#!/usr/bin/env python3
"""
Add a brand logo from a local file to the brand logo database

Usage:
    python3 tools/add_logo_from_file.py <brand_name> <logo_file_path>
    
Example:
    python3 tools/add_logo_from_file.py "Conagra Brands" ~/Downloads/conagra_logo.png
"""

import sys
import os
import shutil
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from brand_logo_database import BrandLogoDatabase
from core.brands import canonicalize, add_brand
from utils.time_utils import now_iso_z

def add_logo_from_file(brand_name: str, logo_file_path: str, verified: bool = True):
    """Add a brand logo from a local file"""
    
    logo_file = Path(logo_file_path)
    
    if not logo_file.exists():
        print(f"❌ Logo file not found: {logo_file_path}")
        return False
    
    if not logo_file.suffix.lower() in ['.png', '.jpg', '.jpeg', '.svg', '.webp']:
        print(f"❌ Unsupported file format: {logo_file.suffix}")
        return False
    
    db = BrandLogoDatabase()
    
    # Canonicalize brand name
    canon = canonicalize(brand_name)
    if not canon:
        # Add to lexicon if not found
        add_brand(brand_name)
        canon = brand_name
    
    display_name = canon
    brand_key = db._normalize_brand_name(display_name)
    
    # Check if brand already has a logo
    if brand_key in db.database["brands"]:
        existing = db.database["brands"][brand_key]
        print(f"⚠️  Brand '{display_name}' already has a logo:")
        print(f"   {existing.get('logo_file')}")
        
        response = input("   Replace existing logo? (y/N): ").strip().lower()
        if response != 'y':
            print("   Cancelled.")
            return False
    
    # Determine destination directory (verified or unverified)
    dest_dir = db.verified_dir if verified else db.unverified_dir
    
    # Find next available number for this brand
    ext = logo_file.suffix.lower().lstrip('.')
    next_num = db._find_next_logo_number(brand_key, ext)
    
    # Generate filename
    if next_num == 1:
        filename = f"{brand_key}.{ext}"
    else:
        filename = f"{brand_key}_{next_num}.{ext}"
    
    dest_path = dest_dir / filename
    
    # Copy file to logo directory
    try:
        shutil.copy2(logo_file, dest_path)
        print(f"✅ Copied logo to: {dest_path.relative_to(project_root)}")
    except Exception as e:
        print(f"❌ Error copying file: {e}")
        return False
    
    # Add to database
    relative_path = str(dest_path.relative_to(db.logos_dir))
    
    db.database["brands"][brand_key] = {
        "brand_name": display_name,
        "logo_url": f"file://{logo_file.absolute()}",  # Original source
        "logo_file": relative_path,
        "retailers": ["manual"],
        "first_seen": now_iso_z(),
        "last_seen": now_iso_z(),
        "metadata": {
            "verified": verified,
            "manual_upload": True,
            "original_filename": logo_file.name
        }
    }
    
    db._save_database()
    print(f"✅ Added '{display_name}' to brand logo database")
    print(f"📁 Database: {db.db_file.relative_to(project_root)}")
    print(f"📊 Total brands: {len(db.database['brands'])}")
    
    return True

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 tools/add_logo_from_file.py <brand_name> <logo_file_path>")
        print("\nExample:")
        print('  python3 tools/add_logo_from_file.py "Conagra Brands" ~/Downloads/conagra_logo.png')
        sys.exit(1)
    
    brand_name = sys.argv[1]
    logo_file_path = sys.argv[2]
    verified = "--unverified" not in sys.argv
    
    add_logo_from_file(brand_name, logo_file_path, verified=verified)
