#!/usr/bin/env python3
"""
Fix corrupted image_path and video_path values in JSON files.

Corruption patterns found:
1. 'no' replaced with 'unknown' repeatedly: non -> unknownn -> unkunknownwnn -> ...
2. 'on' replaced with 'unknown': Sponsored -> Spunknownsored, amazon -> amazunknown
3. Repeated strings: sssss, coffee_coffee_coffee..., foods_foods...

This script:
1. Scans all JSON files in output/
2. Identifies corrupted path fields
3. Applies the reverse_corruption fix from fix_corrupted_filenames.py
4. Updates the JSON with the correct path
"""

import json
import os
import re
import glob
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "output"

# Patterns that indicate corruption
CORRUPTION_PATTERNS = [
    r'unkunk',             # unkunk... pattern from repeated 'no' -> 'unknown'
    r'unknownwn',          # ...unknownwnwn pattern
    r'nunknown',           # non -> nunknown (simpler case)
    r'spounknown',         # spoon -> spounknown (magic_spoon)
    r'spono',              # partial fix that left 'spono'
    r'Spunknown',          # Sponsored -> Spunknownsored
    r'Spnosored',          # partial fix that left 'Spnosored'
    r'amazunknown',        # amazon -> amazunknown
    r'amazno',             # partial fix that left 'amazno'
    r'Amazunknown',        # Amazon -> Amazunknown
    r'ununknown',          # un -> ununknown
    r'(\w)\1{4,}',         # 5+ repeated chars like sssss
    r'(_\w+)\1{2,}',       # repeated word patterns like _coffee_coffee_coffee
]

def reverse_corruption(corrupted: str) -> str:
    """
    Reverse the 'no' -> 'unknown' corruption pattern.
    
    From fix_corrupted_filenames.py:
    The corruption happens when .replace('no', 'unknown') is called repeatedly:
    - 'no' becomes 'unknown'
    - 'unknown' contains 'no' at position 3, so next iteration:
      'unk' + 'no' + 'wn' -> 'unk' + 'unknown' + 'wn' = 'ununknownwn'
    - This repeats, creating: unkunk...unknownwnwn...
    
    To reverse: replace the pattern back to 'no'
    """
    # Pattern: (unk)+ followed by 'unknown' or 'no' followed by (wn)+
    corruption_pattern = r'((?:unk)+)(unknown|no)((?:wn)+|(?:wnwn)*)'
    
    def fix_match(m):
        # The original was just 'no'
        return 'no'
    
    # Apply the fix
    fixed = re.sub(corruption_pattern, fix_match, corrupted)
    
    # Also fix simpler patterns - order matters!
    # Fix specific word corruptions BEFORE general patterns
    fixed = re.sub(r'spounknown', 'spoon', fixed)  # magic_spoon -> magic_spounknown
    fixed = re.sub(r'spono', 'spoon', fixed)  # partial fix that left 'spono'
    fixed = re.sub(r'nunknown', 'non', fixed)
    fixed = re.sub(r'Spunknownsored', 'Sponsored', fixed)
    fixed = re.sub(r'Spnosored', 'Sponsored', fixed)  # partial fix that left 'Spnosored'
    fixed = re.sub(r'amazunknown', 'amazon', fixed)
    fixed = re.sub(r'amazno', 'amazon', fixed)  # partial fix that left 'amazno'
    fixed = re.sub(r'Amazunknown', 'Amazon', fixed)
    # Fix remaining 'nno' that might have been created by earlier fixes
    fixed = re.sub(r'nno_', 'non_', fixed)
    fixed = re.sub(r'__no__', '__unknown__', fixed)
    
    return fixed

def is_corrupted(path_str):
    """Check if a path string contains corruption patterns."""
    if not path_str:
        return False
    for pattern in CORRUPTION_PATTERNS:
        if re.search(pattern, path_str):
            return True
    return False


def fix_json_file(json_path, dry_run=True):
    """Fix corrupted paths in a single JSON file."""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"  [ERROR] Failed to read {json_path}: {e}")
        return 0
    
    fixes_made = 0
    path_fields = ['image_path', 'video_path', 'video_url', 'toa_image_path', 
                   'skyscraper_image_path', 'carousel_image_path']
    
    # Check ads array
    ads = data.get('ads', [])
    if not ads:
        # Legacy structure
        for result in data.get('results', []):
            ads.extend(result.get('ads', []))
    
    for ad in ads:
        # First, check if there's a correct path we can copy from
        # Priority: type-specific path fields often have the correct path
        correct_path = None
        for alt_field in ['toa_image_path', 'skyscraper_image_path', 'carousel_image_path']:
            alt_path = ad.get(alt_field)
            if alt_path and not is_corrupted(alt_path):
                correct_path = alt_path
                break
        
        for field in path_fields:
            old_path = ad.get(field)
            if old_path and is_corrupted(old_path):
                # Try to use the correct path from alternate field if available
                new_path = None
                if correct_path and field == 'image_path':
                    # Use the correct path from the type-specific field
                    new_path = correct_path
                else:
                    # Fall back to reverse_corruption
                    new_path = reverse_corruption(old_path)
                
                if new_path and new_path != old_path:
                    if dry_run:
                        print(f"  [WOULD FIX] {field}:")
                        print(f"    OLD: {old_path[:80]}...")
                        print(f"    NEW: {new_path[:80]}...")
                    else:
                        ad[field] = new_path
                        print(f"  [FIXED] {field}")
                    fixes_made += 1
    
    # Write back if not dry run and fixes were made
    if not dry_run and fixes_made > 0:
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"  [ERROR] Failed to write {json_path}: {e}")
            return 0
    
    return fixes_made

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Fix corrupted JSON paths')
    parser.add_argument('--dry-run', action='store_true', default=True,
                        help='Show what would be fixed without making changes (default)')
    parser.add_argument('--fix', action='store_true',
                        help='Actually fix the files')
    parser.add_argument('--limit', type=int, default=0,
                        help='Limit number of files to process (0 = all)')
    args = parser.parse_args()
    
    dry_run = not args.fix
    
    if dry_run:
        print("=== DRY RUN MODE (use --fix to apply changes) ===\n")
    else:
        print("=== FIXING FILES ===\n")
    
    # Find all JSON files with corrupted paths
    json_files = []
    for pattern in ['output/**/*.json']:
        json_files.extend(glob.glob(str(PROJECT_ROOT / pattern), recursive=True))
    
    # Filter to only corrupted files
    corrupted_files = []
    for jf in json_files:
        try:
            with open(jf, 'r', encoding='utf-8') as f:
                content = f.read()
            if any(re.search(p, content) for p in CORRUPTION_PATTERNS):
                corrupted_files.append(jf)
        except Exception:
            continue
    
    print(f"Found {len(corrupted_files)} JSON files with corrupted paths\n")
    
    if args.limit > 0:
        corrupted_files = corrupted_files[:args.limit]
        print(f"Processing first {args.limit} files\n")
    
    total_fixes = 0
    for jf in corrupted_files:
        rel_path = os.path.relpath(jf, PROJECT_ROOT)
        print(f"Processing: {rel_path}")
        fixes = fix_json_file(jf, dry_run=dry_run)
        total_fixes += fixes
        if fixes == 0:
            print("  (no fixable paths found)")
        print()
    
    print(f"\n{'Would fix' if dry_run else 'Fixed'}: {total_fixes} paths in {len(corrupted_files)} files")
    if dry_run:
        print("\nRun with --fix to apply changes")

if __name__ == '__main__':
    main()
