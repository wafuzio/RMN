#!/usr/bin/env python3
"""
Fix corrupted filenames from the brand review tool's bad find-and-replace.

The brand review tool accidentally did global string replacements on filenames:
  - 'on' -> 'unknown' or 'optimum_nutritino'
  - 'la' -> 'no'
  - Chained: 'la' -> 'no' then 'no' -> 'unknown'

This script:
  1. Scans all instacart JSON run files for corrupted image_path/video_path
  2. For paths where a clean file exists on disk (matched by timestamp suffix),
     updates the JSON to point to the clean file.
  3. For paths where the corrupted file exists on disk, regenerates the correct
     filename from the clean brand in JSON, renames the file, and updates JSON.
  4. Leaves actual "Optimum Nutrition" client data untouched.
  5. Updates the Supabase DB image_path/video_path fields to match.

Usage:
    python tools/fix_corrupted_filenames.py --dry-run
    python tools/fix_corrupted_filenames.py
"""

import argparse
import glob
import json
import os
import re
import sys
from pathlib import Path

# Add parent dir so we can import filename_utils
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from filename_utils import sanitize_component

CORRUPTION_MARKERS = ['unknown', 'optimum_nutriti', 'nond_o_frost', 'bnock', 'bnue']

# Clients that legitimately have "optimum" or "nutrition" in their name — skip these
SKIP_CLIENTS = {'optimum_nutrition', 'optimum nutrition'}


def is_corrupted(path_str):
    """Check if a path contains corruption markers."""
    lower = path_str.lower()
    return any(marker in lower for marker in CORRUPTION_MARKERS)


def find_clean_file_by_timestamp(client_root, corrupted_path):
    """
    Given a corrupted image_path, find the actual file on disk by matching
    the timestamp+index suffix (which was never corrupted).
    
    Returns (clean_relative_path, clean_full_path) or (None, None).
    """
    basename = os.path.basename(corrupted_path)
    ts_match = re.search(r'(D\d{4}-\d{2}-\d{2}_T\d{2}-\d{2}\.\d{2}_\d+\.\w+)$', basename)
    if not ts_match:
        return None, None
    
    ts_suffix = ts_match.group(1)
    subdir = os.path.dirname(corrupted_path)
    search_dir = os.path.join(client_root, subdir) if subdir else client_root
    
    if not os.path.isdir(search_dir):
        return None, None
    
    for f in os.listdir(search_dir):
        if f.endswith(ts_suffix):
            clean_rel = os.path.join(subdir, f) if subdir else f
            clean_full = os.path.join(search_dir, f)
            return clean_rel, clean_full
    
    return None, None


def regenerate_clean_filename(corrupted_basename, brand, ad_type_from_json=None):
    """
    Regenerate a clean filename from a corrupted one using the clean brand.
    
    The filename format is:
    instacart__[advertiser]__[ad_type]__[client]__[search_term]__D[date]_T[time]_[idx].[ext]
    
    We replace the corrupted advertiser segment with the clean brand.
    """
    # Parse the filename: split on double underscore
    parts = corrupted_basename.split('__')
    if len(parts) < 5:
        return None
    
    # parts[0] = retailer (instacart)
    # parts[1] = advertiser (corrupted)
    # parts[2] = ad_type
    # parts[3] = client
    # parts[4+] = search_term + timestamp
    
    clean_advertiser = sanitize_component(brand, max_length=30, preserve_ampersand=True)
    parts[1] = clean_advertiser
    
    return '__'.join(parts)


