#!/usr/bin/env python3
"""
build_slot_coords.py — Extract DOM bounding boxes for each slot from a saved HTML file.

Loads the HTML into a headless Playwright browser at the scrape viewport width,
reads getBoundingClientRect() for each product/ad element, and writes a sidecar
  <html_basename>.coords.json
next to the HTML file. 


The coords file maps slot identifiers (asin / cel_widget_id) to pixel rects:
  { "B00CXXKE9O": {"x": 313, "y": 446, "w": 230, "h": 320}, ... }

The slot_inspector reads this sidecar instead of doing template matching.

Usage:
    python3 tools/build_slot_coords.py <json_or_html_path>
    python3 tools/build_slot_coords.py --retailer amazon output/amazon/community_coffee/runs/
"""

import argparse
import json
import os
import sys

# Viewport width used during the actual scrape captures
VIEWPORT_W = 1385
VIEWPORT_H = 900


def _html_path_for_json(json_path):
    """Mirror of backfill_slots_amazon._find_html_for_json logic."""
    import re
    dirname = os.path.dirname(json_path)
    basename = os.path.basename(json_path)
    m = re.search(r'(\d{14})', basename)
    ts = m.group(1) if m else None

    # Try exact timestamp match first
    if ts:
        for fn in os.listdir(dirname):
            if fn.endswith('.html') and ts in fn:
                return os.path.join(dirname, fn)

    # Fallback: any HTML in same dir
    for fn in sorted(os.listdir(dirname)):
        if fn.endswith('.html'):
            return os.path.join(dirname, fn)
    return None


def coords_path_for_html(html_path):
    """Return the sidecar .coords.json path for a given HTML file."""
    return html_path + '.coords.json'


def build_coords_amazon(html_path, viewport_w=VIEWPORT_W):
    """
    Load the Amazon HTML into headless Playwright and extract bounding rects
    for every [data-asin] product element and known ad container elements.

    Returns dict: { asin_or_cel_widget: {x, y, w, h}, ... }
    """
    from playwright.sync_api import sync_playwright

    coords = {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": viewport_w, "height": VIEWPORT_H})

        abs_path = os.path.abspath(html_path)
        page.goto(f"file://{abs_path}", wait_until="domcontentloaded", timeout=30000)

        # Expand the full page so rects reflect document positions
        # (no lazy loading needed since we're reading static HTML)
        page.evaluate("document.documentElement.style.overflow = 'visible'")

        # Extract rects for all [data-asin] containers and [data-cel-widget] ad slots
        result = page.evaluate("""() => {
            const out = {};

            // Product listing and sponsored product cards
            document.querySelectorAll('[data-asin]').forEach(el => {
                const asin = el.getAttribute('data-asin');
                if (!asin || asin.length < 5) return;
                const rect = el.getBoundingClientRect();
                const scrollY = window.pageYOffset || document.documentElement.scrollTop;
                if (rect.width < 10 || rect.height < 10) return;
                // Only store the largest element per asin (the card container)
                const key = asin;
                if (!(key in out) || rect.width * rect.height > out[key].w * out[key].h) {
                    out[key] = {
                        x: Math.round(rect.left),
                        y: Math.round(rect.top + scrollY),
                        w: Math.round(rect.width),
                        h: Math.round(rect.height)
                    };
                }
            });

            // Sponsored brand / carousel / video / display ad containers
            document.querySelectorAll('[data-cel-widget]').forEach(el => {
                const cel = el.getAttribute('data-cel-widget');
                if (!cel) return;
                // Only capture non-product-listing cel widgets (SBA, SBV, carousels etc.)
                if (/^(SEARCH_RESULTS|search_result)/.test(cel)) return;
                const rect = el.getBoundingClientRect();
                const scrollY = window.pageYOffset || document.documentElement.scrollTop;
                if (rect.width < 10 || rect.height < 10) return;
                out['cel:' + cel] = {
                    x: Math.round(rect.left),
                    y: Math.round(rect.top + scrollY),
                    w: Math.round(rect.width),
                    h: Math.round(rect.height)
                };
            });

            return out;
        }""")

        browser.close()

    return result


def build_and_cache(json_or_html_path):
    """
    Build coords for a run and write the sidecar .coords.json.
    Returns (coords_dict, sidecar_path).
    """
    path = json_or_html_path
    if path.endswith('.json'):
        html_path = _html_path_for_json(path)
        if not html_path or not os.path.exists(html_path):
            raise FileNotFoundError(f"No HTML found for {path}")
    else:
        html_path = path

    sidecar = coords_path_for_html(html_path)

    # Detect retailer from path
    for r in ('amazon', 'walmart', 'target', 'instacart', 'kroger'):
        if r in html_path.lower():
            retailer = r
            break
    else:
        retailer = 'amazon'

    if retailer == 'amazon':
        coords = build_coords_amazon(html_path)
    else:
        # Other retailers: same generic approach works
        coords = build_coords_amazon(html_path)

    with open(sidecar, 'w') as f:
        json.dump(coords, f)

    return coords, sidecar


def load_coords(json_or_html_path):
    """
    Load cached coords for a run. Returns dict or None if not yet built.
    """
    if json_or_html_path.endswith('.json'):
        from tools.backfill_slots_amazon import _find_html_for_json
        html_path = _find_html_for_json(json_or_html_path)
    else:
        html_path = json_or_html_path

    if not html_path:
        return None

    sidecar = coords_path_for_html(html_path)
    if not os.path.exists(sidecar):
        return None

    with open(sidecar) as f:
        return json.load(f)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Build slot DOM coords sidecar for slot_inspector')
    parser.add_argument('path', help='Path to run JSON or HTML, or a directory of runs')
    args = parser.parse_args()

    path = args.path

    if os.path.isdir(path):
        import glob
        jsons = sorted(glob.glob(os.path.join(path, '**', 'run_results_*.json'), recursive=True))
        print(f"Found {len(jsons)} run JSONs")
        for jp in jsons:
            try:
                coords, sp = build_and_cache(jp)
                print(f"  OK  {len(coords)} rects  →  {os.path.basename(sp)}")
            except Exception as e:
                print(f"  ERR {jp}: {e}")
    else:
        coords, sp = build_and_cache(path)
        print(f"Written {len(coords)} rects → {sp}")
