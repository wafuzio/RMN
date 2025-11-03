#!/usr/bin/env python3
"""
Kroger Image-to-JSON Reconciliation Tool

Scans Kroger client directories for saved images and updates run JSON files
to include image_path fields, enabling the API to serve images correctly.

Similar to reconcile_walmart_images_to_json.py but adapted for Kroger's
flat directory structure (TOA/, Skyscraper/, Carousel/ folders).

Usage:
    python3 tools/reconcile_kroger_images_to_json.py
    python3 tools/reconcile_kroger_images_to_json.py --client barilla
    python3 tools/reconcile_kroger_images_to_json.py --dry-run
"""

import os
import sys
import json
import re
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

OUTPUT_ROOT = project_root / "output" / "kroger"

# Kroger folder structure (flat, not nested like Walmart)
KROGER_FOLDERS = ["TOA", "Skyscraper", "Carousel", "Main"]

def parse_filename(filename: str) -> Optional[Dict[str, str]]:
    """
    Parse Kroger filename to extract metadata.
    
    Format: kroger__advertiser__adtype__client__searchterm__D2025-10-29_T17-07.00_1.png
    
    Returns dict with: retailer, advertiser, ad_type, client, search_term, timestamp, index
    """
    # Remove extension
    base = filename.rsplit('.', 1)[0]
    
    # Split by double underscore
    parts = base.split('__')
    
    if len(parts) < 6:
        return None
    
    # Extract timestamp and index from last part (D2025-10-29_T17-07.00_1)
    last_part = parts[-1]
    ts_match = re.search(r'D(\d{4}-\d{2}-\d{2})_T(\d{2})-(\d{2})\.(\d{2})_(\d+)', last_part)
    
    if not ts_match:
        return None
    
    date = ts_match.group(1)
    hour = ts_match.group(2)
    minute = ts_match.group(3)
    second = ts_match.group(4)
    index = ts_match.group(5)
    
    # Reconstruct timestamp as YYYY-MM-DD_HH-MM-SS
    timestamp = f"{date}_{hour}-{minute}-{second}"
    
    return {
        "retailer": parts[0],
        "advertiser": parts[1],
        "ad_type": parts[2],
        "client": parts[3],
        "search_term": parts[4],
        "timestamp": timestamp,
        "index": int(index),
        "filename": filename
    }

def find_matching_json(client_root: Path, timestamp: str, search_term: str) -> Optional[Path]:
    """
    Find the JSON file that matches the given timestamp and search term.
    
    Kroger JSON files are named: run_results_{search_term}_{timestamp}.json
    or run_results_{run_id}.json (canonical format)
    """
    runs_dir = client_root / "runs"
    if not runs_dir.exists():
        return None
    
    # Try canonical format first (run_id = YYYYMMDDHHMMSS)
    run_id = timestamp.replace("-", "").replace("_", "")
    canonical_path = runs_dir / f"run_results_{run_id}.json"
    if canonical_path.exists():
        return canonical_path
    
    # Try legacy format with search term
    clean_term = search_term.replace(" ", "_").lower()
    legacy_path = runs_dir / f"run_results_{clean_term}_{timestamp}.json"
    if legacy_path.exists():
        return legacy_path
    
    # Fuzzy match by timestamp (in case search term differs slightly)
    for json_file in runs_dir.glob("run_results_*.json"):
        if timestamp in json_file.name:
            return json_file
    
    return None

def update_ad_with_image_path(ad: dict, image_info: dict, folder: str) -> bool:
    """
    Update an ad object with image_path if it matches the image metadata.
    
    Returns True if updated, False otherwise.
    """
    # Match by ad type
    ad_type = ad.get("type", "").lower()
    img_type = image_info["ad_type"].lower()
    
    # Normalize ad type names
    type_map = {
        "toa": "toa",
        "top_of_aisle": "toa",
        "skyscraper": "skyscraper",
        "curatedcarousel": "carousel",
        "carousel": "carousel"
    }
    
    ad_type_norm = type_map.get(ad_type, ad_type)
    img_type_norm = type_map.get(img_type, img_type)
    
    if ad_type_norm != img_type_norm:
        return False
    
    # Match by advertiser (if available)
    ad_advertisers = ad.get("advertisers", [])
    img_advertiser = image_info["advertiser"].replace("_", " ").title()
    
    # Check if any advertiser matches (case-insensitive)
    advertiser_match = any(
        img_advertiser.lower() in adv.lower() or adv.lower() in img_advertiser.lower()
        for adv in ad_advertisers
    )
    
    # If advertisers don't match and ad has advertisers, skip
    if ad_advertisers and not advertiser_match:
        return False
    
    # Set image_path
    rel_path = f"{folder}/{image_info['filename']}"
    
    # Set type-specific path
    if ad_type_norm == "toa":
        ad["toa_image_path"] = rel_path
    elif ad_type_norm == "skyscraper":
        ad["skyscraper_image_path"] = rel_path
    elif ad_type_norm == "carousel":
        ad["carousel_image_path"] = rel_path
    
    # Set canonical image_path
    ad["image_path"] = rel_path
    
    return True

