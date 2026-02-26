#!/usr/bin/env python3
"""
Kroger slot backfill: parse saved HTML to reconstruct true page order,
match each DOM slot to its corresponding JSON ad, and assign:
  - slot              (int) : 0-based global page position
  - slot_within_type  (int) : 0-based position within ads of the same type
  - total_slots       (int) : total number of slots on the page
  - total_slots_of_type (int) : total slots of this ad type on the page

Kroger page structure (DOM order via data-testid):
  - StandardTOA              → TOA (Top of Aisle banner)
  - SkyscraperTOA            → Skyscraper (sidebar display ad)
  - product-card-N           → Product_Listing (organic or sponsored)
  - curated-carousel         → CuratedCarousel (expand each card as its own slot)
    └ carousel-product-card-N  (individual cards inside carousel)

All elements are walked in DOM order — no assumptions about fixed layout.

Usage:
    python3 tools/backfill_slots_kroger.py --preview <json_path>
    python3 tools/backfill_slots_kroger.py --dry-run
    python3 tools/backfill_slots_kroger.py
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
    """
    Normalize a timestamp string to compact 14-digit form.
    Handles:  20251125123300  or  2025-11-25_12-33-00  or  2025-12-04_20-13-00
    """
    digits = re.sub(r'[^0-9]', '', ts_str)
    return digits[:14] if len(digits) >= 14 else digits


def _find_html_for_json(json_path):
    """
    Find the HTML file that corresponds to a given Kroger JSON run file.
    JSON names:  run_results_<ts>.json  or  run_results_<kw>_<ts>.json
    HTML names:  search_results_<kw>_<ts>.html
    Timestamps may be compact (20251125123300) or dashed (2025-11-25_12-33-00).
    """
    dirname = os.path.dirname(json_path)
    basename = os.path.basename(json_path)

    # Extract timestamp — try compact first, then dashed
    m = re.search(r'(\d{14})', basename)
    if m:
        ts_compact = m.group(1)
    else:
        m = re.search(r'(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})', basename)
        if m:
            ts_compact = _normalize_timestamp(m.group(1))
        else:
            return None

    # Search for HTML with matching timestamp (either format)
    try:
        for f in os.listdir(dirname):
            if not f.endswith('.html'):
                continue
            f_ts = _normalize_timestamp(f)
            if ts_compact in f_ts or f_ts in ts_compact:
                full = os.path.join(dirname, f)
                if os.path.getsize(full) > 1000:
                    return full
    except OSError:
        pass

    # Check timestamp subdirectory
    ts_dir = os.path.join(dirname, ts_compact)
    if os.path.isdir(ts_dir):
        for f in os.listdir(ts_dir):
            if f.endswith('.html') and 'search_results' in f:
                return os.path.join(ts_dir, f)

    return None


# ── HTML Parsing ──────────────────────────────────────────────────────────────

_SLOT_TESTID_RE = re.compile(
    r'^(product-card-\d+|carousel-product-card-\d+|curated-carousel|StandardTOA|SkyscraperTOA)$'
)


def _extract_product_detail(card_element):
    """Extract detail from a Kroger product card (product-card-N)."""
    detail = {}

    testid = card_element.get('data-testid', '')
    m = re.search(r'(\d+)$', testid)
    detail['grid_position'] = int(m.group(1)) if m else -1

    # Title
    title_el = card_element.select_one('[data-testid="cart-page-item-description"]')
    detail['title'] = title_el.get_text(strip=True)[:120] if title_el else ''

    # Price
    price_el = card_element.select_one(
        '[data-testid="price-heading-tag"], [class*="kds-Price"]'
    )
    detail['price'] = price_el.get_text(strip=True)[:30] if price_el else ''

    # Image
    img_el = card_element.select_one(
        'img[data-testid="product-image-loaded"], img[data-testid="product-image"]'
    )
    detail['image_url'] = img_el.get('src', '') if img_el else ''

    # Product link → extract UPC
    link_el = card_element.select_one('a[href*="/p/"]')
    href = link_el.get('href', '') if link_el else ''
    detail['href'] = href
    upc_match = re.search(r'/(\d{10,})', href)
    detail['upc'] = upc_match.group(1) if upc_match else ''

    # Sponsored?
    detail['is_sponsored'] = 'Sponsored' in card_element.get_text()

    return detail


def _extract_carousel_cards(carousel_element):
    """
    Extract individual card details from a Kroger CuratedCarousel.
    Returns a list of dicts, one per card.
    """
    header_el = carousel_element.select_one('[data-testid="carousel-featured-flag"]')
    header = header_el.get_text(strip=True) if header_el else ''

    cards = carousel_element.find_all(
        attrs={'data-testid': re.compile(r'^carousel-product-card-\d+$')}
    )
    total_cards = len(cards)
    results = []

    for idx, card in enumerate(cards):
        detail = {}
        detail['carousel_header'] = header
        detail['card_index'] = idx
        detail['total_cards_in_carousel'] = total_cards

        # Title
        title_el = card.select_one('[data-testid="cart-page-item-description"]')
        detail['title'] = title_el.get_text(strip=True)[:120] if title_el else ''

        # Price
        price_el = card.select_one('[data-testid="price-heading-tag"]')
        detail['price'] = price_el.get_text(strip=True)[:30] if price_el else ''

        # Image
        img_el = card.select_one(
            'img[data-testid="product-image-loaded"], img[data-testid="product-image"]'
        )
        detail['image_url'] = img_el.get('src', '') if img_el else ''

        # Link → UPC
        link_el = card.select_one('a[href*="/p/"]')
        href = link_el.get('href', '') if link_el else ''
        detail['href'] = href
        upc_match = re.search(r'/(\d{10,})', href)
        detail['upc'] = upc_match.group(1) if upc_match else ''

        results.append(detail)

    return results


def _extract_toa_detail(toa_element):
    """Extract detail from a Kroger TOA (Top of Aisle) banner."""
    detail = {}
    img = toa_element.select_one('img[src*="monetization"]')
    detail['image_url'] = img.get('src', '') if img else ''
    link = toa_element.select_one('a[href]')
    detail['href'] = link.get('href', '')[:200] if link else ''
    return detail


def _extract_skyscraper_detail(sky_element):
    """Extract detail from a Kroger Skyscraper ad."""
    detail = {}
    img = sky_element.select_one('img[src*="monetization"]')
    detail['image_url'] = img.get('src', '') if img else ''
    link = sky_element.select_one('a[href]')
    detail['href'] = link.get('href', '')[:200] if link else ''
    return detail


def parse_kroger_html(html_path):
    """
    Parse a Kroger search results HTML file and return a list of slots
    in true DOM order. Each slot is a dict with ad_type and detail.
    """
    with open(html_path, 'r', encoding='utf-8', errors='replace') as f:
        soup = BeautifulSoup(f, 'html.parser')

    all_elements = soup.find_all(attrs={'data-testid': _SLOT_TESTID_RE})

    slots = []
    for el in all_elements:
        tid = el.get('data-testid', '')

        # Skip carousel card elements — handled when we hit their parent
        if tid.startswith('carousel-product-card-'):
            continue

        if tid == 'StandardTOA':
            detail = _extract_toa_detail(el)
            slots.append({'ad_type': 'TOA', 'detail': detail})

        elif tid == 'SkyscraperTOA':
            detail = _extract_skyscraper_detail(el)
            slots.append({'ad_type': 'Skyscraper', 'detail': detail})

        elif tid == 'curated-carousel':
            card_details = _extract_carousel_cards(el)
            for card_detail in card_details:
                slots.append({'ad_type': 'CuratedCarousel', 'detail': card_detail})

        elif tid.startswith('product-card-'):
            detail = _extract_product_detail(el)
            slots.append({'ad_type': 'Product_Listing', 'detail': detail})

    return slots


# ── JSON Matching ─────────────────────────────────────────────────────────────

def _get_kroger_ads(data):
    """Extract ads from Kroger JSON (may be nested in results[0].ads or top-level)."""
    ads = list(data.get('ads', []))
    for r in data.get('results', []):
        ads.extend(r.get('ads', []))
    return ads


def match_slots_to_json(slots, json_ads):
    """
    Match HTML-derived slots to JSON ad objects.
    Returns list of (slot_dict, matched_json_ad_or_None) in page order.
    """
    toa_ads = [a for a in json_ads if a.get('type') == 'TOA']
    sky_ads = [a for a in json_ads if a.get('type') == 'Skyscraper']
    carousel_ads = [a for a in json_ads if a.get('type') == 'CuratedCarousel']

    toa_idx = 0
    sky_idx = 0
    carousel_idx = 0
    last_carousel_header = None

    results = []

    for slot in slots:
        ad_type = slot['ad_type']
        matched = None

        if ad_type == 'TOA':
            if toa_idx < len(toa_ads):
                matched = toa_ads[toa_idx]
                toa_idx += 1

        elif ad_type == 'Skyscraper':
            if sky_idx < len(sky_ads):
                matched = sky_ads[sky_idx]
                sky_idx += 1

        elif ad_type == 'CuratedCarousel':
            # All cards from the same carousel share the same JSON ad.
            # Advance index only when carousel_header changes.
            this_header = slot['detail'].get('carousel_header', '')
            if this_header != last_carousel_header:
                carousel_idx += 1
                last_carousel_header = this_header
            idx = carousel_idx - 1
            if 0 <= idx < len(carousel_ads):
                matched = carousel_ads[idx]

        elif ad_type == 'Product_Listing':
            # Kroger JSON doesn't store individual product listings —
            # these are HTML-only slots with no JSON match.
            matched = None

        results.append((slot, matched))

    return results


# ── Slot Assignment ───────────────────────────────────────────────────────────

def assign_slot_fields(matched_results):
    """
    Compute and assign slot fields to matched JSON ads.
    Returns (total_assigned, total_unmatched).
    """
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
    json_ads = _get_kroger_ads(data)

    print("JSON:  %s" % json_path)
    print("HTML:  %s" % html_path)
    print("JSON ads: %d" % len(json_ads))
    print()

    slots = parse_kroger_html(html_path)
    print("HTML slots: %d" % len(slots))
    print()

    matched_results = match_slots_to_json(slots, json_ads)

    type_counts = Counter(s['ad_type'] for s, _ in matched_results)
    type_running = Counter()
    total_slots = len(matched_results)

    hdr = "%4s  %-20s  %4s  %5s  %7s  %7s  %s" % (
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
        if ad_type == 'Product_Listing':
            sp = "SP" if detail.get('is_sponsored') else "OR"
            detail_str = "[%s] %-15s  %12s  %s" % (
                sp, detail.get('upc', ''), detail.get('price', ''), detail.get('title', ''))
        elif ad_type == 'CuratedCarousel':
            ci = detail.get('card_index', 0)
            tc = detail.get('total_cards_in_carousel', 0)
            detail_str = "[%s] card %d/%d  %-15s  %8s  %s" % (
                detail.get('carousel_header', ''), ci + 1, tc,
                detail.get('upc', ''), detail.get('price', ''), detail.get('title', ''))
        elif ad_type == 'TOA':
            advertisers = ''
            if json_ad:
                advertisers = ', '.join(json_ad.get('advertisers', []))
            detail_str = "%s  %s" % (advertisers, detail.get('href', '')[:60])
        elif ad_type == 'Skyscraper':
            advertisers = ''
            if json_ad:
                advertisers = ', '.join(json_ad.get('advertisers', []))
            detail_str = "%s  %s" % (advertisers, detail.get('href', '')[:60])
        else:
            detail_str = ''

        print("%4d  %-20s  %4d  %5d  %7d  %7s  %s" % (
            i, ad_type, within, total_slots, of_type, match_str, detail_str))

    total_matched = sum(1 for _, m in matched_results if m)
    print()
    print("Total slots: %d" % total_slots)
    print("Type counts: %s" % dict(type_counts))
    print("Matched: %d/%d" % (total_matched, total_slots))

    # Show unmatched JSON ads
    matched_ids = set(id(m) for _, m in matched_results if m)
    unmatched_json = [a for a in json_ads if id(a) not in matched_ids]
    if unmatched_json:
        print("\nUnmatched JSON ads (%d):" % len(unmatched_json))
        for a in unmatched_json:
            t = a.get('type', '?')
            advs = ', '.join(a.get('advertisers', []))
            print("  %-20s  advertisers=%s" % (t, advs))


# ── Backfill ──────────────────────────────────────────────────────────────────

def _build_slots_array(matched_results, json_ads):
    """Build a serializable slots array from matched_results for persisting in JSON.

    Every entry gets:
      slot, slot_within_type, total_slots, total_slots_of_type,
      ad_type, is_sponsored, product_id, title, price, image_url, image_path,
      brand, href, matched_ad_index

    image_path points to assets/kroger/product_images/<upc>.<ext> —
    downloaded on first encounter, re-linked on subsequent appearances of the
    same upc (same product can appear multiple times on one page).
    """
    try:
        from tools.product_image_store import download_and_store, get_image_path, has_image
        _img_store = True
    except ImportError:
        _img_store = False

    ads_index_map = {id(a): i for i, a in enumerate(json_ads)}
    total_slots = len(matched_results)

    type_counts = Counter(slot['ad_type'] for slot, _ in matched_results)
    type_running = Counter()
    # Cache product_id → image_path within this run (avoids re-downloading duplicates)
    _image_cache = {}

    slots_out = []
    for i, (slot, json_ad) in enumerate(matched_results):
        d = slot['detail']
        ad_type = slot['ad_type']
        within = type_running[ad_type]
        type_running[ad_type] += 1

        product_id = d.get('upc', '')
        image_url  = d.get('image_url', '')

        # Resolve canonical image path — download once, re-link on duplicates
        image_path = None
        if _img_store and product_id:
            if product_id in _image_cache:
                image_path = _image_cache[product_id]
            elif has_image('kroger', product_id):
                image_path = get_image_path('kroger', product_id)
                _image_cache[product_id] = image_path
            elif image_url:
                image_path = download_and_store('kroger', product_id, image_url)
                _image_cache[product_id] = image_path

        entry = {
            'slot': i,
            'slot_within_type': within,
            'total_slots': total_slots,
            'total_slots_of_type': type_counts[ad_type],
            'ad_type': ad_type,
            'is_sponsored': d.get('is_sponsored', ad_type in ('TOA', 'Skyscraper', 'CuratedCarousel')),
            'product_id': product_id,
            'title': d.get('title', ''),
            'price': d.get('price', ''),
            'image_url': image_url,
            'image_path': image_path,
            'href': d.get('href', ''),
            'brand': None,
            'matched_ad_index': ads_index_map.get(id(json_ad)) if json_ad else None,
        }
        if json_ad:
            entry['brand'] = ', '.join(json_ad.get('advertisers', [])) or json_ad.get('brand')
        slots_out.append(entry)
    return slots_out


def _build_product_listings(matched_results):
    """Convert Product_Listing slots to standardized product_listings dicts."""
    listings = []
    for slot, _ in matched_results:
        if slot['ad_type'] != 'Product_Listing':
            continue
        d = slot['detail']
        listings.append({
            'type': 'Product_Listing',
            'subtype': 'sponsored_product' if d.get('is_sponsored') else 'organic_product',
            'product_id': d.get('upc', ''),
            'retailer_id_type': 'upc',
            'title': d.get('title', ''),
            'brand': None,
            'price': d.get('price', ''),
            'image_url': d.get('image_url', ''),
            'href': d.get('href', ''),
            'is_sponsored': d.get('is_sponsored', False),
            'position': d.get('grid_position', -1),
        })
    return listings


def process_file(json_path, dry_run=False):
    """
    Process a single Kroger run JSON + its HTML.
    Returns (num_slots, num_assigned, num_unmatched, error_str|None).
    """
    html_path = _find_html_for_json(json_path)
    if not html_path:
        return 0, 0, 0, "no HTML found"

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return 0, 0, 0, "JSON parse error: %s" % e

    json_ads = _get_kroger_ads(data)

    try:
        slots = parse_kroger_html(html_path)
    except Exception as e:
        return 0, 0, 0, "HTML parse error: %s" % e

    if not slots:
        return 0, 0, 0, "no slots found in HTML"

    matched_results = match_slots_to_json(slots, json_ads)
    assigned, unmatched = assign_slot_fields(matched_results)

    # Build and inject the slots array (single source of truth for the full page)
    slots_array = _build_slots_array(matched_results, json_ads)
    changed = assigned > 0 or (slots_array and data.get('slots') != slots_array)
    if slots_array:
        data['slots'] = slots_array
    # Remove legacy product_listings — slots supersedes it
    if 'product_listings' in data:
        del data['product_listings']
        changed = True

    if changed and not dry_run:
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write("\n")
        except Exception as e:
            return len(slots), 0, 0, "write error: %s" % e

    return len(slots), assigned, unmatched, None


def backfill(dry_run=False, verbose=False):
    """Run backfill across all Kroger JSON files."""
    base = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "output", "kroger")
    if not os.path.isdir(base):
        print("ERROR: Kroger output directory not found: %s" % base)
        sys.exit(1)

    json_files = sorted(glob.glob(os.path.join(base, "**", "runs", "*.json"), recursive=True))
    json_files = [f for f in json_files if 'run_results' in os.path.basename(f)]

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
    print("\n%s (Kroger):" % mode)
    print("  Files scanned:    %d" % total_files)
    print("  Files changed:    %d" % files_changed)
    print("  Files no HTML:    %d" % files_no_html)
    print("  Files with error: %d" % total_errors)
    print("  Total HTML slots: %d" % total_slots)
    print("  JSON ads assigned:%d" % total_assigned)
    print("  Unmatched slots:  %d" % total_unmatched)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Kroger slot backfill from saved HTML")
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
