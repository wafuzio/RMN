#!/usr/bin/env python3
"""
Clean Kroji Holdings references from JSON files
"""

import json
import os
import glob

def clean_json_file(filepath):
    """Remove Kroji Holdings from advertisers and clean up image paths"""
    print(f"Processing: {filepath}")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    modified = False
    
    # Process results array
    if 'results' in data:
        for result in data['results']:
            if 'ads' in result:
                ads_to_keep = []
                for ad in result['ads']:
                    # Check advertisers field
                    advertisers = ad.get('advertisers', [])
                    if advertisers:
                        # Filter out kroji holdings
                        filtered = [a for a in advertisers if 'kroji' not in a.lower()]
                        if len(filtered) != len(advertisers):
                            print(f"  Removed Kroji from advertisers: {advertisers} -> {filtered}")
                            ad['advertisers'] = filtered
                            modified = True
                        
                        # If no advertisers left, skip this ad
                        if not filtered:
                            print(f"  Skipping ad with only Kroji as advertiser")
                            continue
                    
                    # Check image paths for kroji
                    for img_field in ['image_path', 'toa_image_path', 'skyscraper_image_path', 'carousel_image_path']:
                        if img_field in ad and ad[img_field]:
                            if 'kroji' in ad[img_field].lower():
                                print(f"  Removing image path with kroji: {ad[img_field]}")
                                ad[img_field] = None
                                modified = True
                    
                    ads_to_keep.append(ad)
                
                # Update ads list
                if len(ads_to_keep) != len(result['ads']):
                    result['ads'] = ads_to_keep
                    result['count'] = len(ads_to_keep)
                    modified = True
    
    if modified:
        # Write back to file
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        print(f"  ✅ Updated {filepath}")
        return True
    else:
        print(f"  ℹ️  No changes needed")
        return False

def main():
    # Find all JSON files in output directory
    json_files = glob.glob('output/**/runs/*.json', recursive=True)
    
    print(f"Found {len(json_files)} JSON files to check\n")
    
    updated_count = 0
    for json_file in json_files:
        if clean_json_file(json_file):
            updated_count += 1
        print()
    
    print(f"Summary: Updated {updated_count} file(s)")

if __name__ == '__main__':
    main()
