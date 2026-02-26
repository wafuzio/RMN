#!/usr/bin/env python3
"""
Amazon slot backfill: parse saved HTML to reconstruct true page order,
match each DOM slot to its corresponding JSON ad, and assign:
  - slot              (int) : 0-based global page position
  - slot_within_type  (int) : 0-based position within ads of the same type
  - total_slots       (int) : total number of slots on the page
  - total_slots_of_type (int) : total slots of this ad type on the page

Amazon page structure (DOM order via cel_widget_id):
  - sb-themed-collection*     → Sponsored_Brand (top/inline)
  - SEARCH_RESULTS-*          → Product_Listing (sponsored or organic)
  - FEATURED_ASINS_LIST-*     → Sponsored_Carousel
  - VIDEO_SINGLE_PRODUCT-*    → Sponsored_Brand_Video
  - sb-collections*           → Sponsored_Brand (footer)
  - loom-desktop-footer-slot* → Sponsored_Display (bottom)
  - loom-desktop-skyscraper*  → Sponsored_Display (left rail)

Usage:
    # Preview a single file (compare against screengrab)
    python3 tools/backfill_slots_amazon.py --preview <json_path>

    # Dry run (report changes without writing)
    python3 tools/backfill_slots_amazon.py --dry-run

    # Run backfill
    python3 tools/backfill_slots_amazon.py
"""

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter
from bs4 import BeautifulSoup


# ── HTML Parsing ──────────────────────────────────────────────────────────────

def _find_html_for_json(json_path):
    """
    Find the HTML file that corresponds to a given JSON run file.
    Naming conventions:
      run_results_amazon_<client>_<timestamp>.json
      search_results_amazon_<client>_<timestamp>.html
    """
    dirname = os.path.dirname(json_path)
    basename = os.path.basename(json_path)

    # Extract timestamp from JSON filename
    # Pattern: run_results_amazon_<client>_<timestamp>.json
    m = re.search(r'(\d{14})', basename)
    if not m:
        return None
    timestamp = m.group(1)

    # Look for HTML with same timestamp in same directory
    for f in os.listdir(dirname):
        if f.endswith('.html') and timestamp in f:
            return os.path.join(dirname, f)

    # Also check subdirectories (some runs use timestamp subdirs)
    ts_dir = os.path.join(dirname, timestamp)
    if os.path.isdir(ts_dir):
        for f in os.listdir(ts_dir):
            if f.endswith('.html') and 'search_results' in f:
                return os.path.join(ts_dir, f)

    return None


def _extract_product_detail(wrapper_element):
    """
    Extract all available detail from an Amazon search result wrapper.
    The wrapper is the cel_widget_id element (MAIN-SEARCH_RESULTS-*),
    which contains a child div with data-asin and all product detail.
    """
    detail = {}

    # ASIN from the first child with data-asin
    asin_el = wrapper_element.find(attrs={'data-asin': True})
    detail['asin'] = asin_el.get('data-asin', '') if asin_el else ''

    # Sponsored?
    text = wrapper_element.get_text()
    detail['is_sponsored'] = 'Sponsored' in text

    # Title
    title_el = wrapper_element.select_one('h2 a span, h2 span')
    detail['title'] = title_el.get_text(strip=True) if title_el else ''

    # Price
    price_el = wrapper_element.select_one('.a-price .a-offscreen')
    detail['price'] = price_el.get_text(strip=True) if price_el else ''

    # Rating
    rating_el = wrapper_element.select_one('[aria-label*="out of 5"]')
    detail['rating'] = rating_el.get('aria-label', '') if rating_el else ''

    # Review count
    review_el = wrapper_element.select_one('a[href*="customerReviews"] span')
    detail['reviews'] = review_el.get_text(strip=True) if review_el else ''

    # Image
    img_el = wrapper_element.select_one('img.s-image')
    detail['image_url'] = img_el.get('src', '') if img_el else ''

    # Link
    link_el = wrapper_element.select_one('h2 a')
    detail['href'] = link_el.get('href', '') if link_el else ''

    return detail


