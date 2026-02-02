#!/usr/bin/env python3
"""
Batch process all video ads and update their JSON files with overlay data.

This script:
1. Finds all SBV (Sponsored Brand Video) images across retailers
2. Runs auto-detection on each to find video overlay bounds
3. Updates the corresponding JSON run files with overlay metadata
"""

import os
import sys
import json
import glob
import argparse
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.auto_detect_video_overlay import auto_detect_video_bounds


def find_video_images(output_dir: str, retailer: str = None) -> list:
    """Find all video ad images in the output directory."""
    images = []
    
    # Video folder patterns by retailer
    video_folders = {
        'amazon': ['Sponsored_Brand_Video*'],
        'walmart': ['SBV'],
        'instacart': ['Shoppable_Video_Ads'],
    }
    
    if retailer:
        retailers = [retailer]
    else:
        retailers = ['amazon', 'walmart', 'instacart']
    
    for ret in retailers:
        for folder_pattern in video_folders.get(ret, []):
            # Look in client subdirectories
            pattern = os.path.join(output_dir, ret, '*', folder_pattern, '*.png')
            images.extend(glob.glob(pattern))
            
            # Also check direct folder (no client subdir)
            pattern = os.path.join(output_dir, ret, folder_pattern, '*.png')
            images.extend(glob.glob(pattern))
    
    return sorted(set(images))


def find_json_for_image(image_path: str) -> str:
    """Find the JSON run file that corresponds to an image."""
    # Extract datetime from image filename
    # Format: amazon__brand__Sponsored_Brand_Video__client__keyword__D2025-11-20_T19-15.08_0.png
    filename = os.path.basename(image_path)
    
    # Extract datetime: D2025-11-20_T19-15.08 -> 20251120_191508
    import re
    match = re.search(r'D(\d{4})-(\d{2})-(\d{2})_T(\d{2})-(\d{2})\.(\d{2})', filename)
    if not match:
        return None
    
    # Build datetime pattern - canonical format is 14 digits no underscore
    g = match.groups()
    datetime_canonical = f"{g[0]}{g[1]}{g[2]}{g[3]}{g[4]}{g[5]}"
    
    # Find the runs directory (go up from video folder to client, then to runs)
    # image_path: output/amazon/Proactiv/Sponsored_Brand_Video/amazon__...png
    # image_path: output/walmart/client/SBV/walmart__...png
    # runs_dir:   output/<retailer>/<client>/runs/
    parts = image_path.split(os.sep)
    try:
        # Find the video folder (SBV, Sponsored_Brand_Video, Shoppable_Video_Ads)
        video_folders = ['Sponsored_Brand_Video', 'SBV', 'Shoppable_Video_Ads']
        sbv_idx = next(i for i, p in enumerate(parts) if any(vf in p for vf in video_folders))
        runs_dir = os.path.join(*parts[:sbv_idx], 'runs')
    except StopIteration:
        return None
    
    # Try different JSON patterns (retailers use different structures)
    patterns = [
        # Flat: runs/run_results_*_YYYYMMDDHHMMSS.json
        os.path.join(runs_dir, f'*{datetime_canonical}*.json'),
        # Walmart nested: runs/YYYYMMDDHHMMSS/run_results_*.json
        os.path.join(runs_dir, datetime_canonical, 'run_results_*.json'),
    ]
    
    for pattern in patterns:
        matches = glob.glob(pattern)
        if matches:
            return matches[0]
    
    return None


def format_for_frontend(detection: dict) -> dict:
    """
    Format detection for frontend consumption.
    
    Frontend expects pixel values at top level with image dimensions,
    and does its own proportional conversion.
    """
    if not detection or 'image_width' not in detection:
        return detection
    
    return {
        'x': detection['x'],
        'y': detection['y'],
        'width': detection['width'],
        'height': detection['height'],
        'image_width': detection['image_width'],
        'image_height': detection['image_height'],
        'border_radius': detection.get('border_radius', 0),
        'detection_method': detection.get('detection_method', 'auto'),
    }


