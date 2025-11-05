#!/usr/bin/env python3
"""
Add video_overlay metadata to all Walmart SBV ads.

This script scans all Walmart run_results JSON files and adds video_overlay
metadata to SBV ads that have videos but are missing the metadata.
"""

import json
import os
from pathlib import Path
from PIL import Image

# Walmart SBV video slot dimensions (in pixels on the reference 1078x341 image)
# These values were calibrated on the Vital Proteins ad
REFERENCE_IMAGE_WIDTH = 1078
REFERENCE_IMAGE_HEIGHT = 341
SBV_VIDEO_OVERLAY_PX = {
    "x": 2,
    "y": 15,  # Reduced from 19 to 15 to shift video up and cover the gap
    "width": 539,
    "height": 309,  # Increased from 305 to 309 to maintain bottom coverage
}

def get_image_dimensions(image_path):
    """Get the natural dimensions of an image file."""
    try:
        with Image.open(image_path) as img:
            return img.width, img.height
    except Exception as e:
        print(f"  ⚠️  Could not read image {image_path}: {e}")
        return None, None

def process_json_file(json_path):
    """Process a single JSON file and add video_overlay metadata to SBV ads."""
    print(f"\n📄 Processing: {json_path}")
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"  ❌ Error reading JSON: {e}")
        return 0
    
    ads = data.get('ads', [])
    if not ads:
        print(f"  ⚠️  No ads found in file")
        return 0
    
    updated_count = 0
    
    for ad in ads:
        # Only process SBV ads (check both 'type' and 'ad_type' fields)
        ad_type = ad.get('type') or ad.get('ad_type')
        if ad_type != 'SBV':
            continue
        
        # Note: We WILL overwrite existing video_overlay to ensure proportional scaling
        
        # Get image path to determine dimensions
        image_path_rel = ad.get('image_path')
        if not image_path_rel:
            print(f"  ⚠️  Ad missing image_path: {ad.get('brand', 'unknown')}")
            continue
        
        # Construct full image path
        # JSON is in: output/walmart/<client>/runs/<run_id>/run_results_*.json
        # Images are in: output/walmart/<client>/<ad_type>/filename.png
        json_dir = Path(json_path).parent
        client_dir = json_dir.parent.parent  # Go up to output/walmart/<client>/
        image_path = client_dir / image_path_rel
        
        # Check if a video file exists (same name as image but .mp4)
        video_path = image_path.with_suffix('.mp4')
        if not video_path.exists():
            # No video file, skip this ad
            continue
        
        # Get image dimensions
        img_width, img_height = get_image_dimensions(image_path)
        if not img_width or not img_height:
            print(f"  ⚠️  Could not get dimensions for: {image_path_rel}")
            continue
        
        # Add video_url if not present
        if not ad.get('video_url'):
            # Construct video URL path relative to image path
            video_path_rel = str(Path(image_path_rel).with_suffix('.mp4'))
            ad['video_url'] = video_path_rel
        
        # Calculate proportional overlay dimensions based on actual image size
        # Scale from reference image (1078x341) to actual image dimensions
        scale_x = img_width / REFERENCE_IMAGE_WIDTH
        scale_y = img_height / REFERENCE_IMAGE_HEIGHT
        
        overlay_x = round(SBV_VIDEO_OVERLAY_PX["x"] * scale_x)
        overlay_y = round(SBV_VIDEO_OVERLAY_PX["y"] * scale_y)
        overlay_width = round(SBV_VIDEO_OVERLAY_PX["width"] * scale_x)
        overlay_height = round(SBV_VIDEO_OVERLAY_PX["height"] * scale_y)
        
        # Add video_overlay metadata with scaled values
        ad['video_overlay'] = {
            "x": overlay_x,
            "y": overlay_y,
            "width": overlay_width,
            "height": overlay_height,
            "image_width": img_width,
            "image_height": img_height,
        }
        
        updated_count += 1
        print(f"  ✓ Added overlay + video_url to: {ad.get('brand', 'unknown')} ({img_width}x{img_height}) -> overlay: {overlay_width}x{overlay_height}")
    
    if updated_count > 0:
        # Write back to file
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"  💾 Updated {updated_count} ad(s)")
        except Exception as e:
            print(f"  ❌ Error writing JSON: {e}")
            return 0
    else:
        print(f"  ℹ️  No updates needed")
    
    return updated_count

def main():
    """Main function to process all Walmart SBV JSON files."""
    # Find all Walmart run_results JSON files
    output_dir = Path(__file__).parent.parent / 'output' / 'walmart'
    
    if not output_dir.exists():
        print(f"❌ Walmart output directory not found: {output_dir}")
        return
    
    print(f"🔍 Scanning for Walmart run_results JSON files in: {output_dir}")
    
    json_files = list(output_dir.glob('*/runs/*/run_results_*.json'))
    
    if not json_files:
        print(f"⚠️  No run_results JSON files found")
        return
    
    print(f"📊 Found {len(json_files)} JSON file(s)")
    
    total_updated = 0
    for json_file in sorted(json_files):
        updated = process_json_file(json_file)
        total_updated += updated
    
    print(f"\n{'='*60}")
    print(f"✅ Complete! Updated {total_updated} ad(s) across {len(json_files)} file(s)")
    print(f"{'='*60}")

if __name__ == '__main__':
    main()