def _extract_carousel_cards(carousel_element):
    """
    Extract individual card details from an Amazon carousel (FEATURED_ASINS).
    Returns a list of dicts, one per card, each with product detail.
    """
    # Header text (shared across all cards)
    header_el = carousel_element.select_one(
        '.a-carousel-heading, [class*="carousel"] h2, span.a-size-base-plus'
    )
    header = header_el.get_text(strip=True)[:120] if header_el else ''

    cards = carousel_element.select('.a-carousel-card')
    total_cards = len(cards)
    results = []

    for idx, card in enumerate(cards):
        detail = {}
        detail['carousel_header'] = header
        detail['card_index'] = idx
        detail['total_cards_in_carousel'] = total_cards

        # ASIN
        asin_el = card.find(attrs={'data-asin': True})
        detail['asin'] = asin_el.get('data-asin', '') if asin_el else ''

        # Title
        title_el = card.select_one('.a-truncate-full, h2 span, .a-size-base')
        detail['title'] = title_el.get_text(strip=True)[:120] if title_el else ''

        # Price
        price_el = card.select_one('.a-price .a-offscreen')
        detail['price'] = price_el.get_text(strip=True) if price_el else ''

        # Rating
        rating_el = card.select_one('[aria-label*="out of 5"]')
        detail['rating'] = rating_el.get('aria-label', '')[:40] if rating_el else ''

        # Sponsored?
        text = card.get_text()
        detail['is_sponsored'] = 'Sponsored' in text

        # Image
        img_el = card.select_one('img')
        detail['image_url'] = img_el.get('src', '') if img_el else ''

        results.append(detail)

    return results


def _extract_sb_detail(sb_element):
    """Extract detail from a Sponsored Brand element."""
    detail = {}

    # Headline
    headline = sb_element.select_one('.sb-headline, [class*="headline"], h2')
    if headline:
        raw = headline.get_text(strip=True)
        # Clean up: remove "Sponsored|" prefix artifacts
        raw = re.sub(r'Sponsored\|?', '', raw).strip()
        detail['headline'] = raw[:120]
    else:
        detail['headline'] = ''

    # Products in the SB unit
    products = sb_element.select('[data-asin]')
    asins = [p.get('data-asin', '') for p in products if p.get('data-asin')]
    detail['product_count'] = len(asins)
    detail['asins'] = asins

    return detail


def _extract_sbv_detail(sbv_element):
    """Extract detail from a Sponsored Brand Video element."""
    detail = {}

    title_el = sbv_element.select_one('.a-size-medium, h2, [class*="title"]')
    if title_el:
        raw = title_el.get_text(strip=True)
        raw = re.sub(r'^Sponsored', '', raw).strip()
        detail['title'] = raw[:120]
    else:
        detail['title'] = ''

    video = sbv_element.select_one('video')
    detail['video_url'] = video.get('src', '') if video else ''

    return detail


def _extract_display_detail(display_element, slot_location):
    """Extract detail from a Sponsored Display element."""
    detail = {
        'slot_location': slot_location,  # 'left_rail' or 'bottom'
    }
    return detail


