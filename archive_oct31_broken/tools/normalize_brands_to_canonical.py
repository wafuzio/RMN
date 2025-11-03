#!/usr/bin/env python3
"""
Normalize Brand Names to Canonical

Finds JSON advertiser/brand names and image filenames that use synonyms
from the lexicon and updates them to use the main brand name.

This ensures consistency across:
- JSON files (advertisers array)
- Image filenames (brand slug segment)
"""

import json
import os
import glob
import shutil
from pathlib import Path


def load_lexicon(lexicon_path="config/brands.json"):
    """Load brand lexicon and create synonym-to-main-brand mapping"""
    with open(lexicon_path, 'r', encoding='utf-8') as f:
        brands = json.load(f)
    
    # Create mapping: synonym (lowercase) -> main brand name
    synonym_map = {}
    for brand in brands:
        main_name = brand['name']
        # Add the main name itself (for case normalization)
        synonym_map[main_name.lower()] = main_name
        # Add all synonyms
        for syn in brand['synonyms']:
            synonym_map[syn.lower()] = main_name
    
    return synonym_map


def to_slug(text):
    """Convert text to slug format (lowercase with underscores)"""
    return text.lower().replace(' ', '_').replace('-', '_').replace('&', 'and')


def normalize_json_advertisers(json_file, synonym_map, dry_run=True):
    """Normalize advertiser names and image_path fields in JSON files"""
    changes = []
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        modified = False
        
        # Handle both canonical and legacy structures
        ads_to_check = []
        
        if 'ads' in data and isinstance(data['ads'], list):
            ads_to_check = data['ads']
        elif 'results' in data:
            for result in data.get('results', []):
                ads_to_check.extend(result.get('ads', []))
        
        # Check each ad
        for ad in ads_to_check:
            # 1. Normalize advertisers array
            advertisers = ad.get('advertisers', [])
            if advertisers:
                new_advertisers = []
                for adv in advertisers:
                    if adv.lower() in synonym_map:
                        canonical = synonym_map[adv.lower()]
                        if canonical != adv:
                            changes.append({
                                'file': json_file,
                                'type': 'json_advertiser',
                                'old': adv,
                                'new': canonical
                            })
                            new_advertisers.append(canonical)
                            modified = True
                        else:
                            new_advertisers.append(adv)
                    else:
                        new_advertisers.append(adv)
                
                if new_advertisers != advertisers:
                    ad['advertisers'] = new_advertisers
            
            # 2. Normalize image_path field (if it contains a brand slug synonym)
            for path_field in ['image_path', 'screenshot', 'sba_image_path', 'sbv_image_path', 
                               'tile_takeover_image_path', 'toa_image_path', 'skyscraper_image_path']:
                if path_field in ad and ad[path_field]:
                    old_path = ad[path_field]
                    filename = os.path.basename(old_path) if '/' in old_path else old_path
                    
                    # Parse taxonomy filename
                    parts = filename.split('__')
                    if len(parts) >= 2:
                        brand_slug = parts[1]
                        brand_name = brand_slug.replace('_', ' ')
                        
                        if brand_name.lower() in synonym_map:
                            canonical = synonym_map[brand_name.lower()]
                            canonical_slug = to_slug(canonical)
                            
                            if canonical_slug != brand_slug:
                                # Update the path
                                new_parts = parts.copy()
                                new_parts[1] = canonical_slug
                                new_filename = '__'.join(new_parts)
                                
                                if '/' in old_path:
                                    new_path = os.path.join(os.path.dirname(old_path), new_filename)
                                else:
                                    new_path = new_filename
                                
                                changes.append({
                                    'file': json_file,
                                    'type': 'json_image_path',
                                    'field': path_field,
                                    'old': old_path,
                                    'new': new_path
                                })
                                ad[path_field] = new_path
                                modified = True
        
        # Save if modified
        if modified and not dry_run:
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        
        return changes
    
    except Exception as e:
        print(f"[ERROR] Failed to process {json_file}: {e}")
        return []


