#!/usr/bin/env python3
"""
Shared product listing extraction module.

Each retailer scraper saves HTML. This module parses that HTML to extract
product listings and returns them as a list of dicts ready to be added
to the run JSON payload.

The parsing logic mirrors the backfill scripts but is designed to be called
inline by the scrapers at save time, so new runs get product listings
automatically without needing a separate backfill pass.

Usage from a scraper:
    from tools.extract_product_listings import extract_product_listings
    listings = extract_product_listings("walmart", html_path)
    # listings is a list of dicts, each with:
    #   type, subtype, product_id, title, brand, price, image_url,
    #   href, rating, is_sponsored, position, retailer_product_id, ...
"""

import re
import json
from bs4 import BeautifulSoup

try:
    from core.brands import canonicalize as _canonicalize_brand
except ImportError:
    _canonicalize_brand = None


# ── Shared helpers ────────────────────────────────────────────────────────────

def _clean_price(raw):
    """Extract a clean price string like '$4.74' from messy text."""
    if not raw:
        return ''
    m = re.search(r'(\$[\d,.]+(?:\.\d{2})?)', raw)
    return m.group(1) if m else raw.strip()[:20]


_GENERIC_WORDS = frozenset({
    'acne', 'skin', 'face', 'body', 'hair', 'eye', 'lip', 'hand', 'foot',
    'pack', 'count', 'set', 'kit', 'bundle', 'value', 'combo', 'plus',
    'organic', 'natural', 'premium', 'gentle', 'sensitive', 'clear', 'clean',
    'advanced', 'extra', 'ultra', 'super', 'daily', 'deep', 'new', 'best',
    'mini', 'travel', 'size', 'large', 'small', 'original', 'classic',
    'salicylic', 'benzoyl', 'retinol', 'vitamin', 'collagen', 'hyaluronic',
})

def _extract_brands_batch_llm(titles: list) -> dict:
    """Send a batch of product titles to the LLM relay and get {title: brand} back.

    Returns an empty dict on any failure (no API key, network error, bad JSON, etc.)
    so callers can transparently fall back to the heuristic.
    """
    titles = [t for t in titles if t]   # drop blanks
    if not titles:
        return {}
    try:
        from llm_client import RelayClient
        client = RelayClient()          # raises RuntimeError if ALCHEMY_API_KEY missing
    except (ImportError, RuntimeError):
        return {}

    # Build an index-keyed list so the LLM doesn't have to repeat long titles as JSON keys
    numbered = "\n".join(f'{i}. {t}' for i, t in enumerate(titles))
    prompt = (
        "You are a product data specialist. "
        "For each numbered product title below, identify the brand name.\n"
        "Rules:\n"
        "- Return ONLY a JSON object like {\"0\": \"Neutrogena\", \"1\": null, ...}\n"
        "- Use the index number as the key (string).\n"
        "- Value is the brand name string, or null if no brand is identifiable.\n"
        "- Brand name only — no product line, no descriptor words.\n"
        "- If the title starts with a generic word (Acne, Salicylic, Organic, etc.) "
        "and no brand is present, return null.\n"
        "- Do NOT include any explanation, markdown, or extra text.\n\n"
        f"Titles:\n{numbered}"
    )

    try:
        raw = client.complete(prompt, model="gpt-5.4-2026-03-05",
                              temperature=0.0, max_tokens=800)
        # Strip any markdown fences the model might add
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r'^```[a-z]*\n?', '', raw).rstrip('`').strip()
        index_map = json.loads(raw)
        return {titles[int(k)]: v for k, v in index_map.items()
                if v and isinstance(v, str) and int(k) < len(titles)}
    except Exception:
        return {}


def _brand_from_title(title: str) -> str:
    """Derive brand from product title — lexicon first, cautious first-word fallback."""
    if not title:
        return None
    if _canonicalize_brand:
        canon = _canonicalize_brand(title)
        if canon:
            return canon
    # Cautious heuristic: only return a single first word if it looks like a brand name
    # (proper capitalization, 3+ chars, not a generic/chemical/descriptor word, not a number).
    first = title.split()[0] if title.split() else ''
    clean = re.sub(r"[^A-Za-z0-9&'.-]", '', first)
    if (clean and len(clean) >= 3
            and clean[0].isupper()
            and not clean[0].isdigit()
            and clean.lower() not in _GENERIC_WORDS):
        return first
    return None


