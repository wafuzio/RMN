# archived/walmart_ad_core.py
from __future__ import annotations
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from dataclasses import dataclass
from typing import Dict, Any, List

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

def _attrs(el, names):
    out = {}
    for n in names:
        try:
            v = el.get(n) or ""
            if v:
                out[n] = v
        except Exception:
            pass
    return out

def _first_img_src(el):
    try:
        img = el.select_one("img")
        if img and img.get("src"):
            return img["src"]
    except Exception:
        pass
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
    # Keep as-is; your scraper's rd= resolver happens earlier if you prefer.
    return href or ""

def _extract_block(soup, selector, ad_type) -> List[Dict[str, Any]]:
    items = []
    for el in soup.select(selector):
        d: Dict[str, Any] = {"type": ad_type}
        d["text"] = _text(el)
        d["img"]  = _first_img_src(el)
        href = _first_link(el)
        d["href"] = _normalize_url(href) if href else None
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
