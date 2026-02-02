#!/usr/bin/env python3
"""
Fix Instacart video overlay dimensions by using actual image file dimensions
instead of DOM-captured dimensions which may differ.

The issue: video_overlay.image_width/image_height are captured from DOM bounding box,
but the actual screenshot may have different dimensions due to DPR scaling or timing.
"""

import json
import os
import glob
from pathlib import Path
from PIL import Image

def get_image_dimensions(image_path: str) -> tuple:
    """Get actual dimensions of an image file."""
    try:
        with Image.open(image_path) as img:
            return img.width, img.height
    except Exception as e:
        print(f"  ⚠️ Could not read image {image_path}: {e}")
        return None, None


def process_json_file(json_path: str, dry_run: bool = False) -> int:
    """Fix video_overlay dimensions in a JSON file. Returns count of fixed ads."""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"  ⚠️ Could not read {json_path}: {e}")
        return 0
    
    json_dir = Path(json_path).parent
    # Go up to client dir (runs/TIMESTAMP/run_results.json -> client/)
    # or (runs/run_results.json -> client/)
    if json_dir.name.startswith('2025'):
        client_dir = json_dir.parent.parent
    else:
        client_dir = json_dir.parent
    
    updated = 0
    ads = data.get('ads', [])
    
    for ad in ads:
        vo = ad.get('video_overlay')
        if not vo:
            continue
        
        image_path_rel = ad.get('image_path')
        if not image_path_rel:
            continue
        
        image_path = client_dir / image_path_rel
        if not image_path.exists():
            continue
        
        # Get actual image dimensions
        actual_width, actual_height = get_image_dimensions(str(image_path))
        if not actual_width or not actual_height:
            continue
        
        # Check if dimensions differ
        old_width = vo.get('image_width', 0)
        old_height = vo.get('image_height', 0)
        
        if old_width == actual_width and old_height == actual_height:
            continue  # Already correct
        
        # Calculate scale factors
        if old_width > 0 and old_height > 0:
            scale_x = actual_width / old_width
            scale_y = actual_height / old_height
            
            # Scale the overlay coordinates
            new_vo = {
                "x": round(vo.get('x', 0) * scale_x),
                "y": round(vo.get('y', 0) * scale_y),
                "width": round(vo.get('width', 0) * scale_x),
                "height": round(vo.get('height', 0) * scale_y),
                "image_width": actual_width,
                "image_height": actual_height,
            }
            if vo.get('border_radius'):
                new_vo['border_radius'] = vo['border_radius']
            
            if dry_run:
                print(f"  Would fix {ad.get('brand')}: {old_width}x{old_height} -> {actual_width}x{actual_height}")
            else:
                ad['video_overlay'] = new_vo
            updated += 1
    
    if updated > 0 and not dry_run:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    return updated


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Fix Instacart video overlay dimensions")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be fixed without making changes")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of files to process")
    args = parser.parse_args()
    
    base_dir = Path(__file__).resolve().parent.parent / "output" / "instacart"
    
    # Find all run_results JSON files
    json_files = list(base_dir.glob("*/runs/**/run_results_*.json"))
    
    print(f"🔍 Found {len(json_files)} JSON files to check")
    
    if args.limit > 0:
        json_files = json_files[:args.limit]
        print(f"📋 Processing first {len(json_files)} files")
    
    total_updated = 0
    files_modified = 0
    
    for json_path in sorted(json_files):
        count = process_json_file(str(json_path), dry_run=args.dry_run)
        if count > 0:
            total_updated += count
            files_modified += 1
            if not args.dry_run:
                print(f"  ✓ Fixed {count} ad(s) in {json_path.name}")
    
    if args.dry_run:
        print(f"\n📋 Would fix {total_updated} ad(s) across {files_modified} file(s)")
    else:
        print(f"\n✅ Fixed {total_updated} ad(s) across {files_modified} file(s)")


if __name__ == "__main__":
    main()
