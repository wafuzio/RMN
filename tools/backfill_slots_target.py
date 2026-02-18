#!/usr/bin/env python3
"""
Target slot backfill: parse saved HTML to reconstruct true page order,
match each DOM slot to its corresponding JSON ad, and assign:
  - slot              (int) : 0-based global page position
  - slot_within_type  (int) : 0-based position within ads of the same type
  - total_slots       (int) : total number of slots on the page
  - total_slots_of_type (int) : total slots of this ad type on the page

Target page structure (DOM order):
  - ProductCardVariantDefault with sponsoredText → Sponsored_Product
  - ProductCardVariantDefault without            → Product_Listing
  - iframe[title="3rd party ad content"]         → ListingPageBannerAd (SafeFrame display ads)
  - [data-test="sponsored-text"]                 → Sponsored_Logo
  - recommended-products-carousel (data-product-id) → Carousel items

All elements are walked in DOM order — no assumptions about fixed layout.

Usage:
    python3 tools/backfill_slots_target.py --preview <json_path>
    python3 tools/backfill_slots_target.py --dry-run
    python3 tools/backfill_slots_target.py
"""

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter
from bs4 import BeautifulSoup


# ── HTML / JSON file matching ─────────────────────────────────────────────────

def _normalize_timestamp(ts_str):
    """Normalize a timestamp string to compact 14-digit form."""
    digits = re.sub(r'[^0-9]', '', ts_str)
    return digits[:14] if len(digits) >= 14 else digits


def _find_html_for_json(json_path):
    """Find the HTML file that corresponds to a given Target JSON run file."""
    dirname = os.path.dirname(json_path)
    basename = os.path.basename(json_path)

    m = re.search(r'(\d{14})', basename)
    if m:
        ts_compact = m.group(1)
    else:
        m = re.search(r'(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})', basename)
        if m:
            ts_compact = _normalize_timestamp(m.group(1))
        else:
            return None

    try:
        for f in os.listdir(dirname):
            if not f.endswith('.html') or 'safeframe' in f:
                continue
            if 'search_results' in f and ts_compact in _normalize_timestamp(f):
                full = os.path.join(dirname, f)
                if os.path.getsize(full) > 1000:
                    return full
    except OSError:
        pass

    return None


# ── HTML Parsing ──────────────────────────────────────────────────────────────

def _extract_product_detail(card_element):
    """Extract product detail from a Target ProductCardVariantDefault element."""
    detail = {}

    # Title
    title_el = card_element.select_one('[data-test="@web/ProductCard/title"]')
    detail['title'] = title_el.get_text(strip=True)[:120] if title_el else ''

    # Brand
    brand_el = card_element.select_one('[data-test*="brand"]')
    detail['brand'] = brand_el.get_text(strip=True)[:60] if brand_el else ''

    # Price
    price_el = card_element.select_one(
        '[data-test="@web/Price/PriceStandard"], '
        '[data-test="@web/Price/PriceHandle"], '
        '[data-test="@web/Price/PriceAndPromoMinimal"]'
    )
    detail['price'] = price_el.get_text(strip=True)[:40] if price_el else ''

    # Image
    img_el = card_element.select_one(
        '[data-test="@web/ProductCard/ProductCardImage/primary"] img'
    )
    detail['image_url'] = img_el.get('src', '') if img_el else ''

    # Link / TCIN
    link_el = card_element.select_one('a[href*="/p/"]')
    href = link_el.get('href', '') if link_el else ''
    detail['href'] = href
    m = re.search(r'/A-(\d+)', href)
    detail['tcin'] = m.group(1) if m else ''

    # Sponsored?
    sp_el = card_element.select_one('[data-test="sponsoredText"]')
    detail['is_sponsored'] = sp_el is not None

    # Rating
    rating_el = card_element.select_one('[aria-label*="star"]')
    detail['rating'] = rating_el.get('aria-label', '')[:50] if rating_el else ''

    # Fulfillment
    ful_el = card_element.select_one(
        '[data-test="@web/ProductCard/ProductCardFulfillmentMessaging"]'
    )
    detail['fulfillment'] = ful_el.get_text(strip=True)[:60] if ful_el else ''

    return detail


