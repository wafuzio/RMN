#!/usr/bin/env python3
"""Amazon Search and Capture Script (Modern Pattern)

Performs Amazon keyword search and captures assets during search:
- Main full-page screenshot
- Sponsored Brand Video (SBV) module screenshot (+ optional MP4)
- Sponsored Carousels (container-level screenshots)
- Sponsored Products aggregation with ASIN main image downloads

Outputs canonical JSON with flat ads[] array and saves HTML.
"""

import os
import json
import urllib.parse
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright
from browser_lock import single_browser_lock
import requests
import shutil
import hashlib
import re
import time
from core.brands import canonicalize, add_brand

# Brand logo database for centralized logo storage
try:
    from brand_logo_database import BrandLogoDatabase
except ImportError:
    BrandLogoDatabase = None

# Optional helpers with safe fallbacks
try:
    from retailers.amazon.helpers import (
        accept_amazon_cookies,
        ensure_amazon_logged_in,
        scroll_results,
        goto_with_retries,
    )
except Exception:
    def accept_amazon_cookies(page):
        try:
            page.click('input[name="accept"], button:has-text("Accept")', timeout=2000)
        except Exception:
            pass
    def ensure_amazon_logged_in(page):
        pass
    def scroll_results(page, max_loops=8, step_ratio=0.6, sleep_ms=300):
        for _ in range(max_loops):
            try:
                page.evaluate('window.scrollBy(0, window.innerHeight * 0.6)')
            except Exception:
                break
            try:
                time.sleep(max(0, float(sleep_ms) / 1000.0))
            except Exception:
                pass
    def goto_with_retries(page, url, attempts=3, wait_until="domcontentloaded", timeout_ms=45000):
        last_err = None
        for _ in range(attempts):
            try:
                page.goto(url, wait_until=wait_until, timeout=timeout_ms)
                return
            except Exception as e:
                last_err = e
                try:
                    time.sleep(1)
                except Exception:
                    pass
        if last_err:
            raise last_err

CAROUSEL_HEADINGS = [
    "Brands related to your search",
    "Shoppers also explored",
    "Trending now",
    "Popular products in this category",
    "Customers who viewed this item also viewed",
    "Customers mention"
]


