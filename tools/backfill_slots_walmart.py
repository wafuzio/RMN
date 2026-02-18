#!/usr/bin/env python3
"""
Walmart slot backfill: parse saved HTML to reconstruct true page order,
match each DOM slot to its corresponding JSON ad, and assign:
  - slot              (int) : 0-based global page position
  - slot_within_type  (int) : 0-based position within ads of the same type
  - total_slots       (int) : total number of slots on the page
  - total_slots_of_type (int) : total slots of this ad type on the page

Walmart page structure (DOM order via data-item-id + plmt tracking):
  - Gallery_Cards iframe        → Gallery_Cards (banner ad, title="Walmart Advertisement")
  - SBA carousel items          → SBA (plmt=sb-search-top, outside stacks)
  - Sponsored Products          → Sponsored_Product (plmt=sp-search-middle, in grid)
  - Organic Product Listings    → Product_Listing (no sp/track link, in grid)
  - SBV carousel items          → SBV (plmt=sv-search-middle, with video)
  - Tile Takeover               → Tile_Takeover (full-width banner in grid)

All elements are walked in DOM order — no assumptions about fixed layout.

Usage:
    python3 tools/backfill_slots_walmart.py --preview <json_path>
    python3 tools/backfill_slots_walmart.py --dry-run
    python3 tools/backfill_slots_walmart.py
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
    """
    Find the HTML file that corresponds to a given Walmart JSON run file.
    Walmart stores HTML in various locations:
      - Same dir as JSON: search_results_<ts>.html
      - Timestamp subdir: <ts>/search_results_<ts>.html
      - Parent dir with keyword: search_results_<kw>_<ts>.html
    """
    dirname = os.path.dirname(json_path)
    basename = os.path.basename(json_path)

    # Extract timestamp
    m = re.search(r'(\d{14})', basename)
    if m:
        ts_compact = m.group(1)
    else:
        m = re.search(r'(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})', basename)
        if m:
            ts_compact = _normalize_timestamp(m.group(1))
        else:
            return None

    # Search in same directory
    try:
        for f in os.listdir(dirname):
            if not f.endswith('.html') or 'gallery_card' in f:
                continue
            if 'search_results' in f and ts_compact in _normalize_timestamp(f):
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

    # Check parent directory
    parent = os.path.dirname(dirname)
    try:
        for f in os.listdir(parent):
            if not f.endswith('.html') or 'gallery_card' in f:
                continue
            if 'search_results' in f and ts_compact in _normalize_timestamp(f):
                full = os.path.join(parent, f)
                if os.path.getsize(full) > 1000:
                    return full
    except OSError:
        pass

    return None


# ── HTML Parsing ──────────────────────────────────────────────────────────────

def _get_plmt(item_element):
    """Extract placement string from sp/track links inside a data-item-id element."""
    for link in item_element.select('a[href*="sp/track"]'):
        href = link.get('href', '')
        m = re.search(r'plmt=([^&]+)', href)
        if m:
            return m.group(1)
    return ''


def _extract_product_detail(item_element):
    """Extract product detail from a Walmart data-item-id element."""
    detail = {}

    detail['item_id'] = item_element.get('data-item-id', '')

    # Title
    title_el = item_element.select_one('[data-automation-id="product-title"]')
    detail['title'] = title_el.get_text(strip=True)[:120] if title_el else ''

    # Price
    price_el = item_element.select_one('[data-automation-id="product-price"]')
    raw_price = price_el.get_text(strip=True) if price_el else ''
    # Clean up Walmart's price format: "$474current price $4.74" → "$4.74"
    m = re.search(r'(\$[\d,.]+(?:\.\d{2})?)', raw_price)
    detail['price'] = m.group(1) if m else raw_price[:20]

    # Image
    img_el = item_element.select_one('img[src*="walmartimages"]')
    detail['image_url'] = img_el.get('src', '') if img_el else ''

    # Rating
    rating_el = item_element.select_one('[data-testid*="rating"], [aria-label*="star"]')
    if rating_el:
        detail['rating'] = rating_el.get('aria-label', rating_el.get_text(strip=True))[:40]
    else:
        detail['rating'] = ''

    # Link / product URL
    link_el = item_element.select_one('a[href*="/ip/"]')
    if link_el:
        detail['href'] = link_el.get('href', '')
        # Extract Walmart product ID from URL
        m = re.search(r'/(\d{5,})', detail['href'])
        detail['walmart_id'] = m.group(1) if m else ''
    else:
        detail['href'] = ''
        detail['walmart_id'] = ''

    # Fulfillment badge
    ful_el = item_element.select_one('[data-automation-id="fulfillment-badge"]')
    detail['fulfillment'] = ful_el.get_text(strip=True)[:40] if ful_el else ''

    return detail


def _classify_item(item_element):
    """Classify a data-item-id element by its placement tracking."""
    plmt = _get_plmt(item_element)
    if 'sb-search' in plmt:
        return 'SBA'
    elif 'sv-search' in plmt:
        return 'SBV'
    elif 'sp-search' in plmt:
        return 'Sponsored_Product'
    else:
        return 'Product_Listing'


def parse_walmart_html(html_path):
    """
    Parse a Walmart search results HTML file and return a list of slots
    in true DOM order.
    """
    with open(html_path, 'r', encoding='utf-8', errors='replace') as f:
        soup = BeautifulSoup(f, 'html.parser')

    slots = []

    # Walk all slot-relevant elements in DOM order.
    # We need to interleave: data-item-id elements, Gallery Card iframes, and video elements.
    # Strategy: collect all with their source positions, then sort.

    html_str = str(soup)

    candidates = []  # (source_pos, type, element)

    # 1) Gallery Card iframes
    for iframe in soup.select('iframe[title="Walmart Advertisement"]'):
        pos = html_str.find(str(iframe)[:80])
        candidates.append((pos, 'Gallery_Cards', iframe))

    # 2) All data-item-id elements
    for item in soup.find_all(attrs={'data-item-id': True}):
        item_snippet = str(item)[:80]
        pos = html_str.find(item_snippet)
        ad_type = _classify_item(item)
        candidates.append((pos, ad_type, item))

    # Sort by source position (DOM order)
    candidates.sort(key=lambda x: x[0])

    # Track SBA/SBV carousel grouping for JSON matching
    last_sba_group = []
    last_sbv_group = []

    for pos, ad_type, el in candidates:
        if ad_type == 'Gallery_Cards':
            detail = {}
            # Extract iframe src for reference
            detail['iframe_src'] = el.get('src', '')[:200]
            slots.append({'ad_type': 'Gallery_Cards', 'detail': detail})

        elif ad_type in ('SBA', 'SBV', 'Sponsored_Product', 'Product_Listing'):
            detail = _extract_product_detail(el)
            detail['plmt'] = _get_plmt(el)
            detail['is_sponsored'] = ad_type in ('SBA', 'SBV', 'Sponsored_Product')
            slots.append({'ad_type': ad_type, 'detail': detail})

    return slots


# ── JSON Matching ─────────────────────────────────────────────────────────────

def match_slots_to_json(slots, json_ads):
    """
    Match HTML-derived slots to JSON ad objects.
    Returns list of (slot_dict, matched_json_ad_or_None) in page order.
    """
    sba_ads = [a for a in json_ads if a.get('type') in ('SBA', 'sba')]
    sbv_ads = [a for a in json_ads if a.get('type') in ('SBV', 'sbv')]
    gc_ads = [a for a in json_ads if a.get('type') == 'Gallery_Cards']
    tt_ads = [a for a in json_ads if a.get('type') in ('Tile_Takeover', 'tile_takeover')]

    sba_idx = 0
    sbv_idx = 0
    gc_idx = 0
    last_sba_plmt_group = None
    last_sbv_plmt_group = None

    results = []

    for slot in slots:
        ad_type = slot['ad_type']
        matched = None

        if ad_type == 'SBA':
            # All SBA carousel items share the same JSON SBA ad
            # They all have plmt=sb-search-top
            if last_sba_plmt_group is None:
                last_sba_plmt_group = True
                if sba_idx < len(sba_ads):
                    matched = sba_ads[sba_idx]
                    # Don't increment — all SBA items share same ad
            else:
                if sba_idx < len(sba_ads):
                    matched = sba_ads[sba_idx]

        elif ad_type == 'SBV':
            # All SBV carousel items share the same JSON SBV ad
            if last_sbv_plmt_group is None:
                last_sbv_plmt_group = True
                if sbv_idx < len(sbv_ads):
                    matched = sbv_ads[sbv_idx]
            else:
                if sbv_idx < len(sbv_ads):
                    matched = sbv_ads[sbv_idx]

        elif ad_type == 'Gallery_Cards':
            if gc_idx < len(gc_ads):
                matched = gc_ads[gc_idx]
                gc_idx += 1

        elif ad_type in ('Sponsored_Product', 'Product_Listing'):
            # No JSON match for individual product listings
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

    slots = parse_walmart_html(html_path)
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
            detail_str = "[%s] %-15s  %8s  %s" % (
                sp, detail.get('item_id', ''), detail.get('price', ''),
                detail.get('title', ''))
        elif ad_type == 'SBA':
            brand = ''
            if json_ad:
                brand = json_ad.get('brand', '')
            detail_str = "[SBA carousel] %s  item=%s  %s" % (
                brand, detail.get('item_id', ''), detail.get('price', ''))
        elif ad_type == 'SBV':
            brand = ''
            if json_ad:
                brand = json_ad.get('brand', '')
            detail_str = "[SBV carousel] %s  item=%s  %s" % (
                brand, detail.get('item_id', ''), detail.get('price', ''))
        elif ad_type == 'Gallery_Cards':
            brand = ''
            if json_ad:
                brand = json_ad.get('brand', '')
            detail_str = "[Gallery] %s" % brand
        else:
            detail_str = ''

        print("%4d  %-22s  %4d  %5d  %7d  %7s  %s" % (
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
            print("  %-20s  brand=%s" % (a.get('type', '?'), a.get('brand', '?')))


# ── Backfill ──────────────────────────────────────────────────────────────────

def process_file(json_path, dry_run=False):
    """Process a single Walmart run JSON + its HTML."""
    html_path = _find_html_for_json(json_path)
    if not html_path:
        return 0, 0, 0, "no HTML found"

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return 0, 0, 0, "JSON parse error: %s" % e

    json_ads = data.get('ads', [])
    if not json_ads:
        return 0, 0, 0, None

    try:
        slots = parse_walmart_html(html_path)
    except Exception as e:
        return 0, 0, 0, "HTML parse error: %s" % e

    if not slots:
        return 0, 0, 0, "no slots found in HTML"

    matched_results = match_slots_to_json(slots, json_ads)
    assigned, unmatched = assign_slot_fields(matched_results)

    if assigned > 0 and not dry_run:
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write("\n")
        except Exception as e:
            return len(slots), 0, 0, "write error: %s" % e

    return len(slots), assigned, unmatched, None


def backfill(dry_run=False, verbose=False):
    """Run backfill across all Walmart JSON files."""
    base = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "output", "walmart")
    if not os.path.isdir(base):
        print("ERROR: Walmart output directory not found: %s" % base)
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
    print("\n%s (Walmart):" % mode)
    print("  Files scanned:    %d" % total_files)
    print("  Files changed:    %d" % files_changed)
    print("  Files no HTML:    %d" % files_no_html)
    print("  Files with error: %d" % total_errors)
    print("  Total HTML slots: %d" % total_slots)
    print("  JSON ads assigned:%d" % total_assigned)
    print("  Unmatched slots:  %d" % total_unmatched)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Walmart slot backfill from saved HTML")
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
