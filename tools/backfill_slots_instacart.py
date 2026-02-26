#!/usr/bin/env python3
"""
Instacart slot backfill: parse saved HTML to reconstruct true page order,
match each DOM slot to its corresponding JSON ad, and assign:
  - slot              (int) : 0-based global page position
  - slot_within_type  (int) : 0-based position within ads of the same type
  - total_slots       (int) : total number of slots on the page
  - total_slots_of_type (int) : total slots of this ad type on the page

Instacart page structure (DOM order):
  - shoppable-list-sliding-carousel  → Shoppable_Display_Ad / Shoppable_Video_Ad
    - Contains item_list_item_* children (carousel product items)
  - item_list_item_* NOT inside carousel → Product_Listing (organic)

Each shoppable carousel maps to one JSON ad (display or video).
Carousel items are expanded into individual slots under the parent ad.

Usage:
    python3 tools/backfill_slots_instacart.py --preview <json_path>
    python3 tools/backfill_slots_instacart.py --dry-run
    python3 tools/backfill_slots_instacart.py
"""

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict
from bs4 import BeautifulSoup


# ── HTML / JSON file matching ─────────────────────────────────────────────────

def _normalize_timestamp(ts_str):
    """Normalize a timestamp string to compact 14-digit form."""
    digits = re.sub(r'[^0-9]', '', ts_str)
    return digits[:14] if len(digits) >= 14 else digits


def _find_html_for_json(json_path):
    """Find the HTML file that corresponds to a given Instacart JSON run file."""
    dirname = os.path.dirname(json_path)
    basename = os.path.basename(json_path)

    m = re.search(r'(\d{14})', basename)
    if not m:
        m = re.search(r'(\d{8}_?\d{6})', basename)
    if not m:
        return None

    ts_compact = _normalize_timestamp(m.group(1))

    # Search in same directory
    try:
        for f in os.listdir(dirname):
            if not f.endswith('.html'):
                continue
            if 'search_results' in f and ts_compact in _normalize_timestamp(f):
                full = os.path.join(dirname, f)
                if os.path.getsize(full) > 1000:
                    return full
    except OSError:
        pass

    # Check parent directory
    parent = os.path.dirname(dirname)
    try:
        for f in os.listdir(parent):
            if not f.endswith('.html'):
                continue
            if 'search_results' in f and ts_compact in _normalize_timestamp(f):
                full = os.path.join(parent, f)
                if os.path.getsize(full) > 1000:
                    return full
    except OSError:
        pass

    return None


# ── HTML Parsing ──────────────────────────────────────────────────────────────

def _extract_item_detail(item_element):
    """Extract product detail from an Instacart item_list_item element."""
    detail = {}

    tid = item_element.get('data-testid', '')
    detail['testid'] = tid

    # Product ID from href
    link = item_element.select_one('a[href*="/products/"]')
    href = link.get('href', '') if link else ''
    detail['href'] = href
    m = re.search(r'/products/(\d+)', href)
    detail['product_id'] = m.group(1) if m else ''

    # Title from button aria-label: "Add N item <title>"
    btn = item_element.select_one('button[aria-label*="Add"]')
    title = ''
    if btn:
        aria = btn.get('aria-label', '')
        m = re.match(r'Add \d+ item (.+)', aria)
        if m:
            title = m.group(1)
    detail['title'] = title

    # Price from text
    text = item_element.get_text(strip=True)
    price_match = re.search(r'\$(\d+\.\d{2})', text)
    detail['price'] = price_match.group(0) if price_match else ''

    # Image from srcset
    img = item_element.select_one('img')
    image_url = ''
    if img:
        srcset = img.get('srcset', '')
        if srcset:
            image_url = srcset.split(',')[0].split(' ')[0]
        elif img.get('src'):
            image_url = img.get('src', '')
    detail['image_url'] = image_url

    # Review count
    rating_match = re.search(r'\((\d+\.?\d*K?)\)', text)
    detail['review_count'] = rating_match.group(1) if rating_match else ''

    # Size/weight
    size_match = re.search(r'(\d+\.?\d*\s*(?:oz|fl oz|lb|ct|g|ml|L|pk|pack))', text)
    detail['size'] = size_match.group(1) if size_match else ''

    return detail


def _is_inside_carousel(element):
    """Check if an element is inside a shoppable-list-sliding-carousel."""
    parent = element.parent
    for _ in range(15):
        if parent is None:
            return False, None
        if parent.get('data-testid') == 'shoppable-list-sliding-carousel':
            return True, parent
        parent = parent.parent
    return False, None


