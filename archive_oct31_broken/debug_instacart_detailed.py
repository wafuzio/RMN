#!/usr/bin/env python3
"""
Detailed Instacart HTML Analysis

Shows ALL potential ad containers with their class names and content.
"""

import sys
from pathlib import Path
from bs4 import BeautifulSoup


def analyze_all_containers(html_path: str):
    """Find all potential ad containers."""
    print(f"\n{'='*80}")
    print(f"DETAILED CONTAINER ANALYSIS: {Path(html_path).name}")
    print(f"{'='*80}\n")
    
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Look for any div with brand-related content
    print("🔍 SEARCHING FOR BRAND LOGOS (img with alt text):")
    print("-" * 80)
    
    brand_images = soup.select('img[alt]:not([alt=""])')
    brand_containers = {}
    
    for img in brand_images:
        alt = img.get('alt', '').strip()
        if not alt or alt.lower() in ['logo', 'image', 'ad', 'banner']:
            continue
        
        # Find parent container
        parent = img.find_parent('div')
        if parent:
            parent_classes = ' '.join(parent.get('class', []))
            if parent_classes not in brand_containers:
                brand_containers[parent_classes] = []
            brand_containers[parent_classes].append({
                'alt': alt,
                'src': img.get('src', '')[:100],
                'parent_id': parent.get('id', 'no-id')
            })
    
    for classes, images in brand_containers.items():
        print(f"\n  Container class: {classes or '(no class)'}")
        for img_info in images:
            print(f"    - Brand: '{img_info['alt']}'")
            print(f"      Src: {img_info['src']}...")
            if img_info['parent_id'] != 'no-id':
                print(f"      Parent ID: {img_info['parent_id']}")
    
    # Look for specific brand names mentioned
    print("\n\n🔍 SEARCHING FOR SPECIFIC BRANDS:")
    print("-" * 80)
    brands_to_find = ['Stonyfield', 'Marzetti', 'Sour Patch']
    
    for brand in brands_to_find:
        # Search in text content
        elements = soup.find_all(string=lambda text: text and brand.lower() in text.lower())
        print(f"\n  '{brand}' found in {len(elements)} elements:")
        
        for elem in elements[:3]:  # Show first 3
            parent = elem.parent
            parent_name = parent.name if parent else 'unknown'
            parent_classes = ' '.join(parent.get('class', [])) if parent else ''
            text_preview = str(elem).strip()[:80]
            print(f"    - <{parent_name} class='{parent_classes}'> {text_preview}...")
    
    # Look for all divs with e- prefixed classes (Instacart's pattern)
    print("\n\n🔍 ALL INSTACART AD-LIKE CONTAINERS (e-* classes):")
    print("-" * 80)
    
    ad_like_divs = soup.find_all('div', class_=lambda x: x and any(c.startswith('e-') for c in x))
    class_counts = {}
    
    for div in ad_like_divs:
        classes = ' '.join(div.get('class', []))
        # Only count classes that look like ad containers (not tiny utility classes)
        if len(classes) > 5:
            class_counts[classes] = class_counts.get(classes, 0) + 1
    
    # Sort by count
    sorted_classes = sorted(class_counts.items(), key=lambda x: x[1], reverse=True)
    
    print(f"\n  Found {len(sorted_classes)} unique container types:")
    for classes, count in sorted_classes[:20]:  # Top 20
        print(f"    {count:3d}x  {classes}")
    
    print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 debug_instacart_detailed.py <html_file>")
        sys.exit(1)
    
    html_path = sys.argv[1]
    
    if not Path(html_path).exists():
        print(f"❌ File not found: {html_path}")
        sys.exit(1)
    
    analyze_all_containers(html_path)
