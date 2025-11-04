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
from pathlib import Path
from collections import defaultdict

def load_brands_config():
    """Load brands.json and create mapping of all names to canonical"""
    with open('config/brands.json') as f:
        brands = json.load(f)
    
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

def main():
    logo_dir = Path('output/brand_logos')
    db_path = logo_dir / 'brand_logo_database.json'
    
    # Load brand name mappings
    print("Loading brands.json...")
    name_to_canonical = load_brands_config()
    
    # Load logo database
    print("Loading logo database...")
    with open(db_path) as f:
        logo_db = json.load(f)
    
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
    
    if orphaned_files:
        print(f"\nOrphaned files (first 10):")
        for file in sorted(orphaned_files)[:10]:
            print(f"  {file}")
    
    if unmapped_brands:
        print(f"\nUnmapped brands (not in brands.json, first 10):")
        for slug, brand in unmapped_brands[:10]:
            print(f"  {brand}")
    
    # Save updated database
    logo_db['brands'] = new_brands_db
    
    backup_path = db_path.with_suffix('.json.backup')
    print(f"\nBacking up to {backup_path}...")
    with open(backup_path, 'w') as f:
        json.dump(logo_db, f, indent=2)
    
    print(f"Writing updated database...")
    with open(db_path, 'w') as f:
        json.dump(logo_db, f, indent=2)
    
    print(f"\n✅ Done! New DB has {len(new_brands_db)} entries")

if __name__ == '__main__':
    main()