# ── Amazon ────────────────────────────────────────────────────────────────────
# Amazon captures product listings live via Playwright (not from saved HTML),
# so this function is a no-op / fallback for backfill only.

def _extract_amazon(soup):
    """Extract product listings from Amazon saved HTML."""
    listings = []
    cel_widgets = soup.find_all(attrs={'cel_widget_id': True})

    for dom_idx, el in enumerate(cel_widgets):
        wid = el.get('cel_widget_id', '')
        if 'SEARCH_RESULTS' not in wid:
            continue

        asin_el = el.find(attrs={'data-asin': True})
        asin = asin_el.get('data-asin', '') if asin_el else ''
        if not asin:
            continue

        text = el.get_text()
        is_sponsored = 'Sponsored' in text

        title_el = el.select_one('h2 a span, h2 span')
        title = title_el.get_text(strip=True) if title_el else ''

        price_el = el.select_one('.a-price .a-offscreen')
        price = price_el.get_text(strip=True) if price_el else ''

        rating_el = el.select_one('[aria-label*="out of 5"]')
        rating = rating_el.get('aria-label', '') if rating_el else ''

        review_el = el.select_one('a[href*="customerReviews"] span')
        reviews = review_el.get_text(strip=True) if review_el else ''

        img_el = el.select_one('img.s-image')
        image_url = img_el.get('src', '') if img_el else ''

        link_el = el.select_one('h2 a')
        href = link_el.get('href', '') if link_el else ''

        listings.append({
            'type': 'Product_Listing',
            'subtype': 'sponsored_product' if is_sponsored else 'organic_product',
            'product_id': asin,
            'retailer_id_type': 'asin',
            'title': title,
            'brand': None,
            'price': price,
            'image_url': image_url,
            'href': href,
            'rating': rating,
            'review_count': reviews,
            'is_sponsored': is_sponsored,
            'position': dom_idx,
        })

    return listings


# ── Walmart ───────────────────────────────────────────────────────────────────

def _extract_walmart(soup):
    """Extract product listings from Walmart saved HTML."""
    raw_listings = []
    position = 0

    for item in soup.find_all(attrs={'data-item-id': True}):
        item_id = item.get('data-item-id', '')

        # Classify by tracking URL
        plmt = ''
        for link in item.select('a[href*="sp/track"]'):
            href = link.get('href', '')
            m = re.search(r'plmt=([^&]+)', href)
            if m:
                plmt = m.group(1)
                break

        # Skip SBA/SBV carousel items — those are ad slots, not product listings
        if 'sb-search' in plmt or 'sv-search' in plmt:
            continue

        is_sponsored = 'sp-search' in plmt

        # Title
        title_el = item.select_one('[data-automation-id="product-title"]')
        title = title_el.get_text(strip=True)[:120] if title_el else ''

        # Price
        price_el = item.select_one('[data-automation-id="product-price"]')
        raw_price = price_el.get_text(strip=True) if price_el else ''
        price = _clean_price(raw_price)

        # Image
        img_el = item.select_one('img[src*="walmartimages"]')
        image_url = img_el.get('src', '') if img_el else ''

        # Link / product ID
        link_el = item.select_one('a[href*="/ip/"]')
        href = link_el.get('href', '') if link_el else ''
        m = re.search(r'/(\d{5,})', href)
        walmart_id = m.group(1) if m else ''

        # Rating
        rating_el = item.select_one('[data-testid*="rating"], [aria-label*="star"]')
        rating = ''
        if rating_el:
            rating = rating_el.get('aria-label', rating_el.get_text(strip=True))[:40]

        raw_listings.append({
            'type': 'Product_Listing',
            'subtype': 'sponsored_product' if is_sponsored else 'organic_product',
            'product_id': item_id,
            'retailer_id_type': 'walmart_item_id',
            'walmart_id': walmart_id,
            'title': title,
            'brand': None,          # filled in below
            'price': price,
            'image_url': image_url,
            'href': href,
            'rating': rating,
            'is_sponsored': is_sponsored,
            'position': position,
        })
        position += 1

    # ── Brand enrichment: LLM first, heuristic fallback ───────────────────
    titles = [l['title'] for l in raw_listings]
    llm_brands = _extract_brands_batch_llm(titles)   # empty dict if unavailable

    for listing in raw_listings:
        t = listing['title']
        if t in llm_brands:
            listing['brand'] = llm_brands[t]
        else:
            listing['brand'] = _brand_from_title(t)

    return raw_listings


