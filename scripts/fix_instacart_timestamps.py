#!/usr/bin/env python3
"""
Fix Instacart files that have T00-00.00 timestamps.

These files were created with a bug where the time portion was lost.
This script:
1. Finds all files with T00-00.00 in the filename
2. Looks up the correct timestamp from the corresponding JSON run file
3. Renames the files with the correct timestamp
4. Updates the JSON files to reflect the new filenames
"""

import os
import re
import json
import shutil
from pathlib import Path
from datetime import datetime
import argparse


def find_run_file_for_image(image_path: Path) -> tuple:
    """
    Find the JSON run file that contains this image and extract the correct timestamp.
    Returns (json_path, correct_timestamp, ad_index) or (None, None, None)
    """
    # Extract date from filename: D2025-12-05_T00-00.00
    match = re.search(r'D(\d{4}-\d{2}-\d{2})_T00-00\.00_(\d+)', image_path.name)
    if not match:
        return None, None, None
    
    date_str = match.group(1)  # 2025-12-05
    ad_index = match.group(2)  # 1, 2, 3, etc.
    
    # Find runs directory (go up from ad type folder to client, then to runs)
    # Path: output/instacart/client/AdType/filename.png
    # Runs: output/instacart/client/runs/
    client_dir = image_path.parent.parent
    runs_dir = client_dir / 'runs'
    
    if not runs_dir.exists():
        return None, None, None
    
    # Convert date to search pattern: 2025-12-05 -> 20251205
    date_compact = date_str.replace('-', '')
    
    # Find run folders that match this date
    matching_runs = []
    for run_folder in runs_dir.iterdir():
        if run_folder.is_dir() and run_folder.name.startswith(date_compact):
            matching_runs.append(run_folder)
    
    # Also check for flat JSON files
    for json_file in runs_dir.glob(f'*{date_compact}*.json'):
        if json_file.is_file():
            # Check if this JSON contains our image
            try:
                with open(json_file) as f:
                    data = json.load(f)
                for ad in data.get('ads', []):
                    img_field = ad.get('image_path', '')
                    if f'T00-00.00_{ad_index}.' in img_field:
                        # Found it! Extract timestamp from run_id
                        run_id = data.get('run_id', '')
                        if len(run_id) >= 14:
                            # Convert 20251205060144 to 06-01.44
                            time_str = f"{run_id[8:10]}-{run_id[10:12]}.{run_id[12:14]}"
                            return json_file, time_str, ad_index
            except:
                pass
    
    # Check nested run folders
    for run_folder in matching_runs:
        for json_file in run_folder.glob('run_results*.json'):
            try:
                with open(json_file) as f:
                    data = json.load(f)
                for ad in data.get('ads', []):
                    img_field = ad.get('image_path', '')
                    if f'T00-00.00_{ad_index}.' in img_field:
                        # Found it! Extract timestamp from run_id
                        run_id = data.get('run_id', '')
                        if len(run_id) >= 14:
                            time_str = f"{run_id[8:10]}-{run_id[10:12]}.{run_id[12:14]}"
                            return json_file, time_str, ad_index
            except:
                pass
    
    return None, None, None


def fix_filename(old_path: Path, correct_time: str) -> Path:
    """Generate the corrected filename."""
    new_name = old_path.name.replace('T00-00.00', f'T{correct_time}')
    return old_path.parent / new_name


def update_json_file(json_path: Path, old_filename: str, new_filename: str) -> bool:
    """Update JSON file to reflect the renamed file."""
    try:
        with open(json_path) as f:
            content = f.read()
        
        # Simple string replacement
        if old_filename in content:
            new_content = content.replace(old_filename, new_filename)
            with open(json_path, 'w') as f:
                f.write(new_content)
            return True
        return False
    except Exception as e:
        print(f"Error updating {json_path}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Fix Instacart T00-00.00 timestamps')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--limit', type=int, help='Limit number of files to process')
    parser.add_argument('--client', help='Only process specific client')
    args = parser.parse_args()
    
    output_dir = Path('output/instacart')
    
    # Find all files with T00-00.00
    bad_files = []
    for pattern in ['*T00-00.00*.png', '*T00-00.00*.mp4']:
        bad_files.extend(output_dir.rglob(pattern))
    
    # Filter by client if specified
    if args.client:
        bad_files = [f for f in bad_files if args.client.lower() in str(f).lower()]
    
    # Sort for consistent ordering
    bad_files = sorted(set(bad_files))
    
    if args.limit:
        bad_files = bad_files[:args.limit]
    
    print(f"Found {len(bad_files)} files to fix")
    
    stats = {
        'renamed': 0,
        'json_updated': 0,
        'skipped_no_run': 0,
        'skipped_exists': 0,
        'errors': 0,
    }
    
    # Group files by their base name (to handle .png and .mp4 pairs)
    processed_bases = set()
    
    for i, old_path in enumerate(bad_files):
        if i % 100 == 0 and i > 0:
            print(f"Progress: {i}/{len(bad_files)}")
        
        # Find the correct timestamp
        json_path, correct_time, ad_index = find_run_file_for_image(old_path)
        
        if not correct_time:
            stats['skipped_no_run'] += 1
            continue
        
        new_path = fix_filename(old_path, correct_time)
        
        if new_path.exists() and new_path != old_path:
            stats['skipped_exists'] += 1
            continue
        
        if args.dry_run:
            print(f"Would rename: {old_path.name}")
            print(f"         to: {new_path.name}")
            stats['renamed'] += 1
        else:
            try:
                # Rename the file
                old_path.rename(new_path)
                stats['renamed'] += 1
                
                # Update JSON
                if json_path and update_json_file(json_path, old_path.name, new_path.name):
                    stats['json_updated'] += 1
                    
            except Exception as e:
                print(f"Error renaming {old_path}: {e}")
                stats['errors'] += 1
    
    print(f"\n{'='*50}")
    print(f"Results:")
    print(f"  Renamed: {stats['renamed']}")
    print(f"  JSON updated: {stats['json_updated']}")
    print(f"  Skipped (no run file): {stats['skipped_no_run']}")
    print(f"  Skipped (target exists): {stats['skipped_exists']}")
    print(f"  Errors: {stats['errors']}")


if __name__ == '__main__':
    main()
