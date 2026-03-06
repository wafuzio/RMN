#!/usr/bin/env python3
"""
Backfill script to fix GUI display issues in historical JSON data.

Fixes applied:
1. Walmart house ads: Set brand="Walmart" for Gallery Cards with walmart+ messaging
2. Amazon Sponsored Display: Add dimensions and card_format for portrait ads
3. Amazon house ad carousels: Remove "Trending now", "Picks from Amazon Influencers", etc.
4. Instacart video ads: Flag missing video_path (can't fix without MP4 files)

Usage:
    python3 tools/backfill_gui_fixes.py --retailer walmart --preview
    python3 tools/backfill_gui_fixes.py --retailer amazon --apply
    python3 tools/backfill_gui_fixes.py --all --apply
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

CAROUSEL_BLACKLIST = [
    "Brands related to your search",
    "Shoppers also explored",
    "Trending now",
    "Popular products in this category",
    "Customers who viewed this item also viewed",
    "Customers mention",
    "Picks from Amazon Influencers",
    "From Amazon influencer storefronts"
]


def fix_walmart_house_ads(run_data: dict) -> Tuple[int, List[str]]:
    """Fix Walmart house ads showing as Unknown."""
    fixed_count = 0
    changes = []
    
    ads = run_data.get("ads", [])
    for idx, ad in enumerate(ads):
        ad_type = ad.get("type", "")
        brand = ad.get("brand", "")
        advertisers = ad.get("advertisers", [])
        
        # Only fix Gallery Cards with Unknown/empty brand
        if "gallery" not in ad_type.lower():
            continue
        if brand and brand.lower() not in ("unknown", ""):
            continue
        
        # Check for walmart+ indicators
        message = ad.get("message") or ad.get("title") or ad.get("description") or ""
        msg_lower = message.lower()
        
        if "walmart+" in msg_lower or "walmart plus" in msg_lower:
            ad["brand"] = "Walmart"
            if not advertisers or advertisers == ["Unknown"]:
                ad["advertisers"] = ["Walmart"]
            fixed_count += 1
            changes.append(f"  Ad {idx+1}: Set brand=Walmart (Gallery Card with walmart+ messaging)")
    
    return fixed_count, changes


def fix_amazon_sponsored_display(run_data: dict, output_root: Path) -> Tuple[int, List[str]]:
    """Add dimensions and card_format to Amazon Sponsored Display ads."""
    fixed_count = 0
    changes = []
    
    ads = run_data.get("ads", [])
    retailer = run_data.get("retailer", "")
    client = run_data.get("client", "")
    
    if retailer != "amazon":
        return 0, []
    
    for idx, ad in enumerate(ads):
        ad_type = ad.get("type", "")
        
        if ad_type != "Sponsored_Display":
            continue
        
        # Skip if already has dimensions and card_format
        if ad.get("dimensions") and ad.get("card_format"):
            continue
        
        # Try to probe image dimensions
        image_path = ad.get("image_path", "")
        if not image_path:
            continue
        
        # Construct full path
        full_path = output_root / retailer / client / image_path
        
        if not full_path.exists():
            continue
        
        try:
            from PIL import Image
            with Image.open(full_path) as img:
                width, height = img.size
                
                # Add dimensions
                ad["dimensions"] = {"width": width, "height": height}
                
                # Set card_format for portrait ads
                if height > width * 1.5:
                    ad["card_format"] = "tile"
                    fixed_count += 1
                    changes.append(f"  Ad {idx+1}: Added dimensions {width}x{height}, card_format=tile (portrait)")
                else:
                    fixed_count += 1
                    changes.append(f"  Ad {idx+1}: Added dimensions {width}x{height} (landscape)")
        except Exception as e:
            changes.append(f"  Ad {idx+1}: Failed to probe dimensions: {e}")
    
    return fixed_count, changes


def filter_amazon_house_carousels(run_data: dict) -> Tuple[int, List[str]]:
    """Remove Amazon house ad carousels from ads list."""
    removed_count = 0
    changes = []
    
    ads = run_data.get("ads", [])
    retailer = run_data.get("retailer", "")
    
    if retailer != "amazon":
        return 0, []
    
    filtered_ads = []
    for idx, ad in enumerate(ads):
        ad_type = ad.get("type", "")
        message = ad.get("message") or ad.get("title") or ""
        
        # Check if this is a blacklisted carousel
        if ad_type == "Sponsored_Carousel":
            is_blacklisted = False
            for phrase in CAROUSEL_BLACKLIST:
                if phrase.lower() in message.lower():
                    is_blacklisted = True
                    removed_count += 1
                    changes.append(f"  Ad {idx+1}: Removed carousel '{message[:50]}...' (blacklisted)")
                    break
            
            if not is_blacklisted:
                filtered_ads.append(ad)
        else:
            filtered_ads.append(ad)
    
    if removed_count > 0:
        run_data["ads"] = filtered_ads
    
    return removed_count, changes


def audit_instacart_videos(run_data: dict) -> Tuple[int, List[str]]:
    """Audit Instacart video ads for missing video_path."""
    issues = []
    issue_count = 0
    
    ads = run_data.get("ads", [])
    retailer = run_data.get("retailer", "")
    
    if retailer != "instacart":
        return 0, []
    
    for idx, ad in enumerate(ads):
        ad_type = ad.get("type", "")
        
        if "video" in ad_type.lower():
            has_overlay = bool(ad.get("video_overlay"))
            has_path = bool(ad.get("video_path"))
            
            if has_overlay and not has_path:
                issue_count += 1
                brand = ad.get("brand", "Unknown")
                issues.append(f"  Ad {idx+1}: {brand} - has video_overlay but missing video_path (MP4 not downloaded)")
    
    return issue_count, issues


def process_run_file(json_path: Path, output_root: Path, apply: bool = False) -> Dict:
    """Process a single run JSON file."""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            run_data = json.load(f)
    except Exception as e:
        return {"error": str(e), "file": str(json_path)}
    
    retailer = run_data.get("retailer", "")
    run_id = run_data.get("run_id", "")
    
    results = {
        "file": str(json_path.relative_to(output_root)),
        "retailer": retailer,
        "run_id": run_id,
        "changes": [],
        "total_fixes": 0
    }
    
    # Apply fixes based on retailer
    if retailer == "walmart":
        count, changes = fix_walmart_house_ads(run_data)
        results["walmart_house_ads"] = count
        results["changes"].extend(changes)
        results["total_fixes"] += count
    
    elif retailer == "amazon":
        # Fix Sponsored Display dimensions
        count1, changes1 = fix_amazon_sponsored_display(run_data, output_root)
        results["amazon_dimensions"] = count1
        results["changes"].extend(changes1)
        results["total_fixes"] += count1
        
        # Filter house ad carousels
        count2, changes2 = filter_amazon_house_carousels(run_data)
        results["amazon_carousels_removed"] = count2
        results["changes"].extend(changes2)
        results["total_fixes"] += count2
    
    elif retailer == "instacart":
        # Audit video ads
        count, issues = audit_instacart_videos(run_data)
        results["instacart_video_issues"] = count
        results["changes"].extend(issues)
    
    # Write back if applying changes and fixes were made
    if apply and results["total_fixes"] > 0:
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(run_data, f, indent=2, ensure_ascii=False)
            results["applied"] = True
        except Exception as e:
            results["write_error"] = str(e)
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Backfill GUI display fixes for historical JSON data")
    parser.add_argument("--retailer", choices=["walmart", "amazon", "instacart", "all"], 
                       help="Retailer to process (or 'all')")
    parser.add_argument("--client", help="Specific client to process")
    parser.add_argument("--preview", action="store_true", help="Preview changes without applying")
    parser.add_argument("--apply", action="store_true", help="Apply changes to JSON files")
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
    
    # Determine which retailers to process
    if args.retailer == "all":
        retailers = ["walmart", "amazon", "instacart"]
    elif args.retailer:
        retailers = [args.retailer]
    else:
        print("ERROR: Must specify --retailer")
        sys.exit(1)
    
    print(f"{'PREVIEW' if args.preview else 'APPLYING'} GUI fixes for: {', '.join(retailers)}")
    print(f"Output root: {output_root}")
    print()
    
    total_files = 0
    total_fixes = 0
    total_errors = 0
    
    for retailer in retailers:
        retailer_dir = output_root / retailer
        if not retailer_dir.exists():
            print(f"Skipping {retailer} (directory not found)")
            continue
        
        print(f"\n{'='*60}")
        print(f"Processing {retailer.upper()}")
        print(f"{'='*60}")
        
        # Find all run JSON files
        json_files = []
        for client_dir in retailer_dir.iterdir():
            if not client_dir.is_dir():
                continue
            if args.client and client_dir.name != args.client:
                continue
            
            runs_dir = client_dir / "runs"
            if runs_dir.exists():
                for run_dir in runs_dir.iterdir():
                    if run_dir.is_dir():
                        for json_file in run_dir.glob("run_results_*.json"):
                            json_files.append(json_file)
        
        if args.limit:
            json_files = json_files[:args.limit]
        
        print(f"Found {len(json_files)} run files")
        
        for json_path in json_files:
            total_files += 1
            result = process_run_file(json_path, output_root, apply=args.apply)
            
            if result.get("error"):
                total_errors += 1
                print(f"\n❌ ERROR: {result['file']}")
                print(f"   {result['error']}")
                continue
            
            if result.get("total_fixes", 0) > 0 or result.get("instacart_video_issues", 0) > 0:
                total_fixes += result.get("total_fixes", 0)
                print(f"\n📝 {result['file']}")
                for change in result["changes"]:
                    print(change)
                if args.apply and result.get("applied"):
                    print("  ✅ Changes applied")
    
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"Files processed: {total_files}")
    print(f"Total fixes: {total_fixes}")
    print(f"Errors: {total_errors}")
    print(f"Mode: {'PREVIEW (no changes written)' if args.preview else 'APPLIED (changes written)'}")


if __name__ == "__main__":
    main()
