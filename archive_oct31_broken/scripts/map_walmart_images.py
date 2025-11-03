#!/usr/bin/env python3
"""
Map Walmart images to JSON ads by adding screenshot_path fields.

This script:
1. Finds all Walmart run_results JSON files
2. Looks for corresponding image files in SBA, SBV, Tile_Takeover folders
3. Matches images to ads by timestamp, ad type, and advertiser
4. Updates JSON with screenshot_path fields
"""

import os
import json
import glob
import re
from datetime import datetime

def extract_timestamp_from_filename(filename):
    """
    Extract timestamp from filename like:
    walmart__advertiser__sba__client__keyword__D2025-10-22_T13-13.59_1.png
    Returns: 2025-10-22_13-13-59 (normalized format)
    """
    match = re.search(r'D(\d{4}-\d{2}-\d{2})_T(\d{2}-\d{2})\.(\d{2})', filename)
    if match:
        date = match.group(1)
        time = match.group(2).replace('-', ':')
        sec = match.group(3)
        return f"{date}_{time}:{sec}"
    return None

def extract_advertiser_from_filename(filename):
    """
    Extract advertiser from filename:
    walmart__advertiser__sba__client__keyword__D2025-10-22_T13-13.59_1.png
    Returns: advertiser name
    """
    parts = filename.split('__')
    if len(parts) >= 2:
        return parts[1].replace('_', ' ').title()
    return None

def normalize_advertiser(name):
    """Normalize advertiser name for matching"""
    if not name:
        return "unknown"
    return name.lower().strip().replace('_', ' ')

def find_matching_image(ad, images_by_type, json_timestamp, json_keyword=None):
    """
    Find the image file that matches this ad.
    
    Match criteria:
    1. Ad type matches
    2. Keyword matches (if provided)
    3. Advertiser matches (if available)
    4. Position matches
    """
    ad_type = ad.get('type', '').lower()
    ad_advertiser = normalize_advertiser(ad.get('advertiser', 'unknown'))
    ad_pos = ad.get('pos', 1)
    
    # Map ad types to folder names
    type_map = {
        'sba': 'SBA',
        'sbv': 'SBV',
        'tile_takeover': 'Tile_Takeover',
        'top_banner': 'Top_Banner'
    }
    
    folder = type_map.get(ad_type)
    if not folder or folder not in images_by_type:
        return None
    
    candidates = images_by_type[folder]
    
    # Filter by keyword if provided
    if json_keyword:
        keyword_filtered = []
        for img_path, img_ts, img_adv in candidates:
            img_keyword = extract_keyword_from_filename(os.path.basename(img_path))
            if img_keyword and img_keyword.lower().replace(' ', '_') == json_keyword:
                keyword_filtered.append((img_path, img_ts, img_adv))
        if keyword_filtered:
            candidates = keyword_filtered
    
    # Try to match by advertiser first (skip if advertiser is 'unknown' in filename)
    for img_path, img_ts, img_adv in candidates:
        if img_adv and normalize_advertiser(img_adv) != 'unknown':
            if normalize_advertiser(img_adv) == ad_advertiser:
                return img_path
    
    # Fallback: Match by position (index in filename _N.png)
    # Extract position from filename: ..._1.png, ..._2.png
    for img_path, img_ts, img_adv in candidates:
        match = re.search(r'_(\d+)\.(png|jpg|jpeg|mp4)$', img_path)
        if match:
            img_pos = int(match.group(1))
            if img_pos == ad_pos:
                return img_path
    
    # Final fallback: return first image of this type
    if len(candidates) >= 1:
        return candidates[0][0]
    
    return None

def extract_keyword_from_filename(filename):
    """Extract keyword from filename like walmart__adv__type__client__keyword__timestamp"""
    parts = filename.split('__')
    if len(parts) >= 5:
        # keyword is typically the 5th part (0-indexed: 4)
        keyword = parts[4].replace('_', ' ')
        return keyword
    return None

