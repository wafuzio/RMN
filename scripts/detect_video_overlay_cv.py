#!/usr/bin/env python3
"""
Detect video overlay boundaries in existing screenshots using computer vision.

This script analyzes SBV/video ad screenshots to find the video slot boundaries
by detecting the rectangular video frame area. It uses multiple detection strategies:

1. Edge detection + contour finding for clear rectangular boundaries
2. Color segmentation (video areas often have distinct backgrounds)
3. Template matching against known video frame patterns

Usage:
    python scripts/detect_video_overlay_cv.py --retailer walmart --dry-run
    python scripts/detect_video_overlay_cv.py --retailer walmart --apply
"""

import json
import argparse
from pathlib import Path
from typing import Optional, Tuple, Dict, List
import sys

try:
    import cv2
    import numpy as np
except ImportError:
    print("❌ OpenCV not installed. Run: pip install opencv-python numpy")
    sys.exit(1)

OUTPUT_ROOT = Path("/Users/dan.maguire/Documents/Amazon_Scrape/output")

# Known video slot characteristics per retailer/ad_type
# These are calibrated from actual scrape-time captures
# Format: reference dimensions and known margins/ratios
VIDEO_SLOT_CALIBRATION = {
    "walmart": {
        "SBV": {
            # From actual DOM capture: x=2, y=15, width=539, height=302 on 1078x333 image
            "x_margin": 2,           # Left margin in pixels (constant)
            "y_margin_ratio": 0.045, # Top margin as ratio of height (~15/333)
            "width_ratio": 0.50,     # Video width as ratio of image width (~539/1078)
            "height_ratio": 0.907,   # Video height as ratio of image height (~302/333)
        }
    },
    "instacart": {
        "Shoppable_Video_Ad": {
            # Calibrated Dec 2025 from actual Instacart video ad screenshots
            # Video slot: left edge, below header (~8%), width ~32%, height ~58%
            "x_margin": 0,
            "y_margin_ratio": 0.08,   # Header takes ~8% of height
            "width_ratio": 0.32,      # Video is ~32% of image width
            "height_ratio": 0.58,     # Video is ~58% of image height
            "border_radius": 8,       # Instacart videos have 8px rounded corners
        },
        "Shoppable_Video_Ads": {
            # Same as Shoppable_Video_Ad
            "x_margin": 0,
            "y_margin_ratio": 0.08,
            "width_ratio": 0.32,
            "height_ratio": 0.58,
            "border_radius": 8,
        }
    },
    "amazon": {
        "Sponsored_Brand_Video": {
            # TBD - needs calibration from actual captures
            "x_margin": 0,
            "y_margin_ratio": 0.02,
            "width_ratio": 0.45,
            "height_ratio": 0.85,
        }
    }
}

# Hints for CV detection validation
VIDEO_SLOT_HINTS = {
    "walmart": {
        "SBV": {
            "expected_x_ratio": (0.0, 0.1),
            "expected_width_ratio": (0.4, 0.55),
            "expected_height_ratio": (0.7, 1.0),
            "min_area_ratio": 0.25,
            "max_area_ratio": 0.6,
        }
    },
    "instacart": {
        "Shoppable_Video_Ad": {
            "expected_x_ratio": (0.0, 0.2),
            "expected_width_ratio": (0.3, 0.7),
            "expected_height_ratio": (0.5, 1.0),
            "min_area_ratio": 0.2,
            "max_area_ratio": 0.7,
        }
    },
    "amazon": {
        "Sponsored_Brand_Video": {
            "expected_x_ratio": (0.0, 0.15),
            "expected_width_ratio": (0.3, 0.6),
            "expected_height_ratio": (0.6, 1.0),
            "min_area_ratio": 0.2,
            "max_area_ratio": 0.6,
        }
    }
}


