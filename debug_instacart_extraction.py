#!/usr/bin/env python3
"""
Debug Instacart Ad Extraction

This script analyzes saved Instacart HTML files to diagnose extraction issues.
It shows what ad containers are found and what brands are extracted.
"""

import sys
import json
from pathlib import Path
from bs4 import BeautifulSoup


def analyze_html(html_path: str):
    """Analyze an Instacart HTML file for ad containers and brands."""
    print(f"\n{'='*80}")
    print(f"Analyzing: {html_path}")
    print(f"{'='*80}\n")
    
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Check for different ad container types
    selectors = {
        'Shoppable Display Ad (e-1qzz7bi)': 'div.e-1qzz7bi',
        'Display Ad (e-1hv1sre)': 'div.e-1hv1sre',
        'Recipe Container (e-1yrpusx)': 'div.e-1yrpusx',
        'Sponsored Label (e-cwus85)': 'div.e-cwus85',
    }
    
    print("📦 AD CONTAINER COUNTS:")
    print("-" * 80)
    for name, selector in selectors.items():
        elements = soup.select(selector)
        print(f"  {name}: {len(elements)}")
    print()
    
    # Analyze Shoppable Display Ads in detail
    print("🔍 SHOPPABLE DISPLAY ADS ANALYSIS:")
    print("-" * 80)
    shoppable_ads = soup.select('div.e-1qzz7bi')
    
    if not shoppable_ads:
        print("  ❌ No Shoppable Display Ads found!")
        print("  This might indicate:")
        print("    - Selectors have changed")
        print("    - Page didn't load properly")
        print("    - Different ad types are being served")
    else:
        for i, ad in enumerate(shoppable_ads, 1):
            print(f"\n  Ad #{i}:")
            
            # Check for video
            video = ad.select_one('div[id^="video-player-"]')
            ad_type = "Shoppable Video Ad" if video else "Shoppable Display Ad"
            print(f"    Type: {ad_type}")
            
            # Look for brand logo
            logo_img = ad.select_one('img[alt]:not([alt=""])')
            if logo_img:
                alt_text = logo_img.get('alt', '')
                src = logo_img.get('src', '')
                print(f"    Logo Alt: '{alt_text}'")
                print(f"    Logo Src: {src[:80]}...")
            else:
                print(f"    Logo: ❌ Not found")
            
            # Look for product carousel
            products = ad.select('[data-testid^="item_list_item"]')
            if products:
                print(f"    Products in carousel: {len(products)}")
                # Show first product
                first_product = products[0]
                product_text = first_product.get_text(strip=True)
                print(f"    First product: {product_text[:100]}...")
            else:
                print(f"    Products: ❌ Not found")
            
            # Look for brand link
            brand_link = ad.select_one('a[href*="/brands/"]')
            if brand_link:
                href = brand_link.get('href', '')
                print(f"    Brand link: {href}")
            
            # Look for heading
            heading = ad.select_one('h2, h3, [class*="heading"]')
            if heading:
                heading_text = heading.get_text(strip=True)
                print(f"    Heading: '{heading_text}'")
    
    # Analyze Display Ads
    print("\n\n🔍 DISPLAY ADS ANALYSIS:")
    print("-" * 80)
    display_ads = soup.select('div.e-1hv1sre')
    
    if not display_ads:
        print("  ❌ No Display Ads found!")
    else:
        for i, ad in enumerate(display_ads, 1):
            print(f"\n  Ad #{i}:")
            
            # Look for brand logo
            logo_img = ad.select_one('img[alt]:not([alt=""])')
            if logo_img:
                alt_text = logo_img.get('alt', '')
                src = logo_img.get('src', '')
                print(f"    Logo Alt: '{alt_text}'")
                print(f"    Logo Src: {src[:80]}...")
            else:
                print(f"    Logo: ❌ Not found")
            
            # Look for heading
            heading = ad.select_one('h2')
            if heading:
                heading_text = heading.get_text(strip=True)
                print(f"    Heading: '{heading_text}'")
    
    # Analyze Recipe Ads
    print("\n\n🔍 RECIPE ADS ANALYSIS:")
    print("-" * 80)
    recipe_containers = soup.select('div.e-1yrpusx')
    recipe_ads = [r for r in recipe_containers if r.select_one('h2.e-5ieped')]
    
    if not recipe_ads:
        print("  ❌ No Recipe Ads found!")
    else:
        for i, ad in enumerate(recipe_ads, 1):
            print(f"\n  Recipe #{i}:")
            
            # Look for recipe link
            recipe_link = ad.select_one('a[href*="/recipes/"]')
            if recipe_link:
                href = recipe_link.get('href', '')
                print(f"    Recipe URL: {href}")
                
                # Recipe title
                title = recipe_link.select_one('h2')
                if title:
                    print(f"    Title: '{title.get_text(strip=True)}'")
                
                # Brand logo
                logo_img = recipe_link.select_one('img[alt]')
                if logo_img:
                    alt_text = logo_img.get('alt', '')
                    print(f"    Brand: '{alt_text}'")
    
    print("\n" + "="*80 + "\n")


def compare_with_json(html_path: str, json_path: str):
    """Compare HTML analysis with extracted JSON."""
    print(f"\n{'='*80}")
    print(f"COMPARING WITH JSON")
    print(f"{'='*80}\n")
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    ads = data.get('results', [{}])[0].get('ads', [])
    
    print(f"📊 JSON EXTRACTION RESULTS:")
    print(f"  Total ads extracted: {len(ads)}")
    print()
    
    for i, ad in enumerate(ads, 1):
        print(f"  Ad #{i}:")
        print(f"    Type: {ad.get('ad_type', 'Unknown')}")
        print(f"    Brand: {ad.get('brand', 'Unknown')}")
        advertisers = ad.get('advertisers', [])
        if advertisers:
            print(f"    Advertisers: {advertisers}")
        if 'recipe_title' in ad:
            print(f"    Recipe: {ad.get('recipe_title')}")
        print()
    
    print("="*80 + "\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python debug_instacart_extraction.py <html_file> [json_file]")
        print("\nExample:")
        print("  python debug_instacart_extraction.py output/instacart/client/runs/search_results_*.html")
        sys.exit(1)
    
    html_path = sys.argv[1]
    
    if not Path(html_path).exists():
        print(f"❌ File not found: {html_path}")
        sys.exit(1)
    
    analyze_html(html_path)
    
    # If JSON path provided, compare
    if len(sys.argv) >= 3:
        json_path = sys.argv[2]
        if Path(json_path).exists():
            compare_with_json(html_path, json_path)
        else:
            print(f"⚠️  JSON file not found: {json_path}")
