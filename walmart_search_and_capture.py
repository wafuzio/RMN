import os
import pdb
import shutil
import socket
import subprocess
import threading
import time
import json
import base64
import requests
import glob
import collections
import sys
import random
import inspect
import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Dict, Optional, Callable, Tuple, Any
from urllib.parse import urlparse, parse_qs, unquote, quote_plus
from pathlib import Path
from playwright.sync_api import sync_playwright, Page, BrowserContext, Browser

# Canonical timestamp helper
from utils.time_utils import now_iso_z

# Folder mapping/validation
from utils.path_taxonomy import folder_for_adtype, validate_folder

# Brand canonicalization and blacklist
from core.brands import canonicalize, is_blacklisted

# Import standardized filename generation
try:
    from filename_utils import generate_ad_filename
except ImportError:
    # Fallback if filename_utils not available
    def generate_ad_filename(retailer, ad_type, client, search_term, timestamp, index=1, extension='png'):
        return f"{retailer}_{ad_type}_{client}_{search_term}_{timestamp}_{index}.{extension}"

# Import brand logo database
try:
    from brand_logo_database import BrandLogoDatabase
except ImportError:
    BrandLogoDatabase = None

# Import brand lexicon canonicalization and adding
try:
    from core.brands import canonicalize as canonicalize_brand, add_brand as add_brand_to_lexicon
except ImportError:
    canonicalize_brand = None
    add_brand_to_lexicon = None
# --- BEGIN: debug configuration ---
@dataclass
class DebugConfig:
    break_on_px: bool = False
    break_on_blocked: bool = False
    line_trace: bool = False
    pdb_on_exception: bool = True

DEBUG = DebugConfig()

def _apply_debug_config(debug: DebugConfig):
    """Apply debug configuration from GUI to globals and environment."""
    global DEBUG
    DEBUG = debug or DebugConfig()

    # Mirror to environment for any legacy checks
    os.environ["WALMART_BREAK_ON_PX"] = "1" if DEBUG.break_on_px else "0"
    os.environ["WALMART_BREAK_ON_BLOCKED"] = "1" if DEBUG.break_on_blocked else "0"
    os.environ["WALMART_TRACE"] = "1" if DEBUG.line_trace else "0"
# --- END: debug configuration ---

# --- BEGIN: robust stealth import ---
apply_stealth = None
try:
    # Preferred: most recent builds export stealth_sync(page)
    from playwright_stealth import stealth_sync as apply_stealth  # type: ignore
except Exception:
    try:
        # Some builds export `stealth`  (function) at top-level
        from playwright_stealth import stealth as _stealth  # could be function or module
        if callable(_stealth):
            apply_stealth = _stealth  # function
        else:
            # Module: pick a callable inside it
            if hasattr(_stealth, "stealth_sync") and callable(_stealth.stealth_sync):
                def apply_stealth(page): return _stealth.stealth_sync(page)
            elif hasattr(_stealth, "stealth") and callable(_stealth.stealth):
                def apply_stealth(page): return _stealth.stealth(page)
    except Exception:
        try:
            # Fallback: import module and look up symbols dynamically
            import playwright_stealth as _ps
            for n in ("stealth_sync", "stealth"):
                if hasattr(_ps, n) and callable(getattr(_ps, n)):
                    _fn = getattr(_ps, n)
                    def apply_stealth(page, _fn=_fn): return _fn(page)
                    break
        except Exception:
            pass

if apply_stealth is None:
    # No-op fallback keeps the scraper running if the package is missing/mismatched
    def apply_stealth(_page): 
        return
# --- END: robust stealth import ---

# --- BEGIN: step logger ---
class StepLogger:
    """JSONL logger for detailed run telemetry."""
    def __init__(self, base_dir, keyword):
        # Will be set after SLUG is defined
        self.path = None
        self.base_dir = base_dir
        self.keyword = keyword
        self.lock = threading.Lock()
        self.t0 = time.time()
    
    def _ensure_path(self):
        if self.path is None:
            # safe_filename will be defined later in the module
            safe_kw = "".join(c if c.isalnum() or c in (' ', '_', '-') else '_' for c in self.keyword).replace(' ', '_')
            self.path = os.path.join(self.base_dir, f"{SLUG}_{safe_kw}_steps.jsonl")
    
    def log(self, event, **data):
        self._ensure_path()
        rec = {"ts": time.time(), "t": round(time.time() - self.t0, 3), "event": event}
        rec.update(data)
        try:
            with self.lock:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass

@contextmanager
def step(SL, name: str, **meta):
    """Context manager for timing and logging steps."""
    SL.log("step_start", name=name, **meta)
    t0 = time.time()
    try:
        yield
    except Exception as e:
        SL.log("step_error", name=name, dur=round(time.time()-t0, 3), error=str(e))
        raise
    else:
        SL.log("step_end", name=name, dur=round(time.time()-t0, 3))
# --- END: step logger ---

# --- BEGIN: close-aware guards ---
CLOSED = {"page": False, "ctx": False}

def _on_page_close():
    CLOSED["page"] = True
    print("[page] closed")

def _on_ctx_close():
    CLOSED["ctx"] = True
    print("[ctx] closed")

def _guard_against_closed(action_name="action"):
    """Guard against acting after page/context closes."""
    if CLOSED["page"] or CLOSED["ctx"]:
        if CURRENT_SL:
            CURRENT_SL.log("closed_guard_trip", where=action_name)
        return True
    return False
# --- END: close-aware guards ---

# --- BEGIN: milestone tracker ---
class MilestoneTracker:
    def __init__(self, SL):
        self.SL = SL
        self.m = {}   # name -> {"ok": bool, "ts": float, "note": str}
    def mark(self, name, ok=True, note=""):
        self.m[name] = {"ok": bool(ok), "ts": time.time(), "note": note}
        if self.SL:
            self.SL.log("milestone", run_id=RUN_ID, name=name, ok=bool(ok), note=note)
    def summary(self):
        ok_all = all(v["ok"] for v in self.m.values()) if self.m else False
        ordered = [{"name": k, **v} for k, v in self.m.items()]
        return {"ok_all": ok_all, "count": len(self.m), "milestones": ordered}
# --- END: milestone tracker ---

# --- BEGIN: scoped line tracer (opt-in via WALMART_TRACE=1) ---
class ScopedTracer:
    def __init__(self, filename_filter: str, out_path: str):
        self.filter = filename_filter
        self.out_path = out_path
        self.f = None
    def __enter__(self):
        self.f = open(self.out_path, "w", encoding="utf-8")
        def tracer(frame, event, arg):
            if event == "line":
                fn = os.path.basename(frame.f_code.co_filename)
                if self.filter in fn:
                    self.f.write(f"{fn}:{frame.f_lineno} {frame.f_code.co_name}\n")
            return tracer
        sys.settrace(tracer)
        return self
    def __exit__(self, exc_type, exc, tb):
        sys.settrace(None)
        try: self.f.close()
        except: pass
# --- END: scoped line tracer ---

# CRITICAL: Exact headers from real Chrome browser
# ORDER MATTERS! PerimeterX checks header order
# This is the EXACT order Chrome sends headers (captured from real browser)
from collections import OrderedDict

REAL_CHROME_HEADERS = OrderedDict([
    # Chrome sends headers in this specific order:
    ("sec-ch-ua", '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"'),
    ("sec-ch-ua-mobile", "?0"),
    ("sec-ch-ua-platform", '"macOS"'),
    ("Upgrade-Insecure-Requests", "1"),
    ("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"),
    ("Sec-Fetch-Site", "none"),
    ("Sec-Fetch-Mode", "navigate"),
    ("Sec-Fetch-User", "?1"),
    ("Sec-Fetch-Dest", "document"),
    ("Accept-Encoding", "gzip, deflate, br, zstd"),
    ("Accept-Language", "en-US,en;q=0.9"),
])

HEADERS = {
    "user-agent": REAL_CHROME_HEADERS["User-Agent"],
}

# Module-level constants
PROFILE_ENV = "WALMART_PROFILE_DIR"
SLUG = "walmart"
DISPLAY_NAME = "Walmart"

# Module-level logger handles (set inside search_and_capture)
CURRENT_SL: Optional["StepLogger"] = None
RUN_ID: Optional[str] = None

# Submit tracking for forensics
SUBMIT = {"method": "", "t": 0.0}

# Browser UA cache (set once per run from live browser)
BROWSER_UA = {"ua": None}

# ---------------------------------------------------------------------------
# Singleton browser context — shared across all search_and_capture() calls
# within the same process session.  Mirrors the CLI pattern: one Chrome
# launch, one persistent context, one new_page() / page.close() per keyword.
# Poisoned cookies stay in memory (never flushed to disk between keywords).
# Call close_walmart_context() at process exit to clean up.
# ---------------------------------------------------------------------------
_WALMART_SINGLETON: dict = {"playwright": None, "ctx": None, "page": None}

# Shared net counters — reset at the start of each search_and_capture() call.
# Context-level listeners reference this dict so they stay wired across runs.
_WALMART_NET_COUNTERS: dict = {"req_failed": 0, "resp_doc": 0, "route_errors": 0}


def close_walmart_context() -> None:
    """Close the singleton browser context and stop Playwright.

    Call this at application shutdown (e.g. after all keywords have been
    processed).  Safe to call multiple times.
    """
    pg  = _WALMART_SINGLETON.get("page")
    pw  = _WALMART_SINGLETON.get("playwright")
    ctx = _WALMART_SINGLETON.get("ctx")
    _WALMART_SINGLETON["page"] = None
    _WALMART_SINGLETON["ctx"] = None
    _WALMART_SINGLETON["playwright"] = None
    if pg is not None:
        try:
            pg.close()
        except Exception:
            pass
    if ctx is not None:
        try:
            ctx.close()
        except Exception:
            pass
    if pw is not None:
        try:
            pw.stop()
        except Exception:
            pass
    print("[walmart] singleton context closed")

# Ad modules we'll detect and screenshot
SELECTORS = {
    "skyline":        'iframe[data-ad-type="top"]',         # Top strip banner (LandO Lakes style)
    "sba":            '[data-testid="sba-container"]',      # Sponsored Brand module
    "tile_takeover":  '[data-testid="tile-take-over"]',     # Tile takeover
    "sbv":            '[data-testid="search-video-in-grid"]',  # Sponsored Brand Video
    "marquee_banner": '[data-testid="marquee2"]',           # Onsite Display Marquee Banner (top + bottom)
    "gallery_cards":  '[data-testid="galleryBottom"]',      # Gallery Bottom Ad Cards carousel
    "gallery_card_iframe": 'iframe[data-ad-type^="gallerybottom"]',  # Individual card iframes
}
@dataclass
class CaptureResult:
    html_saved: int
    shots: List[str]
    assets: List[str]
    meta: Dict


# --- BEGIN: WalmartAdInterceptor (network response capture for GraphQL ad payloads) ---
import re as _re

_ORCHESTRA_RE = _re.compile(r"/orchestra/(?:home|pdp|api|search)/graphql", _re.I)
_SWAG_RE = _re.compile(r"/swag/graphql", _re.I)
_VIDEO_INTERCEPT_RE = _re.compile(r"\.(mp4|m3u8|mpd|webm|mov)(\?|$)", _re.I)
_VAST_INTERCEPT_RE = _re.compile(r"(vast|vpaid|adtag|adsystem)", _re.I)
_AD_IMAGE_INTERCEPT_RE = _re.compile(r"(creative|banner|ad[_\-]image|sponsoredAsset)", _re.I)


class WalmartAdInterceptor:
    """Attaches to a Playwright page BEFORE navigation and captures ad-relevant network responses.

    Sources:
      - /orchestra/**/graphql  → AdV3 sponsored shelf ads, lazy item stacks
      - /swag/graphql          → AdV2DisplayDSP display/banner ads
      - Video URLs (.mp4/.m3u8/.mpd)
      - VAST/VPAID ad tag URLs
      - Creative asset image URLs
    """

    def __init__(self):
        self.orchestra_payloads: List[Dict] = []
        self.swag_payloads: List[Dict] = []
        self.video_urls: List[str] = []
        self.vast_urls: List[str] = []
        self.asset_urls: List[str] = []

        # Parsed after harvest()
        self.sponsored_shelf_ads: List[Dict] = []
        self.display_banner_ads: List[Dict] = []
        self.lazy_items: List[Dict] = []

    def attach(self, page) -> None:
        """Register response handler. MUST be called before page.goto()."""
        page.on("response", self._on_response)

    def _on_response(self, response) -> None:
        url = response.url
        try:
            if _ORCHESTRA_RE.search(url):
                self._capture_json(url, "orchestra", response)
            elif _SWAG_RE.search(url):
                self._capture_json(url, "swag", response)
            elif _VIDEO_INTERCEPT_RE.search(url):
                if url not in self.video_urls:
                    self.video_urls.append(url)
            elif _VAST_INTERCEPT_RE.search(url):
                if url not in self.vast_urls:
                    self.vast_urls.append(url)
            elif _AD_IMAGE_INTERCEPT_RE.search(url):
                if url not in self.asset_urls:
                    self.asset_urls.append(url)
        except Exception:
            pass

    def _capture_json(self, url: str, source: str, response) -> None:
        try:
            ct = response.headers.get("content-type", "")
            if "json" not in ct and "graphql" not in url:
                return
            body = response.json()
            if source == "orchestra":
                self.orchestra_payloads.append({"url": url, "body": body})
            else:
                self.swag_payloads.append({"url": url, "body": body})
        except Exception:
            pass

    def harvest(self, debug_dir: Optional[str] = None) -> "WalmartAdInterceptor":
        """Parse all captured payloads. Call after scrolling. Returns self."""
        for entry in self.orchestra_payloads:
            self._parse_orchestra(entry.get("body", {}))
        for i, entry in enumerate(self.swag_payloads):
            body = entry.get("body", {})
            # Dump raw payload for key-path inspection when debug_dir provided
            if debug_dir:
                try:
                    import json as _json
                    dp = os.path.join(debug_dir, f"swag_payload_{i}.json")
                    with open(dp, "w") as _f:
                        _json.dump({"url": entry.get("url"), "body": body}, _f, indent=2)
                except Exception:
                    pass
            self._parse_swag(body)
        for i, entry in enumerate(self.orchestra_payloads):
            body = entry.get("body", {})
            if debug_dir:
                try:
                    import json as _json
                    dp = os.path.join(debug_dir, f"orchestra_payload_{i}.json")
                    with open(dp, "w") as _f:
                        _json.dump({"url": entry.get("url"), "body": body}, _f, indent=2)
                except Exception:
                    pass
        return self

    def _parse_orchestra(self, body: Dict) -> None:
        data = body.get("data") or {}
        self._walk_sponsored(data, depth=0)
        self._walk_item_stacks(data, depth=0)

    def _walk_sponsored(self, node: Any, depth: int) -> None:
        if depth > 8 or not isinstance(node, dict):
            return
        for key, val in node.items():
            if key in ("sponsoredProducts", "adV3", "sponsoredShelf", "sponsoredAds"):
                ads = val if isinstance(val, list) else (val.get("ads", []) if isinstance(val, dict) else [])
                for ad in ads:
                    if isinstance(ad, dict):
                        self.sponsored_shelf_ads.append(ad)
                        # Collect video URLs embedded in ad payload
                        ad_str = json.dumps(ad)
                        for m in _VIDEO_INTERCEPT_RE.finditer(ad_str):
                            start = max(0, m.start() - 200)
                            chunk = ad_str[start:m.end() + 50]
                            um = _re.search(r'https?://[^\s"\'\\]+' + _re.escape(m.group(0).split("?")[0]), chunk)
                            if um:
                                u = um.group(0).rstrip('",\\')
                                if u not in self.video_urls:
                                    self.video_urls.append(u)
            elif isinstance(val, dict):
                self._walk_sponsored(val, depth + 1)
            elif isinstance(val, list):
                for item in val:
                    self._walk_sponsored(item, depth + 1)

    def _walk_item_stacks(self, node: Any, depth: int) -> None:
        if depth > 6 or not isinstance(node, dict):
            return
        for key, val in node.items():
            if key == "itemStacks" and isinstance(val, list):
                for stack in val:
                    for item in (stack.get("items", []) if isinstance(stack, dict) else []):
                        if isinstance(item, dict) and item.get("name"):
                            self.lazy_items.append(item)
            elif isinstance(val, dict):
                self._walk_item_stacks(val, depth + 1)

    def _parse_swag(self, body: Dict) -> None:
        data = body.get("data") or {}
        self._walk_display_ads(data, depth=0)

    def _walk_display_ads(self, node: Any, depth: int) -> None:
        if depth > 8 or not isinstance(node, dict):
            return
        for key, val in node.items():
            if key in ("adV2DisplayDSP", "multiImpDspAd", "displayAdDSP", "displayAd", "bannerAd", "dspAd"):
                ads = val if isinstance(val, list) else ([val] if isinstance(val, dict) else [])
                for ad in ads:
                    if isinstance(ad, dict):
                        self.display_banner_ads.append(ad)
            elif isinstance(val, dict):
                self._walk_display_ads(val, depth + 1)
            elif isinstance(val, list):
                for item in val:
                    self._walk_display_ads(item, depth + 1)

# --- END: WalmartAdInterceptor ---


def _extract_next_data_items(page, SL=None) -> Optional[Dict]:
    """Extract organic and sponsored items from __NEXT_DATA__ JSON embedded in the page.

    Returns dict with keys: organic_items, sponsored_items, organic_count, sponsored_count.
    Returns None on failure.
    """
    try:
        raw = page.evaluate(
            "() => { const el = document.getElementById('__NEXT_DATA__'); return el ? el.textContent : null; }"
        )
        if not raw:
            if SL: SL.log("next_data_missing")
            return None

        nd = json.loads(raw)
        props = nd.get("props", {}).get("pageProps", {})
        sr = props.get("initialData", {}).get("searchResult", {})
        stacks = sr.get("itemStacks", [])

        organic: List[Dict] = []
        sponsored: List[Dict] = []

        for stack in stacks:
            for item in stack.get("items", []):
                if not isinstance(item, dict) or not item.get("name"):
                    continue
                item_id = str(item.get("usItemId", ""))
                is_sponsored = bool(item.get("isSponsoredFlag") or item.get("sponsoredProduct"))
                entry = {
                    "item_id": item_id,
                    "name": item.get("name", ""),
                    "brand": item.get("brand", "") or "",
                    "price": ((item.get("priceInfo") or {}).get("linePrice") or ""),
                    "image_url": ((item.get("imageInfo") or {}).get("thumbnailUrl") or ""),
                    "href": item.get("canonicalUrl", ""),
                    "is_sponsored": is_sponsored,
                    "seller": item.get("sellerName", "Walmart"),
                    "ad_uuid": (item.get("sponsoredProduct") or {}).get("adUuid") if isinstance(item.get("sponsoredProduct"), dict) else None,
                }
                if is_sponsored:
                    sponsored.append(entry)
                else:
                    organic.append(entry)

        return {
            "organic_items": organic,
            "sponsored_items": sponsored,
            "organic_count": len(organic),
            "sponsored_count": len(sponsored),
            "total": sr.get("aggregatedCount", 0),
        }
    except Exception as e:
        if SL: SL.log("next_data_error", error=str(e))
        return None


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def safe_filename(name: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in name)


# --- BEGIN: Walmart run helpers (canonical schema and artifact writing) ---

def build_run_id() -> str:
    """
    Build 14-digit run ID in local time, e.g., 20251026161402.
    Walmart uses nested timestamp directories: runs/<run_id>/
    """
    return datetime.now().strftime("%Y%m%d%H%M%S")

