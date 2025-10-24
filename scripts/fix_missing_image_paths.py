#!/usr/bin/env python3
"""
Fix missing image paths in JSON by matching existing image files.
Much faster than re-downloading - just updates the JSON with paths to existing files.
"""

import json
import os
import glob
from pathlib import Path
from datetime import datetime

def get_base_dir():
    """Get the base directory of the project"""
    return Path(__file__).parent.parent

def find_image_for_ad(ad, client_dir, timestamp, ad_index):
    """
    Find the image file that matches this ad.
    Returns relative path from output/ directory.
    """
    ad_type = ad.get('type')
    
    # Determine subfolder
    if ad_type == 'TOA':
        subfolder = 'TOA'
        path_field = 'toa_image_path'
    elif ad_type == 'Skyscraper':
        subfolder = 'Skyscraper'
        path_field = 'skyscraper_image_path'
    elif ad_type == 'CuratedCarousel':
        subfolder = 'Carousel'
        path_field = 'carousel_image_path'
    else:
        return None, None
    
    # Already has path
    if path_field in ad and ad[path_field]:
        return path_field, ad[path_field]
    
    # Build search pattern
    # Format: kroger__brand__type__client__keyword__timestamp_index.png
    folder = os.path.join(client_dir, subfolder)
    
    if not os.path.exists(folder):
        return path_field, None
    
    # Try to find file with matching timestamp
    # Timestamp format in filename: D2025-10-22_T22-39.00 or 2025-10-22_22-39-00
    timestamp_patterns = [
        timestamp.replace('-', '.'),  # 2025-10-22_22-39-00 -> 2025-10-22_22.39.00
        timestamp.replace('_', '_T').replace('-', '.'),  # -> D2025-10-22_T22.39.00
        f"D{timestamp}".replace('-', '.'),
        timestamp,  # exact match
    ]
    
    # Get all files in folder
    all_files = os.listdir(folder)
    
    # Try to match by timestamp and index
    for pattern in timestamp_patterns:
        for filename in all_files:
            if pattern in filename and f"_{ad_index}." in filename:
                # Found a match
                rel_path = os.path.join(subfolder, filename)
                return path_field, rel_path
    
    # Fallback: find any file with matching timestamp (ignore index)
    for pattern in timestamp_patterns:
        matching = [f for f in all_files if pattern in f]
        if matching:
            # Sort and pick based on ad_index
            matching.sort()
            if ad_index <= len(matching):
                rel_path = os.path.join(subfolder, matching[ad_index - 1])
                return path_field, rel_path
    
    return path_field, None

def fix_json_paths(json_file, dry_run=False):
    """Fix missing image paths in a JSON file"""
    try:
        with open(json_file, 'r') as f:
            data = json.load(f)
    except Exception as e:
        return 0, f"Error reading: {e}"
    
    # Extract client and timestamp from filename
    # Format: run_results_{keyword}_{timestamp}.json
    basename = os.path.basename(json_file)
    parts = basename.replace('run_results_', '').replace('.json', '').rsplit('_', 3)
    if len(parts) >= 3:
        timestamp = f"{parts[-3]}_{parts[-2]}-{parts[-1]}"
    else:
        timestamp = ""
    
    # Get client directory
    client_dir = os.path.dirname(os.path.dirname(json_file))
    
    updated_count = 0
    ad_index = 1
    
    for result in data.get('results', []):
        for ad in result.get('ads', []):
            path_field, image_path = find_image_for_ad(ad, client_dir, timestamp, ad_index)
            
            if path_field and image_path and path_field not in ad:
                if not dry_run:
                    ad[path_field] = image_path
                updated_count += 1
            
            ad_index += 1
    
    if updated_count > 0 and not dry_run:
        try:
            with open(json_file, 'w') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return updated_count, "Success"
        except Exception as e:
            return 0, f"Error writing: {e}"
    
    return updated_count, "Success" if updated_count > 0 else "No changes"

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Fix missing image paths in JSON files')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be fixed without making changes')
    parser.add_argument('--limit', type=int, help='Limit number of files to process')
    args = parser.parse_args()
    
    base_dir = get_base_dir()
    
    print("🔍 Scanning for JSON files with missing image paths...\n")
    
    # Find all JSON files
    json_files = []
    for retailer in ['kroger', 'walmart', 'instacart']:
        pattern = str(base_dir / f'output/{retailer}/*/runs/*.json')
        json_files.extend(glob.glob(pattern))
    
    # Filter to only those with missing paths
    missing = []
    for json_file in json_files:
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
            
            has_missing = False
            for result in data.get('results', []):
                for ad in result.get('ads', []):
                    ad_type = ad.get('type')
                    if ad_type == 'TOA' and 'toa_image_path' not in ad:
                        has_missing = True
                    elif ad_type == 'Skyscraper' and 'skyscraper_image_path' not in ad:
                        has_missing = True
                    elif ad_type == 'CuratedCarousel' and 'carousel_image_path' not in ad:
                        has_missing = True
            
            if has_missing:
                missing.append(json_file)
        except:
            continue
    
    if not missing:
        print("✅ All JSON files have image paths!")
        return 0
    
    print(f"📋 Found {len(missing)} file(s) with missing paths\n")
    
    if args.limit:
        missing = missing[:args.limit]
        print(f"⚠️  Processing first {len(missing)} files\n")
    
    if args.dry_run:
        print("🔍 DRY RUN - No changes will be made\n")
    
    total_updated = 0
    success_count = 0
    
    for i, json_file in enumerate(missing, 1):
        rel_path = json_file.replace(str(base_dir), '').lstrip('/')
        
        updated, status = fix_json_paths(json_file, dry_run=args.dry_run)
        
        if updated > 0:
            icon = "✅" if not args.dry_run else "🔍"
            print(f"[{i}/{len(missing)}] {icon} {rel_path}")
            print(f"          Updated {updated} ad(s)")
            total_updated += updated
            success_count += 1
        else:
            print(f"[{i}/{len(missing)}] ⚠️  {rel_path}")
            print(f"          {status}")
    
    print(f"\n📊 Summary:")
    print(f"  📁 Files processed: {len(missing)}")
    print(f"  ✅ Files updated: {success_count}")
    print(f"  🖼️  Total paths added: {total_updated}")
    
    if args.dry_run:
        print(f"\n💡 Run without --dry-run to apply changes")
    
    return 0

if __name__ == '__main__':
    import sys
    sys.exit(main())
