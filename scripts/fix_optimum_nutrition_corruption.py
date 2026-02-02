#!/usr/bin/env python3
"""
Fix 'optimum_nutrition' Filename Corruption

This script fixes filenames corrupted by replacing 'on' with 'optimum_nutrition'
in a non-segment-aware way, causing patterns like:
- "horizon" -> "horizoptimum_nutrition" 
- "stonyfield" -> "stoptimum_nutritionyfield"
- "monster" -> "moptimum_nutritionster"

The fix reverses the corruption by replacing 'optimum_nutrition' back to 'on'
in contexts where it appears mid-word.

Usage:
    python3 scripts/fix_optimum_nutrition_corruption.py --dry-run  # Preview
    python3 scripts/fix_optimum_nutrition_corruption.py            # Apply
"""

import os
import re
import json
import argparse
from pathlib import Path
from typing import Optional, List, Tuple


def count_corruption(text: str) -> int:
    """Count how many times 'optimum_nutrition' appears in the text."""
    return text.lower().count('optimum_nutrition')


def reverse_corruption(corrupted: str) -> Optional[str]:
    """
    Reverse the 'on' -> 'optimum_nutrition' corruption.
    
    The corruption pattern: every 'on' in the filename was replaced with 'optimum_nutrition'.
    Since 'optimum_nutrition' contains 'on' (in 'nutritiON'), this created exponential growth.
    
    Examples:
    - "horizon" -> "horizoptimum_nutrition" -> "horizoptimum_nutritioptimum_nutrition" -> ...
    - "stonyfield" -> "stoptimum_nutritionyfield"
    
    To reverse:
    1. Replace 'optimum_nutrition' with 'on'
    2. Collapse repeated '_on' patterns that came from the 'on' in 'nutrition'
    """
    fixed = corrupted
    
    # Step 1: Replace all 'optimum_nutrition' with 'on'
    while 'optimum_nutrition' in fixed.lower():
        lower = fixed.lower()
        pos = lower.find('optimum_nutrition')
        if pos == -1:
            break
        fixed = fixed[:pos] + 'on' + fixed[pos + len('optimum_nutrition'):]
    
    # Step 2: Collapse repeated '_on' patterns (from the 'on' in 'nutrition')
    # Pattern: word_on_on_on... should become just word
    # But be careful not to remove legitimate '_on' that was part of the original
    import re
    # Remove sequences of 2+ '_on' (keeping single _on could be legitimate)
    fixed = re.sub(r'(_on){2,}', '', fixed)
    
    if fixed != corrupted:
        return fixed
    return None


def fix_filename(filename: str) -> Optional[str]:
    """Fix a corrupted filename. Returns fixed name or None if no fix needed."""
    # Check if this is a legitimate optimum_nutrition file (exactly one occurrence in brand segment)
    parts = filename.split('__')
    if len(parts) >= 2:
        brand_segment = parts[1].lower()
        # If brand segment is exactly 'optimum_nutrition' with no extras, it's legitimate
        if brand_segment == 'optimum_nutrition':
            return None
    
    # Check for corruption pattern - multiple occurrences of optimum_nutrition
    if count_corruption(filename) < 2:
        # Only one occurrence might be legitimate
        # But check if it's embedded in another word
        parts = filename.split('__')
        if len(parts) >= 2:
            brand_segment = parts[1].lower()
            if brand_segment == 'optimum_nutrition':
                return None  # Legitimate
            elif 'optimum_nutrition' in brand_segment and brand_segment != 'optimum_nutrition':
                # Embedded - this is corruption
                pass
            else:
                return None
        else:
            return None
    
    return reverse_corruption(filename)


def find_corrupted_files(root_dir: Path) -> List[Tuple[Path, str]]:
    """Find all files with the corruption pattern."""
    corrupted = []
    
    for ext in ['*.png', '*.jpg', '*.jpeg', '*.mp4', '*.webm']:
        for file_path in root_dir.rglob(ext):
            filename = file_path.name
            if 'optimum_nutrition' in filename.lower():
                # Check if it's corruption (multiple occurrences or embedded)
                count = count_corruption(filename)
                if count >= 2:
                    fixed = fix_filename(filename)
                    if fixed:
                        corrupted.append((file_path, fixed))
                elif count == 1:
                    # Check if embedded in another word
                    parts = filename.split('__')
                    if len(parts) >= 2:
                        brand = parts[1].lower()
                        if 'optimum_nutrition' in brand and brand != 'optimum_nutrition':
                            fixed = fix_filename(filename)
                            if fixed:
                                corrupted.append((file_path, fixed))
    
    return corrupted


def update_json_paths_local(file_path: Path, old_name: str, new_name: str, dry_run: bool = False) -> int:
    """Update JSON files in the same run directory that reference the old filename."""
    updated = 0
    
    # Only check JSONs in the parent directory (same run folder)
    parent = file_path.parent
    for json_path in parent.glob('*.json'):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if old_name in content:
                new_content = content.replace(old_name, new_name)
                if not dry_run:
                    with open(json_path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                updated += 1
        except Exception:
            pass
    
    # Also check the runs folder (one level up for ad type folders like TOA/, Carousel/)
    runs_parent = parent.parent
    if runs_parent.name != 'runs':
        runs_parent = runs_parent.parent
    for json_path in runs_parent.rglob('run_results*.json'):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if old_name in content:
                new_content = content.replace(old_name, new_name)
                if not dry_run:
                    with open(json_path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                updated += 1
        except Exception:
            pass
    
    return updated


def main():
    parser = argparse.ArgumentParser(description='Fix optimum_nutrition filename corruption')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying')
    parser.add_argument('--limit', type=int, default=0, help='Limit number of files to process (0=all)')
    args = parser.parse_args()
    
    output_dir = Path(__file__).resolve().parents[1] / 'output'
    
    print("🔍 Scanning for corrupted files...")
    corrupted = find_corrupted_files(output_dir)
    
    print(f"📁 Found {len(corrupted)} corrupted files")
    
    if args.limit > 0:
        corrupted = corrupted[:args.limit]
        print(f"   (Limited to {args.limit} files)")
    
    if not corrupted:
        print("✅ No corrupted files found!")
        return
    
    # Show samples
    print("\n📋 Sample corrupted files:")
    for file_path, fixed_name in corrupted[:5]:
        print(f"   {file_path.name}")
        print(f"   -> {fixed_name}")
        print()
    
    if args.dry_run:
        print(f"\n🔍 DRY RUN - would rename {len(corrupted)} files")
        return
    
    # Apply fixes
    print(f"\n🔧 Fixing {len(corrupted)} files...")
    success = 0
    errors = 0
    json_updates = 0
    
    for file_path, fixed_name in corrupted:
        try:
            new_path = file_path.parent / fixed_name
            
            # Rename file
            file_path.rename(new_path)
            
            # Update JSON references (local only for speed)
            json_updates += update_json_paths_local(file_path, file_path.name, fixed_name)
            
            success += 1
        except Exception as e:
            print(f"❌ Error fixing {file_path.name}: {e}")
            errors += 1
    
    print(f"\n✅ Fixed {success} files")
    print(f"📝 Updated {json_updates} JSON references")
    if errors:
        print(f"❌ {errors} errors")


if __name__ == '__main__':
    main()
