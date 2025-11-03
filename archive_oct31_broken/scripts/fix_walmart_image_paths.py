#!/usr/bin/env python3
"""
Fix Walmart ad image paths and filenames

This script:
1. Renames image files from __unknown__ to the correct brand slug
2. Adds image path fields to the JSON (sbv_image_path, sba_image_path, etc.)
3. Matches images to ads by timestamp and position
"""

import json
import os
import re
import glob
from pathlib import Path

def to_slug(text):
    """Convert text to slug format"""
    return text.lower().replace(' ', '_').replace("'", '').replace('&', 'and')

def find_walmart_runs():
    """Find all Walmart run_results JSON files"""
    base = Path(__file__).parent.parent / "output" / "walmart"
    if not base.exists():
        return []
    
    json_files = []
    for client_dir in base.iterdir():
        if not client_dir.is_dir():
            continue
        
        # Search in runs/ directory
        runs_dir = client_dir / "runs"
        if runs_dir.exists():
            json_files.extend(runs_dir.rglob("run_results_*.json"))
        
        # Also search in timestamped subdirectories directly under client
        for subdir in client_dir.iterdir():
            if subdir.is_dir() and subdir.name.isdigit() and len(subdir.name) >= 8:
                json_files.extend(subdir.glob("run_results_*.json"))
    
    return json_files

def extract_timestamp_from_filename(filename):
    """Extract timestamp from filename (D2025-10-24_T20-13.51)"""
    match = re.search(r'D(\d{4}-\d{2}-\d{2}_T\d{2}-\d{2}\.\d{2})', filename)
    return match.group(1) if match else None

def find_matching_image(ad_type, timestamp, position, client_dir, search_term, debug=False):
    """Find the image file matching this ad"""
    # Map ad types to folder names
    folder_map = {
        'sbv': 'SBV',
        'sba': 'SBA',
        'tile_takeover': 'Tile_Takeover',
        'top_banner': 'Top_Banner'
    }
    
    folder = folder_map.get(ad_type)
    if not folder:
        if debug:
            print(f"    No folder mapping for ad_type: {ad_type}")
        return None
    
    image_dir = client_dir / folder
    if not image_dir.exists():
        if debug:
            print(f"    Image dir doesn't exist: {image_dir}")
        return None
    
    # Convert timestamp format: 2025-10-24_20-13-51 -> D2025-10-24_T20-13.51
    ts_parts = timestamp.split('_')
    if len(ts_parts) == 2:
        date_part = ts_parts[0]
        time_parts = ts_parts[1].split('-')  # Split HH-MM-SS
        if len(time_parts) == 3:
            # Rejoin as HH-MM.SS
            time_part = f"{time_parts[0]}-{time_parts[1]}.{time_parts[2]}"
            image_ts = f"D{date_part}_T{time_part}"
        else:
            if debug:
                print(f"    Invalid time format: {ts_parts[1]}")
            return None
    else:
        if debug:
            print(f"    Invalid timestamp format: {timestamp}")
        return None
    
    # Find images with matching timestamp and position (PNG files specifically)
    search_slug = search_term.replace(' ', '_').lower()
    pattern = f"walmart__*__{ad_type}__*__{search_slug}__{image_ts}_{position}.png"
    
    if debug:
        print(f"    Pattern: {pattern}")
        print(f"    Image dir: {image_dir}")
    
    matches = list(image_dir.glob(pattern))
    if debug:
        print(f"    Matches: {len(matches)}")
    return matches[0] if matches else None

def fix_json_and_images(json_file, dry_run=False):
    """Fix a single JSON file and its associated images"""
    print(f"\n📄 Processing: {json_file.name}")
    
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    # Find client_dir by going up until we find the walmart/ parent
    client_dir = json_file.parent
    while client_dir.name != 'walmart' and client_dir.parent != client_dir:
        if client_dir.parent.name == 'walmart':
            break
        client_dir = client_dir.parent
    client_dir = client_dir.resolve()
    
    timestamp = data.get('timestamp', '')
    search_term = data.get('search_term', '')
    
    changes = []
    updated = False
    
    for result in data.get('results', []):
        for ad in result.get('ads', []):
            ad_type = ad.get('type', '')
            position = ad.get('pos', 1)
            advertiser = ad.get('advertiser', 'unknown')
            
            # Find the PNG image file
            image_file = find_matching_image(ad_type, timestamp, position, client_dir, search_term, debug=False)
            
            if not image_file:
                continue
            
            new_slug = to_slug(advertiser)
            
            # Rename PNG if it has __unknown__
            if '__unknown__' in image_file.name:
                new_name = image_file.name.replace('__unknown__', f'__{new_slug}__')
                new_path = image_file.parent / new_name
                
                if not dry_run:
                    image_file.rename(new_path)
                    changes.append(f"  ✅ Renamed PNG: {image_file.name} -> {new_name}")
                else:
                    changes.append(f"  🔍 Would rename PNG: {image_file.name} -> {new_name}")
                
                image_file = new_path
            
            # Also find and rename the MP4 video file if it exists
            video_file = image_file.with_suffix('.mp4')
            if not video_file.exists():
                # Try finding it with __unknown__ in the name
                video_pattern = image_file.name.replace('.png', '.mp4').replace(f'__{new_slug}__', '__unknown__')
                potential_video = image_file.parent / video_pattern
                if potential_video.exists():
                    video_file = potential_video
            
            if video_file.exists() and '__unknown__' in video_file.name:
                new_video_name = video_file.name.replace('__unknown__', f'__{new_slug}__')
                new_video_path = video_file.parent / new_video_name
                
                if not dry_run:
                    video_file.rename(new_video_path)
                    changes.append(f"  ✅ Renamed MP4: {video_file.name} -> {new_video_name}")
                else:
                    changes.append(f"  🔍 Would rename MP4: {video_file.name} -> {new_video_name}")
                
                video_file = new_video_path
            
            # Add image path to JSON
            path_key = f"{ad_type}_image_path"
            relative_path = image_file.relative_to(client_dir)
            
            if path_key not in ad:
                ad[path_key] = str(relative_path)
                changes.append(f"  ✅ Added {path_key}: {relative_path}")
                updated = True
            
            # Add video path to JSON if video exists
            if video_file.exists():
                video_path_key = f"{ad_type}_video_path"
                relative_video_path = video_file.relative_to(client_dir)
                
                if video_path_key not in ad:
                    ad[video_path_key] = str(relative_video_path)
                    changes.append(f"  ✅ Added {video_path_key}: {relative_video_path}")
                    updated = True
    
    if updated and not dry_run:
        with open(json_file, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        changes.append(f"  💾 Saved JSON")
    
    if changes:
        for change in changes:
            print(change)
        return True
    else:
        print("  ℹ️  No changes needed")
        return False

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Fix Walmart image paths and filenames')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--json', help='Process specific JSON file')
    args = parser.parse_args()
    
    if args.json:
        json_files = [Path(args.json)]
    else:
        json_files = find_walmart_runs()
    
    if not json_files:
        print("❌ No Walmart run_results JSON files found")
        return
    
    print(f"🔍 Found {len(json_files)} JSON file(s) to process")
    if args.dry_run:
        print("🔍 DRY RUN MODE - no changes will be made")
    
    fixed_count = 0
    renamed_images = 0
    renamed_videos = 0
    added_paths = 0
    
    for json_file in json_files:
        result = fix_json_and_images(json_file, dry_run=args.dry_run)
        if result:
            fixed_count += 1
    
    print(f"\n✅ Processed {len(json_files)} file(s), fixed {fixed_count} file(s)")

if __name__ == '__main__':
    main()