def _slug(text: str) -> str:
    s = (text or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "unknown"


def _short_hash(s: str) -> str:
    try:
        return hashlib.md5((s or "").encode("utf-8")).hexdigest()[:8]
    except Exception:
        return "00000000"


def _first_nonempty(*vals):
    for v in vals:
        if v:
            return v
    return None


def _get_attr(locator, name: str):
    try:
        return locator.get_attribute(name)
    except Exception:
        return None


def _module_anchor(locator):
    # Prefer cel_widget_id then data-uuid then data-aid then data-cel-widget
    return _first_nonempty(
        _get_attr(locator, "cel_widget_id"),
        _get_attr(locator, "data-uuid"),
        _get_attr(locator, "data-aid"),
        _get_attr(locator, "data-cel-widget"),
    ) or "unknown"


def _extract_brand_and_message(container):
    brand = None
    message = None
    # Try aria-labels that include brand references
    try:
        al = container.locator('a[aria-label]')
        if al.count() > 0:
            label = (al.first.get_attribute('aria-label') or '').strip()
            # Strict pattern: "Sponsored ad from <Brand>" only
            # This avoids matching rating text like "from 756 reviews"
            m = re.search(r"Sponsored\s+ad\s+from\s+([^\.\"]+)", label, re.IGNORECASE)
            if m:
                brand = m.group(1).strip()

            # Ignore generic feedback UI such as "Leave feedback on Sponsored ad"
            is_feedback_ui = bool(re.search(r"leave\s+feedback\s+on\s+sponsored\s+ad", label, re.IGNORECASE))
            if not message and not is_feedback_ui:
                message = label
    except Exception:
        pass

    # SBV-specific: try video[aria-label] when we still don't have a brand
    if not brand:
        try:
            v = container.locator('video[aria-label]').first
            if v.count() > 0:
                v_label = (v.get_attribute('aria-label') or '').strip()
                # Split off the SBV preamble before the first '.'
                parts = v_label.split('.', 1)
                product_seg = parts[1].strip() if len(parts) == 2 else v_label
                tokens = product_seg.split()
                if tokens:
                    cand = tokens[0]
                    # Basic filters: non-empty, not purely numeric, not a review token
                    if cand and not re.match(r"^[0-9.,]+$", cand):
                        if not re.search(r"\breviews?\b", cand, re.IGNORECASE) \
                           and not re.search(r"\bout of 5 stars\b", cand, re.IGNORECASE) \
                           and not re.search(r"\brated\b", cand, re.IGNORECASE):
                            brand = cand
                if v_label and not message:
                    message = v_label
        except Exception:
            pass
    # Try logo alt
    if not brand:
        try:
            logos = container.locator('img[alt]').all()
            for logo in logos[:8]:  # Scan up to a few candidates to skip rating stars/UI icons
                alt = (logo.get_attribute('alt') or '').strip()
                if not alt:
                    continue
                # Heuristic: short alts likely brand names, but ignore rating/review-style and UI/badge alts
                tokens = alt.split()
                if not (1 <= len(tokens) <= 4):
                    continue
                # Filter out obvious non-brand patterns like review counts / star ratings
                if re.search(r"\breviews?\b", alt, re.IGNORECASE) \
                   or re.search(r"\bout of 5 stars\b", alt, re.IGNORECASE) \
                   or re.search(r"\brated\b", alt, re.IGNORECASE):
                    continue
                # Filter out generic UI/badge alts
                if re.search(r"thumbs?\s+up\s+feedback", alt, re.IGNORECASE) \
                   or re.search(r"thumbs?\s+down\s+feedback", alt, re.IGNORECASE) \
                   or re.search(r"\bscroll\b", alt, re.IGNORECASE) \
                   or re.search(r"\bicon\b", alt, re.IGNORECASE) \
                   or re.search(r"climate\s+pledge\s+friendly", alt, re.IGNORECASE):
                    continue
                # Skip alts that are mostly numeric (e.g. "4.4" or "4.4 756")
                numeric_like = sum(1 for t in tokens if re.match(r"^[0-9.,]+$", t))
                if numeric_like > len(tokens) / 2.0:
                    continue
                brand = alt
                break
        except Exception:
            pass
    # Try headline text as message/brand source
    try:
        head = container.locator('a[data-elementid="sb-headline"], h2').first
        if head.count() > 0:
            ht = (head.text_content() or '').strip()
            if ht:
                message = message or ht
                # Extract brand from "Shop <Brand>" or "Shop the <Brand> Store" patterns
                # Pattern 1: "Shop the <Brand> Store" (most specific)
                m2 = re.search(r"Shop\s+the\s+(.+?)\s+Store", ht, re.IGNORECASE)
                if m2 and not brand:
                    brand = m2.group(1).strip()
                # Pattern 2: "Shop <Brand>" at end of text
                if not brand:
                    m3 = re.search(r"Shop\s+([^|\n\r]+)$", ht)
                    if m3:
                        brand = m3.group(1).strip()

                # Display/SBV fallback: infer brand from leading tokens of product title
                if not brand:
                    # Use the text before the first '|' as the brand-bearing segment
                    title_seg = ht.split('|', 1)[0].strip()
                    t_tokens = title_seg.split()
                    if t_tokens:
                        # Collect non-numeric leading tokens (up to 3)
                        brand_tokens = []
                        for tok in t_tokens:
                            if any(ch.isdigit() for ch in tok):
                                break
                            brand_tokens.append(tok)
                            if len(brand_tokens) >= 3:
                                break

                        # Try progressively: 1 token, then 2, then 3
                        # This ensures "Rael" matches before "Rael Pimple" is considered
                        for n in range(1, len(brand_tokens) + 1):
                            cand = " ".join(brand_tokens[:n]).strip()
                            if not cand or re.match(r"^[0-9.,]+$", cand):
                                continue
                            if re.search(r"\breviews?\b", cand, re.IGNORECASE) \
                               or re.search(r"\bout of 5 stars\b", cand, re.IGNORECASE) \
                               or re.search(r"\brated\b", cand, re.IGNORECASE):
                                continue
                            # If this candidate already canonicalizes, use it immediately
                            if canonicalize(cand):
                                brand = cand
                                break
                        # If no n-gram matched the lexicon, fall back to first 2 tokens
                        if not brand and len(brand_tokens) >= 1:
                            cand = " ".join(brand_tokens[:min(2, len(brand_tokens))]).strip()
                            if cand and not re.match(r"^[0-9.,]+$", cand):
                                if not re.search(r"\breviews?\b", cand, re.IGNORECASE) \
                                   and not re.search(r"\bout of 5 stars\b", cand, re.IGNORECASE) \
                                   and not re.search(r"\brated\b", cand, re.IGNORECASE):
                                    brand = cand
    except Exception:
        pass

    # Try store links and href-based patterns when brand is still missing
    if not brand:
        try:
            store_link = container.locator('a[href*="/stores/"], a#bylineInfo').first
            if store_link.count() > 0:
                cand = ""
                txt = (store_link.inner_text() or '').strip()
                m = re.search(r"Visit\s+the\s+(.+?)\s+Store", txt, re.IGNORECASE)
                if m:
                    cand = m.group(1).strip()
                else:
                    href = (store_link.get_attribute('href') or '').strip()
                    # Match brand store URLs like /stores/BrandName or /stores/BrandName/page/...
                    # But NOT /stores/page/UUID which is a generic store page
                    m2 = re.search(r"/stores/([^/?#]+)", href)
                    if m2:
                        segment = m2.group(1).strip()
                        # Skip "page" - it's a URL structure element, not a brand
                        if segment.lower() != 'page':
                            cand = segment.replace('-', ' ').replace('_', ' ').strip()
                if cand and not re.match(r"^[0-9.,]+$", cand):
                    if not re.search(r"\breviews?\b", cand, re.IGNORECASE) \
                       and not re.search(r"\bout of 5 stars\b", cand, re.IGNORECASE) \
                       and not re.search(r"\brated\b", cand, re.IGNORECASE):
                        brand = cand
        except Exception:
            pass

    if not brand:
        try:
            prod_link = container.locator('a[href*="/dp/"], a[href*="/gp/"]').first
            if prod_link.count() > 0:
                href = (prod_link.get_attribute('href') or '').strip()
                path = href.split('?', 1)[0]
                m = re.search(r"/([^/]+)/dp/", path)
                if m:
                    slug = m.group(1).replace('-', ' ').replace('_', ' ').strip()
                    tokens = slug.split()
                    brand_tokens = []
                    for tok in tokens:
                        if any(ch.isdigit() for ch in tok):
                            break
                        brand_tokens.append(tok)
                        if len(brand_tokens) >= 3:
                            break
                    # Try progressively: 1 token, then 2, then 3
                    for n in range(1, len(brand_tokens) + 1):
                        cand = " ".join(brand_tokens[:n]).strip()
                        if not cand or re.match(r"^[0-9.,]+$", cand):
                            continue
                        if re.search(r"\breviews?\b", cand, re.IGNORECASE) \
                           or re.search(r"\bout of 5 stars\b", cand, re.IGNORECASE) \
                           or re.search(r"\brated\b", cand, re.IGNORECASE):
                            continue
                        if canonicalize(cand):
                            brand = cand
                            break
                    if not brand and len(brand_tokens) >= 1:
                        cand = " ".join(brand_tokens[:min(2, len(brand_tokens))]).strip()
                        if cand and not re.match(r"^[0-9.,]+$", cand):
                            if not re.search(r"\breviews?\b", cand, re.IGNORECASE) \
                               and not re.search(r"\bout of 5 stars\b", cand, re.IGNORECASE) \
                               and not re.search(r"\brated\b", cand, re.IGNORECASE):
                                brand = cand
        except Exception:
            pass
    
    # Final fallback: search the message itself for brand patterns
    if not brand and message:
        # "Shop the <Brand> Store" pattern in message
        m = re.search(r"Shop\s+the\s+(.+?)\s+Store", message, re.IGNORECASE)
        if m:
            brand = m.group(1).strip()
        # "Visit the <Brand> Store" pattern
        if not brand:
            m = re.search(r"Visit\s+the\s+(.+?)\s+Store", message, re.IGNORECASE)
            if m:
                brand = m.group(1).strip()
    
    # Canonicalize brand
    brand_canon = None
    try:
        if brand:
            brand_canon = canonicalize(brand)
            # Add new brand to lexicon if not already there
            if not brand_canon and brand.lower() not in ('unknown', ''):
                add_brand(brand)
                brand_canon = brand.strip().title()
    except Exception:
        brand_canon = None
    return brand, brand_canon, (message or "")


def _try_hybrid_extraction(container):
    """
    Hybrid fallback for Sponsored Display ads (Iframe Piercing + Positional Matching).
    Strategies:
    1. Gemini: Pierce iframe to find hidden metadata (store links, alt text).
    2. Opus: Match outer DOM accessibility text via geometric proximity.
    """
    brand = None
    message = None
    
    try:
        # Strategy 1: Iframe Piercing (Gemini)
        # Try to find an iframe within the container
        iframe = container.locator('iframe').first
        if iframe.count() > 0:
            try:
                frame = iframe.content_frame
                if frame:
                    # 1a. Body Text Parsing (Most Reliable per Diagnostic Probe)
                    # The probe showed text like: "Sponsored Ad. Brand logo. Product image. Life Extension Hair Growth..."
                    try:
                        body_text = frame.locator('body').inner_text()
                        if body_text:
                            # Clean up text
                            clean_text = re.sub(r'\s+', ' ', body_text).strip()
                            
                            # Pattern 1: "Sponsored Ad. Brand logo. Product image. [Brand] ..."
                            # Remove common prefixes to reveal the start of the actual content (usually Brand)
                            content_text = re.sub(r'^(Sponsored Ad\.?|Brand logo\.?|Branded image\.?|Product image\.?|Shop now\.?|\s+)+', '', clean_text, flags=re.IGNORECASE)
                            
                            # The remaining text usually starts with the Brand + Product Title
                            # Try to match against lexicon, progressively shorter
                            if content_text:
                                parts = content_text.split()
                                if parts:
                                    # Try lexicon match: 3 words, 2 words, 1 word
                                    for n in (3, 2, 1):
                                        if n > len(parts):
                                            continue
                                        cand = " ".join(parts[:n])
                                        cand = re.sub(r'[^\w\s&\'\.-]', '', cand).strip()
                                        if not cand:
                                            continue
                                        canon = canonicalize(cand)
                                        if canon and canon.lower() != cand.lower():
                                            # Lexicon matched — use canonical name
                                            brand = canon
                                            break
                                        elif canon:
                                            brand = canon
                                            break
                                    
                                    # If no lexicon match, refine via store link URL
                                    if not brand:
                                        store_links = frame.locator('a[href*="/stores/"]').all()
                                        if store_links:
                                            href = store_links[0].get_attribute('href')
                                            m_store = re.search(r"/stores/([^/?#]+)", href or "")
                                            if m_store:
                                                store_slug = m_store.group(1).replace('-', ' ').replace('_', ' ')
                                                if len(store_slug) > 2:
                                                    brand = store_slug.title()
                                    
                                    # Last resort: use first word only (safest — avoids product descriptors)
                                    if not brand and len(parts[0]) > 2:
                                        cand = re.sub(r'[^\w\s&\'\.-]', '', parts[0]).strip()
                                        if len(cand) > 2:
                                            brand = cand
                    except Exception:
                        pass

                    # 1b. Fallback: "Visit the [Brand] Store" links (if present)
                    if not brand:
                        store_link = frame.locator('a[href*="/stores/"]').first
                        if store_link.count() > 0:
                            txt = (store_link.inner_text() or '').strip()
                            m = re.search(r"Visit\s+the\s+(.+?)\s+Store", txt, re.IGNORECASE)
                            if m:
                                brand = m.group(1).strip()
                            else:
                                href = store_link.get_attribute('href') or ''
                                m2 = re.search(r"/stores/([^/?#]+)", href)
                                if m2:
                                    cand = m2.group(1).strip()
                                    if cand.lower() not in ('page', 'homepage'):
                                        brand = cand.replace('-', ' ').replace('_', ' ').strip()
                    
                    # 1c. Fallback: Aria-labels
                    if not brand:
                        lbl = frame.locator('div[aria-label*="Sponsored ad from"], a[aria-label*="Sponsored ad from"]').first
                        if lbl.count() > 0:
                            al = lbl.get_attribute('aria-label')
                            m = re.search(r"Sponsored\s+ad\s+from\s+([^\.]+)", al, re.IGNORECASE)
                            if m:
                                brand = m.group(1).strip()
                    
                    # 1d. Fallback: Image Alts (least reliable)
                    if not brand:
                        logos = frame.locator('img[alt]').all()
                        for logo in logos[:3]:
                            alt = (logo.get_attribute('alt') or '').strip()
                            if not alt: continue
                            if any(x in alt.lower() for x in ['sponsored', 'click', 'shop', 'review', 'star', 'rating', 'brand logo', 'product image']):
                                continue
                            if len(alt) < 30:
                                brand = alt
                                break
            except Exception:
                pass # Cross-origin access denied or frame closed

        # Strategy 2: Positional Matching (Opus)
        # If we couldn't get it from the iframe (e.g. cross-origin), try the outer DOM
        if not brand:
            try:
                box = container.bounding_box()
                if box:
                    # Define search area (expanded slightly around the ad)
                    search_area = {
                        "x": box["x"] - 50,
                        "y": box["y"] - 50,
                        "width": box["width"] + 100,
                        "height": box["height"] + 100
                    }
                    
                    # Scan for accessibility spans on the page
                    # We can't query "in rect" easily, so we query all offscreen spans and check coords
                    # Optimization: Limit to reasonable number if page is huge?
                    spans = container.page.locator('span.a-offscreen, span.aok-offscreen').all()
                    
                    for span in spans:
                        try:
                            # Only check spans that contain "Sponsored Ad"
                            # This avoids expensive bounding_box calls on irrelevant elements
                            txt = (span.inner_text() or '').strip()
                            if "Sponsored Ad" not in txt:
                                continue

                            s_box = span.bounding_box()
                            if not s_box:
                                continue
                                
                            # Check center point inclusion
                            sx = s_box["x"] + s_box["width"]/2
                            sy = s_box["y"] + s_box["height"]/2
                            
                            if (search_area["x"] <= sx <= search_area["x"] + search_area["width"] and
                                search_area["y"] <= sy <= search_area["y"] + search_area["height"]):
                                
                                # Found a nearby label! Parse it.
                                # Format 1: "Sponsored Ad.\n[Brand] logo.\n..."
                                m_logo = re.search(r"Sponsored\s+Ad.*?\n(.+?)\s+logo", txt, re.IGNORECASE | re.DOTALL)
                                if m_logo:
                                    brand = m_logo.group(1).strip()
                                
                                # Format 2: "Sponsored Ad - [Brand] - [Title]"
                                if not brand:
                                    # Split by hyphens or newlines
                                    parts = [p.strip() for p in re.split(r'[-\n]', txt) if p.strip()]
                                    # Usually [0]=Sponsored Ad, [1]=Brand
                                    if len(parts) >= 2 and "Sponsored" in parts[0]:
                                        cand = parts[1]
                                        if len(cand) < 40 and "logo" not in cand.lower():
                                            brand = cand
                                
                                if brand:
                                    message = txt
                                    break # Found match for this ad
                        except Exception:
                            continue
            except Exception:
                pass

    except Exception:
        pass
        
    return brand, message


def _build_ids(retailer_type: str, subtype: str, brand_canon: str, anchor: str, run_id: str, pos: int = 0):
    sub = _slug(subtype)
    bc = _slug(brand_canon or "unknown")
    anch = _slug(anchor)
    module_id = f"amazon::{_slug(retailer_type)}::{sub}::{bc}::{anch}"
    eid = f"amazon::{run_id}::{_short_hash(module_id)}::{pos}"
    return module_id, eid


def _search_url(keyword: str, page: int = 1) -> str:
    base = "https://www.amazon.com/s"
    return f"{base}?{urllib.parse.urlencode({'k': keyword, 'page': page})}"


def _std_filename(retailer: str, advertiser: str, ad_type: str, client: str, keyword: str, run_id: str, index: int, ext: str) -> str:
    r = (retailer or "").strip().lower().replace(" ", "_")
    adv = (advertiser or "unknown").strip().lower().replace(" ", "_") or "unknown"
    typ = (ad_type or "").strip().replace(" ", "_")
    cli = (client or "").strip().lower().replace(" ", "_")
    kw = (keyword or "").strip().lower().replace(" ", "_")
    try:
        dt = datetime.strptime(run_id, "%Y%m%d%H%M%S")
    except Exception:
        dt = datetime.utcnow()
    d = dt.strftime("D%Y-%m-%d")
    tstr = dt.strftime("T%H-%M.%S")
    return f"{r}__{adv}__{typ}__{cli}__{kw}__{d}_{tstr}_{index}{ext}"


def _get_container_signature(container):
    """Generate a unique signature for a container based on ID and metrics attributes."""
    try:
        # Priority: CardInstance ID > data-card-metrics-id > cel_widget_id > data-aid
        container_id = _get_attr(container, 'id') or ''
        if container_id.startswith('CardInstance'):
            return f"card:{container_id}"
        
        metrics_id = _get_attr(container, 'data-card-metrics-id') or ''
        if 'sb-themed-collection' in metrics_id:
            return f"metrics:{metrics_id}"
        
        cel_widget = _get_attr(container, 'cel_widget_id') or ''
        if cel_widget:
            return f"cel:{cel_widget}"
        
        data_aid = _get_attr(container, 'data-aid') or ''
        if data_aid:
            return f"aid:{data_aid}"
        
        return None
    except Exception:
        return None


def _normalize_sb_container(el):
    """
    Given any node in a Sponsored Brand module, return the top-level SB container:
    - id starts with CardInstance (v2)
    - or has data-card-metrics-id containing 'sb-themed-collection' (v2)
    - or cel_widget_id contains 'sb-themed-collection' (v1)
    Returns the same node if no better ancestor found.
    """
    try:
        c = el.locator("xpath=ancestor::div[starts-with(@id,'CardInstance')][1]")
        if c.count() > 0:
            return c.first
        c = el.locator("xpath=ancestor::div[contains(@data-card-metrics-id,'sb-themed-collection')][1]")
        if c.count() > 0:
            return c.first
        c = el.locator("xpath=ancestor::div[contains(@cel_widget_id,'sb-themed-collection')][1]")
        if c.count() > 0:
            return c.first
    except Exception:
        pass
    return el


def _is_sb_container(el):
    """
    True if el is a Sponsored Brand container (metrics/headline/aria evidence).
    NOTE: This is ONLY for traditional Sponsored Brands, NOT Brand Cards.
    """
    try:
        m = el.get_attribute("data-card-metrics-id") or ""
        if "sb-themed-collection" in m:
            return True
    except Exception:
        pass
    try:
        c = el.get_attribute("cel_widget_id") or ""
        if "sb-themed-collection" in c:
            return True
    except Exception:
        pass
    try:
        if el.locator("a[data-elementid='sb-headline']").count() > 0:
            return True
        if el.locator("a[aria-label*='Sponsored ad from']").count() > 0:
            return True
    except Exception:
        return None


def _normalize_display_container(el):
    """
    Return a stable, canonical display ad container so cropping is consistent
    and dedupe works. Prefer AdHolder; fall back to desktop-ad-* wrapper.
    """
    try:
        c = el.locator("xpath=ancestor::div[contains(@class,'AdHolder')][1]")
        if c.count() > 0:
            return c.first
        c = el.locator("xpath=ancestor::div[starts-with(@id,'desktop-ad') or contains(@id,'desktop-ad-')][1]")
        if c.count() > 0:
            return c.first
        c = el.locator("xpath=ancestor::div[contains(@id,'ad-creative') or contains(@id,'adv-creative')][1]")
        if c.count() > 0:
            return c.first
    except Exception:
        pass
    return el


MIN_DISPLAY_SCREENSHOT_BYTES = 5000  # Screenshots below this are almost certainly blank/unloaded
MAX_DISPLAY_AD_HEIGHT = 800  # Cap iframe expansion to prevent capturing entire page


def _is_blank_screenshot(fpath):
    """Return True if a screenshot file is blank (too small to contain real ad content)."""
    try:
        return os.path.getsize(fpath) < MIN_DISPLAY_SCREENSHOT_BYTES
    except OSError:
        return True


def _display_screenshot_target(el):
    """
    Given a display ad container (e.g. AdHolder), return the innermost
    visual element to screenshot — the iframe or primary image.
    Falls back to the container itself if nothing better is found.
    """
    try:
        # Prefer iframe — this IS the ad creative
        iframes = el.locator("iframe")
        if iframes.count() > 0:
            iframe = iframes.first
            if iframe.is_visible():
                return iframe
        # Fallback: largest visible image
        imgs = el.locator("img").all()
        best, best_area = None, 0
        for img in imgs:
            try:
                if not img.is_visible():
                    continue
                box = img.bounding_box()
                if box:
                    area = box["width"] * box["height"]
                    if area > best_area:
                        best, best_area = img, area
            except Exception:
                continue
        if best and best_area > 500:
            return best
    except Exception:
        pass
    return el


def _wait_for_iframe_content(page, el, timeout_ms=4000):
    """
    Wait for iframe-based display ads to load their creative content.
    Returns True if content appears loaded, False otherwise.
    """
    try:
        ad_handle = el.element_handle()
        loaded = page.evaluate("""
          (el) => new Promise((resolve) => {
            const sleep = (ms) => new Promise(r => setTimeout(r, ms));
            (async () => {
              // First check for iframes
              const iframe = el.tagName === 'IFRAME' ? el : el.querySelector('iframe');
              if (!iframe) {
                // No iframe — check for direct images instead
                let stable = 0, last = 0;
                for (let i = 0; i < 10 && stable < 3; i++) {
                  const imgs = Array.from(el.querySelectorAll('img')).filter(img => img.complete && img.naturalWidth > 10).length;
                  const content = el.textContent.trim().length;
                  const current = imgs + Math.floor(content / 100);
                  if (current === last) stable++; else stable = 0;
                  last = current;
                  await sleep(300);
                }
                resolve(last > 0);
                return;
              }
              // For iframe-based ads, wait for the iframe to load
              // and have non-trivial dimensions or visible content
              let attempts = 0;
              const maxAttempts = Math.floor(arguments.length > 1 ? arguments[1] : 4000 / 400);
              while (attempts < 12) {
                attempts++;
                try {
                  // Check if iframe has loaded (cross-origin safe checks)
                  const rect = iframe.getBoundingClientRect();
                  const hasSize = rect.width > 50 && rect.height > 20;
                  // Try to check iframe content (same-origin only)
                  let hasContent = false;
                  try {
                    const doc = iframe.contentDocument || iframe.contentWindow.document;
                    if (doc && doc.body) {
                      const bodyHTML = doc.body.innerHTML || '';
                      hasContent = bodyHTML.length > 100;
                    }
                  } catch(e) {
                    // Cross-origin: check if iframe has a valid src and rendered height
                    const src = iframe.src || iframe.getAttribute('src') || '';
                    hasContent = src.length > 10 && rect.height > 30;
                  }
                  if (hasSize && hasContent) {
                    resolve(true);
                    return;
                  }
                } catch(e) {}
                await sleep(400);
              }
              resolve(false);
            })()
          })
        """, ad_handle)
        return bool(loaded)
    except Exception:
        return False


def _creative_fingerprint(el):
    """
    Build a stable fingerprint for an ad creative from image srcs + link hrefs.
    This collapses duplicates even when different DOM nodes are selected.
    """
    try:
        # Collect image URLs and hrefs; strip query noise
        imgs = el.locator("img[src]").all()
        srcs = set()
        for i in imgs:
            s = (i.get_attribute("src") or "").split("?")[0]
            if s:
                srcs.add(s)
        links = el.locator("a[href]").all()
        hrefs = set()
        for a in links:
            h = a.get_attribute("href") or ""
            if h:
                hrefs.add(h)
        key = "|".join(sorted(srcs)) + "||" + "|".join(sorted(hrefs))
        return hashlib.md5(key.encode("utf-8")).hexdigest() if key else None
    except Exception:
        return None


def _center_card_horizontally(card):
    """
    For horizontally scrolling brand carousels, center a given card in its scrollable parent.
    """
    try:
        handle = card.element_handle()
        card.page.evaluate("""
            (el) => {
                // find nearest horizontally scrollable ancestor
                function getScrollableAncestor(n) {
                    while (n && n !== document.body) {
                        const st = getComputedStyle(n);
                        if (/auto|scroll/.test(st.overflowX)) return n;
                        n = n.parentElement;
                    }
                    return null;
                }
                const parent = getScrollableAncestor(el);
                if (parent) {
                    const r = el.getBoundingClientRect();
                    const pr = parent.getBoundingClientRect();
                    const target = parent.scrollLeft + (r.left - pr.left) - (parent.clientWidth - r.width)/2;
                    parent.scrollLeft = Math.max(0, target);
                } else {
                    el.scrollIntoView({block: 'center', inline: 'center'});
                }
            }
        """, handle)
    except Exception:
        pass


def _check_bbox_overlap(new_bbox, existing_bboxes, overlap_threshold=0.3):
    """Check if new bounding box overlaps significantly with any existing ones."""
    try:
        if not new_bbox or not existing_bboxes:
            return False
        
        nx1, ny1, nx2, ny2 = new_bbox['x'], new_bbox['y'], new_bbox['x'] + new_bbox['width'], new_bbox['y'] + new_bbox['height']
        new_area = new_bbox['width'] * new_bbox['height']
        
        for existing in existing_bboxes:
            ex1, ey1, ex2, ey2 = existing['x'], existing['y'], existing['x'] + existing['width'], existing['y'] + existing['height']
            
            # Calculate intersection
            ix1, iy1 = max(nx1, ex1), max(ny1, ey1)
            ix2, iy2 = min(nx2, ex2), min(ny2, ey2)
            
            if ix1 < ix2 and iy1 < iy2:
                intersection_area = (ix2 - ix1) * (iy2 - iy1)
                overlap_ratio = intersection_area / new_area
                if overlap_ratio > overlap_threshold:
                    return True
        return False
    except Exception:
        return False


def search_and_capture(keyword: str, output_dir: str) -> bool:
    print("\n==================================================")
    print("AMAZON SEARCH AND CAPTURE")
    print("==================================================")
    print(f"Keyword: {keyword}")
    print(f"Output directory: {output_dir}")

    # Force Amazon to use its own profile, not walmart
    amazon_profile = os.path.expanduser("~/ChromeProfiles/amazon")
    profile_dir = os.environ.get("AMAZON_PROFILE_DIR") or amazon_profile
    # Ensure we're not accidentally using walmart profile
    if "walmart" in profile_dir.lower():
        log(f"WARNING: Detected walmart profile path '{profile_dir}', forcing to Amazon profile")
        profile_dir = amazon_profile
    try:
        os.makedirs(profile_dir, exist_ok=True)
    except Exception as e:
        print(f"❌ Could not prepare profile dir {profile_dir}: {e}")
        return False
    print(f"Using profile: {profile_dir}")

    client = os.path.basename(output_dir.rstrip('/')) or "unknown"
    run_id = datetime.now().strftime("%Y%m%d%H%M%S")  # Canonical 14-digit format
    runs_dir = os.path.join(output_dir, "runs")
    os.makedirs(runs_dir, exist_ok=True)

    html_path = os.path.join(runs_dir, f"search_results_amazon_{client}_{run_id}.html")
    json_path = os.path.join(runs_dir, f"run_results_amazon_{client}_{run_id}.json")
    debug_log = os.path.join(runs_dir, f"capture_debug_{run_id}.log")
    project_root = Path(__file__).resolve().parent
    central_asin_dir = project_root / "assets" / "amazon" / "ASIN_Images"
    try:
        central_asin_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    def log(msg: str):
        print(msg)
        try:
            with open(debug_log, 'a', encoding='utf-8') as f:
                f.write(f"{datetime.now().isoformat()} {msg}\n")
        except Exception:
            pass

    log("bootstrap: start")

    ads = []
    captured_modules = set()
    seen_anchors = set()
    # Additional dedupe mechanisms for SB modules
    captured_containers = set()  # Container signature dedupe (ID/metrics-based)
    captured_bboxes = []  # Geometric overlap check (bounding boxes)
    seen_video_hashes = set()  # SBV dedupe by video source
    # Display ad dedupe mechanisms (separate slots so left rail and bottom don't dedupe each other)
    captured_display_fingerprints = set()
    captured_display_bboxes = []
    captured_left_display_fingerprints = set()
    captured_left_display_bboxes = []
    captured_bottom_display_fingerprints = set()
    captured_bottom_display_bboxes = []
    success = False

    # Performance controls and time budget
    BUDGET_SEC = int(os.environ.get("AMAZON_BUDGET_SEC", "120"))
    MAX_SP = int(os.environ.get("AMAZON_MAX_SP", "12"))
    MAX_CAR = int(os.environ.get("AMAZON_MAX_CAR", "1"))
    MAX_LEFT_DISPLAY = int(os.environ.get("AMAZON_MAX_LEFT_DISPLAY", "2"))
    MAX_BOTTOM_DISPLAY = int(os.environ.get("AMAZON_MAX_BOTTOM_DISPLAY", "2"))
    log(f"debug: limits BUDGET_SEC={BUDGET_SEC} MAX_SP={MAX_SP} MAX_CAR={MAX_CAR} MAX_LEFT_DISPLAY={MAX_LEFT_DISPLAY} MAX_BOTTOM_DISPLAY={MAX_BOTTOM_DISPLAY}")
    deadline = time.time() + BUDGET_SEC
    def time_left():
        try:
            return max(0, deadline - time.time())
        except Exception:
            return 0

    # Use a dedicated Amazon lock file so we don't collide with other retailers.
    amazon_lock_path = os.environ.get("AMAZON_LOCK_PATH", "/tmp/amazon_playwright_browser.lock")
    log(f"debug: about to acquire single_browser_lock path={amazon_lock_path}")
    try:
        with single_browser_lock(timeout=600, path=amazon_lock_path):
            log("debug: acquired single_browser_lock")
            p = sync_playwright().start()
            bctx = None
            try:
                try:
                    bctx = p.chromium.launch_persistent_context(
                        user_data_dir=profile_dir,
                        channel="chrome",
                        headless=False,
                        viewport={"width": 1400, "height": 900},
                        locale="en-US",
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--no-default-browser-check",
                            "--disable-features=IsolateOrigins,site-per-process",
                            # Keep window visible but don't steal focus
                            "--disable-focus-on-load",
                            "--noerrdialogs",
                        ],
                    )
                except Exception as e:
                    log(f"launch: chrome channel failed -> {e}; retry with default chromium")
                    bctx = p.chromium.launch_persistent_context(
                        user_data_dir=profile_dir,
                        headless=False,
                        viewport={"width": 1400, "height": 900},
                        locale="en-US",
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--no-default-browser-check",
                            "--disable-features=IsolateOrigins,site-per-process",
                            # Keep window visible but don't steal focus
                            "--disable-focus-on-load",
                            "--noerrdialogs",
                        ],
                    )
                page = bctx.new_page()

                # Wire minimal browser events (avoid noisy response logs)
                try:
                    page.on("console", lambda m: log(f"[console:{m.type}] {m.text}"))
                    page.on("pageerror", lambda e: log(f"[pageerror] {e}"))
                    page.on("requestfailed", lambda r: log(f"[requestfailed] {r.method()} {r.url}"))
                except Exception:
                    pass

                # Start tracing only if enabled
                tracing_enabled = False
                try:
                    if os.environ.get("AMAZON_TRACE") == "1":
                        bctx.tracing.start(screenshots=True, snapshots=True, sources=False)
                        tracing_enabled = True
                        log("trace: started")
                except Exception as e:
                    log(f"trace: start error -> {e}")

                url = _search_url(keyword)
                log(f"navigate: {url}")
                goto_with_retries(page, url, attempts=3, wait_until="domcontentloaded", timeout_ms=45000)

                log("cookies/login")
                accept_amazon_cookies(page)
                ensure_amazon_logged_in(page)

                # Wait readiness heuristics
                try:
                    page.wait_for_selector('div[data-component-type="s-search-result"]', timeout=8000)
                    log("ready: s-search-result present")
                except Exception as e:
                    log(f"ready: timeout waiting for results -> {e}")
                    try:
                        time.sleep(3)
                    except Exception:
                        pass

                log("scrolling")
                try:
                    page.evaluate("""
                  () => new Promise((resolve) => {
                    const sleep = (ms) => new Promise(r => setTimeout(r, ms));
                    (async () => {
                      let stable = 0; let last = 0;
                      for (let i=0; i<12 && stable<3; i++) {
                        const imgs = document.querySelectorAll('img');
                        const loaded = Array.from(imgs).filter(i => i.complete && i.naturalWidth > 10).length;
                        if (loaded === last) stable++; else stable = 0;
                        last = loaded; await sleep(600);
                      }
                      resolve(true);
                    })()
                  })
                """)
                    log("scrolling: bottom images settled")
                except Exception as e:
                    log(f"scrolling: settle error -> {e}")

                # Create output folders
                for folder in [
                    "Main",
                    "Sponsored_Brand_Video",
                    "Sponsored_Brand",
                    "Sponsored_Carousel",
                    "Sponsored_Display",
                    "ASIN_Images",
                ]:
                    os.makedirs(os.path.join(output_dir, folder), exist_ok=True)

                # 1) Main full-page screenshot (hide sticky headers before capture)
                try:
                    log("main: prepare (hide sticky headers, scroll top)")
                    # Hide Amazon sticky headers/navs to avoid covering content (fast inline style injection)
                    try:
                        log("main: injecting CSS to hide sticky headers")
                        result = page.evaluate("""
                        () => {
                          try {
                            const css = '#navbar,#nav-belt,#nav-main,#nav-progressive-subnav,header,[data-testid="header"],[class*="sticky" i],[data-sticky],[style*="position: sticky"],.sg-col-20-of-24 .s-desktop-width-max .s-desktop-toolbar,.s-desktop-toolbar .s-desktop-toolbar{display:none!important;visibility:hidden!important;}';
                            const st = document.createElement('style');
                            st.type = 'text/css';
                            st.textContent = css;
                            document.head.appendChild(st);
                            return 'success';
                          } catch(e) {
                            return 'error: ' + e.message;
                          }
                        }
                        """)
                        log(f"main: CSS injection result -> {result}")
                    except Exception as css_err:
                        log(f"main: style inject error -> {css_err}")
                    # Ensure we are at the very top for consistent full-page shot
                    try:
                        page.evaluate("window.scrollTo(0, 0)")
                        try:
                            time.sleep(0.3)
                        except Exception:
                            pass
                    except Exception:
                        pass
                    # Left-rail hydration probe before main screenshot
                    try:
                        log("main: left-rail hydration probe")
                        left_rail_ads = page.locator('div.s-left-ads-item img')
                        if left_rail_ads.count() > 0:
                            # Wait for first left-rail image to load
                            try:
                                left_rail_ads.first.wait_for(state="visible", timeout=2000)
                                time.sleep(0.5)  # Brief settle time
                            except Exception:
                                pass
                        log("main: hydration probe complete")
                    except Exception as e:
                        log(f"main: hydration probe error -> {e}")
                    
                    # Simple scroll to bottom to trigger lazy loading
                    try:
                        log("main: scroll to bottom to trigger lazy loading")
                        
                        # Start at top
                        page.evaluate("window.scrollTo(0, 0)")
                        time.sleep(0.5)

                        steps = 8
                        try:
                            for _ in range(steps):
                                page.mouse.wheel(0, 900)
                                time.sleep(0.7)
                        except Exception as scroll_err:
                            log(f"main: stepped scroll error -> {scroll_err}")
                        log("main: stepped scroll complete")

                        try:
                            log("main: carousel hydration probe")
                            carousels = page.locator('span[data-component-type="s-searchgrid-carousel"]')
                            car_count = carousels.count()
                            log(f"main: found {car_count} carousel containers for hydration")
                            for idx in range(min(car_count, 6)):
                                try:
                                    carousels.nth(idx).scroll_into_view_if_needed()
                                    time.sleep(0.5)
                                except Exception as e:
                                    log(f"main: carousel hydration error idx={idx} -> {e}")
                        except Exception as e:
                            log(f"main: carousel hydration probe error -> {e}")

                        # Center on "Brands related to your search" element for screenshot
                        try:
                            log("main: centering on 'Brands related to your search' element")
                            brands_element = page.locator('span[aria-label="Brands related to your search"], h2:has-text("Brands related to your search")').first
                            if brands_element.count() > 0:
                                # Scroll element to center of viewport
                                brands_element.scroll_into_view_if_needed()
                                time.sleep(0.5)
                                
                                # Center the element in viewport using JavaScript
                                page.evaluate("""
                                (element) => {
                                    const rect = element.getBoundingClientRect();
                                    const elementTop = rect.top + window.pageYOffset;
                                    const elementCenter = elementTop - (window.innerHeight / 2) + (rect.height / 2);
                                    window.scrollTo(0, Math.max(0, elementCenter));
                                }
                                """, brands_element.element_handle())
                                
                                time.sleep(2.0)  # Wait 2 seconds as requested
                                log("main: centered on brands element and waited 2 seconds")
                            else:
                                # Fallback: return to top if brands element not found
                                page.evaluate("window.scrollTo(0, 0)")
                                time.sleep(1.5)
                                log("main: brands element not found, returned to top")
                        except Exception as e:
                            log(f"main: center on brands error -> {e}, falling back to top")
                            page.evaluate("window.scrollTo(0, 0)")
                            time.sleep(1.5)
                        
                        log("main: gentle scroll complete")
                    except Exception as e:
                        log(f"main: progressive scroll error -> {e}")
                    
                    # Re-inject CSS to hide sticky AND fixed elements that cause
                    # duplication in Playwright's full_page stitching
                    try:
                        log("main: re-injecting CSS before screenshot")
                        page.evaluate("""
                        () => {
                          const css = '#navbar,#nav-belt,#nav-main,#nav-progressive-subnav,header,[data-testid="header"],[class*="sticky" i],[data-sticky],[style*="position: sticky"],[style*="position: fixed"],.sg-col-20-of-24 .s-desktop-width-max .s-desktop-toolbar,.s-desktop-toolbar .s-desktop-toolbar{display:none!important;visibility:hidden!important;}';
                          const st = document.createElement('style');
                          st.type = 'text/css';
                          st.textContent = css;
                          document.head.appendChild(st);
                          // Also force-remove position:fixed from all elements to prevent
                          // duplication in Playwright's full-page stitching
                          document.querySelectorAll('*').forEach(el => {
                            const cs = getComputedStyle(el);
                            if (cs.position === 'fixed' || cs.position === 'sticky') {
                              el.style.setProperty('position', 'absolute', 'important');
                            }
                          });
                        }
                        """)
                    except Exception as e:
                        log(f"main: re-inject CSS error -> {e}")
                    
                    # Scroll back to top before screenshot — Playwright's full_page=True
                    # internally scrolls and stitches viewport captures. Starting from a
                    # mid-page position causes duplicated/overlapping regions.
                    try:
                        page.evaluate("window.scrollTo(0, 0)")
                        time.sleep(0.5)
                        log("main: scrolled to top before screenshot")
                    except Exception:
                        pass
                    
                    log("main: screenshot")
                    main_name = _std_filename("amazon", "search_results", "Main", client, keyword, run_id, 0, ".png")
                    main_path = os.path.join(output_dir, "Main", main_name)

                    screenshot_ok = False
                    try:
                        page.screenshot(path=main_path, full_page=True, timeout=10000)
                        screenshot_ok = True
                    except Exception as e:
                        log(f"main: primary screenshot error -> {e}")
                        # Fallback: element-based screenshot of the full HTML root
                        try:
                            log("main: screenshot fallback via html locator")
                            page.locator("html").screenshot(path=main_path)
                            screenshot_ok = True
                        except Exception as e2:
                            log(f"main: screenshot fallback fail -> {e2}")

                    # Canonical HTML snapshot: tie DOM to the main screenshot moment
                    try:
                        log("html: save")
                        html_content = page.content()
                        with open(html_path, "w", encoding="utf-8") as f:
                            f.write(html_content)
                        log(f"html: saved -> {html_path} exists={os.path.exists(html_path)} size={os.path.getsize(html_path) if os.path.exists(html_path) else 0}")
                    except Exception as e:
                        log(f"html: save error -> {e}")
                    log(f"main: saved -> {main_path} exists={os.path.exists(main_path)} size={os.path.getsize(main_path) if os.path.exists(main_path) else 0}")
                except Exception as e:
                    log(f"main: fail -> {e}")

                # 2) Sponsored Brand Video (SBV) - Comprehensive
                try:
                    log("sbv: detect")
                    # Optional quick markers (to verify in logs)
                    video_single_count = page.locator('*[cel_widget_id^="VIDEO_SINGLE_PRODUCT"]').count()
                    sbv_video_count = page.locator('*[cel_widget_id*="sbv-video-single-product"]').count()
                    sbv_search_count = page.locator('*[cel_widget_id*="sbv-search-"]').count()
                    loom_bottom_count = page.locator('*[cel_widget_id*="loom-desktop-bottom-slot"]').count()
                    component_type_count = page.locator('[data-component-type="sbv-video-single-product"]').count()
                    log(
                        f"sbv: markers -> VIDEO_SINGLE_PRODUCT: {video_single_count}, "
                        f"sbv-video-single-product: {sbv_video_count}, "
                        f"sbv-search-: {sbv_search_count}, "
                        f"loom-bottom: {loom_bottom_count}, "
                        f"component-type: {component_type_count}"
                    )
                    # Look for video containers using stable data attributes
                    # Enhanced SBV detection with priority order and better deduplication
                    sbv_selectors = [
                        # Single-product SBV cards (preferred attributes)
                        '[data-component-type="sbv-video-single-product"]',
                        '*[cel_widget_id^="VIDEO_SINGLE_PRODUCT"]',
                        '*[cel_widget_id*="sbv-video-single-product"]',   # variant used on some pages
                        '*[cel_widget_id*="sb-video-single-product"]',    # variant seen in the wild

                        # Single-product SBV cards (class-based fallbacks)
                        '*[class*="sbv-video-single-product"]',

                        # Wrappers that can hold one or more SBV cards (top/mid/bottom slots, attribute-based)
                        '*[cel_widget_id*="sb-video-product-collection"]',
                        '*[data-cel-widget*="sb-video-product-collection"]',
                        '*[cel_widget_id*="sbv-search-"]',                # e.g., sbv-search-bottom, sbv-search-top
                        '*[data-cel-widget*="sbv-search-"]',
                        '*[cel_widget_id*="loom-desktop-bottom-slot"]',   # bottom-slot
                        '*[cel_widget_id*="loom-desktop-inline-slot"]',   # mid/inline slot

                        # Known wrapper classes for SBV scrollers/containers
                        '.sbv-ad-content-container',
                        '*[class*="sbv-desktop-scroller"]',
                        '*[class*="a-scroller-horizontal"]',

                        # Inner video/player nodes (fallback; we'll climb to card container)
                        '*[class*="sbv-video-player"]',
                        '*[class*="sbv-video"]',
                    ]
                    
                    all_sbv_elements = []
                    
                    for selector in sbv_selectors:
                        try:
                            elements = page.locator(selector).all()
                            log(f"sbv: selector '{selector}' found {len(elements)} elements")

                            for el in elements:
                                # Build candidate list: if this is a wrapper, expand to the inner cards
                                inner = el.locator(
                                    '[data-component-type="sbv-video-single-product"], '
                                    '*[cel_widget_id^="VIDEO_SINGLE_PRODUCT"], '
                                    '*[cel_widget_id*="sbv-video-single-product"], '
                                    '*[cel_widget_id*="sb-video-single-product"]'
                                )

                                candidates = inner.all() if inner.count() > 0 else [el]

                                for c in candidates:
                                    # Optional dedupe by container signature to avoid wrapper+card double-add
                                    sig = _get_container_signature(c) or _get_container_signature(el)
                                    if sig and sig in captured_containers:
                                        log(f"sbv: duplicate by signature -> {sig}")
                                        continue
                                    if sig:
                                        captured_containers.add(sig)

                                    # DO NOT require <video> yet — we hydrate later
                                    if c.is_visible():
                                        all_sbv_elements.append(c)
                        except Exception as e:
                            log(f"sbv: selector error {selector} -> {e}")
                    
                    log(f"sbv: discovered {len(all_sbv_elements)} candidates (pre-hydration)")

                    if len(all_sbv_elements) == 0:
                        try:
                            log("sbv: fallback — hydrating bottom slot for SBV")
                            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                            time.sleep(1.2)  # allow ad JS to mount bottom-slot
                        except Exception:
                            pass

                        # Rerun the exact discovery loop once (same selectors & wrapper expansion)
                        all_sbv_elements = []
                        for selector in sbv_selectors:
                            elements = page.locator(selector).all()
                            log(f"sbv: [fallback] selector '{selector}' found {len(elements)} elements")
                            for el in elements:
                                inner = el.locator(
                                    '[data-component-type="sbv-video-single-product"], '
                                    '*[cel_widget_id^="VIDEO_SINGLE_PRODUCT"], '
                                    '*[cel_widget_id*="sbv-video-single-product"], '
                                    '*[cel_widget_id*="sb-video-single-product"]'
                                )
                                candidates = inner.all() if inner.count() > 0 else [el]
                                for c in candidates:
                                    sig = _get_container_signature(c) or _get_container_signature(el)
                                    if sig and sig in captured_containers:
                                        continue
                                    if sig:
                                        captured_containers.add(sig)
                                    if c.is_visible():
                                        all_sbv_elements.append(c)

                        log(f"sbv: [fallback] discovered {len(all_sbv_elements)} candidates (pre-hydration)")

                    # Process all unique SBV elements found
                    sbv_count = len(all_sbv_elements)
                    processed_count = 0
                    for sbv_idx, sbv_widget in enumerate(all_sbv_elements):
                        if processed_count >= 5:  # Limit to 5 SBVs (increased from 2)
                            break
                        if time_left() < 10:
                            break
                        if sbv_widget.is_visible():
                            log(f"sbv: processing widget {sbv_idx}")
                            try:
                                # Find the proper SBV container - be conservative to avoid full page capture
                                sbv_container = None
                                
                                # Try SBV containers using stable data attributes
                                container_selectors = [
                                    "xpath=ancestor::*[@data-component-type='sbv-video-single-product'][1]",  # Primary: stable SBV component type
                                    "xpath=ancestor::div[contains(@cel_widget_id,'VIDEO_SINGLE_PRODUCT')][1]",  # Stable widget ID
                                    "xpath=ancestor::div[@data-asin and @data-index][1]",  # Stable: ASIN + index attributes
                                    "xpath=ancestor::div[@data-component-type][1]",  # Any stable component type
                                    "xpath=ancestor::div[2]",  # Conservative fallback
                                ]
                                
                                for selector in container_selectors:
                                    candidate = sbv_widget.locator(selector)
                                    if candidate.count() > 0:
                                        sbv_container = candidate.first
                                        break
                                
                                # Final fallback - use the video widget itself (better than full page)
                                if not sbv_container:
                                    sbv_container = sbv_widget
                                
                                # Dedup by SBV container signature first
                                sig = _get_container_signature(sbv_container) or _get_container_signature(sbv_widget)
                                if sig and sig in captured_containers:
                                    log(f"sbv: duplicate container skipped -> {sig}")
                                    continue
                                if sig:
                                    captured_containers.add(sig)
                                
                                # Hydrate each SBV just before screenshot/MP4 (not during discovery)
                                try:
                                    # Center horizontally within any scroller so off-screen cards become visible
                                    try:
                                        _center_card_horizontally(sbv_container)
                                    except Exception:
                                        pass

                                    sbv_container.scroll_into_view_if_needed()
                                    time.sleep(0.6)

                                    # Use an ElementHandle for hydration wait to avoid locator ambiguity
                                    el_handle = sbv_container.element_handle()
                                    if el_handle:
                                        page.wait_for_function(
                                            "(el) => !!(el && (el.querySelector('video') || el.querySelector('source')))",
                                            arg=el_handle,
                                            timeout=6000
                                        )
                                except Exception as hydrate_error:
                                    # On Amazon, SBV "play" clicks can navigate into PDPs. Avoid clicking here;
                                    # if hydration fails we still proceed with whatever media is present.
                                    log(f"sbv: hydration wait error -> {hydrate_error}; continuing without click")
                                
                                # Optional debug (helps verify hydration is working)
                                has_media = sbv_container.locator('video, source').count()
                                log(f"sbv: media tags present after hydration -> {has_media}")
                                
                                # Dedupe by video URL only if a URL was actually resolved (don't skip otherwise)
                                video_url = ""
                                try:
                                    v = sbv_container.locator('video').first
                                    if v.count() > 0:
                                        video_url = v.evaluate("el => el.currentSrc || el.src || ''") or ''
                                        if not video_url:
                                            s = v.locator('source').first
                                            if s.count() > 0:
                                                video_url = s.get_attribute('src') or ''
                                    else:
                                        s = sbv_container.locator('source').first
                                        if s.count() > 0:
                                            video_url = s.get_attribute('src') or ''
                                except Exception:
                                    pass
                                
                                if video_url:
                                    vhash = _short_hash(video_url)
                                    if vhash in seen_video_hashes:
                                        log(f"sbv: duplicate by video url -> {video_url}")
                                        continue
                                    seen_video_hashes.add(vhash)
                                
                                # Extract enhanced data from SBV internal structure
                                brand_txt, brand_canon, message = _extract_brand_and_message(sbv_container)
                                
                                # Extract additional info from SBV sections
                                video_info = {}
                                product_info = {}
                                try:
                                    # Get info from video container
                                    video_container = sbv_container.locator('[class*="sbv-video-container"]')
                                    if video_container.count() > 0:
                                        # Video duration, dimensions, etc. could be extracted here
                                        video_info["has_video_container"] = True
                                    
                                    # Get info from product container  
                                    product_container = sbv_container.locator('[class*="sbv-product-container"]')
                                    if product_container.count() > 0:
                                        product_info["has_product_container"] = True
                                        
                                        # Method 1: Extract from displayed product title h2 (most accurate)
                                        try:
                                            product_title = product_container.first.locator('h2[aria-label], h2 span')
                                            if product_title.count() > 0:
                                                # Try aria-label first (complete title)
                                                title_text = product_title.first.get_attribute('aria-label') or ''
                                                if not title_text:
                                                    # Fallback to span text content
                                                    title_text = product_title.first.inner_text().strip()
                                                
                                                if title_text and len(title_text) > 10:
                                                    product_info["product_title"] = title_text
                                                    product_info["product_description"] = title_text  # Keep for backward compatibility
                                                    log(f"sbv: product from h2 title -> {title_text[:100]}...")
                                        except Exception:
                                            pass
                                        
                                        # Method 2: Extract product image URL
                                        try:
                                            product_img = product_container.first.locator('img.s-image[src]')
                                            if product_img.count() > 0:
                                                product_info["product_image_url"] = product_img.first.get_attribute('src') or ''
                                        except Exception:
                                            pass
                                        
                                        # Method 3: Fallback to image alt if h2 method fails
                                        if not product_info.get("product_description"):
                                            try:
                                                product_img = product_container.first.locator('img.s-image[alt]:not([alt=""])')
                                                if product_img.count() > 0:
                                                    product_alt = product_img.first.get_attribute('alt') or ''
                                                    if product_alt and len(product_alt) > 10:
                                                        product_info["product_description"] = product_alt
                                                        log(f"sbv: product from image alt -> {product_alt[:100]}...")
                                            except Exception:
                                                pass
                                        
                                        # Method 4: Final fallback to general text content
                                        if not product_info.get("product_description"):
                                            try:
                                                product_text = product_container.first.inner_text().strip()
                                                if product_text and len(product_text) > 10:
                                                    product_info["product_description"] = product_text[:200]  # Limit length
                                                    log(f"sbv: product from text -> {product_text[:100]}...")
                                            except Exception:
                                                pass
                                    
                                    log(f"sbv: enhanced extraction -> video_container: {video_info.get('has_video_container', False)}, product_container: {product_info.get('has_product_container', False)}")
                                except Exception as e:
                                    log(f"sbv: enhanced extraction error -> {e}")
                                
                                fname = _std_filename("amazon", brand_canon or "unknown", "Sponsored_Brand_Video", client, keyword, run_id, sbv_idx, ".png")
                                fpath = os.path.join(output_dir, "Sponsored_Brand_Video", fname)
                                
                                # Capture video bounding box BEFORE screenshot for accurate overlay positioning
                                video_overlay = None
                                try:
                                    video_el = sbv_container.locator('video').first
                                    if video_el.count() > 0:
                                        container_box = sbv_container.bounding_box()
                                        video_box = video_el.bounding_box()
                                        if container_box and video_box:
                                            video_overlay = {
                                                "x": round(video_box["x"] - container_box["x"]),
                                                "y": round(video_box["y"] - container_box["y"]),
                                                "width": round(video_box["width"]),
                                                "height": round(video_box["height"]),
                                                "image_width": round(container_box["width"]),
                                                "image_height": round(container_box["height"]),
                                            }
                                            log(f"sbv: video_overlay captured -> {video_overlay}")
                                except Exception as e:
                                    log(f"sbv: video_overlay capture error -> {e}")
                                
                                # Ensure directory exists and path is string
                                os.makedirs(os.path.dirname(fpath), exist_ok=True)
                                sbv_container.screenshot(path=str(fpath), timeout=4000)
                                
                                # Try to download MP4 video
                                video_rel = None
                                try:
                                    video_el = sbv_widget.locator('video').first
                                    if video_el.count() > 0:
                                        video_src = video_el.get_attribute('src')
                                        if not video_src:
                                            # Try source tags
                                            source_el = video_el.locator('source').first
                                            if source_el.count() > 0:
                                                video_src = source_el.get_attribute('src')
                                        if video_src and video_src.startswith('http'):
                                            video_name = fname.replace('.png', '.mp4')
                                            mp4_path = os.path.join(output_dir, "Sponsored_Brand_Video", video_name)
                                            video_rel = f"Sponsored_Brand_Video/{video_name}"
                                            try:
                                                import requests
                                                r = requests.get(video_src, timeout=30)
                                                if r.ok:
                                                    with open(mp4_path, 'wb') as f:
                                                        f.write(r.content)
                                                    log(f"sbv: mp4 saved -> {mp4_path}")
                                            except Exception as e:
                                                log(f"sbv: mp4 download error -> {e}")
                                except Exception as e:
                                    log(f"sbv: mp4 error -> {e}")
                                
                                # Add to ads array
                                module_id, eid = _build_ids("Sponsored_Brand_Video", "Video_Single_Product", brand_canon, "sbv", run_id, sbv_idx)
                                ad_obj = {
                                    "id": eid,
                                    "module_id": module_id,
                                    "type": "Sponsored_Brand_Video",
                                    "subtype": "Video_Single_Product",
                                    "brand": brand_txt or "Unknown",
                                    "brand_logo": None,
                                    "title": product_info.get("product_title", "") or None,
                                    "description": product_info.get("product_description", "") or None,
                                    "cta": None,
                                    "href": None,
                                    "image_url": None,
                                    "image_path": f"Sponsored_Brand_Video/{fname}",
                                    "products": [],
                                    "brand_canonical": brand_canon,
                                    "advertisers": [brand_canon] if brand_canon else [],
                                    "video_path": video_rel,
                                    "video_url": video_rel,  # Also set video_url for API consistency
                                    "message": message,
                                    "product_title": product_info.get("product_title", ""),
                                    "product_description": product_info.get("product_description", ""),
                                    "product_image_url": product_info.get("product_image_url", ""),
                                    "metadata": {
                                        "has_video_container": video_info.get("has_video_container", False),
                                        "has_product_container": product_info.get("has_product_container", False),
                                        "has_product_image": bool(product_info.get("product_image_url")),
                                        "has_product_title": bool(product_info.get("product_title")),
                                        "sbv_structure_detected": True
                                    },
                                }
                                # Add video overlay - prefer Playwright capture, fallback to OpenCV detection
                                if video_overlay:
                                    ad_obj["video_overlay"] = video_overlay
                                else:
                                    # Fallback: use OpenCV auto-detection on the saved screenshot
                                    try:
                                        from scripts.auto_detect_video_overlay import auto_detect_video_bounds
                                        detected_overlay = auto_detect_video_bounds(Path(fpath), "amazon", "sbv")
                                        if detected_overlay:
                                            ad_obj["video_overlay"] = detected_overlay
                                            log(f"sbv: video_overlay detected via OpenCV -> {detected_overlay}")
                                    except Exception as cv_err:
                                        log(f"sbv: OpenCV detection error -> {cv_err}")
                                ads.append(ad_obj)
                                log(f"sbv: saved -> {fname}")
                                processed_count += 1
                            except Exception as e:
                                log(f"sbv: screenshot fail -> {e}")
                    if sbv_count == 0:
                        log("sbv: none found")
                except Exception as e:
                    log(f"sbv: detect error -> {e}")

                # 3) Essential ad detection sections
                log("debug: continuing to sb-themed and sb-headline detection")
                
                # 3a) Sponsored Brand Detection (comprehensive)
                try:
                    log("sb-brands: detect")
                    # Look for both traditional SB layouts and individual cards
                    sb_selectors = [
                        # SB containers (v1/v2) - ONLY traditional Sponsored Brands
                        'div[cel_widget_id*="sb-themed-collection-v2-desktop_loom-desktop-inline-slot"]',
                        'div[data-card-metrics-id*="sb-themed-collection-v2-desktop_loom-desktop-inline-slot"]',
                        'div[cel_widget_id*="sb-themed-collection"]:not([cel_widget_id*="inline-slot"])',
                        'div[data-card-metrics-id*="sb-themed-collection"]:not([data-card-metrics-id*="inline-slot"])',
                        # SB headline anchor; we'll normalize to container
                        'a[data-elementid="sb-headline"]',
                    ]
                    
                    all_sb_elements = []
                    for selector in sb_selectors:
                        if time_left() < 30:  # Need at least 30s for processing
                            break
                        try:
                            elements = page.locator(selector).all()
                            for el in elements:
                                if el.is_visible():
                                    # If this is a headline element, find its parent container
                                    if selector == 'a[data-elementid="sb-headline"]':
                                        # Find the parent container that includes the full SB
                                        parent_container = el.locator('xpath=ancestor::div[contains(@data-card-metrics-id,"sb-themed-collection")][1]')
                                        if parent_container.count() > 0:
                                            all_sb_elements.append(parent_container.first)
                                            log(f"sb-brands: found headline, using parent container")
                                        else:
                                            # Skip headlines without sb-themed-collection parent (bottom cards handled separately)
                                            log(f"sb-brands: skipping headline without sb-themed-collection parent")
                                            continue
                                    else:
                                        all_sb_elements.append(el)
                        except Exception as e:
                            log(f"sb-brands: selector error {selector} -> {e}")
                    
                    log(f"sb-brands: found {len(all_sb_elements)} total sponsored brand elements")
                    for i, el in enumerate(all_sb_elements):
                        if time_left() < 10:
                            break
                        if not el.is_visible():
                            continue
                        try:
                            # Normalize to the true SB container
                            container = _normalize_sb_container(el)
                            
                            # Hard gate: skip if not an SB container
                            if not _is_sb_container(container):
                                log("sb-brands: skip — not an SB container")
                                continue
                            
                            # Also ensure we are not grabbing a search result tile
                            try:
                                if container.locator('xpath=self::*[@data-component-type="s-search-result"]').count() > 0:
                                    log("sb-brands: skip — this is a product tile (s-search-result)")
                                    continue
                            except Exception:
                                pass
                            
                            # From here on, use container for bbox/signature and screenshots
                            el = container
                            
                            # Container signature dedupe
                            container_sig = _get_container_signature(el)
                            if container_sig and container_sig in captured_containers:
                                log(f"sb-themed: duplicate container skipped -> {container_sig}")
                                continue
                            
                            # Geometric overlap check and size validation
                            try:
                                bbox = el.bounding_box()
                                if bbox:
                                    # Skip if too large (likely full page capture)
                                    if bbox['width'] > 1200 or bbox['height'] > 800:
                                        log(f"sb-themed: skipping large element (likely full page) -> {bbox}")
                                        continue
                                    if _check_bbox_overlap(bbox, captured_bboxes):
                                        log(f"sb-themed: overlapping bbox skipped -> {bbox}")
                                        continue
                            except Exception as e:
                                log(f"sb-themed: bbox check error -> {e}")
                                bbox = None
                            
                            brand_txt, brand_canon, message = _extract_brand_and_message(el)
                            
                            # Enhanced extraction for sponsored brand ads using aria-label pattern
                            brand_logo_url = ""
                            brand_store_url = ""
                            try:
                                # Method 1: Extract from main sponsored ad link
                                sb_link = el.locator('a[aria-label*="Sponsored ad from"]')
                                if sb_link.count() > 0:
                                    aria_label = sb_link.first.get_attribute('aria-label') or ''
                                    # Parse: "Sponsored ad from [Brand]. "[Message]." Shop [Brand]."
                                    if 'Sponsored ad from ' in aria_label:
                                        # Extract brand name
                                        brand_start = aria_label.find('Sponsored ad from ') + len('Sponsored ad from ')
                                        brand_end = aria_label.find('.', brand_start)
                                        if brand_end > brand_start:
                                            extracted_brand = aria_label[brand_start:brand_end].strip()
                                            if extracted_brand:
                                                brand_txt = extracted_brand
                                                brand_canon = extracted_brand.lower().replace(' ', '_').replace('.', '')
                                        
                                        # Extract message (between quotes)
                                        quote_start = aria_label.find('"')
                                        quote_end = aria_label.find('"', quote_start + 1) if quote_start != -1 else -1
                                        if quote_start != -1 and quote_end != -1:
                                            extracted_message = aria_label[quote_start + 1:quote_end].strip()
                                            if extracted_message:
                                                message = extracted_message
                                
                                # Method 2: Extract brand logo and store URL from brand logo link
                                brand_logo_link = el.locator('a[aria-label]:has(img[alt]):not([aria-label*="Sponsored ad from"])')
                                if brand_logo_link.count() > 0:
                                    logo_link = brand_logo_link.first
                                    # Get brand name from aria-label (cleaner than "Sponsored ad from" version)
                                    logo_brand = logo_link.get_attribute('aria-label') or ''
                                    if logo_brand and not brand_txt:  # Use if we don't have brand from method 1
                                        brand_txt = logo_brand
                                        brand_canon = logo_brand.lower().replace(' ', '_').replace('.', '')
                                    
                                    # Get brand store URL
                                    brand_store_url = logo_link.get_attribute('href') or ''
                                    
                                    # Get brand logo image URL - validate it's actually a logo, not an ad image
                                    logo_img = logo_link.locator('img[alt]')
                                    if logo_img.count() > 0:
                                        candidate_url = logo_img.first.get_attribute('src') or ''
                                        # Validate: logos are small images, ad creatives have large dimensions in URL
                                        # Amazon product images use /images/I/ path
                                        # Brand logos use /images/S/al-na- path (these ARE logos, don't exclude)
                                        # Large ad creatives have patterns like _SX920_ (large scaled)
                                        is_product_image = '/images/I/' in candidate_url
                                        is_oversized = any(pattern in candidate_url for pattern in [
                                            '_SX920', '_SX800', '_SX600',  # Large scaled images
                                            '_CR0,0,1200', '_CR0,0,800',   # Large cropped images
                                        ])
                                        if not is_product_image and not is_oversized:
                                            brand_logo_url = candidate_url
                                        else:
                                            log(f"sb-brands: skipping product/oversized image as logo -> {candidate_url[:80]}...")
                                
                                # Method 3: Extract headline message from sb-headline element
                                headline_link = el.locator('a[data-elementid="sb-headline"]')
                                if headline_link.count() > 0:
                                    headline_message = headline_link.first.get_attribute('aria-label') or ''
                                    if headline_message and not message:  # Use if we don't have message from method 1
                                        message = headline_message
                                    
                                    # Also get store URL from headline if not already captured
                                    if not brand_store_url:
                                        brand_store_url = headline_link.first.get_attribute('href') or ''
                                
                                log(f"sb-brands: enhanced extraction -> brand: {brand_txt}, message: {message}, logo: {bool(brand_logo_url)}, store: {bool(brand_store_url)}")
                            except Exception as e:
                                log(f"sb-brands: enhanced extraction error -> {e}")
                            
                            anchor = _module_anchor(el)
                            if anchor in seen_anchors:
                                log(f"sb-themed: duplicate anchor skipped -> {anchor}")
                                continue
                            seen_anchors.add(anchor)
                            
                            fname = _std_filename("amazon", brand_canon or "unknown", "Sponsored_Brand", client, keyword, run_id, i, ".png")
                            fpath = os.path.join(output_dir, "Sponsored_Brand", fname)
                            
                            # Wait for images to load before screenshot
                            try:
                                el.scroll_into_view_if_needed()
                                time.sleep(0.2)
                                # Wait for images to load
                                el_handle = el.element_handle()
                                page.evaluate("""
                                  (el) => new Promise((resolve) => {
                                    const sleep = (ms) => new Promise(r => setTimeout(r, ms));
                                    (async () => {
                                      let stable = 0; let last = 0;
                                      for (let i=0; i<6 && stable<2; i++) {
                                        const imgs = Array.from(el.querySelectorAll('img')).filter(img => img.complete && img.naturalWidth>10).length;
                                        if (imgs === last) stable++; else stable = 0;
                                        last = imgs; await sleep(300);
                                      }
                                      resolve(true);
                                    })()
                                  })
                                """, el_handle)
                            except Exception as e:
                                log(f"sb-themed: image wait error -> {e}")
                            
                            el.screenshot(path=fpath, timeout=4000)
                            
                            # Record successful captures
                            if container_sig:
                                captured_containers.add(container_sig)
                            if bbox:
                                captured_bboxes.append(bbox)
                            
                            # Add to ads array
                            module_id, eid = _build_ids("Sponsored_Brand", "Themed_Collection", brand_canon, anchor, run_id, i)
                            ads.append({
                                "id": eid,
                                "module_id": module_id,
                                "type": "Sponsored_Brand",
                                "subtype": "Themed_Collection",
                                "brand": brand_txt or "Unknown",
                                "brand_logo": None,
                                "title": message or None,
                                "description": None,
                                "cta": None,
                                "href": None,
                                "image_url": None,
                                "image_path": f"Sponsored_Brand/{fname}",
                                "products": [],
                                "brand_canonical": brand_canon,
                                "advertisers": [brand_canon] if brand_canon else [],
                                "video_path": None,
                                "message": message,
                                "brand_logo_url": brand_logo_url,
                                "brand_store_url": brand_store_url,
                                "metadata": {
                                    "has_brand_logo": bool(brand_logo_url),
                                    "has_store_url": bool(brand_store_url)
                                },
                            })
                            log(f"sb-themed: saved -> {fname}")
                            
                            # Save brand logo to centralized database
                            if brand_logo_url and brand_canon and brand_canon != "unknown" and BrandLogoDatabase:
                                try:
                                    logo_db = BrandLogoDatabase()
                                    logo_db.add_brand_logo(
                                        brand=brand_canon,
                                        logo_url=brand_logo_url,
                                        retailer="amazon",
                                        metadata={"ad_type": "Sponsored Brand", "keyword": keyword}
                                    )
                                except Exception as logo_err:
                                    log(f"sb-brands: logo save error -> {logo_err}")
                        except Exception as e:
                            log(f"sb-themed: screenshot fail -> {e}")
                except Exception as e:
                    log(f"sb-brands: detect error -> {e}")

                # 3a.5) Sponsored Brand Cards - INDEPENDENT section (separate from main SB)
                try:
                    log("sb-cards: detect - INDEPENDENT processing")
                    
                    # Try multiple selectors for the brands carousel - completely independent from main SB
                    brands_carousel = None
                    carousel_selectors = [
                        'div.a-cardui[data-card-metrics-id*="multi-brand-creative-desktop"]:has(span[aria-label="Brands related to your search"])',
                        'div[data-card-metrics-id*="multi-brand-creative-desktop"]',
                        '*:has(span[aria-label="Brands related to your search"])',
                        'div:has-text("Brands related to your search")',
                    ]
                    
                    for selector in carousel_selectors:
                        carousel_candidates = page.locator(selector)
                        if carousel_candidates.count() > 0:
                            brands_carousel = carousel_candidates.first
                            log(f"sb-cards: found brands carousel with selector: {selector}")
                            break
                    
                    # Initialize brand_cards variable
                    brand_cards = None
                    
                    if brands_carousel:
                        # Try multiple methods to find complete brand card containers
                        card_selectors = [
                            'div[data-index="0"], div[data-index="1"], div[data-index="2"]',  # Specific: brand card containers with data-index
                            'div[data-index]',  # Primary: div elements with data-index (complete cards)
                            '*[data-index]',  # Fallback: Any elements with data-index (complete cards)
                            'ul li',  # Fallback: complete li containers
                            'li',     # Fallback: Direct li elements - complete containers  
                        ]
                        
                        for card_selector in card_selectors:
                            cards = brands_carousel.locator(card_selector)
                            card_count_found = cards.count()
                            log(f"sb-cards: selector '{card_selector}' found {card_count_found} cards")
                            if card_count_found > 0:
                                # Debug: Check what each card contains
                                for i in range(min(card_count_found, 3)):
                                    try:
                                        card = cards.nth(i)
                                        img_count = card.locator('img').count()
                                        link_count = card.locator('a').count()
                                        log(f"sb-cards: card {i} has {img_count} images and {link_count} links")
                                    except Exception:
                                        pass
                                
                                brand_cards = cards
                                log(f"sb-cards: using selector: {card_selector}")
                                break
                        
                        if brand_cards:
                            card_count = brand_cards.count()
                        else:
                            card_count = 0
                            log("sb-cards: no brand cards found with any selector")
                    else:
                        card_count = 0
                        log("sb-cards: no brands carousel found with any selector")
                    
                    # Process brand cards if found
                    if brand_cards and card_count > 0:
                        for card_idx in range(min(card_count, 3)):  # Limit to 3 cards
                            if time_left() < 10:
                                break
                            try:
                                brand_li = brand_cards.nth(card_idx)

                                # 1) Try to get it into view horizontally first
                                _center_card_horizontally(brand_li)
                                try:
                                    brand_li.scroll_into_view_if_needed()
                                    time.sleep(0.2)
                                except Exception:
                                    pass

                                # 2) Re-check visibility after centering
                                if not brand_li.is_visible():
                                    # If a nav-left control exists, click it once to expose card 0,
                                    # then try again (useful when the carousel initializes to card 1)
                                    try:
                                        nav_left = brands_carousel.locator('button[aria-label*="left" i], a[aria-label*="left" i]').first
                                        if nav_left.count() > 0:
                                            try:
                                                nav_left.click()
                                                time.sleep(0.3)
                                            except Exception:
                                                pass
                                            try:
                                                brands_carousel.evaluate("el => { try { el.scrollLeft = 0; } catch(e) {} }")
                                            except Exception:
                                                pass
                                            _center_card_horizontally(brand_li)
                                            brand_li.scroll_into_view_if_needed()
                                            time.sleep(0.2)
                                    except Exception:
                                        pass

                                if not brand_li.is_visible():
                                    log(f"sb-cards: card {card_idx} still not visible, skipping")
                                    continue

                                if brand_li.is_visible():
                                    # Debug: Check what we're actually capturing
                                    try:
                                        bbox = brand_li.bounding_box()
                                        tag_name = brand_li.evaluate("el => el.tagName")
                                        class_name = brand_li.get_attribute("class") or "no-class"
                                        child_count = brand_li.locator("*").count()
                                        log(f"sb-cards: card {card_idx} -> tag: {tag_name}, class: {class_name}, children: {child_count}, bbox: {bbox}")
                                    except Exception as e:
                                        log(f"sb-cards: debug error for card {card_idx} -> {e}")
                                    # Get brand name and store URL from the brand store link (more reliable than image alt)
                                    brand_name = 'unknown'
                                    store_url = ''
                                    
                                    # Try to get brand from the store link aria-label or data-label
                                    store_link = brand_li.locator('a[aria-label*="Shop"], a[data-label*="Shop"]')
                                    if store_link.count() > 0:
                                        aria_label = store_link.first.get_attribute('aria-label') or ''
                                        data_label = store_link.first.get_attribute('data-label') or ''
                                        store_url = store_link.first.get_attribute('href') or ''
                                        
                                        # Extract brand name from "Shop [Brand Name]" pattern
                                        if aria_label.startswith('Shop '):
                                            brand_name = aria_label[5:]  # Remove "Shop " prefix
                                        elif data_label.startswith('Shop '):
                                            brand_name = data_label[5:]  # Remove "Shop " prefix
                                    
                                    # Fallback to image alt if store link method fails
                                    # SB Cards have TWO images:
                                    # 1. Large ad creative banner (e.g., _SX920_, _CR0,0,2500,1308_) - NOT a logo
                                    # 2. Small brand logo (e.g., _SX278_SY200_, _AC_SX278_) - THIS is the logo
                                    brand_logo_url = ''
                                    if brand_name == 'unknown':
                                        brand_img = brand_li.locator('img[alt]:not([alt=""])')
                                        if brand_img.count() > 0:
                                            brand_name = brand_img.first.get_attribute('alt') or 'unknown'
                                    
                                    # Find the actual logo image
                                    # Method 1: Look for semantic container with "logoContainer" in class/data attrs
                                    # Method 2: Fall back to structural detection by rendered size
                                    try:
                                        # Method 1: Semantic - find container with logoContainer in any attribute
                                        logo_container = brand_li.locator('[class*="logoContainer"], [data-testid*="logo"], [class*="Logo"]')
                                        if logo_container.count() > 0:
                                            logo_img = logo_container.first.locator('img[src]').first
                                            if logo_img.count() > 0:
                                                brand_logo_url = logo_img.get_attribute('src') or ''
                                                if brand_logo_url:
                                                    log(f"sb-cards: card {card_idx} found logo via logoContainer -> {brand_logo_url[:60]}...")
                                        
                                        # Method 2: Structural fallback - find small image by rendered size
                                        # IMPORTANT: Exclude product images (images/I/) - only use brand assets (images/S/al-na-)
                                        if not brand_logo_url:
                                            all_imgs = brand_li.locator('img[src]')
                                            logo_candidates = []
                                            for img_idx in range(all_imgs.count()):
                                                img = all_imgs.nth(img_idx)
                                                img_src = img.get_attribute('src') or ''
                                                if not img_src:
                                                    continue
                                                # Skip product images - they use /images/I/ path
                                                # Brand logos use /images/S/al-na- path
                                                if '/images/I/' in img_src:
                                                    continue
                                                try:
                                                    bbox = img.bounding_box()
                                                    if bbox:
                                                        w, h = bbox.get('width', 0), bbox.get('height', 0)
                                                        # Logo: 50-350px wide, height > 30px, aspect ≤ 4:1
                                                        if 50 < w < 350 and h > 30:
                                                            aspect = w / h if h > 0 else 999
                                                            if aspect <= 4.0:
                                                                logo_candidates.append((img_src, w, h, aspect))
                                                except:
                                                    pass
                                            
                                            if logo_candidates:
                                                # Prefer squarer aspect ratios (closer to 1:1)
                                                logo_candidates.sort(key=lambda x: abs(x[3] - 1.0))
                                                brand_logo_url = logo_candidates[0][0]
                                                w, h = logo_candidates[0][1], logo_candidates[0][2]
                                                log(f"sb-cards: card {card_idx} found logo by size {w:.0f}x{h:.0f} -> {brand_logo_url[:60]}...")
                                    except Exception as logo_err:
                                        log(f"sb-cards: card {card_idx} logo extraction error -> {logo_err}")

                                    # Use shared canonicalization so SB Cards align with other retailers
                                    if brand_name and brand_name.lower() != 'unknown':
                                        canon = canonicalize(brand_name)
                                        brand_canon = canon or brand_name
                                    else:
                                        brand_canon = None
                                    
                                    # Debug: Log brand extraction for troubleshooting
                                    log(f"sb-cards: card {card_idx} brand extraction -> name: '{brand_name}', canon: '{brand_canon}'")
                                    
                                    # Reset hover filename for this card iteration
                                    fname_hover = None
                                    
                                    # Take two screenshots: normal state and hover state
                                    try:
                                        # Freeze transitions to avoid false "invisible" due to CSS transitions
                                        try:
                                            page.evaluate("""
                                                () => {
                                                    const st = document.createElement('style');
                                                    st.textContent = '*{animation:none !important; transition:none !important;}';
                                                    document.head.appendChild(st);
                                                }
                                            """)
                                        except Exception:
                                            pass
                                        
                                        brand_li.scroll_into_view_if_needed()
                                        time.sleep(0.3)
                                        
                                        # 1) Screenshot normal state (no hover)
                                        fname_normal = _std_filename("amazon", brand_canon or "unknown", "Sponsored_Brand_Card", client, keyword, run_id, f"card_{card_idx}_normal", ".png")
                                        fpath_normal = os.path.join(output_dir, "Sponsored_Brand_Cards", fname_normal)
                                        os.makedirs(os.path.dirname(fpath_normal), exist_ok=True)
                                        
                                        # Debug: Check path before screenshot
                                        log(f"sb-cards: card {card_idx} screenshot path -> '{fpath_normal}' (type: {type(fpath_normal)})")
                                        
                                        brand_li.screenshot(path=fpath_normal, timeout=4000)
                                        log(f"sb-cards: normal state saved -> {fname_normal}")
                                        
                                        # 2) Screenshot hover state
                                        try:
                                            logo_img = brand_li.locator('img').first
                                            if logo_img.count() > 0:
                                                logo_img.hover()
                                                time.sleep(0.5)  # Wait for hover animations/transitions
                                                
                                                fname_hover = _std_filename("amazon", brand_canon or "unknown", "Sponsored_Brand_Card", client, keyword, run_id, f"card_{card_idx}_hover", ".png")
                                                fpath_hover = os.path.join(output_dir, "Sponsored_Brand_Cards", fname_hover)
                                                
                                                brand_li.screenshot(path=fpath_hover, timeout=4000)
                                                log(f"sb-cards: hover state saved -> {fname_hover}")
                                            else:
                                                log(f"sb-cards: no logo found for hover on card {card_idx}")
                                        except Exception as hover_error:
                                            log(f"sb-cards: hover screenshot failed for card {card_idx} -> {hover_error}")
                                        
                                    except Exception as screenshot_error:
                                        log(f"sb-cards: card screenshots error for card {card_idx} -> {screenshot_error}")
                                        continue  # Skip this card and move to next
                                    
                                    # Look for slogan/message text within this li - focus on structure, not hashed classes
                                    message = ""
                                    try:
                                        # Target the stable structure: span.a-truncate-full (Amazon's stable class) within any link
                                        slogan_el = brand_li.locator('a span.a-truncate-full, span.a-truncate-full')
                                        if slogan_el.count() > 0:
                                            message = slogan_el.first.inner_text()
                                        # Fallback: look for any span with sentence-like text (contains periods)
                                        elif brand_li.locator('span:has-text(".")').count() > 0:
                                            message = brand_li.locator('span:has-text(".")').first.inner_text()
                                    except Exception:
                                        pass
                                    
                                    # Add to ads array
                                    module_id, eid = _build_ids("Sponsored_Brand_Card", "Brand_Card", brand_canon, f"bottom_card_{card_idx}", run_id, card_idx)
                                    ads.append({
                                        "id": eid,
                                        "module_id": module_id,
                                        "type": "Sponsored_Brand_Card",
                                        "subtype": "Brand_Card",
                                        "brand": brand_name,
                                        "brand_logo_url": brand_logo_url or None,
                                        "title": brand_name or None,
                                        "description": message or None,
                                        "cta": None,
                                        "href": store_url or None,
                                        "image_url": None,
                                        "image_path": f"Sponsored_Brand_Cards/{fname_normal}",
                                        "products": [],
                                        "brand_canonical": brand_canon,
                                        "advertisers": [brand_canon] if brand_canon else [],
                                        "image_path_hover": f"Sponsored_Brand_Cards/{fname_hover}" if fname_hover else None,
                                        "video_path": None,
                                        "message": message,
                                        "position": f"bottom_card_{card_idx}",
                                        "store_url": store_url,
                                        "metadata": {
                                            "extraction_method": "store_link" if store_url else "image_alt"
                                        },
                                    })
                                    log(f"sb-cards: individual card saved -> normal: {fname_normal}, hover: {fname_hover or 'failed'}")
                                    
                                    # Save brand logo to centralized database
                                    if brand_logo_url and brand_canon and brand_canon != "unknown" and BrandLogoDatabase:
                                        try:
                                            logo_db = BrandLogoDatabase()
                                            logo_db.add_brand_logo(
                                                brand=brand_canon,
                                                logo_url=brand_logo_url,
                                                retailer="amazon",
                                                metadata={"ad_type": "Sponsored_Brand_Card", "keyword": keyword}
                                            )
                                        except Exception as logo_err:
                                            log(f"sb-cards: logo save error -> {logo_err}")
                            except Exception as e:
                                log(f"sb-cards: individual card error -> {e}")
                except Exception as e:
                    log(f"sb-cards: detect error -> {e}")

                # 3b) Sponsored Display Ads (with proper hydration wait)
                try:
                    log("display: detect")
                    # Look for display ads by stable structure, avoiding hashed classes
                    display_selectors = [
                        'div.s-left-ads-item div.AdHolder',  # Left rail skyscraper placements
                        'div[data-cel-widget*="MAIN-ADVERTISING"]',  # Stable widget pattern
                        'div[data-cel-widget*="advertising"]:not([data-asin]):not([cel_widget_id*="sb-"]):not([cel_widget_id*="VIDEO_SINGLE_PRODUCT"])',
                        'iframe[id*="ad"]',  # Stable iframe pattern
                        'div[id*="desktop-ad-"]',  # Stable ID pattern
                        'div:has([id*="ad-feedback-text"]):not([data-card-metrics-id*="sb-"])',  # Structure: ad feedback, not SB
                        'div[data-asin]:has([id*="ad-feedback"]):has(iframe)',  # Structure: ASIN + ad feedback + iframe (display ads)
                    ]
                    
                    all_display_ads = []
                    for selector in display_selectors:
                        try:
                            display_elements = page.locator(selector).all()
                            log(f"display: selector '{selector}' found {len(display_elements)} elements")
                            for ad in display_elements:
                                if ad.is_visible():
                                    all_display_ads.append(ad)
                        except Exception as e:
                            log(f"display: selector error {selector} -> {e}")
                    
                    display_count = len(all_display_ads)
                    log(f"display: found {display_count} total display ads")
                    
                    display_idx = 0
                    left_display_count = 0
                    bottom_display_count = 0
                    other_display_count = 0
                    for i, raw_ad in enumerate(all_display_ads[:10]):  # Soft limit for performance
                        if time_left() < 10:
                            break
                        
                        # Normalize to canonical container so cropping is consistent
                        ad = _normalize_display_container(raw_ad)

                        # Visibility pass AFTER normalization
                        if not ad.is_visible():
                            try:
                                ad.scroll_into_view_if_needed()
                                time.sleep(0.3)
                            except Exception:
                                pass
                        if not ad.is_visible():
                            log(f"display: skipping (not visible) index={i}")
                            continue

                        # Skip if this is clearly a product tile or inside an SB container
                        if ad.locator('xpath=ancestor::div[@data-component-type="s-search-result"]').count() > 0:
                            log("display: skip (inside product tile)")
                            continue
                        if ad.locator('xpath=ancestor::div[contains(@cel_widget_id,"sb-") or contains(@data-card-metrics-id,"sb-")]').count() > 0:
                            log("display: skip (inside SB container)")
                            continue

                        # Classify display slot (left rail / bottom / other)
                        slot = "other"
                        try:
                            if ad.locator('xpath=ancestor::div[contains(@class,"s-left-ads-item")]').count() > 0:
                                slot = "left"
                            elif ad.locator('xpath=.//div[contains(@cel_widget_id,"footer-slot_ad-placements") or contains(@cel_widget_id,"bottom-advertising")]').count() > 0:
                                slot = "bottom"
                        except Exception:
                            pass

                        # Enforce per-slot limits so we don't overshoot
                        if slot == "left" and left_display_count >= MAX_LEFT_DISPLAY:
                            log("display: skipping (left slot max reached)")
                            continue
                        if slot == "bottom" and bottom_display_count >= MAX_BOTTOM_DISPLAY:
                            log("display: skipping (bottom slot max reached)")
                            continue

                        # Choose per-slot dedupe sets
                        if slot == "left":
                            slot_fingerprints = captured_left_display_fingerprints
                            slot_bboxes = captured_left_display_bboxes
                        elif slot == "bottom":
                            slot_fingerprints = captured_bottom_display_fingerprints
                            slot_bboxes = captured_bottom_display_bboxes
                        else:
                            slot_fingerprints = captured_display_fingerprints
                            slot_bboxes = captured_display_bboxes

                        # Compute creative fingerprint and geometric overlap for dedupe
                        fp = _creative_fingerprint(ad)
                        bbox = None
                        try:
                            bbox = ad.bounding_box()
                        except Exception:
                            pass

                        # Strong dedupe: same creative fp within this slot => skip
                        if fp and fp in slot_fingerprints:
                            log("display: duplicate (fingerprint)")
                            continue

                        # Geometric dedupe within this slot
                        if bbox and _check_bbox_overlap(bbox, slot_bboxes, overlap_threshold=0.5):
                            log(f"display: duplicate (bbox overlap) -> {bbox}")
                            continue
                        
                        try:
                            brand_txt, brand_canon, message = _extract_brand_and_message(ad)
                            
                            # --- Hybrid Extraction Fallback (Gemini + Opus) ---
                            # If standard extraction failed (Unknown), try iframe piercing and positional matching
                            if not brand_txt or brand_txt.lower() == "unknown":
                                h_brand, h_msg = _try_hybrid_extraction(ad)
                                if h_brand:
                                    log(f"display: hybrid extraction success -> {h_brand} (msg={str(h_msg)[:30]}...)")
                                    brand_txt = h_brand
                                    if h_msg:
                                        message = h_msg
                                    
                                    # Re-canonicalize the new brand
                                    try:
                                        brand_canon = canonicalize(brand_txt)
                                        if not brand_canon and brand_txt.lower() != "unknown":
                                            add_brand(brand_txt)
                                            brand_canon = brand_txt.strip().title()
                                    except Exception as e:
                                        log(f"display: hybrid canonicalize error -> {e}")
                            # --------------------------------------------------

                            # Extract product description from display ads (multiple possible structures)
                            product_description = ""
                            try:
                                # Method 1: Standard product description div
                                product_desc_el = ad.locator('div[data-testid="product-description"]')
                                if product_desc_el.count() > 0:
                                    product_description = product_desc_el.first.inner_text().strip()
                                    log(f"display: found product description (testid) -> {product_description[:100]}...")
                                
                                # Method 2: Left rail ads with adLink-label span
                                elif ad.locator('span[id="adLink-label"]').count() > 0:
                                    adlink_el = ad.locator('span[id="adLink-label"]')
                                    full_text = adlink_el.first.inner_text().strip()
                                    # Extract product info (skip "Sponsored Ad." and "Product image." prefixes)
                                    lines = [line.strip() for line in full_text.split('\n') if line.strip()]
                                    # Find the product description (usually the longest line that's not price/action)
                                    for line in lines:
                                        if len(line) > 50 and not line.startswith(('Sponsored', 'Product', 'Shop', '$')) and not line.replace('.', '').isdigit():
                                            product_description = line
                                            break
                                    log(f"display: found product description (adLink-label) -> {product_description[:100]}...")
                                
                                # Method 3: Fallback - look for any long descriptive text
                                elif not product_description:
                                    desc_candidates = ad.locator('span:has-text("|"), div:has-text("|")').all()
                                    for candidate in desc_candidates:
                                        text = candidate.inner_text().strip()
                                        if len(text) > 50 and '|' in text:
                                            product_description = text
                                            log(f"display: found product description (fallback) -> {product_description[:100]}...")
                                            break
                                            
                            except Exception as e:
                                log(f"display: product description extraction error -> {e}")
                            
                            fname = _std_filename("amazon", brand_canon or "unknown", "Sponsored_Display", client, keyword, run_id, display_idx, ".png")
                            fpath = os.path.join(output_dir, "Sponsored_Display", fname)
                            
                            # Extended hydration wait for display ads (they're often lazy-loaded)
                            try:
                                ad.scroll_into_view_if_needed()
                                time.sleep(0.5)  # Initial wait
                                
                                # Wait for iframe/image content to actually load
                                content_loaded = _wait_for_iframe_content(page, ad, timeout_ms=5000)
                                
                                # Additional wait for any remaining lazy content
                                time.sleep(0.5)
                                log(f"display: hydration wait complete for ad {display_idx} (loaded={content_loaded})")
                                if not content_loaded:
                                    log(f"display: WARNING ad {display_idx} may not have loaded content")
                            except Exception as e:
                                log(f"display: hydration wait error -> {e}")
                            
                            # Fix clipped display ads: remove overflow:hidden and expand
                            # container height so the full ad creative is captured.
                            # Also scroll iframe content to top if present.
                            try:
                                ad_handle = ad.element_handle()
                                page.evaluate("""
                                  (el) => {
                                    const MAX_HEIGHT = 800;
                                    // Walk up ancestors and remove overflow clipping
                                    let node = el;
                                    for (let i = 0; i < 10 && node && node !== document.body; i++) {
                                      const cs = getComputedStyle(node);
                                      if (cs.overflow === 'hidden' || cs.overflowY === 'hidden') {
                                        node.style.setProperty('overflow', 'visible', 'important');
                                      }
                                      node = node.parentElement;
                                    }
                                    // For iframe-based ads, ensure iframe is tall enough
                                    // but cap at MAX_HEIGHT to avoid capturing the entire page
                                    const iframe = el.tagName === 'IFRAME' ? el : el.querySelector('iframe');
                                    if (iframe) {
                                      try {
                                        const doc = iframe.contentDocument || iframe.contentWindow.document;
                                        if (doc && doc.body) {
                                          const fullHeight = Math.min(doc.body.scrollHeight, MAX_HEIGHT);
                                          if (fullHeight > iframe.clientHeight) {
                                            iframe.style.setProperty('height', fullHeight + 'px', 'important');
                                            iframe.parentElement.style.setProperty('height', fullHeight + 'px', 'important');
                                          }
                                          // Scroll iframe content to top
                                          iframe.contentWindow.scrollTo(0, 0);
                                        }
                                      } catch(e) {
                                        // Cross-origin iframe — can't access content
                                      }
                                    }
                                  }
                                """, ad_handle)
                                time.sleep(0.3)
                            except Exception as e:
                                log(f"display: unclip error -> {e}")
                            
                            # Screenshot the actual ad creative (iframe/img), not the oversized container
                            shot_el = _display_screenshot_target(ad)
                            if shot_el is not ad:
                                log(f"display: targeting inner creative for ad {display_idx}")
                            shot_el.screenshot(path=fpath, timeout=4000)
                            
                            # Post-screenshot blank detection: skip if the capture is blank
                            if _is_blank_screenshot(fpath):
                                log(f"display: BLANK screenshot detected ({os.path.getsize(fpath)} bytes), deleting -> {fname}")
                                try:
                                    os.remove(fpath)
                                except OSError:
                                    pass
                                continue
                            
                            # OCR fallback: if brand is still unknown after DOM extraction,
                            # run OCR on the saved screenshot to find known brands
                            if (not brand_txt or brand_txt.lower() == "unknown") and os.path.exists(fpath):
                                try:
                                    from extractors.ocr_brand_detector import detect_brand_from_image_for_display
                                    ocr_brand = detect_brand_from_image_for_display(fpath)
                                    if ocr_brand and ocr_brand.lower() != "unknown":
                                        log(f"display: OCR fallback found brand -> {ocr_brand}")
                                        brand_txt = ocr_brand
                                        brand_canon = canonicalize(ocr_brand) or ocr_brand
                                        if not brand_canon or brand_canon.lower() == "unknown":
                                            brand_canon = ocr_brand
                                        # Rename screenshot to include correct brand
                                        new_fname = _std_filename("amazon", brand_canon, "Sponsored_Display", client, keyword, run_id, display_idx, ".png")
                                        new_fpath = os.path.join(output_dir, "Sponsored_Display", new_fname)
                                        if new_fpath != fpath:
                                            os.rename(fpath, new_fpath)
                                            fname = new_fname
                                            fpath = new_fpath
                                            log(f"display: renamed screenshot -> {new_fname}")
                                except Exception as e:
                                    log(f"display: OCR fallback error -> {e}")
                            
                            # Update dedupe sets after successful screenshot (per slot)
                            if bbox:
                                slot_bboxes.append(bbox)
                            if fp:
                                slot_fingerprints.add(fp)

                            # Increment per-slot counters
                            if slot == "left":
                                left_display_count += 1
                            elif slot == "bottom":
                                bottom_display_count += 1
                            else:
                                other_display_count += 1

                            # Use the normalized container to compute anchor, not the raw element
                            anchor = _module_anchor(ad)
                            if anchor in seen_anchors:
                                log(f"display: duplicate anchor skipped -> {anchor}")
                                continue
                            seen_anchors.add(anchor)
                            
                            # Add to ads array
                            module_id, eid = _build_ids("Sponsored_Display", "Display_Ad", brand_canon, anchor, run_id, display_idx)
                            ads.append({
                                "id": eid,
                                "module_id": module_id,
                                "type": "Sponsored_Display",
                                "subtype": "Display_Ad",
                                "slot": "left_rail" if slot == "left" else ("bottom" if slot == "bottom" else "top"),
                                "brand": brand_txt or "Unknown",
                                "brand_logo": None,
                                "title": message or None,
                                "description": product_description or None,
                                "cta": None,
                                "href": None,
                                "image_url": None,
                                "image_path": f"Sponsored_Display/{fname}",
                                "products": [],
                                "brand_canonical": brand_canon,
                                "advertisers": [brand_canon] if brand_canon else [],
                                "video_path": None,
                                "message": message,
                                "product_description": product_description,
                                "metadata": {
                                    "has_product_description": bool(product_description)
                                },
                            })
                            log(f"display: saved -> {fname}")
                            display_idx += 1
                        except Exception as e:
                            log(f"display: screenshot fail -> {e}")
                except Exception as e:
                    log(f"display: detect error -> {e}")

                # 4) Product Listings (Sponsored + Organic) - JSON data only, no screenshots
                try:
                    log("products: detect")
                    product_listings = []
                    
                    # Find all product result containers
                    product_containers = page.locator('div[data-component-type="s-search-result"]').all()
                    log(f"products: found {len(product_containers)} total product containers")
                    
                    for container in product_containers:
                        try:
                            if not container.is_visible():
                                continue
                                
                            # Extract basic product data
                            asin = container.get_attribute('data-asin') or ''
                            position_attr = container.get_attribute('data-csa-c-pos') or ''
                            position = int(position_attr) if position_attr.isdigit() else 0
                            
                            if not asin:
                                continue
                            
                            # Determine if sponsored using multiple reliable indicators
                            is_sponsored = False
                            
                            # Method 1: Sponsored popover (most reliable for in-grid products)
                            sponsored_popover = container.locator('[data-a-popover*="sp-info-popover"], [name*="sp-info-popover"]')
                            if sponsored_popover.count() > 0:
                                is_sponsored = True
                            
                            # Method 2: Sponsored label with specific classes
                            elif container.locator('.puis-sponsored-label-text, .puis-label-popover').count() > 0:
                                is_sponsored = True
                            
                            # Method 3: SSPA (Sponsored Product Ads) URLs
                            elif container.locator('[href*="/sspa/click"]').count() > 0:
                                is_sponsored = True
                            
                            # Method 4: Impression logger for sponsored products
                            elif container.locator('[data-component-type="s-impression-logger"]').count() > 0:
                                is_sponsored = True
                            
                            # Method 5: Generic sponsored text (fallback)
                            elif container.locator('span:has-text("Sponsored")').count() > 0:
                                is_sponsored = True
                            
                            # Extract product title
                            product_title = ""
                            title_selectors = [
                                'h2[aria-label]',
                                'h2 span',
                                'a[aria-label] span'
                            ]
                            for selector in title_selectors:
                                title_el = container.locator(selector)
                                if title_el.count() > 0:
                                    title_text = title_el.first.get_attribute('aria-label') or title_el.first.inner_text()
                                    if title_text and len(title_text) > 10:
                                        # Clean sponsored prefix from title
                                        product_title = title_text.replace('Sponsored Ad - ', '').strip()
                                        break
                            
                            # Extract rating
                            rating = ""
                            rating_el = container.locator('span[aria-hidden="true"].a-size-small.a-color-base')
                            if rating_el.count() > 0:
                                rating_text = rating_el.first.inner_text().strip()
                                if rating_text and '.' in rating_text:
                                    rating = rating_text
                            
                            # Extract review count
                            review_count = ""
                            review_selectors = [
                                'a[aria-label*="ratings"] span',
                                'span:has-text("K)")',
                                'span:has-text("(")'
                            ]
                            for selector in review_selectors:
                                review_el = container.locator(selector)
                                if review_el.count() > 0:
                                    review_text = review_el.first.inner_text().strip()
                                    if '(' in review_text and ')' in review_text:
                                        review_count = review_text
                                        break
                            
                            # Extract badges using multiple stable data attributes
                            badges = []
                            
                            # Method 1: Use stable data-csa-c-badge-text attribute
                            badge_elements = container.locator('[data-csa-c-badge-text]').all()
                            log(f"product: found {len(badge_elements)} badge elements with data-csa-c-badge-text for ASIN {asin}")
                            for badge_el in badge_elements:
                                badge_text = badge_el.get_attribute('data-csa-c-badge-text') or ''
                                if badge_text and badge_text not in badges:
                                    badges.append(badge_text)
                                    log(f"product: added badge '{badge_text}' for ASIN {asin}")
                            
                            # Method 2: Amazon Badges (Allure, editorial badges, etc.)
                            amazon_badge_elements = container.locator('[data-csa-c-content-id], [id*="BADGE"], span[aria-label*="Winner"], span[aria-label*="Choice"]').all()
                            for badge_el in amazon_badge_elements:
                                # Try content-id first (e.g., "ALLURE_BADGE")
                                content_id = badge_el.get_attribute('data-csa-c-content-id') or ''
                                if content_id and 'BADGE' in content_id:
                                    # Convert content ID to readable format
                                    badge_name = content_id.replace('_BADGE', '').replace('_', ' ').title()
                                    if badge_name not in badges:
                                        badges.append(badge_name)
                                
                                # Try aria-label for badge text (e.g., "Allure Winner")
                                aria_label = badge_el.get_attribute('aria-label') or ''
                                if aria_label and ('Winner' in aria_label or 'Choice' in aria_label):
                                    if aria_label not in badges:
                                        badges.append(aria_label)
                            
                            # Method 3: Rio badge components (Amazon's badge system)
                            rio_badges = container.locator('.rio-badge-label, .rio-badge-component').all()
                            for rio_el in rio_badges:
                                rio_text = rio_el.inner_text().strip()
                                # Remove info icon text and clean up
                                if rio_text and len(rio_text) < 50:
                                    rio_text = rio_text.split('\n')[0].strip()  # Take first line only
                                    if rio_text and rio_text not in badges:
                                        badges.append(rio_text)
                            
                            # Method 4: Only capture real badges, not product details
                            real_badge_selectors = [
                                'span:has-text("Amazon\'s Choice")',  # Amazon's Choice badge
                                'span:has-text("Best Seller")',      # Best Seller badge
                                'span:has-text("#1 Best Seller")',   # #1 Best Seller badge
                                'span:has-text("Overall Pick")',     # Overall Pick badge
                                'span:has-text("Climate Pledge Friendly")',  # Climate badge
                                'span:has-text("Top Rated")',        # Top Rated badge
                                '.a-badge-region span',              # Badge region spans
                            ]
                            
                            # Only extract badges that are actual Amazon badges, not product details
                            for selector in real_badge_selectors:
                                try:
                                    badge_elements = container.locator(selector).all()
                                    for badge_el in badge_elements:
                                        badge_text = badge_el.inner_text().strip()
                                        
                                        # Filter out product details (size, quantity, features)
                                        if badge_text and len(badge_text) < 50 and badge_text not in badges:
                                            # Skip product details patterns
                                            skip_patterns = [
                                                r'\d+(\.\d+)?\s*(fl\s*oz|ounce|count|piece|pack)',  # Size/quantity
                                                r'pack\s+of\s+\d+',  # Pack of X
                                                r'\d+\s*(fl\s*oz|ounce|count|piece)',  # Measurements
                                                r'(anti-acne|acne prevention|fragrance free|hydrating|soothing)',  # Product features
                                                r'(capsule|unscented|prescription required)',  # Product attributes
                                            ]
                                            
                                            is_product_detail = False
                                            for pattern in skip_patterns:
                                                if re.search(pattern, badge_text.lower()):
                                                    is_product_detail = True
                                                    break
                                            
                                            if not is_product_detail:
                                                badges.append(badge_text)
                                                log(f"product: added real badge '{badge_text}' for ASIN {asin}")
                                            else:
                                                log(f"product: skipped product detail '{badge_text}' for ASIN {asin}")
                                except Exception as e:
                                    log(f"product: badge extraction error with selector {selector} -> {e}")
                            
                            log(f"product: final badge count for ASIN {asin}: {len(badges)} badges: {badges}")
                            
                            # Create product listing entry
                            product_data = {
                                "asin": asin,
                                "position": position,
                                "is_sponsored": is_sponsored,
                                "product_title": product_title,
                                "rating": rating,
                                "review_count": review_count,
                                "badges": badges,
                                "listing_type": "sponsored_product" if is_sponsored else "organic_product"
                            }
                            
                            product_listings.append(product_data)
                            log(f"products: extracted -> ASIN: {asin}, Position: {position}, Sponsored: {is_sponsored}, Title: {product_title[:50]}...")
                            
                        except Exception as e:
                            log(f"products: extraction error for container -> {e}")
                    
                    # Sort by position and add to ads array
                    product_listings.sort(key=lambda x: x['position'])
                    for product in product_listings:
                        module_id, eid = _build_ids("Product_Listing", product['listing_type'], product['asin'], f"pos_{product['position']}", run_id, product['position'])
                        ads.append({
                            "id": eid,
                            "module_id": module_id,
                            "type": "Product_Listing",
                            "subtype": product['listing_type'],
                            "brand": None,
                            "brand_logo": None,
                            "title": product['product_title'] or None,
                            "description": None,
                            "cta": None,
                            "href": None,
                            "image_url": None,
                            "image_path": None,  # No screenshots for product listings
                            "products": [],
                            "asin": product['asin'],
                            "position": product['position'],
                            "is_sponsored": product['is_sponsored'],
                            "product_title": product['product_title'],
                            "rating": product['rating'],
                            "review_count": product['review_count'],
                            "badges": product['badges'],
                            "video_path": None,
                            "metadata": {
                                "badge_count": len(product['badges']),
                                "has_rating": bool(product['rating']),
                                "has_reviews": bool(product['review_count'])
                            }
                        })
                    
                    log(f"products: added {len(product_listings)} product listings to ads array")
                    
                except Exception as e:
                    log(f"products: detect error -> {e}")

                log("debug: essential ad detection complete")
                
                # Continue with remaining ad detection sections
                # 4) Carousels - Dynamic detection using template pattern
                try:
                    log("car: detect")
                    car_idx = 0
                    
                    # Find carousels using the actual HTML structure: s-searchgrid-carousel components
                    carousel_containers = page.locator('span[data-component-type="s-searchgrid-carousel"]')
                    carousel_count = carousel_containers.count()
                    log(f"car: found {carousel_count} carousels using s-searchgrid-carousel selector")
                    
                    for carousel_idx in range(carousel_count):
                        if time_left() < 20:
                            log("car: budget low, break")
                            break
                        
                        try:
                            # Get the specific carousel container
                            carousel_container = carousel_containers.nth(carousel_idx)
                            
                            # Extract the header text from aria-labelledby reference
                            heading = "Unknown Carousel"
                            try:
                                # Look for aria-labelledby attribute to find the heading
                                labelledby_element = carousel_container.locator('[aria-labelledby]').first
                                if labelledby_element.count() > 0:
                                    labelledby_id = labelledby_element.get_attribute('aria-labelledby')
                                    if labelledby_id:
                                        # Find the heading element by ID, scoped to the same widget block
                                        heading_locator = carousel_container.locator(
                                            f'xpath=ancestor::div[contains(@class, "s-include-content-margin")][1]//h2[@id="{labelledby_id}"]'
                                        )
                                        if heading_locator.count() == 0:
                                            heading_locator = carousel_container.locator(
                                                'xpath=ancestor::div[contains(@class, "s-include-content-margin")][1]//h2'
                                            )
                                        if heading_locator.count() > 0:
                                            heading = heading_locator.first.inner_text().strip()
                                            log(f"car: extracted header '{heading}' from carousel {carousel_idx} using aria-labelledby")
                                        else:
                                            log(f"car: heading element not found for ID '{labelledby_id}'")
                                    else:
                                        log(f"car: no aria-labelledby ID found for carousel {carousel_idx}")
                                else:
                                    log(f"car: no aria-labelledby attribute found for carousel {carousel_idx}")
                            except Exception as e:
                                log(f"car: header extraction error for carousel {carousel_idx} -> {e}")
                            
                            # Skip "Brands related to your search" as it's handled as individual sponsored brand cards
                            if heading == "Brands related to your search":
                                log(f"car: skipping '{heading}' - handled as individual brand cards")
                                continue
                            
                            # Scroll into view
                            carousel_container.scroll_into_view_if_needed()
                            time.sleep(0.1)
                            
                            # Find parent container that includes both header and carousel
                            try:
                                # Look for a parent that contains both the heading and the carousel
                                common_parent = carousel_container.locator('xpath=ancestor::div[contains(@class, "s-include-content-margin")][1]')
                                if common_parent.count() > 0:
                                    container_el = common_parent.first
                                    log(f"car: using common parent container (includes header) for '{heading}'")
                                else:
                                    # Fallback: use carousel container only
                                    container_el = carousel_container
                                    log(f"car: fallback to carousel-only container for '{heading}'")
                            except Exception as e:
                                log(f"car: parent container detection error -> {e}, using carousel-only")
                                container_el = carousel_container
                            
                            # Take screenshot
                            fname = _std_filename("amazon", "unknown", "Sponsored_Carousel", client, keyword, run_id, car_idx, ".png")
                            fpath = os.path.join(output_dir, "Sponsored_Carousel", fname)
                            container_el.screenshot(path=fpath, timeout=4000)
                            
                            # Add to ads array
                            module_id, eid = _build_ids("Sponsored_Carousel", "Carousel", "unknown", f"carousel_{car_idx}", run_id, car_idx)
                            ads.append({
                                "id": eid,
                                "module_id": module_id,
                                "type": "Sponsored_Carousel",
                                "subtype": "Carousel",
                                "brand": "Unknown",
                                "brand_logo": None,
                                "title": heading or None,
                                "description": None,
                                "cta": None,
                                "href": None,
                                "image_url": None,
                                "image_path": f"Sponsored_Carousel/{fname}",
                                "products": [],
                                "brand_canonical": "unknown",
                                "advertisers": [],
                                "header": heading,
                                "video_path": None,
                                "message": heading,
                                "metadata": {},
                            })
                            log(f"car: saved -> {fname}")
                            car_idx += 1
                                
                        except Exception as e:
                            log(f"car: carousel processing error for carousel {carousel_idx} -> {e}")
                except Exception as e:
                    log(f"car: detect error -> {e}")
                
                # Save HTML content
                try:
                    log("html: save")
                    html_content = page.content()
                    with open(html_path, "w", encoding="utf-8") as f:
                        f.write(html_content)
                    log(f"html: saved -> {html_path} exists={os.path.exists(html_path)} size={os.path.getsize(html_path) if os.path.exists(html_path) else 0}")
                except Exception as e:
                    log(f"html: save error -> {e}")

                success = True
                log("success: marked as True")
            finally:
                # Save tracing only if it was started
                try:
                    if tracing_enabled:
                        trace_path = os.path.join(runs_dir, f"trace_{ts}.zip")
                        bctx.tracing.stop(path=trace_path)
                        log(f"trace: saved -> {trace_path} exists={os.path.exists(trace_path)} size={os.path.getsize(trace_path) if os.path.exists(trace_path) else 0}")
                    else:
                        log("trace: skipped (not enabled)")
                except Exception as e:
                    log(f"trace: stop error -> {e}")
                try:
                    if bctx:
                        bctx.close()
                except Exception:
                    pass
                try:
                    p.stop()
                except Exception:
                    pass
    except TimeoutError as e:
        log(f"fatal: browser lock timeout -> {e}")
        return False
        bctx = None
        try:
            try:
                bctx = p.chromium.launch_persistent_context(
                    user_data_dir=profile_dir,
                    channel="chrome",
                    headless=False,
                    viewport={"width": 1400, "height": 900},
                    locale="en-US",
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-default-browser-check",
                        "--disable-features=IsolateOrigins,site-per-process",
                        # Keep window visible but don't steal focus
                        "--disable-focus-on-load",
                        "--noerrdialogs",
                    ],
                )
            except Exception as e:
                log(f"launch: chrome channel failed -> {e}; retry with default chromium")
                bctx = p.chromium.launch_persistent_context(
                    user_data_dir=profile_dir,
                    headless=False,
                    viewport={"width": 1400, "height": 900},
                    locale="en-US",
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-default-browser-check",
                        "--disable-features=IsolateOrigins,site-per-process",
                        # Keep window visible but don't steal focus
                        "--disable-focus-on-load",
                        "--noerrdialogs",
                    ],
                )
            page = bctx.new_page()

            # Wire minimal browser events (avoid noisy response logs)
            try:
                page.on("console", lambda m: log(f"[console:{m.type()}] {m.text()}"))
                page.on("pageerror", lambda e: log(f"[pageerror] {e}"))
                page.on("requestfailed", lambda r: log(f"[requestfailed] {r.method()} {r.url}"))
            except Exception:
                pass

            # Start tracing only if enabled
            tracing_enabled = False
            try:
                if os.environ.get("AMAZON_TRACE") == "1":
                    bctx.tracing.start(screenshots=True, snapshots=True, sources=False)
                    tracing_enabled = True
                    log("trace: started")
            except Exception as e:
                log(f"trace: start error -> {e}")

            url = _search_url(keyword)
            log(f"navigate: {url}")
            goto_with_retries(page, url, attempts=3, wait_until="domcontentloaded", timeout_ms=45000)

            log("cookies/login")
            accept_amazon_cookies(page)
            ensure_amazon_logged_in(page)

            # Wait readiness heuristics
            try:
                page.wait_for_selector('div[data-component-type="s-search-result"]', timeout=8000)
                log("ready: s-search-result present")
            except Exception as e:
                log(f"ready: timeout waiting for results -> {e}")
                try:
                    time.sleep(3)
                except Exception:
                    pass

            log("scrolling")
            try:
                page.evaluate("""
                  () => new Promise((resolve) => {
                    const sleep = (ms) => new Promise(r => setTimeout(r, ms));
                    (async () => {
                      let stable = 0; let last = 0;
                      for (let i=0; i<12 && stable<3; i++) {
                        const imgs = document.querySelectorAll('img');
                        const loaded = Array.from(imgs).filter(i => i.complete && i.naturalWidth > 10).length;
                        if (loaded === last) stable++; else stable = 0;
                        last = loaded; await sleep(600);
                      }
                      resolve(true);
                    })()
                  })
                """)
                log("scrolling: bottom images settled")
            except Exception as e:
                log(f"scrolling: settle error -> {e}")

            # Create output folders
            for folder in [
                "Main",
                "Sponsored_Brand_Video",
                "Sponsored_Brand",
                "Sponsored_Carousel",
                "Sponsored_Display",
                "ASIN_Images",
            ]:
                os.makedirs(os.path.join(output_dir, folder), exist_ok=True)

            # 1) Main full-page screenshot (hide sticky headers before capture)
            try:
                log("main: prepare (hide sticky headers, scroll top)")
                # Hide Amazon sticky headers/navs to avoid covering content (fast inline style injection)
                try:
                    log("main: injecting CSS to hide sticky headers")
                    result = page.evaluate("""
                    () => {
                      try {
                        const css = '#navbar,#nav-belt,#nav-main,#nav-progressive-subnav,header,[data-testid="header"],[class*="sticky" i],[data-sticky],[style*="position: sticky"],.sg-col-20-of-24 .s-desktop-width-max .s-desktop-toolbar,.s-desktop-toolbar .s-desktop-toolbar{display:none!important;visibility:hidden!important;}';
                        const st = document.createElement('style');
                        st.type = 'text/css';
                        st.textContent = css;
                        document.head.appendChild(st);
                        return 'success';
                      } catch(e) {
                        return 'error: ' + e.message;
                      }
                    }
                    """)
                    log(f"main: CSS injection result -> {result}")
                except Exception as css_err:
                    log(f"main: style inject error -> {css_err}")
                # Ensure we are at the very top for consistent full-page shot
                try:
                    page.evaluate("window.scrollTo(0, 0)")
                    try:
                        time.sleep(0.3)
                    except Exception:
                        pass
                except Exception:
                    pass
                # Left-rail hydration probe before main screenshot
                try:
                    log("main: left-rail hydration probe")
                    left_rail_ads = page.locator('div.s-left-ads-item img')
                    if left_rail_ads.count() > 0:
                        # Wait for first left-rail image to load
                        try:
                            left_rail_ads.first.wait_for(state="visible", timeout=2000)
                            time.sleep(0.5)  # Brief settle time
                        except Exception:
                            pass
                    log("main: hydration probe complete")
                except Exception as e:
                    log(f"main: hydration probe error -> {e}")
                
                # Wait for bottom content to fully hydrate before full-page screenshot
                try:
                    log("main: bottom hydration wait")
                    # Scroll to bottom to trigger lazy loading, then back to top
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(1.0)  # Wait for bottom content to load
                    page.evaluate("window.scrollTo(0, 0)")
                    time.sleep(0.5)  # Brief settle time
                    log("main: bottom hydration complete")
                except Exception as e:
                    log(f"main: bottom hydration error -> {e}")
                
                log("main: screenshot")
                main_name = _std_filename("amazon", "unknown", "Main", client, keyword, run_id, 0, ".png")
                main_path = os.path.join(output_dir, "Main", main_name)
                page.screenshot(path=main_path, full_page=True)
                log(f"main: saved -> {main_path} exists={os.path.exists(main_path)} size={os.path.getsize(main_path) if os.path.exists(main_path) else 0}")
            except Exception as e:
                log(f"main: fail -> {e}")

            # 2) Sponsored Brand Video (SBV) - REMOVED DUPLICATE SECTION
            # Note: SBV detection is already handled comprehensively in the first section above
            # Note: Carousel detection is already handled in section 4 above

            # Legacy carousel and sb-themed code removed - handled by new dynamic system above

            # Broken legacy carousel and sb-themed code removed 
            # Clean sb-themed detection is handled later in the file

            # 3b2) Sponsored Brand Headlines (v2 inline modules)
            try:
                        # Scroll heading into view first
                        try:
                            h.scroll_into_view_if_needed()
                            time.sleep(0.1)
                        except Exception:
                            pass
                        
                        # Method 1: Try to find the complete carousel container (includes header + items)
                        try:
                            carousel_container = h.locator('xpath=ancestor::span[@data-component-type="s-searchgrid-carousel"][1]')
                            if carousel_container.count() > 0:
                                container_el = carousel_container.first
                                log(f"car: using complete carousel container for {heading}")
                            else:
                                # Method 2: Fallback to original logic for finding container with enough content
                                heading_el = h.element_handle()
                                handle = page.evaluate_handle(
                                    """(el) => {
                                        let n = el;
                                        const enough = (node) => {
                                            try {
                                                const imgs = node.querySelectorAll('img.s-image').length;
                                                const cards = node.querySelectorAll('div[data-component-type=\"s-search-result\"]').length;
                                                return imgs >= 8 || cards >= 8;
                                            } catch(e) { return false; }
                                        };
                                        while (n && n.parentElement) {
                                            if (enough(n)) return n;
                                            n = n.parentElement;
                                        }
                                        return el;
                                    }""",
                                    heading_el,
                                )
                                container_el = handle.as_element()
                                log(f"car: using fallback container detection for {heading}")
                        except Exception as e:
                            log(f"car: container detection error -> {e}")
                            container_el = None
            except Exception as e:
                log(f"sb-headlines: section error -> {e}")

            # Products inside carousel
            products = []
            try:
                # Define root element for product extraction
                root_el = container_el if container_el else h.locator("xpath=ancestor::div[1]")
                try:
                    root_el.scroll_into_view_if_needed()
                    time.sleep(0.2)
                except Exception:
                    pass
                try:
                    el_handle = root_el.element_handle()
                    page.evaluate("""
                      (el) => new Promise((resolve) => {
                        const sleep = (ms) => new Promise(r => setTimeout(r, ms));
                        (async () => {
                          let stable = 0; let last = 0;
                          for (let i=0; i<6 && stable<2; i++) {
                            const imgs = Array.from(el.querySelectorAll('img')).filter(i => i.complete && i.naturalWidth > 10).length;
                            if (imgs === last) stable++; else stable = 0;
                            last = imgs; await sleep(300);
                          }
                          resolve(true);
                        })()
                      })
                    """, el_handle)
                except Exception:
                    pass
                cards = root_el.locator('div[data-asin]')
                cnt = min(cards.count(), 24)
                for i in range(cnt):
                            c = cards.nth(i)
                            asin = _get_attr(c, 'data-asin') or None
                            title = None
                            href = None
                            image_url = None
                            image_path = None
                            central_image_path = None
                            price_text = None
                            try:
                                a = c.locator('h2 a, a.a-link-normal').first
                                if a.count() > 0:
                                    href = a.get_attribute('href')
                                    if href and not href.startswith('http'):
                                        href = f"https://www.amazon.com{href}"
                            except Exception:
                                pass
                            try:
                                title = (c.locator('h2 a span').first.text_content() or '').strip()
                            except Exception:
                                pass
                            try:
                                img = c.locator('img.s-image').first
                                if img.count() > 0:
                                    src = img.get_attribute('src')
                                    if src and src.startswith('http'):
                                        image_url = src
                                        try:
                                            from urllib.parse import urlparse
                                            ext = os.path.splitext(urlparse(src).path)[1] or ".jpg"
                                        except Exception:
                                            ext = ".jpg"
                                        file_name = (asin or f"car_{car_idx}_{i}") + ext
                                        central_full = central_asin_dir / file_name
                                        try:
                                            r = requests.get(src, timeout=10)
                                            if r.ok:
                                                with open(central_full, 'wb') as fimg:
                                                    fimg.write(r.content)
                                                image_path = str(central_full.relative_to(project_root))
                                                # Central ASIN DB only - no client copying
                                        except Exception:
                                            pass
                            except Exception:
                                pass
                            try:
                                price_text = (c.locator('span.a-price .a-offscreen').first.text_content() or '').strip()
                            except Exception:
                                pass
                            if any([asin, title, href, image_url]):
                                products.append({
                                    "asin": asin,
                                    "href": href,
                                    "title": title,
                                    "image_url": image_url,
                                    "image_path": image_path,
                                    "central_image_path": image_path,
                                    "price": price_text,
                                })
            except Exception as e:
                log(f"car: products parse error -> {e}")

            # End of broken legacy carousel code - removed
            # Clean carousel detection is handled earlier in the file

            # 3b) Sponsored Brand Themed Collections (direct detection)
            try:
                log("sb-themed: detect")
                # v1 (cel_widget_id) and v2 (data-card-metrics-id) themed collections
                themed = page.locator(
                    'div[cel_widget_id^="sb-themed-collection-"], '
                    'div[data-card-metrics-id*="sb-themed-collection"]'
                )
                tcount = themed.count()
                for i in range(tcount):
                    if time_left() < 15:
                        log("sb-themed: budget low, break")
                        break
                    el = themed.nth(i)
                    if not el.is_visible():
                        continue
                    brand_txt, brand_canon, message = _extract_brand_and_message(el)
                    raw_cel = _get_attr(el, 'cel_widget_id') or ''
                    raw_metrics = _get_attr(el, 'data-card-metrics-id') or ''
                    subtype = "Top" if ("top-slot" in raw_cel or "top" in raw_metrics) else "Inline"
                    adv_for_name = brand_canon or "unknown"
                    fname = _std_filename("amazon", adv_for_name, "Sponsored_Brand", client, keyword, run_id, i, ".png")
                    fpath = os.path.join(output_dir, "Sponsored_Brand", fname)
                    try:
                        try:
                            el.scroll_into_view_if_needed()
                            time.sleep(0.2)
                        except Exception:
                            pass
                        try:
                            el_handle = el.element_handle()
                            page.evaluate("""
                              (el) => new Promise((resolve) => {
                                const sleep = (ms) => new Promise(r => setTimeout(r, ms));
                                (async () => {
                                  let stable = 0; let last = 0;
                                  for (let i=0; i<6 && stable<2; i++) {
                                    const imgs = Array.from(el.querySelectorAll('img')).filter(img => img.complete && img.naturalWidth>10).length;
                                    if (imgs === last) stable++; else stable = 0;
                                    last = imgs; await sleep(300);
                                  }
                                  resolve(true);
                                })
                              })
                            """, el_handle)
                        except Exception:
                            pass
                        try:
                            page.evaluate("""
                                () => {
                                    const style = document.createElement('style');
                                    style.textContent = '* { transition: none !important; animation: none !important; }';
                                    document.head.appendChild(style);
                                }
                            """)
                        except Exception:
                            pass
                        try:
                            page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
                        except Exception:
                            pass
                        
                        # Container signature dedupe
                        container_sig = _get_container_signature(el)
                        if container_sig and container_sig in captured_containers:
                            log(f"sb-themed: duplicate container skipped -> {container_sig}")
                            continue
                        
                        # Geometric overlap check
                        try:
                            bbox = el.bounding_box()
                            log(f"sb-themed: element bbox -> {bbox}")
                            if bbox and _check_bbox_overlap(bbox, captured_bboxes):
                                log(f"sb-themed: overlapping bbox skipped -> {bbox}")
                                continue
                        except Exception as e:
                            log(f"sb-themed: bbox check error -> {e}")
                            bbox = None
                        
                        # Debug: Check element details before screenshot
                        try:
                            tag_name = el.evaluate("el => el.tagName")
                            class_name = el.get_attribute("class") or "no-class"
                            data_metrics = el.get_attribute("data-card-metrics-id") or "no-metrics"
                            child_count = el.locator("*").count()
                            log(f"sb-themed: screenshotting -> tag: {tag_name}, class: {class_name[:50]}..., metrics: {data_metrics[:50]}..., children: {child_count}, bbox: {bbox}")
                        except Exception as e:
                            log(f"sb-themed: debug error -> {e}")
                        
                        el.screenshot(path=fpath, timeout=4000)
                        anchor = _module_anchor(el)
                        if anchor in seen_anchors:
                            log(f"sb-themed: duplicate anchor skipped -> {anchor}")
                            continue
                        seen_anchors.add(anchor)
                        
                        # Record successful captures
                        if container_sig:
                            captured_containers.add(container_sig)
                        if bbox:
                            captured_bboxes.append(bbox)
                        module_id, eid = _build_ids("Sponsored_Brand", f"Themed_Collection_{subtype}", brand_canon, anchor, run_id, i)
                        if module_id in captured_modules:
                            log(f"sb-themed: duplicate module skipped -> {module_id}")
                            continue
                        captured_modules.add(module_id)
                        # Products
                        products = []
                        cards = el.locator('div[data-asin]')
                        cnt = min(cards.count(), 24)
                        for j in range(cnt):
                            c = cards.nth(j)
                            asin = _get_attr(c, 'data-asin') or None
                            title = None
                            href = None
                            image_url = None
                            image_path = None
                            central_image_path = None
                            price_text = None
                            try:
                                a = c.locator('h2 a, a.a-link-normal').first
                                if a.count() > 0:
                                    href = a.get_attribute('href')
                                    if href and not href.startswith('http'):
                                        href = f"https://www.amazon.com{href}"
                            except Exception:
                                pass
                            try:
                                title = (c.locator('h2 a span').first.text_content() or '').strip()
                            except Exception:
                                pass
                            try:
                                img = c.locator('img.s-image').first
                                if img.count() > 0:
                                    src = img.get_attribute('src')
                                    if src and src.startswith('http'):
                                        image_url = src
                                        try:
                                            from urllib.parse import urlparse
                                            ext = os.path.splitext(urlparse(src).path)[1] or ".jpg"
                                        except Exception:
                                            ext = ".jpg"
                                        # Skip image download for sb-themed performance (60-90s savings)
                                        # Only store the URL for reference
                                        image_path = None
                            except Exception:
                                pass
                            try:
                                price_text = (c.locator('span.a-price .a-offscreen').first.text_content() or '').strip()
                            except Exception:
                                pass
                            if any([asin, title, href, image_url]):
                                products.append({
                                    "asin": asin,
                                    "href": href,
                                    "title": title,
                                    "image_url": image_url,
                                    "image_path": image_path,
                                    "central_image_path": central_image_path,
                                    "price": price_text,
                                })
                        ads.append({
                            "id": eid,
                            "module_id": module_id,
                            "type": "Sponsored_Brand",
                            "subtype": f"Themed_Collection_{subtype}",
                            "brand": brand_txt or "Unknown",
                            "brand_canonical": brand_canon,
                            "advertisers": [brand_canon] if brand_canon else [],
                            "header": message,
                            "products": products,
                            "capture_entire_carousel": True,
                            "position": i + 1,
                            "image_path": f"Sponsored_Brand/{fname}",
                            "video_path": None,
                            "message": message,
                            "metadata": {"count": len(products)},
                        })
                        log(f"sb-themed: saved -> {fpath} module_id={module_id}")
                    except Exception as e:
                        log(f"sb-themed: screenshot fail -> {e}")
            except Exception as e:
                log(f"sb-themed: detect error -> {e}")

            # 3b2) Sponsored Brand Headlines (v2 inline modules)
            try:
                # Quick visibility debug for v2
                try:
                    v2_count = page.locator('div[data-card-metrics-id*="sb-themed-collection"] a[data-elementid="sb-headline"]').count()
                    log(f"sb-headline(v2 themed) count = {v2_count}")
                except Exception:
                    pass
                
                log("sb-headline: detect")
                headlines = page.locator('a[data-elementid="sb-headline"]')
                hcount = headlines.count()
                log(f"sb-headline: found {hcount} headlines")
                
                for i in range(hcount):
                    link = headlines.nth(i)
                    if not link.is_visible():
                        continue
                    
                    # Prefer the v2 wrapper (CardInstance…), then v2 metrics, then legacy sponsored, then nearest div
                    container = link.locator("xpath=ancestor::div[starts-with(@id,'CardInstance')][1]")
                    if container.count() == 0:
                        container = link.locator("xpath=ancestor::div[contains(@data-card-metrics-id,'sb-themed-collection')][1]")
                    if container.count() == 0:
                        container = link.locator("xpath=ancestor::div[contains(@cel_widget_id,'sponsored') or contains(@data-cel-widget,'sponsored')][1]")
                    if container.count() == 0:
                        container = link.locator("xpath=ancestor::div[1]")
                    
                    if container.count() == 0:
                        log(f"sb-headline: no container found for headline {i}")
                        continue
                    
                    container = _normalize_sb_container(container)
                    if not _is_sb_container(container):
                        log("sb-headline: skip — not an SB container after normalize")
                        continue
                    
                    brand_txt, brand_canon, message = _extract_brand_and_message(container)
                    
                    # Container signature dedupe (check first - most reliable)
                    container_sig = _get_container_signature(container)
                    if container_sig and container_sig in captured_containers:
                        log(f"sb-headline: duplicate container skipped -> {container_sig}")
                        continue
                    
                    # Geometric overlap check
                    try:
                        bbox = container.bounding_box()
                        if bbox and _check_bbox_overlap(bbox, captured_bboxes):
                            log(f"sb-headline: overlapping bbox skipped -> {bbox}")
                            continue
                    except Exception as e:
                        log(f"sb-headline: bbox check error -> {e}")
                        bbox = None
                    
                    anchor = _module_anchor(container)
                    if anchor in seen_anchors:
                        log(f"sb-headline: duplicate anchor skipped -> {anchor}")
                        continue
                    seen_anchors.add(anchor)
                    
                    adv_for_name = brand_canon or "unknown"
                    fname = _std_filename("amazon", adv_for_name, "Sponsored_Brand", client, keyword, run_id, i, ".png")
                    fpath = os.path.join(output_dir, "Sponsored_Brand", fname)
                    
                    try:
                        # Scroll into view and freeze animations
                        try:
                            container.scroll_into_view_if_needed()
                            time.sleep(0.2)
                        except Exception:
                            pass
                        try:
                            page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
                        except Exception:
                            pass
                        
                        container.screenshot(path=fpath, timeout=4000)
                        
                        # Record successful captures
                        if container_sig:
                            captured_containers.add(container_sig)
                        if bbox:
                            captured_bboxes.append(bbox)
                        module_id, eid = _build_ids("Sponsored_Brand", "Headline", brand_canon, anchor, run_id, i)
                        if module_id in captured_modules:
                            log(f"sb-headline: duplicate module skipped -> {module_id}")
                            continue
                        captured_modules.add(module_id)
                        
                        ads.append({
                            "id": eid,
                            "module_id": module_id,
                            "type": "Sponsored_Brand",
                            "subtype": "Headline",
                            "brand": brand_txt or "Unknown",
                            "brand_canonical": brand_canon,
                            "advertisers": [brand_canon] if brand_canon else [],
                            "image_path": f"Sponsored_Brand/{fname}",
                            "video_path": None,
                            "message": message,
                            "metadata": {},
                        })
                        log(f"sb-headline: saved -> {fpath} module_id={module_id}")
                    except Exception as e:
                        log(f"sb-headline: screenshot fail -> {e}")
            except Exception as e:
                log(f"sb-headline: detect error -> {e}")

            # 3c) Sponsored Display (Left rail / Bottom)
            # Left rail: .s-left-ads-item contains the outer wrapper, but the ad is .AdHolder inside it
            try:
                log("display: detect left rail")
                # Select the actual AdHolder inside left rail containers
                left_ads = page.locator('div.s-left-ads-item div.AdHolder')
                lcount = min(left_ads.count(), MAX_LEFT_DISPLAY)
                log(f"display: left rail found {lcount} ads")
                for i in range(lcount):
                    el = left_ads.nth(i)
                    if not el.is_visible():
                        continue
                    # Scroll into view and wait for iframe/image content to load
                    try:
                        el.scroll_into_view_if_needed()
                        time.sleep(0.3)
                    except Exception:
                        pass
                    content_loaded = _wait_for_iframe_content(page, el, timeout_ms=4000)
                    if not content_loaded:
                        log(f"display: left ad {i} content may not have loaded")
                    brand_txt, brand_canon, message = _extract_brand_and_message(el)
                    adv_for_name = brand_canon or "unknown"
                    fname = _std_filename("amazon", adv_for_name, "Sponsored_Display", client, keyword, run_id, i, ".png")
                    fpath = os.path.join(output_dir, "Sponsored_Display", fname)
                    try:
                        # Freeze animations (Instacart pattern)
                        try:
                            page.evaluate("""
                                () => {
                                    const style = document.createElement('style');
                                    style.textContent = '* { transition: none !important; animation: none !important; }';
                                    document.head.appendChild(style);
                                }
                            """)
                        except Exception:
                            pass
                        # Flush layout
                        try:
                            page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
                        except Exception:
                            pass
                        # Screenshot the actual ad creative (iframe/img), not the oversized container
                        shot_el = _display_screenshot_target(el)
                        if shot_el is not el:
                            log(f"display: left targeting inner creative for ad {i}")
                        shot_el.screenshot(path=fpath, timeout=4000)
                        # Post-screenshot blank detection
                        if _is_blank_screenshot(fpath):
                            log(f"display: left BLANK screenshot detected ({os.path.getsize(fpath)} bytes), deleting -> {fname}")
                            try:
                                os.remove(fpath)
                            except OSError:
                                pass
                            continue
                        # OCR fallback: if brand is still unknown, run OCR on the screenshot
                        if (not brand_txt or brand_txt.lower() == "unknown") and os.path.exists(fpath):
                            try:
                                from extractors.ocr_brand_detector import detect_brand_from_image_for_display
                                ocr_brand = detect_brand_from_image_for_display(fpath)
                                if ocr_brand and ocr_brand.lower() != "unknown":
                                    log(f"display: left OCR fallback found brand -> {ocr_brand}")
                                    brand_txt = ocr_brand
                                    brand_canon = canonicalize(ocr_brand) or ocr_brand
                                    if not brand_canon or brand_canon.lower() == "unknown":
                                        brand_canon = ocr_brand
                                    adv_for_name = brand_canon
                                    new_fname = _std_filename("amazon", adv_for_name, "Sponsored_Display", client, keyword, run_id, i, ".png")
                                    new_fpath = os.path.join(output_dir, "Sponsored_Display", new_fname)
                                    if new_fpath != fpath:
                                        os.rename(fpath, new_fpath)
                                        fname = new_fname
                                        fpath = new_fpath
                                        log(f"display: left renamed screenshot -> {new_fname}")
                            except Exception as e:
                                log(f"display: left OCR fallback error -> {e}")
                        anchor = _module_anchor(el)
                        if re.match(r'^(sb|sponsoredb|sponsoredbrands)', (anchor or '').lower()):
                            log(f"display: skip sb-like anchor -> {anchor}")
                            continue
                        module_id, eid = _build_ids("Sponsored_Display", "Left_Rail_Display", brand_canon, anchor, run_id, i)
                        if anchor in seen_anchors:
                            log(f"display: left duplicate anchor skipped -> {anchor}")
                            continue
                        seen_anchors.add(anchor)
                        if module_id in captured_modules:
                            log(f"display: left duplicate module skipped -> {module_id}")
                            continue
                        captured_modules.add(module_id)
                        ads.append({
                            "id": eid,
                            "module_id": module_id,
                            "type": "Sponsored_Display",
                            "subtype": "Left_Rail_Display",
                            "slot": "left_rail",
                            "brand": brand_txt or "Unknown",
                            "brand_canonical": brand_canon,
                            "advertisers": [brand_canon] if brand_canon else [],
                            "image_path": f"Sponsored_Display/{fname}",
                            "video_path": None,
                            "message": message,
                            "metadata": {},
                        })
                        log(f"display: left saved -> {fpath} module_id={module_id}")
                    except Exception as e:
                        log(f"display: left screenshot fail -> {e}")
            except Exception as e:
                log(f"display: left detect error -> {e}")

            try:
                log("display: detect bottom")
                # Bottom ads: AdHolder that is NOT inside .s-left-ads-item AND NOT a Sponsored Brand themed collection
                # Exclude: left rail, Sponsored Brand themed collections, in-grid sponsored products
                all_adholders = page.locator('div.AdHolder')
                bottom_ads = []
                for i in range(all_adholders.count()):
                    ad = all_adholders.nth(i)
                    # Skip if inside left rail
                    if ad.locator('xpath=ancestor::div[contains(@class,"s-left-ads-item")]').count() > 0:
                        continue
                    # Skip if inside sb-headline
                    if ad.locator('xpath=ancestor::a[@data-elementid="sb-headline"]').count() > 0:
                        continue
                    # Skip if inside Sponsored Brand themed collection (v1 + v2)
                    if ad.locator('xpath=ancestor::div[contains(@cel_widget_id,"sb-themed-collection") or contains(@data-card-metrics-id,"sb-themed-collection")]').count() > 0:
                        continue
                    # Skip if inside SBV
                    if ad.locator('xpath=ancestor::div[contains(@cel_widget_id,"VIDEO_SINGLE_PRODUCT") or contains(@data-cel-widget,"VIDEO_SINGLE_PRODUCT")]').count() > 0:
                        continue
                    # Skip if it's actually an in-grid search result (has data-component-type="s-search-result")
                    if ad.locator('xpath=ancestor::div[@data-component-type="s-search-result"]').count() > 0:
                        continue
                    bottom_ads.append(ad)
                    if len(bottom_ads) >= MAX_BOTTOM_DISPLAY:
                        break
                
                log(f"display: bottom found {len(bottom_ads)} ads (excluded left rail)")
                for i, el in enumerate(bottom_ads):
                    if not el.is_visible():
                        continue
                    # Scroll into view and wait for iframe/image content to load
                    try:
                        el.scroll_into_view_if_needed()
                        time.sleep(0.3)
                    except Exception:
                        pass
                    content_loaded = _wait_for_iframe_content(page, el, timeout_ms=4000)
                    if not content_loaded:
                        log(f"display: bottom ad {i} content may not have loaded")
                    brand_txt, brand_canon, message = _extract_brand_and_message(el)
                    adv_for_name = brand_canon or "unknown"
                    fname = _std_filename("amazon", adv_for_name, "Sponsored_Display", client, keyword, run_id, i, ".png")
                    fpath = os.path.join(output_dir, "Sponsored_Display", fname)
                    try:
                        # Freeze animations (Instacart pattern)
                        try:
                            page.evaluate("""
                                () => {
                                    const style = document.createElement('style');
                                    style.textContent = '* { transition: none !important; animation: none !important; }';
                                    document.head.appendChild(style);
                                }
                            """)
                        except Exception:
                            pass
                        # Flush layout
                        try:
                            page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
                        except Exception:
                            pass
                        # Screenshot the actual ad creative (iframe/img), not the oversized container
                        shot_el = _display_screenshot_target(el)
                        if shot_el is not el:
                            log(f"display: bottom targeting inner creative for ad {i}")
                        shot_el.screenshot(path=fpath, timeout=4000)
                        # Post-screenshot blank detection
                        if _is_blank_screenshot(fpath):
                            log(f"display: bottom BLANK screenshot detected ({os.path.getsize(fpath)} bytes), deleting -> {fname}")
                            try:
                                os.remove(fpath)
                            except OSError:
                                pass
                            continue
                        # OCR fallback: if brand is still unknown, run OCR on the screenshot
                        if (not brand_txt or brand_txt.lower() == "unknown") and os.path.exists(fpath):
                            try:
                                from extractors.ocr_brand_detector import detect_brand_from_image_for_display
                                ocr_brand = detect_brand_from_image_for_display(fpath)
                                if ocr_brand and ocr_brand.lower() != "unknown":
                                    log(f"display: bottom OCR fallback found brand -> {ocr_brand}")
                                    brand_txt = ocr_brand
                                    brand_canon = canonicalize(ocr_brand) or ocr_brand
                                    if not brand_canon or brand_canon.lower() == "unknown":
                                        brand_canon = ocr_brand
                                    adv_for_name = brand_canon
                                    new_fname = _std_filename("amazon", adv_for_name, "Sponsored_Display", client, keyword, run_id, i, ".png")
                                    new_fpath = os.path.join(output_dir, "Sponsored_Display", new_fname)
                                    if new_fpath != fpath:
                                        os.rename(fpath, new_fpath)
                                        fname = new_fname
                                        fpath = new_fpath
                                        log(f"display: bottom renamed screenshot -> {new_fname}")
                            except Exception as e:
                                log(f"display: bottom OCR fallback error -> {e}")
                        anchor = _module_anchor(el)
                        if re.match(r'^(sb|sponsoredb|sponsoredbrands)', (anchor or '').lower()):
                            log(f"display: skip sb-like anchor -> {anchor}")
                            continue
                        module_id, eid = _build_ids("Sponsored_Display", "Bottom_Display", brand_canon, anchor, run_id, i)
                        if anchor in seen_anchors:
                            log(f"display: bottom duplicate anchor skipped -> {anchor}")
                            continue
                        seen_anchors.add(anchor)
                        if module_id in captured_modules:
                            log(f"display: bottom duplicate module skipped -> {module_id}")
                            continue
                        captured_modules.add(module_id)
                        ads.append({
                            "id": eid,
                            "module_id": module_id,
                            "type": "Sponsored_Display",
                            "subtype": "Bottom_Display",
                            "slot": "bottom",
                            "brand": brand_txt or "Unknown",
                            "brand_canonical": brand_canon,
                            "advertisers": [brand_canon] if brand_canon else [],
                            "image_path": f"Sponsored_Display/{fname}",
                            "video_path": None,
                            "message": message,
                            "metadata": {},
                        })
                        log(f"display: bottom saved -> {fpath} module_id={module_id}")
                    except Exception as e:
                        log(f"display: bottom screenshot fail -> {e}")
            except Exception as e:
                log(f"display: bottom detect error -> {e}")

            # 4) Sponsored Products (aggregate + ASIN images)
            try:
                log("sp: aggregate")
                items = page.locator('div[data-component-type=\"s-search-result\"]')
                n = items.count()
                sp_list = []
                page_num = 1
                try:
                    from urllib.parse import urlparse, parse_qs
                    qs = parse_qs(urlparse(page.url).query)
                    if qs.get("page"):
                        page_num = int(qs["page"][0])
                except Exception:
                    pass

                rank = 0
                for i in range(n):
                    item = items.nth(i)
                    is_sp = False
                    try:
                        lab = item.locator(":text('Sponsored')").first
                        if lab.count() > 0 and lab.is_visible():
                            is_sp = True
                    except Exception:
                        pass
                    if not is_sp:
                        continue
                    rank += 1
                    if len(sp_list) >= MAX_SP:
                        break

                    asin = None
                    try:
                        asin = item.get_attribute("data-asin")
                    except Exception:
                        pass

                    title = None
                    try:
                        title = (item.locator('h2 a span').first.text_content() or '').strip()
                    except Exception:
                        pass

                    brand_txt = None
                    for sel in ["span.a-size-base.a-color-secondary", "span.a-size-base-plus.a-color-base.a-text-normal", "h2 a span"]:
                        try:
                            loc = item.locator(sel).first
                            if loc.count() > 0:
                                t = (loc.text_content() or "").strip()
                                if t:
                                    brand_txt = t
                                    break
                        except Exception:
                            pass
                    brand_canon = None
                    try:
                        if brand_txt:
                            brand_canon = canonicalize(brand_txt)
                    except Exception:
                        brand_canon = None

                    img_url = None
                    img_path_rel = None
                    client_mirror_rel = None
                    try:
                        img = item.locator('img.s-image').first
                        if img.count() > 0:
                            src = img.get_attribute('src')
                            if src and src.startswith('http'):
                                img_url = src
                                try:
                                    from urllib.parse import urlparse
                                    ext = os.path.splitext(urlparse(src).path)[1] or ".jpg"
                                except Exception:
                                    ext = ".jpg"
                                file_name = (asin or f"rank_{rank}") + ext
                                central_full = central_asin_dir / file_name
                                try:
                                    # Skip download if already exists
                                    if not central_full.exists():
                                        r = requests.get(src, timeout=10)
                                        if r.ok:
                                            with open(central_full, 'wb') as fimg:
                                                fimg.write(r.content)
                                    # Set path regardless of whether we just downloaded
                                    if central_full.exists():
                                        img_path_rel = str(central_full.relative_to(project_root))
                                        # Central ASIN DB only - no client copying
                                        client_mirror_rel = None
                                        log(f"sp: asin image -> {central_full} (cached={central_full.exists()})")
                                    else:
                                        log(f"sp: asin download failed for {asin}")
                                except Exception as e:
                                    log(f"sp: asin download fail -> {e}")
                    except Exception as e:
                        log(f"sp: image selector fail -> {e}")

                    price_text = None
                    try:
                        price_text = (item.locator('span.a-price .a-offscreen').first.text_content() or '').strip()
                    except Exception:
                        pass
                    rating = None
                    try:
                        rt = (item.locator('span.a-icon-alt').first.text_content() or '').strip()
                        if rt:
                            rating = float(rt.split()[0])
                    except Exception:
                        pass
                    reviews_count = None
                    try:
                        rc = (item.locator('span[aria-label$="ratings"], span[aria-label$="rating"]').first.text_content() or '').strip()
                        if rc:
                            reviews_count = int(''.join([c for c in rc if c.isdigit()]))
                    except Exception:
                        pass
                    prime = False
                    try:
                        prime = item.locator('i.a-icon.a-icon-prime, svg[aria-label="Prime"]').count() > 0
                    except Exception:
                        pass
                    badges = []
                    try:
                        for lab in ["Amazon's Choice", "Best Seller", "Sponsored"]:
                            try:
                                if item.locator(f'[aria-label="{lab}"]').count() > 0:
                                    badges.append(lab)
                            except Exception:
                                pass
                    except Exception:
                        pass
                    product_url = None
                    try:
                        href = item.locator('h2 a').first.get_attribute('href')
                        if href:
                            product_url = href if href.startswith('http') else f"https://www.amazon.com{href}"
                    except Exception:
                        pass

                    sp_list.append({
                        "asin": asin,
                        "rank": rank,
                        "page": page_num,
                        "brand": brand_txt or None,
                        "brand_canonical": brand_canon,
                        "title": title,
                        "image_url": img_url,
                        "image_path": img_path_rel,
                        "client_image_path": client_mirror_rel,
                        "price": price_text,
                        "rating": rating,
                        "reviews_count": reviews_count,
                        "prime": prime,
                        "badges": badges,
                        "product_url": product_url,
                    })

                if sp_list:
                    module_id, eid = _build_ids("Sponsored_Product_List", "List", None, f"page_{page_num}", run_id, 0)
                    ads.append({
                        "id": eid,
                        "module_id": module_id,
                        "type": "Sponsored_Product_List",
                        "subtype": "List",
                        "brand": None,
                        "brand_canonical": None,
                        "advertisers": [],
                        "image_path": None,
                        "video_path": None,
                        "message": "",
                        "metadata": {"page": page_num, "count": len(sp_list), "items": sp_list},
                    })
                    log(f"sp: items collected -> {len(sp_list)}")
                else:
                    log("sp: none found")
            except Exception as e:
                log(f"sp: aggregate error -> {e}")

            success = True
        except Exception as e:
            log(f"fatal: {e}")
            import traceback
            traceback.print_exc()
            # Try to salvage HTML/JSON on error so GUI doesn't see a total failure
            try:
                if 'page' in locals():
                    log("html: save (exception path)")
                    html_content = page.content()
                    with open(html_path, "w", encoding="utf-8") as f:
                        f.write(html_content)
                    log(f"html: saved -> {html_path} exists={os.path.exists(html_path)} size={os.path.getsize(html_path) if os.path.exists(html_path) else 0}")
                # If we captured any ads or at least a main screenshot, consider the run a success
                try:
                    main_dir = os.path.join(output_dir, "Main")
                    any_main = any(name.endswith(".png") and ts in name for name in os.listdir(main_dir)) if os.path.isdir(main_dir) else False
                except Exception:
                    any_main = False
                log(f"salvage: checking success criteria -> ads={len(ads)} any_main={any_main}")
                if ads or any_main:
                    success = True
                    log("salvage: marking as success due to captured assets")
            except Exception as e2:
                log(f"html: save error (exception path) -> {e2}")
        finally:
            # Save tracing only if it was started
            try:
                if tracing_enabled:
                    trace_path = os.path.join(runs_dir, f"trace_{ts}.zip")
                    bctx.tracing.stop(path=trace_path)
                    log(f"trace: saved -> {trace_path} exists={os.path.exists(trace_path)} size={os.path.getsize(trace_path) if os.path.exists(trace_path) else 0}")
                else:
                    log("trace: skipped (not enabled)")
            except Exception as e:
                log(f"trace: stop error -> {e}")
            try:
                if bctx:
                    bctx.close()
            except Exception:
                pass
            try:
                p.stop()
            except Exception:
                pass

    if success:
        log("json: save")
        run_data = {
            "retailer": "amazon",
            "client": client,
            "keyword": keyword,
            "search_url": _search_url(keyword),
            "html": os.path.basename(html_path),
            "ads": ads,
            "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "run_id": run_id,
        }
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(run_data, f, indent=2, ensure_ascii=False)
            log(f"json: saved -> {json_path} exists={os.path.exists(json_path)} size={os.path.getsize(json_path) if os.path.exists(json_path) else 0}")
        except Exception as e:
            log(f"json: save error -> {e}")

    return success


if __name__ == "__main__":
    import sys
    keyword = sys.argv[1] if len(sys.argv) > 1 else "bandaid"
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "output/amazon/bandaidtest"

    success = search_and_capture(keyword, output_dir)
    if success:
        print("\n✅ AMAZON SEARCH AND CAPTURE COMPLETED SUCCESSFULLY")
    else:
        print("\n❌ AMAZON SEARCH AND CAPTURE FAILED")
        sys.exit(1)
