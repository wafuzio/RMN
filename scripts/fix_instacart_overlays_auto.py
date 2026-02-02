#!/usr/bin/env python3
"""
Fix Instacart video overlays using auto_detect_video_overlay.py CV detection.
This directly updates JSON files with accurate bounding boxes.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.auto_detect_video_overlay import detect_instacart_video_bounds


def process_json_file(json_path: Path, client_root: Path, dry_run: bool = False) -> int:
    """Process a JSON file and update video_overlay for all video ads."""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"  ⚠️ Could not read {json_path}: {e}")
        return 0
    
    updated = 0
    ads = data.get('ads', [])
    
    for ad in ads:
        ad_type = ad.get('type') or ad.get('ad_type', '')
        
        # Only process video ad types
        if 'video' not in ad_type.lower() and 'shoppable_video' not in ad_type.lower():
            continue
        
        # Get image path
        image_path_rel = ad.get('image_path')
        if not image_path_rel:
            continue
        
        image_path = client_root / image_path_rel
        if not image_path.exists():
            print(f"  ⚠️ Image not found: {image_path}")
            continue
        
        # Run CV detection
        bounds = detect_instacart_video_bounds(image_path)
        if not bounds:
            print(f"  ⚠️ Could not detect bounds for {ad.get('brand', 'unknown')}")
            continue
        
        brand = ad.get('brand', 'unknown')
        old_vo = ad.get('video_overlay', {})
        
        if dry_run:
            print(f"  Would update {brand}: x={old_vo.get('x')}→{bounds['x']}, y={old_vo.get('y')}→{bounds['y']}")
        else:
            ad['video_overlay'] = bounds
            print(f"  ✓ Updated {brand}: x={bounds['x']}, y={bounds['y']}, w={bounds['width']}, h={bounds['height']}")
        
        updated += 1
    
    if updated > 0 and not dry_run:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    return updated


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Fix Instacart video overlays with CV detection")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be updated")
    parser.add_argument("--client", help="Process only specific client")
    parser.add_argument("--limit", type=int, default=0, help="Limit files to process")
    args = parser.parse_args()
    
    base_dir = Path(__file__).resolve().parent.parent / "output" / "instacart"
    
    # Find all client directories
    if args.client:
        clients = [base_dir / args.client]
    else:
        clients = [d for d in base_dir.iterdir() if d.is_dir()]
    
    total_updated = 0
    files_processed = 0
    
    for client_dir in sorted(clients):
        runs_dir = client_dir / "runs"
        if not runs_dir.exists():
            continue
        
        # Find all JSON files in runs (handle nested timestamp dirs)
        json_files = list(runs_dir.glob("*/run_results_*.json"))
        if not json_files:
            json_files = list(runs_dir.glob("run_results_*.json"))
        
        if not json_files:
            continue
        
        print(f"\n📁 {client_dir.name} ({len(json_files)} runs)")
        
        for json_path in sorted(json_files):
            if args.limit > 0 and files_processed >= args.limit:
                break
            
            count = process_json_file(json_path, client_dir, dry_run=args.dry_run)
            if count > 0:
                total_updated += count
                files_processed += 1
    
    action = "Would update" if args.dry_run else "Updated"
    print(f"\n✅ {action} {total_updated} video overlay(s) across {files_processed} file(s)")
    
    if not args.dry_run and total_updated > 0:
        print("\n⚠️  Remember to rebuild brand index:")
        print("   .venv/bin/python3 tools/build_brand_index.py")


if __name__ == "__main__":
    main()