def main():
    parser = argparse.ArgumentParser(description='Fix corrupted filenames from brand review tool')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--client', type=str, help='Only process a specific client directory')
    parser.add_argument('--update-db', action='store_true', help='Also update Supabase DB paths')
    args = parser.parse_args()
    
    output_root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'output', 'instacart')
    
    stats = {
        'json_files_scanned': 0,
        'corrupted_paths_found': 0,
        'fixed_via_timestamp': 0,      # Clean file found on disk, JSON updated
        'fixed_via_rename': 0,          # Corrupted file renamed + JSON updated
        'unfixable_no_file': 0,         # No file on disk at all
        'unfixable_no_brand': 0,        # No clean brand in JSON
        'skipped_optimum_nutrition': 0, # Actual Optimum Nutrition client
        'json_files_modified': 0,
        'db_updates': [],               # (old_path, new_path) for DB updates
    }
    
    # Collect all client dirs
    if args.client:
        client_dirs = [os.path.join(output_root, args.client)]
    else:
        client_dirs = sorted(glob.glob(os.path.join(output_root, '*')))
    
    for client_dir in client_dirs:
        if not os.path.isdir(client_dir):
            continue
        
        client_name = os.path.basename(client_dir)
        
        # Skip actual Optimum Nutrition client
        if client_name.lower().replace('_', ' ') in SKIP_CLIENTS:
            print(f"⏭️  Skipping Optimum Nutrition client: {client_name}")
            stats['skipped_optimum_nutrition'] += 1
            continue
        
        json_files = sorted(glob.glob(os.path.join(client_dir, 'runs', '*', 'run_results_*.json')))
        if not json_files:
            continue
        
        client_fixes = 0
        
        for jf in json_files:
            stats['json_files_scanned'] += 1
            
            with open(jf) as f:
                data = json.load(f)
            
            modified = False
            
            for ad in data.get('ads', []):
                for key in ['image_path', 'video_path']:
                    path_val = ad.get(key, '')
                    if not path_val or not is_corrupted(path_val):
                        continue
                    
                    stats['corrupted_paths_found'] += 1
                    brand = ad.get('brand', '')
                    
                    # Strategy 1: Find clean file on disk by timestamp
                    clean_rel, clean_full = find_clean_file_by_timestamp(client_dir, path_val)
                    
                    if clean_rel and clean_full and not is_corrupted(clean_rel):
                        # Clean file exists on disk — just update JSON
                        old_path = path_val
                        ad[key] = clean_rel
                        modified = True
                        stats['fixed_via_timestamp'] += 1
                        stats['db_updates'].append((old_path, clean_rel, client_name))
                        client_fixes += 1
                        if args.dry_run:
                            print(f"  [TIMESTAMP] {key}: {os.path.basename(old_path)}")
                            print(f"           -> {os.path.basename(clean_rel)}")
                        continue
                    
                    # Strategy 2: Corrupted file exists on disk — rename it
                    corrupted_full = os.path.join(client_dir, path_val)
                    if os.path.exists(corrupted_full) and brand:
                        new_basename = regenerate_clean_filename(
                            os.path.basename(path_val), brand
                        )
                        if new_basename and not is_corrupted(new_basename):
                            subdir = os.path.dirname(path_val)
                            new_rel = os.path.join(subdir, new_basename) if subdir else new_basename
                            new_full = os.path.join(client_dir, new_rel)
                            
                            if not os.path.exists(new_full):
                                old_path = path_val
                                if not args.dry_run:
                                    os.rename(corrupted_full, new_full)
                                ad[key] = new_rel
                                modified = True
                                stats['fixed_via_rename'] += 1
                                stats['db_updates'].append((old_path, new_rel, client_name))
                                client_fixes += 1
                                if args.dry_run:
                                    print(f"  [RENAME]    {key}: {os.path.basename(old_path)}")
                                    print(f"           -> {new_basename}")
                            else:
                                # Target already exists (shouldn't happen often)
                                stats['unfixable_no_file'] += 1
                            continue
                        elif not brand:
                            stats['unfixable_no_brand'] += 1
                            continue
                    
                    # Strategy 3: No file on disk at all
                    if not brand:
                        stats['unfixable_no_brand'] += 1
                    else:
                        stats['unfixable_no_file'] += 1
            
            if modified:
                stats['json_files_modified'] += 1
                if not args.dry_run:
                    with open(jf, 'w') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
        
        if client_fixes > 0:
            print(f"📁 {client_name}: {client_fixes} paths fixed")
    
    # Summary
    print(f"\n{'=' * 50}")
    print(f"📊 Summary:")
    print(f"   JSON files scanned: {stats['json_files_scanned']}")
    print(f"   Corrupted paths found: {stats['corrupted_paths_found']}")
    print(f"   Fixed via timestamp match: {stats['fixed_via_timestamp']}")
    print(f"   Fixed via file rename: {stats['fixed_via_rename']}")
    print(f"   Unfixable (no file on disk): {stats['unfixable_no_file']}")
    print(f"   Unfixable (no brand in JSON): {stats['unfixable_no_brand']}")
    print(f"   Skipped (Optimum Nutrition): {stats['skipped_optimum_nutrition']}")
    print(f"   JSON files modified: {stats['json_files_modified']}")
    
    if args.dry_run:
        print(f"\n🔍 DRY RUN — no changes were made")
    
    # DB updates
    if args.update_db and not args.dry_run and stats['db_updates']:
        print(f"\n🗄️  Updating Supabase DB ({len(stats['db_updates'])} paths)...")
        try:
            from supabase import create_client
            supabase = create_client(
                "http://127.0.0.1:54321",
                "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU"
            )
            
            db_updated = 0
            for old_path, new_path, client in stats['db_updates']:
                # Update image_path
                result = supabase.table('ads').update(
                    {'image_path': new_path}
                ).eq('image_path', old_path).execute()
                if result.data:
                    db_updated += len(result.data)
                
                # Update video_path
                result = supabase.table('ads').update(
                    {'video_path': new_path}
                ).eq('video_path', old_path).execute()
                if result.data:
                    db_updated += len(result.data)
            
            print(f"   ✅ Updated {db_updated} DB rows")
        except Exception as e:
            print(f"   ❌ DB update failed: {e}")
    elif stats['db_updates']:
        print(f"\n💡 {len(stats['db_updates'])} DB paths need updating. Run with --update-db to apply.")


if __name__ == '__main__':
    main()
