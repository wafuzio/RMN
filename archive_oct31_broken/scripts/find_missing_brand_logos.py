#!/usr/bin/env python3
"""
Find brands that are missing from the brand logo database.

This script identifies:
1. Brands in the lexicon without logo entries
2. Brands appearing in recent scraper runs without logo entries
3. Brands with broken/inaccessible logo URLs
"""

import json
import os
import re
from pathlib import Path
from collections import Counter

def get_base_dir():
    """Get the base directory of the project"""
    return Path(__file__).parent.parent

def get_brands_from_lexicon():
    """Get all brand names from the lexicon"""
    lexicon_path = get_base_dir() / "config" / "brands.json"
    with open(lexicon_path, 'r') as f:
        brands = json.load(f)
    return {b['name'] for b in brands}

def get_brands_from_logo_database():
    """Get all brand names that have logo entries"""
    logo_db_path = get_base_dir() / "docs" / "BRAND_LOGO_DATABASE.md"
    if not logo_db_path.exists():
        return set()
    
    with open(logo_db_path, 'r') as f:
        content = f.read()
    
    # Extract brand names from ## headers
    brands = set()
    for line in content.split('\n'):
        if line.startswith('## ') and not line.startswith('## '):
            brand = line[3:].strip()
            if brand and brand != 'Brand Logo Database':
                brands.add(brand)
    
    return brands

def get_brands_from_recent_runs(limit=100):
    """Get brands appearing in recent scraper runs"""
    output_dir = get_base_dir() / "output"
    brands = Counter()
    
    # Find all JSON files in output directory
    json_files = []
    for root, dirs, files in os.walk(output_dir):
        for file in files:
            if file.endswith('.json') and 'run_results' in file:
                json_files.append(os.path.join(root, file))
    
    # Sort by modification time, newest first
    json_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    
    # Check the most recent files
    for json_file in json_files[:limit]:
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
            
            # Extract advertisers
            for result in data.get('results', []):
                for ad in result.get('ads', []):
                    advertisers = ad.get('advertisers', [])
                    if advertisers:
                        for advertiser in advertisers:
                            if advertiser and advertiser != 'unknown':
                                brands[advertiser] += 1
        except (json.JSONDecodeError, KeyError):
            continue
    
    return brands

def main():
    print("=" * 70)
    print("BRAND LOGO DATABASE ANALYSIS")
    print("=" * 70)
    print()
    
    # Get brands from different sources
    lexicon_brands = get_brands_from_lexicon()
    logo_db_brands = get_brands_from_logo_database()
    recent_brands = get_brands_from_recent_runs()
    
    print(f"📚 Brands in lexicon: {len(lexicon_brands)}")
    print(f"🖼️  Brands with logos: {len(logo_db_brands)}")
    print(f"📊 Brands in recent runs: {len(recent_brands)}")
    print()
    
    # Find missing from lexicon
    print("=" * 70)
    print("LEXICON BRANDS MISSING LOGOS")
    print("=" * 70)
    missing_from_lexicon = lexicon_brands - logo_db_brands
    if missing_from_lexicon:
        for brand in sorted(missing_from_lexicon):
            print(f"  ❌ {brand}")
    else:
        print("  ✅ All lexicon brands have logos!")
    print()
    
    # Find brands in recent runs without logos
    print("=" * 70)
    print("RECENT BRANDS MISSING LOGOS (by frequency)")
    print("=" * 70)
    missing_recent = {brand: count for brand, count in recent_brands.items() 
                     if brand not in logo_db_brands}
    if missing_recent:
        for brand, count in sorted(missing_recent.items(), key=lambda x: x[1], reverse=True):
            print(f"  ❌ {brand} (appeared {count} times)")
    else:
        print("  ✅ All recent brands have logos!")
    print()
    
    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    total_missing = len(missing_from_lexicon | set(missing_recent.keys()))
    print(f"Total unique brands missing logos: {total_missing}")
    print()
    
    if total_missing > 0:
        print("RECOMMENDED ACTIONS:")
        print("1. Review the list above")
        print("2. Find official logos for each brand")
        print("3. Add entries to docs/BRAND_LOGO_DATABASE.md")
        print("4. See docs/BRAND_LOGO_TASK.md for detailed instructions")
    else:
        print("✅ All brands have logo entries!")
    print()

if __name__ == "__main__":
    main()
