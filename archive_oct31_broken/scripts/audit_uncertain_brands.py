#!/usr/bin/env python3
"""
Audit all JSON files to find ads with uncertain brands that should be marked as 'unknown'.
This uses the same logic as the Brand Review Tool to identify uncertain brands.
Also checks image filenames and renames them to match.
"""

import json
import glob
import re
import os
import shutil
from collections import defaultdict

def to_slug(brand):
    """Convert brand name to filename slug"""
    if not brand:
        return 'unknown'
    return brand.lower().replace(' ', '_').replace("'", '').replace('&', 'and')

def is_uncertain_brand(brand):
    """Check if a brand name looks uncertain or like a campaign code"""
    if not brand or brand == 'unknown':
        return True
    
    # Kroger and Kroger-branded products are valid, not uncertain
    if brand.lower().startswith('kroger'):
        return False
    
    # Single word that's too short or generic
    if len(brand) <= 3 and brand.lower() not in ['p&g', 'jif']:
        return True
    
    # Specific campaign code patterns
    uncertain_patterns = [
        r'^(TOAOB|MSM|SSM|FWGOL)',  # Kroger campaign prefixes
        r'(KB|MB|TOA|Scale|Act)\d+',  # Campaign type codes
        r'(Q\d+|FY\d+|H\d+)$',  # Quarter/fiscal year codes
        r'^NT\d+\s*NT$',  # NT codes
    ]
    
    for pattern in uncertain_patterns:
        if re.search(pattern, brand, re.IGNORECASE):
            return True
    
    # HEURISTIC: Check if it looks like a campaign code vs a real brand
    # Campaign codes typically have:
    # 1. Mix of uppercase/lowercase in weird ways (not title case)
    # 2. Numbers mixed with letters in unnatural patterns
    # 3. Multiple dates/years (e.g., 2025, May, 31)
    # 4. No spaces but very long
    
    # Count digits
    digit_count = sum(c.isdigit() for c in brand)
    letter_count = sum(c.isalpha() for c in brand)
    
    # If more than 30% digits, likely a campaign code
    if letter_count > 0 and digit_count / len(brand) > 0.3:
        return True
    
    # If contains 4-digit year (2024, 2025, etc.)
    if re.search(r'20\d{2}', brand):
        return True
    
    # If has month names mixed with other stuff (as whole words, not substrings)
    months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
    brand_lower = brand.lower()
    for month in months:
        # Use word boundary to avoid matching "may" in "Mayer"
        if re.search(r'\b' + month + r'\b', brand_lower) and len(brand) > 8:
            return True
    
    # If has weird capitalization (multiple capital letters not at start)
    # e.g., "TOAAlwaysOn" or "F25May26"
    capitals = [i for i, c in enumerate(brand) if c.isupper()]
    if len(capitals) > 2:  # More than 2 capitals suggests acronym/code
        # Check if they're not just at word boundaries (like "McDonald's")
        if any(i > 0 and brand[i-1].islower() for i in capitals[1:]):
            return True
    
    # If ends with 4+ digits
    if re.search(r'\d{4,}$', brand):
        return True
    
    return False

