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
from time import sleep as _sleep
from playwright.sync_api import sync_playwright
from browser_lock import single_browser_lock
import requests
import shutil
import hashlib
import re
import time
from core.brands import canonicalize
from difflib import get_close_matches
from urllib.parse import urlparse, parse_qs, unquote

def force_window_and_metrics(context, page, width=1920, height=1080, dpr=1, log=print):
    """Force outer window size, device metrics, page scale, and verify DPR/viewport via CDP."""
    try:
        client = context.new_cdp_session(page)
        log("CDP: session opened")
    except Exception as e:
        log(f"CDP: failed to open session: {e}")
        return

    # 1) Outer window bounds
    try:
        win = client.send('Browser.getWindowForTarget')
        client.send('Browser.setWindowBounds', {
            'windowId': win['windowId'],
            'bounds': {'width': width, 'height': height}
        })
        log(f"CDP: window bounds {width}x{height}")
    except Exception as e:
        log(f"CDP: setWindowBounds failed: {e}")

    # 2) Device metrics (locks CSS pixels and DPR)
    try:
        client.send('Emulation.setDeviceMetricsOverride', {
            'width': width, 'height': height, 'deviceScaleFactor': dpr, 'mobile': False, 'scale': 1
        })
        log(f"CDP: metrics override {width}x{height} DPR={dpr}")
    except Exception as e:
        log(f"CDP: setDeviceMetricsOverride failed: {e}")

    # 3) Clear any persisted zoom
    try:
        client.send('Emulation.setPageScaleFactor', {'pageScaleFactor': 1})
    except Exception:
        pass

    # 4) Verify
    try:
        cur_dpr = page.evaluate('window.devicePixelRatio')
        vp = page.evaluate('() => ({ w: window.innerWidth, h: window.innerHeight })')
        log(f"CDP: verified viewport {vp['w']}x{vp['h']} DPR={cur_dpr}")
    except Exception as e:
        log(f"CDP: verify failed: {e}")


def freeze_layout_and_hide_sticky(page):
    """Eliminate animation/scroll effects and hide sticky UI by visibility (no reflow)."""
    try:
        page.add_style_tag(content="""
            html { scroll-behavior: auto !important; }
            * { transition: none !important; animation: none !important; }
            #navbar,#nav-belt,#nav-main,#nav-progressive-subnav,header,[data-testid="header"],
            [class*="sticky" i],[data-sticky],[style*="position: sticky"] { visibility: hidden !important; }
        """)
    except Exception:
        pass
    try:
        page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
    except Exception:
        pass


def screenshot_element_beyond_viewport(context, page, handle, out_path, pad=8, log=print):
    """Use CDP Page.captureScreenshot with a precise clip in page coordinates."""
    # Compute clip in page coords from DOMRect + scroll
    rect = page.evaluate(
        """([el, pad]) => {
            const r = el.getBoundingClientRect();
            const sx = window.scrollX||window.pageXOffset||0;
            const sy = window.scrollY||window.pageYOffset||0;
            const x  = Math.max(0, Math.floor(r.left + sx - pad));
            const y  = Math.max(0, Math.floor(r.top  + sy - pad));
            const w  = Math.ceil(r.width  + 2*pad);
            const h  = Math.ceil(r.height + 2*pad);
            return {x,y,width:w,height:h};
        }""",
        [handle, pad]
    )
    if not rect:
        raise RuntimeError("No rect for element")

    client = context.new_cdp_session(page)
    shot = client.send('Page.captureScreenshot', {
        'format': 'png',
        'fromSurface': True,
        'captureBeyondViewport': True,
        'clip': {'x': rect['x'], 'y': rect['y'], 'width': rect['width'], 'height': rect['height'], 'scale': 1.0},
    })

    import base64, os
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'wb') as f:
        f.write(base64.b64decode(shot['data']))
    return out_path

# Feature flag: 0 = locator.screenshot() (precise), 1 = CDP clip (advanced)
USE_CDP_ELEMENT_SHOTS = os.environ.get("AMAZON_USE_CDP_ELEMENT_SHOTS", "0") == "1"

def wait_for_bottom_height_to_stabilize(page, max_loops=18, settle_ms=300, log=print):
    """Scroll to bottom repeatedly until document height stops growing twice."""
    last_h = 0
    stable = 0
    for i in range(max_loops):
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        except Exception:
            pass
        _sleep(settle_ms / 1000.0)
        try:
            h = page.evaluate("() => Math.max(document.documentElement.scrollHeight, document.body.scrollHeight, 0)")
        except Exception:
            h = last_h
        if h == last_h:
            stable += 1
            if stable >= 2:
                break
        else:
            stable = 0
            last_h = h
    try:
        log(f"bottom height stabilized at {last_h}px after {i+1} passes")
    except Exception:
        pass

def freeze_layout_and_hide_sticky(page):
    """Hide sticky UI without reflow and stop animations to avoid blurs."""
    try:
        page.add_style_tag(content="""
            html { scroll-behavior: auto !important; }
            * { transition: none !important; animation: none !important; }
            #navbar,#nav-belt,#nav-main,#nav-progressive-subnav,header,[data-testid="header"],
            [class*="sticky" i],[data-sticky],[style*="position: sticky"] { visibility: hidden !important; }
        """)
    except Exception:
        pass
    try:
        page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
    except Exception:
        pass

# Track unique containers across detection strategies
seen_signatures = set()

def container_signature(loc):
    """A stable identity for SB containers across v1/v2 wrappers."""
    try:
        # Prefer v2 metrics and the CardInstance id; then v1 cel-widget and other IDs
        return (
            _get_attr(loc, "data-card-metrics-id") or
            _get_attr(loc, "id") or
            _get_attr(loc, "cel_widget_id") or
            _get_attr(loc, "data-uuid") or
            _get_attr(loc, "data-aid") or
            _get_attr(loc, "data-cel-widget")
        ) or None
    except Exception:
        return None