# ── Kroger ────────────────────────────────────────────────────────────────────

def _extract_kroger(soup):
    """Extract product listings from Kroger saved HTML."""
    listings = []

    for card in soup.find_all(attrs={'data-testid': re.compile(r'^product-card-\d+$')}):
        testid = card.get('data-testid', '')
        m = re.search(r'(\d+)$', testid)
        grid_pos = int(m.group(1)) if m else -1

        # Title
        title_el = card.select_one('[data-testid="cart-page-item-description"]')
        title = title_el.get_text(strip=True)[:120] if title_el else ''

        # Price
        price_el = card.select_one(
            '[data-testid="price-heading-tag"], [class*="kds-Price"]'
        )
        price = price_el.get_text(strip=True)[:30] if price_el else ''

        # Image
        img_el = card.select_one(
            'img[data-testid="product-image-loaded"], img[data-testid="product-image"]'
        )
        image_url = img_el.get('src', '') if img_el else ''

        # Link → UPC
        link_el = card.select_one('a[href*="/p/"]')
        href = link_el.get('href', '') if link_el else ''
        upc_match = re.search(r'/(\d{10,})', href)
        upc = upc_match.group(1) if upc_match else ''

        # Sponsored?
        is_sponsored = 'Sponsored' in card.get_text()

        listings.append({
            'type': 'Product_Listing',
            'subtype': 'sponsored_product' if is_sponsored else 'organic_product',
            'product_id': upc,
            'retailer_id_type': 'upc',
            'title': title,
            'brand': None,
            'price': price,
            'image_url': image_url,
            'href': href,
            'is_sponsored': is_sponsored,
            'position': grid_pos,
        })

    return listings


# ── Target ────────────────────────────────────────────────────────────────────

def _extract_target(soup):
    """Extract product listings from Target saved HTML."""
    listings = []
    position = 0

    for card in soup.select('[data-test="@web/ProductCard/ProductCardVariantDefault"]'):
        # Title
        title_el = card.select_one('[data-test="@web/ProductCard/title"]')
        title = title_el.get_text(strip=True)[:120] if title_el else ''

        # Brand
        brand_el = card.select_one('[data-test*="brand"]')
        brand = brand_el.get_text(strip=True)[:60] if brand_el else None

        # Price
        price_el = card.select_one(
            '[data-test="@web/Price/PriceStandard"], '
            '[data-test="@web/Price/PriceHandle"], '
            '[data-test="@web/Price/PriceAndPromoMinimal"]'
        )
        price = price_el.get_text(strip=True)[:40] if price_el else ''

        # Image
        img_el = card.select_one(
            '[data-test="@web/ProductCard/ProductCardImage/primary"] img'
        )
        image_url = img_el.get('src', '') if img_el else ''

        # Link / TCIN
        link_el = card.select_one('a[href*="/p/"]')
        href = link_el.get('href', '') if link_el else ''
        m = re.search(r'/A-(\d+)', href)
        tcin = m.group(1) if m else ''

        # Sponsored?
        sp_el = card.select_one('[data-test="sponsoredText"]')
        is_sponsored = sp_el is not None

        # Rating
        rating_el = card.select_one('[aria-label*="star"]')
        rating = rating_el.get('aria-label', '')[:50] if rating_el else ''

        listings.append({
            'type': 'Product_Listing',
            'subtype': 'sponsored_product' if is_sponsored else 'organic_product',
            'product_id': tcin,
            'retailer_id_type': 'tcin',
            'title': title,
            'brand': brand,
            'price': price,
            'image_url': image_url,
            'href': href,
            'rating': rating,
            'is_sponsored': is_sponsored,
            'position': position,
        })
        position += 1

    return listings


# ── Instacart ─────────────────────────────────────────────────────────────────

