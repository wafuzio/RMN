#!/usr/bin/env python3
"""
Walmart search and capture with selector-based ad detection.
"""
from __future__ import annotations
import os
import time
import json
import base64
import urllib.parse as ul
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Callable
import threading
from contextlib import contextmanager

import requests
from playwright.sync_api import sync_playwright
import random

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

SLUG = "walmart"
DISPLAY_NAME = "Walmart"
PROFILE_ENV = "WALMART_PROFILE_DIR"

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

# Ad modules we'll detect and screenshot
SELECTORS = {
    "top_banner": "a.ad, a.adctr",  # programmatic banners (top/bottom)
    "sba": '[data-testid="sba-container"]',  # Sponsored Brand module
    "tile_takeover": '[data-testid="tile-take-over"]',  # Tile takeover
    "sbv": '[data-testid="search-video-in-grid"]',  # Sponsored Brand Video
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


def _parse_walmart_redirect(href: str) -> str:
    """
    Walmart redirectors:
    - https://www.walmart.com/sp/track?...&rd=
    - https://www.walmart.com/dad/trk/... (encrypted)
    Prefer rd= when present; otherwise leave as-is.
    """
    try:
        u = ul.urlparse(href)
        qs = ul.parse_qs(u.query)
        if "rd" in qs and qs["rd"]:
            return ul.unquote(qs["rd"][0])
        return href
    except Exception:
        return href


def _download(url: str, out_path: str, timeout: int = 25) -> bool:
    """Download asset (video) through proxy if configured."""
    try:
        proxies = _requests_proxies_from_env()
        # Mirror browser headers to avoid 403s
        hdrs = {
            "User-Agent": HEADERS["user-agent"],
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
    proxy_server = os.environ.get('WALMART_PROXY_SERVER')  # e.g., http://proxy.example.com:8080
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


def _launch(playwright, profile_dir: Optional[str], headless: bool = False, proxy_config: dict = None):
    """
    Returns (browser_or_None, context, page, is_persistent)
    Uses persistent context when profile_dir is provided.
    Uses persistent Chrome (channel=chrome) for maximum stealth.
    """
    # CRITICAL: NO args that trigger Chrome banners (PerimeterX flags them instantly)
    # Empty args = cleanest Chrome = best trust score
    args = []
    
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
            'ignore_default_args': ['--enable-automation'],
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
        except Exception as e:
            # WARNING: Chromium has wrong JA3 fingerprint!
            print(f"⚠️  Chrome launch failed ({e})")
            print(f"⚠️  Falling back to Chromium - JA3 fingerprint will be WRONG!")
            print(f"⚠️  PerimeterX will likely detect this as a bot!")
            print(f"⚠️  Install Chrome: brew install --cask google-chrome")
            del launch_options['channel']
            if proxy_config:
                launch_options['proxy'] = proxy_config
            ctx = playwright.chromium.launch_persistent_context(**launch_options)
        
        # Only set Accept-Language; let Chrome generate sec-* and UA dynamically
        ctx.set_extra_http_headers({"Accept-Language": "en-US,en;q=0.9"})
        
        # Telemetry - catch silent exits
        ctx.tracing.start(screenshots=True, snapshots=True, sources=False)
        ctx.on("close", lambda: print("[ctx] closed"))
        
        # --- BEGIN: off-domain guard rails ---
        # Block only TOP-LEVEL navigations to Google (allow all subresources including PX beacons)
        def _guard_nav(route):
            req = route.request
            url = req.url.lower()
            # Block only TOP-LEVEL navs to google
            if req.is_navigation_request() and ("//google." in url or "//www.google." in url):
                print(f"[blocked] Google nav: {req.url}")
                return route.abort()
            # Allow everything else (including PX beacons to *.px-cloud.net)
            return route.continue_()
        
        ctx.route("**/*", _guard_nav)
        
        # Log PX collector beacons to verify they're reaching the network
        def _log_px_beacon(req):
            u = req.url.lower()
            if "px-cloud.net" in u:
                print(f"[px] beacon -> {req.method} {req.url}")
        
        ctx.on("request", _log_px_beacon)
        # --- END: off-domain guard rails ---
        
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.on("crash", lambda: print("[page] crashed"))
        page.on("close", lambda: print("[page] closed"))
        page.on("console", lambda msg: print("[console]", msg.type, msg.text))
        
        # Apply playwright-stealth (handles fingerprinting automatically)
        # NO manual anti-fingerprinting - playwright-stealth is sufficient
        apply_stealth(page)
        
        return None, ctx, page, True
    
    browser = playwright.chromium.launch(
        headless=headless,
        args=args,
        ignore_default_args=["--enable-automation"],
        chromium_sandbox=True,  # CRITICAL: Force sandbox ON
    )
    ctx = browser.new_context(
        viewport={"width": 1366, "height": 768},
        user_agent=HEADERS["user-agent"],
        locale="en-US",
    )
    page = ctx.new_page()
    
    # Apply playwright-stealth (no manual fingerprinting)
    apply_stealth(page)
    
    return browser, ctx, page, False


def _capture_elements(page, base_dir: str, keyword: str, label: str, css: str, meta: Dict, SL=None) -> Tuple[int, List[str]]:
    shots: List[str] = []
    loc = page.locator(css)
    count = loc.count()
    for i in range(count):
        item = loc.nth(i)
        try:
            # Use native wheel scroll instead of programmatic scrollIntoView
            _bring_into_view(page, item, SL=SL)
            time.sleep(0.2)
            out = os.path.join(base_dir, safe_filename(f"{SLUG}_{keyword}_{label}_{i+1}.png"))
            item.screenshot(path=out)
            shots.append(out)
            # attempt to store a landing URL
            try:
                ahref = item.locator("a[href]").first
                if ahref.count() > 0:
                    href = ahref.get_attribute("href") or ""
                    if href:
                        meta.setdefault("links", []).append(_parse_walmart_redirect(href))
            except Exception:
                pass
            # Throttle per-element operations to avoid rapid-fire actions
            time.sleep(random.uniform(0.12, 0.28))
        except Exception:
            continue
    return count, shots


def _search_url(keyword: str) -> str:
    q = ul.quote_plus(keyword)
    return f"https://www.walmart.com/search?q={q}"


RESULT_READY_SELECTORS = [
    '[data-item-id]',
    '[data-testid="list-view"]',
    'div[data-automation="search-result-gridview-items"]'
]

def _wait_for_results(page, timeout_ms=10000):
    """Wait for search results to render."""
    deadline = time.time() + timeout_ms / 1000.0
    last = {}
    while time.time() < deadline:
        for sel in RESULT_READY_SELECTORS:
            try:
                c = page.locator(sel).count()
                last[sel] = c
                if c > 0:
                    return True, sel
            except:
                pass
        time.sleep(0.2)
    return False, f"no result selectors seen: {last}"

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

# --- BEGIN: PX modal solver v4 (steady-only, no jitter) ---
import base64

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

def _decoded_target_from_blocked(url: str):
    """Extract and decode redirect target from blocked URL."""
    try:
        u = ul.urlparse(url)
        raw = ul.parse_qs(u.query).get("url", [""])[0]
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

def _still_px_modal(page) -> bool:
    """Check if PX modal is still present."""
    try:
        return page.locator('#px-captcha').count() > 0 or \
               page.locator('iframe[title="Human verification challenge"]').count() > 0 or \
               page.locator('text=Robot or human?').count() > 0
    except Exception:
        return False

def _press_and_hold_until_complete(page, say, SL=None):
    """
    One uninterrupted steady hold until 100%.
    - Waits for widget to be visible and stable
    - Focus click once
    - Mouse down, sleep, mouse up (no movement)
    - Returns True when PX cookies present OR modal disappears
    """
    PX_HOLD_GUARD["in_progress"] = True
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

        page.mouse.move(x, y, steps=10)
        page.mouse.click(x, y, delay=random.randint(40, 120))
        time.sleep(random.uniform(0.25, 0.45))

        if t_ready < 3.0:
            low, high = 6.8, 8.2
        else:
            low, high = 8.8, 10.2

        duration = random.uniform(low, high)
        if SL: SL.log("px_hold_plan", duration=round(duration,2))
        say("info", f"[Walmart] Steady hold {duration:.2f}s (ready in {t_ready:.2f}s)")

        page.mouse.down()
        time.sleep(duration)
        page.mouse.up()
        time.sleep(random.uniform(1.4, 2.0))

        # Cookie check
        has_px, names = _wait_px_cookie(page.context, timeout_ms=8000)

        # Try to get off /blocked
        if not _force_redirect_off_blocked(page, SL=SL):
            # Give PX a moment to settle and try a soft reload once
            time.sleep(1.0)
            try:
                page.reload(wait_until="domcontentloaded")
                time.sleep(0.8)
            except Exception:
                pass

        cleared = has_px and not _still_px_modal(page)
        _mark_px_cleared(SL=SL)  # record PX clear time even if we remain cautious
        if SL: SL.log("px_hold_done", cookies_present=has_px, cookie_names=names[:6], cleared=cleared, url=page.url)
        say("info", f"[Walmart] cookies:{has_px} cleared:{cleared} names:{names[:8]}")
        return cleared
    finally:
        PX_HOLD_GUARD["in_progress"] = False
# --- END: PX modal solver ---

# --- BEGIN: PX multi-prompt controller ---
MAX_PX_SOLVES_PER_RUN = 3            # hard cap per run
PX_SOLVE_COOLDOWN_RANGE = (12, 25)   # seconds; backoff before trying again

def _still_px_challenged(page) -> bool:
    """Check if PX challenge is present (modal or /blocked)."""
    try:
        if "walmart.com/blocked" in page.url.lower():
            return True
        return page.locator('#px-captcha').count() > 0 or \
               page.locator('iframe[title="Human verification challenge"]').count() > 0 or \
               page.locator('text=Robot or human?').count() > 0 or \
               page.locator('button:has-text("PRESS & HOLD")').count() > 0
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


def search_and_capture(
    root_logger,
    activity_cb: Optional[Callable[[str, str], None]],
    base_dir: str,
    keyword: str,
    profile_dir: Optional[str] = None,
    headless: bool = False,  # Default to headed for Walmart
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
    # Initialize step logger for detailed telemetry
    SL = StepLogger(base_dir, keyword)
    
    def say(kind: str, msg: str):
        try:
            SL.log("log", level=kind, msg=msg)
            if activity_cb:
                activity_cb(kind, msg)
            elif root_logger:
                (root_logger.info if kind != "error" else root_logger.error)(msg)
            else:
                print(f"{kind.upper()}: {msg}")
        except Exception:
            pass
    
    retailer = DISPLAY_NAME
    shots: List[str] = []
    assets: List[str] = []
    meta: Dict = {"links": [], "videos": []}
    html_saved = 0
    
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
    
    # Get proxy configuration if available
    proxy_config = _get_proxy_config()
    if proxy_config:
        say("info", f"[{retailer}] Using proxy: {proxy_config.get('server', 'N/A')}")
    
    # Cookie diagnostic helper
    def _cookie_names(ctx):
        try:
            return sorted(set(c["name"] for c in ctx.cookies("https://www.walmart.com/")))
        except:
            return []
    
    with sync_playwright() as p:
        browser, ctx, page, persistent = _launch(p, profile_dir, headless=headless, proxy_config=proxy_config)
        try:
            # DIAGNOSTIC: Check cookie persistence before any navigation
            pre_cookies = _cookie_names(ctx)
            print(f"[cookies] pre-run walmart.com: {len(pre_cookies)} names={pre_cookies[:8]}")
            SL.log("cookies_pre", count=len(pre_cookies), names=pre_cookies[:8])
            
            page.set_default_timeout(15000)  # 15s
            
            # CRITICAL: Establish session with human-like browsing pattern
            say("info", f"[{retailer}] Establishing session (human-like pattern)")
            
            # 1. Visit homepage (like real users)
            page.goto("https://www.walmart.com/", wait_until="domcontentloaded")
            
            # Check for PX challenge and solve with cooldown/retry
            if _still_px_modal(page):
                SL.log("px_status", where="home", challenged=True, url=page.url)
                if _solve_px_until_clear(page, say, SL=SL):
                    say("success", f"[{retailer}] ✅ Unblocked on homepage")
                    SL.log("px_result", where="home", ok=True)
                else:
                    say("error", f"[{retailer}] Failed to clear PX after max attempts")
                    SL.log("px_result", where="home", ok=False)
                    return CaptureResult(html_saved=0, shots=[], assets=[], meta={})
            
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
                    time.sleep(random.uniform(0.2, 0.4))
                    
                    # Type with human-like delays (PerimeterX tracks keystroke timing!)
                    say("info", f"[{retailer}] Typing keyword: {keyword}")
                    for char in keyword:
                        search_box.type(char, delay=random.uniform(80, 220))  # 80-220ms per keystroke
                    
                    # Extra "thinking" pause on longer terms
                    if len(keyword) >= 10 and random.random() < 0.6:
                        time.sleep(random.uniform(0.20, 0.45))
                    
                    # CRITICAL: Dwell after typing (humans pause 600-1200ms before submit)
                    time.sleep(random.uniform(0.60, 1.20))
                    
                    # Tiny caret movement or mouse micro-move (optional, low probability)
                    if random.random() < 0.35:
                        page.keyboard.press("ArrowLeft")
                        time.sleep(random.uniform(0.08, 0.18))
                        page.keyboard.press("ArrowRight")
                    
                    # Prefer clicking the search button (varies per build)
                    clicked = False
                    for btn_sel in [
                        'button[aria-label="Search"]',
                        'button[type="submit"]',
                        '[data-automation-id="global-search-submit"]',
                        'button:has(svg[aria-hidden="true"])'  # fallback icon button
                    ]:
                        btn = page.locator(btn_sel).first
                        if btn.count() > 0:
                            # small move then click; not too precise
                            try:
                                box = btn.bounding_box()
                                if box:
                                    mx = box["x"] + box["width"] * random.uniform(0.35, 0.65)
                                    my = box["y"] + box["height"] * random.uniform(0.35, 0.65)
                                    page.mouse.move(mx, my, steps=8)
                                btn.click()
                                clicked = True
                                say("info", f"[{retailer}] Clicked search button")
                                break
                            except:
                                continue
                    
                    if not clicked:
                        # Try typeahead suggestion click before Enter fallback
                        if random.random() < 0.35:
                            sug = page.locator('[data-automation-id="typeahead"] li, [data-testid="typeahead-suggestion"]').first
                            if sug.count() > 0:
                                try:
                                    sug.click()
                                    page.wait_for_load_state('domcontentloaded')
                                    search_typed = True
                                    say("info", f"[{retailer}] Clicked typeahead suggestion")
                                    clicked = True
                                except:
                                    pass
                        
                        if not clicked:
                            # Final fallback to Enter
                            say("info", f"[{retailer}] Pressing Enter (button not found)")
                            search_box.press("Enter")
                    
                    if not search_typed:
                        page.wait_for_load_state('domcontentloaded')
                        _nav_mark_done(SL=SL)
                    search_typed = True
                    say("info", f"[{retailer}] Search completed via typing")
                else:
                    say("warn", f"[{retailer}] Search box not found, using direct navigation")
            except Exception as e:
                say("warn", f"[{retailer}] Search typing failed: {e}")
            
            # Fallback: direct navigation if typing failed
            if not search_typed:
                say("info", f"[{retailer}] Direct navigation to search URL")
                page.goto(url, wait_until="domcontentloaded")
                _nav_mark_done(SL=SL)
                say("info", f"[{retailer}] Navigation completed")
            
            # Check for PX challenge after search navigation
            if _still_px_modal(page):
                SL.log("px_status", where="search_results", challenged=True, url=page.url)
                if _solve_px_until_clear(page, say, SL=SL):
                    say("success", f"[{retailer}] ✅ Unblocked on search results")
                    SL.log("px_result", where="search_results", ok=True)
                else:
                    say("error", f"[{retailer}] Failed to clear PX on search results")
                    SL.log("px_result", where="search_results", ok=False)
                    return CaptureResult(html_saved=0, shots=[], assets=[], meta={})
            
            # Wait for results to render (avoid false "empty" detection)
            ready, which = _wait_for_results(page, timeout_ms=12000)
            SL.log("results_ready", ready=ready, selector=which, url=page.url)
            _nav_mark_done(SL=SL)  # mark nav end regardless
            say("info", f"[{retailer}] Results ready: {ready} ({which}) | url={page.url}")
            if not ready:
                # Forensics to avoid silent retry
                say("warn", f"[{retailer}] No results detected - saving forensics")
                try:
                    page.screenshot(path=os.path.join(base_dir, safe_filename(f"{SLUG}_{keyword}_no_results.png")))
                    with open(os.path.join(base_dir, safe_filename(f"{SLUG}_{keyword}_no_results.html")), "w", encoding="utf-8") as f:
                        f.write((page.content() or "")[:20000])
                except:
                    pass
            
            # Idle a beat before first scroll, then unlock scrolling
            time.sleep(random.uniform(1.6, 2.8))
            _unlock_scroll("results_ready", SL=SL)
            
            # Scroll like a human with native wheel events (PX modal handled inside)
            _scroll_like_human(page, say, bursts=random.randint(2, 4), lines_min=6, lines_max=12, SL=SL)
            
            # Hover over a product (if visible) - realistic behavior
            # Wait a bit after scroll before hovering to avoid triggering PX
            time.sleep(random.uniform(0.8, 1.3))
            if not _still_px_modal(page):
                try:
                    first_product = page.locator('[data-item-id]').first
                    if first_product.count() > 0:
                        first_product.hover()
                        time.sleep(random.uniform(0.5, 1.0))
                except:
                    pass
            
            # Simple mouse movement
            page.mouse.move(
                random.randint(300, 800),
                random.randint(400, 600)
            )
            time.sleep(random.uniform(0.2, 0.4))
            
            # Final check for PX challenge before capturing
            if _still_px_modal(page):
                SL.log("px_status", where="before_capture", challenged=True, url=page.url)
                if not _solve_px_until_clear(page, say, SL=SL):
                    say("error", f"[{retailer}] Failed to clear PX before capture")
                    SL.log("px_result", where="before_capture", ok=False)
                    return CaptureResult(html_saved=0, shots=[], assets=[], meta={})
            
            # Save HTML
            html_path = os.path.join(base_dir, safe_filename(f"{SLUG}_{keyword}_search.html"))
            try:
                content = page.content()
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(content)
                html_saved = 1
                say("info", f"[{retailer}] HTML captured (1/1)")
            except Exception as e:
                say("warn", f"[{retailer}] HTML save failed: {e}")
            
            # 1) Programmatic banners
            n, s = _capture_elements(page, base_dir, keyword, "top_banner", SELECTORS["top_banner"], meta, SL=SL)
            shots.extend(s)
            if n:
                say("info", f"[{retailer}] Top banner found ({n})")
            
            # 2) SBA
            n, s = _capture_elements(page, base_dir, keyword, "sba", SELECTORS["sba"], meta, SL=SL)
            shots.extend(s)
            if n:
                say("info", f"[{retailer}] SBA found ({n})")
            
            # 3) Tile takeover
            n, s = _capture_elements(page, base_dir, keyword, "tile_takeover", SELECTORS["tile_takeover"], meta, SL=SL)
            shots.extend(s)
            if n:
                say("info", f"[{retailer}] Tile takeover found ({n})")
            
            # 4) SBV (screenshot module + attempt mp4 download)
            sbv_mod = page.locator(SELECTORS["sbv"])
            vcount = sbv_mod.count()
            vids_saved = 0
            for i in range(vcount):
                mod = sbv_mod.nth(i)
                try:
                    mod.scroll_into_view_if_needed()
                    time.sleep(0.2)
                    out = os.path.join(base_dir, safe_filename(f"{SLUG}_{keyword}_sbv_{i+1}.png"))
                    mod.screenshot(path=out)
                    shots.append(out)
                    v = mod.locator("video").first
                    if v.count() > 0:
                        src = v.get_attribute("src") or ""
                        if src and src.startswith(("http://", "https://")):
                            vpath = os.path.join(base_dir, safe_filename(f"{SLUG}_{keyword}_sbv_{i+1}.mp4"))
                            if _download(src, vpath):
                                vids_saved += 1
                                assets.append(vpath)
                                meta["videos"].append(vpath)
                except Exception:
                    continue
            if vcount:
                say("info", f"[{retailer}] SBV found (videos {vids_saved})")
            
            # Save meta.json (links/videos)
            try:
                meta_path = os.path.join(base_dir, safe_filename(f"{SLUG}_{keyword}_meta.json"))
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2)
                assets.append(meta_path)
            except Exception:
                pass
        
        finally:
            # DIAGNOSTIC: Check cookie persistence after run
            post_cookies = _cookie_names(ctx)
            print(f"[cookies] post-run walmart.com: {len(post_cookies)} names={post_cookies[:8]}")
            SL.log("cookies_post", count=len(post_cookies), names=post_cookies[:8])
            
            # Save trace for debugging silent exits
            try:
                trace_path = os.path.join(base_dir, safe_filename(f"{SLUG}_{keyword}_trace.zip"))
                ctx.tracing.stop(path=trace_path)
                print(f"[trace] saved → {trace_path}")
            except Exception as e:
                print(f"[trace] stop failed: {e}")
            
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
    SL.log("run_complete", html_saved=html_saved, shots_count=len(shots), assets_count=len(assets))
    
    return CaptureResult(html_saved=html_saved, shots=shots, assets=assets, meta=meta)
