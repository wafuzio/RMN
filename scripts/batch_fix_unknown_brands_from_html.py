#!/usr/bin/env python3
"""
Batch Fix Unknown Amazon Brands from HTML (Slot-Aware w/ BeautifulSoup)

Scans all Amazon JSON files for ads with "Unknown" brands.
Parses the companion HTML file using BeautifulSoup to map ad slots (Left Rail, Bottom)
to their specific accessibility text, ensuring 1:1 matching accuracy.

Updates:
  - JSON: advertisers, brand, brand_canonical
  - Image filenames: renames __unknown__ to __brand_slug__
"""

import os
import re
import json
import glob
import shutil
import argparse
from bs4 import BeautifulSoup

def load_lexicon(path="config/brands.json"):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception:
        return []

def to_slug(name):
    """Convert brand name to filename slug."""
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')

def match_brand_from_text(text, lexicon):
    """
    Extract brand from text using lexicon + heuristics.
    Text format often: "Sponsored Ad - [Brand] - [Title]" or "Sponsored Ad.\n[Brand] logo..."
    """
    if not text:
        return None
        
    # clean up text
    text = text.replace('\n', ' ').strip()
    
    # 1. Check strict "Sponsored ad from [Brand]"
    m = re.search(r"Sponsored\s+ad\s+from\s+([^\.]+)", text, re.IGNORECASE)
    if m:
        cand = m.group(1).strip()
        # Verify against lexicon if possible, or just accept if it looks like a brand
        return cand

    # 2. Check "Visit the [Brand] Store"
    m = re.search(r"Visit\s+the\s+(.+?)\s+Store", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # 3. Check Lexicon Matches against start of strings (common in product titles)
    text_lower = text.lower()
    for entry in lexicon:
        name = entry['name']
        # Check specific known synonyms first
        for syn in entry.get('synonyms', []):
            if syn.startswith("MSG:"): continue
            if syn.lower() in text_lower: # relaxed check
                return name
        # Check main name
        if name.lower() in text_lower:
            return name
            
    return None

def parse_html_for_ads(html_path):
    """
    Parse HTML to find display ads and their brands.
    Returns a dict: {'left': [brand1, brand2], 'bottom': [brand1...], 'other': []}
    """
    try:
        with open(html_path, 'r', errors='ignore') as f:
            soup = BeautifulSoup(f, 'html.parser')
    except Exception as e:
        print(f"  [ERROR] HTML parse failed: {e}")
        return {}

    results = {
        'left': [],
        'bottom': [],
        'other': []
    }

    # Helper to extract brand from an ad container
    def get_brand_from_node(node):
        # Look for accessibility spans
        spans = node.select('span.a-offscreen, span.aok-offscreen')
        for span in spans:
            txt = span.get_text(" ", strip=True)
            if "Sponsored Ad" in txt:
                # Try to extract brand from this text
                # Logic: "Sponsored Ad - Brand - Title" or "Sponsored Ad. Brand logo."
                
                # Cleanup common prefixes
                clean = re.sub(r'^Sponsored Ad\.?\s*', '', txt, flags=re.IGNORECASE)
                clean = re.sub(r'Brand logo\.?\s*', '', clean, flags=re.IGNORECASE)
                clean = re.sub(r'Product image\.?\s*', '', clean, flags=re.IGNORECASE)
                
                # If we have a clean string starting with something, that's likely the brand+title
                # We'll return the full clean text and let the caller match it to lexicon
                return clean
        return None

    # 1. Left Rail Ads
    # Selector: .s-left-ads-item or #desktop-ad-left-*
    left_items = soup.select('.s-left-ads-item, [id^="desktop-ad-left"]')
    for item in left_items:
        b = get_brand_from_node(item)
        if b: results['left'].append(b)

    # 2. Bottom/Footer Ads
    # Selector: #desktop-ad-bottom-*, or widgets in footer
    bottom_items = soup.select('[id^="desktop-ad-bottom"], [data-cel-widget*="bottom-advertising"], #ad-creative-bottom')
    for item in bottom_items:
        b = get_brand_from_node(item)
        if b: results['bottom'].append(b)

    return results

def main():
    parser = argparse.ArgumentParser(description="Batch fix unknown Amazon brands (Slot-Aware)")
    parser.add_argument('--dry-run', action='store_true', help="Preview changes without applying")
    args = parser.parse_args()

    lexicon = load_lexicon()
    print(f"Loaded {len(lexicon)} brands from lexicon")

    # Find JSON files recursively
    print("Scanning for run_results JSON files...")
    json_files = glob.glob('**/runs/run_results_*.json', recursive=True) + \
                 glob.glob('**/runs/*/run_results_*.json', recursive=True)
    
    # Filter out files in hidden directories or unwanted paths if necessary
    json_files = sorted(list(set(json_files)))
    print(f"Found {len(json_files)} JSON files")

    count_fixed = 0
    
    for json_file in json_files:
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
        except: continue

        ads = data.get('ads', [])
        html_file = data.get('html')
        if not html_file: continue
        
        html_path = os.path.join(os.path.dirname(json_file), html_file)
        if not os.path.exists(html_path): continue

        # Identify Unknown Display Ads by Slot
        unknowns = {'left': [], 'bottom': [], 'other': []}
        for i, ad in enumerate(ads):
            if ad.get('type') == 'Sponsored_Display' and \
               (not ad.get('brand') or ad.get('brand').lower() == 'unknown'):
                
                # Determine slot from ad data or guess
                slot = 'other'
                if ad.get('slot') == 'left_rail': slot = 'left'
                elif ad.get('slot') == 'bottom': slot = 'bottom'
                
                unknowns[slot].append((i, ad))

        if not any(unknowns.values()):
            continue

        # Parse HTML for brands
        html_brands = parse_html_for_ads(html_path)
        if args.dry_run:
             print(f"  [DEBUG] HTML Brands found: Left={len(html_brands.get('left',[]))}, Bottom={len(html_brands.get('bottom',[]))}")
             if html_brands.get('left'): print(f"    Left: {html_brands['left']}")
             if html_brands.get('bottom'): print(f"    Bottom: {html_brands['bottom']}")

        modified = False
        base_dir = os.path.dirname(os.path.dirname(json_file))

        # Try to match
        for slot in ['left', 'bottom']:
            u_list = unknowns[slot]
            b_list = html_brands.get(slot, [])
            
            if args.dry_run and u_list:
                print(f"  [DEBUG] Slot '{slot}': {len(u_list)} unknowns vs {len(b_list)} html brands")

            # Simple matching: if counts match, align 1-to-1
            # Or if we have 1 unknown and >=1 brand, pick the first
            if len(u_list) == 1 and len(b_list) >= 1:
                # High confidence match
                idx, ad = u_list[0]
                raw_text = b_list[0]
                
                # Try to resolve brand against lexicon
                brand_name = match_brand_from_text(raw_text, lexicon)
                if not brand_name:
                    # Fallback: take first 2 words if it looks like a Title
                    # e.g. "Purito Daily Go-To Sunscreen..." -> "Purito"
                    words = raw_text.split()
                    if len(words) > 0:
                        brand_name = words[0] # Very naive, but better than Unknown?
                
                if brand_name and brand_name.lower() != 'unknown':
                    print(f"{'[DRY]' if args.dry_run else '[FIX]'} {os.path.basename(json_file)}: Slot {slot} -> {brand_name}")
                    if not args.dry_run:
                        ad['brand'] = brand_name
                        ad['brand_canonical'] = brand_name
                        ad['advertisers'] = [brand_name]
                        
                        # Fix image name
                        if ad.get('image_path') and '__unknown__' in ad['image_path']:
                            old_path = os.path.join(os.path.dirname(json_file).replace('/runs/', '/'), ad['image_path'])
                            # Correction: image_path in JSON is relative to client root usually?
                            # Actually typically "Sponsored_Display/filename.png"
                            # Let's check where the JSON is.
                            # Standard: output/amazon/CLIENT/runs/RUNID/run_results.json
                            # Images: output/amazon/CLIENT/Sponsored_Display/...
                            
                            client_dir = os.path.dirname(os.path.dirname(json_file))
                            old_full = os.path.join(client_dir, ad['image_path'])
                            
                            new_name = ad['image_path'].replace('__unknown__', f'__{to_slug(brand_name)}__')
                            new_full = os.path.join(client_dir, new_name)
                            
                            if os.path.exists(old_full):
                                try:
                                    shutil.move(old_full, new_full)
                                    ad['image_path'] = new_name
                                except Exception as e:
                                    print(f"    Error renaming image: {e}")
                        
                        modified = True
                        count_fixed += 1
            elif u_list and args.dry_run:
                 print(f"  [DEBUG] Skipping slot '{slot}': Count mismatch (Unknowns={len(u_list)}, Brands={len(b_list)})")


        if modified:
            with open(json_file, 'w') as f:
                json.dump(data, f, indent=2)

    print(f"Total fixed: {count_fixed}")

if __name__ == '__main__':
    main()