def update_json_with_overlay(json_path: str, image_path: str, overlay_data: dict) -> bool:
    """Update a JSON file with overlay data for a specific image."""
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
        
        # Find the ad entry that matches this image
        image_filename = os.path.basename(image_path)
        updated = False
        
        # Handle different JSON structures
        # Match on datetime + index since filenames may differ slightly
        import re
        match = re.search(r'D(\d{4}-\d{2}-\d{2}_T\d{2}-\d{2}\.\d{2})_(\d+)\.png', image_filename)
        if not match:
            return False
        datetime_part, index = match.groups()
        
        if 'ads' in data:
            for ad in data['ads']:
                # Check both image_path and screenshot fields
                img_field = ad.get('image_path') or ad.get('screenshot') or ''
                # Match on datetime and index
                if datetime_part in img_field and f'_{index}.png' in img_field:
                    ad['video_overlay'] = overlay_data
                    updated = True
                    break
        
        if updated:
            with open(json_path, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        
        return False
    except Exception as e:
        print(f"Error updating {json_path}: {e}")
        return False


def process_image(image_path: str, retailer: str, dry_run: bool = False) -> dict:
    """Process a single image and return detection results."""
    # Determine ad type from path
    if 'Sponsored_Brand_Video' in image_path or '/SBV/' in image_path:
        ad_type = 'sbv'
    elif 'Shoppable_Video_Ads' in image_path:
        ad_type = 'video'  # Instacart video ads
    else:
        return None
    
    # Run detection
    try:
        detection = auto_detect_video_bounds(Path(image_path), retailer, ad_type)
        if detection:
            return format_for_frontend(detection)
    except Exception as e:
        print(f"Error detecting overlay for {image_path}: {e}")
    
    return None


def main():
    parser = argparse.ArgumentParser(description='Batch update video overlay metadata')
    parser.add_argument('--output-dir', default='output', help='Output directory with images')
    parser.add_argument('--retailer', choices=['amazon', 'walmart', 'instacart'], 
                        help='Process only specific retailer')
    parser.add_argument('--dry-run', action='store_true', 
                        help='Show what would be done without making changes')
    parser.add_argument('--limit', type=int, help='Limit number of images to process')
    parser.add_argument('--output-json', help='Write all detections to a single JSON file')
    args = parser.parse_args()
    
    # Find all video images
    images = find_video_images(args.output_dir, args.retailer)
    
    if args.limit:
        images = images[:args.limit]
    
    print(f"Found {len(images)} video images to process")
    
    results = {
        'processed': 0,
        'success': 0,
        'failed': 0,
        'detections': {}
    }
    
    for i, image_path in enumerate(images):
        # Determine retailer from path
        path_parts = image_path.split(os.sep)
        retailer = None
        for part in path_parts:
            if part in ['amazon', 'walmart', 'instacart']:
                retailer = part
                break
        
        if not retailer:
            print(f"Could not determine retailer for {image_path}")
            continue
        
        print(f"[{i+1}/{len(images)}] Processing: {os.path.basename(image_path)}")
        
        detection = process_image(image_path, retailer, args.dry_run)
        
        if detection:
            results['success'] += 1
            results['detections'][image_path] = detection
            
            if not args.dry_run:
                # Try to find and update JSON
                json_path = find_json_for_image(image_path)
                if json_path:
                    if update_json_with_overlay(json_path, image_path, detection):
                        print(f"  Updated: {json_path}")
                    else:
                        print(f"  Could not update JSON (image not found in file)")
            else:
                print(f"  Detection: x={detection['x']}, "
                      f"y={detection['y']}, "
                      f"w={detection['width']}, "
                      f"h={detection['height']}")
        else:
            results['failed'] += 1
            print(f"  Failed to detect overlay")
        
        results['processed'] += 1
    
    # Summary
    print(f"\n{'='*50}")
    print(f"Processed: {results['processed']}")
    print(f"Success: {results['success']}")
    print(f"Failed: {results['failed']}")
    
    # Optionally write all detections to a single JSON
    if args.output_json:
        with open(args.output_json, 'w') as f:
            json.dump(results['detections'], f, indent=2)
        print(f"\nWrote detections to: {args.output_json}")


if __name__ == '__main__':
    main()