def main():
    print("🔍 Auditing all JSON files for uncertain brands...\n")
    
    # Scan all Kroger JSON files
    json_files = glob.glob('output/kroger/*/runs/*.json')
    print(f"Found {len(json_files)} JSON files to scan\n")
    
    uncertain_ads = []
    stats = {
        'total_files': len(json_files),
        'total_ads': 0,
        'uncertain_ads': 0,
        'by_pattern': defaultdict(int),
        'by_client': defaultdict(int),
    }
    
    for json_file in json_files:
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
            
            # Extract client from path
            client = json_file.split(os.sep)[-3]
            
            for result in data.get('results', []):
                for ad in result.get('ads', []):
                    stats['total_ads'] += 1
                    advertisers = ad.get('advertisers', [])
                    
                    # Check each advertiser
                    for advertiser in advertisers:
                        if is_uncertain_brand(advertiser):
                            stats['uncertain_ads'] += 1
                            stats['by_client'][client] += 1
                            
                            # Determine which pattern matched
                            if not advertiser or advertiser == 'unknown':
                                reason = "Already 'unknown'"
                            elif re.search(r'^(TOAOB|MSM|SSM|FWGOL)', advertiser, re.IGNORECASE):
                                reason = "Campaign prefix"
                            elif re.search(r'^\w+\d{4,}$', advertiser):
                                reason = "Alphanumeric + 4+ digits"
                            elif re.search(r'(KB|MB|TOA|Scale|Act)\d+', advertiser, re.IGNORECASE):
                                reason = "Campaign type code"
                            elif re.search(r'(Q\d+|FY\d+|H\d+)$', advertiser, re.IGNORECASE):
                                reason = "Quarter/fiscal code"
                            elif re.search(r'\d{4}(Q\d+|SD|SB)', advertiser, re.IGNORECASE):
                                reason = "Year + season code"
                            elif re.search(r'^NT\d+\s*NT$', advertiser, re.IGNORECASE):
                                reason = "NT code"
                            elif re.search(r'^TOA\w+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)', advertiser, re.IGNORECASE):
                                reason = "TOA + month code"
                            elif len(advertiser) <= 3:
                                reason = "Too short"
                            else:
                                reason = "Unknown reason"
                            
                            stats['by_pattern'][reason] += 1
                            
                            uncertain_ads.append({
                                'file': json_file,
                                'client': client,
                                'ad_type': ad.get('type'),
                                'current_brand': advertiser,
                                'reason': reason,
                                'message': ad.get('message', '')[:50]
                            })
                            break  # Only count once per ad
        
        except (json.JSONDecodeError, KeyError) as e:
            print(f"⚠️  Error reading {json_file}: {e}")
            continue
    
    # Print summary
    print("=" * 80)
    print("📊 AUDIT SUMMARY")
    print("=" * 80)
    print(f"Total files scanned: {stats['total_files']}")
    print(f"Total ads found: {stats['total_ads']}")
    print(f"Uncertain ads: {stats['uncertain_ads']}")
    print()
    
    print("Breakdown by reason:")
    for reason, count in sorted(stats['by_pattern'].items(), key=lambda x: -x[1]):
        print(f"  {reason:30s}: {count:4d}")
    print()
    
    print("Breakdown by client:")
    for client, count in sorted(stats['by_client'].items(), key=lambda x: -x[1])[:10]:
        print(f"  {client:30s}: {count:4d}")
    print()
    
    # Show examples
    if uncertain_ads:
        print("=" * 80)
        print("📋 EXAMPLES (first 20)")
        print("=" * 80)
        for i, ad in enumerate(uncertain_ads[:20], 1):
            print(f"\n{i}. {ad['current_brand']}")
            print(f"   Reason: {ad['reason']}")
            print(f"   Client: {ad['client']}")
            print(f"   Type: {ad['ad_type']}")
            print(f"   File: {os.path.basename(ad['file'])}")
            if ad['message']:
                print(f"   Message: {ad['message']}")
    
    # Ask if user wants to fix them
    print("\n" + "=" * 80)
    if uncertain_ads:
        response = input(f"\nFound {len(uncertain_ads)} uncertain ads. Mark them all as 'unknown'? (yes/no): ")
        if response.lower() in ['yes', 'y']:
            fix_uncertain_brands(uncertain_ads)
        else:
            print("No changes made.")
    else:
        print("✅ No uncertain brands found!")

def fix_uncertain_brands(uncertain_ads):
    """Update JSON files and image filenames to mark uncertain brands as 'unknown'"""
    print("\n🔧 Updating JSON files and image filenames...")
    
    # Group by file
    by_file = defaultdict(list)
    for ad in uncertain_ads:
        by_file[ad['file']].append(ad)
    
    updated_files = 0
    updated_ads = 0
    renamed_images = 0
    
    for json_file, ads_to_fix in by_file.items():
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
            
            modified = False
            base_dir = os.path.dirname(os.path.dirname(json_file))  # output/kroger/CLIENT
            
            for result in data.get('results', []):
                for ad in result.get('ads', []):
                    advertisers = ad.get('advertisers', [])
                    
                    # Check if any advertiser is uncertain
                    new_advertisers = []
                    old_brand = None
                    changed = False
                    
                    for advertiser in advertisers:
                        if is_uncertain_brand(advertiser) and advertiser != 'unknown':
                            old_brand = advertiser
                            new_advertisers.append('unknown')
                            changed = True
                        else:
                            new_advertisers.append(advertiser)
                    
                    if changed and old_brand:
                        ad['advertisers'] = new_advertisers
                        modified = True
                        updated_ads += 1
                        
                        # Update image path in JSON and rename file
                        for path_key in ['carousel_image_path', 'toa_image_path', 'skyscraper_image_path']:
                            if path_key in ad:
                                old_path_rel = ad[path_key]
                                old_path_full = os.path.join(base_dir, old_path_rel)
                                
                                # Generate new path with 'unknown' instead of old brand
                                old_slug = to_slug(old_brand)
                                new_slug = 'unknown'
                                new_path_rel = old_path_rel.replace(f'__{old_slug}__', f'__{new_slug}__')
                                new_path_full = os.path.join(base_dir, new_path_rel)
                                
                                # Rename file if it exists and paths are different
                                if old_path_full != new_path_full and os.path.exists(old_path_full):
                                    try:
                                        shutil.move(old_path_full, new_path_full)
                                        ad[path_key] = new_path_rel
                                        renamed_images += 1
                                        print(f"  📁 Renamed: {os.path.basename(old_path_full)}")
                                        print(f"         -> {os.path.basename(new_path_full)}")
                                    except Exception as e:
                                        print(f"  ⚠️  Failed to rename {old_path_full}: {e}")
                                elif old_path_full != new_path_full:
                                    # Update path in JSON even if file doesn't exist
                                    ad[path_key] = new_path_rel
            
            if modified:
                with open(json_file, 'w') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                updated_files += 1
                print(f"  ✓ {os.path.basename(json_file)}")
        
        except Exception as e:
            print(f"  ✗ Error updating {json_file}: {e}")
    
    print(f"\n✅ Updated {updated_ads} ads in {updated_files} files")
    print(f"✅ Renamed {renamed_images} image files")

if __name__ == '__main__':
    main()
