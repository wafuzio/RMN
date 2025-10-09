# archived/walmart_ad_core.py
from __future__ import annotations
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, unquote
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