def parse_instacart_html(html_path):
    """
    Parse an Instacart search results HTML file and return a list of slots
    in true DOM order.
    """
    with open(html_path, 'r', encoding='utf-8', errors='replace') as f:
        soup = BeautifulSoup(f, 'html.parser')

    html_str = str(soup)

    # Collect all shoppable carousels and their positions
    carousels = soup.select('[data-testid="shoppable-list-sliding-carousel"]')
    carousel_positions = []
    for car in carousels:
        # Use a unique snippet for position
        car_id_str = str(car)[:120]
        pos = html_str.find(car_id_str)
        carousel_positions.append((pos, car))

    # Collect all item_list_item elements
    items = soup.find_all(attrs={'data-testid': re.compile(r'^item_list_item_')})

    # Separate items into carousel items and organic items
    carousel_item_groups = defaultdict(list)  # carousel_id -> [item_detail]
    organic_items = []  # [(pos, item_detail)]

    for item in items:
        inside, carousel_parent = _is_inside_carousel(item)
        detail = _extract_item_detail(item)

        if inside and carousel_parent is not None:
            carousel_item_groups[id(carousel_parent)].append(detail)
        else:
            snippet = str(item)[:80]
            pos = html_str.find(snippet)
            organic_items.append((pos, detail))

    # Build slot list in DOM order
    # Carousels come first (each expanded into individual item slots),
    # then organic items
    candidates = []

    for pos, car in carousel_positions:
        car_items = carousel_item_groups.get(id(car), [])
        for item_detail in car_items:
            item_detail['is_sponsored'] = True
            candidates.append((pos, 'Shoppable_Ad_Item', item_detail))
        # Increment pos slightly for each item to maintain order within carousel
        pos += 1

    for pos, detail in organic_items:
        detail['is_sponsored'] = False
        candidates.append((pos, 'Product_Listing', detail))

    candidates.sort(key=lambda x: x[0])

    slots = []
    for pos, ad_type, detail in candidates:
        slots.append({
            'ad_type': ad_type,
            'detail': detail,
            'carousel_id': None,
        })

    # Tag carousel items with their carousel index for JSON matching
    carousel_idx = 0
    seen_carousels = set()
    for i, (pos, car) in enumerate(carousel_positions):
        car_obj_id = id(car)
        if car_obj_id not in seen_carousels:
            seen_carousels.add(car_obj_id)
            # Mark all slots from this carousel
            for slot in slots:
                if slot['ad_type'] == 'Shoppable_Ad_Item':
                    detail = slot['detail']
                    # Check if this item belongs to this carousel
                    if detail.get('testid', '') in [
                        it.get('data-testid', '')
                        for it in car.find_all(attrs={'data-testid': re.compile(r'^item_list_item_')})
                    ]:
                        if slot['carousel_id'] is None:
                            slot['carousel_id'] = carousel_idx
            carousel_idx += 1

    return slots


# ── JSON Matching ─────────────────────────────────────────────────────────────

def match_slots_to_json(slots, json_ads):
    """Match HTML-derived slots to JSON ad objects."""
    # Instacart JSON ads are Shoppable_Display_Ad and Shoppable_Video_Ad
    shoppable_ads = [a for a in json_ads
                     if a.get('type') in ('Shoppable_Display_Ad', 'Shoppable_Video_Ad')]

    results = []

    for slot in slots:
        ad_type = slot['ad_type']
        matched = None

        if ad_type == 'Shoppable_Ad_Item':
            car_idx = slot.get('carousel_id')
            if car_idx is not None and car_idx < len(shoppable_ads):
                matched = shoppable_ads[car_idx]

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

    slots = parse_instacart_html(html_path)
    print("HTML slots: %d" % len(slots))
    print()

    matched_results = match_slots_to_json(slots, json_ads)

    type_counts = Counter(s['ad_type'] for s, _ in matched_results)
    type_running = Counter()
    total_slots = len(matched_results)

    hdr = "%4s  %-22s  %4s  %5s  %7s  %7s  %4s  %s" % (
        'slot', 'type', 'w/in', 'total', 'of_type', 'match', 'car#', 'detail')
    print(hdr)
    print("-" * 140)

    for i, (slot, json_ad) in enumerate(matched_results):
        ad_type = slot['ad_type']
        within = type_running[ad_type]
        type_running[ad_type] += 1
        of_type = type_counts[ad_type]
        match_str = "YES" if json_ad else "---"
        car_idx = slot.get('carousel_id', '')
        car_str = str(car_idx) if car_idx is not None else ''

        detail = slot['detail']
        if ad_type == 'Shoppable_Ad_Item':
            brand = ''
            if json_ad:
                brand = json_ad.get('brand', '')
            detail_str = "[%s] pid=%-10s  %6s  %s" % (
                brand, detail.get('product_id', ''),
                detail.get('price', ''), detail.get('title', '')[:50])
        elif ad_type == 'Product_Listing':
            detail_str = "[OR] pid=%-10s  %6s  %s" % (
                detail.get('product_id', ''),
                detail.get('price', ''), detail.get('title', '')[:50])
        else:
            detail_str = ''

        print("%4d  %-22s  %4d  %5d  %7d  %7s  %4s  %s" % (
            i, ad_type, within, total_slots, of_type, match_str, car_str, detail_str))

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
            print("  %-25s  brand=%s" % (a.get('type', '?'), a.get('brand', '?')))


