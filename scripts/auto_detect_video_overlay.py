#!/usr/bin/env python3
"""
Auto-detect video overlay bounds in SBV screenshots using computer vision.
Uses retailer-specific rules to find the video region.
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Optional, Tuple, Dict
import json


def detect_walmart_sbv_bounds(image_path: Path) -> Optional[Dict]:
    """
    Detect video bounds in Walmart SBV screenshots.
    
    Walmart SBV layout:
    - Video on left ~50% of width
    - Thin gray borders top/bottom that span FULL width
    - Product cards on right side (white background)
    
    Strategy: Detect gray borders in the WHITE product area (right side)
    where they're clearly visible, then apply to video area.
    """
    img = cv2.imread(str(image_path))
    if img is None:
        return None
    
    height, width = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # --- Detect right edge (where white product area starts) ---
    # Look for a vertical column that is consistently white from top to bottom
    # This avoids false positives from white objects inside the video
    right_edge = width // 2  # Default to 50%
    
    for x in range(int(width * 0.35), int(width * 0.60)):
        # Check if this entire column (within content area) is white
        # Sample from ~20px from top to ~20px from bottom
        col = gray[20:height-20, x]
        if col.size == 0:
            continue
        mean_val = np.mean(col)
        min_val = np.min(col)
        
        # Column must be consistently white (high mean AND high minimum)
        if mean_val > 250 and min_val > 240:
            right_edge = x
            break
    
    # --- Detect gray borders using the WHITE AREA (right side) ---
    # The gray border is much easier to see against white background
    # Sample from the right 1/3 of the image where product cards are
    sample_x_start = int(width * 0.7)
    sample_x_end = int(width * 0.95)
    
    # Find TOP border: skip first 8px, then find gray->white transition
    top_border = 0
    found_gray = False
    for y in range(8, min(50, height)):  # Start at 8px from top
        row = gray[y, sample_x_start:sample_x_end]
        mean_val = np.mean(row)
        
        if mean_val < 250:  # Gray row
            found_gray = True
        elif found_gray and mean_val > 253:  # White after gray
            top_border = y
            break
    
    # Now check if there's a white gap before the actual video content
    # Sample across the VIDEO area (left side, 0 to right_edge)
    if top_border > 0:
        for y in range(top_border, min(top_border + 30, height)):
            video_row = gray[y, 5:right_edge-5]
            mean_val = np.mean(video_row)
            # If this row is NOT white (has actual video content), we found the top
            if mean_val < 250:
                top_border = y
                break
    
    # Find BOTTOM border: skip last 8px, then find gray->white transition
    bottom_border = height
    found_gray = False
    for y in range(height - 9, max(height - 50, 0), -1):  # Start at 8px from bottom
        row = gray[y, sample_x_start:sample_x_end]
        mean_val = np.mean(row)
        
        if mean_val < 250:  # Gray row
            found_gray = True
        elif found_gray and mean_val > 253:  # White after gray
            bottom_border = y + 1
            break
    
    # Check if there's a white gap before the actual video content
    # Scan UP from bottom_border until we hit non-white video content
    if bottom_border < height:
        for y in range(bottom_border - 1, max(bottom_border - 30, top_border), -1):
            video_row = gray[y, 5:right_edge-5]
            mean_val = np.mean(video_row)
            # If this row is NOT white (has actual video content), we found the bottom
            if mean_val < 250:
                bottom_border = y + 1
                break
    
    # --- Left edge ---
    left_edge = 0
    
    # Sanity checks
    if top_border >= bottom_border or (bottom_border - top_border) < height * 0.5:
        # Detection failed, use defaults
        top_border = int(height * 0.04)
        bottom_border = int(height * 0.99)
    
    if right_edge <= left_edge:
        right_edge = width // 2
    
    # Add 4px buffer to right edge - the detection finds the white boundary
    # but the video content extends slightly into it
    right_edge = min(right_edge + 4, width)
    
    # Pull bottom up 4px - detection overshoots into the white gap below gray border
    bottom_border = max(bottom_border - 4, top_border + 1)
    
    return {
        'x': left_edge,
        'y': top_border,
        'width': right_edge - left_edge,
        'height': bottom_border - top_border,
        'image_width': width,
        'image_height': height,
        'border_radius': 0,
        'detection_method': 'auto_walmart_sbv'
    }


def detect_instacart_video_bounds(image_path: Path) -> Optional[Dict]:
    """
    Detect video bounds in Instacart video ad screenshots.
    
    Instacart layout:
    - Video is inset within the ad card on all 4 sides
    - Surrounded by white/light background
    - Has rounded corners
    - Product listings to the right
    
    Strategy: Find all 4 edges by detecting where solid/multicolor 
    video content begins (not white/light gray background).
    """
    img = cv2.imread(str(image_path))
    if img is None:
        return None
    
    height, width = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # First, find approximate video region (left ~40% of image)
    video_region_right = int(width * 0.45)
    
    # --- Find LEFT edge ---
    # First pass: skip past any gray border (uniform gray near edge)
    # Then find where non-white content starts
    left_edge = 8
    passed_gray_border = False
    for x in range(8, min(100, width)):
        col = gray[height//4:height*3//4, x]
        mean_val = np.mean(col)
        std_val = np.std(col)
        
        # Gray border: uniform (low std) and grayish (220-250)
        is_gray_border = (220 < mean_val < 250) and std_val < 15
        
        if is_gray_border and not passed_gray_border:
            # Still in gray border, keep scanning
            continue
        
        passed_gray_border = True
        
        # Now look for non-white content
        if mean_val < 252:
            left_edge = x
            break
    
    # --- Find RIGHT edge ---
    # Primary: Find where sustained white starts (5+ consecutive white columns)
    # Fallback: If white found too early (video has white content), look for play button
    
    right_edge = video_region_right
    first_white_run_start = None
    consecutive_white = 0
    
    for x in range(left_edge + 50, video_region_right):
        col = gray[height//4:height*3//4, x]
        mean_val = np.mean(col)
        if mean_val >= 252:
            consecutive_white += 1
            if consecutive_white >= 5:
                first_white_run_start = x - 4
                right_edge = first_white_run_start
                break
        else:
            consecutive_white = 0
    
    # Check if we stopped too early (white video content case)
    # Expected video width is ~500px, if we stopped before ~480, check for play button
    if first_white_run_start and (first_white_run_start - left_edge) < 480:
        # Look for play button (dark pixels with min < 120 in top 50px of video area)
        play_button_right = None
        for x in range(first_white_run_start, min(first_white_run_start + 150, width)):
            col = gray[90:145, x]  # Top portion where play button would be
            if np.min(col) < 120:  # Dark pixel (play button)
                play_button_right = x
            elif play_button_right and np.min(col) >= 200:
                # We were in play button and now we're out - stop
                break
        
        if play_button_right:
            # Found play button - find product tile start and set right edge to midpoint
            product_start = None
            for x in range(play_button_right + 5, min(play_button_right + 80, width)):
                col = gray[height//4:height*3//4, x]
                mean_val = np.mean(col)
                std_val = np.std(col)
                if std_val > 30 or mean_val < 240:
                    product_start = x
                    break
            
            if product_start:
                right_edge = (play_button_right + product_start) // 2
            else:
                right_edge = play_button_right + 15  # Small buffer past play button
    
    # --- Find TOP edge ---
    # Instacart layout: Logo -> "Sponsored" text -> white gap -> Video
    # Find the LAST solid white row (true white stripe) before video content
    
    # Find the last solid white row (mean >= 252 AND very uniform std < 5)
    last_solid_white = 8
    for y in range(8, min(120, height)):
        row = gray[y, left_edge:right_edge]
        mean_val = np.mean(row)
        std_val = np.std(row)
        # Solid white stripe: high mean AND very low variation
        if mean_val >= 252 and std_val < 5:
            last_solid_white = y
    
    # Video starts right after the last solid white row
    top_edge = last_solid_white + 1
    
    # Verify there's actual content there (not white)
    if top_edge < height:
        row = gray[top_edge, left_edge:right_edge]
        if np.mean(row) >= 250:
            # Still white-ish, scan forward to find content
            for y in range(top_edge, min(150, height)):
                row = gray[y, left_edge:right_edge]
                if np.mean(row) < 250:
                    top_edge = y
                    break
    
    # --- Find BOTTOM edge ---
    # Scan from bottom, find where actual video content starts
    # Skip white, and skip uniform gray border only in bottom 5% of image
    bottom_edge = height - 8
    gray_border_zone = height - int(height * 0.05)  # Bottom 5%
    
    for y in range(height - 9, max(height - 150, 0), -1):
        row = gray[y, left_edge:right_edge]
        mean_val = np.mean(row)
        std_val = np.std(row)
        
        # Skip white (>= 252)
        if mean_val >= 252:
            continue
        
        # Skip uniform gray border, but only in bottom 5% of image
        if y > gray_border_zone:
            is_gray_border = 200 < mean_val < 250 and std_val < 5
            if is_gray_border:
                continue
        
        # Found actual video content
        bottom_edge = y + 1
        break
    
    # Sanity checks
    if left_edge >= right_edge or top_edge >= bottom_edge:
        return None
    
    if (right_edge - left_edge) < width * 0.15:
        return None
    
    if (bottom_edge - top_edge) < height * 0.3:
        return None
    
    return {
        'x': left_edge,
        'y': top_edge,
        'width': right_edge - left_edge,
        'height': bottom_edge - top_edge,
        'image_width': width,
        'image_height': height,
        'border_radius': 8,  # Instacart uses rounded corners
        'detection_method': 'auto_instacart'
    }


def detect_amazon_sbv_bounds(image_path: Path) -> Optional[Dict]:
    """
    Detect video bounds in Amazon SBV screenshots.
    
    Amazon SBV layout:
    - Brand logo, tagline, "Shop" text at top
    - Video on left ~50% of width
    - Product tiles on right (white background)
    - May have gray border wrapping video and products
    """
    img = cv2.imread(str(image_path))
    if img is None:
        return None
    
    height, width = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # --- Find LEFT edge ---
    # Skip any white/gray border, find where video content starts
    left_edge = 0
    for x in range(0, min(50, width)):
        col = gray[height//4:height*3//4, x]
        mean_val = np.mean(col)
        # If it's not white/light (< 252), it's video content
        if mean_val < 252:
            left_edge = x
            break
    
    # --- Find RIGHT edge ---
    # Strategy 1: Look for pure white column (clearest signal)
    # Strategy 2: Look for uniform gray/white after varied video content
    # Use aspect ratio to estimate expected position as hint
    estimated_video_height = int(height * 0.75)
    expected_width = int(estimated_video_height * 16 / 9)
    
    right_edge = width // 2  # Default
    
    # First: scan for pure white column (most reliable)
    for x in range(left_edge + 50, int(width * 0.60)):
        col = gray[height//4:height*3//4, x]
        mean_val = np.mean(col)
        if mean_val >= 254:  # Pure white column found
            right_edge = x
            break
    
    # If no pure white found, find product tile border then scan left to video edge
    # Product tile white is TALL (50+ pixels), logo text white is short (<15px)
    if right_edge == width // 2:
        # Sample bottom 100 pixels (excluding bottom 10px buffer)
        y_start = height - 100
        y_end = height - 10
        min_start = max(left_edge + 400, int(width * 0.40))
        product_border = -1
        
        # First find product tile border (tall white column)
        for x in range(min_start, int(width * 0.60)):
            col = gray[y_start:y_end, x]
            white_pixels = np.sum(col >= 254)
            if white_pixels >= 50:
                product_border = x
                break
        
        # Check for strong black stripe in the gap area (within 60px of product border)
        # Some videos have a black border at the edge
        if product_border > 0:
            mid_y_start = height // 4
            mid_y_end = height * 3 // 4
            
            # Only scan the gap area (product_border to product_border - 60)
            found_black_stripe = False
            scan_limit = max(product_border - 60, left_edge + 100)
            for x in range(product_border, scan_limit, -1):
                col = gray[mid_y_start:mid_y_end, x]
                black_pixels = np.sum(col < 50)
                # Strong black stripe = 50+ black pixels
                if black_pixels >= 50:
                    right_edge = x + 1
                    found_black_stripe = True
                    break
            
            # No black stripe found in gap, use product border
            if not found_black_stripe:
                right_edge = product_border
    
    # --- Find TOP edge ---
    # Amazon SBV has: white margin -> logo/headline -> "Shop" link -> white gap -> video
    # Find where we go from white/text area to actual video content
    # Video content is significantly darker (mean < 200) and stays dark
    top_edge = 0
    last_white_row = 0
    for y in range(0, min(150, height)):
        row = gray[y, left_edge:right_edge]
        mean_val = np.mean(row)
        
        # Track last white row (the gap before video)
        if mean_val >= 254:
            last_white_row = y
        # Video content: significantly darker after a white gap
        # Use stricter threshold (< 200) to avoid catching light text areas
        elif mean_val < 200 and last_white_row > 20:
            # Make sure it's not just a blip - check next few rows
            if y + 3 < height:
                next_rows = gray[y:y+4, left_edge:right_edge]
                next_mean = np.mean(next_rows)
                if next_mean < 200:
                    top_edge = y
                    break
    # Fallback if no white gap detected
    if top_edge == 0:
        # Use default top margin as heuristic
        top_edge = int(height * 0.04)
    
    # --- Find BOTTOM edge ---
    # Scan from bottom up: skip white/gray, find video content
    # Video content is darker (< 180) or has variation (std > 5)
    bottom_edge = height
    for y in range(height - 1, max(height - 80, 0), -1):
        row = gray[y, left_edge:right_edge]
        mean_val = np.mean(row)
        std_val = np.std(row)
        
        # Skip white or uniform gray (light and low variation)
        if mean_val > 180 and std_val < 5:
            continue
        # Found video content (darker or varied)
        if mean_val < 180 or std_val > 5:
            bottom_edge = y + 1
            break
    
    # Sanity checks
    if left_edge >= right_edge or top_edge >= bottom_edge:
        return None
    
    return {
        'x': left_edge,
        'y': top_edge,
        'width': right_edge - left_edge,
        'height': bottom_edge - top_edge,
        'image_width': width,
        'image_height': height,
        'border_radius': 0,
        'detection_method': 'auto_amazon_sbv'
    }


def auto_detect_video_bounds(image_path: Path, retailer: str, ad_type: str) -> Optional[Dict]:
    """
    Auto-detect video overlay bounds based on retailer and ad type.
    """
    retailer = retailer.lower()
    ad_type = ad_type.lower()
    
    if retailer == 'walmart' and 'sbv' in ad_type:
        return detect_walmart_sbv_bounds(image_path)
    elif retailer == 'instacart':
        return detect_instacart_video_bounds(image_path)
    elif retailer == 'amazon' and ('sbv' in ad_type or 'video' in ad_type):
        return detect_amazon_sbv_bounds(image_path)
    
    return None


def visualize_detection(image_path: Path, bounds: Dict, output_path: Optional[Path] = None):
    """Draw detected bounds on image for verification."""
    import subprocess
    import tempfile
    
    img = cv2.imread(str(image_path))
    if img is None:
        return
    
    img_h, img_w = img.shape[:2]
    x, y = bounds['x'], bounds['y']
    w, h = bounds['width'], bounds['height']
    
    print(f"Image size: {img_w}x{img_h}")
    print(f"Box: x={x}, y={y}, w={w}, h={h}")
    print(f"Box bottom-right: ({x+w}, {y+h})")
    print(f"Gap at bottom: {img_h - (y + h)} pixels")
    
    # Draw rectangle
    cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)
    
    # Add label
    label = f"{w}x{h} @ ({x},{y})"
    cv2.putText(img, label, (x + 5, y + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    
    if output_path:
        cv2.imwrite(str(output_path), img)
    else:
        # Save to temp file and open with system viewer
        tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        cv2.imwrite(tmp.name, img)
        import sys
        import os
        if sys.platform == "darwin":
            subprocess.Popen(['open', tmp.name])
        elif sys.platform == "win32":
            os.startfile(tmp.name)
        else:
            subprocess.Popen(['xdg-open', tmp.name])


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python auto_detect_video_overlay.py <image_path> <retailer> [ad_type]")
        print("Example: python auto_detect_video_overlay.py image.png walmart sbv")
        sys.exit(1)
    
    image_path = Path(sys.argv[1])
    retailer = sys.argv[2]
    ad_type = sys.argv[3] if len(sys.argv) > 3 else 'sbv'
    
    bounds = auto_detect_video_bounds(image_path, retailer, ad_type)
    
    if bounds:
        print(json.dumps(bounds, indent=2))
        
        # Visualize
        visualize_detection(image_path, bounds)
    else:
        print("Could not detect video bounds")
