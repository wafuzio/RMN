#!/usr/bin/env python3
"""
Backfill Gallery Card dimensions from actual image files.

Scans all Gallery_Cards images, reads their dimensions using PIL,
and updates the corresponding run_results JSON files.
"""

import json
import sys
from pathlib import Path
from PIL import Image

# Project root
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "output"


def find_gallery_card_images():
    """Find all Gallery_Cards image files."""
    images = []
    for retailer_dir in OUTPUT_DIR.iterdir():
        if not retailer_dir.is_dir():
            continue
        for client_dir in retailer_dir.iterdir():
            if not client_dir.is_dir():
                continue
            gallery_dir = client_dir / "Gallery_Cards"
            if gallery_dir.exists():
                for img_file in gallery_dir.glob("*.png"):
                    images.append(img_file)
                for img_file in gallery_dir.glob("*.jpg"):
                    images.append(img_file)
    return images


def get_image_dimensions(img_path: Path) -> dict:
    """Get width and height of an image."""
    try:
        with Image.open(img_path) as img:
            return {"width": img.width, "height": img.height}
    except Exception as e:
        print(f"  ⚠️  Could not read {img_path.name}: {e}")
        return None


def find_run_results_files():
    """Find all run_results JSON files."""
    results = []
    for retailer_dir in OUTPUT_DIR.iterdir():
        if not retailer_dir.is_dir():
            continue
        for client_dir in retailer_dir.iterdir():
            if not client_dir.is_dir():
                continue
            # Check in runs/ subdirectory (flat structure)
            runs_dir = client_dir / "runs"
            if runs_dir.exists():
                for item in runs_dir.iterdir():
                    if item.is_file() and item.name.startswith("run_results_") and item.name.endswith(".json"):
                        results.append(item)
                    elif item.is_dir():
                        # Check in runs/<run_id>/ subdirectory (nested structure)
                        for json_file in item.glob("run_results_*.json"):
                            results.append(json_file)
            # Also check directly in client dir (legacy)
            for json_file in client_dir.glob("run_results_*.json"):
                results.append(json_file)
    return results


def backfill_dimensions():
    """Main backfill logic."""
    print("🔍 Scanning for Gallery Card images...")
    
    # Build a map of image filename -> dimensions
    images = find_gallery_card_images()
    print(f"   Found {len(images)} Gallery Card images")
    
    image_dims = {}
    for img_path in images:
        dims = get_image_dimensions(img_path)
        if dims:
            image_dims[img_path.name] = dims
    
    print(f"   Read dimensions for {len(image_dims)} images")
    
    # Find all run_results files
    print("\n📁 Scanning run_results files...")
    run_files = find_run_results_files()
    print(f"   Found {len(run_files)} run_results files")
    
    # Update each run_results file
    updated_files = 0
    updated_ads = 0
    
    for json_path in run_files:
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"  ⚠️  Could not read {json_path.name}: {e}")
            continue
        
        modified = False
        ads = data.get("ads", [])
        
        for ad in ads:
            # Check both "type" and "ad_type" fields
            ad_type = ad.get("type") or ad.get("ad_type") or ""
            if ad_type != "Gallery_Cards":
                continue
            
            # Skip if already has dimensions
            if ad.get("dimensions") and ad["dimensions"].get("width"):
                continue
            
            # Try to find matching image - check both image_path and image_url
            img_path = ad.get("image_path") or ad.get("image_url") or ""
            if not img_path:
                continue
            
            # Extract filename from URL/path
            img_name = Path(img_path).name
            
            if img_name in image_dims:
                ad["dimensions"] = image_dims[img_name]
                # Also set card_format based on aspect ratio
                dims = image_dims[img_name]
                aspect = dims["width"] / dims["height"] if dims["height"] > 0 else 1
                ad["card_format"] = "banner" if aspect > 1.5 else "tile"
                modified = True
                updated_ads += 1
        
        if modified:
            # Write back
            try:
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                updated_files += 1
                print(f"  ✅ Updated {json_path.name}")
            except Exception as e:
                print(f"  ❌ Could not write {json_path.name}: {e}")
    
    print(f"\n✨ Done! Updated {updated_ads} ads across {updated_files} files.")


if __name__ == "__main__":
    backfill_dimensions()