def process_json_file(json_path, client_root):
    """
    Process a single JSON file and add screenshot_path fields.
    
    Args:
        json_path: Path to run_results JSON file
        client_root: Root directory for client (e.g., output/walmart/magic_spoon)
    
    Returns:
        (updated_count, total_ads)
    """
    print(f"\n📄 Processing: {os.path.basename(json_path)}")
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"   ❌ Failed to read JSON: {e}")
        return 0, 0
    
    # Get timestamp and keyword from JSON
    json_timestamp = data.get('timestamp', '')
    json_keyword = (data.get('keyword') or data.get('search_term', '')).lower().replace(' ', '_')
    
    # Find all image files in client root
    images_by_type = {}
    for folder in ['SBA', 'SBV', 'Tile_Takeover', 'Top_Banner']:
        folder_path = os.path.join(client_root, folder)
        if os.path.isdir(folder_path):
            images = []
            for img_file in os.listdir(folder_path):
                if img_file.endswith(('.png', '.jpg', '.jpeg')):
                    img_path = os.path.join(folder, img_file)  # Relative path
                    img_ts = extract_timestamp_from_filename(img_file)
                    img_adv = extract_advertiser_from_filename(img_file)
                    images.append((img_path, img_ts, img_adv))
            if images:
                images_by_type[folder] = images
    
    print(f"   Found images: {sum(len(imgs) for imgs in images_by_type.values())} across {len(images_by_type)} folders")
    
    # Process ads in results
    updated_count = 0
    total_ads = 0
    
    if 'results' in data:
        for result in data.get('results', []):
            for ad in result.get('ads', []):
                total_ads += 1
                
                # Skip if already has screenshot_path
                if ad.get('screenshot_path'):
                    continue
                
                # Find matching image
                img_path = find_matching_image(ad, images_by_type, json_timestamp, json_keyword)
                if img_path:
                    ad['screenshot_path'] = img_path
                    updated_count += 1
                    print(f"   ✅ Mapped {ad.get('type', 'unknown')} ad ({ad.get('advertiser', 'unknown')}) -> {img_path}")
    
    # Save updated JSON
    if updated_count > 0:
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"   💾 Updated {updated_count}/{total_ads} ads")
        except Exception as e:
            print(f"   ❌ Failed to write JSON: {e}")
            return 0, total_ads
    else:
        print(f"   ℹ️  No updates needed ({total_ads} ads already mapped)")
    
    return updated_count, total_ads

def main():
    """Process all Walmart JSON files"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Map Walmart images to JSON ads")
    parser.add_argument("--client", help="Specific client to process (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without modifying files")
    args = parser.parse_args()
    
    output_root = "output/walmart"
    
    if not os.path.isdir(output_root):
        print(f"❌ Walmart output directory not found: {output_root}")
        return
    
    # Find all client directories
    clients = []
    if args.client:
        client_dir = os.path.join(output_root, args.client)
        if os.path.isdir(client_dir):
            clients.append((args.client, client_dir))
        else:
            print(f"❌ Client not found: {args.client}")
            return
    else:
        for item in os.listdir(output_root):
            item_path = os.path.join(output_root, item)
            if os.path.isdir(item_path):
                clients.append((item, item_path))
    
    print(f"🔍 Found {len(clients)} Walmart client(s)")
    
    total_updated = 0
    total_ads = 0
    
    for client_name, client_root in clients:
        print(f"\n{'='*60}")
        print(f"📁 Client: {client_name}")
        print(f"{'='*60}")
        
        # Find all JSON files in runs directory and timestamped subdirectories
        json_files = []
        
        # Check runs directory
        runs_dir = os.path.join(client_root, "runs")
        if os.path.isdir(runs_dir):
            # Flat files in runs/
            json_files.extend(glob.glob(os.path.join(runs_dir, "run_results_*.json")))
            
            # Files in timestamped subdirectories
            for subdir in os.listdir(runs_dir):
                subdir_path = os.path.join(runs_dir, subdir)
                if os.path.isdir(subdir_path):
                    json_files.extend(glob.glob(os.path.join(subdir_path, "run_results_*.json")))
        
        # Also check timestamped directories at client root (old structure)
        for item in os.listdir(client_root):
            if re.match(r'^\d{14}$', item):  # YYYYMMDDHHMMSS
                item_path = os.path.join(client_root, item)
                if os.path.isdir(item_path):
                    json_files.extend(glob.glob(os.path.join(item_path, "run_results_*.json")))
        
        print(f"Found {len(json_files)} JSON file(s)")
        
        if args.dry_run:
            print("🔸 DRY RUN MODE - No files will be modified")
            for json_file in json_files:
                print(f"   Would process: {os.path.basename(json_file)}")
            continue
        
        for json_file in sorted(json_files):
            updated, ads = process_json_file(json_file, client_root)
            total_updated += updated
            total_ads += ads
    
    print(f"\n{'='*60}")
    print(f"📊 Summary:")
    print(f"   Total ads processed: {total_ads}")
    print(f"   Screenshot paths added: {total_updated}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