def _extract_instacart(soup):
    """Extract product listings from Instacart saved HTML."""
    listings = []
    position = 0

    for item in soup.find_all(attrs={'data-testid': re.compile(r'^item_list_item_')}):
        # Skip items inside shoppable carousels (those are ad items)
        parent = item.parent
        inside_carousel = False
        for _ in range(15):
            if parent is None:
                break
            if parent.get('data-testid') == 'shoppable-list-sliding-carousel':
                inside_carousel = True
                break
            parent = parent.parent
        if inside_carousel:
            continue

        # Product ID from href
        link = item.select_one('a[href*="/products/"]')
        href = link.get('href', '') if link else ''
        m = re.search(r'/products/(\d+)', href)
        product_id = m.group(1) if m else ''

        # Title from button aria-label
        btn = item.select_one('button[aria-label*="Add"]')
        title = ''
        if btn:
            aria = btn.get('aria-label', '')
            m = re.match(r'Add \d+ item (.+)', aria)
            if m:
                title = m.group(1)

        # Price from text
        text = item.get_text(strip=True)
        price_match = re.search(r'\$(\d+\.\d{2})', text)
        price = price_match.group(0) if price_match else ''

        # Image from srcset
        img = item.select_one('img')
        image_url = ''
        if img:
            srcset = img.get('srcset', '')
            if srcset:
                image_url = srcset.split(',')[0].split(' ')[0]
            elif img.get('src'):
                image_url = img.get('src', '')

        # Size
        size_match = re.search(r'(\d+\.?\d*\s*(?:oz|fl oz|lb|ct|g|ml|L|pk|pack))', text)
        size = size_match.group(1) if size_match else ''

        listings.append({
            'type': 'Product_Listing',
            'subtype': 'organic_product',
            'product_id': product_id,
            'retailer_id_type': 'instacart_product_id',
            'title': title,
            'brand': None,
            'price': price,
            'image_url': image_url,
            'href': href,
            'size': size,
            'is_sponsored': False,
            'position': position,
        })
        position += 1

    return listings


# ── Public API ────────────────────────────────────────────────────────────────

_EXTRACTORS = {
    'amazon': _extract_amazon,
    'walmart': _extract_walmart,
    'kroger': _extract_kroger,
    'target': _extract_target,
    'instacart': _extract_instacart,
}


def extract_product_listings(retailer, html_path_or_content):
    """
    Extract product listings from saved HTML.

    Args:
        retailer: One of 'amazon', 'walmart', 'kroger', 'target', 'instacart'
        html_path_or_content: Either a file path (str) or raw HTML content (str).
            If it starts with '<' or contains '<html', treated as content;
            otherwise treated as a file path.

    Returns:
        List of product listing dicts, each with standardized fields.
    """
    retailer = retailer.lower()
    extractor = _EXTRACTORS.get(retailer)
    if not extractor:
        raise ValueError(f"Unknown retailer: {retailer}. Expected one of: {list(_EXTRACTORS.keys())}")

    # Determine if input is a path or raw HTML
    if isinstance(html_path_or_content, str) and not html_path_or_content.lstrip().startswith('<'):
        # Treat as file path
        with open(html_path_or_content, 'r', encoding='utf-8', errors='replace') as f:
            soup = BeautifulSoup(f, 'html.parser')
    else:
        soup = BeautifulSoup(html_path_or_content, 'html.parser')

    return extractor(soup)


# ── CLI for testing ───────────────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse
    import json

    parser = argparse.ArgumentParser(description='Extract product listings from saved HTML')
    parser.add_argument('retailer', choices=list(_EXTRACTORS.keys()))
    parser.add_argument('html_path')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    args = parser.parse_args()

    listings = extract_product_listings(args.retailer, args.html_path)

    if args.json:
        print(json.dumps(listings, indent=2, ensure_ascii=False))
    else:
        print(f"Extracted {len(listings)} product listings from {args.html_path}")
        sp = sum(1 for l in listings if l.get('is_sponsored'))
        org = len(listings) - sp
        print(f"  Sponsored: {sp}  Organic: {org}")
        for i, l in enumerate(listings[:10]):
            sp_tag = 'SP' if l.get('is_sponsored') else 'OR'
            print(f"  [{sp_tag}] pos={l.get('position'):>3}  id={l.get('product_id', ''):>15}  "
                  f"{l.get('price', ''):>8}  {l.get('title', '')[:50]}")
        if len(listings) > 10:
            print(f"  ... and {len(listings) - 10} more")