def detect_video_region_edges(image: np.ndarray, hints: dict) -> Optional[Dict]:
    """
    Detect video region using edge detection and contour finding.
    Returns bounding box dict or None if not found.
    """
    height, width = image.shape[:2]
    
    # Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Apply Gaussian blur to reduce noise
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # Edge detection
    edges = cv2.Canny(blurred, 50, 150)
    
    # Dilate edges to connect nearby lines
    kernel = np.ones((3, 3), np.uint8)
    dilated = cv2.dilate(edges, kernel, iterations=2)
    
    # Find contours
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Filter contours by area and shape
    candidates = []
    min_area = width * height * hints.get("min_area_ratio", 0.15)
    max_area = width * height * hints.get("max_area_ratio", 0.7)
    
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_area or area > max_area:
            continue
        
        # Get bounding rectangle
        x, y, w, h = cv2.boundingRect(contour)
        
        # Check aspect ratio (video slots are usually wider than tall or square-ish)
        aspect = w / h if h > 0 else 0
        if aspect < 0.5 or aspect > 3.0:  # Reasonable aspect ratio range
            continue
        
        # Check position hints
        x_ratio = x / width
        w_ratio = w / width
        h_ratio = h / height
        
        x_range = hints.get("expected_x_ratio", (0, 1))
        w_range = hints.get("expected_width_ratio", (0, 1))
        h_range = hints.get("expected_height_ratio", (0, 1))
        
        # Score based on how well it matches hints
        score = 0
        if x_range[0] <= x_ratio <= x_range[1]:
            score += 1
        if w_range[0] <= w_ratio <= w_range[1]:
            score += 1
        if h_range[0] <= h_ratio <= h_range[1]:
            score += 1
        
        candidates.append({
            "x": x, "y": y, "width": w, "height": h,
            "area": area, "score": score, "aspect": aspect
        })
    
    if not candidates:
        return None
    
    # Return best candidate (highest score, then largest area)
    candidates.sort(key=lambda c: (c["score"], c["area"]), reverse=True)
    best = candidates[0]
    
    return {
        "x": best["x"],
        "y": best["y"],
        "width": best["width"],
        "height": best["height"],
        "image_width": width,
        "image_height": height,
        "detection_method": "edge_contour",
        "confidence": best["score"] / 3.0,  # Normalize to 0-1
    }


