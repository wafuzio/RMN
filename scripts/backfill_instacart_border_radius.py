#!/usr/bin/env python3
"""
Backfill border_radius for Instacart video overlays that are missing it.
Instacart videos typically have 8px border radius.
"""

import json
import os
import glob
from pathlib import Path

DEFAULT_BORDER_RADIUS = 8

def process_json_file(json_path: str) -> int:
    """Add border_radius to video_overlay if missing. Returns count of updated ads."""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"  ⚠️ Could not read {json_path}: {e}")
        return 0
    
    updated = 0
    ads = data.get('ads', [])
    
    for ad in ads:
        vo = ad.get('video_overlay')
        if vo and 'border_radius' not in vo:
            vo['border_radius'] = DEFAULT_BORDER_RADIUS
            updated += 1
    
    if updated > 0:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    return updated


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Backfill border_radius for Instacart video overlays")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be updated without making changes")
    args = parser.parse_args()
    
    base_dir = Path(__file__).resolve().parent.parent / "output" / "instacart"
    
    # Find all run_results JSON files
    json_files = list(base_dir.glob("*/runs/**/run_results_*.json"))
    
    print(f"🔍 Found {len(json_files)} JSON files to check")
    
    total_updated = 0
    files_modified = 0
    
    for json_path in sorted(json_files):
        # Quick check if file has video_overlay without border_radius
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if '"video_overlay"' not in content:
                continue
            if '"border_radius"' in content:
                continue  # Already has border_radius
            
            data = json.loads(content)
            needs_update = any(
                ad.get('video_overlay') and 'border_radius' not in ad.get('video_overlay', {})
                for ad in data.get('ads', [])
            )
            
            if not needs_update:
                continue
            
            if args.dry_run:
                print(f"  Would update: {json_path}")
                total_updated += 1
            else:
                count = process_json_file(str(json_path))
                if count > 0:
                    print(f"  ✓ Updated {count} ad(s) in {json_path.name}")
                    total_updated += count
                    files_modified += 1
                    
        except Exception as e:
            print(f"  ⚠️ Error processing {json_path}: {e}")
    
    if args.dry_run:
        print(f"\n📋 Would update {total_updated} file(s)")
    else:
        print(f"\n✅ Updated {total_updated} ad(s) across {files_modified} file(s)")


if __name__ == "__main__":
    main()