def normalize_image_filename(image_path, synonym_map, dry_run=True):
    """Normalize brand slug in image filename"""
    filename = os.path.basename(image_path)
    
    # Parse taxonomy filename: retailer__brand_slug__ad_type__client__search__Dts_idx.ext
    parts = filename.split('__')
    if len(parts) < 2:
        return None
    
    retailer = parts[0]
    brand_slug = parts[1]
    
    # Check if brand slug is a synonym
    brand_name = brand_slug.replace('_', ' ')
    
    if brand_name.lower() in synonym_map:
        canonical = synonym_map[brand_name.lower()]
        canonical_slug = to_slug(canonical)
        
        if canonical_slug != brand_slug:
            # Build new filename
            new_parts = parts.copy()
            new_parts[1] = canonical_slug
            new_filename = '__'.join(new_parts)
            new_path = os.path.join(os.path.dirname(image_path), new_filename)
            
            change = {
                'file': image_path,
                'type': 'image_filename',
                'old': brand_slug,
                'new': canonical_slug,
                'old_path': image_path,
                'new_path': new_path
            }
            
            # Rename file
            if not dry_run and os.path.exists(image_path):
                shutil.move(image_path, new_path)
            
            return change
    
    return None


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Normalize brand names to canonical form')
    parser.add_argument('--dry-run', action='store_true', help='Show what would change without making changes')
    parser.add_argument('--apply', action='store_true', help='Actually apply the changes')
    args = parser.parse_args()
    
    dry_run = not args.apply
    
    if dry_run:
        print("🔍 DRY RUN MODE - No changes will be made")
        print("   Use --apply to actually make changes\n")
    else:
        print("✏️  APPLY MODE - Changes will be made\n")
    
    # Load lexicon
    print("Loading brand lexicon...")
    synonym_map = load_lexicon()
    print(f"  Loaded {len(synonym_map)} brand names and synonyms\n")
    
    # Find all JSON files
    print("Scanning JSON files...")
    json_files = []
    for retailer in ['kroger', 'walmart', 'instacart']:
        pattern1 = f'output/{retailer}/*/runs/*.json'
        pattern2 = f'output/{retailer}/*/runs/*/*.json'
        json_files.extend(glob.glob(pattern1))
        json_files.extend(glob.glob(pattern2))
    
    json_files = list(set(json_files))
    print(f"  Found {len(json_files)} JSON files\n")
    
    # Process JSON files
    print("Checking JSON advertisers...")
    json_changes = []
    for json_file in json_files:
        changes = normalize_json_advertisers(json_file, synonym_map, dry_run)
        json_changes.extend(changes)
    
    print(f"  Found {len(json_changes)} advertiser names to normalize\n")
    
    # Find all image files
    print("Scanning image files...")
    image_files = []
    for retailer in ['kroger', 'walmart', 'instacart']:
        for ext in ['png', 'jpg', 'jpeg']:
            pattern1 = f'output/{retailer}/*/*.{ext}'
            pattern2 = f'output/{retailer}/*/*/*.{ext}'
            pattern3 = f'output/{retailer}/*/*/*/*.{ext}'
            image_files.extend(glob.glob(pattern1))
            image_files.extend(glob.glob(pattern2))
            image_files.extend(glob.glob(pattern3))
    
    image_files = list(set(image_files))
    print(f"  Found {len(image_files)} image files\n")
    
    # Process image files
    print("Checking image filenames...")
    image_changes = []
    for image_file in image_files:
        change = normalize_image_filename(image_file, synonym_map, dry_run)
        if change:
            image_changes.append(change)
    
    print(f"  Found {len(image_changes)} image filenames to normalize\n")
    
    # Report results
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    if json_changes:
        print(f"\n📄 JSON Advertiser Changes ({len(json_changes)}):")
        # Group by old -> new
        grouped = {}
        for change in json_changes:
            key = (change['old'], change['new'])
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(change['file'])
        
        for (old, new), files in sorted(grouped.items()):
            print(f"  '{old}' → '{new}' ({len(files)} files)")
            if len(files) <= 5:
                for f in files:
                    print(f"    - {f}")
            else:
                for f in files[:3]:
                    print(f"    - {f}")
                print(f"    ... and {len(files) - 3} more")
    
    if image_changes:
        print(f"\n🖼️  Image Filename Changes ({len(image_changes)}):")
        # Group by old -> new
        grouped = {}
        for change in image_changes:
            key = (change['old'], change['new'])
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(change['old_path'])
        
        for (old, new), files in sorted(grouped.items()):
            print(f"  '{old}' → '{new}' ({len(files)} files)")
            if len(files) <= 5:
                for f in files:
                    print(f"    - {os.path.basename(f)}")
            else:
                for f in files[:3]:
                    print(f"    - {os.path.basename(f)}")
                print(f"    ... and {len(files) - 3} more")
    
    if not json_changes and not image_changes:
        print("\n✅ No changes needed - all brands are already canonical!")
    elif dry_run:
        print(f"\n💡 Run with --apply to make these changes")
    else:
        print(f"\n✅ Changes applied successfully!")
    
    print()


if __name__ == '__main__':
    main()