# ── Backfill ──────────────────────────────────────────────────────────────────

def _build_slots_array(matched_results, json_ads):
    """Build a serializable slots array from matched_results for persisting in JSON.

    Every entry gets:
      slot, slot_within_type, total_slots, total_slots_of_type,
      ad_type, is_sponsored, product_id, title, price, image_url, image_path,
      brand, href, matched_ad_index

    image_path points to assets/instacart/product_images/<product_id>.<ext> —
    downloaded on first encounter, re-linked on subsequent appearances of the
    same product_id (same product can appear multiple times on one page).
    Note: Instacart images may require auth cookies; download_and_store will
    skip gracefully if the CDN URL returns a non-200 response.
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

        product_id = d.get('product_id', '')
        image_url  = d.get('image_url', '')

        # Resolve canonical image path — download once, re-link on duplicates
        image_path = None
        if _img_store and product_id:
            if product_id in _image_cache:
                image_path = _image_cache[product_id]
            elif has_image('instacart', product_id):
                image_path = get_image_path('instacart', product_id)
                _image_cache[product_id] = image_path
            elif image_url:
                image_path = download_and_store('instacart', product_id, image_url)
                _image_cache[product_id] = image_path

        entry = {
            'slot': i,
            'slot_within_type': within,
            'total_slots': total_slots,
            'total_slots_of_type': type_counts[ad_type],
            'ad_type': ad_type,
            'is_sponsored': ad_type in ('Shoppable_Ad_Item', 'Shoppable_Display_Ad', 'Shoppable_Video_Ad'),
            'product_id': product_id,
            'title': d.get('title', ''),
            'price': d.get('price', ''),
            'image_url': image_url,
            'image_path': image_path,
            'href': d.get('href', ''),
            'brand': d.get('brand'),
            'matched_ad_index': ads_index_map.get(id(json_ad)) if json_ad else None,
        }
        if slot.get('carousel_index') is not None:
            entry['carousel_index'] = slot['carousel_index']
        if json_ad and not entry['brand']:
            entry['brand'] = json_ad.get('brand', json_ad.get('brand_name'))
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
            'subtype': 'organic_product',
            'product_id': d.get('product_id', ''),
            'retailer_id_type': 'instacart_product_id',
            'title': d.get('title', ''),
            'brand': None,
            'price': d.get('price', ''),
            'image_url': d.get('image_url', ''),
            'href': d.get('href', ''),
            'size': d.get('size', ''),
            'is_sponsored': False,
            'position': d.get('grid_position', -1),
        })
    return listings


def process_file(json_path, dry_run=False):
    """Process a single Instacart run JSON + its HTML."""
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
        slots = parse_instacart_html(html_path)
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
    """Run backfill across all Instacart JSON files."""
    base = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "output", "instacart")
    if not os.path.isdir(base):
        print("ERROR: Instacart output directory not found: %s" % base)
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
    print("\n%s (Instacart):" % mode)
    print("  Files scanned:    %d" % total_files)
    print("  Files changed:    %d" % files_changed)
    print("  Files no HTML:    %d" % files_no_html)
    print("  Files with error: %d" % total_errors)
    print("  Total HTML slots: %d" % total_slots)
    print("  JSON ads assigned:%d" % total_assigned)
    print("  Unmatched slots:  %d" % total_unmatched)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Instacart slot backfill from saved HTML")
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
