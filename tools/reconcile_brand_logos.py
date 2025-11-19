#!/usr/bin/env python3
"""
Reconcile brand logos, logo database, and brands.json after cleanup.

This script:
1. Finds orphaned logo files (no DB entry)
2. Finds missing logo files (DB entry but no file)
3. Fixes logo_file paths in DB
4. Maps old brand names to new canonical names from brands.json
5. Removes duplicate entries
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

def load_brands_config():
    """Load brands.json and create mapping of all names to canonical"""
    brands_file = Path('config/brands.json')
    if not brands_file.exists():
        print(f"❌ Brands config not found: {brands_file}")
        print("Make sure you're running from the project root directory")
        sys.exit(1)
    
    try:
        with open(brands_file) as f:
            brands = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in brands config: {e}")
        sys.exit(1)
    
    # Map all names (canonical + synonyms) to canonical name
    name_to_canonical = {}
    for brand in brands:
        canonical = brand['name']
        name_to_canonical[canonical] = canonical
        name_to_canonical[canonical.lower()] = canonical
        
        for synonym in brand.get('synonyms', []):
            name_to_canonical[synonym] = canonical
            name_to_canonical[synonym.lower()] = canonical
    
    return name_to_canonical

def slugify(name):
    """Convert brand name to slug"""
    return name.lower().replace(' ', '_').replace('-', '_').replace("'", "").replace("&", "and")

def validate_results(new_brands_db, logo_files):
    """Validate the reconciliation results"""
    issues = []
    
    for slug, entry in new_brands_db.items():
        logo_file = entry.get('logo_file', '')
        if logo_file and logo_file not in logo_files:
            issues.append(f"Still missing: {logo_file}")
    
    if issues:
        print(f"⚠️  Validation found {len(issues)} remaining issues:")
        for issue in issues[:10]:
            print(f"  {issue}")
        if len(issues) > 10:
            print(f"  ... and {len(issues) - 10} more")
    else:
        print("✅ Validation passed - all references point to existing files")
    
    return len(issues) == 0

def main():
    logo_dir = Path('output/brand_logos')
    db_path = logo_dir / 'brand_logo_database.json'
    
    # Check if logo directory exists
    if not logo_dir.exists():
        print(f"❌ Logo directory not found: {logo_dir}")
        print("Run logo_scout.py first to create logos")
        sys.exit(1)
    
    # Check if database exists
    if not db_path.exists():
        print(f"❌ Logo database not found: {db_path}")
        print("Run logo_scout.py first to create the database")
        sys.exit(1)
    
    # Load brand name mappings
    print("Loading brands.json...")
    name_to_canonical = load_brands_config()
    
    # Load logo database
    print("Loading logo database...")
    try:
        with open(db_path) as f:
            logo_db = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in logo database: {e}")
        sys.exit(1)
    
    brands_db = logo_db.get('brands', {})
    
    # Get actual logo files
    print("Scanning logo files...")
    logo_files = {f.name: f for f in logo_dir.glob('*') 
                  if f.is_file() and f.suffix in ['.png', '.jpg', '.jpeg', '.svg', '.webp']}
    
    print(f"\nCurrent state:")
    print(f"  Logo DB entries: {len(brands_db)}")
    print(f"  Actual logo files: {len(logo_files)}")
    print(f"  Canonical brands: {len(set(name_to_canonical.values()))}")
    
    # Find issues
    missing_files = []
    orphaned_files = set(logo_files.keys())
    wrong_paths = []
    unmapped_brands = []
    
    new_brands_db = {}
    
    for slug, entry in brands_db.items():
        brand_name = entry.get('brand_name', '')
        logo_file = entry.get('logo_file', '')
        
        # Fix logo_file path (remove brand_logos/ prefix)
        if logo_file.startswith('brand_logos/'):
            logo_file = logo_file.replace('brand_logos/', '')
            entry['logo_file'] = logo_file
            wrong_paths.append(slug)
        
        # Check if file exists
        if logo_file not in logo_files:
            missing_files.append((slug, brand_name, logo_file))
        else:
            orphaned_files.discard(logo_file)
        
        # Map to canonical brand name
        canonical = name_to_canonical.get(brand_name) or name_to_canonical.get(brand_name.lower())
        
        if canonical:
            # Use canonical name's slug as key
            canonical_slug = slugify(canonical)
            entry['brand_name'] = canonical
            
            # Merge if duplicate
            if canonical_slug in new_brands_db:
                # Keep the entry with more recent last_seen
                existing = new_brands_db[canonical_slug]
                if entry.get('last_seen', '') > existing.get('last_seen', ''):
                    new_brands_db[canonical_slug] = entry
            else:
                new_brands_db[canonical_slug] = entry
        else:
            unmapped_brands.append((slug, brand_name))
            # Keep unmapped brands for now
            new_brands_db[slug] = entry
    
    # Report findings
    print(f"\nIssues found:")
    print(f"  Missing logo files: {len(missing_files)}")
    print(f"  Orphaned logo files: {len(orphaned_files)}")
    print(f"  Wrong paths fixed: {len(wrong_paths)}")
    print(f"  Unmapped brands: {len(unmapped_brands)}")
    print(f"  Deduplicated entries: {len(brands_db) - len(new_brands_db)}")
    
    if missing_files:
        print(f"\nMissing files (first 10):")
        for slug, brand, file in missing_files[:10]:
            print(f"  {brand}: {file}")
        if len(missing_files) > 10:
            print(f"  ... and {len(missing_files) - 10} more")
    
    if orphaned_files:
        print(f"\nOrphaned files (first 10):")
        for file in sorted(orphaned_files)[:10]:
            print(f"  {file}")
        if len(orphaned_files) > 10:
            print(f"  ... and {len(orphaned_files) - 10} more")
    
    if unmapped_brands:
        print(f"\nUnmapped brands (not in brands.json, first 10):")
        for slug, brand in unmapped_brands[:10]:
            print(f"  {brand}")
        if len(unmapped_brands) > 10:
            print(f"  ... and {len(unmapped_brands) - 10} more")
    
    # Validate results before saving
    print(f"\n🔍 Validating results...")
    is_valid = validate_results(new_brands_db, logo_files)
    
    # Save updated database
    logo_db['brands'] = new_brands_db
    
    backup_path = db_path.with_suffix('.json.backup')
    print(f"\n💾 Backing up to {backup_path}...")
    try:
        with open(backup_path, 'w') as f:
            json.dump(logo_db, f, indent=2)
    except Exception as e:
        print(f"❌ Failed to create backup: {e}")
        sys.exit(1)
    
    print(f"💾 Writing updated database...")
    try:
        with open(db_path, 'w') as f:
            json.dump(logo_db, f, indent=2)
    except Exception as e:
        print(f"❌ Failed to write database: {e}")
        print(f"Backup is available at: {backup_path}")
        sys.exit(1)
    
    print(f"\n✅ Done! New DB has {len(new_brands_db)} entries")
    if is_valid:
        print("🎉 All logo references are valid!")
    else:
        print("⚠️  Some issues remain - check the validation output above")

if __name__ == '__main__':
    main()
