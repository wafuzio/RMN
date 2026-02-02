#!/usr/bin/env python3
"""
Fix Corrupted Filenames Script

This script fixes filenames that were corrupted by a bug in recanon_ads.py
where simple .replace('no', 'unknown') caused exponential string growth.

The corruption pattern:
- "non-dairy_milk" -> "unknownn-dairy_milk" -> "unkunknownwnn-dairy_milk" -> ...
- "Danone" -> "Daunknowne" -> "Daunkunknownwne" -> ...

The fix:
1. Detect the corruption pattern (unkunk...unknownwnwn...)
2. Reverse the corruption to recover the original string
3. Rename the file back to the correct name

Usage:
    python3 scripts/fix_corrupted_filenames.py --dry-run  # Preview changes
    python3 scripts/fix_corrupted_filenames.py            # Apply changes
"""

import os
import re
import argparse
from pathlib import Path
from typing import Optional, Tuple


def reverse_corruption(corrupted: str) -> Optional[str]:
    """
    Reverse the 'no' -> 'unknown' corruption pattern.
    
    The corruption happens when .replace('no', 'unknown') is called repeatedly:
    - 'no' becomes 'unknown'
    - 'unknown' contains 'no' at position 3, so next iteration:
      'unk' + 'no' + 'wn' -> 'unk' + 'unknown' + 'wn' = 'ununknownwn'
    - This repeats, creating: unkunk...unknownwnwn...
    
    To reverse: replace the pattern back to 'no'
    """
    # Pattern: unk repeated N times, then 'nown' repeated N times
    # The core corruption is: (unk)+ unknown (wn)+
    # Which came from: 'no' being replaced with 'unknown' repeatedly
    
    # Match the corruption pattern
    # Pattern: (unk)+ followed by 'no' or 'unknown' followed by (wn)+
    corruption_pattern = r'((?:unk)+)(unknown|no)((?:wn)+|(?:wnwn)*)'
    
    def fix_match(m):
        prefix = m.group(1)  # unkunk...
        middle = m.group(2)  # unknown or no
        suffix = m.group(3)  # wnwn...
        
        # Count iterations
        unk_count = prefix.count('unk')
        wn_count = suffix.count('wn') if suffix else 0
        
        # The original was just 'no'
        return 'no'
    
    # Try to fix the corruption
    fixed = re.sub(corruption_pattern, fix_match, corrupted)
    
    if fixed != corrupted:
        return fixed
    return None


def fix_filename(filename: str) -> Optional[str]:
    """
    Fix a corrupted filename.
    
    Returns the fixed filename, or None if no fix needed.
    """
    # Check if filename contains the corruption pattern
    if 'unkunk' not in filename.lower() and 'unknownwn' not in filename.lower():
        return None
    
    # Apply the fix
    fixed = reverse_corruption(filename)
    
    if fixed and fixed != filename:
        return fixed
    
    return None


def find_corrupted_files(output_dir: str) -> list:
    """Find all files with corrupted filenames."""
    corrupted = []
    
    output_path = Path(output_dir)
    if not output_path.exists():
        print(f"Output directory not found: {output_dir}")
        return corrupted
    
    # Search for files with the corruption pattern
    for file_path in output_path.rglob('*'):
        if not file_path.is_file():
            continue
        
        filename = file_path.name
        
        # Check for corruption pattern
        if 'unkunk' in filename.lower() or 'unknownwn' in filename.lower():
            fixed_name = fix_filename(filename)
            if fixed_name:
                corrupted.append({
                    'path': file_path,
                    'original': filename,
                    'fixed': fixed_name
                })
    
    return corrupted


def main():
    parser = argparse.ArgumentParser(description='Fix corrupted filenames from recanon_ads.py bug')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying')
    parser.add_argument('--output-dir', default='output', help='Output directory to scan')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show detailed output')
    args = parser.parse_args()
    
    print("=" * 60)
    print("Corrupted Filename Fixer")
    print("=" * 60)
    print()
    
    if args.dry_run:
        print("🔍 DRY RUN - No changes will be made\n")
    
    # Find corrupted files
    print(f"Scanning {args.output_dir} for corrupted filenames...")
    corrupted = find_corrupted_files(args.output_dir)
    
    if not corrupted:
        print("✅ No corrupted files found!")
        return
    
    print(f"\n📁 Found {len(corrupted)} corrupted files\n")
    
    # Group by directory for cleaner output
    by_dir = {}
    for item in corrupted:
        dir_path = str(item['path'].parent)
        if dir_path not in by_dir:
            by_dir[dir_path] = []
        by_dir[dir_path].append(item)
    
    # Process files
    success_count = 0
    error_count = 0
    
    for dir_path, items in sorted(by_dir.items()):
        print(f"\n📂 {dir_path}")
        print(f"   ({len(items)} files)")
        
        for item in items:
            old_path = item['path']
            new_path = old_path.parent / item['fixed']
            
            if args.verbose:
                print(f"   {item['original'][:60]}...")
                print(f"   -> {item['fixed'][:60]}...")
            
            if args.dry_run:
                success_count += 1
                continue
            
            try:
                # Check if target already exists
                if new_path.exists():
                    print(f"   ⚠️  Target exists, skipping: {item['fixed'][:40]}...")
                    error_count += 1
                    continue
                
                old_path.rename(new_path)
                success_count += 1
                
                if args.verbose:
                    print(f"   ✅ Renamed")
                    
            except Exception as e:
                print(f"   ❌ Error: {e}")
                error_count += 1
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  Files found:    {len(corrupted)}")
    print(f"  Successfully fixed: {success_count}")
    print(f"  Errors:         {error_count}")
    
    if args.dry_run:
        print("\n💡 Run without --dry-run to apply changes")


if __name__ == "__main__":
    main()