def capture_module(locator, out_path, context, page, log):
    """
    Default: exact DOM-bounded screenshot via locator.screenshot().
    Optional: CDP clip if AMAZON_USE_CDP_ELEMENT_SHOTS=1 (kept for experiments).
    """
    try:
        locator.scroll_into_view_if_needed()
    except Exception:
        pass
    # Freeze before measuring/shot
    freeze_layout_and_hide_sticky(page)

    if not USE_CDP_ELEMENT_SHOTS:
        # Exact to the element bounding box
        locator.screenshot(path=out_path, timeout=4000)
        return

    # CDP path (only if you explicitly enable it)
    try:
        handle = locator.element_handle(timeout=750)
    except Exception:
        handle = None
    if not handle:
        locator.screenshot(path=out_path, timeout=4000)
        return

    # Compute clip in page coords
    rect = page.evaluate(
        """([el, pad]) => {
            const r = el.getBoundingClientRect();
            const sx = window.scrollX||window.pageXOffset||0;
            const sy = window.scrollY||window.pageYOffset||0;
            const x  = Math.max(0, Math.floor(r.left + sx - pad));
            const y  = Math.max(0, Math.floor(r.top  + sy - pad));
            const w  = Math.ceil(r.width  + 2*pad);
            const h  = Math.ceil(r.height + 2*pad);
            return {x,y,width:w,height:h};
        }""",
        [handle, 6]
    )
    if not rect:
        locator.screenshot(path=out_path, timeout=4000)
        return

    try:
        client = context.new_cdp_session(page)
        shot = client.send('Page.captureScreenshot', {
            'format': 'png',
            'fromSurface': True,
            'captureBeyondViewport': True,
            'clip': {'x': rect['x'], 'y': rect['y'], 'width': rect['width'], 'height': rect['height'], 'scale': 1.0},
        })
        import base64, os
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, 'wb') as f:
            f.write(base64.b64decode(shot['data']))
    except Exception as e:
        log(f"CDP element capture failed, fallback to locator.screenshot(): {e}")
        locator.screenshot(path=out_path, timeout=4000)

def full_page_screenshot_cdp(context, page, out_path, log=print):
    """
    Capture the entire document with CDP using Page.getLayoutMetrics and Page.captureScreenshot.
    This is more reliable than full_page=True on pages with lazy/hydrated bottoms.
    """
    try:
        client = context.new_cdp_session(page)
    except Exception as e:
        log(f"CDP: session open failed: {e}")
        # fall back to Playwright full page if CDP unavailable
        page.screenshot(path=out_path, full_page=True)
        return out_path

    # Ensure the document is fully measured (call our stabilizer beforehand)
    # Compute content size in CSS pixels
    try:
        metrics = client.send('Page.getLayoutMetrics')
        css_size = metrics.get('cssContentSize') or metrics.get('contentSize')
        width = int(css_size['width'])
        height = int(css_size['height'])
    except Exception as e:
        log(f"CDP: getLayoutMetrics failed: {e}")
        page.screenshot(path=out_path, full_page=True)
        return out_path

    # Chrome has practical limits; clamp if truly huge
    MAX_DIM = 16384
    width = min(width, MAX_DIM)
    height = min(height, MAX_DIM)

    # Freeze motion and hide sticky (visibility only)
    try:
        page.add_style_tag(content="""
          html { scroll-behavior: auto !important; }
          * { transition: none !important; animation: none !important; }
          #navbar,#nav-belt,#nav-main,#nav-progressive-subnav,header,[data-testid="header"],
          [class*="sticky" i],[data-sticky],[style*="position: sticky"] { visibility: hidden !important; }
        """)
        page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
    except Exception:
        pass

    try:
        shot = client.send('Page.captureScreenshot', {
            'format': 'png',
            'fromSurface': True,
            'captureBeyondViewport': True,
            'clip': {'x': 0, 'y': 0, 'width': width, 'height': height, 'scale': 1.0},
        })
        import base64, os
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, 'wb') as f:
            f.write(base64.b64decode(shot['data']))
        log(f"main(full): captured {width}x{height}")
        return out_path
    except Exception as e:
        log(f"CDP: captureScreenshot failed: {e}")
        page.screenshot(path=out_path, full_page=True)
        return out_path

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
    "Shoppers also explored",
    "Trending now",
    "Popular products in this category",
    "Customers who viewed this item also viewed",
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

"""Brand lexicon + token helpers for Amazon brand extraction."""

# Load brand lexicon from JSON (Kroger-style). Falls back to empty if missing.
try:
    lex_path = os.environ.get("BRAND_LEXICON_JSON", "config/brands.json")
    data = json.load(open(lex_path, "r", encoding="utf-8"))
    # Expect structure: { "Ben & Jerry's": {"synonyms": ["B&J", "Ben and Jerrys", ...]}, ... }
    _SYNONYM_TO_CANON = {}
    for canon, entry in data.items():
        _SYNONYM_TO_CANON[canon.lower()] = canon
        for s in entry.get("synonyms", []):
            _SYNONYM_TO_CANON[str(s).lower()] = canon
    _CANON_CHOICES = list(_SYNONYM_TO_CANON.keys())
except Exception:
    _SYNONYM_TO_CANON = {}
    _CANON_CHOICES = []

# Fuzzy cutoff can be tuned via BRAND_FUZZY_CUTOFF, default 0.86 (Kroger-style)
try:
    BRAND_FUZZY_CUTOFF = float(os.environ.get("BRAND_FUZZY_CUTOFF", "0.86"))
except Exception:
    BRAND_FUZZY_CUTOFF = 0.86

GENERIC_ALT_WORDS = {"logo", "brand", "image", "product image", "advertisement", "ad", "banner"}

DESCRIPTIVE_WORDS = {
    "fresh","cut","pure","premium","original","classic","natural","organic","whole","sliced",
    "diced","chopped","ultra","extra","plus","advanced","gentle","daily","hydrating","repair",
    "treatment","system","mask","wash","cream","gel","serum","lotion","patches","kit","set",
}

STOP_WORDS = {"the","a","an","by","with","and","or","for","of","on","to"}


def _slug_tokens(text: str) -> list[str]:
    if not text:
        return []
    t = re.sub(r"[^A-Za-z0-9&'’\- ]+", " ", text)
    t = re.sub(r"\s+", " ", t).strip()
    return t.split()


def _split_camel_pascal(s: str) -> list[str]:
    if not s:
        return []
    out, cur = [], s[0]
    for c in s[1:]:
        if c.isupper() and (not cur[-1].isupper()):
            out.append(cur)
            cur = c
        else:
            cur += c
    out.append(cur)
    return out


def _n_grams(tokens: list[str], n: int) -> list[str]:
    return [" ".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1)] if n > 0 else []


def _brand_from_token(token: str, cutoff: float = None) -> str | None:
    """Resolve a token/phrase to a canonical brand using lexicon + fuzzy matching.

    Strict behavior: returns None unless lexicon/canonicalizer agrees the token is a known brand.
    """
    if not token:
        return None
    tok = token.strip().lower()
    if tok in _SYNONYM_TO_CANON:
        return _SYNONYM_TO_CANON[tok]
    try:
        # Prefer retailer-aware canonicalizer if supported
        try:
            c = canonicalize(token, retailer="amazon")  # type: ignore[call-arg]
        except TypeError:
            c = canonicalize(token)
        if c:
            return c
    except Exception:
        pass
    if _CANON_CHOICES:
        eff_cutoff = BRAND_FUZZY_CUTOFF if cutoff is None else cutoff
        match = get_close_matches(tok, _CANON_CHOICES, n=1, cutoff=eff_cutoff)
        if match:
            return _SYNONYM_TO_CANON.get(match[0])
    return None