def parse_target_html(html_path):
    """
    Parse a Target search results HTML file and return a list of slots
    in true DOM order.
    """
    with open(html_path, 'r', encoding='utf-8', errors='replace') as f:
        soup = BeautifulSoup(f, 'html.parser')

    html_str = str(soup)
    candidates = []  # (source_pos, ad_type, detail)

    # 1) Product cards (main grid)
    for card in soup.select('[data-test="@web/ProductCard/ProductCardVariantDefault"]'):
        snippet = str(card)[:80]
        pos = html_str.find(snippet)
        detail = _extract_product_detail(card)
        ad_type = 'Sponsored_Product' if detail['is_sponsored'] else 'Product_Listing'
        candidates.append((pos, ad_type, detail))

    # 2) SafeFrame display ad iframes
    for iframe in soup.select('iframe[title="3rd party ad content"]'):
        snippet = str(iframe)[:80]
        pos = html_str.find(snippet)
        iframe_id = iframe.get('id', '')
        src = iframe.get('src', '')[:200]
        candidates.append((pos, 'ListingPageBannerAd', {
            'iframe_id': iframe_id,
            'iframe_src': src,
        }))

    # 3) Sponsored logo sections
    for sp_logo in soup.select('[data-test="sponsored-text"]'):
        snippet = str(sp_logo)[:80]
        pos = html_str.find(snippet)
        # Look for associated image in parent
        parent = sp_logo.parent
        img = ''
        for _ in range(5):
            if parent:
                img_el = parent.select_one('img')
                if img_el:
                    img = img_el.get('src', '')
                    break
                parent = parent.parent
        candidates.append((pos, 'Sponsored_Logo', {
            'image_url': img,
        }))

    # Sort by DOM position
    candidates.sort(key=lambda x: x[0])

    slots = []
    for pos, ad_type, detail in candidates:
        slots.append({'ad_type': ad_type, 'detail': detail})

    return slots


# ── JSON Matching ─────────────────────────────────────────────────────────────

def match_slots_to_json(slots, json_ads):
    """Match HTML-derived slots to JSON ad objects."""
    banner_ads = [a for a in json_ads if a.get('type') == 'ListingPageBannerAd']
    logo_ads = [a for a in json_ads if a.get('type') == 'Sponsored_Logo']

    banner_idx = 0
    logo_idx = 0

    results = []

    for slot in slots:
        ad_type = slot['ad_type']
        matched = None

        if ad_type == 'ListingPageBannerAd':
            if banner_idx < len(banner_ads):
                matched = banner_ads[banner_idx]
                banner_idx += 1

        elif ad_type == 'Sponsored_Logo':
            if logo_idx < len(logo_ads):
                matched = logo_ads[logo_idx]
                logo_idx += 1

        elif ad_type in ('Sponsored_Product', 'Product_Listing'):
            matched = None

        results.append((slot, matched))

    return results


# ── Slot Assignment ───────────────────────────────────────────────────────────

def assign_slot_fields(matched_results):
    """Compute and assign slot fields to matched JSON ads."""
    total_slots = len(matched_results)
    type_counts = Counter(slot['ad_type'] for slot, _ in matched_results)
    type_running = Counter()
    assigned = 0
    unmatched = 0

    for global_idx, (slot, json_ad) in enumerate(matched_results):
        ad_type = slot['ad_type']
        within_type = type_running[ad_type]
        type_running[ad_type] += 1

        if json_ad is not None:
            json_ad['slot'] = global_idx
            json_ad['slot_within_type'] = within_type
            json_ad['total_slots'] = total_slots
            json_ad['total_slots_of_type'] = type_counts[ad_type]
            assigned += 1
        else:
            unmatched += 1

    return assigned, unmatched


# ── Preview ───────────────────────────────────────────────────────────────────

def preview_file(json_path):
    """Print a readable slot table for manual validation."""
    html_path = _find_html_for_json(json_path)
    if not html_path:
        print("ERROR: No HTML file found for %s" % json_path)
        return

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    json_ads = data.get('ads', [])

    print("JSON:  %s" % json_path)
    print("HTML:  %s" % html_path)
    print("JSON ads: %d" % len(json_ads))
    for a in json_ads:
        print("  %s: %s" % (a.get('type', '?'), a.get('brand', '?')))
    print()

    slots = parse_target_html(html_path)
    print("HTML slots: %d" % len(slots))
    print()

    matched_results = match_slots_to_json(slots, json_ads)

    type_counts = Counter(s['ad_type'] for s, _ in matched_results)
    type_running = Counter()
    total_slots = len(matched_results)

    hdr = "%4s  %-22s  %4s  %5s  %7s  %7s  %s" % (
        'slot', 'type', 'w/in', 'total', 'of_type', 'match', 'detail')
    print(hdr)
    print("-" * 140)

    for i, (slot, json_ad) in enumerate(matched_results):
        ad_type = slot['ad_type']
        within = type_running[ad_type]
        type_running[ad_type] += 1
        of_type = type_counts[ad_type]
        match_str = "YES" if json_ad else "---"

        detail = slot['detail']
        if ad_type in ('Product_Listing', 'Sponsored_Product'):
            sp = "SP" if detail.get('is_sponsored') else "OR"
            detail_str = "[%s] tcin=%-10s  %12s  %-15s  %s" % (
                sp, detail.get('tcin', ''), detail.get('price', ''),
                detail.get('brand', ''), detail.get('title', '')[:40])
        elif ad_type == 'ListingPageBannerAd':
            brand = ''
            if json_ad:
                brand = json_ad.get('brand', '')
            detail_str = "[Banner] %s  id=%s" % (brand, detail.get('iframe_id', '')[:40])
        elif ad_type == 'Sponsored_Logo':
            brand = ''
            if json_ad:
                brand = json_ad.get('brand', '')
            detail_str = "[Logo] %s" % brand
        else:
            detail_str = ''

        print("%4d  %-22s  %4d  %5d  %7d  %7s  %s" % (
            i, ad_type, within, total_slots, of_type, match_str, detail_str))

    total_matched = sum(1 for _, m in matched_results if m)
    print()
    print("Total slots: %d" % total_slots)
    print("Type counts: %s" % dict(type_counts))
    print("Matched: %d/%d" % (total_matched, total_slots))

    matched_ids = set(id(m) for _, m in matched_results if m)
    unmatched_json = [a for a in json_ads if id(a) not in matched_ids]
    if unmatched_json:
        print("\nUnmatched JSON ads (%d):" % len(unmatched_json))
        for a in unmatched_json:
            print("  %-20s  brand=%s" % (a.get('type', '?'), a.get('brand', '?')))


