#!/usr/bin/env python3
"""Test if the brand review tool logic catches the unknown carousel"""

import json
import os
import re
from pathlib import Path

json_file = 'output/kroger/MilkPEP/runs/run_results_protein_powder_2025-10-24_10-36-09.json'

with open(json_file) as f:
    data = json.load(f)

ads = [ad for r in data.get('results',[]) for ad in r.get('ads',[])]
carousel2 = [ad for ad in ads if ad.get('type')=='CuratedCarousel'][1]

print("Testing carousel #2 detection:")
print(f"  Advertisers in JSON: {carousel2.get('advertisers')}")
print(f"  Image path in JSON: {carousel2.get('carousel_image_path')}")
print()

# Simulate the brand review tool logic
advertisers = carousel2.get('advertisers', [])
is_unknown_in_json = (
    not advertisers or
    advertisers == ['unknown'] or
    advertisers == ['Unknown'] or
    any(adv and adv.lower() == 'unknown' for adv in advertisers)
)

print(f"is_unknown_in_json: {is_unknown_in_json}")
print()

# Get image path from JSON
image_path_from_json = carousel2.get('carousel_image_path', '')
base_dir = os.path.dirname(os.path.dirname(json_file))
image_path = os.path.join(base_dir, image_path_from_json) if image_path_from_json else None

print(f"Constructed image path: {image_path}")
print(f"Path exists: {os.path.exists(image_path) if image_path else False}")
print()

# Check for unknown files
is_unknown_in_filename = False

if image_path and not os.path.exists(image_path):
    print("Image path doesn't exist, searching for unknown files...")
    
    ad_type = carousel2.get('type')
    type_to_folder = {
        'TOA': 'TOA',
        'Skyscraper': 'Skyscraper',
        'CuratedCarousel': 'Carousel',
    }
    subfolder = type_to_folder.get(ad_type)
    
    if subfolder:
        search_dir = os.path.join(base_dir, subfolder)
        print(f"  Search dir: {search_dir}")
        print(f"  Search dir exists: {os.path.exists(search_dir)}")
        
        if os.path.exists(search_dir):
            for filename in os.listdir(search_dir):
                if '__unknown__' in filename:
                    print(f"  Found unknown file: {filename}")
                    
                    # Check timestamp match
                    stored_filename = os.path.basename(image_path)
                    stored_ts = re.search(r'D(\d{4}-\d{2}-\d{2}_T\d{2}-\d{2})', stored_filename)
                    unknown_ts = re.search(r'D(\d{4}-\d{2}-\d{2}_T\d{2}-\d{2})', filename)
                    
                    print(f"    Stored timestamp: {stored_ts.group(1) if stored_ts else 'None'}")
                    print(f"    Unknown timestamp: {unknown_ts.group(1) if unknown_ts else 'None'}")
                    
                    if stored_ts and unknown_ts:
                        stored_dt = stored_ts.group(1)
                        unknown_dt = unknown_ts.group(1)
                        if stored_dt == unknown_dt:
                            print(f"    ✓ Timestamps match! Should flag this ad.")
                            is_unknown_in_filename = True
                            image_path = os.path.join(search_dir, filename)
                            break

print()
print(f"is_unknown_in_filename: {is_unknown_in_filename}")
print(f"Should be flagged for review: {is_unknown_in_json or is_unknown_in_filename}")