def _best_brand_from_tokens(tokens: list[str]) -> str | None:
    if not tokens:
        return None
    toks = [t for t in tokens if t.lower() not in STOP_WORDS]
    for n in (3, 2, 1):
        for ng in _n_grams(toks, n):
            first = ng.split()[0].lower()
            if first in DESCRIPTIVE_WORDS:
                continue
            b = _brand_from_token(ng)
            if b:
                return b
    return None


def _brand_from_url(href: str) -> str | None:
    """Kroger-style URL extraction for /brand/ or /brands/ slugs."""
    if not href:
        return None
    try:
        u = urlparse(href)
        path = u.path or ""
        m = re.search(r"/brands/([^/?#]+)", path, re.IGNORECASE)
        if m:
            slug = unquote(m.group(1)).replace("-", " ").strip()
            return _brand_from_token(slug)
        m = re.search(r"/brand/([^/?#]+)", path, re.IGNORECASE)
        if m:
            slug = unquote(m.group(1)).replace("-", " ").strip()
            return _brand_from_token(slug)
    except Exception:
        pass
    return None


def _clean_logo_alt(alt: str) -> str | None:
    if not alt:
        return None
    low = alt.lower()
    for w in GENERIC_ALT_WORDS:
        low = low.replace(w, "")
    cleaned = re.sub(r"\s+", " ", low).strip()
    if not cleaned:
        return None
    words = cleaned.split()
    if len(words) > 3:
        return None
    return " ".join([w.capitalize() if w.islower() else w for w in words]) or None


def _brand_from_shop_text(s: str) -> str | None:
    m = re.search(r"\b(?:Save on|Shop|Buy|Get|Try)\s+([A-Z][A-Za-z0-9&'’\-]+(?:\s+[A-Z][A-Za-z0-9&'’\-]+){0,2})", s or "")
    if m:
        return _brand_from_token(m.group(1).strip())
    return None


def _brand_from_from_text(s: str) -> str | None:
    m = re.search(r"\bfrom\s+([A-Z][A-Za-z0-9&'’\-]+(?:\s+[A-Z][A-Za-z0-9&'’\-]+){0,2})", s or "", re.IGNORECASE)
    if m:
        return _brand_from_token(m.group(1).strip())
    return None


def _brand_from_title_like(s: str) -> str | None:
    if not s:
        return None
    s = re.sub(r"^Sponsored\s+Ad\.?\s*", "", s, flags=re.IGNORECASE).strip()
    seg = re.split(r"\s[-–—]\s|®|™", s, maxsplit=1)[0].strip()
    tokens = _slug_tokens(seg)
    for n in (2, 1):
        for ng in _n_grams(tokens, n):
            b = _brand_from_token(ng)
            if b:
                return b
    return None


def _extract_brand_amz(container, keyword: str = "", ad_type: str = "", prefer_url: bool = True):
    """Amazon brand extractor combining lexicon validation and multiple heuristics."""
    brand = None
    message = None

    hrefs: list[str] = []
    try:
        for a in container.locator("a[href]").all():
            try:
                h = a.get_attribute("href")
                if h:
                    hrefs.append(h)
            except Exception:
                pass
    except Exception:
        pass

    if prefer_url and hrefs:
        for h in hrefs:
            b = _brand_from_url(h)
            if b:
                brand = b
                break

    try:
        al = container.locator("a[aria-label]").first
        if al.count() > 0:
            label = (al.get_attribute("aria-label") or "").strip()
            if label:
                message = message or label
                brand = brand or _brand_from_from_text(label) or _brand_from_shop_text(label)
    except Exception:
        pass

    try:
        head = container.locator('a[data-elementid="sb-headline"], h2').first
        if head.count() > 0:
            ht = (head.text_content() or "").strip()
            if ht:
                message = message or ht
                brand = brand or _brand_from_shop_text(ht) or _brand_from_from_text(ht)
    except Exception:
        pass

    if not brand:
        try:
            logo = container.locator("img[alt]").first
            if logo.count() > 0:
                alt = (logo.get_attribute("alt") or "").strip()
                cleaned = _clean_logo_alt(alt)
                if cleaned:
                    cand = _brand_from_token(cleaned)
                    if cand:
                        brand = cand
        except Exception:
            pass

    if not brand:
        try:
            cards = container.locator("div[data-asin]")
            if cards.count() > 0:
                title = (cards.nth(0).locator("h2 a span").first.text_content() or "").strip()
                if title:
                    tokens = _slug_tokens(title)
                    brand = _best_brand_from_tokens(tokens)
        except Exception:
            pass

    if not brand:
        try:
            long_lab = None
            for n in container.locator("[aria-label]").all():
                lab = (n.get_attribute("aria-label") or "").strip()
                if lab and len(lab) > 24 and "sponsored" not in lab.lower():
                    long_lab = lab
                    break
            if long_lab:
                b = _brand_from_title_like(long_lab)
                if b:
                    brand = b
                if not message:
                    message = long_lab
        except Exception:
            pass

    if not brand and keyword:
        tokens = _slug_tokens(keyword) + _split_camel_pascal(keyword)
        brand = _best_brand_from_tokens(tokens)

    brand_canon = None
    try:
        if brand:
            brand_canon = canonicalize(brand)
    except Exception:
        pass

    return (brand or None), brand_canon, (message or "")


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


