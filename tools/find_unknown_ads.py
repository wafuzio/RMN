#!/usr/bin/env python3
"""
Quick diagnostic script to find ads with "unknown" or missing brands
that might not be caught by the brand review tool.
"""

import json
import glob
import os
import re

def check_ad(ad, json_file):
    """Check if an ad should be flagged as unknown"""
    advertisers = ad.get('advertisers', [])
    ad_type = ad.get('type', 'unknown')
    
    # Skip main ads (full-page screengrabs)
    if ad_type == 'main':
        return None
    
    # Check various unknown conditions
    reasons = []
    
    # Empty or missing advertisers
    if not advertisers:
        reasons.append("Empty/missing advertisers")
    
    # Explicitly unknown
    if advertisers == ['unknown'] or advertisers == ['Unknown']:
        reasons.append("Explicitly 'unknown'")
    
    # Contains unknown
    if any(adv and adv.lower() == 'unknown' for adv in advertisers):
        reasons.append("Contains 'unknown'")
    
    # Check for None values
    if advertisers and any(adv is None for adv in advertisers):
        reasons.append("Contains None values")
    
    # NEW: Check if image path exists and if actual file has __unknown__
    image_path = None
    if ad_type == 'CuratedCarousel':
        image_path = ad.get('carousel_image_path', '')
    elif ad_type == 'TOA':
        image_path = ad.get('toa_image_path', '')
    elif ad_type == 'Skyscraper':
        image_path = ad.get('skyscraper_image_path', '')
    else:
        image_path = ad.get('image_path', '')
    
    if image_path:
        base_dir = os.path.dirname(os.path.dirname(json_file))
        full_path = os.path.join(base_dir, image_path)
        
        if not os.path.exists(full_path):
            # Path from JSON doesn't exist - search for actual files
            ad_type_folders = {
                'CuratedCarousel': 'Carousel',
                'TOA': 'TOA',
                'Skyscraper': 'Skyscraper',
                'sba': 'SBA',
                'sbv': 'SBV',
            }
            folder = ad_type_folders.get(ad_type)
            if folder:
                search_dir = os.path.join(base_dir, folder)
                if os.path.exists(search_dir):
                    # Extract timestamp from JSON path
                    ts_match = re.search(r'D(\d{4}-\d{2}-\d{2}_T\d{2}-\d{2})', image_path)
                    if ts_match:
                        ts = ts_match.group(1)
                        # Look for files with same timestamp
                        for filename in os.listdir(search_dir):
                            if ts in filename and '__unknown__' in filename:
                                reasons.append(f"JSON path doesn't exist, found __unknown__ file: {filename}")
                                break
    
    if reasons:
        return {
            'file': json_file,
            'type': ad_type,
            'advertisers': advertisers,
            'reasons': reasons,
            'message': ad.get('message', '')[:60],
            'image_path': image_path
        }
    
    return None

def main():
    print("🔍 Scanning for unknown ads...\n")
    
    unknown_ads = []
    
    # Scan all retailers
    patterns = [
        'output/kroger/*/runs/*.json',
        'output/instacart/*/runs/*.json',
        'output/walmart/*/*/run_results_*.json',
        'output/walmart/*/runs/run_results_*.json',
    ]
    
    json_files = []
    for pattern in patterns:
        json_files.extend(glob.glob(pattern))
    
    print(f"Scanning {len(json_files)} JSON files...\n")
    
    for json_file in json_files:
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
            
            # Handle both canonical and legacy structures
            ads_to_check = []
            
            if 'ads' in data and isinstance(data['ads'], list):
                ads_to_check = data['ads']
            elif 'results' in data:
                for result in data.get('results', []):
                    ads_to_check.extend(result.get('ads', []))
            
            for ad in ads_to_check:
                result = check_ad(ad, json_file)
                if result:
                    unknown_ads.append(result)
        
        except Exception as e:
            print(f"Error reading {json_file}: {e}")
    
    print(f"\n📊 Found {len(unknown_ads)} unknown ads\n")
    
    # Group by reason
    by_reason = {}
    for ad in unknown_ads:
        for reason in ad['reasons']:
            if reason not in by_reason:
                by_reason[reason] = []
            by_reason[reason].append(ad)
    
    print("Breakdown by reason:")
    for reason, ads in by_reason.items():
        print(f"  {reason}: {len(ads)}")
    
    print("\n" + "="*80)
    print("Sample unknown ads (first 10):")
    print("="*80 + "\n")
    
    for i, ad in enumerate(unknown_ads[:10], 1):
        print(f"{i}. Type: {ad['type']}")
        print(f"   File: {ad['file']}")
        print(f"   Advertisers: {ad['advertisers']}")
        print(f"   Image path: {ad.get('image_path', 'N/A')}")
        print(f"   Reasons: {', '.join(ad['reasons'])}")
        print(f"   Message: {ad['message']}")
        print()

if __name__ == '__main__':
    main()
