#!/usr/bin/env python3
"""
Crop white borders from ad images.

For Sponsored Logos and other ads with white padding/borders, this script:
1. Detects the actual content area (non-white pixels)
2. Crops to the content, removing white borders
3. Optionally centers the content if it's smaller than expected dimensions

Usage:
    python3 tools/crop_white_borders.py --retailer target --ad-type Sponsored_Logo --preview
    python3 tools/crop_white_borders.py --retailer target --ad-type Sponsored_Logo --apply
    python3 tools/crop_white_borders.py --all --apply
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from PIL import Image, ImageChops
except ImportError:
    print("ERROR: PIL/Pillow not installed. Run: pip install Pillow")
    sys.exit(1)


def detect_content_bbox(img: Image.Image, threshold: int = 250) -> Tuple[int, int, int, int]:
    """
    Detect the bounding box of non-white content in an image.
    
    Returns (left, top, right, bottom) or None if image is all white.
    threshold: pixel values above this (0-255) are considered "white"
    """
    # Convert to RGB if needed
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    # Get image data
    pixels = img.load()
    width, height = img.size
    
    # Find bounds
    min_x, min_y = width, height
    max_x, max_y = 0, 0
    
    found_content = False
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            # Check if pixel is NOT white (all channels below threshold)
            if r < threshold or g < threshold or b < threshold:
                found_content = True
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
    
    if not found_content:
        return None
    
    # Add 1 to max values since crop is exclusive on right/bottom
    return (min_x, min_y, max_x + 1, max_y + 1)


def crop_white_borders(image_path: Path, threshold: int = 250, min_crop_pixels: int = 5) -> Tuple[bool, str]:
    """
    Crop white borders from an image.
    
    Returns (success, message)
    min_crop_pixels: minimum pixels to crop before considering it worthwhile
    """
    try:
        with Image.open(image_path) as img:
            original_size = img.size
            
            # Detect content bbox
            bbox = detect_content_bbox(img, threshold)
            
            if bbox is None:
                return False, "Image is all white (no content detected)"
            
            left, top, right, bottom = bbox
            
            # Check if cropping is worthwhile
            crop_left = left
            crop_top = top
            crop_right = original_size[0] - right
            crop_bottom = original_size[1] - bottom
            
            total_crop = crop_left + crop_top + crop_right + crop_bottom
            
            if total_crop < min_crop_pixels:
                return False, f"No significant borders (only {total_crop}px total)"
            
            # Crop the image
            cropped = img.crop(bbox)
            new_size = cropped.size
            
            # Save back to same file
            cropped.save(image_path, quality=95, optimize=True)
            
            return True, f"Cropped {original_size[0]}x{original_size[1]} → {new_size[0]}x{new_size[1]} (removed {total_crop}px borders)"
    
    except Exception as e:
        return False, f"Error: {e}"


def process_ad_images(retailer: str, client: str, output_root: Path, ad_type_filter: str = None, 
                     apply: bool = False) -> Dict:
    """Process all images for a retailer/client."""
    results = {
        "retailer": retailer,
        "client": client,
        "total_images": 0,
        "cropped": 0,
        "skipped": 0,
        "errors": 0,
        "changes": []
    }
    
    client_dir = output_root / retailer / client
    if not client_dir.exists():
        return results
    
    # Find all image files in ad type subdirectories
    for ad_type_dir in client_dir.iterdir():
        if not ad_type_dir.is_dir():
            continue
        
        # Skip runs directory
        if ad_type_dir.name == "runs":
            continue
        
        # Filter by ad type if specified
        if ad_type_filter and ad_type_filter.lower() not in ad_type_dir.name.lower():
            continue
        
        # Process all PNG images in this directory
        for img_file in ad_type_dir.glob("*.png"):
            results["total_images"] += 1
            
            if apply:
                success, message = crop_white_borders(img_file)
                if success:
                    results["cropped"] += 1
                    results["changes"].append(f"  ✅ {img_file.name}: {message}")
                elif "Error:" in message:
                    results["errors"] += 1
                    results["changes"].append(f"  ❌ {img_file.name}: {message}")
                else:
                    results["skipped"] += 1
            else:
                # Preview mode - just detect
                try:
                    with Image.open(img_file) as img:
                        bbox = detect_content_bbox(img)
                        if bbox:
                            left, top, right, bottom = bbox
                            original_size = img.size
                            total_crop = left + top + (original_size[0] - right) + (original_size[1] - bottom)
                            if total_crop >= 5:
                                results["cropped"] += 1
                                results["changes"].append(f"  📋 {img_file.name}: Would crop {total_crop}px borders")
                            else:
                                results["skipped"] += 1
                        else:
                            results["skipped"] += 1
                except Exception as e:
                    results["errors"] += 1
                    results["changes"].append(f"  ❌ {img_file.name}: {e}")
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Crop white borders from ad images")
    parser.add_argument("--retailer", help="Retailer to process (or 'all')")
    parser.add_argument("--client", help="Specific client to process")
    parser.add_argument("--ad-type", help="Filter by ad type (e.g., 'Sponsored_Logo', 'Gallery_Cards')")
    parser.add_argument("--preview", action="store_true", help="Preview changes without applying")
    parser.add_argument("--apply", action="store_true", help="Apply cropping to images")
    parser.add_argument("--threshold", type=int, default=250, help="White threshold (0-255, default 250)")
    parser.add_argument("--all", action="store_true", help="Process all retailers and clients")
    
    args = parser.parse_args()
    
    if not args.preview and not args.apply:
        print("ERROR: Must specify either --preview or --apply")
        sys.exit(1)
    
    # Get output root
    script_dir = Path(__file__).parent.parent
    output_root = script_dir / "output"
    
    if not output_root.exists():
        print(f"ERROR: Output directory not found: {output_root}")
        sys.exit(1)
    
    print(f"{'PREVIEW' if args.preview else 'APPLYING'} white border cropping")
    print(f"Output root: {output_root}")
    print(f"White threshold: {args.threshold}")
    if args.ad_type:
        print(f"Ad type filter: {args.ad_type}")
    print()
    
    # Determine which retailers/clients to process
    targets = []
    
    if args.all:
        # Process all retailers and clients
        for retailer_dir in output_root.iterdir():
            if not retailer_dir.is_dir():
                continue
            for client_dir in retailer_dir.iterdir():
                if not client_dir.is_dir():
                    continue
                targets.append((retailer_dir.name, client_dir.name))
    elif args.retailer and args.client:
        targets.append((args.retailer, args.client))
    elif args.retailer:
        # Process all clients for this retailer
        retailer_dir = output_root / args.retailer
        if retailer_dir.exists():
            for client_dir in retailer_dir.iterdir():
                if client_dir.is_dir():
                    targets.append((args.retailer, client_dir.name))
    else:
        print("ERROR: Must specify --retailer or --all")
        sys.exit(1)
    
    print(f"Processing {len(targets)} retailer/client combinations\n")
    print(f"{'='*60}\n")
    
    total_images = 0
    total_cropped = 0
    total_skipped = 0
    total_errors = 0
    
    for retailer, client in targets:
        result = process_ad_images(retailer, client, output_root, args.ad_type, apply=args.apply)
        
        if result["total_images"] == 0:
            continue
        
        total_images += result["total_images"]
        total_cropped += result["cropped"]
        total_skipped += result["skipped"]
        total_errors += result["errors"]
        
        if result["cropped"] > 0 or result["errors"] > 0:
            print(f"📁 {retailer}/{client}")
            print(f"   Images: {result['total_images']}, Cropped: {result['cropped']}, Skipped: {result['skipped']}, Errors: {result['errors']}")
            
            # Show first 10 changes
            for change in result["changes"][:10]:
                print(change)
            
            if len(result["changes"]) > 10:
                print(f"   ... and {len(result['changes']) - 10} more")
            print()
    
    print(f"{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"Total images: {total_images}")
    print(f"Cropped: {total_cropped}")
    print(f"Skipped: {total_skipped}")
    print(f"Errors: {total_errors}")
    print(f"Mode: {'PREVIEW (no changes written)' if args.preview else 'APPLIED (images modified)'}")


if __name__ == "__main__":
    main()
