# archived/walmart_ad_core.py
from __future__ import annotations
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, unquote
from typing import Dict, Any, List
import json
import os
from difflib import get_close_matches

# Walmart ad module selectors (align with your scraper)
SEL_TOP_BANNER = "a.ad, a.adctr"
SEL_SBA        = '[data-testid="sba-container"]'
SEL_TILE       = '[data-testid="tile-take-over"]'
SEL_SBV        = '[data-testid="search-video-in-grid"]'

def _text(el):
    try:
        return " ".join(el.get_text(" ", strip=True).split())
    except Exception:
        return ""

def _first_img_src(el):
    # Try common lazy-image attributes in priority order
    try:
        img = el.select_one("img")
        if not img:
            return None
        for attr in ("src", "data-src", "data-original", "data-lazy", "data-srcset", "srcset"):
            v = img.get(attr)
            if not v:
                continue
            # srcset may have multiple URLs; take the first
            if attr.endswith("srcset"):
                first = v.split(",")[0].strip().split(" ")[0]
                if first:
                    return first
            else:
                return v
    except Exception:
        pass
    return None

def _first_video_src(el):
    # Look for <video> or <source> inside SBV module
    try:
        src = None
        s = el.select_one("video source[src]") or el.select_one("source[src]")
        if s and s.get("src"):
            src = s["src"]
        if not src:
            v = el.select_one("video")
            if v and v.get("src"):
                src = v["src"]
        return src
    except Exception:
        return None

def _first_link(el):
    try:
        a = el.select_one("a[href]")
        if a and a.get("href"):
            return a["href"]
    except Exception:
        pass
    return None

def _normalize_url(href: str) -> str:
    """
    Walmart redirectors:
      - https://www.walmart.com/sp/track?...&rd=
      - https://www.walmart.com/dad/trk/... (encrypted)
    Prefer rd= when present; otherwise return the original href.
    """
    try:
        u = urlparse(href or "")
        qs = parse_qs(u.query)
        if "rd" in qs and qs["rd"]:
            return unquote(qs["rd"][0])
    except Exception:
        pass
    return href or ""

def _extract_advertiser(el):
    """Extract advertiser/brand name from ad element."""
    try:
        import re
        from urllib.parse import unquote
        
        # Method 1: Try to find "Sponsored by [Brand]" text (works for SBA)
        text = _text(el)
        match = re.search(r'Sponsored by\s+(.+?)(?:\s+Shop now|\s+Add\s|\s+\$)', text, re.IGNORECASE)
        if match:
            advertiser = match.group(1).strip()
            return advertiser
        
        # Method 2: Extract from product URL for SBV (e.g., /ip/Claussen-Pickles-...)
        href = _first_link(el)
        if href:
            # First decode the rd= parameter if present (Walmart tracking URL)
            rd_match = re.search(r'rd=([^&]+)', href)
            if rd_match:
                href = unquote(rd_match.group(1))
            
            # Extract brand from /ip/{Brand}-{Product}/ID pattern
            ip_match = re.search(r'/ip/([^-/]+)', href)
            if ip_match:
                brand = ip_match.group(1).replace('-', ' ')
                return brand.strip()
            
            # Method 3: Fallback to facet parameter
            brand_match = re.search(r'facet[^&]*brand[^&]*[:%]([^&%]+)', href, re.IGNORECASE)
            if brand_match:
                advertiser = brand_match.group(1).replace('%20', ' ').replace('+', ' ')
                return advertiser.strip()
    except Exception:
        pass
    return None

def _extract_block(soup, selector, ad_type) -> List[Dict[str, Any]]:
    items = []
    for idx, el in enumerate(soup.select(selector), start=1):
        d: Dict[str, Any] = {"type": ad_type, "pos": idx}
        d["text"] = _text(el)
        d["img"]  = _first_img_src(el)

        href = _first_link(el)
        d["href"] = _normalize_url(href) if href else None

        if ad_type == "sbv":
            d["video"] = _first_video_src(el)
        
        # Extract advertiser
        advertiser = _extract_advertiser(el)
        
        # For tile_takeover, if no brand advertiser found, it's Walmart promotional content
        if ad_type == "tile_takeover" and not advertiser:
            # Check if it's a Walmart promo (category/browse pages) vs brand ad
            text = _text(el)
            href_check = href or ""
            
            # If has "Sponsored" text or ad tracking, try harder to find brand
            has_sponsored = "Sponsored" in text
            has_ad_tracking = any(x in href_check for x in ['adsRedirect=true', 'adUid=', 'adcampaignid='])
            
            if has_sponsored or has_ad_tracking:
                # This is likely a brand ad, but we couldn't extract the brand
                # Leave advertiser as None so it can be investigated
                pass
            else:
                # No sponsored indicators - this is Walmart promotional content
                d["advertiser"] = "Walmart"
                d["advertisers"] = ["Walmart"]
        elif advertiser:
            d["advertiser"] = advertiser
            # Also set advertisers array for consistency with Kroger format
            d["advertisers"] = [advertiser]

        items.append(d)
    return items

def extract_ads_from_html(html: str, keyword: str, timestamp: str, source_file: str) -> Dict[str, Any]:
    """
    Mirror Kroger's core API:
    Return a single `result`  dict: {keyword, search_term, count, ads, source_file, timestamp}
    """
    soup = BeautifulSoup(html or "", "html.parser")

    ads: List[Dict[str, Any]] = []
    ads += _extract_block(soup, SEL_TOP_BANNER, "top_banner")
    ads += _extract_block(soup, SEL_SBA,        "sba")
    ads += _extract_block(soup, SEL_TILE,       "tile_takeover")
    ads += _extract_block(soup, SEL_SBV,        "sbv")

    result = {
        "keyword": keyword,
        "search_term": keyword,
        "count": len(ads),
        "ads": ads,
        "source_file": source_file,
        "timestamp": timestamp,
    }
    return result
