#!/usr/bin/env python3
"""
Automatically add image paths to JSON files where we can confidently match files to ads.
Only adds paths when there's a clear 1-to-1 match.
"""

import json
import os
import glob
import re
from pathlib import Path

def get_base_dir():
    return Path(__file__).parent.parent

def normalize_brand(brand):
    """Normalize brand name for comparison"""
    return brand.lower().replace(' ', '_').replace("'", '').replace('-', '_')

def extract_timestamp_from_filename(filename):
    """Extract timestamp from image filename"""
    # Format: kroger__brand__type__client__keyword__D2025-10-22_T22-39.00_1.png
    match = re.search(r'D(\d{4}-\d{2}-\d{2}_T\d{2}-\d{2}\.\d{2})', filename)
    if match:
        return match.group(1)
    return None

def extract_timestamp_from_json(json_file):
    """Extract timestamp from JSON filename"""
    # Format: run_results_keyword_2025-10-22_22-39-00.json
    basename = os.path.basename(json_file)
    match = re.search(r'(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})', basename)
    if match:
        ts = match.group(1)
        # Convert to image format: 2025-10-22_22-39-00 -> D2025-10-22_T22-39.00
        parts = ts.split('_')
        date = parts[0]
        time = parts[1].replace('-', '-', 2).replace('-', '.', 1)
        return f"D{date}_T{time}"
    return None

def find_matching_images(client_dir, ad_type, timestamp, brand):
    """Find image files that match the ad criteria"""
    if ad_type == 'TOA':
        subfolder = 'TOA'
    elif ad_type == 'Skyscraper':
        subfolder = 'Skyscraper'
    elif ad_type == 'CuratedCarousel':
        subfolder = 'Carousel'
    else:
        return []
    
    folder = os.path.join(client_dir, subfolder)
    if not os.path.exists(folder):
        return []
    
    # Get all files with matching timestamp
    matching = []
    for filename in os.listdir(folder):
        file_ts = extract_timestamp_from_filename(filename)
        if file_ts == timestamp:
            matching.append(filename)
    
    return matching

def can_confidently_match(ad, matching_files):
    """Determine if we can confidently match this ad to a file"""
    if not matching_files:
        return None
    
    # If only one file, use it
    if len(matching_files) == 1:
        return matching_files[0]
    
    # If multiple files, try to match by brand name
    advertisers = ad.get('advertisers', [])
    if not advertisers or advertisers == ['unknown']:
        return None
    
    # Normalize brand names
    ad_brands = [normalize_brand(b) for b in advertisers]
    
    # Check each file
    for filename in matching_files:
        # Extract brand from filename: kroger__BRAND__type__client__keyword__timestamp_index.png
        parts = filename.split('__')
        if len(parts) >= 2:
            file_brand = normalize_brand(parts[1])
            
            # Check if any ad brand matches file brand
            if file_brand in ad_brands or any(file_brand in b or b in file_brand for b in ad_brands):
                return filename
    
    return None

def process_json_file(json_file, dry_run=False):
    """Process a single JSON file and add image paths where possible"""
    try:
        with open(json_file, 'r') as f:
            data = json.load(f)
    except Exception as e:
        return 0, f"Error reading: {e}"
    
    # Get timestamp and client
    timestamp = extract_timestamp_from_json(json_file)
    if not timestamp:
        return 0, "Could not extract timestamp"
    
    client_dir = os.path.dirname(os.path.dirname(json_file))
    
    updated_count = 0
    
    for result in data.get('results', []):
        for ad in result.get('ads', []):
            ad_type = ad.get('type')
            
            # Determine path field
            if ad_type == 'TOA':
                path_field = 'toa_image_path'
                subfolder = 'TOA'
            elif ad_type == 'Skyscraper':
                path_field = 'skyscraper_image_path'
                subfolder = 'Skyscraper'
            elif ad_type == 'CuratedCarousel':
                path_field = 'carousel_image_path'
                subfolder = 'Carousel'
            else:
                continue
            
            # Skip if already has path
            if path_field in ad and ad[path_field]:
                continue
            
            # Find matching images
            matching_files = find_matching_images(client_dir, ad_type, timestamp, ad.get('advertisers', []))
            
            # Try to match
            matched_file = can_confidently_match(ad, matching_files)
            
            if matched_file:
                rel_path = f"{subfolder}/{matched_file}"
                if not dry_run:
                    ad[path_field] = rel_path
                updated_count += 1
    
    # Save if changes were made
    if updated_count > 0 and not dry_run:
        try:
            with open(json_file, 'w') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return updated_count, "Success"
        except Exception as e:
            return 0, f"Error writing: {e}"
    
    return updated_count, "Success" if updated_count > 0 else "No matches"

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Auto-add image paths to JSON files')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be added without making changes')
    parser.add_argument('--limit', type=int, help='Limit number of files to process')
    args = parser.parse_args()
    
    base_dir = get_base_dir()
    
    print("🔍 Scanning for JSON files with missing image paths...\n")
    
    # Find all JSON files with missing paths
    json_files = []
    for retailer in ['kroger', 'walmart', 'instacart']:
        pattern = str(base_dir / f'output/{retailer}/*/runs/*.json')
        for json_file in glob.glob(pattern):
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
                    json_files.append(json_file)
            except:
                continue
    
    if not json_files:
        print("✅ All JSON files have image paths!")
        return 0
    
    print(f"📋 Found {len(json_files)} file(s) with missing paths\n")
    
    if args.limit:
        json_files = json_files[:args.limit]
        print(f"⚠️  Processing first {len(json_files)} files\n")
    
    if args.dry_run:
        print("🔍 DRY RUN - No changes will be made\n")
    
    total_updated = 0
    success_count = 0
    
    for i, json_file in enumerate(json_files, 1):
        rel_path = json_file.replace(str(base_dir), '').lstrip('/')
        
        updated, status = process_json_file(json_file, dry_run=args.dry_run)
        
        if updated > 0:
            icon = "✅" if not args.dry_run else "🔍"
            print(f"[{i}/{len(json_files)}] {icon} {rel_path}")
            print(f"          Added {updated} path(s)")
            total_updated += updated
            success_count += 1
        elif i <= 10 or args.dry_run:  # Show first 10 or all in dry-run
            print(f"[{i}/{len(json_files)}] ⚠️  {rel_path}")
            print(f"          {status}")
    
    if success_count < len(json_files) and not args.dry_run:
        print(f"\n... ({len(json_files) - success_count} files with no confident matches)")
    
    print(f"\n📊 Summary:")
    print(f"  📁 Files processed: {len(json_files)}")
    print(f"  ✅ Files updated: {success_count}")
    print(f"  🖼️  Total paths added: {total_updated}")
    print(f"  ⚠️  Files with no matches: {len(json_files) - success_count}")
    
    if args.dry_run:
        print(f"\n💡 Run without --dry-run to apply changes")
    
    return 0

if __name__ == '__main__':
    import sys
    sys.exit(main())