def search_and_capture(keyword: str, output_dir: str) -> bool:
    print("\n==================================================")
    print("AMAZON SEARCH AND CAPTURE")
    print("==================================================")
    print(f"Keyword: {keyword}")
    print(f"Output directory: {output_dir}")

    profile_dir = os.environ.get("AMAZON_PROFILE_DIR") or os.path.expanduser("~/ChromeProfiles/amazon")
    try:
        os.makedirs(profile_dir, exist_ok=True)
    except Exception as e:
        print(f"❌ Could not prepare profile dir {profile_dir}: {e}")
        return False
    print(f"Using profile: {profile_dir}")

    client = os.path.basename(output_dir.rstrip('/')) or "unknown"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = datetime.now().strftime("%Y%m%d%H%M%S")
    runs_dir = os.path.join(output_dir, "runs")
    os.makedirs(runs_dir, exist_ok=True)

    html_path = os.path.join(runs_dir, f"search_results_amazon_{client}_{ts}.html")
    json_path = os.path.join(runs_dir, f"run_results_amazon_{client}_{ts}.json")
    debug_log = os.path.join(runs_dir, f"capture_debug_{ts}.log")
    project_root = Path(__file__).resolve().parent
    # Use a stable assets/amazon/ASIN_Images folder under the project root; avoid calling log() before it's defined
    env_asin_dir = os.environ.get("AMAZON_ASIN_DB_DIR")
    central_asin_dir = Path(env_asin_dir) if env_asin_dir else project_root / "assets" / "amazon" / "ASIN_Images"
    try:
        central_asin_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        # log() is not defined yet; use print to avoid early NameError
        print(f"central_asin_dir mkdir error -> {e}")

    # Global session for ASIN image downloads with keep-alive and retries
    session = requests.Session()
    try:
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        retries = Retry(total=2, backoff_factor=0.2, status_forcelist=[429, 500, 502, 503, 504])
        session.mount("https://", HTTPAdapter(max_retries=retries))
    except Exception:
        pass

    DOWNLOAD_ASIN_IMAGES = os.environ.get("AMAZON_DOWNLOAD_ASIN_IMAGES", "1") == "1"
    ASIN_FETCH_TIMEOUT = (2, 8)  # (connect, read) seconds

    def log(msg: str):
        timestamp = datetime.now().isoformat()
        print(f"[{timestamp}] {msg}")
        try:
            with open(debug_log, 'a', encoding='utf-8') as f:
                f.write(f"{timestamp} {msg}\n")
        except Exception:
            pass

    def progressive_scroll(page, steps=30, step_px=900, pause_ms=300):
        """Incrementally scrolls the page to trigger lazy rendering. No Playwright waits inside."""
        try:
            try:
                page.keyboard.press("Home")
            except Exception:
                pass
            _sleep(0.3)
            for _ in range(steps):
                try:
                    page.mouse.wheel(0, step_px)
                except Exception:
                    pass
                _sleep(pause_ms / 1000.0)
            try:
                page.keyboard.press("End")
            except Exception:
                pass
            _sleep(0.8)
        except Exception as e:
            log(f"scroll: error -> {e}")

    log("bootstrap: start")
    log("debug: enabled - all steps will be logged with timestamps")

    ads = []
    captured_modules = set()
    seen_anchors = set()
    success = False

    # Performance controls and time budget
    BUDGET_SEC = int(os.environ.get("AMAZON_BUDGET_SEC", "120"))
    MAX_SP = int(os.environ.get("AMAZON_MAX_SP", "12"))
    MAX_CAR = int(os.environ.get("AMAZON_MAX_CAR", "1"))
    MAX_LEFT_DISPLAY = int(os.environ.get("AMAZON_MAX_LEFT_DISPLAY", "2"))
    MAX_BOTTOM_DISPLAY = int(os.environ.get("AMAZON_MAX_BOTTOM_DISPLAY", "2"))
    deadline = time.time() + BUDGET_SEC
    def time_left():
        try:
            return max(0, deadline - time.time())
        except Exception:
            return 0

    occupied_regions = []  # list of (x,y,w,h)

    def bbox(locator):
        try:
            h = locator.element_handle(timeout=500)
            if not h:
                return None
            b = h.bounding_box()
            if not b:
                return None
            return (b["x"], b["y"], b["width"], b["height"])
        except Exception:
            return None

    def overlaps(a, b, frac_threshold=0.35):
        if not a or not b:
            return False
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        x1 = max(ax, bx); y1 = max(ay, by)
        x2 = min(ax+aw, bx+bw); y2 = min(ay+ah, by+bh)
        if x2 <= x1 or y2 <= y1:
            return False
        inter = (x2-x1)*(y2-y1)
        area_a = aw*ah; area_b = bw*bh
        # If overlap is large vs the smaller region, treat as duplicate
        return inter / max(1.0, min(area_a, area_b)) >= frac_threshold

    def safe_text(loc, timeout=0):
        try:
            t = loc.first.text_content(timeout=timeout)
            return (t or "").strip()
        except Exception:
            return ""

    def safe_attr(loc, name, timeout=0):
        try:
            return loc.first.get_attribute(name, timeout=timeout)
        except Exception:
            return None

    def present(loc, timeout=0):
        try:
            return bool(loc.first.element_handle(timeout=timeout))
        except Exception:
            return False

    with single_browser_lock(timeout=600):
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
                    ],
                )
            page = bctx.new_page()
            force_window_and_metrics(bctx, page, width=1920, height=1080, dpr=1, log=log)

            # Wire minimal browser events (avoid noisy response logs)
            try:
                # Playwright console messages expose .type and .text as attributes, not callables
                page.on("console", lambda m: log(f"[console:{m.type}] {m.text}"))
                page.on("pageerror", lambda e: log(f"[pageerror] {e}"))
                page.on("requestfailed", lambda r: log(f"[requestfailed] {r.method()} {r.url}"))
            except Exception:
                pass

            # Start tracing only if enabled
            try:
                if os.environ.get("AMAZON_TRACE") == "1":
                    bctx.tracing.start(screenshots=True, snapshots=True, sources=False)
            except Exception:
                pass

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

            # 1) Main full-page screenshot (hide sticky headers, AFTER scroll, short left-rail probe)
            try:
                log("main: prepare (hide sticky headers, scroll top)")
                try:
                    page.add_style_tag(content="""
                      html { scroll-behavior: auto !important; }
                      * { transition: none !important; animation: none !important; }
                      #navbar,#nav-belt,#nav-main,#nav-progressive-subnav,header,[data-testid="header"],
                      [class*="sticky" i],[data-sticky],[style*="position: sticky"] { visibility: hidden !important; }
                    """)
                except Exception as css_err:
                    log(f"main: style inject error -> {css_err}")

                # give the left rail a brief chance to render (non-fatal)
                try:
                    if page.locator('div.s-left-ads-item img').count() > 0:
                        page.locator('div.s-left-ads-item img').first.wait_for(state='visible', timeout=2000)
                except Exception:
                    pass

                # Hydrate the whole page
                progressive_scroll(page)
                wait_for_bottom_height_to_stabilize(page, max_loops=18, settle_ms=300, log=log)

                # Now capture full page via CDP (don't rely on full_page=True)
                log("main: screenshot (CDP full document)")
                main_name = _std_filename("amazon", "unknown", "Main", client, keyword, run_id, 0, ".png")
                main_path = os.path.join(output_dir, "Main", main_name)
                full_page_screenshot_cdp(bctx, page, main_path, log=log)
                log(f"main: saved -> {main_path} exists={os.path.exists(main_path)} size={os.path.getsize(main_path) if os.path.exists(main_path) else 0}")
            except Exception as e:
                log(f"main: fail -> {e}")

            # Create output folders
            for folder in [
                "Sponsored_Brand_Video",
                "Sponsored_Brand",
                "Sponsored_Carousel",
                "Sponsored_Display",
            ]:
                os.makedirs(os.path.join(output_dir, folder), exist_ok=True)

            # 2) Sponsored Brand Video (SBV)
            try:
                log("sbv: detect")
                # Try both cel_widget_id and data-cel-widget variants
                sbv_loc = page.locator("div[cel_widget_id*='VIDEO_SINGLE_PRODUCT'], div[data-cel-widget*='VIDEO_SINGLE_PRODUCT']")
                sbv_el = sbv_loc.element_handle(timeout=1000)
                if sbv_el:
                    sbv_root = sbv_loc.first
                    # Brand/message using lexicon-aware extractor
                    brand_txt, brand_canon, message = _extract_brand_amz(sbv_root, keyword=keyword, ad_type="Sponsored_Brand_Video")
                    adv_for_name = brand_canon or "unknown"
                    fname = _std_filename("amazon", adv_for_name, "Sponsored_Brand_Video", client, keyword, run_id, 0, ".png")
                    fpath = os.path.join(output_dir, "Sponsored_Brand_Video", fname)

                    # Freeze animations + flush layout
                    try:
                        page.evaluate("() => { const st=document.createElement('style'); st.textContent='*{transition:none!important;animation:none!important}'; document.head.appendChild(st); }")
                    except Exception:
                        pass
                    capture_module(sbv_root, fpath, bctx, page, log)
                    # Possible MP4 capture (unchanged)
                    video_rel = None
                    try:
                        sources = []
                        try:
                            sources += [s.get_attribute('src') for s in sbv_root.locator('video source').element_handles()]
                        except Exception:
                            pass
                        try:
                            v = sbv_root.locator('video').first
                            s = v.get_attribute('src')
                            if s:
                                sources.append(s)
                        except Exception:
                            pass
                        try:
                            dv = sbv_root.get_attribute('data-video-url')
                            if dv:
                                sources.append(dv)
                        except Exception:
                            pass
                        sources = [u for u in (sources or []) if u]
                        mp4 = next((u for u in sources if '.mp4' in u.lower()), None)
                        if mp4:
                            mp4_name = os.path.splitext(fname)[0] + ".mp4"
                            mp4_path = os.path.join(output_dir, "Sponsored_Brand_Video", mp4_name)
                            r = session.get(mp4, timeout=ASIN_FETCH_TIMEOUT, stream=True)
                            if r.ok:
                                with open(mp4_path, "wb") as vf:
                                    shutil.copyfileobj(r.raw, vf)
                            video_rel = f"Sponsored_Brand_Video/{mp4_name}"
                    except Exception as e:
                        log(f"sbv: mp4 error -> {e}")

                    anchor = _module_anchor(sbv_root)
                    if anchor not in seen_anchors:
                        seen_anchors.add(anchor)
                        module_id, eid = _build_ids("Sponsored_Brand_Video", "Video_Single_Product", brand_canon, anchor, run_id, 0)
                        ads.append({
                            "id": eid,
                            "module_id": module_id,
                            "type": "Sponsored_Brand_Video",
                            "subtype": "Video_Single_Product",
                            "brand": brand_txt or "Unknown",
                            "brand_canonical": brand_canon,
                            "advertisers": [brand_canon] if brand_canon else [],
                            "image_path": f"Sponsored_Brand_Video/{fname}",
                            "video_path": video_rel,
                            "message": message,
                            "metadata": {},
                        })
                        log(f"sbv: saved -> {fpath} module_id={module_id}")
                        # Track bbox to prevent display overlap
                        try:
                            r = bbox(sbv_root)
                            if r:
                                occupied_regions.append(r)
                        except Exception:
                            pass
                    else:
                        log(f"sbv: duplicate anchor skipped")
                else:
                    log("sbv: none")
            except Exception as e:
                log(f"sbv: detect error -> {e}")

            # 3) Carousels ("Brands related to your search")
            try:
                log("car: detect")
                car_idx = 0
                for heading in CAROUSEL_HEADINGS:
                    # Amazon uses span[role=heading] for these carousels, not h2
                    h = page.locator(f"span[role=heading]:has-text(\"{heading}\")").first
                    if h.count() == 0 or not h.is_visible():
                        # Fallback: try h2 variants
                        h = page.locator(f"h2:has-text(\"{heading}\")").first
                        if h.count() == 0 or not h.is_visible():
                            h = page.locator(f"h2 span:has-text(\"{heading}\")").first
                            if h.count() == 0 or not h.is_visible():
                                log(f"car: heading not found -> {heading}")
                                continue
                    # Budget check
                    if time_left() < 20:
                        log("car: budget low, break")
                        break
                    log(f"car: found heading -> {heading}")
                    container_el = None
                    try:
                        # Scroll heading into view first (Instacart pattern)
                        try:
                            h.scroll_into_view_if_needed()
                            time.sleep(0.1)
                        except Exception:
                            pass
                        
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
                    except Exception:
                        container_el = None

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
                        # CDP capture handles image stability - no need for stabilization loop

                        # IMPORTANT: choose the real container we will classify & screenshot
                        root_loc = root_el if container_el else h.locator("xpath=ancestor::div[1]")

                        # Extract brand/message now (you use these later)
                        brand_txt, brand_canon, message = _extract_brand_amz(root_loc, keyword=keyword, ad_type="Sponsored_Brand_or_Carousel")

                        # Classifier guardrail: SB vs Carousel
                        try:
                            cards_count = root_loc.locator('div[data-asin]').count()
                        except Exception:
                            cards_count = 0
                        try:
                            brand_links = root_loc.locator('a[href*="/stores/"], a[href*="/brand"]').count()
                        except Exception:
                            brand_links = 0
                        force_sb_brand_tiles = (cards_count < 3 and brand_links >= 3)

                        anchor = _module_anchor(root_loc)
                        if anchor in seen_anchors:
                            log(f"car: duplicate anchor skipped -> {anchor}")
                            continue
                        seen_anchors.add(anchor)

                        is_sb = bool(re.match(r'^(sb|sponsoredb|sponsoredbrands)', (anchor or '').lower()))
                        adv_for_name = brand_canon or "unknown"
                        ad_type = "Sponsored_Brand" if (force_sb_brand_tiles or is_sb or (brand_links >= 3 and cards_count == 0)) else "Sponsored_Carousel"
                        folder = "Sponsored_Brand" if ad_type == "Sponsored_Brand" else "Sponsored_Carousel"

                        # Build product list quickly (no image downloads here – screenshot is the asset)
                        products = []
                        try:
                            cards = root_loc.locator('div[data-asin]')
                            cnt = min(cards.count(), 24)
                            for i2 in range(cnt):
                                c = cards.nth(i2)
                                asin = _get_attr(c, 'data-asin') or None
                                title = safe_text(c.locator('h2 a span'), timeout=50)
                                href = safe_attr(c.locator('h2 a, a.a-link-normal'), 'href', timeout=50)
                                if href and not href.startswith('http'):
                                    href = f"https://www.amazon.com{href}"
                                if any([asin, title, href]):
                                    products.append({"asin": asin, "href": href, "title": title})
                        except Exception as e:
                            log(f"car: products parse error -> {e}")
                    except Exception as e:
                        log(f"car: detect error -> {e}")

                    # Screenshot the module
                    fname = _std_filename("amazon", adv_for_name, ad_type, client, keyword, run_id, car_idx, ".png")
                    fpath = os.path.join(output_dir, folder, fname)
                    try:
                        freeze_layout_and_hide_sticky(page)
                        try:
                            root_loc.scroll_into_view_if_needed()
                            _sleep(0.2)
                        except Exception:
                            pass
                        capture_module(root_loc, fpath, bctx, page, log)
                        module_id, eid = _build_ids(ad_type, heading, brand_canon, anchor, run_id, car_idx)
                        if module_id in captured_modules:
                            log(f"car: duplicate module skipped -> {module_id}")
                        else:
                            captured_modules.add(module_id)
                            ads.append({
                                "id": eid,
                                "module_id": module_id,
                                "type": ad_type,
                                "subtype": heading,
                                "brand": brand_txt or "Unknown",
                                "brand_canonical": brand_canon,
                                "advertisers": [brand_canon] if brand_canon else [],
                                "header": heading,
                                "products": products,
                                "capture_entire_carousel": True,
                                "position": car_idx + 1,
                                "image_path": f"{folder}/{fname}",
                                "video_path": None,
                                "message": message,
                                "metadata": {"subtype": heading, "count": len(products)},
                            })
                        log(f"car: saved -> {fpath} exists={os.path.exists(fpath)} module_id={module_id}")
                        # Track bbox to prevent display overlap
                        try:
                            r = bbox(root_loc)
                            if r:
                                occupied_regions.append(r)
                        except Exception:
                            pass
                        car_idx += 1
                        if car_idx >= MAX_CAR:
                            log("car: reached MAX_CAR, stop")
                            break
                    except Exception as e:
                        log(f"car: screenshot fail -> {e}")
            except Exception as e:
                log(f"car: detect error -> {e}")

            # 3a) Sponsored Brand (headline-based, mid-page or top)
            try:
                log("sb-headline: detect")
                # Quick visibility debug for v2
                try:
                    v2_count = page.locator('div[data-card-metrics-id*="sb-themed-collection"] a[data-elementid="sb-headline"]').count()
                    log(f"sb-headline(v2 themed) count = {v2_count}")
                except Exception:
                    pass
                sbh = page.locator('a[data-elementid="sb-headline"]')
                h_count_el = sbh.element_handle(timeout=1000)  # presence check
                if h_count_el:
                    count = sbh.count()  # safe now
                    for i in range(count):
                        if time_left() < 15:
                            log("sb-headline: budget low, break")
                            break
                        link = sbh.nth(i)
                        # Prefer the v2 wrapper (CardInstance…), then v2 metrics, then legacy sponsored, then nearest div
                        container = link.locator("xpath=ancestor::div[starts-with(@id,'CardInstance')][1]")
                        if container.count() == 0:
                            container = link.locator("xpath=ancestor::div[contains(@data-card-metrics-id,'sb-themed-collection')][1]")
                        if container.count() == 0:
                            container = link.locator("xpath=ancestor::div[contains(@cel_widget_id,'sponsored') or contains(@data-cel-widget,'sponsored')][1]")
                        if container.count() == 0:
                            container = link.locator("xpath=ancestor::div[1]")
                        # Dedupe before we shoot
                        try:
                            sig = container_signature(container)
                            if sig and sig in seen_signatures:
                                log(f"sb-headline: duplicate signature skipped -> {sig}")
                                continue
                            # Overlap dedupe: if this headline container sits inside a previously captured SB, skip it
                            try:
                                container.scroll_into_view_if_needed()
                            except Exception:
                                pass
                            _sleep(0.2)
                            this_box = bbox(container)
                            if any(overlaps(this_box, prev) for prev in occupied_regions):
                                log("sb-headline: skipped due to overlap with captured module")
                                continue
                        except Exception:
                            pass

                        # Freeze + screenshot (use your capture wrapper or locator.screenshot)
                        try:
                            page.evaluate("() => { const st=document.createElement('style'); st.textContent='*{transition:none!important;animation:none!important}'; document.head.appendChild(st); }")
                        except Exception:
                            pass
                        # Brand/message
                        brand_txt, brand_canon, message = _extract_brand_amz(container, keyword=keyword, ad_type="Sponsored_Brand_Headline")
                        adv_for_name = brand_canon or "unknown"
                        fname = _std_filename("amazon", adv_for_name, "Sponsored_Brand", client, keyword, run_id, i, ".png")
                        fpath = os.path.join(output_dir, "Sponsored_Brand", fname)
                        freeze_layout_and_hide_sticky(page)
                        try:
                            container.scroll_into_view_if_needed()
                            _sleep(0.2)
                        except Exception:
                            pass
                        capture_module(container, fpath, bctx, page, log)
                        anchor = _module_anchor(container)
                        if anchor in seen_anchors:
                            log(f"sb-headline: duplicate anchor skipped -> {anchor}")
                            continue
                        seen_anchors.add(anchor)
                        module_id, eid = _build_ids("Sponsored_Brand", "Headline", brand_canon, anchor, run_id, i)
                        if module_id in captured_modules:
                            log(f"sb-headline: duplicate module -> {module_id}")
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
                            "header": message,
                            "products": [],
                            "capture_entire_carousel": True,
                            "position": i + 1,
                            "image_path": f"Sponsored_Brand/{fname}",
                            "video_path": None,
                            "message": message,
                            "metadata": {},
                        })
                        log(f"sb-headline: saved -> {fpath} module_id={module_id}")
                        # Record signature and occupied geometry
                        try:
                            sig = container_signature(container)
                            if sig:
                                seen_signatures.add(sig)
                            r = bbox(container)
                            if r:
                                occupied_regions.append(r)
                        except Exception:
                            pass
                else:
                    log("sb-headline: none")
            except Exception as e:
                log(f"sb-headline: detect error -> {e}")

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
                    # Skip if we already captured this SB wrapper (signature or overlap)
                    try:
                        sig = container_signature(el)
                        if sig and sig in seen_signatures:
                            log(f"sb-themed: duplicate signature skipped -> {sig}")
                            continue
                        # Avoid double-capturing top SB via geometry
                        this_box = bbox(el)
                        if any(overlaps(this_box, prev) for prev in occupied_regions):
                            log("sb-themed: skipped due to overlap with captured module")
                            continue
                    except Exception:
                        pass
                    brand_txt, brand_canon, message = _extract_brand_amz(el, keyword=keyword, ad_type="Sponsored_Brand_Themed")
                    raw_cel = _get_attr(el, 'cel_widget_id') or ''
                    raw_metrics = _get_attr(el, 'data-card-metrics-id') or ''
                    subtype = "Top" if ("top-slot" in raw_cel or "top" in raw_metrics) else "Inline"
                    adv_for_name = brand_canon or "unknown"
                    fname = _std_filename("amazon", adv_for_name, "Sponsored_Brand", client, keyword, run_id, i, ".png")
                    fpath = os.path.join(output_dir, "Sponsored_Brand", fname)
                    try:
                        freeze_layout_and_hide_sticky(page)
                        try:
                            el.scroll_into_view_if_needed()
                            _sleep(0.2)
                        except Exception:
                            pass
                        capture_module(el, fpath, bctx, page, log)
                        anchor = _module_anchor(el)
                        if anchor in seen_anchors:
                            log(f"sb-themed: duplicate anchor skipped -> {anchor}")
                            continue
                        seen_anchors.add(anchor)
                        module_id, eid = _build_ids("Sponsored_Brand", f"Themed_Collection_{subtype}", brand_canon, anchor, run_id, i)
                        if module_id in captured_modules:
                            log(f"sb-themed: duplicate module skipped -> {module_id}")
                            continue
                        captured_modules.add(module_id)
                        # Products (lightweight; no image downloads)
                        products = []
                        cards = el.locator('div[data-asin]')
                        cnt = min(cards.count(), 24)
                        for j in range(cnt):
                            c = cards.nth(j)
                            asin = _get_attr(c, 'data-asin') or None
                            title = safe_text(c.locator('h2 a span'), timeout=50)
                            href = safe_attr(c.locator('h2 a, a.a-link-normal'), 'href', timeout=50)
                            if href and not href.startswith('http'):
                                href = f"https://www.amazon.com{href}"
                            if any([asin, title, href]):
                                products.append({"asin": asin, "href": href, "title": title})
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
                        # Record signature and occupied geometry for later dedupe
                        try:
                            sig = container_signature(el)
                            if sig:
                                seen_signatures.add(sig)
                            r = bbox(el)
                            if r:
                                occupied_regions.append(r)
                        except Exception:
                            pass
                    except Exception as e:
                        log(f"sb-themed: screenshot fail -> {e}")
            except Exception as e:
                log(f"sb-themed: detect error -> {e}")

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
                    # Instacart-style scroll and freeze
                    try:
                        el.scroll_into_view_if_needed()
                        time.sleep(0.1)
                    except Exception:
                        pass
                    try:
                        el.evaluate("""
                          (el) => new Promise(async (resolve) => {
                            const sleep = (ms) => new Promise(r => setTimeout(r, ms));
                            let stable = 0, last = 0;
                            for (let i=0; i<8 && stable<3; i++) {
                              const imgs = Array.from(el.querySelectorAll('img')).filter(i => i.complete && i.naturalWidth > 10).length;
                              if (imgs === last) stable++; else stable = 0;
                              last = imgs; await sleep(300);
                            }
                            resolve(true);
                          })
                        """)
                    except Exception:
                        pass
                    try:
                        if left_ads.nth(i).locator('img').count() == 0:
                            log("display: left skipped (no images)")
                            continue
                    except Exception:
                        pass
                    # Enhanced brand extraction for display ads
                    brand_txt, brand_canon, message = _extract_brand_amz(el, keyword=keyword, ad_type="Sponsored_Display_Left")
                    # Display-specific fallback: try to extract brand from iframe content or alt text
                    if not brand_txt:
                        try:
                            # Try brand from image alt text in display ads
                            img_alt = safe_text(el.locator('img[alt]'), timeout=50)
                            if img_alt and len(img_alt.strip()) > 0 and len(img_alt.split()) <= 4:
                                brand_txt = img_alt.strip()
                                try:
                                    brand_canon = canonicalize(brand_txt)
                                except Exception:
                                    brand_canon = brand_txt.lower().replace(' ', '_')
                        except Exception:
                            pass
                    adv_for_name = brand_canon or "unknown"
                    fname = _std_filename("amazon", adv_for_name, "Sponsored_Display", client, keyword, run_id, i, ".png")
                    fpath = os.path.join(output_dir, "Sponsored_Display", fname)
                    try:
                        freeze_layout_and_hide_sticky(page)
                        try:
                            el.scroll_into_view_if_needed()
                            _sleep(0.1)
                        except Exception:
                            pass
                        capture_module(el, fpath, bctx, page, log)
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
                            "brand": brand_txt or "Unknown",
                            "brand_canonical": brand_canon,
                            "advertisers": [brand_canon] if brand_canon else [],
                            "image_path": f"Sponsored_Display/{fname}",
                            "video_path": None,
                            "message": message,
                            "metadata": {},
                        })
                        log(f"display: left saved -> {fpath} module_id={module_id}")
                        # Track bbox to prevent future overlaps
                        try:
                            box = bbox(el)
                            if box:
                                occupied_regions.append(box)
                        except Exception:
                            pass
                    except Exception as e:
                        log(f"display: left screenshot fail -> {e}")
            except Exception as e:
                log(f"display: left detect error -> {e}")

            try:
                log("display: detect bottom")
                all_adholders = page.locator('div.AdHolder')
                bottom_ads = []
                total = min(all_adholders.count(), 20)
                for i in range(total):
                    ad = all_adholders.nth(i)
                    if ad.locator('xpath=ancestor::div[contains(@class, "s-left-ads-item")]').count() > 0: continue
                    if ad.locator('xpath=ancestor::a[@data-elementid="sb-headline"]').count() > 0: continue
                    if ad.locator('xpath=ancestor::div[contains(@cel_widget_id,"sb-themed-collection") or contains(@data-card-metrics-id,"sb-themed-collection")]').count() > 0: continue
                    if ad.locator('xpath=ancestor::div[contains(@cel_widget_id,"VIDEO_SINGLE_PRODUCT") or contains(@data-cel-widget,"VIDEO_SINGLE_PRODUCT")]').count() > 0: continue
                    if ad.locator('xpath=ancestor::div[@data-component-type="s-search-result"]').count() > 0: continue
                    if ad.locator("iframe").count() == 0: continue
                    bottom_ads.append(ad)
                    if len(bottom_ads) >= MAX_BOTTOM_DISPLAY:
                        break

                log(f"display: bottom found {len(bottom_ads)} ads (excluded left rail & SB)")
                for i, el in enumerate(bottom_ads):
                    if not el.is_visible():
                        continue
                    # dedupe by overlap
                    try:
                        this_box = bbox(el)
                        if any(overlaps(this_box, prev) for prev in occupied_regions):
                            log("display: skipped due to overlap with captured module")
                            continue
                    except Exception:
                        pass
                    # Instacart-style scroll and freeze
                    try:
                        el.scroll_into_view_if_needed()
                        time.sleep(0.1)
                    except Exception:
                        pass
                    try:
                        el.evaluate("""
                          (el) => new Promise(async (resolve) => {
                            const sleep = (ms) => new Promise(r => setTimeout(r, ms));
                            let stable = 0, last = 0;
                            for (let i=0; i<10 && stable<3; i++) {
                              const imgs = Array.from(el.querySelectorAll('img')).filter(i => i.complete && i.naturalWidth > 10).length;
                              if (imgs === last) stable++; else stable = 0;
                              last = imgs; await sleep(300);
                            }
                            resolve(true);
                          })
                        """)
                    except Exception:
                        pass
                    try:
                        if bottom_ads.nth(i).locator('img').count() == 0:
                            log("display: bottom skipped (no images)")
                            continue
                    except Exception:
                        pass
                    # Enhanced brand extraction for display ads
                    brand_txt, brand_canon, message = _extract_brand_and_message(el)
                    # Display-specific fallback: try to extract brand from iframe content or alt text
                    if not brand_txt:
                        try:
                            # Try brand from image alt text in display ads
                            img_alt = safe_text(el.locator('img[alt]'), timeout=50)
                            if img_alt and len(img_alt.strip()) > 0 and len(img_alt.split()) <= 4:
                                brand_txt = img_alt.strip()
                                try:
                                    brand_canon = canonicalize(brand_txt)
                                except Exception:
                                    brand_canon = brand_txt.lower().replace(' ', '_')
                        except Exception:
                            pass
                    adv_for_name = brand_canon or "unknown"
                    fname = _std_filename("amazon", adv_for_name, "Sponsored_Display", client, keyword, run_id, i, ".png")
                    fpath = os.path.join(output_dir, "Sponsored_Display", fname)
                    try:
                        freeze_layout_and_hide_sticky(page)
                        try:
                            el.scroll_into_view_if_needed()
                            _sleep(0.1)
                        except Exception:
                            pass
                        capture_module(el, fpath, bctx, page, log)
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
                            "brand": brand_txt or "Unknown",
                            "brand_canonical": brand_canon,
                            "advertisers": [brand_canon] if brand_canon else [],
                            "image_path": f"Sponsored_Display/{fname}",
                            "video_path": None,
                            "message": message,
                            "metadata": {},
                        })
                        log(f"display: bottom saved -> {fpath} module_id={module_id}")
                        # Track bbox to prevent future overlaps
                        try:
                            box = bbox(el)
                            if box:
                                occupied_regions.append(box)
                        except Exception:
                            pass
                    except Exception as e:
                        log(f"display: bottom screenshot fail -> {e}")
            except Exception as e:
                log(f"display: bottom detect error -> {e}")

            # 4) Sponsored Products (aggregate + ASIN images)
            try:
                log("sp: aggregate")
                items = page.locator('div[data-component-type="s-search-result"]')
                n = min(items.count(), 80)  # cap to avoid huge pages
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
                    if not present(item.locator('span:has-text("Sponsored"), div:has-text("Sponsored")'), timeout=50):
                        continue

                    rank += 1
                    if len(sp_list) >= MAX_SP:
                        break

                    asin = safe_attr(item, "data-asin", timeout=50)
                    # Try multiple title selectors for better reliability
                    title = (safe_text(item.locator('h2 a span'), timeout=50) or 
                            safe_text(item.locator('h2 span'), timeout=50) or
                            safe_text(item.locator('[data-cy="title-recipe-title"]'), timeout=50) or
                            safe_text(item.locator('.a-size-medium-plus'), timeout=50) or "")
                    img_src = safe_attr(item.locator('img.s-image'), 'src', timeout=50)
                    price_text = safe_text(item.locator('span.a-price .a-offscreen'), timeout=50)
                    rating_label = safe_text(item.locator('span.a-icon-alt'), timeout=50)
                    rating = None
                    if rating_label:
                        try:
                            rating = float(rating_label.split()[0])
                        except Exception:
                            rating = None
                    reviews_count = None
                    rv_txt = safe_text(item.locator('span[aria-label$="ratings"], span[aria-label$="rating"]'), timeout=50)
                    if rv_txt:
                        digits = ''.join(c for c in rv_txt if c.isdigit())
                        reviews_count = int(digits) if digits else None
                    prime = present(item.locator('i.a-icon.a-icon-prime, svg[aria-label="Prime"]'), timeout=50)

                    # Try multiple selectors for product URL
                    product_url = (safe_attr(item.locator('h2 a'), 'href', timeout=50) or
                                  safe_attr(item.locator('.a-link-normal.a-text-normal'), 'href', timeout=50) or
                                  safe_attr(item.locator('[data-cy="title-recipe-title"]'), 'href', timeout=50))
                    if product_url and not product_url.startswith('http'):
                        product_url = f"https://www.amazon.com{product_url}"

                    # Image handling (central only)
                    image_path_rel = None
                    if img_src and img_src.startswith("http"):
                        from urllib.parse import urlparse
                        ext = os.path.splitext(urlparse(img_src).path)[1] or ".jpg"
                        file_name = (asin or f"rank_{rank}") + ext
                        central_full = central_asin_dir / file_name
                        if not central_full.exists():
                            try:
                                r = session.get(img_src, timeout=ASIN_FETCH_TIMEOUT, stream=True)
                                if r.ok:
                                    with open(central_full, 'wb') as fimg:
                                        shutil.copyfileobj(r.raw, fimg)
                            except Exception as e:
                                log(f"sp: asin download fail -> {e}")
                        if central_full.exists():
                            image_path_rel = str(central_full)

                    # Extract brand from product detail
                    brand = None
                    brand_canonical = None
                    try:
                        # Try brand from multiple sources
                        brand_text = (safe_text(item.locator('h5.a-color-base span'), timeout=50) or
                                    safe_text(item.locator('.a-size-base-plus.a-color-base'), timeout=50) or
                                    safe_text(item.locator('[data-cy="brand-recipe-title"]'), timeout=50))
                        if brand_text and len(brand_text.strip()) > 0:
                            brand = brand_text.strip()
                            try:
                                brand_canonical = canonicalize(brand)
                            except Exception:
                                brand_canonical = brand.lower().replace(' ', '_')
                    except Exception:
                        pass

                    sp_list.append({
                        "asin": asin,
                        "rank": rank,
                        "page": page_num,
                        "brand": brand,
                        "brand_canonical": brand_canonical,
                        "title": title,
                        "image_url": img_src,
                        "image_path": image_path_rel,  # central path only
                        "price": price_text,
                        "rating": rating,
                        "reviews_count": reviews_count,
                        "prime": prime,
                        "badges": [],
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

            # Save HTML at the end
            try:
                log("html: save")
                html_content = page.content()
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                log(f"html: saved -> {html_path} exists={os.path.exists(html_path)} size={os.path.getsize(html_path) if os.path.exists(html_path) else 0}")
            except Exception as e:
                log(f"html: save error -> {e}")

            success = True
        except Exception as e:
            log(f"fatal: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Save tracing
            try:
                trace_path = os.path.join(runs_dir, f"trace_{ts}.zip")
                bctx.tracing.stop(path=trace_path)
                log(f"trace: saved -> {trace_path} exists={os.path.exists(trace_path)} size={os.path.getsize(trace_path) if os.path.exists(trace_path) else 0}")
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
            "ts": ts,
            "html": os.path.basename(html_path),
            "ads": ads,
            "timestamp": datetime.utcnow().isoformat(timespec="seconds").replace("+00:00", "Z"),
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
    keyword = sys.argv[1] if len(sys.argv) > 1 else "coffee maker"
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "output/amazon/test"

    success = search_and_capture(keyword, output_dir)
    if success:
        print("\n✅ AMAZON SEARCH AND CAPTURE COMPLETED SUCCESSFULLY")
    else:
        print("\n❌ AMAZON SEARCH AND CAPTURE FAILED")
        sys.exit(1)