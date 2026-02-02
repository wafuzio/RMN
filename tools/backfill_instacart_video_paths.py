#!/usr/bin/env python3
"""
Backfill video_path for Instacart video ads.

This script:
1. Finds all Instacart video ad entries in run JSONs
2. Checks if a matching MP4 file exists (same base name as PNG)
3. Updates the JSON with video_path if MP4 exists
4. Optionally adds video_overlay metadata using calibrations or defaults

Usage:
    python tools/backfill_instacart_video_paths.py [--dry-run] [--client CLIENT]
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional, Dict
import argparse

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_ROOT = PROJECT_ROOT / "output" / "instacart"
CALIBRATIONS_PATH = PROJECT_ROOT / "config" / "video_overlay_calibrations.json"

# Default Instacart video overlay (approximate, based on recent captures)
# Video is typically in the left portion of the ad
DEFAULT_INSTACART_OVERLAY = {
    "x": 17,
    "y": 80,
    "width": 501,
    "height": 282,
}


def load_calibrations() -> Dict:
    """Load video overlay calibrations from config."""
    if CALIBRATIONS_PATH.exists():
        with open(CALIBRATIONS_PATH) as f:
            return json.load(f).get("calibrations", {})
    return {}


def get_image_dimensions(image_path: Path) -> Optional[tuple]:
    """Get image dimensions using PIL."""
    try:
        from PIL import Image
        with Image.open(image_path) as img:
            return img.size  # (width, height)
    except Exception as e:
        print(f"  ⚠️ Could not read image dimensions: {e}")
        return None


def find_matching_mp4(png_path: Path) -> Optional[Path]:
    """Find MP4 file with same base name as PNG."""
    mp4_path = png_path.with_suffix('.mp4')
    if mp4_path.exists():
        return mp4_path
    return None


def process_json_file(json_path: Path, calibrations: Dict, dry_run: bool = False) -> Dict:
    """Process a single JSON file and update video ads."""
    stats = {"checked": 0, "updated_path": 0, "updated_overlay": 0, "mp4_found": 0, "mp4_missing": 0}
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    ads = data.get('ads', [])
    if not ads:
        return stats
    
    # Get client from path: output/instacart/{client}/runs/...
    parts = json_path.parts
    try:
        instacart_idx = parts.index('instacart')
        client = parts[instacart_idx + 1]
    except (ValueError, IndexError):
        client = "unknown"
    
    client_root = OUTPUT_ROOT / client
    modified = False
    
    for ad in ads:
        ad_type = (ad.get('type') or '').lower()
        if 'video' not in ad_type:
            continue
        
        stats["checked"] += 1
        image_path = ad.get('image_path')
        
        if not image_path:
            continue
        
        # Construct full paths
        full_image_path = client_root / image_path
        
        if not full_image_path.exists():
            print(f"  ⚠️ Image not found: {full_image_path}")
            continue
        
        # Check for matching MP4
        mp4_path = find_matching_mp4(full_image_path)
        
        if mp4_path:
            stats["mp4_found"] += 1
            
            # Update video_path if not set
            if not ad.get('video_path'):
                rel_mp4_path = str(mp4_path.relative_to(client_root))
                ad['video_path'] = rel_mp4_path
                stats["updated_path"] += 1
                modified = True
                print(f"  ✅ Added video_path: {rel_mp4_path}")
        else:
            stats["mp4_missing"] += 1
        
        # Add video_overlay if not present
        if not ad.get('video_overlay'):
            dims = get_image_dimensions(full_image_path)
            if dims:
                width, height = dims
                
                # Check calibrations first (by image hash or filename)
                # For now, use default overlay scaled to image dimensions
                overlay = {
                    "x": DEFAULT_INSTACART_OVERLAY["x"],
                    "y": DEFAULT_INSTACART_OVERLAY["y"],
                    "width": DEFAULT_INSTACART_OVERLAY["width"],
                    "height": DEFAULT_INSTACART_OVERLAY["height"],
                    "image_width": width,
                    "image_height": height,
                }
                
                ad['video_overlay'] = overlay
                stats["updated_overlay"] += 1
                modified = True
                print(f"  ✅ Added video_overlay: {overlay}")
    
    # Write back if modified
    if modified and not dry_run:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"  💾 Saved {json_path.name}")
    elif modified and dry_run:
        print(f"  🔍 [DRY RUN] Would save {json_path.name}")
    
    return stats


def main():
    parser = argparse.ArgumentParser(description="Backfill video_path for Instacart video ads")
    parser.add_argument("--dry-run", action="store_true", help="Don't write changes, just report")
    parser.add_argument("--client", type=str, help="Process only specific client")
    args = parser.parse_args()
    
    if not OUTPUT_ROOT.exists():
        print(f"❌ Output directory not found: {OUTPUT_ROOT}")
        sys.exit(1)
    
    calibrations = load_calibrations()
    print(f"📋 Loaded {len(calibrations)} calibrations")
    
    # Find all client directories
    if args.client:
        clients = [OUTPUT_ROOT / args.client]
        if not clients[0].exists():
            print(f"❌ Client not found: {args.client}")
            sys.exit(1)
    else:
        clients = [d for d in OUTPUT_ROOT.iterdir() if d.is_dir()]
    
    total_stats = {"checked": 0, "updated_path": 0, "updated_overlay": 0, "mp4_found": 0, "mp4_missing": 0}
    
    for client_dir in sorted(clients):
        client_name = client_dir.name
        
        # Find all run JSON files
        json_files = list(client_dir.glob("**/run_results*.json"))
        if not json_files:
            continue
        
        print(f"\n📁 {client_name}: {len(json_files)} run files")
        
        for json_path in json_files:
            stats = process_json_file(json_path, calibrations, args.dry_run)
            for k, v in stats.items():
                total_stats[k] += v
    
    # Summary
    print(f"\n{'='*50}")
    print(f"📊 Summary:")
    print(f"   Video ads checked: {total_stats['checked']}")
    print(f"   MP4s found: {total_stats['mp4_found']}")
    print(f"   MP4s missing: {total_stats['mp4_missing']}")
    print(f"   video_path updated: {total_stats['updated_path']}")
    print(f"   video_overlay added: {total_stats['updated_overlay']}")
    
    if args.dry_run:
        print(f"\n🔍 DRY RUN - no files were modified")


if __name__ == "__main__":
    main()
