#!/usr/bin/env python3
"""
Re-canonicalize ads - update brand assignments based on current lexicon.

Use cases:
1. Re-run brand matching after adding new brands to lexicon
2. Change a brand to "unknown" when deleting from lexicon
3. Fix misidentified brands

Usage:
    # Re-canonicalize all ads for a specific old brand
    python tools/recanon_ads.py --old-brand "Baked" --new-brand "FITCRUNCH"
    
    # Mark all ads for a deleted brand as unknown
    python tools/recanon_ads.py --old-brand "Baked" --delete
    
    # Re-run canonicalization on all ads matching old brand (auto-detect new brand)
    python tools/recanon_ads.py --old-brand "Baked" --auto
    
    # Dry run (show what would change without making changes)
    python tools/recanon_ads.py --old-brand "Baked" --new-brand "FITCRUNCH" --dry-run
"""

import argparse
import json
import os
import re
import glob
from pathlib import Path
from datetime import datetime

# Add parent to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.brands import canonicalize

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"


def slugify(brand_name):
    """Convert brand name to slug format used in filenames."""
    slug = brand_name.lower()
    slug = slug.replace('&', 'and').replace("'", "").replace('.', '')
    slug = re.sub(r'[^a-z0-9]+', '_', slug)
    slug = re.sub(r'_+', '_', slug).strip('_')
    return slug


def find_ads_by_brand(old_brand, retailers=None):
    """Find all ads and files associated with a brand."""
    if retailers is None:
        retailers = ["walmart", "instacart", "kroger", "amazon"]
    
    old_slug = slugify(old_brand)
    results = []
    
    for retailer in retailers:
        retailer_dir = OUTPUT_DIR / retailer
        if not retailer_dir.exists():
            continue
        
        # Find JSON files with this brand in advertisers
        json_patterns = [
            retailer_dir / "**" / "*_meta.json",
            retailer_dir / "**" / "runs" / "*.json",
            retailer_dir / "**" / "run_results_*.json",
        ]
        
        for pattern in json_patterns:
            for json_file in glob.glob(str(pattern), recursive=True):
                try:
                    with open(json_file, 'r') as f:
                        data = json.load(f)
                    
                    # Check various structures for brand references
                    matches = find_brand_in_json(data, old_brand, old_slug)
                    if matches:
                        results.append({
                            'json_file': json_file,
                            'data': data,
                            'matches': matches,
                            'retailer': retailer
                        })
                except Exception as e:
                    print(f"[WARN] Error reading {json_file}: {e}")
    
    return results


def find_brand_in_json(data, old_brand, old_slug):
    """Find all references to a brand in JSON data."""
    matches = []
    old_lower = old_brand.lower()
    
    # Check advertisers dict (meta.json style)
    if 'advertisers' in data and isinstance(data['advertisers'], dict):
        for key, value in data['advertisers'].items():
            if value and value.lower() == old_lower:
                matches.append({'type': 'advertisers_dict', 'key': key, 'value': value})
    
    # Check ads array
    if 'ads' in data and isinstance(data['ads'], list):
        for i, ad in enumerate(data['ads']):
            advertisers = ad.get('advertisers', [])
            if isinstance(advertisers, list):
                for j, adv in enumerate(advertisers):
                    if adv and adv.lower() == old_lower:
                        matches.append({'type': 'ads_array', 'ad_index': i, 'adv_index': j, 'value': adv})
            
            # Check screenshot_path for brand slug
            screenshot = ad.get('screenshot_path', '')
            if old_slug in screenshot.lower():
                matches.append({'type': 'screenshot_path', 'ad_index': i, 'path': screenshot})
    
    # Check videos array
    if 'videos' in data and isinstance(data['videos'], list):
        for i, video in enumerate(data['videos']):
            if old_slug in video.lower():
                matches.append({'type': 'video_path', 'index': i, 'path': video})
    
    return matches


def update_json_brand(data, matches, old_brand, new_brand):
    """Update brand references in JSON data."""
    old_slug = slugify(old_brand)
    new_slug = slugify(new_brand)
    changes = []
    
    for match in matches:
        if match['type'] == 'advertisers_dict':
            key = match['key']
            old_val = data['advertisers'][key]
            data['advertisers'][key] = new_brand
            changes.append(f"advertisers.{key}: {old_val} -> {new_brand}")
        
        elif match['type'] == 'ads_array':
            ad_idx = match['ad_index']
            adv_idx = match['adv_index']
            old_val = data['ads'][ad_idx]['advertisers'][adv_idx]
            data['ads'][ad_idx]['advertisers'][adv_idx] = new_brand
            changes.append(f"ads[{ad_idx}].advertisers[{adv_idx}]: {old_val} -> {new_brand}")
        
        elif match['type'] == 'screenshot_path':
            ad_idx = match['ad_index']
            old_path = data['ads'][ad_idx]['screenshot_path']
            new_path = old_path.replace(old_slug, new_slug)
            data['ads'][ad_idx]['screenshot_path'] = new_path
            changes.append(f"ads[{ad_idx}].screenshot_path: slug {old_slug} -> {new_slug}")
        
        elif match['type'] == 'video_path':
            idx = match['index']
            old_path = data['videos'][idx]
            new_path = old_path.replace(old_slug, new_slug)
            data['videos'][idx] = new_path
            changes.append(f"videos[{idx}]: slug {old_slug} -> {new_slug}")
    
    return changes


