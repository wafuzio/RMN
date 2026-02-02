#!/usr/bin/env python3
"""
Instacart Image Reconciliation Tool

Fixes broken image_path references in Instacart JSON files by matching orphaned
images to ads based on advertiser, ad type, and timestamp proximity.

Root Cause:
- Filename generation uses search_term parameter that sometimes differs from
  the keyword stored in JSON metadata
- This creates mismatches like: filename has "keto_pint_chips" but JSON has "keto_chips"
- Results in broken image_path references

Solution:
- Match images to ads by: advertiser + ad_type + timestamp (within 5 min)
- Ignore search_term portion of filename since it's unreliable
- Update JSON image_path to point to actual file on disk

Usage:
    python3 tools/reconcile_instacart_images.py [--client CLIENT] [--dry-run]
"""

import json
import glob
import os
import re
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

def parse_filename_timestamp(filename):
    """Extract timestamp from filename: D2025-12-05_T02-38.00"""
    match = re.search(r'D(\d{4}-\d{2}-\d{2})_T(\d{2})-(\d{2})\.(\d{2})', filename)
    if match:
        date_str, hour_str, min_str, sec_str = match.groups()
        dt_str = f'{date_str} {hour_str}:{min_str}:{sec_str}'
        try:
            return datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
        except:
            return None
    return None

def extract_filename_components(filename):
    """
    Extract components from Instacart filename.
    Format: instacart__[advertiser]__[ad_type]__[client]__[search]__D[date]_T[time]_[idx].png
    """
    parts = filename.split('__')
    if len(parts) < 6:
        return None
    
    return {
        'retailer': parts[0],
        'advertiser': parts[1],
        'ad_type': parts[2],
        'client': parts[3],
        'search_term': parts[4],
        'timestamp_part': parts[5] if len(parts) > 5 else None
    }

def normalize_advertiser(name):
    """Normalize advertiser name for matching"""
    if not name:
        return 'unknown'
    return name.lower().replace(' ', '_').replace("'", '').replace('&', 'and')

def build_image_index(client_dir):
    """Build index of all images in client directory"""
    image_index = defaultdict(list)
    
    # Scan all subdirectories for images (not just specific folder names)
    for folder_path in client_dir.iterdir():
        if not folder_path.is_dir():
            continue
        
        # Skip non-ad folders
        if folder_path.name in ['runs', 'locks', 'legacy_backup']:
            continue
        
        # Find all PNG files in this folder
        for img_file in folder_path.glob('*.png'):
            components = extract_filename_components(img_file.name)
            if not components:
                continue
            
            timestamp = parse_filename_timestamp(img_file.name)
            if not timestamp:
                continue
            
            # Index by advertiser + ad_type (normalized)
            # Normalize ad_type to handle variations
            ad_type_norm = components['ad_type'].lower().replace('_', '')
            key = (components['advertiser'], ad_type_norm)
            image_index[key].append({
                'path': img_file,
                'timestamp': timestamp,
                'components': components,
                'folder': folder_path.name
            })
    
    return image_index

def find_matching_image(image_index, advertiser, ad_type, target_timestamp, position=None):
    """Find image matching ad criteria"""
    advertiser_norm = normalize_advertiser(advertiser)
    
    # Normalize ad_type to match indexing (remove underscores, lowercase)
    ad_type_norm = ad_type.lower().replace('_', '').replace(' ', '')
    
    # Try to find candidates
    key = (advertiser_norm, ad_type_norm)
    candidates = image_index.get(key, [])
    
    if not candidates:
        return None
    
    # Parse target timestamp
    try:
        if isinstance(target_timestamp, str):
            target_time = datetime.fromisoformat(target_timestamp.replace('Z', '+00:00'))
            # Make timezone-naive for comparison
            target_time = target_time.replace(tzinfo=None)
        else:
            target_time = target_timestamp
            if hasattr(target_time, 'tzinfo') and target_time.tzinfo:
                target_time = target_time.replace(tzinfo=None)
    except:
        return None
    
    # Find closest match within 5 minutes
    matches = []
    for candidate in candidates:
        time_diff = abs((candidate['timestamp'] - target_time).total_seconds())
        if time_diff < 300:  # 5 minutes
            matches.append((candidate, time_diff))
    
    if not matches:
        return None
    
    # Sort by time difference and return closest
    matches.sort(key=lambda x: x[1])
    return matches[0][0]['path']

