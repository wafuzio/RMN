#!/usr/bin/env python3
"""
Fix Gallery Card Margins - Remove white border from vertical gallery cards.

The scraper was capturing #tile-container or body instead of #tile, which included
extra padding/margin. The actual #tile element is 307px wide, but captures were
346px or 339px wide.

This script crops vertical gallery cards to remove the white margin on the right.
It detects the actual content boundary by finding where the white margin starts.
"""

import sys
from pathlib import Path
from PIL import Image
import numpy as np

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def find_right_content_edge(img):
    """
    Find the right edge of actual content by detecting where solid white begins.
    Scans from right to left looking for non-white pixels.
    """
    arr = np.array(img)
    height, width = arr.shape[:2]
    
    # Sample the middle 60% of the image height (avoid top/bottom borders)
    start_y = int(height * 0.2)
    end_y = int(height * 0.8)
    
    # Scan from right to left
    for x in range(width - 1, 0, -1):
        col = arr[start_y:end_y, x]
        # Check if this column has any non-white pixels
        # White is (255, 255, 255) or close to it
        if len(col.shape) == 3:  # RGB
            # Check if any pixel is not white (threshold 250)
            if np.any(col[:, :3] < 250):
                return x + 1  # Include this column
        else:  # Grayscale
            if np.any(col < 250):
                return x + 1
    
    return width  # No white margin found


def fix_gallery_cards(dry_run=False, force=False):
    """Find and fix gallery cards with white margins."""
    
    # Find all Gallery_Cards PNGs
    gallery_cards = list(OUTPUT_DIR.glob("**/Gallery_Cards/*.png"))
    print(f"Found {len(gallery_cards)} gallery card images")
    
    fixed = 0
    skipped = 0
    errors = 0
    
    for img_path in gallery_cards:
        try:
            with Image.open(img_path) as img:
                width, height = img.size
                
                # Only process vertical cards (not banners)
                # Vertical cards are roughly square (height > width * 0.8)
                # Banners are wide (width > height * 2)
                is_vertical = height > width * 0.8 and width < 400
                
                if not is_vertical:
                    skipped += 1
                    continue
                
                # Find the actual content edge
                content_right = find_right_content_edge(img)
                
                # If there's significant white margin (> 5px), crop it
                margin = width - content_right
                if margin > 5:
                    # Crop to content (keep 2px buffer for anti-aliasing)
                    new_width = content_right + 2
                    new_img = img.crop((0, 0, new_width, height))
                    
                    if dry_run:
                        print(f"[DRY RUN] Would crop: {img_path.name} ({width}x{height} -> {new_width}x{height}, removing {margin}px margin)")
                    else:
                        new_img.save(img_path, optimize=True)
                        print(f"✓ Fixed: {img_path.name} ({width} -> {new_width}px, -{margin}px)")
                    fixed += 1
                else:
                    skipped += 1
                    
        except Exception as e:
            print(f"✗ Error processing {img_path.name}: {e}")
            errors += 1
    
    print(f"\n{'='*50}")
    print(f"Summary:")
    print(f"  Fixed: {fixed}")
    print(f"  Skipped (no margin or banner): {skipped}")
    print(f"  Errors: {errors}")
    if dry_run:
        print(f"  (DRY RUN - no changes made)")
    print(f"{'='*50}")
    
    return fixed


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    force = "--force" in sys.argv
    
    if dry_run:
        print("DRY RUN MODE - no files will be modified\n")
    
    fix_gallery_cards(dry_run=dry_run, force=force)
