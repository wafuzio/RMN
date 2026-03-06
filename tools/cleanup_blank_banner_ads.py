#!/usr/bin/env python3
"""
Clean up blank Target banner ads from JSON files and delete blank image files.

Identifies ListingPageBannerAd entries where the screenshot is >95% white pixels
and removes them from the JSON data.

Usage:
    python3 tools/cleanup_blank_banner_ads.py --preview
    python3 tools/cleanup_blank_banner_ads.py --apply
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def is_image_blank(image_path: Path, threshold: int = 240) -> Tuple[bool, float]:
    """
    Check if an image is blank (>95% white pixels).
    
    Returns (is_blank, white_percentage)
    """
    try:
        from PIL import Image
        
        with Image.open(image_path) as img:
            pixels = img.load()
            width, height = img.size
            
            white_count = 0
            total = 0
            
            # Sample pixels across the image
            for x in range(0, width, max(1, width//20)):
                for y in range(0, height, max(1, height//20)):
                    r, g, b = pixels[x, y]
                    if r > threshold and g > threshold and b > threshold:
                        white_count += 1
                    total += 1
            
            white_pct = 100 * white_count / total if total > 0 else 100
            is_blank = white_pct > 95
            
            return is_blank, white_pct
    except Exception as e:
        return False, 0.0


def cleanup_blank_ads(run_data: dict, output_root: Path, delete_images: bool = False) -> Tuple[int, List[str]]:
    """Remove blank banner ads from run data."""
    removed_count = 0
    changes = []
    
    retailer = run_data.get("retailer", "")
    client = run_data.get("client", "")
    
    if retailer != "target":
        return 0, []
    
    ads = run_data.get("ads", [])
    filtered_ads = []
    
    for idx, ad in enumerate(ads):
        ad_type = ad.get("type", "")
        
        # Only check ListingPageBannerAd
        if ad_type != "ListingPageBannerAd":
            filtered_ads.append(ad)
            continue
        
        image_path = ad.get("image_path", "")
        if not image_path:
            filtered_ads.append(ad)
            continue
        
        # Check if image is blank
        full_path = output_root / retailer / client / image_path
        
        if not full_path.exists():
            changes.append(f"  Ad {idx+1}: Image not found: {image_path}")
            filtered_ads.append(ad)
            continue
        
        is_blank, white_pct = is_image_blank(full_path)
        
        if is_blank:
            removed_count += 1
            brand = ad.get("brand", "Unknown")
            changes.append(f"  Ad {idx+1}: REMOVED {brand} banner ({white_pct:.0f}% white) - {full_path.name}")
            
            # Delete the blank image file if requested
            if delete_images:
                try:
                    full_path.unlink()
                    changes.append(f"           Deleted image file: {full_path.name}")
                except Exception as e:
                    changes.append(f"           Failed to delete: {e}")
        else:
            filtered_ads.append(ad)
    
    if removed_count > 0:
        run_data["ads"] = filtered_ads
    
    return removed_count, changes


def process_run_file(json_path: Path, output_root: Path, apply: bool = False, delete_images: bool = False) -> Dict:
    """Process a single run JSON file."""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            run_data = json.load(f)
    except Exception as e:
        return {"error": str(e), "file": str(json_path)}
    
    retailer = run_data.get("retailer", "")
    run_id = run_data.get("run_id", "")
    
    if retailer != "target":
        return {"skipped": True}
    
    results = {
        "file": str(json_path.relative_to(output_root)),
        "retailer": retailer,
        "run_id": run_id,
        "changes": [],
        "total_removed": 0
    }
    
    count, changes = cleanup_blank_ads(run_data, output_root, delete_images=delete_images and apply)
    results["blank_ads_removed"] = count
    results["changes"].extend(changes)
    results["total_removed"] = count
    
    # Write back if applying changes and ads were removed
    if apply and results["total_removed"] > 0:
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(run_data, f, indent=2, ensure_ascii=False)
            results["applied"] = True
        except Exception as e:
            results["write_error"] = str(e)
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Clean up blank Target banner ads from JSON files")
    parser.add_argument("--client", help="Specific client to process")
    parser.add_argument("--preview", action="store_true", help="Preview changes without applying")
    parser.add_argument("--apply", action="store_true", help="Apply changes to JSON files")
    parser.add_argument("--delete-images", action="store_true", help="Also delete blank image files")
    parser.add_argument("--limit", type=int, help="Limit number of files to process")
    
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
    
    print(f"{'PREVIEW' if args.preview else 'APPLYING'} blank banner ad cleanup")
    print(f"Output root: {output_root}")
    if args.delete_images and args.apply:
        print("⚠️  Will also DELETE blank image files")
    print()
    
    retailer_dir = output_root / "target"
    if not retailer_dir.exists():
        print("ERROR: Target directory not found")
        sys.exit(1)
    
    # Find all run JSON files
    json_files = []
    for client_dir in retailer_dir.iterdir():
        if not client_dir.is_dir():
            continue
        if args.client and client_dir.name != args.client:
            continue
        
        runs_dir = client_dir / "runs"
        if runs_dir.exists():
            for json_file in runs_dir.glob("run_results_*.json"):
                json_files.append(json_file)
    
    if args.limit:
        json_files = json_files[:args.limit]
    
    print(f"Processing {len(json_files)} Target run files")
    print(f"{'='*60}\n")
    
    total_files = 0
    total_removed = 0
    total_errors = 0
    
    for json_path in json_files:
        total_files += 1
        result = process_run_file(json_path, output_root, apply=args.apply, delete_images=args.delete_images)
        
        if result.get("error"):
            total_errors += 1
            print(f"❌ ERROR: {result['file']}")
            print(f"   {result['error']}\n")
            continue
        
        if result.get("skipped"):
            continue
        
        if result.get("total_removed", 0) > 0:
            total_removed += result.get("total_removed", 0)
            print(f"📝 {result['file']}")
            for change in result["changes"]:
                print(change)
            if args.apply and result.get("applied"):
                print("  ✅ Changes applied")
            print()
    
    print(f"{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"Files processed: {total_files}")
    print(f"Blank ads removed: {total_removed}")
    print(f"Errors: {total_errors}")
    print(f"Mode: {'PREVIEW (no changes written)' if args.preview else 'APPLIED (changes written)'}")


if __name__ == "__main__":
    main()