def reconcile_client(client_name: str, dry_run: bool = False) -> Dict[str, int]:
    """
    Reconcile images to JSON for a single Kroger client.
    
    Returns stats: {images_found, jsons_updated, ads_updated}
    """
    client_root = OUTPUT_ROOT / client_name
    
    if not client_root.exists():
        print(f"❌ Client directory not found: {client_root}")
        return {"images_found": 0, "jsons_updated": 0, "ads_updated": 0}
    
    stats = {
        "images_found": 0,
        "jsons_updated": 0,
        "ads_updated": 0
    }
    
    # Group images by timestamp and search term
    images_by_run: Dict[Tuple[str, str], List[Tuple[str, dict]]] = {}
    
    # Scan all Kroger folders for images
    for folder in KROGER_FOLDERS:
        folder_path = client_root / folder
        if not folder_path.exists():
            continue
        
        for img_file in folder_path.glob("*.png"):
            stats["images_found"] += 1
            
            # Parse filename
            img_info = parse_filename(img_file.name)
            if not img_info:
                print(f"⚠️  Could not parse filename: {img_file.name}")
                continue
            
            # Group by (timestamp, search_term)
            key = (img_info["timestamp"], img_info["search_term"])
            if key not in images_by_run:
                images_by_run[key] = []
            images_by_run[key].append((folder, img_info))
    
    print(f"\n📊 Found {stats['images_found']} images across {len(images_by_run)} runs")
    
    # Process each run
    for (timestamp, search_term), images in images_by_run.items():
        # Find matching JSON
        json_path = find_matching_json(client_root, timestamp, search_term)
        
        if not json_path:
            print(f"⚠️  No JSON found for {search_term} @ {timestamp} ({len(images)} images)")
            continue
        
        # Load JSON
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"❌ Error loading {json_path.name}: {e}")
            continue
        
        # Get ads array
        ads = data.get("ads", [])
        if not ads:
            print(f"⚠️  No ads in {json_path.name}")
            continue
        
        # Try to match images to ads
        updated_count = 0
        for folder, img_info in images:
            # Find matching ad by type and advertiser
            for ad in ads:
                if update_ad_with_image_path(ad, img_info, folder):
                    updated_count += 1
                    break
        
        if updated_count > 0:
            stats["ads_updated"] += updated_count
            stats["jsons_updated"] += 1
            
            if not dry_run:
                # Save updated JSON
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print(f"✅ Updated {json_path.name}: {updated_count} ads linked to images")
            else:
                print(f"🔍 [DRY RUN] Would update {json_path.name}: {updated_count} ads")
    
    return stats

def main():
    parser = argparse.ArgumentParser(description="Reconcile Kroger images to JSON files")
    parser.add_argument("--client", help="Specific client to reconcile (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    args = parser.parse_args()
    
    print("=" * 60)
    print("Kroger Image-to-JSON Reconciliation Tool")
    print("=" * 60)
    
    if args.dry_run:
        print("🔍 DRY RUN MODE - No files will be modified\n")
    
    # Get list of clients
    if args.client:
        clients = [args.client]
    else:
        clients = [d.name for d in OUTPUT_ROOT.iterdir() if d.is_dir()]
    
    print(f"📁 Processing {len(clients)} client(s)\n")
    
    # Process each client
    total_stats = {"images_found": 0, "jsons_updated": 0, "ads_updated": 0}
    
    for client in sorted(clients):
        print(f"\n{'='*60}")
        print(f"Client: {client}")
        print(f"{'='*60}")
        
        stats = reconcile_client(client, dry_run=args.dry_run)
        
        for key in total_stats:
            total_stats[key] += stats[key]
        
        print(f"\n📊 Client Stats:")
        print(f"   Images found: {stats['images_found']}")
        print(f"   JSONs updated: {stats['jsons_updated']}")
        print(f"   Ads updated: {stats['ads_updated']}")
    
    # Print summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Total images found: {total_stats['images_found']}")
    print(f"Total JSONs updated: {total_stats['jsons_updated']}")
    print(f"Total ads updated: {total_stats['ads_updated']}")
    
    if args.dry_run:
        print(f"\n🔍 DRY RUN - Run without --dry-run to apply changes")
    else:
        print(f"\n✅ Reconciliation complete!")

if __name__ == "__main__":
    main()
