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
    # Walmart embeds both forms: "$497current price $4.97" — prefer decimal form
    m_decimal = re.search(r'(\$[\d,]+\.\d{2})', raw_price)
    m_any     = re.search(r'(\$[\d,.]+)', raw_price)
    detail['price'] = (m_decimal or m_any).group(1) if (m_decimal or m_any) else raw_price[:20]

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

    Uses a recursive DOM walk to guarantee correct ordering, instead of
    html_str.find() which gives wrong positions for nested elements.
    """
    with open(html_path, 'r', encoding='utf-8', errors='replace') as f:
        soup = BeautifulSoup(f, 'html.parser')

    slots = []
    seen_ids = set()  # avoid double-counting nested data-item-id elements

    def _walk(el):
        """Recursively walk the DOM in document order, emitting slots."""
        if not hasattr(el, 'name') or not el.name:
            return

        # ── Ad iframes (display ads, gallery cards) ─────────────────
        if el.name == 'iframe' and 'Walmart Advertisement' in el.get('title', ''):
            ad_type_attr = el.get('data-ad-type', '')
            testid = el.get('data-testid', '')
            # Determine slot_location from data-testid / data-ad-type
            if 'skyline' in testid or ad_type_attr == 'top':
                iframe_type = 'Sponsored_Display'
                slot_location = 'top'
            elif ad_type_attr == 'bottom' or 'btf' in testid:
                iframe_type = 'Sponsored_Display'
                slot_location = 'bottom'
            elif 'sidebar' in testid or 'skyscraper' in testid:
                iframe_type = 'Sponsored_Display'
                slot_location = 'left_rail'
            else:
                iframe_type = 'Gallery_Cards'
                slot_location = ''
            slots.append({
                'ad_type': iframe_type,
                'detail': {
                    'iframe_src': el.get('src', '')[:200],
                    'is_sponsored': True,
                    'slot_location': slot_location,
                    'data_testid': testid,
                    'data_ad_type': ad_type_attr,
                }
            })
            return

        # ── SBA container — emit all child data-item-id as SBA ──────
        if el.get('data-testid') == 'sba-container':
            for item in el.find_all(attrs={'data-item-id': True}):
                iid = item.get('data-item-id', '')
                if iid not in seen_ids:
                    seen_ids.add(iid)
                    detail = _extract_product_detail(item)
                    detail['plmt'] = _get_plmt(item)
                    detail['is_sponsored'] = True
                    slots.append({'ad_type': 'SBA', 'detail': detail})
            return  # don't recurse further

        # ── SBV video carousel — emit child data-item-id as SBV ─────
        if el.get('data-testid') == 'video-product-carousel':
            for item in el.find_all(attrs={'data-item-id': True}):
                iid = item.get('data-item-id', '')
                if iid not in seen_ids:
                    seen_ids.add(iid)
                    detail = _extract_product_detail(item)
                    detail['plmt'] = _get_plmt(item)
                    detail['is_sponsored'] = True
                    slots.append({'ad_type': 'SBV', 'detail': detail})
            return  # don't recurse further

        # ── Tile Takeover ────────────────────────────────────────────
        if el.get('data-testid') == 'tile-take-over':
            # Extract link and text from the tile takeover
            link_el = el.select_one('a[href]')
            detail = {
                'href': link_el.get('href', '') if link_el else '',
                'title': el.get_text(strip=True)[:120],
                'is_sponsored': True,
            }
            slots.append({'ad_type': 'Tile_Takeover', 'detail': detail})
            return

        # ── Individual product (data-item-id) ────────────────────────
        # seen_ids only contains IDs already emitted by SBA/SBV containers;
        # duplicate product IDs in the grid are real (SP + OR for same item).
        iid = el.get('data-item-id', '')
        if iid and iid not in seen_ids:
            ad_type = _classify_item(el)
            detail = _extract_product_detail(el)
            detail['plmt'] = _get_plmt(el)
            detail['is_sponsored'] = ad_type in ('SBA', 'SBV', 'Sponsored_Product')
            slots.append({'ad_type': ad_type, 'detail': detail})
            return  # don't recurse into product children

        # ── Otherwise, recurse into children ─────────────────────────
        for child in el.children:
            _walk(child)

    _walk(soup)
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

        elif ad_type == 'Sponsored_Display':
            # Programmatic display ads — no direct JSON match
            matched = None

        elif ad_type == 'Tile_Takeover':
            # Tile takeovers — no direct JSON match
            matched = None

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
        elif ad_type == 'Sponsored_Display':
            loc = detail.get('slot_location', '?')
            detail_str = "[Display:%s] testid=%s" % (loc, detail.get('data_testid', ''))
        elif ad_type == 'Tile_Takeover':
            detail_str = "[Tile] %s" % detail.get('title', '')[:60]
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

def _build_slots_array(matched_results, json_ads):
    """Build a serializable slots array from matched_results for persisting in JSON.

    Every entry gets:
      slot, slot_within_type, total_slots, total_slots_of_type,
      ad_type, is_sponsored, product_id, title, price, image_url, image_path,
      brand, href, matched_ad_index

    image_path points to assets/walmart/product_images/<product_id>.<ext> —
    downloaded on first encounter, re-linked on subsequent appearances of the
    same product_id (same product can appear multiple times on one page).
    """
    try:
        from tools.product_image_store import download_and_store, get_image_path, has_image
        _img_store = True
    except ImportError:
        _img_store = False

    ads_index_map = {id(a): i for i, a in enumerate(json_ads)}
    total_slots = len(matched_results)

    # Pre-compute per-type totals
    type_counts = Counter(slot['ad_type'] for slot, _ in matched_results)
    # Running within-type index
    type_running = Counter()
    # Cache product_id → image_path within this run (avoids re-downloading duplicates)
    _image_cache = {}

    slots_out = []
    for i, (slot, json_ad) in enumerate(matched_results):
        d = slot['detail']
        ad_type = slot['ad_type']
        within = type_running[ad_type]
        type_running[ad_type] += 1

        product_id = d.get('item_id', '')
        image_url  = d.get('image_url', '')

        # Resolve canonical image path — download once, re-link on duplicates
        image_path = None
        if _img_store and product_id:
            if product_id in _image_cache:
                image_path = _image_cache[product_id]
            elif has_image('walmart', product_id):
                image_path = get_image_path('walmart', product_id)
                _image_cache[product_id] = image_path
            elif image_url:
                image_path = download_and_store('walmart', product_id, image_url)
                _image_cache[product_id] = image_path

        entry = {
            'slot': i,
            'slot_within_type': within,
            'total_slots': total_slots,
            'total_slots_of_type': type_counts[ad_type],
            'ad_type': ad_type,
            'is_sponsored': d.get('is_sponsored', ad_type in (
                'SBA', 'SBV', 'Sponsored_Product', 'Gallery_Cards',
                'Sponsored_Display', 'Tile_Takeover')),
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
            entry['brand'] = json_ad.get('brand', json_ad.get('brand_name'))
        # Sponsored_Display gets slot_location (top, bottom, left_rail)
        if ad_type == 'Sponsored_Display':
            entry['slot_location'] = d.get('slot_location', '')
        slots_out.append(entry)
    return slots_out


def _build_product_listings(matched_results):
    """Convert Product_Listing slots to standardized product_listings dicts."""
    listings = []
    for slot, _ in matched_results:
        if slot['ad_type'] not in ('Product_Listing', 'Sponsored_Product'):
            continue
        d = slot['detail']
        listings.append({
            'type': 'Product_Listing',
            'subtype': 'sponsored_product' if d.get('is_sponsored') else 'organic_product',
            'product_id': d.get('item_id', ''),
            'retailer_id_type': 'walmart_item_id',
            'title': d.get('title', ''),
            'brand': None,
            'price': d.get('price', ''),
            'image_url': d.get('image_url', ''),
            'href': d.get('href', ''),
            'is_sponsored': d.get('is_sponsored', False),
            'position': d.get('grid_position', -1),
        })
    return listings


def _find_screenshot_for_run(json_path):
    """Find the Main page screenshot matching a run's timestamp."""
    dirname = os.path.dirname(json_path)
    ts = os.path.basename(dirname)  # e.g. 20260112200800
    if len(ts) < 14:
        m = re.search(r'(\d{14})', os.path.basename(json_path))
        if m:
            ts = m.group(1)
        else:
            return None
    # Convert to screenshot date format: DYYYY-MM-DD_THH-MM.SS
    date_str = 'D%s-%s-%s_T%s-%s.%s' % (ts[:4], ts[4:6], ts[6:8], ts[8:10], ts[10:12], ts[12:14])
    # Screenshots live in <keyword_dir>/Main/
    kw_dir = os.path.dirname(os.path.dirname(dirname))
    main_dir = os.path.join(kw_dir, 'Main')
    if not os.path.isdir(main_dir):
        return None
    for f in os.listdir(main_dir):
        if f.endswith('.png') and date_str in f:
            return os.path.join(main_dir, f)
    return None


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

    try:
        slots = parse_walmart_html(html_path)
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

    # Link to Main page screenshot
    screenshot = _find_screenshot_for_run(json_path)
    if screenshot:
        # Store as relative path from the output root
        output_root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'output')
        try:
            rel = os.path.relpath(screenshot, os.path.dirname(json_path))
        except ValueError:
            rel = screenshot
        if 'screenshot_path' not in data or data['screenshot_path'] != rel:
            data['screenshot_path'] = rel
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