def reconcile_client(client_name, dry_run=False):
    """Reconcile images for a single client"""
    client_dir = Path('output/instacart') / client_name
    if not client_dir.exists():
        print(f"❌ Client directory not found: {client_dir}")
        return {'fixed': 0, 'broken': 0, 'total': 0}
    
    print(f"\n📁 Processing client: {client_name}")
    
    # Build image index
    print(f"   Building image index...")
    image_index = build_image_index(client_dir)
    total_images = sum(len(imgs) for imgs in image_index.values())
    print(f"   Found {total_images} images indexed by {len(image_index)} advertiser+type combinations")
    
    # Process all JSON files
    stats = {'fixed': 0, 'broken': 0, 'total': 0, 'files_modified': 0}
    
    json_pattern = str(client_dir / 'runs' / '*' / '*.json')
    for json_file in glob.glob(json_pattern):
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
            
            modified = False
            
            for ad in data.get('ads', []):
                img_path = ad.get('image_path', '')
                if not img_path:
                    continue
                
                stats['total'] += 1
                
                # Check if image exists
                full_path = client_dir / img_path
                if full_path.exists():
                    continue
                
                stats['broken'] += 1
                
                # Try to find matching image
                advertisers = ad.get('advertisers', [])
                if not advertisers or advertisers[0] == 'unknown':
                    continue
                
                advertiser = advertisers[0]
                ad_type = ad.get('type', '')
                timestamp = ad.get('timestamp', '')
                position = ad.get('position')
                
                matching_img = find_matching_image(image_index, advertiser, ad_type, timestamp, position)
                
                if matching_img:
                    # Update image_path to point to the found file
                    new_path = str(matching_img.relative_to(client_dir))
                    
                    if not dry_run:
                        ad['image_path'] = new_path
                        modified = True
                    
                    stats['fixed'] += 1
            
            if modified and not dry_run:
                with open(json_file, 'w') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                stats['files_modified'] += 1
        
        except Exception as e:
            print(f"   ⚠️  Error processing {json_file}: {e}")
            continue
    
    return stats

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Reconcile Instacart image paths')
    parser.add_argument('--client', help='Specific client to reconcile (default: all)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    args = parser.parse_args()
    
    print("=" * 80)
    print("INSTACART IMAGE RECONCILIATION")
    print("=" * 80)
    
    if args.dry_run:
        print("🔍 DRY RUN MODE - No changes will be made\n")
    
    # Get list of clients
    instacart_dir = Path('output/instacart')
    if not instacart_dir.exists():
        print("❌ Instacart output directory not found")
        return
    
    if args.client:
        clients = [args.client]
    else:
        clients = [d.name for d in instacart_dir.iterdir() if d.is_dir() and (d / 'runs').exists()]
    
    print(f"Processing {len(clients)} client(s)...\n")
    
    # Process each client
    total_stats = {'fixed': 0, 'broken': 0, 'total': 0, 'files_modified': 0}
    
    for client in sorted(clients):
        stats = reconcile_client(client, dry_run=args.dry_run)
        total_stats['fixed'] += stats['fixed']
        total_stats['broken'] += stats['broken']
        total_stats['total'] += stats['total']
        total_stats['files_modified'] += stats['files_modified']
        
        if stats['broken'] > 0:
            fix_rate = (stats['fixed'] / stats['broken'] * 100) if stats['broken'] > 0 else 0
            print(f"   ✅ Fixed: {stats['fixed']}/{stats['broken']} ({fix_rate:.1f}%)")
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total ads with image_path: {total_stats['total']}")
    print(f"Broken references: {total_stats['broken']}")
    print(f"Fixed: {total_stats['fixed']}")
    print(f"Remaining broken: {total_stats['broken'] - total_stats['fixed']}")
    
    if not args.dry_run:
        print(f"JSON files modified: {total_stats['files_modified']}")
        print(f"\n✅ Reconciliation complete!")
        print(f"\nNext steps:")
        print(f"  1. Rebuild brand index: python3 tools/build_brand_index.py")
        print(f"  2. Test brand name verifier: python3 tools/brand_name_verifier.py")
    else:
        print(f"\n🔍 Dry run complete. Run without --dry-run to apply changes.")

if __name__ == '__main__':
    main()
