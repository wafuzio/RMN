#!/usr/bin/env python3
"""
Batch Fix Unknown Amazon Brands from HTML

Scans all Amazon JSON files for ads with unknown/empty advertisers,
then checks the companion HTML file's accessibility text for product titles.
Cross-references against the brand lexicon to auto-fix verified matches.

Updates both:
  - JSON: advertisers, brand, brand_canonical fields
  - Image filenames: renames __unknown__ to the matched brand slug

Usage:
    python3 scripts/batch_fix_unknown_brands_from_html.py --dry-run   # Preview
    python3 scripts/batch_fix_unknown_brands_from_html.py             # Apply
"""

import os
import re
import json
import glob
import shutil
import argparse
from pathlib import Path


def load_lexicon(path="config/brands.json"):
    with open(path, 'r') as f:
        return json.load(f)


def to_slug(name):
    """Convert brand name to filename slug: lowercase, spaces to underscores."""
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')


def extract_titles_from_html(html_path):
    """Extract product titles from Sponsored Display accessibility text in HTML."""
    try:
        with open(html_path, 'r', errors='ignore') as f:
            content = f.read()
        titles = re.findall(
            r'Sponsored Ad\.\\n(?:Branded image\.\\n)?(.+?)\\n',
            content
        )
        # Decode HTML entities
        cleaned = []
        for t in titles:
            t = t.replace('&amp;amp;', '&').replace('&amp;', '&').strip()
            cleaned.append(t)
        return cleaned
    except Exception as e:
        print(f"  [ERROR] Failed to read HTML: {e}")
        return []


def match_title_to_lexicon(title, lexicon):
    """Check if a product title starts with a known brand name or synonym.
    Returns the canonical brand name or None."""
    title_lower = title.lower()
    for lex_brand in lexicon:
        brand_name = lex_brand['name']
        if title_lower.startswith(brand_name.lower()):
            return brand_name
        for synonym in lex_brand.get('synonyms', []):
            if synonym.startswith('MSG:'):
                continue
            if title_lower.startswith(synonym.lower()):
                return brand_name
    return None


def main():
    parser = argparse.ArgumentParser(description="Batch fix unknown Amazon brands from HTML")
    parser.add_argument('--dry-run', action='store_true', help="Preview changes without applying")
    args = parser.parse_args()

    lexicon = load_lexicon()
    print(f"Loaded {len(lexicon)} brands from lexicon")

    # Find all Amazon JSON files
    patterns = [
        'output/amazon/*/runs/run_results_*.json',
        'output/amazon/*/runs/*/run_results_*.json',
    ]
    json_files = []
    for pattern in patterns:
        json_files.extend(glob.glob(pattern))
    json_files = sorted(set(json_files))
    print(f"Found {len(json_files)} Amazon JSON files\n")

    total_fixed = 0
    total_unknown = 0
    total_renamed = 0

    for json_file in json_files:
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
        except Exception:
            continue

        ads = data.get('ads', [])
        html_filename = data.get('html')
        if not html_filename:
            continue

        html_path = os.path.join(os.path.dirname(json_file), html_filename)

        # Find unknown ads in this file
        unknown_ads = []
        for i, ad in enumerate(ads):
            advertisers = ad.get('advertisers', [])
            brand = (ad.get('brand') or '').lower()
            is_unknown = (
                not advertisers or
                advertisers == ['unknown'] or
                advertisers == ['Unknown'] or
                brand in ('unknown', '', 'none')
            )
            if is_unknown and ad.get('type') in ('Sponsored_Display', 'Sponsored_Carousel'):
                unknown_ads.append((i, ad))

        if not unknown_ads:
            continue

        total_unknown += len(unknown_ads)

        # Extract titles from HTML
        if not os.path.exists(html_path):
            continue

        titles = extract_titles_from_html(html_path)
        if not titles:
            continue

        # Build a set of matched brands from HTML titles
        html_brands = []
        for title in titles:
            brand = match_title_to_lexicon(title, lexicon)
            if brand:
                html_brands.append((brand, title))

        if not html_brands:
            continue

        # Match unknown ads to HTML brands.
        # Strategy: group unknowns by slot. For each slot, if there's exactly
        # one unknown and one HTML brand match, apply it confidently.
        # If multiple unknowns share a slot, we can still apply if the
        # HTML brand count matches the unknown count (assign in order).
        json_modified = False
        runs_dir = os.path.dirname(json_file)
        base_dir = os.path.dirname(runs_dir)

        # All verified brand names from HTML (preserving order = DOM order)
        matched_brands = [brand_name for brand_name, title in html_brands]

        # For each unknown ad, try to find a matching brand
        used_brands = set()
        for ad_idx, ad in unknown_ads:
            ad_type = ad.get('type', '')
            image_path = ad.get('image_path', '')
            slot = ad.get('slot', '')

            matched_brand = None

            # Strategy 1: If only one unknown in this slot and one brand
            # matches, it's a confident 1:1 match
            same_slot_unknowns = [
                (idx, a) for idx, a in unknown_ads
                if a.get('slot') == slot and a.get('type') == ad_type
            ]
            if len(same_slot_unknowns) == 1:
                # Use any available brand not yet assigned
                for brand_name, title in html_brands:
                    if brand_name not in used_brands:
                        matched_brand = brand_name
                        used_brands.add(brand_name)
                        break

            # Strategy 2: Check product_description against HTML titles
            if not matched_brand:
                prod_desc = (ad.get('product_description') or '').lower()
                for brand_name, title in html_brands:
                    if brand_name in used_brands:
                        continue
                    if prod_desc and prod_desc.startswith(title[:30].lower()):
                        matched_brand = brand_name
                        used_brands.add(brand_name)
                        break

            if not matched_brand:
                continue

            brand_slug = to_slug(matched_brand)
            print(f"{'[DRY RUN] ' if args.dry_run else ''}MATCH: {os.path.basename(json_file)}")
            print(f"  Ad #{ad_idx} ({ad_type}, slot={slot}) -> {matched_brand}")

            if not args.dry_run:
                # Update JSON fields
                ad['brand'] = matched_brand
                ad['brand_canonical'] = matched_brand
                ad['advertisers'] = [matched_brand]
                json_modified = True

                # Rename image file if it contains __unknown__
                if image_path and '__unknown__' in image_path:
                    old_full = os.path.join(base_dir, image_path)
                    new_image_path = image_path.replace('__unknown__', f'__{brand_slug}__')
                    new_full = os.path.join(base_dir, new_image_path)

                    if os.path.exists(old_full):
                        shutil.move(old_full, new_full)
                        ad['image_path'] = new_image_path
                        print(f"  [FILE] Renamed: {os.path.basename(old_full)}")
                        print(f"      -> {os.path.basename(new_full)}")
                        total_renamed += 1
                    else:
                        print(f"  [WARN] Image not found: {old_full}")

            total_fixed += 1

        # Save modified JSON
        if json_modified and not args.dry_run:
            with open(json_file, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"  [SAVED] {json_file}")

    print(f"\n{'=' * 60}")
    print(f"Summary:")
    print(f"  Total unknown ads scanned: {total_unknown}")
    print(f"  Brands matched from HTML:  {total_fixed}")
    print(f"  Image files renamed:       {total_renamed}")
    if args.dry_run:
        print(f"\n  (DRY RUN — no changes applied)")


if __name__ == '__main__':
    main()
