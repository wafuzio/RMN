#!/usr/bin/env python3
"""
Add video_overlay metadata to existing Walmart SBV ad JSONs.
This allows the frontend to position videos accurately without dynamic calculation.
"""

import json
import os
from pathlib import Path
from PIL import Image

OUTPUT_ROOT = Path("/Users/dan.maguire/Documents/Amazon_Scrape/output")

# Video slot dimensions for Walmart SBV ads (constant)
VIDEO_SLOT = {"x": 0, "y": 18, "width": 544, "height": 301}

def process_json_file(json_path: Path) -> int:
    """Add video_overlay metadata to ads in a JSON file. Returns count of ads updated."""
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Handle both canonical and legacy JSON structures
    ads = data.get('ads', [])
    if not ads and 'results' in data:
        ads = data['results'][0].get('ads', [])
    
    updated_count = 0
    
    for ad in ads:
        # Only process SBV ads that don't already have video_overlay
        if ad.get('type') in ['SBV', 'Sponsored_Brand_Video'] and 'video_overlay' not in ad:
            image_path = ad.get('image_path')
            if not image_path:
                continue
            
            # Construct full path to image
            retailer = ad.get('retailer', 'walmart')
            client = ad.get('client', 'unknown')
            full_image_path = OUTPUT_ROOT / retailer / client / image_path
            
            if not full_image_path.exists():
                print(f"⚠️  Image not found: {full_image_path}")
                continue
            
            # Get image dimensions
            try:
                with Image.open(full_image_path) as img:
                    width, height = img.size
                
                # Add video_overlay metadata
                ad['video_overlay'] = {
                    "x": VIDEO_SLOT["x"],
                    "y": VIDEO_SLOT["y"],
                    "width": VIDEO_SLOT["width"],
                    "height": VIDEO_SLOT["height"],
                    "image_width": width,
                    "image_height": height
                }
                updated_count += 1
                print(f"✓ Added overlay metadata to {ad.get('brand', 'unknown')} ({width}×{height})")
                
            except Exception as e:
                print(f"❌ Error processing {full_image_path}: {e}")
    
    if updated_count > 0:
        # Write back to file
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"💾 Updated {json_path} with {updated_count} ads")
    
    return updated_count

def main():
    """Process all Walmart run JSON files."""
    
    walmart_dir = OUTPUT_ROOT / "walmart"
    if not walmart_dir.exists():
        print(f"❌ Walmart directory not found: {walmart_dir}")
        return
    
    total_updated = 0
    total_files = 0
    
    # Find all run_results JSON files
    for client_dir in walmart_dir.iterdir():
        if not client_dir.is_dir():
            continue
        
        runs_dir = client_dir / "runs"
        if not runs_dir.exists():
            continue
        
        for run_dir in runs_dir.iterdir():
            if not run_dir.is_dir():
                continue
            
            for json_file in run_dir.glob("run_results_*.json"):
                print(f"\n📄 Processing {json_file.relative_to(OUTPUT_ROOT)}...")
                count = process_json_file(json_file)
                total_updated += count
                total_files += 1
    
    print(f"\n✅ Complete! Updated {total_updated} ads across {total_files} files")

if __name__ == "__main__":
    main()