def parse_amazon_html(html_path):
    """
    Parse an Amazon search results HTML file and return a list of slots
    in true page order. Each slot is a dict:
      {
        'ad_type': str,
        'dom_position': int,       # index in cel_widget_id list
        'cel_widget_id': str,
        'detail': dict,            # type-specific extracted detail
      }
    """
    with open(html_path, 'r', encoding='utf-8', errors='replace') as f:
        soup = BeautifulSoup(f, 'html.parser')

    slots = []
    cel_widgets = soup.find_all(attrs={'cel_widget_id': True})

    for dom_idx, el in enumerate(cel_widgets):
        wid = el.get('cel_widget_id', '')

        # Skip inner adplacements: wrappers (children of loom-desktop wrappers)
        if wid.startswith('adplacements:'):
            continue

        # ── Sponsored Brand (top/inline) ──
        if 'sb-themed-collection' in wid:
            detail = _extract_sb_detail(el)
            slots.append({
                'ad_type': 'Sponsored_Brand',
                'dom_position': dom_idx,
                'cel_widget_id': wid,
                'detail': detail,
            })

        # ── Sponsored Brand (footer) ──
        elif 'sb-collections' in wid:
            detail = _extract_sb_detail(el)
            slots.append({
                'ad_type': 'Sponsored_Brand',
                'dom_position': dom_idx,
                'cel_widget_id': wid,
                'detail': detail,
            })

        # ── Sponsored Brand Video ──
        elif 'VIDEO_SINGLE_PRODUCT' in wid:
            detail = _extract_sbv_detail(el)
            slots.append({
                'ad_type': 'Sponsored_Brand_Video',
                'dom_position': dom_idx,
                'cel_widget_id': wid,
                'detail': detail,
            })

        # ── Carousel (expand each card as its own slot) ──
        elif 'FEATURED_ASINS' in wid:
            card_details = _extract_carousel_cards(el)
            for card_detail in card_details:
                slots.append({
                    'ad_type': 'Sponsored_Carousel',
                    'dom_position': dom_idx,
                    'cel_widget_id': wid,
                    'detail': card_detail,
                })

        # ── Product Listing (search result) ──
        elif 'SEARCH_RESULTS' in wid:
            # Pass the whole wrapper; _extract_product_detail finds data-asin inside
            detail = _extract_product_detail(el)
            if detail.get('asin'):
                slots.append({
                    'ad_type': 'Product_Listing',
                    'dom_position': dom_idx,
                    'cel_widget_id': wid,
                    'detail': detail,
                })

        # ── Sponsored Display: left rail ──
        elif 'skyscraper' in wid.lower():
            detail = _extract_display_detail(el, 'left_rail')
            slots.append({
                'ad_type': 'Sponsored_Display',
                'dom_position': dom_idx,
                'cel_widget_id': wid,
                'detail': detail,
            })

        # ── Sponsored Display: bottom ──
        elif 'footer-slot' in wid.lower() and 'sb-' not in wid:
            detail = _extract_display_detail(el, 'bottom')
            slots.append({
                'ad_type': 'Sponsored_Display',
                'dom_position': dom_idx,
                'cel_widget_id': wid,
                'detail': detail,
            })

    return slots


# ── JSON Matching ─────────────────────────────────────────────────────────────

def match_slots_to_json(slots, json_ads):
    """
    Match HTML-derived slots to JSON ad objects.
    Returns list of (slot_dict, matched_json_ad_or_None) in page order.
    """
    # Build lookup structures from JSON
    sbv_ads = [a for a in json_ads if a.get('type') == 'Sponsored_Brand_Video']
    sb_ads = [a for a in json_ads if a.get('type') == 'Sponsored_Brand']
    sb_card_ads = [a for a in json_ads if a.get('type') == 'Sponsored_Brand_Card']
    sd_ads = [a for a in json_ads if a.get('type') == 'Sponsored_Display']
    carousel_ads = [a for a in json_ads if a.get('type') == 'Sponsored_Carousel']

    # Product listings: queue per ASIN to handle duplicates (same ASIN can appear
    # multiple times on the page, e.g. in different grid positions)
    from collections import defaultdict, deque
    pl_queues = defaultdict(deque)
    for a in json_ads:
        if a.get('type') == 'Product_Listing' and a.get('asin'):
            pl_queues[a['asin']].append(a)

    # Running indices per type
    sbv_idx = 0
    sb_idx = 0
    carousel_idx = 0
    last_carousel_wid = None
    matched_sd_ids = set()

    results = []

    for slot in slots:
        ad_type = slot['ad_type']
        matched = None

        if ad_type == 'Sponsored_Brand_Video':
            if sbv_idx < len(sbv_ads):
                matched = sbv_ads[sbv_idx]
                sbv_idx += 1

        elif ad_type == 'Sponsored_Brand':
            if sb_idx < len(sb_ads):
                matched = sb_ads[sb_idx]
                sb_idx += 1

        elif ad_type == 'Sponsored_Carousel':
            # All cards from the same carousel (same cel_widget_id) share
            # the same parent JSON ad. Advance index only on new carousel.
            this_wid = slot.get('cel_widget_id', '')
            if this_wid != last_carousel_wid:
                carousel_idx += 1
                last_carousel_wid = this_wid
            idx = carousel_idx - 1
            if 0 <= idx < len(carousel_ads):
                matched = carousel_ads[idx]

        elif ad_type == 'Product_Listing':
            asin = slot['detail'].get('asin', '')
            if asin in pl_queues and pl_queues[asin]:
                matched = pl_queues[asin].popleft()

        elif ad_type == 'Sponsored_Display':
            slot_loc = slot['detail'].get('slot_location', '')
            for sd in sd_ads:
                if id(sd) not in matched_sd_ids:
                    sd_slot = sd.get('slot', '')
                    if sd_slot == slot_loc:
                        matched = sd
                        matched_sd_ids.add(id(sd))
                        break

        results.append((slot, matched))

    return results


