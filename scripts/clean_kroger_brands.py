#!/usr/bin/env python3
"""
Clean and normalize Kroger brand extractions.

This script:
1. Extracts brand names from campaign codes (e.g., Campbell'sHoliday → Campbell's)
2. Filters out pure Kroger internal codes
3. Fixes partial text extractions
4. Normalizes case and duplicates
"""

import json
import os
import glob
import re
from collections import Counter

def extract_brand_from_campaign_code(code):
    """Extract brand name from Kroger campaign codes.
    
    Examples:
        Campbell'sHoliday → Campbell's
        HillshireFarmMB1025 → Hillshire Farm
        PinterestHeinzTailgate0825 → Heinz
        Impossible2025 → Impossible
    """
    # Remove common campaign suffixes
    code = re.sub(r'(Holiday|Tailgate|MB|TOA|Scale|Wave\d+|Always|Mayhem|Q\d+|FY\d+)\d*$', '', code, flags=re.IGNORECASE)
    
    # Remove platform prefixes
    code = re.sub(r'^(Pinterest|Facebook|Instagram|Twitter)', '', code, flags=re.IGNORECASE)
    
    # Remove date codes (MMYY or MMDDYY)
    code = re.sub(r'\d{4,6}$', '', code)
    
    # Split camelCase into words
    words = re.findall(r'[A-Z][a-z]+|[A-Z]+(?=[A-Z][a-z]|\b)', code)
    
    if words:
        brand = ' '.join(words)
        # Handle possessives
        brand = re.sub(r"s\s+", "s ", brand)  # "Campbell s" → "Campbell's"
        return brand.strip()
    
    return None

def is_kroger_internal_code(text):
    """Check if this is a pure Kroger internal campaign code (not a brand)."""
    # Patterns that indicate internal codes
    internal_patterns = [
        r'^(TOAOB|KROG|MSM|SSM|ZB)',  # Kroger prefixes
        r'^\w+\d{4,}$',  # Alphanumeric ending in 4+ digits
        r'(KB|MB|TOA|Scale|Act)\d+',  # Campaign type codes
        r'(Q\d+|FY\d+|H\d+)$',  # Quarter/fiscal year codes
    ]
    
    for pattern in internal_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    
    return False

def is_partial_extraction(text):
    """Check if this is a partial text extraction (not a real brand)."""
    # Common partial extractions that aren't brands
    partial_words = {
        'save', 'save on', 'save now', 'beat', 'beat the',
        'big', 'for', 'enjoy', 'ice', 'hamburger',
        'advertisement', 'digital deal', 'solutions', 'simple',
        'size', 'same', 'tailgate', 'tailgate m',
        'three', 'ghoul aid kool aid package'
    }
    
    return text.lower() in partial_words

def normalize_brand(brand):
    """Normalize brand name (fix case, remove duplicates)."""
    # Handle special cases
    if brand.lower() in ['kroger', 'kroger cereal']:
        return 'Kroger'
    
    if brand.lower() in ['frollies']:
        return 'Frollies'
    
    if brand.lower() in ['barilla']:
        return 'Barilla'
    
    if brand.lower() in ['magic spoon', 'magic_spoon']:
        return 'Magic Spoon'
    
    if brand.lower() in ["kellogg's", 'kellogg_s', 'kelloggs']:
        return "Kellogg's"
    
    # Handle P&G subbrands
    if 'tide' in brand.lower():
        return 'Tide'
    
    # Handle compound brands
    if 'uncrustables' in brand.lower():
        return 'Uncrustables'
    
    if 'ghoul aid' in brand.lower() or 'kool aid' in brand.lower():
        return 'Kool-Aid'
    
    if 'nestlé' in brand.lower() or 'nestle' in brand.lower():
        if 'toll' in brand.lower():
            return 'Toll House'
        return 'Nestlé'
    
    if 'hillshire' in brand.lower():
        return 'Hillshire Farm'
    
    if 'tillamook' in brand.lower():
        return 'Tillamook'
    
    # Default: return as-is
    return brand

def clean_kroger_brands():
    """Clean and normalize all Kroger brand extractions."""
    raw_brands = Counter()
    
    # Collect all brands from JSON files
    json_files = glob.glob('output/kroger/*/runs/*.json')
    
    for json_file in json_files:
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
            
            for result in data.get('results', []):
                for ad in result.get('ads', []):
                    advertisers = ad.get('advertisers', [])
                    for advertiser in advertisers:
                        if advertiser and advertiser != 'unknown':
                            raw_brands[advertiser] += 1
        except (json.JSONDecodeError, KeyError):
            continue
    
    # Process brands
    cleaned_brands = Counter()
    skipped = []
    extracted = []
    
    for brand, count in raw_brands.items():
        # Skip partial extractions
        if is_partial_extraction(brand):
            skipped.append((brand, count, "Partial extraction"))
            continue
        
        # Check if it's a campaign code
        if is_kroger_internal_code(brand):
            # Try to extract brand from campaign code
            extracted_brand = extract_brand_from_campaign_code(brand)
            if extracted_brand and not is_partial_extraction(extracted_brand):
                normalized = normalize_brand(extracted_brand)
                cleaned_brands[normalized] += count
                extracted.append((brand, extracted_brand, normalized, count))
            else:
                skipped.append((brand, count, "Internal code"))
            continue
        
        # Normalize the brand
        normalized = normalize_brand(brand)
        cleaned_brands[normalized] += count
    
    # Print results
    print("="*70)
    print("CLEANED KROGER BRANDS")
    print("="*70)
    print(f"\nTotal unique cleaned brands: {len(cleaned_brands)}\n")
    
    print("Brands by frequency:")
    for brand, count in sorted(cleaned_brands.items(), key=lambda x: x[1], reverse=True):
        print(f"  {brand:40} {count:4} occurrences")
    
    print("\n" + "="*70)
    print("BRANDS ALPHABETICALLY")
    print("="*70)
    for brand in sorted(cleaned_brands.keys()):
        print(f"  - {brand}")
    
    print("\n" + "="*70)
    print("EXTRACTED FROM CAMPAIGN CODES")
    print("="*70)
    for original, extracted_brand, normalized, count in extracted:
        print(f"  {original:40} → {normalized:20} ({count} occurrences)")
    
    print("\n" + "="*70)
    print("SKIPPED")
    print("="*70)
    for brand, count, reason in skipped:
        print(f"  {brand:40} ({count:2}x) - {reason}")
    
    return cleaned_brands

if __name__ == "__main__":
    clean_kroger_brands()