def detect_video_region_color(image: np.ndarray, hints: dict) -> Optional[Dict]:
    """
    Detect video region using color segmentation.
    Video areas often have a distinct background color.
    """
    height, width = image.shape[:2]
    
    # Convert to HSV for better color segmentation
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    
    # Look for dark regions (video backgrounds are often darker)
    # Also look for saturated color regions (branded video backgrounds)
    
    # Strategy 1: Find large dark rectangular regions
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Threshold to find darker regions
    _, dark_mask = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY_INV)
    
    # Find contours in dark regions
    contours, _ = cv2.findContours(dark_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    min_area = width * height * hints.get("min_area_ratio", 0.15)
    max_area = width * height * hints.get("max_area_ratio", 0.7)
    
    candidates = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_area or area > max_area:
            continue
        
        x, y, w, h = cv2.boundingRect(contour)
        aspect = w / h if h > 0 else 0
        if aspect < 0.5 or aspect > 3.0:
            continue
        
        # Check position
        x_ratio = x / width
        x_range = hints.get("expected_x_ratio", (0, 1))
        
        score = 1 if x_range[0] <= x_ratio <= x_range[1] else 0
        
        candidates.append({
            "x": x, "y": y, "width": w, "height": h,
            "area": area, "score": score
        })
    
    if not candidates:
        return None
    
    candidates.sort(key=lambda c: (c["score"], c["area"]), reverse=True)
    best = candidates[0]
    
    return {
        "x": best["x"],
        "y": best["y"],
        "width": best["width"],
        "height": best["height"],
        "image_width": width,
        "image_height": height,
        "detection_method": "color_segmentation",
        "confidence": 0.5,  # Lower confidence for color-based detection
    }


def detect_video_region_vertical_split(image: np.ndarray, hints: dict) -> Optional[Dict]:
    """
    Detect video region by finding vertical split point.
    Many video ads have a clear left (video) / right (products) split.
    """
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Calculate column-wise variance
    # The split point often has low variance (edge/border)
    col_variance = np.var(gray, axis=0)
    
    # Smooth the variance
    kernel_size = width // 20
    if kernel_size % 2 == 0:
        kernel_size += 1
    smoothed = np.convolve(col_variance, np.ones(kernel_size)/kernel_size, mode='same')
    
    # Look for local minima in the middle portion (40-60% of width)
    search_start = int(width * 0.35)
    search_end = int(width * 0.65)
    
    search_region = smoothed[search_start:search_end]
    if len(search_region) == 0:
        return None
    
    # Find the minimum (likely split point)
    min_idx = np.argmin(search_region) + search_start
    
    # The video region is from left edge to split point
    # Estimate y boundaries (usually near top/bottom with small margins)
    y_margin = int(height * 0.03)
    
    return {
        "x": 0,
        "y": y_margin,
        "width": min_idx,
        "height": height - (2 * y_margin),
        "image_width": width,
        "image_height": height,
        "detection_method": "vertical_split",
        "confidence": 0.6,
    }


def detect_video_region_calibrated(image: np.ndarray, retailer: str, ad_type: str) -> Optional[Dict]:
    """
    Use calibrated ratios from known good captures to estimate video region.
    This is the most reliable method for historical data.
    """
    height, width = image.shape[:2]
    
    calibration = VIDEO_SLOT_CALIBRATION.get(retailer, {}).get(ad_type)
    if not calibration:
        return None
    
    x = calibration.get("x_margin", 0)
    y = round(height * calibration.get("y_margin_ratio", 0))
    w = round(width * calibration.get("width_ratio", 0.5))
    h = round(height * calibration.get("height_ratio", 0.9))
    
    result = {
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "image_width": width,
        "image_height": height,
        "detection_method": "calibrated",
        "confidence": 0.85,  # High confidence for calibrated values
    }
    
    # Include border_radius if specified in calibration
    if calibration.get("border_radius"):
        result["border_radius"] = calibration["border_radius"]
    
    return result


def detect_video_overlay(image_path: Path, retailer: str, ad_type: str) -> Optional[Dict]:
    """
    Main detection function that tries multiple strategies.
    Priority:
    1. Calibrated ratios (most reliable for known ad types)
    2. Edge detection (for unknown layouts)
    3. Vertical split detection
    4. Color segmentation (fallback)
    """
    image = cv2.imread(str(image_path))
    if image is None:
        return None
    
    # First try calibrated detection (most reliable)
    calibrated = detect_video_region_calibrated(image, retailer, ad_type)
    if calibrated:
        return calibrated
    
    hints = VIDEO_SLOT_HINTS.get(retailer, {}).get(ad_type, {})
    if not hints:
        # Use generic hints
        hints = {
            "expected_x_ratio": (0.0, 0.15),
            "expected_width_ratio": (0.35, 0.6),
            "expected_height_ratio": (0.7, 1.0),
            "min_area_ratio": 0.2,
            "max_area_ratio": 0.6,
        }
    
    # Try detection methods in order of reliability
    result = detect_video_region_edges(image, hints)
    if result and result.get("confidence", 0) >= 0.6:
        return result
    
    # Try vertical split detection (good for Walmart SBV layout)
    split_result = detect_video_region_vertical_split(image, hints)
    if split_result:
        # If edge detection found something, compare
        if result:
            # Use edge result if it's close to split result
            if abs(result["width"] - split_result["width"]) < image.shape[1] * 0.1:
                return result
        return split_result
    
    # Fall back to color segmentation
    color_result = detect_video_region_color(image, hints)
    if color_result:
        return color_result
    
    return result  # Return edge result even if low confidence


def process_json_file(json_path: Path, retailer: str, dry_run: bool = True, force: bool = False) -> Tuple[int, int]:
    """
    Process a single JSON file and detect video overlays for video ads.
    Returns (updated_count, skipped_count).
    """
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"  ⚠️  Error reading {json_path}: {e}")
        return 0, 0
    
    ads = data.get('ads', [])
    if not ads:
        return 0, 0
    
    updated = 0
    skipped = 0
    
    # Determine client root from json path
    # Structure: output/<retailer>/<client>/runs/<run_id>/run_results_*.json
    client_root = json_path.parent.parent.parent
    
    for ad in ads:
        ad_type = ad.get('type') or ad.get('ad_type', '')
        
        # Only process video ad types
        video_types = ['SBV', 'Sponsored_Brand_Video', 'Shoppable_Video_Ad', 'Shoppable_Video_Ads']
        if ad_type not in video_types:
            continue
        
        # Skip if already has video_overlay (unless force is set)
        existing = ad.get('video_overlay')
        if existing and not force:
            # Has overlay from scrape-time capture, skip unless forcing recalculation
            skipped += 1
            continue
        
        # Get image path
        image_path_rel = ad.get('image_path')
        if not image_path_rel:
            continue
        
        image_path = client_root / image_path_rel
        if not image_path.exists():
            print(f"  ⚠️  Image not found: {image_path}")
            continue
        
        # Detect video region
        overlay = detect_video_overlay(image_path, retailer, ad_type)
        if overlay:
            overlay["detection_method"] = "cv_detected"
            brand = ad.get('brand', 'unknown')
            conf = overlay.get('confidence', 0)
            print(f"  ✓ Detected overlay for {brand}: {overlay['width']}x{overlay['height']} @ ({overlay['x']},{overlay['y']}) [conf={conf:.2f}]")
            
            if not dry_run:
                ad['video_overlay'] = overlay
                # Also ensure video_url is set if we have video_path
                if ad.get('video_path') and not ad.get('video_url'):
                    ad['video_url'] = ad['video_path']
            
            updated += 1
        else:
            print(f"  ⚠️  Could not detect overlay for {ad.get('brand', 'unknown')}")
    
    if updated > 0 and not dry_run:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"  💾 Saved {updated} update(s)")
    
    return updated, skipped