# ── Backfill ──────────────────────────────────────────────────────────────────

def _build_product_listings(matched_results):
    """Convert Product_Listing slots to standardized product_listings dicts."""
    listings = []
    for slot, _ in matched_results:
        if slot['ad_type'] not in ('Sponsored_Product', 'Product_Listing'):
            continue
        d = slot['detail']
        listings.append({
            'type': 'Product_Listing',
            'subtype': 'sponsored_product' if d.get('is_sponsored') else 'organic_product',
            'product_id': d.get('tcin', ''),
            'retailer_id_type': 'tcin',
            'title': d.get('title', ''),
            'brand': d.get('brand'),
            'price': d.get('price', ''),
            'image_url': d.get('image_url', ''),
            'href': d.get('href', ''),
            'rating': d.get('rating', ''),
            'is_sponsored': d.get('is_sponsored', False),
            'position': d.get('grid_position', -1),
        })
    return listings


def process_file(json_path, dry_run=False):
    """Process a single Target run JSON + its HTML."""
    html_path = _find_html_for_json(json_path)
    if not html_path:
        return 0, 0, 0, "no HTML found"

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return 0, 0, 0, "JSON parse error: %s" % e

    json_ads = data.get('ads', [])

    try:
        slots = parse_target_html(html_path)
    except Exception as e:
        return 0, 0, 0, "HTML parse error: %s" % e

    if not slots:
        return 0, 0, 0, "no slots found in HTML"

    matched_results = match_slots_to_json(slots, json_ads)
    assigned, unmatched = assign_slot_fields(matched_results)

    # Inject product listings from HTML
    product_listings = _build_product_listings(matched_results)
    changed = assigned > 0 or (product_listings and 'product_listings' not in data)
    if product_listings:
        data['product_listings'] = product_listings

    if changed and not dry_run:
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write("\n")
        except Exception as e:
            return len(slots), 0, 0, "write error: %s" % e

    return len(slots), assigned, unmatched, None


def backfill(dry_run=False, verbose=False):
    """Run backfill across all Target JSON files."""
    base = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "output", "target")
    if not os.path.isdir(base):
        print("ERROR: Target output directory not found: %s" % base)
        sys.exit(1)

    json_files = sorted(glob.glob(os.path.join(base, "**", "run_results_*.json"), recursive=True))

    total_files = 0
    total_slots = 0
    total_assigned = 0
    total_unmatched = 0
    total_errors = 0
    files_changed = 0
    files_no_html = 0

    for filepath in json_files:
        num_slots, num_assigned, num_unmatched, error = process_file(filepath, dry_run=dry_run)
        total_files += 1
        total_slots += num_slots
        total_assigned += num_assigned
        total_unmatched += num_unmatched

        if error:
            if error == "no HTML found":
                files_no_html += 1
            else:
                total_errors += 1
            if verbose:
                label = "SKIP" if error == "no HTML found" else "ERROR"
                print("  %s %s: %s" % (label, filepath, error))
        elif num_assigned > 0:
            files_changed += 1
            if verbose:
                print("  %s: %d slots, %d assigned, %d unmatched" % (
                    filepath, num_slots, num_assigned, num_unmatched))

    mode = "DRY RUN" if dry_run else "DONE"
    print("\n%s (Target):" % mode)
    print("  Files scanned:    %d" % total_files)
    print("  Files changed:    %d" % files_changed)
    print("  Files no HTML:    %d" % files_no_html)
    print("  Files with error: %d" % total_errors)
    print("  Total HTML slots: %d" % total_slots)
    print("  JSON ads assigned:%d" % total_assigned)
    print("  Unmatched slots:  %d" % total_unmatched)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Target slot backfill from saved HTML")
    parser.add_argument("--preview", type=str, metavar="JSON_PATH",
                        help="Preview slot readout for a single JSON file")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report changes without writing files")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print every file processed")
    args = parser.parse_args()

    if args.preview:
        preview_file(args.preview)
    else:
        backfill(dry_run=args.dry_run, verbose=args.verbose)


if __name__ == "__main__":
    main()