# ── Slot Assignment ───────────────────────────────────────────────────────────

def assign_slot_fields(matched_results):
    """
    Given matched results in page order, compute and assign slot fields
    to the matched JSON ads.

    Returns (total_assigned, total_unmatched).
    """
    total_slots = len(matched_results)

    # Count totals per type
    type_counts = Counter(slot['ad_type'] for slot, _ in matched_results)

    # Running index per type
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
    """
    Parse HTML + JSON for a single run and print a readable slot table
    for manual comparison against the screengrab.
    """
    html_path = _find_html_for_json(json_path)
    if not html_path:
        print(f"ERROR: No HTML file found for {json_path}")
        return

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    json_ads = data.get('ads', [])

    print(f"JSON:  {json_path}")
    print(f"HTML:  {html_path}")
    print(f"JSON ads: {len(json_ads)}")
    print()

    # Parse HTML
    slots = parse_amazon_html(html_path)
    print(f"HTML slots: {len(slots)}")
    print()

    # Match
    matched_results = match_slots_to_json(slots, json_ads)

    # Compute type totals
    type_counts = Counter(s['ad_type'] for s, _ in matched_results)
    type_running = Counter()

    total_slots = len(matched_results)

    # Print table — all 4 slot fields on every row
    hdr = (f"{'slot':>4s}  {'type':25s}  "
           f"{'w/in':>4s}  {'total':>5s}  {'of_type':>7s}  "
           f"{'match':7s}  {'detail'}")
    print(hdr)
    print("-" * 130)

    for i, (slot, json_ad) in enumerate(matched_results):
        ad_type = slot['ad_type']
        within = type_running[ad_type]
        type_running[ad_type] += 1
        of_type = type_counts[ad_type]

        match_str = "YES" if json_ad else "---"

        # Build detail string based on type
        detail = slot['detail']
        if ad_type == 'Product_Listing':
            sp = "SP" if detail.get('is_sponsored') else "OR"
            asin = detail.get('asin', '')
            title = detail.get('title', '')[:45]
            price = detail.get('price', '')
            detail_str = f"[{sp}] {asin}  {price:>8s}  {title}"
        elif ad_type == 'Sponsored_Brand':
            headline = detail.get('headline', '')[:50]
            n_products = detail.get('product_count', 0)
            detail_str = f"{headline}  ({n_products} products)"
        elif ad_type == 'Sponsored_Brand_Video':
            title = detail.get('title', '')[:60]
            detail_str = title
        elif ad_type == 'Sponsored_Carousel':
            header = detail.get('carousel_header', '')[:35]
            card_idx = detail.get('card_index', 0)
            total_cards = detail.get('total_cards_in_carousel', 0)
            asin = detail.get('asin', '')
            price = detail.get('price', '')
            title = detail.get('title', '')[:40]
            detail_str = f"[{header}] card {card_idx+1}/{total_cards}  {asin}  {price:>8s}  {title}"
        elif ad_type == 'Sponsored_Display':
            loc = detail.get('slot_location', '?')
            brand = ''
            if json_ad:
                brand = json_ad.get('brand', '')
            detail_str = f"[{loc}] {brand}"
        else:
            detail_str = ''

        # Add JSON brand if matched and not already shown
        if json_ad and ad_type not in ('Product_Listing', 'Sponsored_Display'):
            brand = json_ad.get('brand') or json_ad.get('brand_canonical') or ''
            if brand:
                detail_str = f"{brand:20s}  {detail_str}"

        print(f"{i:4d}  {ad_type:25s}  "
              f"{within:4d}  {total_slots:5d}  {of_type:7d}  "
              f"{match_str:7s}  {detail_str}")

    # Summary
    total_matched = sum(1 for _, m in matched_results if m)
    print()
    print(f"Total slots: {total_slots}")
    print(f"Type counts: {dict(type_counts)}")
    print(f"Matched: {total_matched}/{total_slots}")

    # Show unmatched JSON ads
    matched_ids = set(id(m) for _, m in matched_results if m)
    unmatched_json = [a for a in json_ads if id(a) not in matched_ids]
    if unmatched_json:
        print(f"\nUnmatched JSON ads ({len(unmatched_json)}):")
        for a in unmatched_json:
            t = a.get('type', '?')
            b = a.get('brand', a.get('brand_canonical', ''))
            asin = a.get('asin', '')
            print(f"  {t:25s}  brand={b}  asin={asin}")


