import os
import pdb
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

# Ad modules we'll detect and screenshot
SELECTORS = {
    "top_banner": "a.ad, a.adctr",  # programmatic banners (top/bottom)
    "sba": '[data-testid="sba-container"]',  # Sponsored Brand module
    "tile_takeover": '[data-testid="tile-take-over"]',  # Tile takeover
    "sbv": '[data-testid="search-video-in-grid"]',  # Sponsored Brand Video
    "marquee_banner": '[data-testid="marquee2"]',  # Onsite Display Marquee Banner
    "gallery_cards": '[data-testid="galleryBottom"]',  # Gallery Bottom Ad Cards carousel
    "gallery_card_iframe": 'iframe[data-ad-type^="gallerybottom"]',  # Individual card iframes
}
@dataclass
class CaptureResult:
    html_saved: int
    shots: List[str]
    assets: List[str]
    meta: Dict


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def safe_filename(name: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in name)


# --- BEGIN: Walmart run helpers (canonical schema and artifact writing) ---

def build_run_id() -> str:
    """
    Build 14-digit run ID in UTC, e.g., 20251026161402.
    Walmart uses nested timestamp directories: runs/<run_id>/
    """
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

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
    (run_dir / f"run_results_{run_id}.json").write_text(json.dumps(run_payload, indent=2, ensure_ascii=False))

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
    assert ad_type in {"SBA", "SBV", "Tile_Takeover", "Gallery_Cards"}, f"Unexpected ad_type: {ad_type}"
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
        # fallback defaults
        return {"width": 1440, "height": 900}, "America/Chicago"
    try:
        with open(vp_path, "r") as f:
            viewport = json.load(f)
        with open(tz_path, "r") as f:
            timezone = f.read().strip()
        return viewport, timezone
    except:
        # Choose once, save, reuse
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
        
        # Use persistent Chrome (channel=chrome) for real Chrome browser
        launch_options = {
            'user_data_dir': profile_dir,
            'headless': False,  # ALWAYS headed for Walmart
            'viewport': viewport,  # STABLE per profile
            'locale': 'en-US',
            'timezone_id': timezone,  # STABLE per profile
            'args': args,
            'ignore_default_args': ['--enable-automation'],  # Prevents navigator.webdriver=true
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
            
            # CRITICAL: Force navigator.webdriver to be undefined (not true)
            # With persistent context, ignore_default_args doesn't reliably clear it
            # This minimal init script prevents PX from seeing webdriver=true
            ctx.add_init_script("""
                // Make navigator.webdriver be undefined rather than true
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
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
        
        # Telemetry - catch silent exits
        ctx.tracing.start(screenshots=True, snapshots=True, sources=False)
        ctx.on("close", lambda: print("[ctx] closed"))
        
        # Create page BEFORE using it anywhere
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.on("crash", lambda: print("[page] crashed"))
        page.on("close", lambda: _on_page_close())
        ctx.on("close", lambda: _on_ctx_close())
        page.on("console", lambda msg: print("[console]", msg.type, msg.text))
        
        # --- forensic listeners ---
        def _req_failed(req):
            if CURRENT_SL:
                CURRENT_SL.log("req_failed",
                               url=req.url, method=req.method,
                               resource=req.resource_type, failure=str(req.failure))
            net_counters["req_failed"] += 1

        def _resp_doc(res):
            try:
                req = res.request
                if req.is_navigation_request() and req.resource_type == "document":
                    if CURRENT_SL:
                        CURRENT_SL.log("resp_doc",
                                       url=res.url, status=res.status,
                                       method=req.method, fromCache=res.from_service_worker)
                    net_counters["resp_doc"] += 1
            except Exception as e:
                if CURRENT_SL:
                    CURRENT_SL.log("resp_doc_error", err=str(e))

        def _page_error(err):
            if CURRENT_SL:
                CURRENT_SL.log("page_error", error=str(err))

        ctx.on("requestfailed", _req_failed)
        ctx.on("response", _resp_doc)
        page.on("pageerror", _page_error)
        
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
                net_counters["route_errors"] += 1
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
        
        # Navigation logging - log via CURRENT_SL
        def _log_navigation(fr):
            if CURRENT_SL:
                CURRENT_SL.log("nav", url=fr.url, name=fr.name)
        page.on("framenavigated", _log_navigation)
        
        # /blocked detector (request-level)
        def _log_blocked_nav(req):
            if req.is_navigation_request() and "walmart.com/blocked" in req.url.lower():
                _log_px_trip(CURRENT_SL, "nav_to_blocked")
                if os.environ.get("WALMART_BREAK_ON_BLOCKED") == "1":
                    print(f"\n🔴 NAV TO BLOCKED: {req.url}")
                    import pdb; pdb.set_trace()
        ctx.on("request", _log_blocked_nav)
        
        # Apply stealth ONLY if explicitly enabled (PX detects stealth mutations)
        # For Walmart, stealth is OFF by default - use real Chrome + coherent signals instead
        if os.environ.get("WALMART_ENABLE_STEALTH") == "1":
            apply_stealth(page)
            if CURRENT_SL:
                CURRENT_SL.log("stealth_applied", enabled=True)
        else:
            if CURRENT_SL:
                CURRENT_SL.log("stealth_skipped", reason="px_detection_risk")
        
        return None, ctx, page, True
    
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
    
    return browser, ctx, page, False


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
                                            ad_type_name = ad_type_map.get(label, label.title())
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
                    
                    # Map label to ad type folder name (canonical: SBA, SBV, Tile_Takeover only)
                    ad_type_map = {
                        'sba': 'SBA',
                        'sbv': 'SBV',
                        'tile_takeover': 'Tile_Takeover',
                        # top_banner and marquee_banner are future features (not yet implemented)
                    }
                    ad_type_folder = ad_type_map.get(label, label.title())
                    
                    # Validate folder is allowed for Walmart
                    from utils.path_taxonomy import validate_folder
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
        
        # Find all ad card iframes - try multiple patterns
        # Primary: data-ad-type starts with "gallerybottom"
        # Also check for any sponsored ad iframes in the container
        iframe_selector = SELECTORS["gallery_card_iframe"]
        iframes = page.query_selector_all(iframe_selector)
        
        # If no iframes found with primary selector, try broader search
        if not iframes:
            # Try iframes with title="Walmart Advertisement" within gallery containers
            iframes = page.query_selector_all('[id*="zonebottom"] iframe[title="Walmart Advertisement"]')
            if iframes and SL:
                SL.log("gallery_cards_fallback_iframes", count=len(iframes))
        
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
                    iframe_handle.scroll_into_view_if_needed()
                    time.sleep(0.3)  # Let it settle
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
def human_type(element, text: str):
    """Type with human-like delays and occasional pauses."""
    for ch in text:
        element.type(ch, delay=random.uniform(80, 220))
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

def _on_blocked(url: str) -> bool:
    """Check if URL is the /blocked route."""
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
    One uninterrupted steady hold until 100%.
    - Waits for widget to be visible and stable
    - Focus click once
    - Mouse down, sleep, mouse up (no movement)
    - Wait for Walmart's auto-transition (beacon + modal vanish)
    - Only if needed: gentle fallback (reload vs goto home)
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

        x = box["x"] + box["width"] * 0.25   # inside button
        y = box["y"] + box["height"] / 2.0

        # Focus click (guarded against page close)
        try:
            page.mouse.move(x, y, steps=10)
            page.mouse.click(x, y, delay=random.randint(40, 120))
        except Exception:
            if SL: SL.log("px_hold_bail", reason="page_closed_on_focus_click")
            return False
        time.sleep(random.uniform(0.25, 0.45))

        if t_ready < 3.0:
            low, high = 6.8, 8.2
        else:
            low, high = 8.8, 10.2

        duration = random.uniform(low, high)
        if SL: SL.log("px_hold_plan", duration=round(duration,2))
        say("info", f"[Walmart] Steady hold {duration:.2f}s (ready in {t_ready:.2f}s)")

        # Hold (guarded against page close)
        try:
            page.mouse.down()
            time.sleep(duration)
            page.mouse.up()
        except Exception:
            if SL: SL.log("px_hold_bail", reason="page_closed_on_down_up")
            return False
        time.sleep(random.uniform(1.4, 2.0))

        # Wait for Walmart's auto-transition (beacon + modal vanish or nav)
        t0 = time.time()
        auto_ok = False
        if SL: SL.log("px_auto_wait_start", timeout=4.0)

        while time.time() - t0 < 4.0:
            if px_beacon_seen["ok"]:
                auto_ok = True
                if SL: SL.log("px_auto_ok", reason="beacon_seen")
                break
            if page.locator("#px-captcha").count() == 0 and \
               page.locator('iframe[title="Human verification challenge"]').count() == 0 and \
               "Robot or human?" not in (page.content() or ""):
                auto_ok = True
                if SL: SL.log("px_auto_ok", reason="modal_vanished")
                break
            time.sleep(0.15)

        if SL and not auto_ok:
            SL.log("px_auto_wait_timeout", waited=round(time.time()-t0,2))

        # Gentle fallback only if auto-transition failed
        if not auto_ok:
            if SL: SL.log("px_fallback_start")
            if _on_blocked(page.url):
                # Go to home (like Walmart would send us), then idle
                if SL: SL.log("px_fallback", action="goto_home")
                try:
                    page.goto("https://www.walmart.com/", wait_until="domcontentloaded")
                    time.sleep(random.uniform(1.2, 2.0))
                except Exception as e:
                    if SL: SL.log("px_fallback_error", error=str(e))
            else:
                # Soft reload to let scripts re-evaluate
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
                     cleared=cleared, url=page.url, auto_ok=auto_ok)
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
    
    try:
        with sync_playwright() as p:
            with step(SL, "launch_context"):
                browser, ctx, page, persistent = _launch(p, profile_dir, headless=headless, proxy_config=proxy_config, net_counters=net_counters)
                MT.mark("launch_context", ok=True)

            # --- BEGIN: close-aware guards ---
            CLOSED = {"page": False, "ctx": False}

            def _on_page_close():
                CLOSED["page"] = True
                print("[page] closed")

            def _on_ctx_close():
                CLOSED["ctx"] = True
                print("[ctx] closed")

            # Only register handlers if page/ctx were successfully created
            if page and ctx:
                try:
                    page.on("close", lambda: _on_page_close())
                    ctx.on("close", lambda: _on_ctx_close())
                except Exception:
                    pass
            # --- END: close-aware guards ---
            
            # Guard: If launch failed, bail early
            if not page or not ctx:
                SL.log("launch_failed", reason="page or ctx is None")
                say("error", f"[{retailer}] Browser launch failed")
                return CaptureResult(html_saved=0, shots=[], assets=[], meta={})
            
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
            
            # CRITICAL: Establish session with human-like browsing pattern
            say("info", f"[{retailer}] Establishing session (human-like pattern)")
            
            # Log sec-ch-ua headers on FIRST navigation (before homepage - PX checks these)
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
                        
                        # Warn if UA-CH is missing on first nav
                        if not any(wanted.values()):
                            SL.log("ua_ch_missing", url=req.url)
                            say("warn", f"[{retailer}] ⚠️  UA-CH headers missing on first nav; PX may flag this")
                except Exception:
                    pass
            ctx.on("request", _log_first_nav_headers)
            
            # 1. Visit homepage (like real users) - resilient navigation
            phase = _goto_home(page, SL)
            SL.log("home_goto_phase_final", phase=phase)
            
            # Timing: to homepage
            timings["to_home_ms"] = int((time.time() - SL.t0) * 1000)
            
            # CRITICAL: Bail fast if blocked on first navigation (prevents eval errors)
            if _on_blocked(page.url):
                SL.log("hard_block", where="initial_home", url=page.url, reason="blocked_on_first_nav")
                say("error", f"[{retailer}] ❌ Hard blocked on first navigation")
                say("error", f"  URL: {page.url}")
                say("error", f"  This indicates IP/profile reputation issue or Bot Manager flag")
                
                bail_reason = "hard_block"
                meta["bail"] = bail_reason
                meta["steps_log"] = SL.path
                report = _build_report(keyword, "bail", bail_reason, started_at, timings, env_info, cookies_info, px_stats, net_counters, artifacts, SL)
                _write_run_report(base_dir, report)
                return CaptureResult(html_saved=0, shots=[], assets=[], meta=meta)
            
            # DIAGNOSTIC: Log User-Agent (should be stable across runs)
            ua = eval_safe(page, "() => navigator.userAgent", "ua", SL=SL)
            if ua:
                print(f"[ua] {ua}")
                SL.log("user_agent", ua=ua)
                env_info["ua"] = ua
            else:
                print(f"[ua] eval failed - page may be redirecting")
                env_info["ua"] = None
            
            # Cache UA for requests library (video downloads)
            BROWSER_UA["ua"] = ua
            try:
                HEADERS["user-agent"] = ua
            except Exception:
                pass
            
            # Log WebGL info (sanity check GPU isn't SwiftShader)
            try:
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
                
                # Get UNMASKED WebGL info (real GPU string - PX checks this)
                unmasked = eval_safe(page, """() => {
                    const c=document.createElement('canvas');
                    const gl=c.getContext('webgl')||c.getContext('experimental-webgl');
                    if (!gl) return null;
                    const ext = gl.getExtension('WEBGL_debug_renderer_info');
                    return ext ? {
                        unmaskedVendor: gl.getParameter(ext.UNMASKED_VENDOR_WEBGL),
                        unmaskedRenderer: gl.getParameter(ext.UNMASKED_RENDERER_WEBGL)
                    } : null;
                }""", "webgl_unmasked", SL=SL)
                
                SL.log("webgl", vendor=vendor, renderer=renderer)
                print(f"[webgl] vendor={vendor}, renderer={renderer}")
                if unmasked:
                    SL.log("webgl_unmasked", **unmasked)
                    print(f"[webgl_unmasked] {unmasked}")
                
                env_info["webgl"] = {"vendor": vendor, "renderer": renderer, "unmasked": unmasked}
                
                # CRITICAL: Fingerprint verification guard (use UNMASKED when available)
                # Masked WebGL can show "WebKit" in real Chrome - UNMASKED is the key differentiator
                is_chrome_ua = ua and " Chrome/" in ua
                
                # Extract unmasked values (may be None if extension unavailable)
                def _string(s):
                    return (s or "").lower()
                
                unmasked_vendor = (unmasked or {}).get("unmaskedVendor") if isinstance(unmasked, dict) else None
                unmasked_renderer = (unmasked or {}).get("unmaskedRenderer") if isinstance(unmasked, dict) else None
                
                # Heuristics for UNMASKED values
                unmasked_ok = False
                unmasked_bad = False
                if unmasked_vendor or unmasked_renderer:
                    # OK: ANGLE (Chromium), Google Inc., Metal (macOS)
                    if "angle" in _string(unmasked_renderer) or "google" in _string(unmasked_vendor) or "metal" in _string(unmasked_renderer):
                        unmasked_ok = True
                    # BAD: SwiftShader (software renderer)
                    if "swiftshader" in _string(unmasked_renderer):
                        unmasked_bad = True
                
                # Decision logic
                if is_chrome_ua and unmasked_bad:
                    # FATAL: SwiftShader with Chrome UA = software rendering
                    SL.log("fingerprint_mismatch", ua=ua, vendor=vendor, renderer=renderer, unmasked=unmasked, fatal=True)
                    say("error", f"[{retailer}] ❌ FATAL: SwiftShader software renderer detected (will trip PX)")
                    say("error", f"  UA: {ua}")
                    say("error", f"  Unmasked: {unmasked}")
                    
                    bail_reason = "fingerprint_mismatch"
                    meta["bail"] = bail_reason
                    meta["steps_log"] = SL.path
                    report = _build_report(keyword, "bail", bail_reason, started_at, timings, env_info, cookies_info, px_stats, net_counters, artifacts, SL)
                    _write_run_report(base_dir, report)
                    return CaptureResult(html_saved=0, shots=[], assets=[], meta=meta)
                    
                elif is_chrome_ua and (unmasked_vendor or unmasked_renderer):
                    # UNMASKED present - trust it more than masked
                    if not unmasked_ok:
                        SL.log("fingerprint_warning", reason="unmasked_unknown", ua=ua, vendor=vendor, renderer=renderer, unmasked=unmasked)
                        say("warn", f"[{retailer}] ⚠️  Unmasked WebGL is unusual; proceeding cautiously")
                        say("warn", f"  Unmasked: {unmasked}")
                else:
                    # UNMASKED missing; masked shows WebKit often in real Chrome - warn only
                    if ("webkit" in _string(vendor)) or ("webkit" in _string(renderer)):
                        SL.log("fingerprint_warning", reason="masked_webkit", ua=ua, vendor=vendor, renderer=renderer)
                        say("warn", f"[{retailer}] ⚠️  Masked WebGL looks WebKit; no UNMASKED info. Not bailing.")
                        say("warn", f"  Masked: {vendor} / {renderer}")
                
            except Exception:
                pass
            
            # Log navigator diagnostics (webdriver, plugins, etc) - pinpoint bot signals
            try:
                diag = eval_safe(page, """() => ({
                    webdriver: navigator.webdriver,
                    languages: navigator.languages,
                    language: navigator.language,
                    platform: navigator.platform,
                    hardwareConcurrency: navigator.hardwareConcurrency,
                    deviceMemory: navigator.deviceMemory || null,
                    vendor: navigator.vendor,
                    pluginsLength: (navigator.plugins||[]).length,
                    userAgentData: (navigator.userAgentData ? {
                        brands: navigator.userAgentData.brands || null,
                        platform: navigator.userAgentData.platform || null,
                        mobile: navigator.userAgentData.mobile || null
                    } : null)
                })""", "navigator_diag", SL=SL)
                if diag:
                    SL.log("navigator_diag", **diag)
                    print(f"[diag] {diag}")
                    env_info["navigator_diag"] = diag
                    
                    # CRITICAL: Bail if webdriver is still true (init script failed)
                    if diag.get("webdriver"):
                        SL.log("fingerprint_mismatch", webdriver=True, fatal=True)
                        say("error", f"[{retailer}] ❌ webdriver=true detected — aborting to avoid PX hard block")
                        
                        bail_reason = "fingerprint_mismatch"
                        meta["bail"] = bail_reason
                        meta["steps_log"] = SL.path
                        report = _build_report(keyword, "bail", bail_reason, started_at, timings, env_info, cookies_info, px_stats, net_counters, artifacts, SL)
                        _write_run_report(base_dir, report)
                        return CaptureResult(html_saved=0, shots=[], assets=[], meta=meta)
                        
            except Exception:
                pass
            
            # Check for PX challenge and solve with cooldown/retry
            if _still_px_modal(page):
                SL.log("px_status", where="home", challenged=True, url=page.url)
                if _solve_px_until_clear(page, say, SL=SL):
                    say("success", f"[{retailer}] ✅ Unblocked on homepage")
                    SL.log("px_result", where="home", ok=True)
                else:
                    say("error", f"[{retailer}] Failed to clear PX after max attempts")
                    SL.log("px_result", where="home", ok=False)
                    bail_reason = "px_locked"
                    meta["bail"] = bail_reason
                    meta["steps_log"] = SL.path
                    report = _build_report(keyword, "bail", bail_reason, started_at, timings, env_info, cookies_info, px_stats, net_counters, artifacts, SL)
                    _write_run_report(base_dir, report)
                    return CaptureResult(html_saved=0, shots=[], assets=[], meta=meta)
            
            # Idle before any action (no scrolling - triggers PX)
            time.sleep(random.uniform(1.0, 2.0))
            
            # Accept cookie consent if present (optional)
            try:
                page.locator('button:has-text("Accept")').first.click(timeout=2000)
                time.sleep(random.uniform(0.3, 0.6))
            except:
                pass
            
            # Directly type into search – do not scroll the homepage
            say("info", f"[{retailer}] Typing search query")
            
            # Optional: line-by-line tracer around “type → submit → first PX check”
            if DEBUG.line_trace:
                trace_path = os.path.join(base_dir, safe_filename(f"{SLUG}_{keyword}_linetrace.log"))
                with ScopedTracer(os.path.basename(__file__), trace_path):
                    # typing + submit code block
                    # immediate PX check after submit (your px_after_submit_check)
                    pass
            
            # Try to use the search box if visible (more realistic)
            search_typed = False
            try:
                # Try multiple selectors for search box
                search_selectors = [
                    'input[aria-label="Search"]',
                    'input[name="q"]',
                    'input[type="search"]',
                    '#global-search-input'
                ]
                
                search_box = None
                for selector in search_selectors:
                    try:
                        search_box = page.locator(selector).first
                        if search_box.count() > 0:
                            say("info", f"[{retailer}] Found search box: {selector}")
                            break
                    except:
                        continue
                
                if search_box and search_box.count() > 0:
                    # Click search box
                    say("info", f"[{retailer}] Clicking search box")
                    search_box.click()
                    random_delay(0.2, 0.4)
                    
                    # CRITICAL: Longer dwell before typing to add entropy
                    # Reduces "home → submit in ~4s" uniformity that PX detects
                    time.sleep(random.uniform(2.0, 4.0))
                    
                    # Human typing with natural delays
                    say("info", f"[{retailer}] Typing keyword: {keyword}")
                    human_type(search_box, keyword)
                    
                    # CRITICAL: Dwell after typing (humans pause 600-1200ms before submit)
                    random_delay(0.60, 1.20)
                    
                    # Tiny "attention" mouse move (low energy)
                    if random.random() < 0.4:
                        micro_mouse_attention(page, around=(5, 9), jitter=6)
                    
                    # Prefer submitting with a real transition (nav OR url OR DOM)
                    submitted = False
                    submit_start = time.time()
                    SL.log("submit_wait_begin", ts=submit_start)
                    
                    def _log_after_submit(tag):
                        px_now = _still_px_modal(page)
                        ms_since_submit = int((time.time() - submit_start) * 1000)
                        cookies_now = sorted(set(c["name"] for c in page.context.cookies("https://www.walmart.com/")))
                        SL.log("after_submit", method=tag, px_visible=bool(px_now),
                               ms_since_submit=ms_since_submit, url=page.url, cookies=cookies_now[:6])
                    
                    # 1) Try a visible search button
                    btn = None
                    for btn_sel in [
                        'button[aria-label="Search"]',
                        'button[type="submit"]',
                        '[data-automation-id="global-search-submit"]',
                        'button:has(svg[aria-hidden="true"])'
                    ]:
                        candidate = page.locator(btn_sel).first
                        if candidate.count() > 0:
                            btn = candidate
                            break
                    
                    if btn and btn.count() > 0:
                        try:
                            box = btn.bounding_box()
                            if box:
                                mx = box["x"] + box["width"] * random.uniform(0.35, 0.65)
                                my = box["y"] + box["height"] * random.uniform(0.35, 0.65)
                                page.mouse.move(mx, my, steps=random.randint(6, 12))
                            random_delay(0.05, 0.12)
                        except:
                            pass
                        
                        SUBMIT["method"] = "button"; SUBMIT["t"] = submit_start
                        try:
                            btn.click()
                            trans = _wait_for_search_transition(page, timeout_ms=20000)  # 20s SPA-friendly wait
                            if trans:
                                submitted = True
                                _log_after_submit(f"button:{trans}")
                        except Exception:
                            pass
                    
                    # 2) Fallback: press Enter (use page.keyboard, not element.press), allow a second Enter
                    if not submitted:
                        try:
                            search_box.focus()
                        except Exception:
                            try:
                                search_box.click()
                            except:
                                pass
                        SUBMIT["method"] = "enter"; SUBMIT["t"] = submit_start
                        try:
                            page.keyboard.press("Enter")
                            trans = _wait_for_search_transition(page, timeout_ms=20000)
                            if not trans:
                                time.sleep(random.uniform(0.25, 0.6))  # sometimes first Enter just closes typeahead
                                page.keyboard.press("Enter")
                                trans = _wait_for_search_transition(page, timeout_ms=20000)
                            if trans:
                                submitted = True
                                _log_after_submit(f"enter:{trans}")
                        except Exception:
                            pass
                    
                    SL.log("submit_wait_end", elapsed_ms=int((time.time()-submit_start)*1000))
                    
                    # 3) No transition? Bail (do NOT goto /search)
                    if not submitted:
                        SL.log("submit_no_nav", note="No form-driven navigation or SPA transition after button/enter")
                        say("error", f"[{retailer}] No navigation after button/enter; bailing to avoid PX trip")
                        bail_reason = "search_submit_no_nav"
                        meta["bail"] = bail_reason
                        meta["steps_log"] = SL.path
                        report = _build_report(keyword, "bail", bail_reason, started_at, timings, env_info, cookies_info, px_stats, net_counters, artifacts, SL)
                        _write_run_report(base_dir, report)
                        return CaptureResult(html_saved=0, shots=[], assets=[], meta=meta)
                    
                    search_typed = True
                    say("info", f"[{retailer}] Search completed via typing")
                else:
                    say("warn", f"[{retailer}] Search box not found, using direct navigation")
            except Exception as e:
                say("warn", f"[{retailer}] Search typing failed: {e}")
            
            # Check for PX challenge after search navigation
            if _still_px_modal(page):
                SL.log("px_status", where="search_results", challenged=True, url=page.url)
                if _solve_px_until_clear(page, say, SL=SL):
                    say("success", f"[{retailer}] ✅ Unblocked on search results")
                    SL.log("px_result", where="search_results", ok=True)
                else:
                    say("error", f"[{retailer}] Failed to clear PX on search results")
                    SL.log("px_result", where="search_results", ok=False)
                    bail_reason = "px_locked"
                    meta["bail"] = bail_reason
                    meta["steps_log"] = SL.path
                    report = _build_report(keyword, "bail", bail_reason, started_at, timings, env_info, cookies_info, px_stats, net_counters, artifacts, SL)
                    _write_run_report(base_dir, report)
                    return CaptureResult(html_saved=0, shots=[], assets=[], meta={})

            # Hard block detection: if immediately sent to /blocked after submit, bail
            if _on_blocked(page.url) and (time.time() - LAST_NAV_DONE_TS["t"] < 5.0):
                SL.log("hard_block", where="after_submit", url=page.url, reason="blocked_immediate_after_nav")
                say("warn", f"[{retailer}] Hard block immediately after submit; backing off")
                bail_reason = "hard_block"
                meta["bail"] = bail_reason
                meta["steps_log"] = SL.path
                report = _build_report(keyword, "bail", bail_reason, started_at, timings, env_info, cookies_info, px_stats, net_counters, artifacts, SL)
                _write_run_report(base_dir, report)
                return CaptureResult(html_saved=0, shots=[], assets=[], meta={})
            
            # Re-run search only after a small idle on home (if PX recovery took us home)
            if page.url.rstrip("/") == "https://www.walmart.com":
                say("info", f"[{retailer}] Post-PX recovery: idling on home")
                time.sleep(random.uniform(2.0, 4.0))  # give PX state time to settle
                # If PX re-appeared on home, bail
                if _still_px_modal(page):
                    SL.log("hard_block", reason="px_on_home_after_recovery", url=page.url)
                    bail_reason = "px_locked"
                    meta["bail"] = bail_reason
                    meta["steps_log"] = SL.path
                    report = _build_report(keyword, "bail", bail_reason, started_at, timings, env_info, cookies_info, px_stats, net_counters, artifacts, SL)
                    _write_run_report(base_dir, report)
                    return CaptureResult(html_saved=0, shots=shots, assets=assets, meta=meta)
                # Single retry to search
                page.goto(url, wait_until="domcontentloaded")
                _nav_mark_done(SL=SL)
                # If this jumps to /blocked immediately, bail (don't hammer)
                if _on_blocked(page.url) and (time.time() - LAST_NAV_DONE_TS["t"] < 5.0):
                    SL.log("hard_block", reason="blocked_immediate_after_recovery_nav", url=page.url)
                    bail_reason = "hard_block"
                    meta["bail"] = bail_reason
                    meta["steps_log"] = SL.path
                    report = _build_report(keyword, "bail", bail_reason, started_at, timings, env_info, cookies_info, px_stats, net_counters, artifacts, SL)
                    _write_run_report(base_dir, report)
                    return CaptureResult(html_saved=0, shots=shots, assets=assets, meta=meta)
            
            # Wait for results to render (avoid false "empty" detection)
            ready, which = _wait_for_search_results(page, timeout_ms=15000)
            SL.log("results_ready", ready=ready, selector=which, url=page.url)
            _nav_mark_done(SL=SL)  # mark nav end regardless
            say("info", f"[{retailer}] Results ready: {ready} ({which}) | url={page.url}")
            
            # Wait for visual stability before acting
            if ready:
                timings["results_ready_ms"] = int((time.time() - (SUBMIT.get("t") or time.time()))*1000)
                stable = _wait_results_stable(page)
                SL.log("results_stable", stable=stable)
            
            if not ready:
                # Forensics to avoid silent retry
                say("warn", f"[{retailer}] No results detected - saving forensics")
                _dump_html_png(page, base_dir, f"{SLUG}_{keyword}_no_results")
                artifacts["no_results_html"] = os.path.join(base_dir, safe_filename(f"{SLUG}_{keyword}_no_results.html"))
                artifacts["no_results_png"] = os.path.join(base_dir, safe_filename(f"{SLUG}_{keyword}_no_results.png"))
            
            # Idle a beat before first scroll, then unlock scrolling
            random_delay(2.2, 3.5)  # Increased from 1.6-2.8 for better trust
            _unlock_scroll("results_ready", SL=SL)
            
            # Scroll like a human with native wheel events (PX modal handled inside)
            _scroll_like_human(page, say, bursts=random.randint(2, 4), lines_min=6, lines_max=12, SL=SL)
            
            # Exploratory behavior: drift reading + optional back-scroll + hover
            _drift_reading(page, seconds=random.uniform(1.8, 3.0))
            _backscroll_peek(page)
            
            # Hover on a random product tile
            try:
                if not page.is_closed() and not _still_px_modal(page):
                    tiles = page.locator('[data-item-id]')
                    if tiles.count() > 0:
                        n = random.randint(0, min(5, tiles.count()-1))
                        tiles.nth(n).hover()
                        time.sleep(random.uniform(0.4, 0.9))
            except Exception:
                pass
            
            # Wait a bit after interactions before capturing
            time.sleep(random.uniform(0.5, 0.9))
            
            # Simple mouse movement (guarded against closed)
            try:
                if not page.is_closed():
                    page.mouse.move(
                        random.randint(300, 800),
                        random.randint(400, 600)
                    )
                    time.sleep(random.uniform(0.2, 0.4))
            except Exception as e:
                if SL: SL.log("mouse_move_error", error=str(e))
            
            # Final check for PX challenge before capturing
            if _still_px_modal(page):
                SL.log("px_status", where="before_capture", challenged=True, url=page.url)
                if not _solve_px_until_clear(page, say, SL=SL):
                    say("error", f"[{retailer}] Failed to clear PX before capture")
                    SL.log("px_result", where="before_capture", ok=False)
                    bail_reason = "px_locked"
                    meta["bail"] = bail_reason
                    meta["steps_log"] = SL.path
                    report = _build_report(keyword, "bail", bail_reason, started_at, timings, env_info, cookies_info, px_stats, net_counters, artifacts, SL)
                    _write_run_report(base_dir, report)
                    return CaptureResult(html_saved=0, shots=[], assets=[], meta={})
            
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
            except Exception as e:
                say("warn", f"[{retailer}] HTML save failed: {e}")
            
            # Save canonical JSON schema (will be populated after ad capture)
            # Note: ads_list will be built during ad capture below, then saved at the end
            SL.log("canonical_json_prep", run_id=run_id, client=client_name, keyword=keyword)
            
            # 1) Programmatic banners (top_banner/marquee_banner - future feature, not yet implemented)
            # n, s = _capture_elements(page, base_dir, keyword, "top_banner", SELECTORS["top_banner"], meta, SL=SL, client_name=client_name, client_root=client_root, timestamp=run_timestamp)
            # shots.extend(s)
            # if n:
            #     say("info", f"[{retailer}] Top banner found ({n})")
            
            # 2) SBA
            n, s = _capture_elements(page, base_dir, keyword, "sba", SELECTORS["sba"], meta, SL=SL, client_name=client_name, client_root=client_root, timestamp=run_timestamp, run_id=run_id, ads_list=ads_list)
            shots.extend(s)
            if n:
                say("info", f"[{retailer}] SBA found ({n})")
            
            # 3) Tile takeover (only capture SPONSORED tile takeovers)
            def is_sponsored_tile(item):
                """Filter to only capture sponsored/featured tile takeovers"""
                try:
                    # Look for "Sponsored" indicator in the tile
                    text = item.inner_text().lower()
                    return 'sponsored' in text or 'featured' in text or 'ad' in text
                except:
                    # If we can't determine, skip it (safer to miss than capture organic)
                    return False
            
            n, s = _capture_elements(page, base_dir, keyword, "tile_takeover", SELECTORS["tile_takeover"], meta, SL=SL, client_name=client_name, client_root=client_root, timestamp=run_timestamp, filter_fn=is_sponsored_tile, run_id=run_id, ads_list=ads_list)
            shots.extend(s)
            if n:
                say("info", f"[{retailer}] Sponsored tile takeover found ({n})")
            
            # 4) SBV (screenshot module + attempt mp4 download)
            sbv_mod = page.locator(SELECTORS["sbv"])
            vcount = sbv_mod.count()
            vids_saved = 0
            for i in range(vcount):
                mod = sbv_mod.nth(i)
                try:
                    mod.scroll_into_view_if_needed()
                    time.sleep(0.2)
                    
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
            try:
                # First, scroll to bottom to trigger lazy loading of gallery cards
                try:
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(2.0)  # Wait for iframes to start loading
                    
                    # Check if gallery container exists now
                    gallery_container = page.locator(SELECTORS["gallery_cards"])
                    if gallery_container.count() > 0:
                        # Scroll the container into view and wait for iframes to hydrate
                        gallery_container.first.scroll_into_view_if_needed()
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
            try:
                # Incremental scroll to load lazy images throughout the page
                try:
                    # Get page height
                    page_height = page.evaluate("document.body.scrollHeight")
                    viewport_height = page.evaluate("window.innerHeight")
                    
                    # Scroll in increments, pausing to let images load
                    scroll_position = 0
                    scroll_increment = viewport_height * 0.75  # Scroll 75% of viewport at a time
                    
                    while scroll_position < page_height:
                        page.evaluate(f"window.scrollTo(0, {scroll_position})")
                        time.sleep(0.8)  # Pause to let lazy images load
                        scroll_position += scroll_increment
                    
                    # Final scroll to absolute bottom
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(1.0)  # Longer pause at bottom
                except Exception as e:
                    if SL: SL.log("fullpage_scroll_error", error=str(e))
                
                # Scroll back to top for clean screenshot
                try:
                    page.evaluate("window.scrollTo(0, 0)")
                    time.sleep(0.5)  # Let header settle
                except Exception:
                    pass
                
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
        # DIAGNOSTIC: Check cookie persistence after run (only if ctx is alive)
        if ctx:
            try:
                ctx_alive = not CLOSED.get("ctx", False)
            except Exception:
                ctx_alive = False

            if ctx_alive:
                try:
                    # Multi-domain cookie snapshot to diagnose domain/partition issues
                    snap = _cookie_snapshot(ctx)
                    SL.log("cookies_post_multi", 
                           by_www_count=snap["counts"]["by_www"],
                           by_root_count=snap["counts"]["by_root"],
                           all_count=snap["counts"]["all"],
                           by_www_names=snap["by_www"],
                           by_root_names=snap["by_root"],
                           all_names=snap["all"])
                    
                    # Keep original for back-compat metrics
                    post_cookies = _cookie_names(ctx)
                    print(f"[cookies] post-run walmart.com: {len(post_cookies)} names={post_cookies[:8]}")
                    print(f"[cookies] multi-domain: www={snap['counts']['by_www']}, root={snap['counts']['by_root']}, all={snap['counts']['all']}")
                    SL.log("cookies_post", count=len(post_cookies), names=post_cookies[:8])
                    cookies_info["post_count"] = snap["counts"]["by_www"]
                    cookies_info["post_names"] = snap["by_www"]
                except Exception as e:
                    print(f"[cookies] post-run failed: {e}")

            # Save trace for debugging silent exits
            if ctx:
                try:
                    trace_path = os.path.join(base_dir, safe_filename(f"{SLUG}_{keyword}_trace.zip"))
                    ctx.tracing.stop(path=trace_path)
                    print(f"[trace] saved → {trace_path}")
                    artifacts["trace_zip"] = trace_path
                except Exception as e:
                    print(f"[trace] stop failed: {e}")

            if ctx:
                try:
                    ctx.close()
                except Exception:
                    pass
            if browser:
                try:
                    browser.close()
                except Exception:
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