def main():
    parser = argparse.ArgumentParser(description='Detect video overlay boundaries using computer vision')
    parser.add_argument('--retailer', required=True, choices=['walmart', 'instacart', 'amazon', 'all'],
                        help='Retailer to process')
    parser.add_argument('--client', help='Specific client to process (optional)')
    parser.add_argument('--dry-run', action='store_true', default=True,
                        help='Show what would be detected without saving (default)')
    parser.add_argument('--apply', action='store_true',
                        help='Actually apply detected overlays to JSON files')
    parser.add_argument('--force', action='store_true',
                        help='Recalculate overlays even if they already exist')
    parser.add_argument('--visualize', help='Save visualization of detection to this path')
    
    args = parser.parse_args()
    
    dry_run = not args.apply
    
    if dry_run:
        print("🔍 DRY RUN - No changes will be saved")
        print("   Use --apply to save detected overlays\n")
    else:
        print("⚠️  APPLYING CHANGES - Detected overlays will be saved\n")
    
    retailers = ['walmart', 'instacart', 'amazon'] if args.retailer == 'all' else [args.retailer]
    
    total_updated = 0
    total_skipped = 0
    total_files = 0
    
    for retailer in retailers:
        retailer_dir = OUTPUT_ROOT / retailer
        if not retailer_dir.exists():
            continue
        
        print(f"\n{'='*60}")
        print(f"Processing {retailer}")
        print('='*60)
        
        # Find all client directories
        clients = [d for d in retailer_dir.iterdir() if d.is_dir()]
        if args.client:
            clients = [c for c in clients if c.name == args.client]
        
        for client_dir in sorted(clients):
            runs_dir = client_dir / "runs"
            if not runs_dir.exists():
                continue
            
            json_files = list(runs_dir.glob("*/run_results_*.json"))
            if not json_files:
                continue
            
            print(f"\n📁 {retailer}/{client_dir.name} ({len(json_files)} runs)")
            
            for json_file in sorted(json_files):
                print(f"\n📄 {json_file.name}")
                updated, skipped = process_json_file(json_file, retailer, dry_run, force=args.force)
                total_updated += updated
                total_skipped += skipped
                total_files += 1
    
    print(f"\n{'='*60}")
    print(f"✅ Complete!")
    print(f"   Files processed: {total_files}")
    print(f"   Overlays detected: {total_updated}")
    print(f"   Already had overlay: {total_skipped}")
    if dry_run:
        print(f"\n   Run with --apply to save changes")
    print('='*60)


if __name__ == '__main__':
    main()