# ── Backfill ──────────────────────────────────────────────────────────────────

def _build_slots_array(matched_results, json_ads):
    """Build a serializable slots array from matched_results for persisting in JSON.

    Every entry gets:
      slot, slot_within_type, total_slots, total_slots_of_type,
      ad_type, is_sponsored, product_id, title, price, image_url, image_path,
      brand, href, matched_ad_index

    image_path points to assets/amazon/product_images/<asin>.<ext> —
    downloaded on first encounter, re-linked on subsequent appearances of the
    same asin (same product can appear multiple times on one page).
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
    type_running = Counter()
    # Cache product_id → image_path within this run (avoids re-downloading duplicates)
    _image_cache = {}

    slots_out = []
    for i, (slot, json_ad) in enumerate(matched_results):
        d = slot['detail']
        ad_type = slot['ad_type']
        within = type_running[ad_type]
        type_running[ad_type] += 1

        product_id = d.get('asin', '')
        image_url  = d.get('image_url', '')

        # Resolve canonical image path — download once, re-link on duplicates
        image_path = None
        if _img_store and product_id:
            if product_id in _image_cache:
                image_path = _image_cache[product_id]
            elif has_image('amazon', product_id):
                image_path = get_image_path('amazon', product_id)
                _image_cache[product_id] = image_path
            elif image_url:
                image_path = download_and_store('amazon', product_id, image_url)
                _image_cache[product_id] = image_path

        entry = {
            'slot': i,
            'slot_within_type': within,
            'total_slots': total_slots,
            'total_slots_of_type': type_counts[ad_type],
            'ad_type': ad_type,
            'is_sponsored': d.get('is_sponsored', ad_type != 'Product_Listing'),
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
            entry['brand'] = json_ad.get('brand', json_ad.get('brand_canonical'))
        # Sponsored_Display gets slot_location
        if ad_type == 'Sponsored_Display':
            entry['slot_location'] = d.get('slot_location', '')
        slots_out.append(entry)
    return slots_out


def process_file(json_path, dry_run=False):
    """
    Process a single Amazon run JSON + its HTML.
    Returns (num_slots, num_assigned, num_unmatched, error_str|None).
    """
    html_path = _find_html_for_json(json_path)
    if not html_path:
        return 0, 0, 0, "no HTML found"

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return 0, 0, 0, f"JSON parse error: {e}"

    json_ads = data.get('ads', [])
    if not json_ads:
        return 0, 0, 0, None

    try:
        slots = parse_amazon_html(html_path)
    except Exception as e:
        return 0, 0, 0, f"HTML parse error: {e}"

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
            return len(slots), 0, 0, f"write error: {e}"

    return len(slots), assigned, unmatched, None


def backfill(dry_run=False, verbose=False):
    """Run backfill across all Amazon JSON files."""
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output", "amazon")
    if not os.path.isdir(base):
        print(f"ERROR: Amazon output directory not found: {base}")
        sys.exit(1)

    json_files = sorted(glob.glob(os.path.join(base, "**", "runs", "*.json"), recursive=True))
    # Filter to run_results files only
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
                print(f"  {'SKIP' if error == 'no HTML found' else 'ERROR'} {filepath}: {error}")
        elif num_assigned > 0:
            files_changed += 1
            if verbose:
                print(f"  {filepath}: {num_slots} slots, {num_assigned} assigned, {num_unmatched} unmatched")

    mode = "DRY RUN" if dry_run else "DONE"
    print(f"\n{mode} (Amazon):")
    print(f"  Files scanned:    {total_files}")
    print(f"  Files changed:    {files_changed}")
    print(f"  Files no HTML:    {files_no_html}")
    print(f"  Files with error: {total_errors}")
    print(f"  Total HTML slots: {total_slots}")
    print(f"  JSON ads assigned:{total_assigned}")
    print(f"  Unmatched slots:  {total_unmatched}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Amazon slot backfill from saved HTML")
    parser.add_argument("--preview", type=str, metavar="JSON_PATH",
                        help="Preview slot readout for a single JSON file (for manual validation)")
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