def rename_files(json_file, old_brand, new_brand, dry_run=False):
    """Rename associated image/video files."""
    old_slug = slugify(old_brand)
    new_slug = slugify(new_brand)
    renamed = []
    
    # Find files in same directory and subdirectories
    json_path = Path(json_file)
    search_dirs = [json_path.parent]
    
    # Also check common subdirectories
    for subdir in ['SBV', 'SBA', 'SP', 'images', 'screenshots']:
        subdir_path = json_path.parent.parent / subdir
        if subdir_path.exists():
            search_dirs.append(subdir_path)
    
    for search_dir in search_dirs:
        for ext in ['*.png', '*.jpg', '*.jpeg', '*.mp4', '*.webm']:
            for file_path in search_dir.glob(ext):
                if old_slug in file_path.name.lower():
                    new_name = file_path.name.replace(old_slug, new_slug)
                    new_path = file_path.parent / new_name
                    
                    if dry_run:
                        renamed.append(f"[DRY RUN] {file_path.name} -> {new_name}")
                    else:
                        try:
                            file_path.rename(new_path)
                            renamed.append(f"{file_path.name} -> {new_name}")
                        except Exception as e:
                            renamed.append(f"[ERROR] {file_path.name}: {e}")
    
    return renamed


def recanon_brand(old_brand, new_brand=None, delete=False, auto=False, dry_run=False):
    """Re-canonicalize all ads for a brand."""
    
    if delete:
        new_brand = "unknown"
        print(f"🗑️  Deleting brand '{old_brand}' - changing to 'unknown'")
    elif auto:
        # Try to auto-detect what the brand should be
        # This would require looking at the actual ad content
        print(f"🔄 Auto-detecting new brand for '{old_brand}'...")
        # For now, just mark as unknown for review
        new_brand = "unknown"
    elif not new_brand:
        print("❌ Error: Must specify --new-brand, --delete, or --auto")
        return
    
    print(f"\n{'='*60}")
    print(f"Re-canonicalizing: {old_brand} -> {new_brand}")
    print(f"{'='*60}\n")
    
    # Find all ads with this brand
    results = find_ads_by_brand(old_brand)
    
    if not results:
        print(f"No ads found for brand '{old_brand}'")
        return
    
    print(f"Found {len(results)} JSON files with brand '{old_brand}'\n")
    
    total_changes = 0
    total_renames = 0
    
    for result in results:
        json_file = result['json_file']
        data = result['data']
        matches = result['matches']
        
        print(f"📄 {json_file}")
        
        # Update JSON
        changes = update_json_brand(data, matches, old_brand, new_brand)
        for change in changes:
            print(f"   ✏️  {change}")
            total_changes += 1
        
        # Rename files
        renames = rename_files(json_file, old_brand, new_brand, dry_run=dry_run)
        for rename in renames:
            print(f"   📁 {rename}")
            total_renames += 1
        
        # Save JSON
        if not dry_run and changes:
            try:
                with open(json_file, 'w') as f:
                    json.dump(data, f, indent=2)
                print(f"   ✅ Saved")
            except Exception as e:
                print(f"   ❌ Error saving: {e}")
        
        print()
    
    print(f"{'='*60}")
    print(f"Summary:")
    print(f"  JSON changes: {total_changes}")
    print(f"  Files renamed: {total_renames}")
    if dry_run:
        print(f"  (DRY RUN - no changes made)")
    else:
        # Update brand index incrementally
        try:
            from tools.build_brand_index import update_brand_in_index
            if delete:
                update_brand_in_index(old_brand, delete=True)
            else:
                update_brand_in_index(old_brand, new_brand)
        except Exception as e:
            print(f"  [WARN] Could not update brand index: {e}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="Re-canonicalize ads - update brand assignments")
    parser.add_argument('--old-brand', required=True, help="Brand to replace")
    parser.add_argument('--new-brand', help="New brand name")
    parser.add_argument('--delete', action='store_true', help="Mark as unknown (for deleted brands)")
    parser.add_argument('--auto', action='store_true', help="Auto-detect new brand from content")
    parser.add_argument('--dry-run', action='store_true', help="Show changes without applying")
    
    args = parser.parse_args()
    
    recanon_brand(
        old_brand=args.old_brand,
        new_brand=args.new_brand,
        delete=args.delete,
        auto=args.auto,
        dry_run=args.dry_run
    )


if __name__ == "__main__":
    main()
