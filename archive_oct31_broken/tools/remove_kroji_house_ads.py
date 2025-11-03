#!/usr/bin/env python3
"""
Remove Kroji house ads from JSON files.
Kroji is Kroger's mascot and these are house ads, not brand ads.
"""

import json
import glob
import os
from pathlib import Path

def is_kroji_ad(ad):
    """Check if ad contains Kroji (Kroger house ad)"""
    # Check message
    message = ad.get('message', '')
    if 'kroji' in message.lower():
        return True
    
    # Check header
    header = ad.get('header', '')
    if 'kroji' in header.lower():
        return True
    
    # Check advertisers
    advertisers = ad.get('advertisers', [])
    if any('kroji' in str(adv).lower() for adv in advertisers):
        return True
    
    return False

def remove_kroji_from_json_files():
    """Remove Kroji ads from all JSON files"""
    # Find all JSON files
    json_files = []
    for retailer in ['kroger', 'walmart', 'instacart']:
        pattern1 = f'output/{retailer}/*/runs/*.json'
        pattern2 = f'output/{retailer}/*/runs/*/*.json'
        json_files.extend(glob.glob(pattern1))
        json_files.extend(glob.glob(pattern2))
    
    json_files = list(set(json_files))
    
    total_removed = 0
    files_modified = 0
    
    for json_file in json_files:
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
            
            modified = False
            
            # Handle both legacy and canonical structures
            if 'results' in data:
                # Legacy structure
                for result in data['results']:
                    if 'ads' in result:
                        original_count = len(result['ads'])
                        result['ads'] = [ad for ad in result['ads'] if not is_kroji_ad(ad)]
                        removed = original_count - len(result['ads'])
                        if removed > 0:
                            total_removed += removed
                            modified = True
                            print(f"  Removed {removed} Kroji ad(s) from {json_file}")
            
            elif 'ads' in data:
                # Canonical structure
                original_count = len(data['ads'])
                data['ads'] = [ad for ad in data['ads'] if not is_kroji_ad(ad)]
                removed = original_count - len(data['ads'])
                if removed > 0:
                    total_removed += removed
                    modified = True
                    print(f"  Removed {removed} Kroji ad(s) from {json_file}")
            
            # Save if modified
            if modified:
                with open(json_file, 'w') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                files_modified += 1
        
        except Exception as e:
            print(f"  Error processing {json_file}: {e}")
            continue
    
    print(f"\n✅ Cleanup complete:")
    print(f"   Files scanned: {len(json_files)}")
    print(f"   Files modified: {files_modified}")
    print(f"   Total Kroji ads removed: {total_removed}")

if __name__ == '__main__':
    print("Removing Kroji house ads from JSON files...")
    remove_kroji_from_json_files()
