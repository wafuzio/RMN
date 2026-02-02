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
            # Check brand field directly
            brand = ad.get('brand', '')
            if brand and brand.lower() == old_lower:
                matches.append({'type': 'brand_field', 'ad_index': i, 'value': brand})
            
            # Check brand_canonical field
            brand_canon = ad.get('brand_canonical', '')
            if brand_canon and brand_canon.lower() == old_lower:
                matches.append({'type': 'brand_canonical', 'ad_index': i, 'value': brand_canon})
            
            # Check advertisers array
            advertisers = ad.get('advertisers', [])
            if isinstance(advertisers, list):
                for j, adv in enumerate(advertisers):
                    if adv and adv.lower() == old_lower:
                        matches.append({'type': 'ads_array', 'ad_index': i, 'adv_index': j, 'value': adv})
            
            # Check screenshot_path for brand slug
            screenshot = ad.get('screenshot_path', '')
            if old_slug in screenshot.lower():
                matches.append({'type': 'screenshot_path', 'ad_index': i, 'path': screenshot})
            
            # Check image_path for brand slug
            image_path = ad.get('image_path', '')
            if image_path and old_slug in image_path.lower():
                matches.append({'type': 'image_path', 'ad_index': i, 'path': image_path})
            
            # Check video_path for brand slug
            video_path = ad.get('video_path', '')
            if video_path and old_slug in video_path.lower():
                matches.append({'type': 'video_path_ad', 'ad_index': i, 'path': video_path})
            
            # Check video_url for brand slug (local video references)
            video_url = ad.get('video_url', '')
            if video_url and old_slug in video_url.lower() and not video_url.startswith('http'):
                matches.append({'type': 'video_url_ad', 'ad_index': i, 'path': video_url})
    
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
        
        elif match['type'] == 'brand_field':
            ad_idx = match['ad_index']
            old_val = data['ads'][ad_idx]['brand']
            data['ads'][ad_idx]['brand'] = new_brand
            changes.append(f"ads[{ad_idx}].brand: {old_val} -> {new_brand}")
        
        elif match['type'] == 'brand_canonical':
            ad_idx = match['ad_index']
            old_val = data['ads'][ad_idx]['brand_canonical']
            data['ads'][ad_idx]['brand_canonical'] = new_brand.lower()
            changes.append(f"ads[{ad_idx}].brand_canonical: {old_val} -> {new_brand.lower()}")
        
        elif match['type'] == 'screenshot_path':
            ad_idx = match['ad_index']
            old_path = data['ads'][ad_idx]['screenshot_path']
            new_path = old_path.replace(old_slug, new_slug)
            data['ads'][ad_idx]['screenshot_path'] = new_path
            changes.append(f"ads[{ad_idx}].screenshot_path: slug {old_slug} -> {new_slug}")
        
        elif match['type'] == 'image_path':
            ad_idx = match['ad_index']
            old_path = data['ads'][ad_idx]['image_path']
            new_path = old_path.replace(old_slug, new_slug)
            data['ads'][ad_idx]['image_path'] = new_path
            changes.append(f"ads[{ad_idx}].image_path: slug {old_slug} -> {new_slug}")
        
        elif match['type'] == 'video_path_ad':
            ad_idx = match['ad_index']
            old_path = data['ads'][ad_idx]['video_path']
            new_path = old_path.replace(old_slug, new_slug)
            data['ads'][ad_idx]['video_path'] = new_path
            changes.append(f"ads[{ad_idx}].video_path: slug {old_slug} -> {new_slug}")
        
        elif match['type'] == 'video_url_ad':
            ad_idx = match['ad_index']
            old_path = data['ads'][ad_idx]['video_url']
            new_path = old_path.replace(old_slug, new_slug)
            data['ads'][ad_idx]['video_url'] = new_path
            changes.append(f"ads[{ad_idx}].video_url: slug {old_slug} -> {new_slug}")
        
        elif match['type'] == 'video_path':
            idx = match['index']
            old_path = data['videos'][idx]
            new_path = old_path.replace(old_slug, new_slug)
            data['videos'][idx] = new_path
            changes.append(f"videos[{idx}]: slug {old_slug} -> {new_slug}")
    
    return changes


def rename_files_for_brand(old_brand, new_brand, dry_run=False):
    """Rename ALL files globally that match the old brand slug.
    
    IMPORTANT: Only renames files that follow the canonical naming convention
    with double-underscore delimiters (e.g., kroger__brand__toa__...).
    Files without this pattern (like search_results_*.png) are skipped to
    prevent accidental corruption from simple string replacement.
    
    This searches the entire output/ directory tree for matching files.
    """
    old_slug = slugify(old_brand)
    new_slug = slugify(new_brand)
    renamed = []
    
    # Safety check: don't process very short slugs that could match unintended substrings
    if len(old_slug) < 3:
        print(f"[WARN] Skipping file renames - old_slug '{old_slug}' is too short (< 3 chars)")
        return renamed
    
    # Search entire output directory
    output_dir = Path(__file__).resolve().parents[1] / "output"
    if not output_dir.exists():
        return renamed
    
    # Find all media files recursively
    for ext in ['*.png', '*.jpg', '*.jpeg', '*.mp4', '*.webm']:
        for file_path in output_dir.rglob(ext):
            filename = file_path.name
            
            # Only process files with canonical naming (double-underscore delimiters)
            # Format: retailer__brand__adtype__client__searchterm__timestamp.ext
            if '__' not in filename:
                continue
            
            parts = filename.split('__')
            if len(parts) < 2:
                continue
            
            # The brand slug is in the second segment (parts[1])
            # Only rename if the brand segment matches exactly
            brand_segment = parts[1].lower()
            if brand_segment != old_slug:
                continue
            
            # Replace only the brand segment (not arbitrary substrings)
            parts[1] = new_slug
            new_name = '__'.join(parts)
            new_path = file_path.parent / new_name
            
            if dry_run:
                renamed.append(f"[DRY RUN] {filename} -> {new_name}")
            else:
                try:
                    file_path.rename(new_path)
                    renamed.append(f"{filename} -> {new_name}")
                except Exception as e:
                    renamed.append(f"[ERROR] {filename}: {e}")
    
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
        
        # Save JSON
        if not dry_run and changes:
            try:
                with open(json_file, 'w') as f:
                    json.dump(data, f, indent=2)
                print(f"   ✅ Saved")
            except Exception as e:
                print(f"   ❌ Error saving: {e}")
        
        print()
    
    # Rename files globally (once, not per-JSON)
    print(f"\n📁 Renaming files globally...")
    renames = rename_files_for_brand(old_brand, new_brand, dry_run=dry_run)
    for rename in renames:
        print(f"   {rename}")
        total_renames += 1
    
    print(f"\n{'='*60}")
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
