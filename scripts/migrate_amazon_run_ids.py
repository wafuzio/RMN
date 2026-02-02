#!/usr/bin/env python3
"""
Migrate Amazon run files to canonical format.

Changes:
- Rename run_results_amazon_<client>_YYYYMMDD_HHMMSS.json -> run_results_amazon_<client>_YYYYMMDDHHMMSS.json
- Rename search_results_amazon_<client>_YYYYMMDD_HHMMSS.html -> search_results_amazon_<client>_YYYYMMDDHHMMSS.html  
- Rename capture_debug_YYYYMMDD_HHMMSS.log -> capture_debug_YYYYMMDDHHMMSS.log
- Update run_id field in JSON from YYYYMMDD_HHMMSS to YYYYMMDDHHMMSS
- Remove stale 'ts' field from JSON if present
"""

import os
import re
import json
import glob
import argparse
from pathlib import Path


def migrate_filename(filepath: str, dry_run: bool = False) -> str:
    """Rename file from underscore format to canonical format."""
    dirname = os.path.dirname(filepath)
    filename = os.path.basename(filepath)
    
    # Match pattern: _YYYYMMDD_HHMMSS. or _YYYYMMDD_HHMMSS_
    match = re.search(r'_(\d{8})_(\d{6})([._])', filename)
    if not match:
        return None
    
    date_part, time_part, suffix = match.groups()
    old_pattern = f"_{date_part}_{time_part}{suffix}"
    new_pattern = f"_{date_part}{time_part}{suffix}"
    
    new_filename = filename.replace(old_pattern, new_pattern)
    new_filepath = os.path.join(dirname, new_filename)
    
    if filepath == new_filepath:
        return None  # Already canonical
    
    if not dry_run:
        os.rename(filepath, new_filepath)
    
    return new_filepath


def migrate_json_content(json_path: str, dry_run: bool = False) -> bool:
    """Update JSON content to canonical format."""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        modified = False
        
        # Fix run_id if it has underscore
        if 'run_id' in data:
            old_run_id = data['run_id']
            new_run_id = old_run_id.replace('_', '')
            if old_run_id != new_run_id:
                data['run_id'] = new_run_id
                modified = True
        
        # Remove stale 'ts' field
        if 'ts' in data:
            del data['ts']
            modified = True
        
        # Fix timestamp if not ISO 8601 with Z
        if 'timestamp' in data:
            ts = data['timestamp']
            if ts and not ts.endswith('Z') and '+' not in ts:
                data['timestamp'] = ts + 'Z'
                modified = True
        
        if modified and not dry_run:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        
        return modified
    except Exception as e:
        print(f"  Error processing {json_path}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Migrate Amazon run files to canonical format')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--output-dir', default='output/amazon', help='Amazon output directory')
    args = parser.parse_args()
    
    output_dir = args.output_dir
    dry_run = args.dry_run
    
    if dry_run:
        print("DRY RUN - no changes will be made\n")
    
    # Find all Amazon run files
    patterns = [
        os.path.join(output_dir, '*/runs/run_results_*.json'),
        os.path.join(output_dir, '*/runs/search_results_*.html'),
        os.path.join(output_dir, '*/runs/capture_debug_*.log'),
    ]
    
    files_renamed = 0
    jsons_updated = 0
    
    for pattern in patterns:
        for filepath in glob.glob(pattern):
            original_path = filepath
            
            # Check if file needs renaming
            if re.search(r'_\d{8}_\d{6}[._]', os.path.basename(filepath)):
                new_path = migrate_filename(filepath, dry_run)
                if new_path:
                    print(f"Rename: {os.path.basename(filepath)} -> {os.path.basename(new_path)}")
                    files_renamed += 1
                    if not dry_run:
                        filepath = new_path  # Use new path for JSON update
            
            # Update JSON content (use original path in dry-run)
            json_path = filepath if not dry_run else original_path
            if json_path.endswith('.json'):
                if migrate_json_content(json_path, dry_run):
                    print(f"Updated JSON: {os.path.basename(json_path)}")
                    jsons_updated += 1
    
    print(f"\n{'Would rename' if dry_run else 'Renamed'}: {files_renamed} files")
    print(f"{'Would update' if dry_run else 'Updated'}: {jsons_updated} JSON files")


if __name__ == '__main__':
    main()