def build_run_payload(retailer: str, client: str, keyword: str, run_id: str, ads: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Canonical run JSON payload:
    {
      "retailer": "...",
      "client": "...",
      "keyword": "...",
      "timestamp": "YYYY-MM-DDTHH:MM:SSZ",
      "run_id": "YYYYMMDDHHMMSS",
      "ads": [ {...}, ... ]
    }
    """
    return {
        "retailer": retailer,
        "client": client,
        "keyword": keyword,
        "timestamp": now_iso_z(),  # ISO 8601 with Z
        "run_id": run_id,
        "ads": ads,
    }

def save_run_artifacts(client_root: Path, run_id: str, html_content: str, run_payload: Dict[str, Any]) -> Path:
    """
    Save Walmart run artifacts under:
      <client_root>/runs/<run_id>/
        - search_results_<run_id>.html
        - run_results_<run_id>.json
    client_root must be the path: output/walmart/<client>
    """
    run_dir = client_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Save HTML
    (run_dir / f"search_results_{run_id}.html").write_text(html_content, encoding="utf-8")

    # Save canonical JSON
    (run_dir / f"run_results_{run_id}.json").write_text(json.dumps(run_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    return run_dir

# --- END: Walmart run helpers ---


# --- BEGIN: Walmart ad object builder (canonical) ---

def _ensure_str_or_none(val: Optional[str]) -> Optional[str]:
    """Convert value to string or None, stripping whitespace."""
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None

def _relative_image_path(saved_path: Path, client_root: Path) -> str:
    """
    Return path like 'SBA/walmart__brand__sba__client__kw__D2025-10-26_T16-14.02_1.png'
    saved_path MUST be under output/walmart/<client> (client_root).
    """
    return str(saved_path.relative_to(client_root))

def build_ad_object(
    run_id: str,
    ad_index: int,
    ad_type: str,                  # "SBA" | "SBV" | "Tile_Takeover"
    client_root: Path,             # output/walmart/<client>
    saved_path: Path,              # absolute path to saved image file
    brand_name: Optional[str] = None,
    ad_title: Optional[str] = None,
    cta_text: Optional[str] = None,
    destination_url: Optional[str] = None,
    cdn_image_url: Optional[str] = None,
    slot_index: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Build a canonical ad object with safe defaults.
    """
    # Defensive checks
    assert ad_type in {"SBA", "SBV", "Tile_Takeover", "Gallery_Cards", "Skyline", "Marquee_Banner"}, f"Unexpected ad_type: {ad_type}"
    folder = folder_for_adtype("walmart", ad_type)
    assert validate_folder("walmart", folder), f"Invalid Walmart folder: {folder}"

    rel_path = _relative_image_path(saved_path, client_root)
    ad_id = f"walmart-{run_id}-{ad_index}"

    # Canonicalize brand name using lexicon
    raw_brand = _ensure_str_or_none(brand_name)
    canon_brand = canonicalize(raw_brand) if raw_brand else None
    
    # Skip blacklisted brands (house ads, retailer brands)
    final_brand = canon_brand or raw_brand
    if is_blacklisted(final_brand):
        print(f"⚠️ Skipping blacklisted brand: {final_brand}")
        return None

    ad_obj: Dict[str, Any] = {
        "id": ad_id,
        "type": ad_type,                                 # exact canonical type
        "brand": canon_brand or raw_brand,               # prefer canonical; fallback to raw
        "brand_logo": None,                              # to be enriched later
        "title": _ensure_str_or_none(ad_title),
        "description": None,                             # capture later if you have it
        "cta": _ensure_str_or_none(cta_text),
        "href": _ensure_str_or_none(destination_url),
        "image_url": _ensure_str_or_none(cdn_image_url), # original CDN, if known
        "image_path": rel_path,                          # relative to client_root
        "products": [],                                  # reserved for future
        "metadata": {
            "slot": slot_index,
        },
    }
    return ad_obj

# --- END: Walmart ad object builder ---


def _extract_brand_from_title(title: str) -> Optional[str]:
    """
    Extract brand name from product title.
    Flexible approach - brand could be 1-3 words at the start.
    
    Examples:
      "Keto Pint Salted Caramel..." -> "Keto Pint"
      "Breyers Ice Cream..." -> "Breyers"
      "Ben & Jerry's Cherry Garcia..." -> "Ben & Jerry's"
    """
    if not title or len(title) < 2:
        return None
    
    # Split into words
    words = title.split()
    if not words:
        return None
    
    # Common patterns for brand extraction:
    # 1. Single capitalized word (e.g., "Breyers")
    # 2. Two words, both capitalized (e.g., "Keto Pint", "Blue Bunny")
    # 3. Brand with & (e.g., "Ben & Jerry's")
    # 4. Brand with apostrophe (e.g., "Reese's")
    
    # Try 1-3 words, stop at common product descriptors
    stop_words = {
        'ice', 'cream', 'bar', 'bars', 'pint', 'pints', 'oz', 'fl', 'count',
        'pack', 'box', 'tub', 'carton', 'sandwich', 'cone', 'cones',
        'chocolate', 'vanilla', 'strawberry', 'caramel', 'cookie', 'fudge',
        'with', 'in', 'of', 'the', 'and', 'or', 'for', 'no', 'added', 'sugar',
        'low', 'fat', 'free', 'dairy', 'non', 'organic', 'natural',
        'gelato', 'sorbet', 'yogurt', 'butter', 'cups', 'cup', 'sea', 'salt',
        'sweet', 'freedom', 'keto', 'top', 'cherry', 'garcia', 'peanut'
    }
    
    brand_words = []
    for i, word in enumerate(words[:4]):  # Check first 4 words max
        word_lower = word.lower().rstrip(',')
        
        # Stop if we hit a common product descriptor
        if word_lower in stop_words and i > 0:
            break
        
        # Include word if:
        # - It's capitalized (brand names are usually capitalized)
        # - It's a connector (&, 'n, ')
        # - It's part of a possessive (ends with 's or ')
        if word[0].isupper() or word in ['&', "'n", "n'"] or word.endswith("'s") or word.endswith("'"):
            brand_words.append(word)
            # Limit to 3 words max for brand
            if len(brand_words) >= 3:
                break
        else:
            # Stop at first non-capitalized word (unless it's a connector)
            if i > 0:  # Allow at least one word
                break
    
    if not brand_words:
        # Fallback: just use first word if it's capitalized
        if words[0][0].isupper():
            return words[0].rstrip(',')
        return None
    
    # Join brand words
    brand = ' '.join(brand_words).strip()
    
    # Clean up trailing punctuation
    brand = brand.rstrip('.,;:')
    
    return brand if len(brand) > 1 else None


def _write_run_report(base_dir, report): 
    """Write both JSON and Markdown report into the run dir."""
    try:
        # JSON
        jpath = os.path.join(base_dir, "run_report.json")
        with open(jpath, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        
        # Markdown
        mpath = os.path.join(base_dir, "run_report.md")
        lines = []
        add = lines.append
        add(f"# Walmart Run Report — {report.get('keyword','')}")
        add(f"- started: {report.get('started_at','')}")
        add(f"- outcome: {report.get('outcome','')}  ")
        if report.get("bail_reason"):
            add(f"- bail_reason: {report['bail_reason']}")
        add("")
        add("## Timings")
        t = report.get("timings", {})
        for k,v in t.items():
            add(f"- {k}: {v}")
        add("")
        add("## Environment")
        env = report.get("env",{})
        add(f"- user_agent: {env.get('ua')}")
        wg = env.get("webgl",{})
        add(f"- webgl_vendor: {wg.get('vendor')}  ")
        add(f"- webgl_renderer: {wg.get('renderer')}")
        add("")
        add("## Cookies")
        cok = report.get("cookies",{})
        add(f"- pre_count: {cok.get('pre_count')}  pre_names: {cok.get('pre_names',[])[:8]}")
        add(f"- post_count: {cok.get('post_count')} post_names: {cok.get('post_names',[])[:8]}")
        add("")
        add("## PX")
        px = report.get("px",{})
        for k,v in px.items():
            add(f"- {k}: {v}")
        add("")
        add("## Network Forensics")
        nf = report.get("network",{})
        add(f"- req_failed: {nf.get('req_failed',0)}")
        add(f"- resp_doc: {nf.get('resp_doc',0)}")
        add(f"- route_errors: {nf.get('route_errors',0)}")
        add("")
        add("## Artifacts")
        art = report.get("artifacts",{})
        for k,v in art.items():
            if v:
                add(f"- {k}: {v}")
        
        # Diagnostics summary for quick PX blame analysis
        diag = report.get("diag", {})
        if any(diag.values()):
            add("")
            add("## Diagnostics")
            if diag.get("navigator"):
                nd = diag["navigator"]
                add(f"- webdriver: {nd.get('webdriver')} plugins: {nd.get('pluginsLength')} hwc: {nd.get('hardwareConcurrency')} deviceMemory: {nd.get('deviceMemory')}")
            if diag.get("webglUnmasked"):
                wu = diag["webglUnmasked"]
                add(f"- webgl_unmasked_vendor: {wu.get('unmaskedVendor')} ")
                add(f"- webgl_unmasked_renderer: {wu.get('unmaskedRenderer')}")
            if diag.get("navHeaders"):
                nh = diag["navHeaders"]
                add(f"- sec-ch-ua: {nh.get('sec-ch-ua')}")
                add(f"- sec-ch-ua-mobile: {nh.get('sec-ch-ua-mobile')}")
                add(f"- sec-ch-ua-platform: {nh.get('sec-ch-ua-platform')}")
            if diag.get("suspiciousCookies"):
                add(f"- suspicious_cookies: {diag.get('suspiciousCookies')}")
        
        try:
            with open(mpath, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
        except Exception:
            pass
        
        return {"json": jpath, "md": mpath}
    except Exception:
        return {}


def _build_report(keyword, outcome, bail_reason, started_at, timings, env_info, cookies_info, px_stats, net_counters, artifacts, SL):
    """Helper to build report dict with diagnostics for PX troubleshooting."""
    # Build diagnostics section for quick PX blame analysis
    diag = {
        "navigator": env_info.get("navigator_diag"),
        "webglUnmasked": env_info.get("webgl", {}).get("unmasked"),
        "navHeaders": env_info.get("nav_headers"),
        "suspiciousCookies": cookies_info.get("suspicious", []),
    }
    
    return {
        "keyword": keyword,
        "outcome": outcome,
        "bail_reason": bail_reason,
        "started_at": started_at,
        "timings": timings,
        "env": env_info,
        "cookies": cookies_info,
        "px": px_stats,
        "network": net_counters,
        "artifacts": {**artifacts, "steps_log": SL.path if SL else None},
        "diag": diag,  # Quick diagnosis: webdriver, plugins, sec-ch-ua, etc.
    }


def _dump_html_png(page, base_dir: str, stem: str):
    """Save HTML and screenshot for forensics."""
    try:
        page.screenshot(path=os.path.join(base_dir, safe_filename(f"{stem}.png")))
    except Exception:
        pass
    try:
        with open(os.path.join(base_dir, safe_filename(f"{stem}.html")), "w", encoding="utf-8") as f:
            f.write((page.content() or "")[:200_000])
    except Exception:
        pass


def _parse_walmart_redirect(href: str) -> str:
    """
    Walmart redirectors:
    - https://www.walmart.com/sp/track?...&rd=
    - https://www.walmart.com/dad/trk/... (encrypted)
    Prefer rd= when present; otherwise leave as-is.
    """
    try:
        u = urlparse(href)
        qs = parse_qs(u.query)
        if "rd" in qs and qs["rd"]:
            return unquote(qs["rd"][0])
        return href
    except Exception:
        return href


def _download(url: str, out_path: str, timeout: int = 25) -> bool:
    """Download asset (video) through proxy if configured."""
    try:
        proxies = _requests_proxies_from_env()
        # Use live browser UA (not hardcoded)
        hdrs = {
            "User-Agent": BROWSER_UA["ua"] or HEADERS["user-agent"],
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.walmart.com/",
        }
        r = requests.get(url, headers=hdrs, timeout=timeout, proxies=proxies)
        r.raise_for_status()
        with open(out_path, "wb") as f:
            f.write(r.content)
        return True
    except Exception:
        return False


# --- BEGIN: profile fingerprint persistence ---
def _fp_paths(profile_dir: Optional[str]):
    if not profile_dir:
        return None, None
    fp_dir = os.path.join(profile_dir, "_rmn_fingerprint")
    os.makedirs(fp_dir, exist_ok=True)
    return os.path.join(fp_dir, "viewport.json"), os.path.join(fp_dir, "timezone.txt")

def _load_or_init_profile_fingerprint(profile_dir: Optional[str]):
    vp_path, tz_path = _fp_paths(profile_dir)
    if not vp_path:
        return {"width": 1440, "height": 900}, "America/Chicago"
    try:
        with open(vp_path, "r") as f:
            viewport = json.load(f)
        with open(tz_path, "r") as f:
            timezone = f.read().strip()
        return viewport, timezone
    except:
        viewports = [
            {'width': 1920, 'height': 1080},
            {'width': 1366, 'height': 768},
            {'width': 1440, 'height': 900},
            {'width': 1536, 'height': 864},
            {'width': 1680, 'height': 1050},
        ]
        timezones = ['America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles']
        viewport = random.choice(viewports)
        timezone = random.choice(timezones)
        try:
            with open(vp_path, "w") as f:
                json.dump(viewport, f)
            with open(tz_path, "w") as f:
                f.write(timezone)
        except:
            pass
        return viewport, timezone

def _load_or_init_noise_seed(profile_dir: Optional[str]) -> int:
    """
    Return a stable integer noise seed for this profile.

    Used to generate hardware fingerprint noise that is:
    - Consistent within a profile (same session = same fingerprint)
    - Different from the real hardware values (changes canvas/audio hash)
    - Different across profiles (each profile looks like a different machine)

    Stored at <profile_dir>/_rmn_fingerprint/noise_seed.txt
    """
    if not profile_dir:
        return 0x1A2B3C4D
    fp_dir = os.path.join(profile_dir, "_rmn_fingerprint")
    os.makedirs(fp_dir, exist_ok=True)
    seed_path = os.path.join(fp_dir, "noise_seed.txt")
    try:
        with open(seed_path, "r") as f:
            return int(f.read().strip())
    except:
        import secrets
        seed = secrets.randbelow(2**31)
        try:
            with open(seed_path, "w") as f:
                f.write(str(seed))
        except:
            pass
        return seed
# --- END: profile fingerprint persistence ---

def _get_proxy_config():
    """Get proxy configuration from environment if available."""
    proxy_server = os.environ.get('WALMART_PROXY_SERVER')  # e.g., http://proxy.example.com:8080?session=WALMART001
    proxy_username = os.environ.get('WALMART_PROXY_USERNAME')
    proxy_password = os.environ.get('WALMART_PROXY_PASSWORD')

    if proxy_server:
        proxy_config = {'server': proxy_server}
        if proxy_username and proxy_password:
            proxy_config['username'] = proxy_username
            proxy_config['password'] = proxy_password
        return proxy_config
    return None


def _requests_proxies_from_env():
    """Get proxy dict for requests library (routes video downloads through proxy)."""
    proxy_server = os.environ.get('WALMART_PROXY_SERVER')
    proxy_username = os.environ.get('WALMART_PROXY_USERNAME')
    proxy_password = os.environ.get('WALMART_PROXY_PASSWORD')
    
    if not proxy_server:
        return None
    
    # Build proxy URL with auth if provided
    if proxy_username and proxy_password:
        # Extract scheme and host from proxy_server
        if '://' in proxy_server:
            scheme, rest = proxy_server.split('://', 1)
            proxy_url = f"{scheme}://{proxy_username}:{proxy_password}@{rest}"
        else:
            proxy_url = f"http://{proxy_username}:{proxy_password}@{proxy_server}"
    else:
        proxy_url = proxy_server
    
    return {
        "http": proxy_url,
        "https": proxy_url,
    }


def _launch(playwright, profile_dir: Optional[str], headless: bool = False, proxy_config: dict = None, net_counters: dict = None):
    """
    Returns (browser_or_None, context, page, is_persistent)
    Uses persistent context when profile_dir is provided.
    Uses persistent Chrome (channel=chrome) for maximum stealth.
    """
    # CRITICAL: Walmart requires persistent profile (defense-in-depth)
    if not profile_dir:
        raise RuntimeError("Walmart requires a persistent Chrome profile; non-persistent context is disabled.")
    
    if net_counters is None:
        net_counters = {"req_failed": 0, "resp_doc": 0, "route_errors": 0}
    # CRITICAL: GPU acceleration args for proper WebGL fingerprint
    # Empty args = software rendering = "WebKit WebGL" = instant PX block
    # These args ensure Chrome uses real GPU (ANGLE/Metal on macOS)
    args = [
        '--disable-blink-features=AutomationControlled',  # Sets navigator.webdriver=undefined at browser level (no JS override needed)
        '--use-angle=metal',  # Force ANGLE→Metal backend on macOS
        '--enable-gpu-rasterization',  # Prefer GPU raster
        '--ignore-gpu-blocklist',  # Don't let Chrome silently disable GPU
        # Keep window visible but don't steal focus
        '--disable-focus-on-load',
        '--noerrdialogs',
    ]
    
    if profile_dir:
        # DIAGNOSTIC: Verify we're using the same profile path every run
        print(f"[profile] using user_data_dir={profile_dir!r}")
        
        # Load stable fingerprint for this profile (not randomized per run!)
        viewport, timezone = _load_or_init_profile_fingerprint(profile_dir)
        noise_seed = _load_or_init_noise_seed(profile_dir)
        print(f"[fingerprint] noise_seed={noise_seed} (stable per profile)")
        
        # Use persistent Chrome (channel=chrome) for real Chrome browser
        launch_options = {
            'user_data_dir': profile_dir,
            'headless': False,  # ALWAYS headed for Walmart
            'viewport': viewport,  # STABLE per profile
            'locale': 'en-US',
            'timezone_id': timezone,  # STABLE per profile
            'args': args,
            'chromium_sandbox': True,  # CRITICAL: Force sandbox ON (removes banner)
        }
        
        # CRITICAL: Use real Chrome for correct JA3 TLS fingerprint
        # Playwright's Chromium has different TLS stack = detectable
        try:
            launch_options['channel'] = 'chrome'  # Real Chrome = correct JA3
            if proxy_config:
                launch_options['proxy'] = proxy_config
            ctx = playwright.chromium.launch_persistent_context(**launch_options)
            print(f"✅ Using real Chrome (correct JA3 fingerprint)")
            
            # Hardware fingerprint spoofing init script.
            #
            # Akamai identifies machines by canvas hash, audio fingerprint, and
            # navigator hardware properties — not just IP or cookies. If this
            # machine's fingerprint is in their blocklist, every session is
            # pre-challenged regardless of behavior or IP.
            #
            # This script applies stable per-profile noise that shifts those
            # signals to look like different hardware. The seed is generated
            # once and stored in the profile directory so the fingerprint is
            # consistent within a profile but unique across profiles/machines.
            ctx.add_init_script(f"""
(function() {{
    const SEED = {noise_seed};

    // --- Fast seeded PRNG (mulberry32) ---
    function prng(seed) {{
        return function() {{
            seed = (seed + 0x6D2B79F5) | 0;
            var t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
            t = t + Math.imul(t ^ (t >>> 7), 61 | t) ^ t;
            return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
        }};
    }}

    // --- navigator.webdriver: must be undefined, not true ---
    try {{
        Object.defineProperty(navigator, 'webdriver', {{ get: () => undefined }});
    }} catch(e) {{}}

    // --- Hardware concurrency + device memory ---
    // Pick from realistic values, stable for this profile.
    const HW_OPTIONS  = [4, 6, 8, 10, 12, 16];
    const MEM_OPTIONS = [4, 8, 16];
    const hwConcurrency = HW_OPTIONS[SEED % HW_OPTIONS.length];
    const deviceMemory  = MEM_OPTIONS[(SEED >> 4) % MEM_OPTIONS.length];
    try {{ Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => hwConcurrency }}); }} catch(e) {{}}
    try {{ Object.defineProperty(navigator, 'deviceMemory',        {{ get: () => deviceMemory  }}); }} catch(e) {{}}

    // --- Canvas fingerprint noise ---
    // Akamai draws text to a small canvas and hashes the pixel output.
    // We add 1-bit noise to the first row of small canvases — imperceptible
    // visually but changes the hash. We save + restore pixels so the page
    // rendering canvas is unaffected.
    (function() {{
        const orig = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function() {{
            // Only touch small canvases (fingerprinting), not UI/render targets
            if (this.width > 0 && this.width <= 500 && this.height > 0 && this.height <= 300) {{
                const ctx2d = this.getContext('2d');
                if (ctx2d) {{
                    try {{
                        const scanW = Math.min(this.width, 64);
                        const img   = ctx2d.getImageData(0, 0, scanW, 1);
                        const saved = new Uint8ClampedArray(img.data);
                        const rng   = prng(SEED ^ (this.width * 997 + this.height));
                        for (let i = 0; i < img.data.length; i += 4) {{
                            img.data[i] ^= (rng() > 0.5 ? 1 : 0); // flip LSB of red
                        }}
                        ctx2d.putImageData(img, 0, 0);
                        const result = orig.apply(this, arguments);
                        // Restore so the visible canvas is unchanged
                        for (let j = 0; j < img.data.length; j++) img.data[j] = saved[j];
                        ctx2d.putImageData(img, 0, 0);
                        return result;
                    }} catch(e) {{}}
                }}
            }}
            return orig.apply(this, arguments);
        }};
    }})();

    // --- Audio fingerprint noise ---
    // AudioContext fingerprinting reads the output of an OfflineAudioContext
    // oscillator through an AnalyserNode. We add a tiny seed-derived offset
    // only for very short buffers (fingerprinting), not real audio playback.
    (function() {{
        const audioNoise = ((SEED & 0xFFFF) / 0xFFFF) * 1e-7;
        const orig = AudioBuffer.prototype.getChannelData;
        AudioBuffer.prototype.getChannelData = function(ch) {{
            const data = orig.call(this, ch);
            // Only perturb fingerprinting buffers (short, not music/SFX)
            if (this.length > 0 && this.length < 4096 && this.numberOfChannels <= 2) {{
                data[0] = data[0] + audioNoise;
            }}
            return data;
        }};
    }})();
}})();
            """)
            
        except Exception as e:
            # CRITICAL: Do NOT fall back to Chromium - bail instead
            # Chromium has wrong JA3/CH fingerprint = instant PX detection
            print(f"❌ Chrome channel launch failed ({e})")
            print(f"❌ Real Chrome not available - aborting to avoid PX fingerprint mismatch")
            print(f"❌ Install Chrome: brew install --cask google-chrome")
            if CURRENT_SL:
                CURRENT_SL.log("chrome_channel_failed", error=str(e), fatal=True)
            raise RuntimeError(f"Real Chrome not available; aborting to avoid PX fingerprint mismatch: {e}")
        
        # Only set Accept-Language; let Chrome generate sec-* and UA dynamically
        ctx.set_extra_http_headers({"Accept-Language": "en-US,en;q=0.9"})
        
        ctx.on("close", lambda: print("[ctx] closed"))
        
        # --- forensic listeners (context-level — fire for all pages, all runs) ---
        def _req_failed(req):
            if CURRENT_SL:
                CURRENT_SL.log("req_failed",
                               url=req.url, method=req.method,
                               resource=req.resource_type, failure=str(req.failure))
            _WALMART_NET_COUNTERS["req_failed"] += 1

        def _resp_doc(res):
            try:
                req = res.request
                if req.is_navigation_request() and req.resource_type == "document":
                    if CURRENT_SL:
                        CURRENT_SL.log("resp_doc",
                                       url=res.url, status=res.status,
                                       method=req.method, fromCache=res.from_service_worker)
                    _WALMART_NET_COUNTERS["resp_doc"] += 1
            except Exception as e:
                if CURRENT_SL:
                    CURRENT_SL.log("resp_doc_error", err=str(e))

        ctx.on("requestfailed", _req_failed)
        ctx.on("response", _resp_doc)
        
        # --- BEGIN: off-domain guard rails (NARROW - Google only) ---
        # CRITICAL: Do NOT route PX/RUM/TAP endpoints - PX detects routing fingerprints
        # Only route Google top-level navigations to prevent accidental redirects
        def _guard_google_nav(route):
            req = route.request
            try:
                if req.is_navigation_request():
                    u = req.url.lower()
                    if "//google." in u or "//www.google." in u:
                        if CURRENT_SL:
                            CURRENT_SL.log("route_abort", url=req.url, reason="google_top_nav")
                        return route.abort()
                return route.continue_()
            except Exception as e:
                if CURRENT_SL:
                    CURRENT_SL.log("route_error", url=req.url, err=str(e))
                _WALMART_NET_COUNTERS["route_errors"] += 1
                return route.continue_()
        
        # Route ONLY Google domains (not "**/*" - that touches PX/RUM endpoints)
        ctx.route("*://www.google.*/**", _guard_google_nav)
        ctx.route("*://google.*/**", _guard_google_nav)
        # --- END: off-domain guard rails ---
        
        # PX beacons (requests)
        def _log_px_beacon(req):
            u = req.url.lower()
            if "px-cloud.net" in u:
                print(f"[px] beacon -> {req.method} {req.url}")
        ctx.on("request", _log_px_beacon)
        
        # PX responses - log via CURRENT_SL
        def _log_px_response(res):
            u = res.url.lower()
            if "px-cloud.net" in u and CURRENT_SL:
                CURRENT_SL.log("px_resp", url=res.url, status=res.status, method=res.request.method)
        ctx.on("response", _log_px_response)
        
        # /blocked detector (request-level)
        def _log_blocked_nav(req):
            if req.is_navigation_request() and "walmart.com/blocked" in req.url.lower():
                _log_px_trip(CURRENT_SL, "nav_to_blocked")
                if os.environ.get("WALMART_BREAK_ON_BLOCKED") == "1":
                    print(f"\n🔴 NAV TO BLOCKED: {req.url}")
                    import pdb; pdb.set_trace()
        ctx.on("request", _log_blocked_nav)
        
        # Return context only — page is created per-run by _get_walmart_ctx / search_and_capture
        return None, ctx, None, True
    
    browser = playwright.chromium.launch(
        headless=headless,
        args=args,
        ignore_default_args=["--enable-automation"],
        chromium_sandbox=True,  # CRITICAL: Force sandbox ON
    )
    # CRITICAL: Never override UA - decouples UA/JA3/CH from browser's real fingerprint
    # For Walmart, this branch should never run (persistent profile required)
    ctx = browser.new_context(
        viewport={"width": 1366, "height": 768},
        # user_agent removed - let Chrome use its real UA
        locale="en-US",
    )
    page = ctx.new_page()
    page.on("crash", lambda: print("[page] crashed"))
    page.on("close", lambda: _on_page_close())
    ctx.on("close", lambda: _on_ctx_close())
    page.on("console", lambda msg: print("[console]", msg.type, msg.text))
    
    return None, ctx, page, False


# Cookies that Akamai/PX use to flag a session as bot-contaminated.
# Removing them from the profile DB before Chrome launches gives the
# session a clean slate without touching any legitimate trust cookies.
_POISONED_COOKIE_NAMES = {'adblocked', 'ak_bmsc', 'bm_sv', 'bm_mi', 'bm_sz'}

def _scrub_profile_cookies(profile_dir: str) -> None:
    """Delete known bot-detection cookies from the Chrome profile SQLite DB.

    Must be called BEFORE Chrome launches — Chrome holds an exclusive lock
    on the Cookies DB while running.
    """
    import sqlite3
    cookie_db = os.path.join(profile_dir, "Default", "Cookies")
    if not os.path.exists(cookie_db):
        return
    try:
        conn = sqlite3.connect(cookie_db)
        placeholders = ",".join("?" * len(_POISONED_COOKIE_NAMES))
        cur = conn.execute(
            f"DELETE FROM cookies WHERE name IN ({placeholders})",
            list(_POISONED_COOKIE_NAMES)
        )
        removed = cur.rowcount
        conn.commit()
        conn.close()
        if removed:
            print(f"[walmart] scrubbed {removed} poisoned cookie(s) from profile: {cookie_db}")
        else:
            print(f"[walmart] profile clean — no poisoned cookies found")
    except Exception as e:
        print(f"[walmart] cookie scrub failed (non-fatal): {e}")


def _get_walmart_ctx(profile_dir: str, proxy_config: dict = None):
    """Return the shared persistent browser context, creating it on first call.

    Mirrors the CLI singleton pattern: one Chrome launch per process, one
    new_page()/page.close() per keyword.  Poisoned cookies stay in memory
    and are never flushed to disk between keyword runs.

    Call close_walmart_context() at process exit to tear down gracefully.
    """
    from playwright.sync_api import sync_playwright as _sync_pw

    singleton = _WALMART_SINGLETON
    ctx = singleton.get("ctx")

    if ctx is not None:
        try:
            _ = ctx.pages  # health-check — raises if playwright is gone
            return ctx
        except Exception:
            print("[walmart] singleton context dead — recreating")
            singleton["ctx"] = None
            try:
                singleton["playwright"].stop()
            except Exception:
                pass
            singleton["playwright"] = None

    # Scrub poisoned bot-detection cookies from the profile on disk BEFORE
    # Chrome launches — Chrome locks the SQLite DB once running, so this is
    # the only window where we can remove them cleanly.
    if profile_dir:
        _scrub_profile_cookies(profile_dir)

    print("[walmart] launching singleton Chrome context")
    pw = _sync_pw().start()
    singleton["playwright"] = pw

    _, ctx, _, _ = _launch(pw, profile_dir, proxy_config=proxy_config)
    singleton["ctx"] = ctx
    print("[walmart] singleton context ready")
    return ctx


def _capture_elements(page, base_dir: str, keyword: str, label: str, css: str, meta: Dict, SL=None, client_name: str = None, client_root: str = None, timestamp: str = None, filter_fn=None, run_id: str = None, ads_list: List[Dict[str, Any]] = None) -> Tuple[int, List[str]]:
    """
    Capture ad elements with optional filtering.
    
    Args:
        filter_fn: Optional function(item) -> bool to filter elements before capturing
        run_id: 14-digit run ID for canonical ad objects
        ads_list: List to append canonical ad objects to
    """
    shots: List[str] = []
    loc = page.locator(css)
    count = loc.count()

    # Close guard at start
    try:
        if page.is_closed():
            if SL: SL.log("closed_guard_trip", where="capture_elements_start", label=label)
            return 0, []
    except Exception:
        return 0, []

    for i in range(count):
        # Close guard in loop
        try:
            if page.is_closed():
                if SL: SL.log("closed_guard_trip", where="capture_elements_loop", label=label, i=i)
                break
        except Exception:
            break

        item = loc.nth(i)
        try:
            # Apply filter if provided
            if filter_fn and not filter_fn(item):
                if SL: SL.log("element_filtered", label=label, index=i+1)
                continue
            
            # Use native wheel scroll instead of programmatic scrollIntoView
            _bring_into_view(page, item, SL=SL)
            time.sleep(0.2)
            
            # Generate standardized filename and save to ad-type folder
            try:
                print(f"[CONDITION CHECK] client_name={client_name}, client_root={client_root}, timestamp={timestamp}, label={label}")
                if client_name and client_root and timestamp:
                    print(f"[USING STANDARDIZED] label={label}, index={i+1}")
                    
                    # Extract advertiser/brand name from the ad element
                    advertiser = None
                    try:
                        import re
                        
                        # Method 1: Try to find "Sponsored by [Brand]" text (works for SBA)
                        sponsored_text = item.locator('text=/Sponsored by/i').first
                        if sponsored_text.count() > 0:
                            full_text = sponsored_text.text_content()
                            match = re.search(r'Sponsored by\s+(.+)', full_text, re.IGNORECASE)
                            if match:
                                extracted_text = match.group(1).strip()
                                # Try lexicon match first
                                if canonicalize_brand:
                                    canonical = canonicalize_brand(extracted_text)
                                    if canonical:
                                        advertiser = canonical
                                        if SL: SL.log("sba_brand_lexicon_match", brand=advertiser, text=extracted_text)
                                    else:
                                        advertiser = extracted_text
                                else:
                                    advertiser = extracted_text
                        
                        # Method 2: For SBV/video ads, try multiple extraction strategies
                        if not advertiser and label == 'sbv':
                            # Strategy 2a: Try to find brand in video title/description text
                            try:
                                video_text = item.inner_text()
                                # Look for common patterns like "Brand Name - Product" or "Brand Name:"
                                brand_match = re.search(r'^([A-Z][a-zA-Z\s&\']+?)(?:\s*[-:]\s*|\s+presents)', video_text, re.MULTILINE)
                                if brand_match:
                                    advertiser = brand_match.group(1).strip()
                            except:
                                pass
                            
                            # Strategy 2b: Extract from video URL or tracking URL
                            if not advertiser:
                                try:
                                    # Look for any link within the video container
                                    video_link = item.locator('a').first
                                    if video_link.count() > 0:
                                        href = video_link.get_attribute('href') or ''
                                        # Extract product name from URL (handles both direct and redirect URLs)
                                        # Pattern: /ip/Brand-Product-Name/12345 or rd=...%2Fip%2FBrand-Product-Name%2F...
                                        product_match = re.search(r'(?:/ip/|%2Fip%2F)([^/]+?)(?:/|%2F|$)', href)
                                        if product_match:
                                            product_slug = product_match.group(1)
                                            # URL decode and get first word (usually the brand)
                                            product_slug = product_slug.replace('%20', ' ').replace('-', ' ')
                                            brand_parts = product_slug.split()
                                            if brand_parts:
                                                # Capitalize properly (e.g., "claussen" -> "Claussen")
                                                advertiser = brand_parts[0].title()
                                except:
                                    pass
                            
                            # Strategy 2c: Extract from product carousel within video ad
                            if not advertiser:
                                try:
                                    # SBV ads contain product items - look inside them
                                    # First, try to find product items within the SBV container
                                    product_items = item.locator('[data-item-id]').all()
                                    if product_items and len(product_items) > 0:
                                        # Get first product item
                                        first_product = product_items[0]
                                        
                                        # Try product brand element
                                        brand_elem = first_product.locator('[data-automation-id="product-brand"]').first
                                        if brand_elem.count() > 0:
                                            advertiser = brand_elem.inner_text().strip()
                                        
                                        # Alternative: extract from product title
                                        if not advertiser:
                                            product_title = first_product.locator('[data-automation-id="product-title"]').first
                                            if product_title.count() > 0:
                                                title_text = product_title.inner_text().strip()
                                                # First word is usually the brand (e.g., "Breyers Chocolate Ice Cream")
                                                brand_parts = title_text.split()
                                                if brand_parts:
                                                    advertiser = brand_parts[0]
                                except:
                                    pass
                        
                        # Method 3: Try to extract from URL facet parameter
                        if not advertiser:
                            links = item.locator('a[href*="facet"]').all()
                            for link in links[:3]:  # Check first few links
                                href = link.get_attribute('href') or ''
                                brand_match = re.search(r'facet[^&]*brand[^&]*[:%]([^&%]+)', href, re.IGNORECASE)
                                if brand_match:
                                    extracted_text = brand_match.group(1).replace('%20', ' ').replace('+', ' ')
                                    # Try lexicon match
                                    if canonicalize_brand:
                                        canonical = canonicalize_brand(extracted_text)
                                        if canonical:
                                            advertiser = canonical
                                            if SL: SL.log("brand_lexicon_match_facet", brand=advertiser, text=extracted_text)
                                        else:
                                            advertiser = extracted_text
                                    else:
                                        advertiser = extracted_text
                                    break
                        
                        # Method 4: For tile takeovers, extract from product brand
                        if not advertiser and label == 'tile_takeover':
                            # Try to find brand in product listings within the tile
                            brand_elem = item.locator('[data-automation-id="product-brand"]').first
                            if brand_elem.count() > 0:
                                advertiser = brand_elem.inner_text().strip()
                        
                        # Method 5: For marquee banners, extract from iframe or surrounding content
                        if not advertiser and label == 'marquee_banner':
                            try:
                                # Try to get iframe element
                                iframe = item.locator('iframe[data-ad-type="marquee2"]').first
                                if iframe.count() > 0:
                                    # Try to extract from iframe src URL
                                    iframe_src = iframe.get_attribute('src') or ''
                                    # Look for brand in URL parameters or path
                                    brand_match = re.search(r'brand[=_-]([^&/]+)', iframe_src, re.IGNORECASE)
                                    if brand_match:
                                        advertiser = brand_match.group(1).replace('%20', ' ').replace('+', ' ').title()
                                
                                # Alternative: Look for brand logo image near the marquee
                                if not advertiser:
                                    logo_img = item.locator('img[alt]:not([alt=""])').first
                                    if logo_img.count() > 0:
                                        logo_alt = logo_img.get_attribute('alt')
                                        if logo_alt and len(logo_alt) > 2:
                                            # Clean up alt text (remove "Logo", "Brand", etc.)
                                            cleaned = logo_alt
                                            for word in ['Logo', 'logo', 'Brand', 'brand']:
                                                cleaned = cleaned.replace(word, '').strip()
                                            if cleaned:
                                                advertiser = cleaned
                                
                                # Fallback: Extract from parent container ID
                                if not advertiser:
                                    parent_id = item.get_attribute('id') or ''
                                    # ID format: "SEARCH-MarqueeDisplayAd-marquee2-vanilla ice cream-"
                                    # Extract the search term part which might contain brand info
                                    id_match = re.search(r'marquee2-([^-]+)-', parent_id)
                                    if id_match:
                                        search_term = id_match.group(1).strip()
                                        # This is the search keyword, not the brand, so skip
                                        pass
                            except:
                                pass
                        
                        # Extract and save brand logo to database (for SBA and Marquee Banner ads)
                        if advertiser and advertiser != "unknown" and label in ['sba', 'marquee_banner'] and BrandLogoDatabase:
                            try:
                                # Look for brand logo image in SBA container
                                logo_img = item.locator('img[alt]:not([alt=""])').first
                                if logo_img.count() > 0:
                                    logo_src = logo_img.get_attribute('src')
                                    logo_alt = logo_img.get_attribute('alt')
                                    
                                    # Verify alt text matches advertiser (fuzzy match)
                                    if logo_src and logo_alt:
                                        # Normalize for comparison
                                        norm_alt = logo_alt.lower().strip()
                                        norm_advertiser = advertiser.lower().strip()
                                        
                                        # If alt text is close to advertiser name, save the logo
                                        if norm_alt in norm_advertiser or norm_advertiser in norm_alt:
                                            logo_db = BrandLogoDatabase()
                                            from utils.path_taxonomy import WALMART_LABEL_TO_FOLDER
                                            ad_type_name = WALMART_LABEL_TO_FOLDER.get(label, label.title())
                                            logo_db.add_brand_logo(
                                                brand=advertiser,
                                                logo_url=logo_src,
                                                retailer="walmart",
                                                metadata={
                                                    "ad_type": ad_type_name,
                                                    "keyword": keyword,
                                                    "timestamp": timestamp
                                                }
                                            )
                                            if SL: SL.log("brand_logo_saved", brand=advertiser, label=label)
                            except Exception as logo_err:
                                if SL: SL.log("brand_logo_error", error=str(logo_err), label=label)
                        
                        # Final fallback: Use "unknown" if we couldn't extract brand
                        # This ensures filename generation doesn't fail and frontend hooks work
                        if not advertiser:
                            advertiser = "unknown"
                            if SL: SL.log("advertiser_fallback", label=label, index=i+1, reason="no_extraction_method_succeeded")
                    except Exception as e:
                        if SL: SL.log("advertiser_extraction_error", error=str(e), label=label, index=i+1)
                        advertiser = "unknown"  # Ensure we have a value even on error
                    
                    # Map label to ad type folder name — imported from path_taxonomy,
                    # which also derives ALLOWED_FOLDERS from the same dict.
                    from utils.path_taxonomy import WALMART_LABEL_TO_FOLDER, validate_folder
                    ad_type_folder = WALMART_LABEL_TO_FOLDER.get(label, label.title())
                    
                    # Validate folder is allowed for Walmart
                    if not validate_folder('walmart', ad_type_folder):
                        if SL: SL.log("invalid_folder", label=label, folder=ad_type_folder, reason="not_in_allowed_folders")
                        continue  # Skip this ad if folder not allowed
                    # Save images to client_root (like Kroger), metadata goes to base_dir/runs
                    ad_folder = os.path.join(client_root, ad_type_folder)
                    print(f"[DEBUG] client_root={client_root}, ad_type_folder={ad_type_folder}, ad_folder={ad_folder}, advertiser={advertiser}")
                    os.makedirs(ad_folder, exist_ok=True)
                    
                    # Generate standardized filename
                    filename = generate_ad_filename(
                        retailer='walmart',
                        ad_type=label,
                        client=client_name,
                        search_term=keyword,
                        timestamp=timestamp,
                        index=i+1,
                        extension='png',
                        advertiser=advertiser
                    )
                    out = os.path.join(ad_folder, filename)
                    if SL: SL.log("standardized_filename", path=out, client_root=client_root, ad_folder=ad_folder, advertiser=advertiser)
                else:
                    # Fallback to old naming (for backward compatibility)
                    out = os.path.join(base_dir, safe_filename(f"{SLUG}_{keyword}_{label}_{i+1}.png"))
                    if SL: SL.log("fallback_filename", path=out, reason="missing_params", client_name=client_name, client_root=client_root, timestamp=timestamp)
            except Exception as e:
                # If standardized naming fails, fall back to old naming
                if SL: SL.log("filename_generation_error", error=str(e), label=label, index=i+1)
                out = os.path.join(base_dir, safe_filename(f"{SLUG}_{keyword}_{label}_{i+1}.png"))
            
            # For tile takeovers, screenshot 2 levels down (> div > section) to
            # skip the padding wrapper (pr4-xl) that adds large whitespace on the right.
            # Tachyons class names and data-dca-type are stable but structural nav
            # is more resilient than attribute matching.
            if label == 'tile_takeover':
                try:
                    inner = item.locator('> div > section').first
                    if inner.count() > 0:
                        inner.screenshot(path=out)
                    else:
                        item.screenshot(path=out)
                except Exception:
                    item.screenshot(path=out)
            else:
                item.screenshot(path=out)
            shots.append(out)
            
            # Build and append canonical ad object (if run_id and ads_list provided)
            if run_id and ads_list is not None and client_root and client_name:
                try:
                    # Extract destination URL
                    destination_url = None
                    try:
                        ahref = item.locator("a[href]").first
                        if ahref.count() > 0:
                            href = ahref.get_attribute("href") or ""
                            if href:
                                destination_url = _parse_walmart_redirect(href)
                    except Exception:
                        pass
                    
                    # Build ad object
                    ad_index = len(ads_list) + 1
                    saved_path = Path(out)
                    client_root_path = Path(client_root)
                    
                    ad_obj = build_ad_object(
                        run_id=run_id,
                        ad_index=ad_index,
                        ad_type=ad_type_folder,  # "SBA" | "SBV" | "Tile_Takeover"
                        client_root=client_root_path,
                        saved_path=saved_path,
                        brand_name=advertiser if advertiser != "unknown" else None,
                        ad_title=None,  # TODO: extract title when available
                        cta_text=None,  # TODO: extract CTA when available
                        destination_url=destination_url,
                        cdn_image_url=None,  # TODO: extract CDN URL when available
                        slot_index=i,  # grid position
                    )
                    if ad_obj is None:
                        # Blacklisted brand - delete the saved image
                        try:
                            saved_path.unlink(missing_ok=True)
                        except Exception:
                            pass
                        continue
                    ads_list.append(ad_obj)
                    if SL: SL.log("ad_object_built", ad_id=ad_obj["id"], type=ad_obj["type"], brand=ad_obj["brand"])
                except Exception as e:
                    if SL: SL.log("ad_object_build_error", error=str(e), label=label, index=i+1)
            
            # Store advertiser in metadata with ad type and index
            if advertiser:
                ad_key = f"{label}_{i+1}"  # e.g., "sba_1", "tile_takeover_2"
                meta.setdefault("advertisers", {})[ad_key] = advertiser
            
            # Store landing URL in legacy metadata
            if destination_url:
                meta.setdefault("links", []).append(destination_url)
            # Throttle per-element operations to avoid rapid-fire actions
            time.sleep(random.uniform(0.12, 0.28))
        except Exception:
            continue
    return count, shots


def _capture_gallery_cards(page, base_dir: str, keyword: str, meta: Dict, SL=None, client_name: str = None, client_root: str = None, timestamp: str = None, run_id: str = None, ads_list: List[Dict[str, Any]] = None) -> Tuple[int, List[str]]:
    """
    Capture Gallery Bottom Ad Cards (carousel of sponsored brand cards).
    
    These ads are in iframes with content like:
    - #heading: headline text
    - #subheading: subheadline/description
    - #logo: brand logo image (alt text contains brand name)
    - #img: hero/product image
    - #cta: call-to-action button text
    
    Returns: (count, list_of_screenshot_paths)
    """
    from bs4 import BeautifulSoup
    
    shots: List[str] = []
    cards_captured = 0
    
    try:
        # Check if page is closed
        if page.is_closed():
            if SL: SL.log("closed_guard_trip", where="gallery_cards_start")
            return 0, []
        
        # Find the gallery bottom container - try multiple selectors
        # Primary: data-testid="galleryBottom"
        # Fallback: id containing "zonebottom" (from DynamicAdContainer)
        container = page.locator(SELECTORS["gallery_cards"])
        container_found = container.count() > 0
        
        if not container_found:
            # Try fallback selector for zonebottom containers
            container = page.locator('[id*="zonebottom"]')
            container_found = container.count() > 0
            if container_found and SL:
                SL.log("gallery_cards_fallback_selector", selector='[id*="zonebottom"]')
        
        if not container_found:
            if SL: SL.log("gallery_cards_not_found")
            return 0, []
        
        # Find gallery card iframes — only match data-ad-type starting with "gallerybottom"
        # The broader zonebottom fallback was matching marquee banners and the site header,
        # causing misclassification. If no gallerybottom iframes exist, there are no gallery cards.
        iframe_selector = SELECTORS["gallery_card_iframe"]
        iframes = page.query_selector_all(iframe_selector)
        
        if SL: SL.log("gallery_cards_found", iframe_count=len(iframes))
        
        for idx, iframe_handle in enumerate(iframes, 1):
            try:
                # Get iframe attributes for logging and format detection
                data_ad_type = iframe_handle.get_attribute("data-ad-type") or f"gallerybottom{idx}"
                
                # Get bounding box to determine actual rendered dimensions
                try:
                    bbox = iframe_handle.bounding_box()
                    if bbox:
                        iframe_width = bbox.get("width", 0)
                        iframe_height = bbox.get("height", 0)
                        aspect_ratio = iframe_width / iframe_height if iframe_height > 0 else 1.0
                        # Wide banner: aspect ratio > 1.5 (e.g., 600x200 = 3.0)
                        # Square tile: aspect ratio ~1.0 (e.g., 300x300 = 1.0)
                        card_format = "banner" if aspect_ratio > 1.5 else "tile"
                    else:
                        iframe_width, iframe_height, card_format = 0, 0, "tile"
                except Exception:
                    iframe_width, iframe_height, card_format = 0, 0, "tile"
                
                # Get the content frame
                frame = iframe_handle.content_frame()
                if frame is None:
                    if SL: SL.log("gallery_card_no_frame", index=idx)
                    continue
                
                # Get the HTML content inside the iframe
                try:
                    card_html = frame.content()
                except Exception as e:
                    if SL: SL.log("gallery_card_content_error", index=idx, error=str(e))
                    continue
                
                if not card_html:
                    continue
                
                # Parse with BeautifulSoup
                soup = BeautifulSoup(card_html, "html.parser")
                
                # Extract brand from logo alt text
                # Patterns:
                #   "image of the logo for the brand [BRAND]" - new Walmart format
                #   "... of [brand name] logo" or "[brand name] logo" - older format
                advertiser = None
                logo_url = None
                logo_elem = soup.select_one("#logo")
                if logo_elem:
                    logo_url = logo_elem.get("src")
                    logo_alt = logo_elem.get("alt") or ""
                    alt_lower = logo_alt.lower()
                    
                    # First, try the new Walmart format: "image of the logo for the brand [BRAND]"
                    if "for the brand " in alt_lower:
                        # Extract everything after "for the brand "
                        advertiser = alt_lower.split("for the brand ")[-1].strip().title()
                        # Strip trailing "Brand" — Walmart sometimes includes it in the alt text
                        if advertiser.endswith(" Brand"):
                            advertiser = advertiser[:-6].strip()
                    elif " logo" in alt_lower:
                        # Fallback to older format: extract text before "logo"
                        # Examples: "cursive black font on white background of peach slices logo"
                        #           "Peach Slices logo"
                        before_logo = alt_lower.split(" logo")[0].strip()
                        # Try to get the brand name (last few words before "logo")
                        # Handle "of [brand]" pattern
                        if " of " in before_logo:
                            advertiser = before_logo.split(" of ")[-1].strip().title()
                        else:
                            # Just use the whole thing or last 2-3 words
                            words = before_logo.split()
                            if len(words) <= 3:
                                advertiser = " ".join(words).title()
                            else:
                                advertiser = " ".join(words[-3:]).title()
                    
                    # Try lexicon canonicalization if available
                    if advertiser and canonicalize_brand:
                        canonical = canonicalize_brand(advertiser)
                        if canonical:
                            advertiser = canonical
                
                # Fallback: try hero image alt text
                if not advertiser:
                    hero_img = soup.select_one("#img")
                    if hero_img:
                        hero_alt = hero_img.get("alt") or ""
                        if hero_alt and canonicalize_brand:
                            canonical = canonicalize_brand(hero_alt)
                            if canonical:
                                advertiser = canonical
                
                # Extract ad copy
                headline = None
                subheadline = None
                cta_text = None
                hero_image_url = None
                
                heading_elem = soup.select_one("#heading")
                if heading_elem:
                    headline = heading_elem.get_text(strip=True)
                
                subheading_elem = soup.select_one("#subheading")
                if subheading_elem:
                    subheadline = subheading_elem.get_text(strip=True)
                
                cta_elem = soup.select_one("#cta")
                if cta_elem:
                    cta_text = cta_elem.get_text(strip=True)
                
                hero_img_elem = soup.select_one("#img")
                if hero_img_elem:
                    hero_image_url = hero_img_elem.get("src")
                
                # Detect Walmart house ads (Walmart+ promotions)
                # These use descriptive alt text instead of brand patterns
                if not advertiser:
                    # Check logo alt text for walmart plus indicators
                    if logo_elem:
                        logo_alt_lower = (logo_elem.get("alt") or "").lower()
                        if "walmart plus" in logo_alt_lower or "walmart+" in logo_alt_lower:
                            advertiser = "Walmart"
                    
                    # Also check headline for walmart plus
                    if not advertiser and headline:
                        headline_lower = headline.lower()
                        if "walmart+" in headline_lower or "walmart plus" in headline_lower:
                            advertiser = "Walmart"
                
                if SL: SL.log("gallery_card_extracted", 
                             index=idx, 
                             advertiser=advertiser,
                             headline=headline[:50] if headline else None,
                             has_logo=bool(logo_url),
                             has_hero=bool(hero_image_url))
                
                # Fallback advertiser
                if not advertiser:
                    advertiser = "unknown"
                
                # Add new brand to lexicon if discovered
                if advertiser and advertiser != "unknown" and add_brand_to_lexicon:
                    if add_brand_to_lexicon(advertiser):
                        if SL: SL.log("gallery_card_brand_added_to_lexicon", brand=advertiser)
                
                # Scroll the iframe into view and take screenshot
                try:
                    # Use wheel-based scroll so PX sensor sees real mouse delta events.
                    # scroll_into_view_if_needed() + window.scrollBy() are JS calls — detectable.
                    _bring_into_view(page, iframe_handle, SL=SL)
                    time.sleep(random.uniform(0.25, 0.55))
                    # Fine-tune: if card top is too close to viewport top (behind sticky header),
                    # nudge down with wheel so the card sits ≥120px from viewport top.
                    _bb = iframe_handle.bounding_box()
                    if _bb is not None:
                        _current_y = _bb["y"]
                        _target_y = 120
                        if _current_y < _target_y:
                            # Need to scroll page UP (negative delta) to push element down
                            delta_px = _target_y - _current_y  # positive → need to scroll up
                            steps = max(2, int(delta_px / 40))
                            for _ in range(steps):
                                page.mouse.wheel(0, -int(delta_px / steps))
                                time.sleep(random.uniform(0.04, 0.10))
                except Exception:
                    pass
                
                # Generate filename and save screenshot
                if client_name and client_root and timestamp:
                    # Create Gallery_Cards folder
                    gallery_folder = os.path.join(client_root, "Gallery_Cards")
                    os.makedirs(gallery_folder, exist_ok=True)
                    
                    png_filename = generate_ad_filename(
                        retailer='walmart',
                        ad_type='gallery_card',
                        client=client_name,
                        search_term=keyword,
                        timestamp=timestamp,
                        index=idx,
                        extension='png',
                        advertiser=advertiser
                    )
                    out_path = os.path.join(gallery_folder, png_filename)
                else:
                    out_path = os.path.join(base_dir, safe_filename(f"{SLUG}_{keyword}_gallery_card_{idx}.png"))
                
                # Screenshot the content INSIDE the iframe (not the iframe element itself)
                # This captures the full ad creative without carousel CSS constraints
                try:
                    # Screenshot #tile (the actual card) not #tile-container (which has shadow padding)
                    # #tile-container adds extra margin/padding for box-shadow which creates white borders
                    tile_elem = frame.locator('#tile')
                    if tile_elem.count() > 0:
                        tile_elem.screenshot(path=out_path)
                    else:
                        # Fallback to tile-container if #tile not found
                        tile_container = frame.locator('#tile-container')
                        if tile_container.count() > 0:
                            tile_container.screenshot(path=out_path)
                        else:
                            # Final fallback to full iframe body
                            frame.locator('body').screenshot(path=out_path)
                except Exception as inner_screenshot_err:
                    # Final fallback: screenshot the iframe element from parent
                    if SL: SL.log("gallery_card_inner_screenshot_failed", index=idx, error=str(inner_screenshot_err))
                    iframe_handle.screenshot(path=out_path)
                shots.append(out_path)
                cards_captured += 1
                
                # Save iframe HTML for debugging/reference
                if base_dir:
                    try:
                        iframe_html_path = os.path.join(base_dir, f"gallery_card_{idx}_{run_id or 'debug'}.html")
                        with open(iframe_html_path, "w", encoding="utf-8") as f:
                            f.write(card_html)
                    except Exception:
                        pass
                
                # Build canonical ad object
                if run_id and ads_list is not None and client_root and client_name:
                    try:
                        client_root_path = Path(client_root)
                        saved_path = Path(out_path)
                        
                        # Get next ad index
                        ad_index = len(ads_list) + 1
                        
                        ad_obj = build_ad_object(
                            run_id=run_id,
                            ad_index=ad_index,
                            ad_type="Gallery_Cards",
                            client_root=client_root_path,
                            saved_path=saved_path,
                            brand_name=advertiser if advertiser != "unknown" else None,
                            ad_title=headline,
                            cta_text=cta_text,
                            destination_url=None,  # Could extract from click handler if needed
                            cdn_image_url=hero_image_url,
                            slot_index=idx - 1,  # 0-indexed
                        )
                        if ad_obj is None:
                            # Blacklisted brand - delete the saved image
                            try:
                                saved_path.unlink(missing_ok=True)
                            except Exception:
                                pass
                            continue
                        # Add extra fields specific to gallery cards
                        ad_obj["subheadline"] = subheadline
                        ad_obj["logo_url"] = logo_url
                        ad_obj["card_format"] = card_format  # "tile" or "banner"
                        ad_obj["dimensions"] = {"width": int(iframe_width), "height": int(iframe_height)}
                        
                        ads_list.append(ad_obj)
                        if SL: SL.log("gallery_card_ad_object", ad_id=ad_obj["id"], brand=advertiser, headline=headline[:30] if headline else None)
                    except Exception as e:
                        if SL: SL.log("gallery_card_ad_object_error", error=str(e), index=idx)
                
                # Store in metadata
                meta.setdefault("gallery_cards", []).append({
                    "index": idx,
                    "advertiser": advertiser,
                    "headline": headline,
                    "subheadline": subheadline,
                    "cta": cta_text,
                    "logo_url": logo_url,
                    "hero_image_url": hero_image_url,
                    "screenshot": out_path,
                    "card_format": card_format,  # "tile" or "banner"
                    "dimensions": {"width": int(iframe_width), "height": int(iframe_height)}
                })
                
                # Save brand logo if we have one
                if logo_url and advertiser and advertiser != "unknown" and BrandLogoDatabase:
                    try:
                        logo_db = BrandLogoDatabase()
                        logo_db.add_brand_logo(
                            brand=advertiser,
                            logo_url=logo_url,
                            retailer="walmart",
                            metadata={
                                "ad_type": "Gallery_Cards",
                                "keyword": keyword,
                                "timestamp": timestamp
                            }
                        )
                        if SL: SL.log("gallery_card_logo_saved", brand=advertiser)
                    except Exception:
                        pass
                
                time.sleep(random.uniform(0.15, 0.3))
                
            except Exception as e:
                if SL: SL.log("gallery_card_error", index=idx, error=str(e))
                continue
        
        return cards_captured, shots
        
    except Exception as e:
        if SL: SL.log("gallery_cards_exception", error=str(e))
        return 0, []


def _search_url(keyword: str) -> str:
    q = quote_plus(keyword)
    return f"https://www.walmart.com/search?q={q}"


RESULT_READY_SELECTORS = [
    '[data-item-id]',
    '[data-testid="list-view"]',
    'div[data-automation="search-result-gridview-items"]'
]

def _wait_for_search_results(page, timeout_ms=15000):
    """Wait until we're on /search AND result containers exist."""
    deadline = time.time() + timeout_ms/1000.0
    last = {}
    while time.time() < deadline:
        url = page.url
        on_search = ("/search?" in url or url.rstrip("/").endswith("/search"))
        found = False
        which = None
        for sel in RESULT_READY_SELECTORS:
            try:
                c = page.locator(sel).count()
                last[sel] = c
                if c > 0:
                    found = True
                    which = sel
                    break
            except:
                pass
        if on_search and found:
            return True, which
        time.sleep(0.2)
    return False, f"wait timed out; url={page.url} last={last}"

def _detect_block_signals(page) -> tuple:
    """
    Detect if Walmart has blocked or challenged us.
    Returns (is_blocked, reason)
    """
    try:
        content = page.content()
        
        # PerimeterX CAPTCHA
        if page.locator("#px-captcha").count() > 0 or "Robot or human?" in content:
            return True, "perimeterx_captcha"
        
        # Access denied / blocked
        if "access denied" in content.lower() or "blocked" in content.lower():
            return True, "access_denied"
        
        # Rate limit
        if "too many requests" in content.lower() or "rate limit" in content.lower():
            return True, "rate_limit"
        
        # Unusual activity
        if "unusual activity" in content.lower():
            return True, "unusual_activity"
        
        # Check for actual product results
        if page.locator('[data-testid="list-view"]').count() == 0 and \
           page.locator('[data-item-id]').count() == 0:
            # No products found - might be blocked
            if len(content) < 5000:  # Suspiciously small page
                return True, "empty_response"
        
        return False, ""
    except Exception as e:
        return False, f"detection_error: {e}"


# --- BEGIN: human scroll helpers ---

def _scroll_burst_wheel(page, lines=8):
    """Emit a small burst of native wheel events (human-like)."""
    for _ in range(lines):
        if not _within_scroll_budget(1):
            break
        page.mouse.wheel(0, random.randint(48, 140))  # mac trackpad-ish deltas
        time.sleep(random.uniform(0.045, 0.12))

def _scroll_like_human(page, say, bursts=2, lines_min=6, lines_max=12, pause_min=0.25, pause_max=0.9, SL=None):
    """Several short wheel bursts with pauses; solve PX if it appears mid-scroll."""
    # Close guard
    try:
        if page.is_closed():
            if SL: SL.log("closed_guard_trip", where="scroll_like_human_start")
            return
    except Exception:
        return

    if PX_HOLD_GUARD["in_progress"]:
        if SL: SL.log("scroll_blocked", reason="hold_in_progress")
        return
    ok, reason = _can_scroll_now(page, SL=SL)
    if not ok:
        if SL: SL.log("scroll_blocked", reason=reason, url=page.url)
        return

    # First scroll on results: keep it light
    local_bursts = bursts
    if not FIRST_SCROLL_DONE["done"]:
        local_bursts = min(local_bursts, 2)
        lines_min, lines_max = max(4, lines_min-2), max(6, min(8, lines_max))
        if SL: SL.log("first_scroll_start", bursts=local_bursts, lines_min=lines_min, lines_max=lines_max)

    for b in range(local_bursts):
        _scroll_burst_wheel(page, lines=random.randint(lines_min, lines_max))
        time.sleep(random.uniform(pause_min, pause_max))
        # If PX pops during scroll, solve with controller
        if _still_px_modal(page):
            if SL: SL.log("scroll_px_pop", burst=b+1)
            say("warn", "[Walmart] PX popped mid-scroll — solving")
            if not _solve_px_until_clear(page, say, SL=SL):
                say("error", "[Walmart] PX not cleared mid-scroll; aborting scroll")
                break
            # after solving, don't resume scrolling immediately
            _lock_scroll("px_recent")
            return

        if not FIRST_SCROLL_DONE["done"]:
            # Idle after very first burst to avoid "action storm"
            time.sleep(random.uniform(1.0, 2.2))
            FIRST_SCROLL_DONE["done"] = True
            FIRST_SCROLL_DONE["ts"] = time.time()
            if SL: SL.log("first_scroll_done", ts=FIRST_SCROLL_DONE["ts"])

def _tap_pagedown(page, SL=None):
    """Press PageDown key (varies input method)."""
    ok, reason = _can_scroll_now(page, SL=SL)
    if not ok:
        if SL: SL.log("scroll_blocked_pagedown", reason=reason)
        return
    page.keyboard.press("PageDown")
    time.sleep(random.uniform(0.25, 0.55))

def _bring_into_view(page, loc, SL=None, max_bursts=8):
    """Prefer native wheel to move viewport; fall back to scrollIntoView if needed."""
    # Close guard at start
    try:
        if page.is_closed():
            if SL: SL.log("closed_guard_trip", where="bring_into_view")
            return False
    except Exception:
        return False

    try:
        box = loc.bounding_box()
        if not box:
            return False
        viewport = page.viewport_size or {"width": 1366, "height": 768}
        center_y = viewport["height"] * 0.45
        # If already near center, do nothing
        if 0 < box["y"] < viewport["height"] and abs(box["y"] - center_y) < 200:
            return True
        # Use wheel bursts to approach the target
        bursts = 0
        while bursts < max_bursts:
            direction = 1 if box["y"] > center_y else -1
            for _ in range(random.randint(4, 8)):
                page.mouse.wheel(0, direction * random.randint(48, 140))
                time.sleep(random.uniform(0.045, 0.11))
            bursts += 1
            box = loc.bounding_box() or box
            if 0 < box["y"] < viewport["height"] and abs(box["y"] - center_y) < 220:
                return True
        # Fallback (only if we failed to bring it close with wheel)
        loc.scroll_into_view_if_needed()
        time.sleep(0.2)
        return True
    except Exception as e:
        if SL: SL.log("bring_into_view_error", err=str(e))
        return False

# --- END: human scroll helpers ---

# --- BEGIN: human typing and micro-movement helpers ---
def human_type(element, text: str, page=None):
    """Type with human-like delays using real keyboard events.

    IMPORTANT: must use page.keyboard.press() (not element.type()).
    element.type() fires only synthetic InputEvent — PX's sensor detects the
    missing KeyDown/KeyPress/KeyUp chain. page.keyboard.press() dispatches the
    full event sequence, indistinguishable from a real keypress.

    If page is not supplied, falls back to element.type() (cold-start paths
    that don't go through the search bar, where PX is not a concern).
    """
    for ch in text:
        if page is not None:
            page.keyboard.type(ch)  # real KeyDown+KeyPress+KeyUp events
        else:
            element.type(ch, delay=0)  # fallback: synthetic only (avoid if PX-sensitive)
        time.sleep(random.uniform(0.08, 0.22))
        if random.random() < 0.10:
            time.sleep(random.uniform(0.05, 0.15))
    if len(text) >= 10 and random.random() < 0.6:
        time.sleep(random.uniform(0.20, 0.45))


def micro_mouse_attention(page, around=(8, 15), jitter=10):
    """Subtle mouse micro-movements to simulate attention."""
    try:
        pos = page.mouse.position
        mx, my = pos['x'], pos['y']
    except Exception:
        mx, my = (random.randint(300, 700), random.randint(300, 600))
    steps = random.randint(*around)
    for i in range(steps):
        dx = random.randint(-jitter, jitter)
        dy = random.randint(-jitter, jitter)
        mx += dx
        my += dy
        page.mouse.move(mx, my)
        time.sleep(random.uniform(0.01, 0.03))


def random_delay(a=0.6, b=1.4):
    """Random delay between actions."""
    time.sleep(random.uniform(a, b))


def _bezier_mouse_move(page, from_x: float, from_y: float, to_x: float, to_y: float,
                       duration_ms: int = None, steps: int = None):
    """
    Move mouse along a cubic bezier curve with natural easing.

    Real mouse movements follow curved paths with ease-in/ease-out speed.
    page.mouse.move(steps=N) uses linear interpolation — PX sensor can detect
    this as non-human. This function generates natural-looking trajectories.
    """
    dist = ((to_x - from_x) ** 2 + (to_y - from_y) ** 2) ** 0.5
    if steps is None:
        steps = max(25, min(100, int(dist / 7)))
    if duration_ms is None:
        # Natural speed: ~400-900px/sec with fixed overhead
        duration_ms = int(180 + dist * random.uniform(0.5, 1.1))

    dx = to_x - from_x
    dy = to_y - from_y
    length = max(dist, 1.0)

    # Perpendicular unit vector for wobble
    perp_x = -dy / length
    perp_y = dx / length
    wobble = dist * random.uniform(0.04, 0.12)
    side = random.choice([-1, 1])

    cp1_x = from_x + dx * 0.3 + perp_x * wobble * side
    cp1_y = from_y + dy * 0.3 + perp_y * wobble * side
    cp2_x = from_x + dx * 0.7 + perp_x * wobble * side * random.uniform(0.5, 1.5)
    cp2_y = from_y + dy * 0.7 + perp_y * wobble * side * random.uniform(0.5, 1.5)

    def _bez(t):
        u = 1 - t
        x = u**3*from_x + 3*u**2*t*cp1_x + 3*u*t**2*cp2_x + t**3*to_x
        y = u**3*from_y + 3*u**2*t*cp1_y + 3*u*t**2*cp2_y + t**3*to_y
        return x, y

    def _ease(t):
        return t * t * (3 - 2 * t)  # cubic smoothstep

    step_base_ms = duration_ms / max(steps, 1)
    for i in range(steps + 1):
        t_lin = i / max(steps, 1)
        x, y = _bez(_ease(t_lin))
        try:
            page.mouse.move(x, y)
        except Exception:
            return
        if i < steps:
            # Bell-curve: faster in the middle, slower at start/end
            bell = 1.0 + 0.6 * (1 - (2 * t_lin - 1) ** 2)
            time.sleep(max(0.001, step_base_ms / 1000.0 / bell + random.uniform(-0.002, 0.002)))


def _homepage_warmup(page, SL=None):
    """
    Natural mouse warm-up after homepage load.

    A real user who just loaded the page glances at the nav and content
    before deciding to search. PX builds a trust score during this window —
    movement quality and duration both matter.
    """
    start_x = random.uniform(380, 820)
    start_y = random.uniform(180, 380)
    try:
        page.mouse.move(start_x, start_y)
    except Exception:
        time.sleep(random.uniform(1.5, 2.5))
        return

    time.sleep(random.uniform(0.9, 1.6))  # initial "page loaded, reading" pause

    # Move toward nav bar (orientation behavior)
    nav_x = random.uniform(180, 680)
    nav_y = random.uniform(52, 78)
    _bezier_mouse_move(page, start_x, start_y, nav_x, nav_y,
                       duration_ms=random.randint(380, 680))
    time.sleep(random.uniform(0.25, 0.60))

    # Maybe drift to a second nav point (65% chance)
    cur_x, cur_y = nav_x, nav_y
    if random.random() < 0.65:
        nav2_x = nav_x + random.uniform(-220, 220)
        nav2_y = nav_y + random.uniform(-8, 12)
        _bezier_mouse_move(page, cur_x, cur_y, nav2_x, nav2_y,
                           duration_ms=random.randint(220, 440))
        time.sleep(random.uniform(0.18, 0.45))
        cur_x, cur_y = nav2_x, nav2_y

    # Glance down at hero/featured content area
    content_x = random.uniform(280, 920)
    content_y = random.uniform(190, 340)
    _bezier_mouse_move(page, cur_x, cur_y, content_x, content_y,
                       duration_ms=random.randint(320, 580))
    time.sleep(random.uniform(0.45, 1.10))

    if SL:
        SL.log("homepage_warmup_done")


def _wait_results_stable(page, timeout_ms=4000, still_ms=350):
    """Wait for results count to stabilize (avoid acting on mid-render DOM)."""
    t0 = time.time()
    dead = t0 + timeout_ms/1000.0
    last_count, stable_start = None, None
    while time.time() < dead:
        try:
            c = page.locator('[data-item-id]').count()
        except Exception:
            c = 0
        if c > 0 and c == last_count:
            if stable_start is None:
                stable_start = time.time()
            if (time.time() - stable_start)*1000 >= still_ms:
                return True
        else:
            stable_start = None
        last_count = c
        time.sleep(0.1)
    return False


def _drift_reading(page, seconds=2.0):
    """Subtle mouse drift to simulate reading/scanning."""
    end = time.time() + seconds
    try:
        pos = page.mouse.position
        x, y = pos['x'], pos['y']
    except Exception:
        x, y = (random.randint(300, 700), random.randint(300, 600))
    
    while time.time() < end:
        x += random.randint(-15, 15)
        y += random.randint(-10, 12)
        try:
            page.mouse.move(x, y, steps=random.randint(2, 5))
        except Exception:
            break
        time.sleep(random.uniform(0.12, 0.35))


def _backscroll_peek(page):
    """Occasional back-scroll peek (35% chance)."""
    if random.random() < 0.35:
        try:
            page.mouse.wheel(0, -random.randint(120, 320))
            time.sleep(random.uniform(0.4, 0.9))
        except Exception:
            pass
# --- END: human typing and micro-movement helpers ---

# --- BEGIN: PX modal solver v4 (steady-only, no jitter) ---

# PX hold guard – prevents any other action while we're holding
PX_HOLD_GUARD = {"in_progress": False}

# --- BEGIN: scroll/nav gates ---
SCROLL_LOCK = {"unlocked": False, "why": "init"}
LAST_NAV_DONE_TS = {"t": 0.0}
LAST_PX_CLEAR_TS = {"t": 0.0}

# --- BEGIN: scroll pacing ---
SCROLL_BUDGET = {"win_start": 0.0, "events": 0}
FIRST_SCROLL_DONE = {"done": False, "ts": 0.0}

def _reset_scroll_budget():
    SCROLL_BUDGET["win_start"] = time.time()
    SCROLL_BUDGET["events"] = 0

def _within_scroll_budget(delta_events=1, max_events_per_10s=40):
    # ~4 events/sec average cap
    now = time.time()
    if now - SCROLL_BUDGET["win_start"] > 10.0:
        _reset_scroll_budget()
    SCROLL_BUDGET["events"] += delta_events
    return SCROLL_BUDGET["events"] <= max_events_per_10s
# --- END: scroll pacing ---

def _lock_scroll(why="lock"):
    SCROLL_LOCK["unlocked"] = False
    SCROLL_LOCK["why"] = why

def _unlock_scroll(why="unlock", SL=None):
    SCROLL_LOCK["unlocked"] = True
    SCROLL_LOCK["why"] = why
    if SL: SL.log("scroll_unlocked", why=why)

def _nav_mark_done(SL=None):
    LAST_NAV_DONE_TS["t"] = time.time()
    if SL: SL.log("nav_done", ts=LAST_NAV_DONE_TS["t"])

def _mark_px_cleared(SL=None):
    LAST_PX_CLEAR_TS["t"] = time.time()
    if SL: SL.log("px_cleared_ts", ts=LAST_PX_CLEAR_TS["t"])

def _can_scroll_now(page, SL=None, px_cooldown=3.7) -> Tuple[bool, str]:
    if not SCROLL_LOCK["unlocked"]:
        return False, f"locked:{SCROLL_LOCK['why']}"
    if _still_px_modal(page):
        return False, "px_visible"
    if time.time() - LAST_NAV_DONE_TS["t"] < 0.8:
        return False, "nav_recent"
    if time.time() - LAST_PX_CLEAR_TS["t"] < px_cooldown:
        return False, "px_recent"
    # require at least one result container to exist
    for sel in RESULT_READY_SELECTORS:
        try:
            if page.locator(sel).count() > 0:
                return True, "ok"
        except:
            pass
    return False, "no_results_dom"
# --- END: scroll/nav gates ---

def _wait_visible_hc_iframe(page, timeout_ms=12000, stable_ms=700):
    """
    Wait for the PX iframe (title='Human verification challenge') to be visible AND stable.
    Returns (element, box, time_to_ready_seconds) or (None, None, t) on timeout.
    """
    t0 = time.time()
    deadline = t0 + timeout_ms/1000.0
    last_box = None
    stable_start = None

    while time.time() < deadline:
        loc = page.locator('iframe[title="Human verification challenge"]')
        try:
            n = loc.count()
        except Exception:
            n = 0

        el = None
        box = None
        for i in range(n):
            f = loc.nth(i)
            try:
                b = f.bounding_box()
                if b and b.get("width", 0) > 120 and b.get("height", 0) > 60:
                    el, box = f, b
                    break
            except Exception:
                continue

        if not el:
            host = page.locator('#px-captcha')
            if host.count() > 0:
                try:
                    b = host.bounding_box()
                    if b and b.get("width", 0) > 120 and b.get("height", 0) > 60:
                        el, box = host, b
                except Exception:
                    pass

        if el and box:
            # stability check – the box shouldn't move for ~stable_ms
            if last_box and abs(last_box["x"]-box["x"]) < 1 and abs(last_box["y"]-box["y"]) < 1 \
               and abs(last_box["width"]-box["width"]) < 1 and abs(last_box["height"]-box["height"]) < 1:
                if stable_start is None:
                    stable_start = time.time()
                if (time.time()-stable_start)*1000 >= stable_ms:
                    return el, box, time.time()-t0
            else:
                last_box = box
                stable_start = None

        time.sleep(0.08)

    return None, None, time.time()-t0

def _wait_px_cookie(ctx, timeout_ms=8000):
    """Wait for PX cookies to appear."""
    deadline = time.time() + timeout_ms/1000.0
    last = []
    while time.time() < deadline:
        try:
            cookies = ctx.cookies("https://www.walmart.com/")
            names = sorted(set(c["name"].lower() for c in cookies))
            last = names
            if any(n in names for n in ["_px3", "_pxvid"]):
                return True, names
        except Exception:
            pass
        time.sleep(0.2)
    return False, last

_FORCE_BLOCK_ONCE_STATE = {"armed": os.environ.get("WALMART_FORCE_BLOCK_ONCE_FOR_TEST", "0") == "1"}
_FORCED_TEST_MODE = os.environ.get("WALMART_FORCE_BLOCK_ONCE_FOR_TEST", "0") == "1"

def _on_blocked(url: str) -> bool:
    """Check if URL is the /blocked route. Optional one-shot force for deterministic validation."""
    if _FORCE_BLOCK_ONCE_STATE["armed"]:
        _FORCE_BLOCK_ONCE_STATE["armed"] = False
        return True
    return "walmart.com/blocked" in (url or "").lower()


def _wait_for_search_transition(page, timeout_ms=20000):
    """
    Wait for any of:
      - URL contains '/search' (supports pushState, no navigation event)
      - Results DOM appears (any selector in RESULT_READY_SELECTORS)
    Returns: 'url' | 'dom' | None
    """
    deadline = time.time() + timeout_ms/1000.0
    while time.time() < deadline:
        try:
            if re.search(r"/search(?:\?|$)", page.url):
                return "url"
        except Exception:
            pass
        for sel in RESULT_READY_SELECTORS:
            try:
                if page.locator(sel).count() > 0:
                    return "dom"
            except Exception:
                pass
        time.sleep(0.2)
    return None


def eval_safe(page, script, label, SL=None):
    """
    Safe page.evaluate wrapper that logs errors instead of crashing.
    Prevents "Page.evaluate:" fatal errors when page is redirecting/blocked.
    """
    try:
        return page.evaluate(script)
    except Exception as e:
        if SL:
            SL.log("eval_error", label=label, url=page.url, error=str(e))
        return None

def _decoded_target_from_blocked(url: str):
    """Extract and decode redirect target from blocked URL."""
    try:
        u = urlparse(url)
        raw = parse_qs(u.query).get("url", [""])[0]
        if not raw:
            return None
        try:
            dec = base64.b64decode(raw).decode("utf-8", "ignore")
        except Exception:
            dec = raw
        if dec.startswith("/"):
            return "https://www.walmart.com" + dec
        if dec.startswith("http"):
            return dec
        return "https://www.walmart.com/"
    except Exception:
        return None

def _force_redirect_off_blocked(page, SL=None) -> bool:
    """Multi-try redirect off /blocked route."""
    if not _on_blocked(page.url):
        return True
    
    tgt = _decoded_target_from_blocked(page.url) or "https://www.walmart.com/"
    
    # Try 1: normal goto
    if SL: SL.log("px_redirect_attempt", how="goto", target=tgt)
    try:
        page.goto(tgt, wait_until="domcontentloaded")
        time.sleep(1.0)
        if not _on_blocked(page.url):
            return True
    except Exception:
        pass
    
    # Try 2: JS location.assign
    if SL: SL.log("px_redirect_attempt", how="location.assign", target=tgt)
    try:
        page.evaluate("(u)=>window.location.assign(u)", tgt)
        page.wait_for_load_state("domcontentloaded", timeout=10000)
        time.sleep(1.0)
        if not _on_blocked(page.url):
            return True
    except Exception:
        pass
    
    # Try 3: JS location.replace (no history)
    if SL: SL.log("px_redirect_attempt", how="location.replace", target=tgt)
    try:
        page.evaluate("(u)=>window.location.replace(u)", tgt)
        page.wait_for_load_state("domcontentloaded", timeout=10000)
        time.sleep(1.0)
        if not _on_blocked(page.url):
            return True
    except Exception:
        pass
    
    # Try 4: cache-busted goto
    bust = tgt + ("&" if "?" in tgt else "?") + f"pxr={int(time.time()*1000)}"
    if SL: SL.log("px_redirect_attempt", how="goto_bust", target=bust)
    try:
        page.goto(bust, wait_until="domcontentloaded")
        time.sleep(1.0)
        if not _on_blocked(page.url):
            return True
    except Exception:
        pass
    
    if SL: SL.log("px_redirect_failed", url=page.url)
    return False

def _log_px_trip(SL, reason: str):
    """Log PX detection with stack trace for debugging."""
    try:
        # Get stack trace
        stack = inspect.stack()
        # Skip this function and the caller (_still_px_modal)
        relevant_stack = stack[2:5]  # Get 3 levels up

        stack_info = []
        for frame_info in relevant_stack:
            filename = os.path.basename(frame_info.filename)
            line_num = frame_info.lineno
            func_name = frame_info.function
            code_line = frame_info.code_context[0].strip() if frame_info.code_context else ""
            stack_info.append({
                "file": filename,
                "line": line_num,
                "func": func_name,
                "code": code_line
            })

        if SL:
            SL.log("px_trip", reason=reason, stack=stack_info)

        # Break into debugger if DEBUG.break_on_px is set
        if DEBUG.break_on_px:
            print(f"\n🔴 PX DETECTED: {reason}")
            print("Stack trace:")
            for i, frame in enumerate(stack_info):
                print(f"  {i+1}. {frame['file']}:{frame['line']} in {frame['func']}")
                if frame['code']:
                    print(f"     {frame['code']}")
            print("\n🔍 BREAKING INTO DEBUGGER - Type 'c' to continue, 'q' to quit")
            pdb.set_trace()

    except Exception as e:
        if SL:
            SL.log("px_trip_error", error=str(e), reason=reason)

def _press_and_hold_until_complete(page, say, SL=None):
    """
    Human-like press-and-hold on the PX captcha widget.

    What a real human does:
      1. Moves cursor naturally (curved Bezier path) to inside the button
      2. Presses and holds — no preliminary separate click
      3. Holds until progress bar fills / modal vanishes (not a fixed timer)
      4. Has tiny hand tremor (~1-3px micro-drift) during the hold
      5. Releases after seeing completion

    Previous version tells that PX scored negatively:
      - 10-step straight-line mouse.move() (not Bezier)
      - Separate click() before down() (unnatural — humans just press and hold)
      - Perfectly static cursor for 7-10s (no human hand is that still)
      - Fixed timer instead of watching for completion signal
    """
    PX_HOLD_GUARD["in_progress"] = True

    # Setup PX beacon detection before hold
    px_beacon_seen = {"ok": False}
    def _on_response(res):
        try:
            if "px-cloud.net" in res.url.lower():
                px_beacon_seen["ok"] = True
                if SL: SL.log("px_beacon_detected", url=res.url)
        except:
            pass
    page.on("response", _on_response)

    try:
        el, box, t_ready = _wait_visible_hc_iframe(page, timeout_ms=12000, stable_ms=700)
        if SL:
            SL.log("px_widget_ready", t_ready=round(t_ready,2),
                   box=None if not box else {k: round(box[k],1) for k in ("x","y","width","height")})
        if not el or not box:
            say("warn", "[Walmart] PX widget not ready in time")
            return False

        # Randomized target inside button — humans don't always hit the exact same spot
        x_frac = random.uniform(0.22, 0.42)
        y_frac = random.uniform(0.35, 0.65)
        x = box["x"] + box["width"] * x_frac
        y = box["y"] + box["height"] * y_frac

        # Bezier approach from current position — natural curved path, same as rest of scraper
        try:
            cur = page.mouse.position
            _bezier_mouse_move(page, cur["x"], cur["y"], x, y,
                               duration_ms=random.randint(420, 780))
        except Exception:
            if SL: SL.log("px_hold_bail", reason="page_closed_on_approach")
            return False

        # Brief pause after arriving — human reads/sees the button before pressing
        time.sleep(random.uniform(0.18, 0.40))

        if SL: SL.log("px_hold_plan", x=round(x,1), y=round(y,1),
                      x_frac=round(x_frac,2), y_frac=round(y_frac,2))
        say("info", f"[Walmart] PX hold starting (widget ready in {t_ready:.2f}s)")

        # Press and hold — watch for completion signal, don't use a fixed timer.
        # Max cap of 18s prevents infinite hold if completion never fires.
        HOLD_MAX = 18.0
        drift_interval = random.uniform(0.8, 1.6)  # seconds between micro-movements

        try:
            page.mouse.down()
        except Exception:
            if SL: SL.log("px_hold_bail", reason="page_closed_on_down")
            return False

        hold_start = time.time()
        last_drift = hold_start
        completed = False

        while time.time() - hold_start < HOLD_MAX:
            elapsed = time.time() - hold_start

            # Completion signal 1: PX beacon fired
            if px_beacon_seen["ok"]:
                if SL: SL.log("px_completion_beacon", elapsed=round(elapsed,2))
                completed = True
                break

            # Completion signal 2: modal DOM elements gone
            try:
                modal_gone = (
                    page.locator("#px-captcha").count() == 0 and
                    page.locator('iframe[title="Human verification challenge"]').count() == 0 and
                    "Robot or human?" not in (page.content() or "")
                )
                if modal_gone and elapsed > 2.0:
                    if SL: SL.log("px_completion_modal_gone", elapsed=round(elapsed,2))
                    completed = True
                    break
            except Exception:
                pass

            # Micro hand tremor — very small random drift while holding.
            # A real human hand is never perfectly static for 10+ seconds;
            # a completely frozen cursor during a mouse-down is a bot signal.
            now = time.time()
            if now - last_drift >= drift_interval:
                try:
                    dx = random.uniform(-2.5, 2.5)
                    dy = random.uniform(-1.5, 1.5)
                    page.mouse.move(x + dx, y + dy)
                    drift_interval = random.uniform(0.7, 1.8)
                    last_drift = now
                except Exception:
                    pass

            time.sleep(0.10)

        try:
            page.mouse.up()
        except Exception:
            pass

        if not completed:
            if SL: SL.log("px_hold_timeout", held=round(time.time()-hold_start,2))
        time.sleep(random.uniform(1.4, 2.2))

        # If beacon/DOM check didn't confirm completion during hold, wait a bit more
        if not completed:
            t0 = time.time()
            if SL: SL.log("px_auto_wait_start", timeout=4.0)
            while time.time() - t0 < 4.0:
                if px_beacon_seen["ok"]:
                    completed = True
                    if SL: SL.log("px_auto_ok", reason="beacon_seen")
                    break
                if page.locator("#px-captcha").count() == 0 and \
                   page.locator('iframe[title="Human verification challenge"]').count() == 0 and \
                   "Robot or human?" not in (page.content() or ""):
                    completed = True
                    if SL: SL.log("px_auto_ok", reason="modal_vanished")
                    break
                time.sleep(0.15)
            if SL and not completed:
                SL.log("px_auto_wait_timeout", waited=round(time.time()-t0,2))

        # Gentle fallback only if auto-transition failed
        if not completed:
            if SL: SL.log("px_fallback_start")
            if _on_blocked(page.url):
                if SL: SL.log("px_fallback", action="goto_home")
                try:
                    page.goto("https://www.walmart.com/", wait_until="domcontentloaded")
                    time.sleep(random.uniform(1.2, 2.0))
                except Exception as e:
                    if SL: SL.log("px_fallback_error", error=str(e))
            else:
                if SL: SL.log("px_fallback", action="soft_reload")
                try:
                    page.reload(wait_until="domcontentloaded")
                    time.sleep(random.uniform(0.8, 1.4))
                except Exception as e:
                    if SL: SL.log("px_fallback_error", error=str(e))

        # Cookie check and cleared calculation AFTER wait/recovery
        has_px, names = _wait_px_cookie(page.context, timeout_ms=8000)
        cleared = has_px and not _still_px_modal(page)

        _mark_px_cleared(SL=SL)
        if SL: SL.log("px_hold_done", cookies_present=has_px, cookie_names=names[:6],
                     cleared=cleared, url=page.url, auto_ok=completed)
        say("info", f"[Walmart] cookies:{has_px} cleared:{cleared} names:{names[:8]}")
        return cleared
    finally:
        PX_HOLD_GUARD["in_progress"] = False
# --- END: PX modal solver ---

# --- BEGIN: PX multi-prompt controller ---
MAX_PX_SOLVES_PER_RUN = 3            # hard cap per run
PX_SOLVE_COOLDOWN_RANGE = (12, 25)   # seconds; backoff before trying again

def _still_px_modal(page) -> bool:
    """Check if PX modal is still present; on first visible transition, log px_trip."""
    # Static memory to avoid spamming on every call
    if not hasattr(_still_px_modal, "_prev"): _still_px_modal._prev = False
    try:
        now = page.locator('#px-captcha').count() > 0 or \
              page.locator('iframe[title="Human verification challenge"]').count() > 0 or \
              page.locator('text=Robot or human?').count() > 0
        if now and not _still_px_modal._prev:
            _log_px_trip(CURRENT_SL, "modal_visible_first")
        _still_px_modal._prev = now
        return now
    except Exception:
        return False

def _px_try_again_text(page) -> bool:
    """Check for 'Please try again' message."""
    try:
        if page.locator('text=/Please try again/i').count() > 0:
            return True
        if page.locator('p[role="alert"]:has-text("Please try again")').count() > 0:
            return True
    except:
        pass
    return False

def _px_widget_signature(page):
    """Get widget position/size signature."""
    el, box, _ = _wait_visible_hc_iframe(page, timeout_ms=2000, stable_ms=300)
    if not el or not box:
        return None
    return (round(box["x"]), round(box["y"]), round(box["width"]), round(box["height"]))

def _solve_px_until_clear(page, say, SL=None, immediate_retries=3, max_cycles=3, cooldown_range=(10, 18)):
    """Immediate retries for same widget, cooldown for new prompts."""
    cycles = 0
    while _still_px_modal(page) and cycles < max_cycles:
        cycles += 1
        same_sig = _px_widget_signature(page)
        
        for r in range(1, immediate_retries + 1):
            if SL: SL.log("px_try", cycle=cycles, try_num=r)
            say("warn", f"[Walmart] PX try {r}/{immediate_retries} (cycle {cycles}) — steady hold")
            ok = _press_and_hold_until_complete(page, say, SL=SL)
            time.sleep(random.uniform(1.0, 1.6))
            cleared = ok and not _still_px_modal(page)
            if SL: SL.log("px_result_try", cycle=cycles, try_num=r, ok=ok, cleared=cleared)
            if cleared:
                # Health check: ensure we're not stuck on /blocked even though cookies exist
                if _on_blocked(page.url):
                    say("warn", "[Walmart] Still on /blocked after cookies; forcing redirect")
                    if SL: SL.log("px_health_check", stuck_on_blocked=True)
                    _force_redirect_off_blocked(page, SL=SL)
                time.sleep(random.uniform(2.5, 4.5))
                return True
            
            # Retry immediately if same widget OR explicit 'Please try again'
            new_sig = _px_widget_signature(page)
            retry_now = (_still_px_modal(page) and new_sig == same_sig) or _px_try_again_text(page)
            if SL: SL.log("px_retry_policy", cycle=cycles, try_num=r, 
                         policy=("immediate" if retry_now else "cooldown"))
            if retry_now:
                continue
            break  # new widget or no widget → exit immediate loop
        
        if not _still_px_modal(page):
            return True
        
        cd = random.uniform(*cooldown_range)
        if SL: SL.log("px_cooldown", seconds=round(cd,1))
        say("warn", f"[Walmart] PX still not cleared — cooling down {cd:.1f}s")
        time.sleep(cd)
    return not _still_px_modal(page)
# --- END: PX multi-prompt controller ---

# --- BEGIN: PX press-and-hold solver (sync) - DEPRECATED ---
def _find_px_frame_sync(*args, **kwargs):
    """DEPRECATED: Do not use."""
    raise RuntimeError("Deprecated solver path: do not call.")

def _press_and_hold_sync(*args, **kwargs):
    """DEPRECATED: Do not use. Use _press_and_hold_until_complete instead."""
    raise RuntimeError("Deprecated solver path with jitter: do not call. Use _press_and_hold_until_complete.")
# --- END: PX press-and-hold solver (sync) - DEPRECATED ---

def _clear_bot_detection_cookies(ctx, SL=None) -> int:
    """
    Surgically remove Akamai/PX bot-detection cookies while preserving auth cookies.

    These cookies carry an encrypted reputation score. When a session has been
    flagged as bot-like, the score embedded in abck/bm_sz causes future requests
    to be pre-challenged. Clearing them forces Walmart to issue a fresh score on
    the next page load — without discarding the login session.

    Returns the number of bot-detection cookies removed.
    """
    BOT_COOKIE_NAMES = {"abck", "_abck", "bm_sz", "bm_sv", "bm_mi", "ak_bmsc", "adblocked"}
    try:
        all_cookies = ctx.cookies()
        bot_cookies = [c for c in all_cookies if c["name"].lower() in BOT_COOKIE_NAMES]
        if not bot_cookies:
            return 0
        auth_cookies = [c for c in all_cookies if c["name"].lower() not in BOT_COOKIE_NAMES]
        ctx.clear_cookies()
        if auth_cookies:
            try:
                ctx.add_cookies(auth_cookies)
            except Exception:
                pass
        cleared_names = [c["name"] for c in bot_cookies]
        if SL:
            SL.log("bot_cookies_cleared", cleared=cleared_names, preserved=len(auth_cookies))
        print(f"[cookies] 🧹 Cleared {len(bot_cookies)} bot-detection cookies: {cleared_names}")
        print(f"[cookies] Preserved {len(auth_cookies)} auth/session cookies")
        return len(bot_cookies)
    except Exception as e:
        if SL:
            SL.log("bot_cookies_clear_error", error=str(e))
        return 0


def _should_refresh_cookies(profile_dir: Optional[str]) -> bool:
    """Check if cookies should be refreshed (every 24 hours)."""
    if not profile_dir:
        return False
    
    cookie_marker = os.path.join(profile_dir, '.cookie_refresh_time')
    if not os.path.exists(cookie_marker):
        return True
    
    try:
        with open(cookie_marker, 'r') as f:
            last_refresh = float(f.read().strip())
        # Refresh if older than 24 hours
        return (time.time() - last_refresh) > 86400
    except:
        return True


def _mark_cookies_refreshed(profile_dir: Optional[str]):
    """Mark cookies as refreshed."""
    if not profile_dir:
        return
    
    cookie_marker = os.path.join(profile_dir, '.cookie_refresh_time')
    with open(cookie_marker, 'w') as f:
        f.write(str(time.time()))


def _abs(path: str) -> str:
    """Get absolute path, expanding user home (~)."""
    return os.path.abspath(os.path.expanduser(path or ""))


def _goto_home(page, SL, timeout_dom_ms=30000):
    """Resilient homepage navigation with commit → selector fallback."""
    url = "https://www.walmart.com/"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_dom_ms)
        if SL:
            SL.log("home_goto_phase", phase="domcontentloaded")
        return "domcontentloaded"
    except Exception as e:
        if SL:
            SL.log("home_goto_timeout", err=str(e))
        # Forensics on timeout
        try:
            _dump_html_png(page, SL.base_dir if hasattr(SL, "base_dir") else "/tmp", f"{SLUG}_home_timeout")
        except Exception:
            pass
        # Fallback: commit + wait for search box (visual readiness)
        try:
            page.goto(url, wait_until="commit", timeout=15000)
            page.wait_for_selector('input[aria-label="Search"]', timeout=15000)
            if SL:
                SL.log("home_goto_phase", phase="commit+search")
            return "commit+search"
        except Exception as e2:
            if SL:
                SL.log("home_goto_phase", phase="commit+networkidle", err=str(e2))
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            return "networkidle"

def _verify_writable_dir(path: str, create: bool = True) -> str:
    """Ensure path exists and is writable. Returns absolute path; raises on failure."""
    p = _abs(path)
    if create:
        os.makedirs(p, exist_ok=True)
    # write test
    try:
        test_path = os.path.join(p, f".perm{int(time.time()*1000)}")
        with open(test_path, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(test_path)
    except OSError as e:
        raise RuntimeError(f"Directory not writable: {p} ({e})")
    return p

# ---------------------------------------------------------------------------
# Opensteer warm-session recovery
# ---------------------------------------------------------------------------

_OPENSTEER_WARM_ENABLED  = os.environ.get("ENABLE_OPENSTEER_WARM_RECOVERY",   "1") == "1"
_OPENSTEER_ATTACH_MODE   = os.environ.get("WALMART_OPENSTEER_ATTACH_MODE",     "0") == "1"

_CHROME_BINARY_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta",
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
]


def _find_chrome_binary() -> str:
    override = os.environ.get("CHROME_BINARY")
    if override and os.path.exists(override):
        return override
    for p in _CHROME_BINARY_CANDIDATES:
        if os.path.exists(p):
            return p
    raise RuntimeError(
        "Chrome binary not found. Install Chrome or set CHROME_BINARY env var."
    )


def _find_free_port(start: int = 9222) -> int:
    for port in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("localhost", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free TCP port found in range {start}–{start + 19}")


def _clone_profile_minimal(src_user_data_dir: str, dst_dir: str, profile: str = "Default") -> str:
    """
    Copy only cookie-critical files from a Chrome profile into dst_dir.
    Much faster than a full clone and avoids lock conflicts with the running
    Playwright context (which holds the real profile's SQLite lock).
    Returns the path to the cloned user-data dir.
    """
    src = os.path.join(src_user_data_dir, profile)
    dst_profile = os.path.join(dst_dir, profile)
    os.makedirs(dst_profile, exist_ok=True)

    file_targets = [
        "Cookies",
        "Network Persistent State",
        "Preferences",
        "Secure Preferences",
    ]
    dir_targets = [
        "Local Storage",
        "Session Storage",
    ]
    for name in file_targets:
        s = os.path.join(src, name)
        if os.path.isfile(s):
            shutil.copy2(s, os.path.join(dst_profile, name))
    for name in dir_targets:
        s = os.path.join(src, name)
        d = os.path.join(dst_profile, name)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)

    return dst_dir


def _opensteer_warm_session(
    profile_dir: str,
    target_url: str,
    run_id: str,
    say: Optional[Callable] = None,
    SL=None,
) -> dict:
    """
    Launch a headed Chrome browser pre-seeded with the scraper profile.
    Block via tkinter dialog until the user signals results are visible.
    Return cookies + localStorage to inject into the existing Playwright context.

    Attach mode (WALMART_OPENSTEER_ATTACH_MODE=1 — default off):
      Launches a clean Chrome binary (no automation flags) on a free CDP port,
      then attaches opensteer to it. This removes the --disable-blink-features
      banner that Akamai scores negatively. Falls back to direct mode on any error.

    Direct mode (default):
      Uses opensteer browser clone + opensteer open. Simpler but Chrome shows
      the AutomationControlled warning banner.

    profile_dir is the Chrome user-data root (same as WALMART_PROFILE_DIR).
    """
    WS = f"walmart-warm-{run_id}"
    _say = say or (lambda kind, msg: print(f"[opensteer/{kind}] {msg}"))

    user_data_dir = profile_dir
    profile_directory = "Default"

    ws_deleted    = False
    chrome_proc   = None
    tmp_clone_dir = None

    try:
        attach_succeeded = False

        # ------------------------------------------------------------------
        # Attempt attach mode: clean Chrome → opensteer --attach-endpoint
        # ------------------------------------------------------------------
        if _OPENSTEER_ATTACH_MODE:
            try:
                chrome_bin = _find_chrome_binary()
                port = _find_free_port()

                # Minimal clone into a temp dir — avoids SQLite lock conflict
                # with the Playwright context that already holds the real profile.
                tmp_clone_dir = os.path.join(
                    os.path.dirname(user_data_dir),
                    f".warm_clone_{run_id}",
                )
                _clone_profile_minimal(user_data_dir, tmp_clone_dir, profile_directory)

                _say("info", f"[opensteer/attach] Launching clean Chrome on port {port} ...")
                chrome_proc = subprocess.Popen(
                    [
                        chrome_bin,
                        f"--user-data-dir={tmp_clone_dir}",
                        f"--profile-directory={profile_directory}",
                        f"--remote-debugging-port={port}",
                        "--no-first-run",
                        "--no-default-browser-check",
                        target_url,
                    ]
                )

                # Wait up to 10s for CDP to become reachable
                deadline = time.time() + 10
                while time.time() < deadline:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        if s.connect_ex(("localhost", port)) == 0:
                            break
                    time.sleep(0.3)
                else:
                    raise RuntimeError(f"Chrome CDP not ready on port {port} after 10s")

                # Attach opensteer to the running Chrome
                result = subprocess.run(
                    [
                        "opensteer", "open", target_url,
                        "--workspace", WS,
                        "--attach-endpoint", f"http://localhost:{port}",
                    ],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode != 0:
                    raise RuntimeError(
                        f"opensteer --attach-endpoint failed: {result.stderr.strip()}"
                    )

                attach_succeeded = True
                if SL: SL.log("opensteer_attach_mode", ws=WS, port=port)
                _say("info", f"[opensteer/attach] Attached to clean Chrome (no automation banner)")

            except Exception as e:
                _say("warn", f"[opensteer/attach] Failed ({e}) — falling back to direct mode")
                if SL: SL.log("opensteer_attach_fallback", error=str(e))
                if chrome_proc:
                    try: chrome_proc.terminate()
                    except Exception: pass
                    chrome_proc = None
                if tmp_clone_dir and os.path.exists(tmp_clone_dir):
                    try: shutil.rmtree(tmp_clone_dir, ignore_errors=True)
                    except Exception: pass
                    tmp_clone_dir = None

        # ------------------------------------------------------------------
        # Direct mode: opensteer-managed clone + open (existing behaviour)
        # ------------------------------------------------------------------
        if not attach_succeeded:
            _say("info", f"[opensteer] Cloning scraper profile → workspace {WS} ...")
            result = subprocess.run(
                [
                    "opensteer", "browser", "clone",
                    "--workspace", WS,
                    "--source-user-data-dir", user_data_dir,
                    "--source-profile-directory", profile_directory,
                ],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                if SL: SL.log("opensteer_clone_error", ws=WS, stderr=result.stderr.strip())
                raise RuntimeError(
                    f"opensteer browser clone failed (rc={result.returncode}): {result.stderr.strip()}"
                )

            _say("info", "[opensteer] Opening headed browser — navigate past the block, then confirm here")
            open_cmd = [
                "opensteer", "open", target_url,
                "--workspace", WS,
                "--headless", "false",
            ]
            result = None
            last_stderr = ""
            max_open_attempts = 3
            for attempt in range(1, max_open_attempts + 1):
                result = subprocess.run(open_cmd, capture_output=True, text=True)
                last_stderr = (result.stderr or "").strip()
                if result.returncode == 0:
                    break

                page_race = (
                    "browserContext.newPage" in last_stderr
                    or "reading '_page'" in last_stderr
                )
                if page_race and attempt < max_open_attempts:
                    if SL:
                        SL.log(
                            "opensteer_open_retry",
                            ws=WS,
                            attempt=attempt,
                            reason="browser_context_page_race",
                            stderr=last_stderr,
                        )
                    _say(
                        "warn",
                        f"[opensteer] Browser init race on attempt {attempt}/{max_open_attempts}; retrying...",
                    )
                    time.sleep(2.0)
                    continue
                break

            if result is None or result.returncode != 0:
                if SL:
                    SL.log("opensteer_open_error", ws=WS, stderr=last_stderr)
                raise RuntimeError(
                    f"opensteer open failed (rc={result.returncode if result else 'unknown'}): {last_stderr}"
                )

        _opensteer_set_title(WS, "OPENSTEER WARM SESSION (USE THIS WINDOW)", SL=SL)

        # ------------------------------------------------------------------
        # Prompt user via tkinter dialog (same pattern as prompt_relogin)
        # ------------------------------------------------------------------
        user_confirmed = False
        try:
            import tkinter as tk
            from tkinter import messagebox
            try:
                _root = tk._default_root  # type: ignore[attr-defined]
                if _root is None or not _root.winfo_exists():
                    raise RuntimeError("no root")
                own_root = False
            except Exception:
                _root = tk.Tk()
                _root.withdraw()
                own_root = True
            user_confirmed = messagebox.askyesno(
                "Walmart — Navigate Past Block",
                "An opensteer browser window is open.\n\n"
                "Use the window titled: OPENSTEER WARM SESSION (USE THIS WINDOW).\n"
                "Do NOT use the window titled: SCRAPER (DO NOT TOUCH).\n\n"
                "Navigate to Walmart search results in that window, then return here.\n\n"
                "Click Yes when results are visible.\n"
                "Click No to abort warm-session recovery.",
            )
            if own_root:
                _root.destroy()
        except Exception:
            if sys.stdin.isatty():
                _say("warn", "[opensteer] Use window 'OPENSTEER WARM SESSION'. Navigate to results, then press Enter.")
                input("[opensteer] Press Enter when Walmart search results are visible...")
                user_confirmed = True
            else:
                raise RuntimeError("[opensteer] No interactive prompt available (no tkinter, no TTY)")

        if not user_confirmed:
            raise RuntimeError("[opensteer] User aborted warm-session recovery")

        # ------------------------------------------------------------------
        # Export cookies and localStorage
        # ------------------------------------------------------------------
        cookies_raw = subprocess.run(
            ["opensteer", "exec", "return await this.cookies('walmart.com')", "--workspace", WS],
            capture_output=True, text=True, timeout=30,
        )
        if cookies_raw.returncode != 0:
            if SL: SL.log("opensteer_cookies_error", ws=WS, stderr=cookies_raw.stderr.strip())
            raise RuntimeError(f"opensteer exec cookies failed: {cookies_raw.stderr.strip()}")

        storage_raw = subprocess.run(
            ["opensteer", "exec", "return await this.storage('walmart.com', 'local')", "--workspace", WS],
            capture_output=True, text=True, timeout=30,
        )
        storage_stdout = storage_raw.stdout if storage_raw.returncode == 0 else "{}"
        if storage_raw.returncode != 0 and SL:
            SL.log("opensteer_storage_error", ws=WS, stderr=storage_raw.stderr.strip())

        # Delete opensteer workspace
        subprocess.run(
            ["opensteer", "browser", "delete", "--workspace", WS],
            capture_output=True, timeout=30,
        )
        ws_deleted = True

    finally:
        if not ws_deleted:
            try:
                subprocess.run(
                    ["opensteer", "browser", "delete", "--workspace", WS],
                    capture_output=True, timeout=30,
                )
            except Exception:
                pass
        if chrome_proc:
            try: chrome_proc.terminate()
            except Exception: pass
        if tmp_clone_dir and os.path.exists(tmp_clone_dir):
            try: shutil.rmtree(tmp_clone_dir, ignore_errors=True)
            except Exception: pass

    try:
        cookies = json.loads(cookies_raw.stdout).get("cookies", [])
    except Exception as e:
        raise RuntimeError(
            f"Could not parse opensteer cookies JSON: {e}\nRaw: {cookies_raw.stdout[:200]}"
        )

    try:
        local_storage = json.loads(storage_stdout)
        if not isinstance(local_storage, dict):
            local_storage = {}
    except Exception:
        local_storage = {}

    if SL:
        SL.log(
            "opensteer_warm_session_done",
            ws=WS,
            mode="attach" if attach_succeeded else "direct",
            cookies=len(cookies),
            storage_keys=len(local_storage),
        )

    return {"cookies": cookies, "local_storage": local_storage}


_SAMESITE_MAP = {
    "strict":         "Strict",
    "lax":            "Lax",
    "none":           "None",
    "no_restriction": "None",
    "unspecified":    "Lax",
    "":               "Lax",
}


def _set_page_title(page, title: str, SL=None):
    """Best-effort browser tab/window title labeling for operator clarity."""
    try:
        page.evaluate("(t) => { try { document.title = t; } catch (_) {} }", title)
        if SL:
            SL.log("page_title_set", title=title)
    except Exception as e:
        if SL:
            SL.log("page_title_set_error", title=title, error=str(e))


def _opensteer_set_title(ws: str, title: str, SL=None):
    """Best-effort label for OpenSteer warm-session window title."""
    cmds = [
        f"try {{ document.title = {json.dumps(title)}; return document.title; }} catch (e) {{ return 'title_set_failed'; }}",
        f"try {{ await this.eval(() => {{ document.title = {json.dumps(title)}; return document.title; }}); return 'ok'; }} catch (e) {{ return 'title_set_failed'; }}",
    ]
    for cmd in cmds:
        try:
            result = subprocess.run(
                ["opensteer", "exec", cmd, "--workspace", ws],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0:
                if SL:
                    SL.log("opensteer_title_set", ws=ws, title=title)
                return
        except Exception:
            pass
    if SL:
        SL.log("opensteer_title_set_failed", ws=ws, title=title)


def _inject_warm_session(ctx, page, session: dict, SL=None):
    """
    Inject opensteer warm-session state into the existing Playwright context.
    Must be called before any navigation retry.
    """
    if not isinstance(session, dict):
        if SL:
            SL.log("warm_session_invalid", type=str(type(session)))
        return

    cookies = session.get("cookies", [])
    local_storage = session.get("local_storage", {})

    if cookies:
        normalized = []
        for c in cookies:
            try:
                if not isinstance(c, dict):
                    if SL:
                        SL.log("warm_cookie_invalid_type", cookie_type=str(type(c)))
                    continue
                raw_ss = str(c.get("sameSite") or "").lower().strip()
                norm = {
                    "name":     str(c.get("name", "")),
                    "value":    str(c.get("value", "")),
                    "domain":   c.get("domain") or ".walmart.com",
                    "path":     c.get("path") or "/",
                    "expires":  float(c["expiresAt"]) / 1000 if c.get("expiresAt") not in (None, -1, "") else -1,
                    "httpOnly": bool(c.get("httpOnly", False)),
                    "secure":   bool(c.get("secure", False)),
                    "sameSite": _SAMESITE_MAP.get(raw_ss, "Lax"),
                }
                if norm["name"] and norm["domain"]:
                    normalized.append(norm)
            except Exception as e:
                cookie_name = c.get("name") if isinstance(c, dict) else None
                if SL: SL.log("warm_cookie_normalize_error", cookie_name=cookie_name, error=str(e))
        try:
            ctx.add_cookies(normalized)
            if SL: SL.log("warm_session_cookies_injected", count=len(normalized))
        except Exception as e:
            if SL: SL.log("warm_session_cookie_error", error=str(e))

    if local_storage and isinstance(local_storage, dict):
        try:
            if "walmart.com" not in (page.url or ""):
                page.goto("https://www.walmart.com", wait_until="domcontentloaded")
            page.evaluate("(data) => Object.assign(localStorage, data)", local_storage)
            if SL: SL.log("warm_session_storage_injected", keys=list(local_storage.keys())[:8])
        except Exception as e:
            if SL: SL.log("warm_session_storage_error", error=str(e))


def _resolve_run_dir(base_dir: Optional[str], keyword: str) -> str:
    """Always produce a unique, timestamped run folder and create it."""
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    if base_dir:
        root = _abs(base_dir)
    else:
        root = _abs(os.path.join("output", "walmart", safe_filename(keyword)))
    run_dir = os.path.join(root, ts)
    return _verify_writable_dir(run_dir, create=True)

def search_and_capture(
    root_logger,
    activity_cb: Optional[Callable[[str, str], None]],
    base_dir: str,
    keyword: str,
    profile_dir: Optional[str] = None,
    headless: bool = False,  # Default to headed for Walmart
    debug: DebugConfig | None = None,
) -> CaptureResult:
    """
    GUI calls this function.
    activity_cb(kind, msg) — kind in {'info','warn','error','success'}

    Strategy based on cookie-based trust:
    - Fresh fingerprint with exact Chrome headers
    - Stable viewport/timezone per profile
    - Random wait times
    - Human-like browsing patterns
    - Auto press-and-hold CAPTCHA solver
    """
    # PRE-FLIGHT: do not begin until these are verified
    # 1) activity_cb must be provided and callable (GUI live logging)
    if not callable(activity_cb):
        raise AssertionError("activity_cb is required and must be callable for GUI live logging")

    # 2) base_dir must be a real, timestamped folder per run
    #    We always convert the incoming base_dir to a unique run folder here.
    try:
        run_dir = _resolve_run_dir(base_dir, keyword)
    except Exception as e:
        # We have no logger yet, so raise a crisp error that the GUI can surface
        raise RuntimeError(f"Base directory preflight failed: {e}")
    
    # Extract client name and timestamp from paths for standardized filenames
    # run_dir format: output/walmart/[client_name]/runs/[timestamp]
    # We always extract from run_dir since base_dir might already be the runs dir
    client_name = None
    client_root = None
    run_timestamp = None
    try:
        # Extract timestamp from run_dir (format: YYYYMMDDHHMMSS)
        run_timestamp = os.path.basename(run_dir)
        
        # Get client root by going up from run_dir
        # run_dir = .../client/runs/timestamp or .../client/timestamp
        parent = os.path.dirname(run_dir)
        if os.path.basename(parent) == "runs":
            # Structure: client/runs/timestamp
            client_root = os.path.dirname(parent)
        else:
            # Structure: client/timestamp (legacy)
            client_root = parent
        
        client_name = os.path.basename(client_root)
    except Exception as e:
        print(f"[ERROR] Failed to extract client info: {e}")
        pass  # Will use fallback naming if extraction fails
    
    print(f"[EXTRACTION] client_name={client_name}, client_root={client_root}, run_timestamp={run_timestamp}")
    
    # Initialize canonical run tracking (retailer will be set later from DISPLAY_NAME)
    run_id = run_timestamp if run_timestamp else build_run_id()
    ads_list: List[Dict[str, Any]] = []
    print(f"[CANONICAL] run_id={run_id}, will collect ads into canonical schema")

    # 3) WALMART_PROFILE_DIR must exist and be writable (stable persistent profile)
    resolved_profile = profile_dir or os.environ.get(PROFILE_ENV)
    if not resolved_profile or not resolved_profile.strip():
        raise AssertionError(f"{PROFILE_ENV} is required (persistent Chrome profile for Walmart)")
    try:
        resolved_profile = _verify_writable_dir(resolved_profile, create=True)
    except Exception as e:
        raise RuntimeError(f"Profile directory preflight failed: {e}")

    # CRITICAL: Never use real Chrome Default profile (contains personal data)
    if resolved_profile.rstrip("/").endswith("Google/Chrome/Default"):
        raise AssertionError("Do not use your real Chrome Default profile. Set RETAILER_PROFILE_DIR to a dedicated folder (e.g., ~/ChromeProfiles/retailer_clean_profile).")

    # From here on, use run_dir and resolved_profile only
    base_dir = run_dir
    profile_dir = resolved_profile

    # Apply debug selection from GUI
    _apply_debug_config(debug or DebugConfig())

    # Initialize step logger AFTER preflight, so runs only start when verified
    SL = StepLogger(base_dir, keyword)

    def say(kind: str, msg: str):
        try:
            SL.log("log", level=kind, msg=msg)
            activity_cb(kind, msg)
        except Exception:
            pass

    # Run wiring
    global CURRENT_SL, RUN_ID
    CURRENT_SL = SL
    RUN_ID = f"{int(time.time()*1000)}-{random.randint(1000,9999)}"
    SL.log("run_start", run_id=RUN_ID, keyword=keyword,
           preflight={"base_dir": base_dir, "profile_dir": profile_dir},
           debug=(debug or DebugConfig()).__dict__)
    # _install_global_exception_hook(lambda: CURRENT_SL)  # TODO: implement if needed

    # Milestones
    MT = MilestoneTracker(SL)
    MT.mark("preflight_ok", ok=True)
    
    # Run report metrics
    started_at = datetime.now().isoformat(timespec="seconds")
    timings = {"to_home_ms": None, "after_submit_px_ms": None, "results_ready_ms": None}
    px_stats = {"tries": 0, "cycles": 0, "cleared": None}
    net_counters = {"req_failed": 0, "resp_doc": 0, "route_errors": 0}
    env_info = {"ua": None, "webgl": {}}
    cookies_info = {"pre_count": 0, "pre_names": [], "post_count": 0, "post_names": []}
    artifacts = {"steps_log": SL.path, "trace_zip": None, "no_results_html": None, 
                 "no_results_png": None, "saved_html": None, "meta_json": None}
    
    retailer = "walmart"  # Canonical lowercase for JSON schema (DISPLAY_NAME is for UI)
    shots: List[str] = []
    assets: List[str] = []
    meta: Dict = {"links": [], "videos": []}
    html_saved = 0
    bail_reason = None  # Set when we should NOT retry
    
    _ensure_dir(base_dir)
    url = _search_url(keyword)
    
    # Lock scrolling at start
    _lock_scroll("start")
    
    # DISABLED: Don't refresh cookies on timer - it resets trust
    # Only refresh if persistently blocked across multiple runs
    # if _should_refresh_cookies(profile_dir):
    #     say("info", f"[{retailer}] Refreshing cookies (24hr cycle)")
    #     # Clear old cookies by removing specific files
    #     if profile_dir and os.path.exists(profile_dir):
    #         cookie_files = ['Cookies', 'Cookies-journal', 'Network Persistent State']
    #         for cf in cookie_files:
    #             cf_path = os.path.join(profile_dir, 'Default', cf)
    #             if os.path.exists(cf_path):
    #                 try:
    #                     os.remove(cf_path)
    #                     say("info", f"[{retailer}] Cleared {cf}")
    #                 except:
    #                     pass
    
    # CRITICAL: Verify persistent profile is configured
    profile_dir = profile_dir or os.environ.get(PROFILE_ENV)
    print(f"[profile] WALMART_PROFILE_DIR={profile_dir!r}")
    assert profile_dir and profile_dir.strip(), "Missing WALMART_PROFILE_DIR (persistent profile disabled)"
    
    # Profile health check helper
    def _profile_health(pdir):
        d = os.path.join(pdir, "Default")
        paths = {
            "Cookies": os.path.join(d, "Cookies"),
            "Network Persistent State": os.path.join(d, "Network Persistent State"),
            "Preferences": os.path.join(d, "Preferences"),
        }
        info = {}
        for k, p in paths.items():
            size = os.path.getsize(p) if os.path.exists(p) else 0
            info[k] = {"exists": os.path.exists(p), "size": size}
        return info
    
    # Get proxy configuration if available
    proxy_config = _get_proxy_config()
    if proxy_config:
        say("info", f"[{retailer}] Using proxy: {proxy_config.get('server', 'N/A')}")
        # Log proxy session info for debugging
        if 'session=' in proxy_config.get('server', ''):
            SL.log("proxy_config", server=proxy_config['server'], has_session=True)
    
    # Cookie diagnostic helpers
    def _cookie_names(ctx):
        try:
            return sorted(set(c["name"] for c in ctx.cookies("https://www.walmart.com/")))
        except:
            return []
    
    def _cookie_snapshot(ctx):
        """Multi-domain cookie snapshot to diagnose domain/partition issues."""
        try:
            by_www = ctx.cookies("https://www.walmart.com/")
        except Exception:
            by_www = []
        try:
            by_root = ctx.cookies("https://walmart.com/")
        except Exception:
            by_root = []
        try:
            all_c = ctx.cookies()
        except Exception:
            all_c = []
        
        names_www = sorted({c.get("name") for c in by_www})
        names_root = sorted({c.get("name") for c in by_root})
        names_all = sorted({c.get("name") for c in all_c})
        
        return {
            "by_www": names_www[:12],
            "by_root": names_root[:12],
            "all": names_all[:12],
            "counts": {
                "by_www": len(names_www),
                "by_root": len(names_root),
                "all": len(names_all),
            }
        }
    
    # Initialize browser/context/page to None to prevent UnboundLocalError
    page: Optional[Page] = None
    ctx: Optional[BrowserContext] = None
    browser: Optional[Browser] = None
    
    # Reset shared net counters for this run
    _WALMART_NET_COUNTERS.update({"req_failed": 0, "resp_doc": 0, "route_errors": 0})
    net_counters = _WALMART_NET_COUNTERS

    try:
        with step(SL, "launch_context"):
            ctx = _get_walmart_ctx(profile_dir, proxy_config=proxy_config)

            # Reuse the singleton page if it's still alive and on Walmart.
            # Creating a new page per keyword is a cold-start robot signal —
            # a real user keeps the same tab open and types in the search bar.
            _existing_page = _WALMART_SINGLETON.get("page")
            _reuse_page = (
                _existing_page is not None
                and not _existing_page.is_closed()
                and "walmart.com" in (_existing_page.url or "")
            )

            if _reuse_page:
                page = _existing_page
                SL.log("page_reused", url=page.url)
            else:
                page = ctx.new_page()
                _WALMART_SINGLETON["page"] = page
                SL.log("page_created_fresh")

            # Page-level listeners — re-attached each run
            CLOSED.update({"page": False, "ctx": False})
            page.on("crash",  lambda: print("[page] crashed"))
            page.on("close",  lambda: CLOSED.update({"page": True}) or print("[page] closed"))
            page.on("console", lambda msg: print("[console]", msg.type, msg.text))
            page.on("pageerror", lambda err: CURRENT_SL and CURRENT_SL.log("page_error", error=str(err)))
            page.on("framenavigated", lambda fr: CURRENT_SL and CURRENT_SL.log("nav", url=fr.url, name=fr.name))
            if os.environ.get("WALMART_ENABLE_STEALTH") == "1":
                apply_stealth(page)
                SL.log("stealth_applied", enabled=True)
            else:
                SL.log("stealth_skipped", reason="px_detection_risk")
            _set_page_title(page, "SCRAPER (DO NOT TOUCH)", SL=SL)
            MT.mark("launch_context", ok=True)
            
            # DIAGNOSTIC: Profile health check (verify Chrome is writing to disk)
            health = _profile_health(profile_dir)
            print(f"[profile_health] {health}")
            SL.log("profile_health", **health)
            
            # DIAGNOSTIC: Check cookie persistence before any navigation
            pre_cookies = _cookie_names(ctx)
            print(f"[cookies] pre-run walmart.com: {len(pre_cookies)} names={pre_cookies[:8]}")
            SL.log("cookies_pre", count=len(pre_cookies), names=pre_cookies[:8])
            cookies_info["pre_count"] = len(pre_cookies)
            cookies_info["pre_names"] = pre_cookies[:12]
            
            # Flag suspicious cookies (Akamai/BotManager flags indicate scrutiny)
            suspicious = [n for n in pre_cookies if n.lower() in (
                "adblocked", "ak_bmsc", "bm_mi", "bm_sv", "bm_sz", "abck"
            )]
            if suspicious:
                SL.log("cookie_suspicious", names=suspicious)
                say("warn", f"[{retailer}] ⚠️  Suspicious cookies present: {suspicious}")
                cookies_info["suspicious"] = suspicious
                if not _reuse_page:
                    # Cold start: clear all bot-detection cookies before first navigation
                    n_cleared = _clear_bot_detection_cookies(ctx, SL=SL)
                    if n_cleared:
                        say("info", f"[{retailer}] 🧹 Auto-cleared {n_cleared} poisoned bot-detection cookies")
                        cookies_info["bot_cookies_cleared"] = n_cleared
                else:
                    # Reused page: ak_bmsc/bm_sv are live Akamai session tokens — keep them.
                    # But "adblocked" is a pure bot flag with no session value — clear it now.
                    _PURE_BOT_FLAGS = {"adblocked", "abck", "_abck"}
                    live_bot_flags = [n for n in suspicious if n.lower() in _PURE_BOT_FLAGS]
                    if live_bot_flags:
                        try:
                            all_cookies = ctx.cookies()
                            keep = [c for c in all_cookies if c["name"].lower() not in _PURE_BOT_FLAGS]
                            ctx.clear_cookies()
                            if keep:
                                ctx.add_cookies(keep)
                            SL.log("bot_flags_cleared_on_reuse", cleared=live_bot_flags)
                            say("info", f"[{retailer}] 🧹 Cleared bot flag cookie(s) on reused page: {live_bot_flags}")
                        except Exception as _ce:
                            SL.log("bot_flags_clear_error", error=str(_ce))
                    else:
                        SL.log("cookie_suspicious_kept", reason="reused_page_live_session")

            # CRITICAL: Verify cookie persistence for debugging
            if len(pre_cookies) == 0:
                SL.log("cookie_persistence", status="NO_COOKIES",
                       note="First run or profile issue - cookies will be saved after this run")
            elif len(pre_cookies) > 0:
                SL.log("cookie_persistence", status="COOKIES_PRESENT",
                       note=f"Profile working - {len(pre_cookies)} cookies persisted from previous run")
            else:
                SL.log("cookie_persistence", status="ERROR",
                       note="Cookie read failed - check profile permissions")
            
            # Increase timeouts for Walmart (PX delays can be long)
            page.set_default_timeout(30000)  # 30s
            try:
                page.set_default_navigation_timeout(30000)  # 30s
            except Exception:
                pass
            
            # Log PX collector beacons to verify they're reaching the network
            def _log_px_beacon(req):
                u = req.url.lower()
                if "px-cloud.net" in u:
                    print(f"[px] beacon -> {req.method} {req.url}")
            ctx.on("request", _log_px_beacon)
            
            # Log navigation to /blocked with stack trace
            def _log_blocked_nav(req):
                if req.is_navigation_request() and "walmart.com/blocked" in req.url.lower():
                    _log_px_trip(SL, "nav_to_blocked")
                    # Optional breakpoint for debugging
                    if DEBUG.break_on_blocked:
                        print(f"\n🔴 NAV TO BLOCKED: {req.url}")
                        print("Breaking into debugger - Type 'c' to continue, 'q' to quit")
                        import pdb; pdb.set_trace()
            
            # --- BEGIN: Direct navigation approach ---
            # Replaces: homepage warmup + search box typing + submit + human scroll
            # Key insight: navigating directly to /search?q=keyword avoids the
            # search-box interaction that is the primary PerimeterX trigger.

            # Log sec-ch-ua headers on FIRST navigation (PX checks these)
            nav_headers_logged = {"done": False}
            def _log_first_nav_headers(req):
                if nav_headers_logged["done"]:
                    return
                try:
                    if req.is_navigation_request() and req.resource_type == "document" and "walmart.com" in req.url:
                        hdrs = req.headers
                        wanted = {
                            "sec-ch-ua": hdrs.get("sec-ch-ua"),
                            "sec-ch-ua-mobile": hdrs.get("sec-ch-ua-mobile"),
                            "sec-ch-ua-platform": hdrs.get("sec-ch-ua-platform"),
                            "user-agent": hdrs.get("user-agent"),
                        }
                        SL.log("nav_headers", url=req.url, **wanted)
                        print(f"[nav_headers] {wanted}")
                        env_info["nav_headers"] = wanted
                        nav_headers_logged["done"] = True
                        if not any(wanted.values()):
                            SL.log("ua_ch_missing", url=req.url)
                            say("warn", f"[{retailer}] ⚠️  UA-CH headers missing on first nav; PX may flag this")
                except Exception:
                    pass
            ctx.on("request", _log_first_nav_headers)

            # Attach ad interceptor BEFORE navigation so it captures every response
            interceptor = WalmartAdInterceptor()
            interceptor.attach(page)
            SL.log("interceptor_attached", url=url)

            # Homepage buffer: when a poisoned session is detected (adblocked/ak_bmsc/bm_sv
            # present at startup), a direct search URL hit will be pre-blocked at Akamai's
            # edge before the page even loads. A quiet homepage visit lets PX re-score the
            # session with no search interaction, giving it a clean slate before we hit /search.
            # Real users also don't navigate directly from one search URL to another.
            # Skip homepage buffer when reusing a live page — ak_bmsc/bm_sv are
            # legitimate Akamai cookies Walmart issued during keyword 1. Navigating
            # to the homepage on an already-warm session triggers /blocked, not cures it.
            _needs_home_buffer = (
                not _reuse_page
                and bool(cookies_info.get("suspicious") or cookies_info.get("bot_cookies_cleared"))
            )
            if _needs_home_buffer:
                say("info", f"[{retailer}] Poisoned session detected — homepage buffer visit before search")
                SL.log("homepage_buffer_start", reason="suspicious_cookies")
                with step(SL, "homepage_buffer"):
                    try:
                        page.goto("https://www.walmart.com/", wait_until="domcontentloaded", timeout=20000)
                    except Exception:
                        pass  # timeout is fine — we just need the request to land
                    # Quiet pause — no interaction, just let PX observe a homepage load
                    page.wait_for_timeout(random.randint(2500, 4000))
                    # Clear any newly-issued bot cookies before the real nav
                    _clear_bot_detection_cookies(ctx, SL=SL)
                    SL.log("homepage_buffer_done", url=page.url)
            else:
                say("info", f"[{retailer}] Clean session — navigating to search")
                # Clear PX localStorage on fresh pages too — the browser profile retains
                # _pxvid / pxcts from previous sessions. A flagged vid from a prior
                # hard-blocked run will cause PX to challenge even on a cold start.
                try:
                    _px_ls_cleared_fresh = page.evaluate("""() => {
                        const keys = Object.keys(localStorage).filter(k =>
                            k.startsWith('_px') || k.startsWith('px_') || k === 'pxcts'
                        );
                        keys.forEach(k => localStorage.removeItem(k));
                        return keys;
                    }""")
                    if _px_ls_cleared_fresh:
                        SL.log("px_localstorage_cleared_fresh", keys=_px_ls_cleared_fresh)
                except Exception:
                    pass
                # PX stores the visitor ID in BOTH localStorage AND a cookie (_pxvid).
                # Clearing localStorage is insufficient — the cookie survives in the
                # Chromium profile and PX reads it on the next page load to restore the
                # flagged vid. Delete _pxvid from ctx cookies before any navigation.
                try:
                    _all_ck = ctx.cookies()
                    _px_vid_ck = [c for c in _all_ck if c["name"] in ("_pxvid", "_pxde")]
                    if _px_vid_ck:
                        _keep_ck = [c for c in _all_ck if c["name"] not in ("_pxvid", "_pxde")]
                        ctx.clear_cookies()
                        if _keep_ck:
                            ctx.add_cookies(_keep_ck)
                        SL.log("px_vid_cookie_cleared_fresh", names=[c["name"] for c in _px_vid_ck])
                except Exception as _px_ck_err:
                    SL.log("px_vid_cookie_clear_error", path="fresh", error=str(_px_ck_err))

            # Navigate to search results — prefer search bar (human pattern) over
            # direct URL navigation when the page is already live on Walmart.
            with step(SL, "goto_search"):
                _used_searchbar = False
                if _reuse_page:
                    # Clear PX localStorage before navigation so the new search results
                    # page gets a fresh visitor ID (_pxvid). The old vid may carry a
                    # "flagged" reputation from a prior blocked session — same vid =
                    # same bad score even with clean keyboard events.
                    try:
                        _px_ls_cleared = page.evaluate("""() => {
                            const keys = Object.keys(localStorage).filter(k =>
                                k.startsWith('_px') || k.startsWith('px_') || k === 'pxcts'
                            );
                            keys.forEach(k => localStorage.removeItem(k));
                            return keys;
                        }""")
                        if _px_ls_cleared:
                            SL.log("px_localstorage_cleared", keys=_px_ls_cleared)
                    except Exception as _ls_err:
                        SL.log("px_localstorage_clear_error", error=str(_ls_err))
                    # Also delete _pxvid from ctx cookies — PX persists the visitor ID
                    # in a cookie as well as localStorage. If the cookie is not removed,
                    # PX reads it back after navigation and reuses the flagged vid regardless
                    # of the localStorage clear. This was confirmed by ift.px-cloud.net/ns?v=
                    # showing the same vid (337ff3c0) on KW2 after localStorage was empty.
                    try:
                        _all_ck = ctx.cookies()
                        _px_vid_ck = [c for c in _all_ck if c["name"] in ("_pxvid", "_pxde")]
                        if _px_vid_ck:
                            _keep_ck = [c for c in _all_ck if c["name"] not in ("_pxvid", "_pxde")]
                            ctx.clear_cookies()
                            if _keep_ck:
                                ctx.add_cookies(_keep_ck)
                            SL.log("px_vid_cookie_cleared", names=[c["name"] for c in _px_vid_ck])
                    except Exception as _px_ck_err:
                        SL.log("px_vid_cookie_clear_error", path="reuse", error=str(_px_ck_err))
                    try:
                        _sb = page.locator('[data-testid="search-form"] input[name="q"]')
                        if _sb.count() > 0:
                            # Bezier move to search bar, then click — same pattern as homepage warmup
                            _sb_box = _sb.first.bounding_box()
                            if _sb_box:
                                _sb_cx = _sb_box["x"] + _sb_box["width"] / 2
                                _sb_cy = _sb_box["y"] + _sb_box["height"] / 2
                                try:
                                    cur = page.mouse.position
                                    _bezier_mouse_move(page, cur["x"], cur["y"], _sb_cx, _sb_cy,
                                                       duration_ms=random.randint(350, 650))
                                except Exception:
                                    pass
                            _sb.first.click(timeout=4000)
                            page.wait_for_timeout(random.randint(250, 500))
                            # Triple-click selects all text in the input reliably on all platforms
                            _sb.first.click(click_count=3)
                            page.wait_for_timeout(random.randint(80, 150))
                            # Also press platform select-all as belt-and-suspenders
                            import platform as _platform
                            _sel_all = "Meta+a" if _platform.system() == "Darwin" else "Control+a"
                            _sb.first.press(_sel_all)
                            page.wait_for_timeout(random.randint(60, 120))
                            # Use page.keyboard.type() via human_type(page=page) — real
                            # KeyDown/KeyPress/KeyUp events instead of synthetic InputEvent.
                            # PX sensors detect element.type(); page.keyboard does not trigger it.
                            human_type(_sb.first, keyword, page=page)
                            # Brief pause before submitting — simulates reading what was typed
                            page.wait_for_timeout(random.randint(300, 600))
                            _sb.first.press("Enter")
                            try:
                                page.wait_for_load_state("domcontentloaded", timeout=20000)
                            except Exception:
                                time.sleep(1)
                            _used_searchbar = True
                            SL.log("searchbar_nav_done", keyword=keyword, url=page.url)
                        else:
                            SL.log("searchbar_not_found", fallback="goto")
                    except Exception as _sb_err:
                        SL.log("searchbar_nav_failed", error=str(_sb_err), fallback="goto")

                if not _used_searchbar:
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    except Exception as _nav_err:
                        if "timeout" not in str(_nav_err).lower():
                            bail_reason = "navigation_failed"
                            meta["bail"] = bail_reason
                            meta["steps_log"] = SL.path
                            report = _build_report(keyword, "bail", bail_reason, started_at, timings, env_info, cookies_info, px_stats, net_counters, artifacts, SL)
                            _write_run_report(base_dir, report)
                            return CaptureResult(html_saved=0, shots=[], assets=[], meta=meta)
                        # domcontentloaded timeout is acceptable -- page is still usually usable
                        time.sleep(1)

                _nav_mark_done(SL=SL)
                timings["to_home_ms"] = int((time.time() - SL.t0) * 1000)
                SL.log("goto_search_done", url=page.url)

            # Diagnostics: UA, WebGL (masked only), navigator
            try:
                ua = eval_safe(page, "() => navigator.userAgent", "ua", SL=SL)
                vendor = eval_safe(page, """() => {
                    const c=document.createElement('canvas');
                    const gl=c.getContext('webgl')||c.getContext('experimental-webgl');
                    return gl ? gl.getParameter(gl.VENDOR) : null;
                }""", "webgl_vendor", SL=SL)
                renderer = eval_safe(page, """() => {
                    const c=document.createElement('canvas');
                    const gl=c.getContext('webgl')||c.getContext('experimental-webgl');
                    return gl ? gl.getParameter(gl.RENDERER) : null;
                }""", "webgl_renderer", SL=SL)
                # Note: WEBGL_debug_renderer_info (unmasked vendor/renderer) is NOT
                # evaluated — real pages rarely call this extension and PX flags it.
                diag = eval_safe(page, """() => ({
                    webdriver: navigator.webdriver,
                    pluginsLength: (navigator.plugins||[]).length,
                    hardwareConcurrency: navigator.hardwareConcurrency,
                    deviceMemory: navigator.deviceMemory || null,
                    vendor: navigator.vendor,
                })""", "navigator_diag", SL=SL)

                env_info["ua"] = ua
                env_info["webgl"] = {"vendor": vendor, "renderer": renderer}
                env_info["navigator_diag"] = diag
                BROWSER_UA["ua"] = ua
                try:
                    HEADERS["user-agent"] = ua
                except Exception:
                    pass

                SL.log("diagnostics", ua=str(ua)[:80], vendor=vendor, renderer=renderer)
                print(f"[ua] {ua}")
                print(f"[webgl] vendor={vendor} renderer={renderer}")

                # Bail on SwiftShader (software renderer = instant PX fail)
                if renderer and "SwiftShader" in str(renderer):
                    bail_reason = "fingerprint_mismatch"
                    SL.log("fingerprint_mismatch", renderer=renderer, fatal=True)
                    say("error", f"[{retailer}] ❌ SwiftShader detected -- aborting (PX will hard-block)")
                    meta["bail"] = bail_reason
                    meta["steps_log"] = SL.path
                    report = _build_report(keyword, "bail", bail_reason, started_at, timings, env_info, cookies_info, px_stats, net_counters, artifacts, SL)
                    _write_run_report(base_dir, report)
                    return CaptureResult(html_saved=0, shots=[], assets=[], meta=meta)

                # Bail if webdriver=true (automation flag still set)
                if diag and diag.get("webdriver"):
                    bail_reason = "fingerprint_mismatch"
                    SL.log("fingerprint_mismatch", webdriver=True, fatal=True)
                    say("error", f"[{retailer}] ❌ webdriver=true -- aborting to avoid PX hard block")
                    meta["bail"] = bail_reason
                    meta["steps_log"] = SL.path
                    report = _build_report(keyword, "bail", bail_reason, started_at, timings, env_info, cookies_info, px_stats, net_counters, artifacts, SL)
                    _write_run_report(base_dir, report)
                    return CaptureResult(html_saved=0, shots=[], assets=[], meta=meta)
            except Exception as _diag_err:
                SL.log("diagnostics_error", error=str(_diag_err))

            # Cookie snapshot (post-nav)
            try:
                pre_cookies = _cookie_names(ctx)
                SL.log("cookies_after_nav", count=len(pre_cookies), names=pre_cookies[:8])
                print(f"[cookies] post-nav walmart.com: {len(pre_cookies)} names={pre_cookies[:8]}")
                suspicious = [n for n in pre_cookies if n.lower() in (
                    "adblocked", "ak_bmsc", "bm_mi", "bm_sv", "bm_sz", "abck"
                )]
                if suspicious:
                    SL.log("cookie_suspicious", names=suspicious)
                    say("warn", f"[{retailer}] ⚠️  Suspicious cookies present: {suspicious}")
            except Exception as _ck_err:
                SL.log("cookie_snapshot_error", error=str(_ck_err))

            # Hard block check after navigation
            if _on_blocked(page.url):
                SL.log("hard_block", where="after_search_nav", url=page.url)
                say("error", f"[{retailer}] Hard blocked after search navigation -- bailing")
                bail_reason = "hard_block"
                meta["bail"] = bail_reason
                meta["steps_log"] = SL.path
                report = _build_report(keyword, "bail", bail_reason, started_at, timings, env_info, cookies_info, px_stats, net_counters, artifacts, SL)
                _write_run_report(base_dir, report)
                return CaptureResult(html_saved=0, shots=[], assets=[], meta=meta)

            # PX challenge check (less common with direct URL but still possible)
            if _still_px_modal(page):
                SL.log("px_status", where="search_page", challenged=True, url=page.url)
                if _solve_px_until_clear(page, say, SL=SL):
                    say("success", f"[{retailer}] ✅ PX cleared on search page")
                    SL.log("px_result", where="search_page", ok=True)
                    PX_ESCALATION["main_js_seen"] = False
                    PX_ESCALATION["bundle_post_seen"] = False
                    PX_ESCALATION["escalation_ts"] = None
                    SL.log("px_escalation_reset", where="search_page_solve")
                else:
                    say("error", f"[{retailer}] Failed to clear PX on search page")
                    SL.log("px_result", where="search_page", ok=False)
                    bail_reason = "px_locked"
                    meta["bail"] = bail_reason
                    meta["steps_log"] = SL.path
                    report = _build_report(keyword, "bail", bail_reason, started_at, timings, env_info, cookies_info, px_stats, net_counters, artifacts, SL)
                    _write_run_report(base_dir, report)
                    return CaptureResult(html_saved=0, shots=[], assets=[], meta=meta)

            # Wait for search results to render
            ready, which = _wait_for_search_results(page, timeout_ms=15000)
            SL.log("results_ready", ready=ready, selector=which, url=page.url)
            _nav_mark_done(SL=SL)
            say("info", f"[{retailer}] Results ready: {ready} ({which}) | url={page.url}")
            timings["results_ready_ms"] = int((time.time() - SL.t0) * 1000)

            if not ready:
                say("warn", f"[{retailer}] No results detected - saving forensics")
                _dump_html_png(page, base_dir, f"{SLUG}_{keyword}_no_results")
                artifacts["no_results_html"] = os.path.join(base_dir, safe_filename(f"{SLUG}_{keyword}_no_results.html"))
                artifacts["no_results_png"] = os.path.join(base_dir, safe_filename(f"{SLUG}_{keyword}_no_results.png"))

            # Extract __NEXT_DATA__ (structured product + sponsored item data from Next.js SSR)
            nd_result = _extract_next_data_items(page, SL=SL)
            if nd_result:
                SL.log("next_data_extracted",
                       organic=nd_result["organic_count"],
                       sponsored=nd_result["sponsored_count"],
                       total=nd_result.get("total", 0))
                say("info", f"[{retailer}] __NEXT_DATA__: {nd_result['organic_count']} organic, "
                            f"{nd_result['sponsored_count']} sponsored, {nd_result.get('total', 0)} total")
            else:
                nd_result = {"organic_items": [], "sponsored_items": [], "organic_count": 0, "sponsored_count": 0}

            # Scroll down to trigger lazy-loaded ad network calls (GraphQL responses).
            # IMPORTANT: use page.mouse.wheel() — NOT window.scrollTo().
            # PX's sensor distinguishes programmatic JS scrolls from user wheel events.
            # window.scrollTo() is a dead giveaway; mouse.wheel() matches real trackpad input.
            _unlock_scroll("direct_nav", SL=SL)

            # Pre-scroll dwell: a human reads the top of the page for a few seconds
            # before starting to scroll. Starting immediately after results load is a
            # bot signal. 2.5-4.5s matches realistic reading/scan behaviour.
            _pre_scroll_dwell = random.uniform(2.5, 4.5)
            SL.log("pre_scroll_dwell", seconds=round(_pre_scroll_dwell, 2))
            page.wait_for_timeout(int(_pre_scroll_dwell * 1000))

            # Move mouse into the content area before scrolling (simulate gaze landing
            # on product grid). PX checks that wheel events originate near the viewport
            # centre, not from a stationary corner position.
            try:
                _vp = page.viewport_size or {"width": 1280, "height": 800}
                _mx = random.randint(int(_vp["width"] * 0.25), int(_vp["width"] * 0.65))
                _my = random.randint(int(_vp["height"] * 0.30), int(_vp["height"] * 0.55))
                page.mouse.move(_mx, _my)
                page.wait_for_timeout(random.randint(300, 650))
                SL.log("pre_scroll_mouse_pos", x=_mx, y=_my)
            except Exception:
                pass

            # Reset FIRST_SCROLL_DONE so the lighter first-burst logic fires correctly
            # for each keyword (it's a module-level flag that stays set between keywords).
            FIRST_SCROLL_DONE["done"] = False

            with step(SL, "scroll_passes"):
                for _spass in range(3):
                    try:
                        # Each pass: several wheel bursts with natural reading pauses.
                        # Pass 0 is lighter (first_scroll logic inside _scroll_like_human
                        # limits it automatically); passes 1-2 are fuller scrolls.
                        _bursts = random.randint(3, 5) if _spass == 0 else random.randint(4, 7)
                        _scroll_like_human(
                            page, say,
                            bursts=_bursts,
                            lines_min=7, lines_max=16,
                            pause_min=0.45, pause_max=1.3,
                            SL=SL,
                        )
                        # Brief micro-movement: simulate eye scanning the results
                        try:
                            micro_mouse_attention(page, around=(4, 8), jitter=18)
                        except Exception:
                            pass
                        page.wait_for_timeout(random.randint(1000, 2200))
                        SL.log("scroll_pass", pass_num=_spass)
                        if _still_px_modal(page):
                            SL.log("px_mid_scroll", pass_num=_spass)
                            say("warn", f"[{retailer}] PX appeared mid-scroll -- solving")
                            if not _solve_px_until_clear(page, say, SL=SL):
                                SL.log("px_mid_scroll_failed", pass_num=_spass)
                                break
                    except Exception as _scroll_err:
                        SL.log("scroll_pass_error", pass_num=_spass, error=str(_scroll_err))

                # Scroll back to top with wheel (not scrollTo — same reason).
                try:
                    for _ in range(random.randint(4, 7)):
                        page.mouse.wheel(0, -random.randint(200, 420))
                        time.sleep(random.uniform(0.05, 0.14))
                    page.wait_for_timeout(random.randint(400, 800))
                except Exception:
                    pass
                # Wait for in-flight ad network calls to complete (matches CLI behaviour)
                try:
                    page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass

            # Harvest intercepted GraphQL ad data
            interceptor.harvest(debug_dir=base_dir)
            SL.log("interceptor_harvest",
                   orchestra_payloads=len(interceptor.orchestra_payloads),
                   swag_payloads=len(interceptor.swag_payloads),
                   sponsored_shelf_ads=len(interceptor.sponsored_shelf_ads),
                   display_banner_ads=len(interceptor.display_banner_ads),
                   video_urls=len(interceptor.video_urls))
            say("info", f"[{retailer}] Intercepted: "
                        f"{len(interceptor.sponsored_shelf_ads)} shelf ads, "
                        f"{len(interceptor.display_banner_ads)} banner ads, "
                        f"{len(interceptor.video_urls)} video URLs")
            timings["after_submit_px_ms"] = int((time.time() - SL.t0) * 1000)

            # Final PX check before capture
            if _still_px_modal(page):
                SL.log("px_status", where="before_capture", challenged=True, url=page.url)
                if not _solve_px_until_clear(page, say, SL=SL):
                    say("error", f"[{retailer}] Failed to clear PX before capture")
                    bail_reason = "px_locked"
                    meta["bail"] = bail_reason
                    meta["steps_log"] = SL.path
                    report = _build_report(keyword, "bail", bail_reason, started_at, timings, env_info, cookies_info, px_stats, net_counters, artifacts, SL)
                    _write_run_report(base_dir, report)
                    return CaptureResult(html_saved=0, shots=[], assets=[], meta={})
            # --- END: Direct navigation approach ---

            # Save HTML with Kroger-style filename (standardized for GUI)
            # Use run_timestamp from directory name to ensure consistency with image filenames
            if run_timestamp and len(run_timestamp) == 14:
                # Convert YYYYMMDDHHMMSS to YYYY-MM-DD_HH-MM-SS
                run_ts_file = f"{run_timestamp[0:4]}-{run_timestamp[4:6]}-{run_timestamp[6:8]}_{run_timestamp[8:10]}-{run_timestamp[10:12]}-{run_timestamp[12:14]}"
            else:
                # Fallback to current time if run_timestamp is invalid
                run_ts_file = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            clean_kw_for_file = (keyword or "search").replace(" ", "_").lower()
            html_path = os.path.join(base_dir, f"search_results_{clean_kw_for_file}_{run_ts_file}.html")
            
            try:
                content = page.content()
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(content)
                html_saved = 1
                artifacts["saved_html"] = html_path
                say("info", f"[{retailer}] HTML captured (1/1)")

                # Track profile health (block detection + persistent ledger)
                try:
                    from utils.profile_health import check_and_record
                    blk, blk_reason = check_and_record(content, "walmart", keyword, alert=True)
                    if blk:
                        say("warn", f"[{retailer}] Page blocked: {blk_reason}")
                except Exception:
                    pass
            except Exception as e:
                say("warn", f"[{retailer}] HTML save failed: {e}")
            
            # Save canonical JSON schema (will be populated after ad capture)
            # Note: ads_list will be built during ad capture below, then saved at the end
            SL.log("canonical_json_prep", run_id=run_id, client=client_name, keyword=keyword)

            # Helper: check for PX modal and solve before/between captures.
            # Called as a statement before each ad type — blocks until PX is cleared
            # or times out. Screenshots taken while the modal is overlaid are unusable.
            def _px_guard(where: str):
                if _still_px_modal(page):
                    SL.log("px_guard_triggered", where=where)
                    say("warn", f"[{retailer}] PX modal before {where} — solving")
                    _solve_px_until_clear(page, say, SL=SL)

            # 1) Skyline top strip banner (e.g. LandO Lakes thin banner at page top)
            _px_guard("skyline")
            n, s = _capture_elements(page, base_dir, keyword, "skyline", SELECTORS["skyline"], meta, SL=SL, client_name=client_name, client_root=client_root, timestamp=run_timestamp, run_id=run_id, ads_list=ads_list)
            shots.extend(s)
            if n:
                say("info", f"[{retailer}] Skyline top banner found ({n})")

            # 2) Marquee banners — scroll each into view so the iframe src hydrates,
            #    then screenshot. Walmart places marquee2 iframes both above the grid
            #    (shoppable banner, e.g. Country Crock) and below (e.g. Thyme & Table).
            _px_guard("marquee_banner")
            marquee_locs = page.locator(SELECTORS["marquee_banner"])
            marquee_count = marquee_locs.count()
            SL.log("marquee_found", count=marquee_count)
            if marquee_count:
                say("info", f"[{retailer}] Marquee banners found ({marquee_count}) — scrolling to hydrate")
                # Wheel-scroll each marquee into view so its iframe src loads before screenshot.
                # scroll_into_view_if_needed() is a JS call — PX detects no mouse delta events.
                for _mi in range(marquee_count):
                    try:
                        _bring_into_view(page, marquee_locs.nth(_mi), SL=SL)
                        time.sleep(random.uniform(0.6, 1.1))
                    except Exception:
                        pass
                try:
                    page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                # Wheel back to top — window.scrollTo(0,0) is a JS call PX scores negatively.
                try:
                    _scroll_like_human(page, say, bursts=random.randint(3, 5),
                                       lines_min=-20, lines_max=-8,
                                       pause_min=0.12, pause_max=0.30, SL=SL)
                    time.sleep(random.uniform(0.2, 0.4))
                except Exception:
                    pass
                _seen_marquee_srcs: set = set()
                def _marquee_dedup(item):
                    try:
                        # If this element contains another [data-testid="marquee2"], it's the
                        # outer wrapper — skip it. We only want the innermost element.
                        if item.locator('[data-testid="marquee2"]').count() > 0:
                            return False
                    except Exception:
                        pass
                    # Deduplicate by iframe src to handle top/bottom placement of same ad.
                    try:
                        src = item.locator("iframe").first.get_attribute("src") or ""
                        src_key = src.split("?")[0]
                        if src_key in _seen_marquee_srcs:
                            return False
                        if src_key:
                            _seen_marquee_srcs.add(src_key)
                    except Exception:
                        pass
                    return True
                n, s = _capture_elements(
                    page, base_dir, keyword, "marquee_banner",
                    SELECTORS["marquee_banner"],
                    meta, SL=SL, client_name=client_name, client_root=client_root,
                    timestamp=run_timestamp, run_id=run_id, ads_list=ads_list,
                    filter_fn=_marquee_dedup,
                )
                shots.extend(s)
                if n:
                    say("info", f"[{retailer}] Marquee banner captured ({n})")

            # 3) SBA
            _px_guard("sba")
            n, s = _capture_elements(page, base_dir, keyword, "sba", SELECTORS["sba"], meta, SL=SL, client_name=client_name, client_root=client_root, timestamp=run_timestamp, run_id=run_id, ads_list=ads_list)
            shots.extend(s)
            if n:
                say("info", f"[{retailer}] SBA found ({n})")
            
            # 3) Tile takeover — any element with data-testid="tile-take-over" is a paid placement
            _px_guard("tile_takeover")
            n, s = _capture_elements(page, base_dir, keyword, "tile_takeover", SELECTORS["tile_takeover"], meta, SL=SL, client_name=client_name, client_root=client_root, timestamp=run_timestamp, filter_fn=None, run_id=run_id, ads_list=ads_list)
            shots.extend(s)
            if n:
                say("info", f"[{retailer}] Tile takeover found ({n})")
            
            # 4) SBV (screenshot module + attempt mp4 download)
            _px_guard("sbv")
            sbv_mod = page.locator(SELECTORS["sbv"])
            vcount = sbv_mod.count()
            vids_saved = 0
            for i in range(vcount):
                mod = sbv_mod.nth(i)
                try:
                    # Scroll SBV module into view using wheel events (not JS scrollIntoView).
                    # element.scroll_into_view_if_needed() uses JS — PX detects no mouse delta.
                    _bring_into_view(page, mod, SL=SL)
                    time.sleep(random.uniform(0.3, 0.6))
                    
                    # Extract advertiser for SBV
                    # Priority: Use first product in carousel (matches HTML parser logic)
                    advertiser = None
                    try:
                        # Method 1: Extract from first product in carousel (MOST RELIABLE)
                        # Try both old and new product tile selectors
                        if not advertiser:
                            try:
                                # Try new selector first (search-in-grid-*)
                                products = mod.locator('[data-testid^="search-in-grid-"]').all()
                                
                                # Fallback to old selector (item-stack-*)
                                if not products:
                                    products = mod.locator('[data-testid^="item-stack-"]').all()
                                
                                if products:
                                    first_product = products[0]
                                    
                                    # Try product brand element (old structure)
                                    brand_elem = first_product.locator('[data-automation-id="product-brand"]').first
                                    if brand_elem.count() > 0:
                                        advertiser = brand_elem.inner_text().strip()
                                    
                                    # Try product title element (old structure)
                                    if not advertiser:
                                        product_title = first_product.locator('[data-automation-id="product-title"]').first
                                        if product_title.count() > 0:
                                            title_text = product_title.inner_text().strip()
                                            # Extract brand from title (flexible - could be 1-3 words)
                                            advertiser = _extract_brand_from_title(title_text)
                                    
                                    # Try span elements (new structure - search-in-grid-*)
                                    if not advertiser:
                                        # Look for product title in spans with common classes
                                        span_selectors = ['span.w_iUH7', 'span.w_V_DM', 'span[class*="product"]']
                                        for selector in span_selectors:
                                            span = first_product.locator(selector).first
                                            if span.count() > 0:
                                                title_text = span.inner_text().strip()
                                                if title_text and len(title_text) > 5:
                                                    # Try lexicon match first (most accurate)
                                                    if canonicalize_brand:
                                                        canonical = canonicalize_brand(title_text)
                                                        if canonical:
                                                            advertiser = canonical
                                                            if SL: SL.log("sbv_brand_lexicon_match", brand=advertiser, title=title_text[:50])
                                                            break
                                                    # Fallback to title extraction
                                                    if not advertiser:
                                                        advertiser = _extract_brand_from_title(title_text)
                                                        if advertiser:
                                                            if SL: SL.log("sbv_brand_title_extract", brand=advertiser, title=title_text[:50])
                                                            break
                                    
                                    # Try product link URL (works for both structures)
                                    if not advertiser:
                                        product_link = first_product.locator('a[href*="/ip/"]').first
                                        if product_link.count() > 0:
                                            href = product_link.get_attribute('href') or ''
                                            # Extract brand from /ip/{Brand}-{Product}/ID pattern
                                            ip_match = re.search(r'/ip/([^-/]+)', href)
                                            if ip_match:
                                                brand = ip_match.group(1).replace('-', ' ').replace('_', ' ')
                                                advertiser = brand.strip().title()
                            except:
                                pass
                        
                        # Method 2: Extract from URL facet parameter (fallback)
                        if not advertiser:
                            links = mod.locator('a[href*="facet"]').all()
                            for link in links[:3]:
                                href = link.get_attribute('href') or ''
                                brand_match = re.search(r'facet[^&]*brand[^&]*[:%]([^&%]+)', href, re.IGNORECASE)
                                if brand_match:
                                    advertiser = brand_match.group(1).replace('%20', ' ').replace('+', ' ')
                                    break
                        
                        # Final fallback: Use "unknown" if we couldn't extract brand
                        if not advertiser:
                            advertiser = "unknown"
                    except Exception as e:
                        advertiser = "unknown"  # Ensure we have a value even on error
                    
                    # Generate standardized filename and save to SBV folder
                    if client_name and client_root and run_timestamp:
                        # Save images to client_root (like Kroger), metadata goes to base_dir/runs
                        sbv_folder = os.path.join(client_root, "SBV")
                        os.makedirs(sbv_folder, exist_ok=True)
                        
                        # PNG screenshot
                        png_filename = generate_ad_filename(
                            retailer='walmart',
                            ad_type='sbv',
                            client=client_name,
                            search_term=keyword,
                            timestamp=run_timestamp,
                            index=i+1,
                            extension='png',
                            advertiser=advertiser
                        )
                        out = os.path.join(sbv_folder, png_filename)
                    else:
                        # Fallback to old naming
                        out = os.path.join(base_dir, safe_filename(f"{SLUG}_{keyword}_sbv_{i+1}.png"))
                    
                    # Capture video bounding box BEFORE screenshot for accurate overlay positioning
                    video_overlay = None
                    video_url = None
                    try:
                        v = mod.locator("video").first
                        if v.count() > 0:
                            video_url = v.get_attribute("src") or None
                            # Get video element's bounding box relative to the module container
                            mod_box = mod.bounding_box()
                            video_box = v.bounding_box()
                            if mod_box and video_box:
                                # Calculate video position relative to the module (screenshot area)
                                video_overlay = {
                                    "x": round(video_box["x"] - mod_box["x"]),
                                    "y": round(video_box["y"] - mod_box["y"]),
                                    "width": round(video_box["width"]),
                                    "height": round(video_box["height"]),
                                    "image_width": round(mod_box["width"]),
                                    "image_height": round(mod_box["height"]),
                                }
                                if SL: SL.log("sbv_video_overlay_captured", overlay=video_overlay)
                    except Exception as e:
                        if SL: SL.log("sbv_video_overlay_error", error=str(e))
                    
                    mod.screenshot(path=out)
                    shots.append(out)
                    
                    # Build and append canonical ad object for SBV
                    if run_id and ads_list is not None and client_root and client_name:
                        try:
                            ad_index = len(ads_list) + 1
                            saved_path = Path(out)
                            client_root_path = Path(client_root)
                            
                            ad_obj = build_ad_object(
                                run_id=run_id,
                                ad_index=ad_index,
                                ad_type="SBV",
                                client_root=client_root_path,
                                saved_path=saved_path,
                                brand_name=advertiser if advertiser != "unknown" else None,
                                ad_title=None,  # TODO: extract title when available
                                cta_text=None,  # TODO: extract CTA when available
                                destination_url=None,  # TODO: extract destination when available
                                cdn_image_url=video_url,  # Store video URL in image_url for now
                                slot_index=i,
                            )
                            if ad_obj is None:
                                # Blacklisted brand - delete the saved image
                                try:
                                    saved_path.unlink(missing_ok=True)
                                except Exception:
                                    pass
                                continue
                            
                            # Add video overlay metadata if captured
                            if video_overlay:
                                ad_obj["video_overlay"] = video_overlay
                            # Add video_url path (relative to client folder)
                            if video_url:
                                mp4_rel = f"SBV/{generate_ad_filename(retailer='walmart', ad_type='sbv', client=client_name, search_term=keyword, timestamp=run_timestamp, index=i+1, extension='mp4', advertiser=advertiser)}"
                                ad_obj["video_url"] = mp4_rel
                            
                            ads_list.append(ad_obj)
                            if SL: SL.log("ad_object_built", ad_id=ad_obj["id"], type=ad_obj["type"], brand=ad_obj["brand"])
                        except Exception as e:
                            if SL: SL.log("ad_object_build_error", error=str(e), label="sbv", index=i+1)
                    
                    # Store advertiser in metadata with ad type and index
                    if advertiser:
                        ad_key = f"sbv_{i+1}"  # e.g., "sbv_1", "sbv_2"
                        meta.setdefault("advertisers", {})[ad_key] = advertiser
                    
                    # Try to download video
                    v = mod.locator("video").first
                    if v.count() > 0:
                        src = v.get_attribute("src") or ""
                        if src and src.startswith(("http://", "https://")):
                            # Generate video filename
                            if client_name and client_root and run_timestamp:
                                mp4_filename = generate_ad_filename(
                                    retailer='walmart',
                                    ad_type='sbv',
                                    client=client_name,
                                    search_term=keyword,
                                    timestamp=run_timestamp,
                                    index=i+1,
                                    extension='mp4',
                                    advertiser=advertiser
                                )
                                vpath = os.path.join(sbv_folder, mp4_filename)
                            else:
                                vpath = os.path.join(base_dir, safe_filename(f"{SLUG}_{keyword}_sbv_{i+1}.mp4"))
                            
                            if _download(src, vpath):
                                vids_saved += 1
                                assets.append(vpath)
                                meta["videos"].append(vpath)
                except Exception:
                    continue
            if vcount:
                say("info", f"[{retailer}] SBV found (videos {vids_saved})")
            
            # 5) Gallery Bottom Ad Cards (carousel of sponsored brand cards in iframes)
            # These ads are at the bottom of the page and need scrolling to hydrate
            _px_guard("gallery_cards")
            try:
                # Scroll to bottom using wheel bursts to trigger lazy loading of gallery cards.
                # window.scrollTo() is detectable by PX — use mouse.wheel() instead.
                try:
                    _scroll_like_human(page, say, bursts=random.randint(4, 7),
                                       lines_min=10, lines_max=20,
                                       pause_min=0.3, pause_max=0.7, SL=SL)
                    time.sleep(2.0)  # Wait for iframes to start loading

                    # Check if gallery container exists now
                    gallery_container = page.locator(SELECTORS["gallery_cards"])
                    if gallery_container.count() > 0:
                        # Wheel-scroll until container is in view (not JS scrollIntoView)
                        _bring_into_view(page, gallery_container.first, SL=SL)
                        time.sleep(1.5)  # Additional wait for iframe content to load
                        
                        # Wait for at least one iframe to have content
                        try:
                            page.wait_for_selector(
                                f'{SELECTORS["gallery_cards"]} iframe[data-ad-type^="gallerybottom"]',
                                timeout=5000
                            )
                            time.sleep(1.0)  # Extra buffer for iframe content hydration
                            if SL: SL.log("gallery_cards_hydrated")
                        except Exception:
                            if SL: SL.log("gallery_cards_iframe_timeout")
                except Exception as scroll_err:
                    if SL: SL.log("gallery_cards_scroll_error", error=str(scroll_err))
                
                n_cards, card_shots = _capture_gallery_cards(
                    page, base_dir, keyword, meta, 
                    SL=SL, 
                    client_name=client_name, 
                    client_root=client_root, 
                    timestamp=run_timestamp, 
                    run_id=run_id, 
                    ads_list=ads_list
                )
                shots.extend(card_shots)
                if n_cards:
                    say("info", f"[{retailer}] Gallery Cards found ({n_cards})")
            except Exception as e:
                if SL: SL.log("gallery_cards_capture_error", error=str(e))
                say("warn", f"[{retailer}] Gallery Cards capture failed: {e}")
            
            # 6) Full-page screenshot to Main folder
            _px_guard("fullpage_screenshot")
            # Gallery card iframes are lazy-rendered only when in-viewport. Scrolling
            # back to top BEFORE screenshotting causes them to unload, leaving blank
            # sections at the bottom of the full-page image.
            # Fix: stay at the bottom after the incremental scroll (gallery cards already
            # captured and still rendered there). Playwright's full_page=True renders
            # the entire document without needing to be at the top.
            try:
                try:
                    # One pass: scroll to bottom with wheel bursts so lazy content fires
                    # and PX sees real wheel events, not JS scrollTo calls.
                    _scroll_like_human(page, say, bursts=random.randint(5, 8),
                                       lines_min=12, lines_max=22,
                                       pause_min=0.25, pause_max=0.6, SL=SL)
                    # Final push to ensure we're at the very bottom
                    for _ in range(random.randint(3, 5)):
                        page.mouse.wheel(0, random.randint(300, 500))
                        time.sleep(random.uniform(0.08, 0.18))

                    # Hold at absolute bottom — gallery iframes render when in-viewport
                    time.sleep(2.5)
                    # Stay here — do NOT scroll back to top before shooting
                except Exception as e:
                    if SL: SL.log("fullpage_scroll_error", error=str(e))
                
                if client_root and run_timestamp:
                    main_folder = os.path.join(client_root, "Main")
                    os.makedirs(main_folder, exist_ok=True)
                    
                    # Generate full-page screenshot filename
                    fullpage_filename = generate_ad_filename(
                        retailer='walmart',
                        ad_type='main',
                        client=client_name,
                        search_term=keyword,
                        timestamp=run_timestamp,
                        index=1,
                        extension='png'
                    )
                    fullpage_path = os.path.join(main_folder, fullpage_filename)
                else:
                    # Fallback to runs directory
                    fullpage_path = os.path.join(base_dir, safe_filename(f"{SLUG}_{keyword}_fullpage.png"))
                
                # Take full-page screenshot
                page.screenshot(path=fullpage_path, full_page=True)
                shots.append(fullpage_path)
                say("info", f"[{retailer}] Full-page screenshot saved")
                if SL: SL.log("fullpage_screenshot", path=fullpage_path)
            except Exception as e:
                say("warn", f"[{retailer}] Full-page screenshot failed: {e}")
                if SL: SL.log("fullpage_screenshot_error", error=str(e))
            
            # Save meta.json (links/videos)
            try:
                meta_path = os.path.join(base_dir, safe_filename(f"{SLUG}_{keyword}_meta.json"))
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2)
                assets.append(meta_path)
                artifacts["meta_json"] = meta_path
            except Exception:
                pass
    
    except Exception as e:
        # Catch launch failures or other outer errors
        SL.log("outer_error", error=str(e))
        say("error", f"[{retailer}] Fatal error: {e}")
        bail_reason = "fatal"
        meta["bail"] = bail_reason
        meta["steps_log"] = SL.path
        report = _build_report(keyword, "bail", bail_reason, started_at, timings, env_info, cookies_info, px_stats, net_counters, artifacts, SL)
        _write_run_report(base_dir, report)
        return CaptureResult(html_saved=0, shots=[], assets=[], meta={})
    
    finally:
        # Post-run cookie snapshot (ctx stays alive — singleton context)
        if ctx:
            try:
                snap = _cookie_snapshot(ctx)
                SL.log("cookies_post_multi",
                       by_www_count=snap["counts"]["by_www"],
                       by_root_count=snap["counts"]["by_root"],
                       all_count=snap["counts"]["all"],
                       by_www_names=snap["by_www"],
                       by_root_names=snap["by_root"],
                       all_names=snap["all"])
                post_cookies = _cookie_names(ctx)
                print(f"[cookies] post-run walmart.com: {len(post_cookies)} names={post_cookies[:8]}")
                SL.log("cookies_post", count=len(post_cookies), names=post_cookies[:8])
                cookies_info["post_count"] = snap["counts"]["by_www"]
                cookies_info["post_names"] = snap["by_www"]
            except Exception as e:
                print(f"[cookies] post-run failed: {e}")

        # Keep the page alive in the singleton — next keyword will reuse it
        # via the search bar rather than opening a fresh page (more human-like).
        # Page is only closed at process exit via close_walmart_context().
        pass
    
    # Mark cookies as refreshed if successful
    if html_saved > 0:
        _mark_cookies_refreshed(profile_dir)
    
    # Add step log path to meta
    meta["steps_log"] = SL.path if SL.path else None
    
    # Write run report
    outcome = "success" if html_saved > 0 else "fail"
    report = _build_report(keyword, outcome, None, started_at, timings, env_info, cookies_info, px_stats, net_counters, artifacts, SL)
    paths = _write_run_report(base_dir, report)
    if paths:
        SL.log("run_report_paths", **paths)
    
    SL.log("run_complete", html_saved=html_saved, shots_count=len(shots), assets_count=len(assets))
    
    # Save canonical JSON schema
    try:
        if client_root and client_name:
            # Build canonical payload with collected ads
            # ads_list was populated during capture (SBA, SBV, Tile_Takeover)
            payload = build_run_payload(
                retailer=retailer,
                client=client_name,
                keyword=keyword,
                run_id=run_id,
                ads=ads_list  # Populated during ad capture
            )
            
            # Save to Walmart's nested structure: output/walmart/<client>/runs/<run_id>/
            # Read HTML from saved file if content variable not available
            html_content = ""
            if 'content' in locals():
                html_content = content
            elif 'html_path' in locals() and os.path.exists(html_path):
                try:
                    with open(html_path, 'r', encoding='utf-8') as f:
                        html_content = f.read()
                except:
                    pass
            
            # Extract product listings from saved HTML
            if html_content:
                try:
                    from tools.extract_product_listings import extract_product_listings
                    product_listings = extract_product_listings("walmart", html_content)
                    payload["product_listings"] = product_listings
                    SL.log("product_listings_extracted", count=len(product_listings),
                           sponsored=sum(1 for p in product_listings if p.get("is_sponsored")))
                    say("info", f"[{retailer}] Extracted {len(product_listings)} product listings from HTML")
                except Exception as pl_err:
                    SL.log("product_listings_error", error=str(pl_err))
                    say("warn", f"[{retailer}] Product listing extraction failed: {pl_err}")
            
            run_dir = save_run_artifacts(
                client_root=Path(client_root),
                run_id=run_id,
                html_content=html_content,
                run_payload=payload
            )
            
            SL.log("canonical_json_saved", run_dir=str(run_dir), ads_count=len(ads_list))
            say("info", f"[{retailer}] Canonical JSON saved: {run_dir}/run_results_{run_id}.json")
    except Exception as e:
        SL.log("canonical_json_error", error=str(e))
        say("warn", f"[{retailer}] Failed to save canonical JSON: {e}")
    
    # Final summary
    summary = MT.summary()
    SL.log("run_summary", run_id=RUN_ID, **summary)
    SL.log("run_end", run_id=RUN_ID, html_saved=html_saved, shots_count=len(shots), assets_count=len(assets))
    
    return CaptureResult(html_saved=html_saved, shots=shots, assets=assets, meta=meta)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Walmart search and capture")
    parser.add_argument("keyword", help="Search keyword")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    args = parser.parse_args()
    
    # Get profile dir from environment
    profile_dir = os.environ.get("WALMART_PROFILE_DIR")
    
    # Dummy activity callback for CLI mode
    def dummy_activity_cb(event, **kwargs):
        pass
    
    # Call the search_and_capture function
    result = search_and_capture(
        root_logger=None,
        activity_cb=dummy_activity_cb,
        base_dir=args.output_dir,
        keyword=args.keyword,
        profile_dir=profile_dir,
        headless=args.headless,
        debug=None,
    )
    
    # Exit with appropriate code
    html_saved = getattr(result, "html_saved", 0) or 0
    sys.exit(0 if html_saved > 0 else 1)
