"""Kroger Search and Capture Script

This script performs Kroger search operations and captures results by:
1. Checking for existing cookies
2. Launching browser with persistent context
3. Verifying login status
4. Performing a search query
5. Capturing screenshots and HTML of search results
6. Saving data for later processing

The captured HTML can be processed by process_saved_html.py to extract TOA data.
"""

import os
import random
from datetime import datetime
import subprocess
import time
import json
import urllib.parse
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright
from browser_lock import single_browser_lock
from playwright._impl._errors import Error as PWError
from Kroger_login import save_cookies  # Removed load_cookies as it's redundant with user_data_dir
from filename_utils import generate_ad_filename
from core.brands import canonicalize, add_brand
from utils.profile_health import check_and_record, record_login_outcome, should_bail, send_relogin_alert
from utils.kroger_diagnostics import KrogerDiagnostics

# Brand logo database for centralized logo storage
# Note: Kroger TOA ads are product carousels without brand logos.
# This import is for future use if Kroger adds banner ads with logos.
try:
    from brand_logo_database import BrandLogoDatabase
except ImportError:
    BrandLogoDatabase = None

# Constants for file paths
PROJECT_ROOT = Path(__file__).resolve().parent

# Constants
USER_DATA_DIR = os.path.expanduser("~/ChromeProfiles/kroger_clean_profile")
DEFAULT_SEARCH_TERM = "black forest ham"
DEFAULT_OUTPUT_DIR = "output"

# --- Human Behavior Simulation (ported from Walmart) ---
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

def scroll_like_human(page, bursts=2, lines_min=4, lines_max=8):
    """Natural wheel scrolling with random bursts."""
    for _ in range(bursts):
        lines = random.randint(lines_min, lines_max)
        for _ in range(lines):
            page.mouse.wheel(0, random.randint(48, 140))
            time.sleep(random.uniform(0.045, 0.12))
        time.sleep(random.uniform(0.25, 0.9))

def drift_reading(page, seconds=2.0):
    """Simulate reading by pausing with occasional micro mouse movements."""
    end_time = time.time() + seconds
    while time.time() < end_time:
        if random.random() < 0.3:
            micro_mouse_attention(page, around=(3, 6), jitter=5)
        time.sleep(random.uniform(0.3, 0.7))

def backscroll_peek(page):
    """Scroll up a bit then back down (human curiosity behavior)."""
    if random.random() < 0.4:
        for _ in range(random.randint(2, 4)):
            page.mouse.wheel(0, -random.randint(60, 120))
            time.sleep(random.uniform(0.05, 0.1))
        time.sleep(random.uniform(0.4, 0.8))
        for _ in range(random.randint(2, 4)):
            page.mouse.wheel(0, random.randint(60, 120))
            time.sleep(random.uniform(0.05, 0.1))

# --- End Human Behavior Simulation ---

def pick_app_frame(page):
    """Safely pick the best frame to use for DOM operations
    
    Args:
        page: Playwright page object
        
    Returns:
        The best frame to use for DOM operations
    """
    # Prefer top frame if it has a real DOM
    top = page.main_frame
    try:
        has_dom = top.evaluate("() => !!document.body && document.body.children.length > 0")
        if has_dom:
            print(f"Using main frame: {top.url}")
            return top
    except PWError:
        pass

    # Otherwise look for a frame that actually has Kroger's root/app
    for f in page.frames:
        if f is top:
            continue
        try:
            if f.url and "kroger.com" in f.url:
                ok = f.evaluate("() => !!document.querySelector('#root') || !!document.body")
                if ok:
                    print(f"Using Kroger frame: {f.url}")
                    return f
        except PWError:
            continue
    
    print(f"Falling back to main frame: {top.url}")
    return top  # fallback

def eval_safe(page, script, retries=3):
    """Safely evaluate JavaScript in the best available frame
    
    Args:
        page: Playwright page object
        script: JavaScript to evaluate
        retries: Number of retries if frame detaches
        
    Returns:
        Result of the evaluation
    """
    for attempt in range(retries):
        app = pick_app_frame(page)
        try:
            return app.evaluate(script)
        except PWError as e:
            if "Frame was detached" in str(e) and attempt < retries - 1:
                print("   Frame detached; re-picking frame and retrying...")
                page.wait_for_load_state("domcontentloaded")
                continue
            raise

# ---------------------------------------------------------------------------
# Human-like interaction helpers (ported from Walmart's proven cadence)
# ---------------------------------------------------------------------------

def _human_type(element, text: str):
    """Type with human-like per-character delays and occasional micro-pauses."""
    for ch in text:
        element.type(ch, delay=random.uniform(80, 220))
        if random.random() < 0.10:
            time.sleep(random.uniform(0.05, 0.15))
    # Longer words get a natural trailing pause
    if len(text) >= 10 and random.random() < 0.6:
        time.sleep(random.uniform(0.20, 0.45))


def _micro_mouse_attention(page, around=(8, 15), jitter=10):
    """Subtle mouse micro-movements to simulate reading/attention."""
    try:
        pos = page.mouse.position
        mx, my = pos['x'], pos['y']
    except Exception:
        mx, my = (random.randint(300, 700), random.randint(300, 600))
    steps = random.randint(*around)
    for _ in range(steps):
        dx = random.randint(-jitter, jitter)
        dy = random.randint(-jitter, jitter)
        mx += dx
        my += dy
        page.mouse.move(mx, my)
        time.sleep(random.uniform(0.01, 0.03))


def _random_delay(a=0.6, b=1.4):
    """Random delay between actions."""
    time.sleep(random.uniform(a, b))


def _scroll_burst_wheel(page, lines=8):
    """Emit a small burst of native wheel events (trackpad-like)."""
    for _ in range(lines):
        page.mouse.wheel(0, random.randint(48, 140))
        time.sleep(random.uniform(0.045, 0.12))


def _scroll_like_human(page, bursts=3, lines_min=6, lines_max=12,
                       pause_min=0.25, pause_max=0.9):
    """Several short wheel bursts with pauses — feels like a real user scrolling."""
    for b in range(bursts):
        _scroll_burst_wheel(page, lines=random.randint(lines_min, lines_max))
        time.sleep(random.uniform(pause_min, pause_max))
        # First burst: longer idle to avoid action-storm fingerprint
        if b == 0:
            time.sleep(random.uniform(1.0, 2.2))


def _drift_reading(page, seconds=2.0):
    """Simulate idle reading — small mouse drifts, no scrolling."""
    t0 = time.time()
    while time.time() - t0 < seconds:
        _micro_mouse_attention(page, around=(3, 6), jitter=5)
        time.sleep(random.uniform(0.3, 0.7))


def _backscroll_peek(page, chance=0.35):
    """Occasionally scroll back up slightly, like re-reading."""
    if random.random() < chance:
        page.mouse.wheel(0, random.randint(-200, -60))
        time.sleep(random.uniform(0.4, 0.8))


def scroll_results(page, max_loops=120, step_ratio=0.85, sleep_ms=300):
    """
    Scroll the top-level document in controlled steps, backing off when no progress.
    Returns basic scroll info.
    """
    return page.evaluate(
        """
        async ({ maxLoops, stepRatio, sleepMs }) => {
          const sleep = (ms) => new Promise(r => setTimeout(r, ms));

          const scrollEl = document.scrollingElement || document.documentElement || document.body;
          const step = Math.max(200, Math.floor(window.innerHeight * stepRatio));
          let stagnant = 0;
          let lastY = scrollEl.scrollTop;
          let lastProducts = 0;
          let steps = 0;

          // Wait for grid to show up (best effort, 10s)
          const start = Date.now();
          while (
            document.querySelectorAll('[data-testid*="product"], [class*="product-card"]').length === 0 &&
            Date.now() - start < 10000
          ) {
            await sleep(250);
          }

          for (let i = 0; i < maxLoops && stagnant < 5; i++) {
            // Use absolute target (helps when lazy-load inserts content)
            const targetY = (i + 1) * step;
            window.scrollTo(0, targetY);
            await sleep(sleepMs + Math.floor(Math.random() * 150)); // tiny jitter

            const y = scrollEl.scrollTop;
            const h = scrollEl.scrollHeight;
            const products = document.querySelectorAll('[data-testid*="product"], [class*="product-card"]').length;

            steps++;
            
            const moved = Math.abs(y - lastY) >= 2;
            const grew = products > lastProducts;
            const atBottom = y + window.innerHeight >= h - 10;

            if (atBottom || (!moved && !grew)) {
              stagnant++;
            } else {
              stagnant = 0;
            }

            lastY = y;
            lastProducts = products;

            if (atBottom) break;
          }
        
          // Always scroll back to top before returning
          console.log('Scrolling back to top...');
          window.scrollTo(0, 0);
          await sleep(250); // Wait for scroll to complete
        
          // Verify we're at the top
          const finalY = (document.scrollingElement || document.documentElement || document.body).scrollTop;
          const finalH = (document.scrollingElement || document.documentElement || document.body).scrollHeight;
          console.log(`After scrolling back to top: Y=${finalY} of ${finalH}`);

          return {
            finalY: finalY,
            finalH: finalH,
            steps: steps
          };
        }
        """,
        {"maxLoops": max_loops, "stepRatio": step_ratio, "sleepMs": sleep_ms},
    )

def dismiss_kroger_popups(page):
    """Best-effort removal of Kroger modals/popups (esp. X-only modal) and unlock scrolling.

    Strategy:
    - Click likely close/accept buttons (including the X in the modal header).
    - Remove common overlays/backdrops and re-enable scrolling.
    - Run in top frame and all child frames.
    - Attach a short MutationObserver to auto-dismiss popups that appear right after navigation.
    """
    try:
        selectors = [
            '#onetrust-accept-btn-handler',                # OneTrust
            '.truste_accept',                              # TrustArc
            'button:has-text("Accept All Cookies")',
            'button:has-text("Accept All")',
            'button:has-text("Accept")',
            'button:has-text("I Agree")',
            'button:has-text("Got it")',
            'button:has-text("Got It")',
            'button:has-text("I Understand")',
            'button:has-text("OK")',
            'button:has-text("Dismiss")',
            'button:has-text("No thanks")',
            '[data-testid="ModalClose"]',
            '[data-testid="close"]',
            '[data-testid="Close"]',
            'button[aria-label="Close"]',
            '[aria-label="Close"]',
            '.kds-Modal [aria-label="Close"]',           # Kroger KDS modal close
            '.kds-IconButton[aria-label="Close"]',       # Common X button
            'button[aria-label="Close pop-up"]',         # Specific button from your markup
            '.kds-Modal-closeButton',                      # KDS modal close button class
            'button.kds-DismissalButton',                  # KDS dismissal button
            '.kds-DismissalButton.kds-Modal-closeButton',  # Combined KDS classes
        ]

        def try_frame(f):
            try:
                # Two quick passes: click close buttons, then clean overlays
                for _ in range(2):
                    for sel in selectors:
                        try:
                            loc = f.locator(sel).first
                            if loc.is_visible():
                                loc.click(force=True, timeout=800)
                                f.wait_for_timeout(200)
                        except Exception:
                            pass
                    try:
                        f.evaluate(
                            """
                            () => {
                                const kill = (el) => { try { el.remove(); } catch (e) {} };
                                const qs = [
                                  '#onetrust-banner-sdk', '.ot-sdk-container', '.kds-Modal',
                                  '[role="dialog"]', '[aria-modal="true"]', '.modal-backdrop',
                                  '.Modal', '.modal', '.backdrop'
                                ];
                                qs.forEach(s => document.querySelectorAll(s).forEach(kill));
                                try { document.body.style.overflow = 'auto'; } catch (e) {}
                            }
                            """
                        )
                    except Exception:
                        pass
                    f.wait_for_timeout(150)

                # Send an Escape keypress in-frame as a final fallback
                try:
                    f.evaluate(
                        """
                        () => {
                          try {
                            document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', keyCode: 27, which: 27, bubbles: true }));
                            document.dispatchEvent(new KeyboardEvent('keyup', { key: 'Escape', keyCode: 27, which: 27, bubbles: true }));
                          } catch (e) {}
                        }
                        """
                    )
                except Exception:
                    pass

                # Short MutationObserver window (2s) to auto-dismiss newly-added dialogs
                try:
                    f.evaluate(
                        """
                        () => {
                          if (window.__kdsObserver) return; // prevent duplicates
                          const closeCandidates = () => {
                            const sels = [
                              'button[aria-label="Close"]', '[aria-label="Close"]', '.kds-Modal [aria-label="Close"]',
                              '#onetrust-accept-btn-handler', '.truste_accept'
                            ];
                            for (const s of sels) {
                              const el = document.querySelector(s);
                              if (el) { try { el.click(); } catch (e) {} }
                            }
                          };
                          closeCandidates();
                          const mo = new MutationObserver(() => closeCandidates());
                          mo.observe(document.documentElement, { childList: true, subtree: true });
                          window.__kdsObserver = mo;
                          setTimeout(() => { try { mo.disconnect(); delete window.__kdsObserver; } catch(e) {} }, 2000);
                        }
                        """
                    )
                except Exception:
                    pass
            except Exception:
                pass

        # Run for main page and child frames
        try_frame(page)
        for fr in page.frames:
            try:
                if fr is not page.main_frame:
                    try_frame(fr)
            except Exception:
                pass
    except Exception:
        pass

def goto_with_retries(page, url: str, attempts: int = 3, wait_until: str = "domcontentloaded", timeout_ms: int = 30000):
    """Navigate with retries to mitigate transient Chromium errors (e.g., HTTP/2 protocol errors)."""
    last_err = None
    for i in range(1, attempts + 1):
        try:
            page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            return True
        except Exception as e:
            last_err = e
            print(f"   goto error ({i}/{attempts}) -> {e}")
            try:
                page.wait_for_timeout(1000)
            except Exception:
                pass
    if last_err:
        raise last_err
    return False

def chromium_count(target_profile: str = USER_DATA_DIR):
    """Return number of Chromium/Chrome processes that are actually using our shared profile.

    We filter by the user-data-dir path or its basename to avoid counting unrelated
    Chromium Embedded Framework apps or other Chrome instances.
    """
    try:
        r = subprocess.run(["ps", "ax", "-o", "pid=,command="], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        if r.returncode != 0 or not r.stdout:
            return 0
        prof = os.path.normpath(target_profile)
        prof_base = os.path.basename(prof)
        count = 0
        for line in r.stdout.splitlines():
            cmd = line.strip()
            # Only consider Chrome/Chromium-like commands
            if ("Chrom" in cmd) or ("HeadlessChrome" in cmd) or ("playwright" in cmd and "chrom" in cmd.lower()):
                if prof in cmd or (prof_base and prof_base in cmd):
                    count += 1
        return count
    except Exception:
        return 0


def ensure_low_chromium(threshold=1, timeout=60, poll=1.0):
    """Wait until our-profile Chromium processes <= threshold. Return True if ok, False otherwise."""
    deadline = time.time() + timeout
    while time.time() < deadline:
            # Only count processes tied to our shared profile to avoid blocking on unrelated apps
        if chromium_count(USER_DATA_DIR) <= threshold:
            return True
        time.sleep(poll)
    return chromium_count(USER_DATA_DIR) <= threshold

def _sanitize_name(name: str):
    return ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in (name or '')).strip('_')


def _derive_client_from_output_dir(output_dir: str):
    """
    Derive client name from output directory path.
    Handles both old (output/<client>) and new (output/<retailer>/<client>) layouts.
    """
    try:
        parts = os.path.normpath(output_dir or '').split(os.sep)
        try:
            idx = parts.index("output")
            # New layout: output/<retailer>/<client>
            known_retailers = {'kroger', 'walmart', 'amazon', 'instacart', 'target', 'albertsons'}
            if idx + 2 < len(parts) and parts[idx + 1].lower() in known_retailers:
                client = parts[idx + 2]
                if client and client not in ('runs', 'output', ''):
                    return client
            # Old layout: output/<client>
            if idx + 1 < len(parts):
                client = parts[idx + 1]
                if client and client not in ('runs', 'output', ''):
                    return client
        except ValueError:
            pass
        
        # Fallback: basename
        base = os.path.basename(os.path.normpath(output_dir or ''))
        if base and base != 'output':
            return base
    except Exception:
        pass
    return None


def _launch_context_resilient(pw, client_name: str):
    """Launch a single shared persistent context using the common profile only."""
    # Pre-launch guard: if other Chrome processes are present for our profile, warn but continue.
    # The global file lock will serialize actual launches across our tools.
    if not ensure_low_chromium(threshold=1, timeout=60):
        print("⚠️ Detected other Chrome/Chromium processes using the shared profile. Proceeding due to global lock; launch may wait or reuse session.")
    # Use the system Chrome channel exclusively with our shared profile.
    # Mixing different Chromium builds with the same user_data_dir can break session persistence.
    candidates = [
        {"user_data_dir": USER_DATA_DIR, "channel": "chrome"},
    ]
    last_error = None
    for cand in candidates:
        try:
            print(f"   Attempting persistent context with profile: {cand['user_data_dir']} channel={cand['channel'] or 'default'}")
            ctx = pw.chromium.launch_persistent_context(
                user_data_dir=cand['user_data_dir'],
                headless=False,
                channel=cand['channel'],
                ignore_https_errors=True,
                ignore_default_args=['--enable-automation'],  # CRITICAL: Prevents navigator.webdriver=true
                chromium_sandbox=True,  # CRITICAL: Enables sandbox (no --no-sandbox banner)
                args=[
                    # Chrome 145-compatible args only (9 old flags removed — they crash Chrome 145)
                    # NOTE: --no-sandbox REMOVED - conflicts with chromium_sandbox=True and triggers Akamai
                    # NOTE: --disable-blink-features=AutomationControlled REMOVED - unsupported in Chrome 145, causes instability
                    "--disable-dev-shm-usage",
                    "--disable-infobars",
                    "--no-first-run",
                    "--disable-default-apps",
                    "--disable-backgrounding-occluded-windows",
                    "--window-size=1280,720",
                    "--disable-notifications",
                    "--disable-quic",
                    "--noerrdialogs",
                    # GPU acceleration args (CRITICAL: Prevents SwiftShader software rendering)
                    "--use-angle=metal",  # Force ANGLE→Metal backend on macOS
                    "--enable-gpu-rasterization",  # Prefer GPU raster
                    "--ignore-gpu-blocklist",  # Don't let Chrome silently disable GPU
                ],
            )
            # CRITICAL: Force navigator.webdriver to undefined (ignore_default_args doesn't always work with persistent context)
            ctx.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            
            # WORKAROUND: Navigate to dummy page first to ensure init script takes effect
            # The init script only applies to pages created AFTER it's called
            # Initial about:blank page has webdriver=true, so we navigate away and back
            try:
                dummy_page = ctx.pages[0] if ctx.pages else ctx.new_page()
                dummy_page.goto("data:text/html,<html><body>Initializing...</body></html>", wait_until="domcontentloaded", timeout=5000)
                dummy_page.wait_for_timeout(500)  # Let override settle
            except Exception:
                pass  # Non-fatal if dummy navigation fails
            
            print(f"   ✅ Launched persistent context using profile: {cand['user_data_dir']}")
            return ctx
        except Exception as e:
            last_error = e
            print(f"   ⚠️ Persistent launch failed: {e}")
            continue
    # If all persistent attempts fail, raise the last error rather than creating a separate session
    if last_error:
        raise last_error
    raise RuntimeError("Failed to launch persistent context with shared profile")


def is_kroger_logged_in(page) -> bool:
    """Heuristic to detect Kroger login state from header menu.

    Returns True if Sign In controls are not visible; False if explicit Sign In is present.
    """
    try:
        # Prefer explicit Sign In button in welcome menu if present
        if page.locator('[data-testid="WelcomeMenuButtonSignIn"]').first.is_visible():
            return False
    except Exception:
        pass
    try:
        # Fallback: visible Sign In text in header
        if page.get_by_text("Sign In", exact=True).first.is_visible():
            return False
    except Exception:
        pass
    # Otherwise assume logged in
    return True


def search_and_capture(search_term=None, output_dir=None):
    """Test if the session persists between browser launches"""
    # Use a dict to store paths for post-processing (mutable container accessible everywhere)
    paths = {'html': None, 'output': None}
    print("\n" + "="*50)
    print("KROGER SEARCH AND CAPTURE")
    print("="*50)
    
    # Use default search term if none provided
    if search_term is None:
        search_term = DEFAULT_SEARCH_TERM
    
    # Use default output directory if none provided
    if output_dir is None:
        output_dir = DEFAULT_OUTPUT_DIR
        
    print(f"Search term: {search_term}")
    print(f"Output directory: {output_dir}")
    
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    
    # Initialize diagnostic logging for this run
    diag = KrogerDiagnostics(output_dir=output_dir, run_id=timestamp.replace("-", "").replace("_", ""))
    diag.log("search_and_capture_start", search_term=search_term, output_dir=output_dir)
    os.makedirs(output_dir, exist_ok=True)
    
    # Step 1: Check if cookies exist
    print("\n📋 Step 1: Checking for existing cookies...")
    cookie_file = "cookies_kroger.json"
    cookies_exist = os.path.exists(cookie_file)
    
    if cookies_exist:
        with open(cookie_file, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        print("✅ Found cookie file with {} cookies".format(len(cookies)))
    else:
        print("⚠️ No cookie file found - will need to create one")
    
    # Step 2: Launch browser and check login status
    print("\n🔐 Step 2: Checking login status...")
    # Variable to store html_path for post-processing after browser lock is released
    saved_html_path = None
    saved_output_dir = output_dir
    
    # Enforce a single Chromium across all processes
    with single_browser_lock(timeout=600):
        with sync_playwright() as p:
            client_name = _derive_client_from_output_dir(output_dir)
            print(f"Browser launch: client context = {client_name or 'unknown'}")
            context = _launch_context_resilient(p, client_name)

            try:
                page = context.pages[0] if context.pages else context.new_page()
                diag.log("browser_launched", pages=len(context.pages))

                # Be more lenient with transient network delays
                try:
                    context.set_default_navigation_timeout(45000)
                except Exception:
                    pass
                
                # Track pre-run cookies for reputation analysis
                diag.track_cookies(context, "pre")
                
                # Collect initial diagnostics before navigation
                diag.collect_diagnostics(page, context, "before_navigation")

                # Early bail: if profile is already known-blocked, skip the browser work
                if should_bail("kroger"):
                    print("⚠️ Kroger profile is blocked (consecutive failures). Skipping scrape.")
                    print("   Run the profile in a real Chrome window to clear the block.")
                    send_relogin_alert("kroger", "consecutive_failures")
                    return False

                # Navigate to Kroger homepage (non-fatal; continue even if it fails)
                try:
                    diag.log("homepage_navigation_start", url="https://www.kroger.com/")
                    goto_with_retries(page, "https://www.kroger.com/", attempts=4, wait_until="domcontentloaded", timeout_ms=45000)
                    page.wait_for_timeout(5000)
                    diag.log("homepage_loaded", url=page.url)
                    
                    # Track timing to homepage
                    diag.track_timing("to_home_ms")
                    
                    # Capture environment info
                    try:
                        ua = page.evaluate("() => navigator.userAgent")
                        diag.env_info["ua"] = ua
                    except Exception:
                        pass
                    
                    try:
                        webgl_vendor = page.evaluate("() => { const gl = document.createElement('canvas').getContext('webgl'); return gl ? gl.getParameter(gl.VENDOR) : null; }")
                        webgl_renderer = page.evaluate("() => { const gl = document.createElement('canvas').getContext('webgl'); const ext = gl ? gl.getExtension('WEBGL_debug_renderer_info') : null; return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : null; }")
                        diag.env_info["webgl"] = {"vendor": webgl_vendor, "renderer": webgl_renderer}
                    except Exception:
                        pass
                    
                    # Collect diagnostics after homepage load
                    diag.collect_diagnostics(page, context, "after_homepage_load")
                    
                    # Check for Akamai block
                    is_blocked, reason, details = diag.check_akamai_block(page)
                    if is_blocked:
                        diag.save_forensics(page, "blocked_at_homepage")
                        print(f"❌ AKAMAI BLOCK DETECTED AT HOMEPAGE: {reason} - {details}")
                        diag.finalize()
                        return False
                    
                    # Dismiss any homepage popups
                    dismiss_kroger_popups(page)
                except Exception as e:
                    diag.log("homepage_navigation_error", error=str(e))
                    print(f"   Homepage navigate failed: {e} — proceeding directly to search.")

                # Logged-in check
                try:
                    is_logged_in = not page.is_visible("text=Sign In")
                except Exception:
                    is_logged_in = False
                
                diag.log("login_check", is_logged_in=is_logged_in)
                
                if is_logged_in:
                    print("✅ Logged in session detected.")
                else:
                    print("⚠️ Not logged in. Attempting interactive login once...")
                    try:
                        dismiss_kroger_popups(page)
                        # Open sign-in menu and click Sign In
                        # Header sign-in text
                        try:
                            page.get_by_text("Sign In", exact=True).first.click(timeout=3000)
                            page.wait_for_timeout(800)
                        except Exception:
                            pass
                        # Welcome menu sign-in button
                        try:
                            page.locator('[data-testid="WelcomeMenuButtonSignIn"]').first.click(timeout=3000)
                        except Exception:
                            pass
                        print("   Please complete login in the browser window (waiting up to 90s)...")
                        # Give time for user login; keep dismissing popups
                        for _ in range(18):  # ~90s total
                            dismiss_kroger_popups(page)
                            try:
                                if not page.is_visible("text=Sign In"):
                                    is_logged_in = True
                                    break
                            except Exception:
                                pass
                            page.wait_for_timeout(5000)
                        if is_logged_in:
                            print("✅ Login detected; saving cookies snapshot as backup")
                            try:
                                save_cookies(context)
                            except Exception as e:
                                print(f"   Note: could not save cookies backup: {e}")
                        else:
                            print("❌ Still not logged in after waiting.")
                            try:
                                from utils.profile_health import prompt_relogin
                                _relogged = prompt_relogin(page, "kroger", search_term)
                                if _relogged:
                                    print("✅ User completed re-login — continuing")
                                    is_logged_in = True
                                else:
                                    if should_bail("kroger"):
                                        print("   Profile needs manual re-login. Aborting scrape.")
                                        return False
                                    print("   Will proceed but some content may be limited.")
                            except Exception:
                                stale, _ = record_login_outcome("kroger", search_term, logged_in=False)
                                if should_bail("kroger"):
                                    print("   Profile needs manual re-login. Aborting scrape.")
                                    return False
                                print("   Will proceed but some content may be limited.")
                    except Exception as e:
                        print(f"   Login attempt encountered an issue: {e}")

                # Step 3: Perform the search query (organic search box — Walmart cadence)
                print("\n🔎 Step 3: Performing search...")
                diag.log("search_step_start", search_term=search_term)
                
                # CRITICAL: Initial homepage dwell to show browsing intent (Akamai Jan 2026 update)
                # Akamai's intent-based detection flags instant searches as scraping
                print("   Initial browsing simulation...")
                diag.log("browsing_simulation_start")
                random_delay(3.0, 6.0)  # Humans browse before searching
                
                # Optional: Scroll homepage a bit (shows exploration intent)
                if random.random() < 0.5:
                    diag.log("homepage_scroll_start")
                    scroll_like_human(page, bursts=1, lines_min=2, lines_max=4)
                    random_delay(1.0, 2.0)
                    diag.log("homepage_scroll_complete")
                
                _search_typed = False
                try:
                    # Kroger search box selectors (try multiple)
                    _search_sels = [
                        'input[data-testid="SearchBox-input"]',
                        'input[aria-label="search"]',
                        'input[name="query"]',
                        'input[type="search"]',
                        '#SearchBox-input',
                        'input[placeholder*="Search"]',
                    ]
                    _box = None
                    _matched_sel = None
                    for _sel in _search_sels:
                        try:
                            _candidate = page.locator(_sel).first
                            if _candidate.is_visible(timeout=2000):
                                _box = _candidate
                                _matched_sel = _sel
                                break
                        except Exception:
                            continue

                    if not _box:
                        # Some Kroger pages hide the input behind a search icon
                        print("   ⚠️ Search box not visible — trying search icon first")
                        for _btn_sel in [
                            '[data-testid="SearchBox-button"]',
                            'button[aria-label="search"]',
                            '[data-testid="SearchIcon"]',
                        ]:
                            try:
                                _btn = page.locator(_btn_sel).first
                                if _btn.is_visible(timeout=2000):
                                    _btn.click()
                                    page.wait_for_timeout(1000)
                                    # Re-check inputs
                                    for _sel in _search_sels:
                                        try:
                                            _candidate = page.locator(_sel).first
                                            if _candidate.is_visible(timeout=2000):
                                                _box = _candidate
                                                _matched_sel = _sel
                                                break
                                        except Exception:
                                            continue
                                    if _box:
                                        break
                            except Exception:
                                continue

                    if _box:
                        # --- Walmart-proven cadence ---
                        # 1) Click search box
                        print(f"   Found search box: {_matched_sel}")
                        diag.log("search_box_click", selector=_matched_sel)
                        _box.click()
                        random_delay(0.2, 0.4)

                        # 2) Pre-type dwell (adds entropy — avoids "home → submit in ~4s")
                        time.sleep(random.uniform(2.0, 4.0))

                        # 3) Clear any stale text, then human-type
                        _box.fill("")
                        random_delay(0.15, 0.35)
                        print(f"   Typing: {search_term}")
                        diag.log("search_typing_start", search_term=search_term)
                        human_type(_box, search_term)
                        diag.log("search_typing_complete")

                        # 4) Post-type dwell (humans pause before submitting)
                        random_delay(0.60, 1.20)

                        # 5) Subtle mouse movement (40% chance)
                        if random.random() < 0.4:
                            micro_mouse_attention(page, around=(5, 9), jitter=6)

                        # 6) Submit: prefer clicking a visible search button
                        _submitted = False
                        for _btn_sel in [
                            'button[data-testid="SearchBox-submitButton"]',
                            'button[aria-label="search"]',
                            'button[type="submit"]',
                        ]:
                            try:
                                _btn = page.locator(_btn_sel).first
                                if _btn.is_visible(timeout=1500):
                                    # Move mouse to button naturally
                                    try:
                                        _bbox = _btn.bounding_box()
                                        if _bbox:
                                            _mx = _bbox["x"] + _bbox["width"] * random.uniform(0.3, 0.7)
                                            _my = _bbox["y"] + _bbox["height"] * random.uniform(0.3, 0.7)
                                            page.mouse.move(_mx, _my, steps=random.randint(6, 12))
                                            random_delay(0.05, 0.12)
                                    except Exception:
                                        pass
                                    _btn.click()
                                    _submitted = True
                                    diag.log("search_submitted", method="button", selector=_btn_sel)
                                    print(f"   ✅ Submitted via button ({_btn_sel})")
                                    break
                            except Exception:
                                continue

                        # 7) Fallback: press Enter (double-Enter for typeahead dismiss)
                        if not _submitted:
                            try:
                                _box.focus()
                            except Exception:
                                try:
                                    _box.click()
                                except Exception:
                                    pass
                            page.keyboard.press("Enter")
                            time.sleep(random.uniform(0.25, 0.6))
                            # Second Enter in case the first just closed autocomplete
                            page.keyboard.press("Enter")
                            diag.log("search_submitted", method="enter_key")
                            print("   ✅ Submitted via Enter key")

                        # 8) Wait for search results page to load
                        try:
                            page.wait_for_load_state("domcontentloaded", timeout=30000)
                        except Exception:
                            pass
                        page.wait_for_timeout(random.randint(2500, 4000))
                        
                        diag.log("search_results_loaded", url=page.url)
                        
                        # Collect diagnostics after search results load
                        diag.collect_diagnostics(page, context, "after_search_results")
                        
                        # Check for Akamai block on search results
                        is_blocked, reason, details = diag.check_akamai_block(page)
                        if is_blocked:
                            diag.save_forensics(page, "blocked_at_search_results")
                            print(f"❌ AKAMAI BLOCK DETECTED AT SEARCH RESULTS: {reason} - {details}")
                            diag.finalize()
                            return False

                        _search_typed = True
                    else:
                        print("   ⚠️ Could not find search box at all")

                except Exception as _search_err:
                    print(f"   ⚠️ Organic search failed: {_search_err}")

                if not _search_typed:
                    # Fallback: direct URL (may trigger Akamai)
                    print("   ⚠️ Falling back to direct URL navigation")
                    diag.log("search_fallback_url", method="direct_navigation")
                    search_url = "https://www.kroger.com/search?query={}".format(urllib.parse.quote_plus(search_term))
                    goto_with_retries(page, search_url, attempts=4, wait_until="domcontentloaded", timeout_ms=45000)
                    
                    # Check for block after direct navigation
                    is_blocked, reason, details = diag.check_akamai_block(page)
                    if is_blocked:
                        diag.save_forensics(page, "blocked_at_direct_navigation")
                        print(f"❌ AKAMAI BLOCK DETECTED AFTER DIRECT NAVIGATION: {reason} - {details}")
                        diag.finalize()
                        return False

                # Dismiss any search-page popups
                dismiss_kroger_popups(page)

                # Short readiness wait (whichever happens first)
                print("   Waiting for page to be ready...")
                try:
                    page.evaluate(
                        """
                        async () => {
                            return await Promise.race([
                                new Promise(resolve => {
                                    const checkProducts = () => {
                                        const products = document.querySelectorAll('[data-testid*="product"], [class*="product-card"]');
                                        if (products.length > 0) { resolve('products_found'); return true; }
                                        return false;
                                    };
                                    if (checkProducts()) return;
                                    let attempts = 0;
                                    const interval = setInterval(() => {
                                        attempts++;
                                        if (checkProducts() || attempts >= 50) {
                                            clearInterval(interval);
                                            if (attempts >= 50) resolve('products_timeout');
                                            else resolve('products_found');
                                        }
                                    }, 300);
                                }),
                                new Promise(resolve => {
                                    if (document.readyState === 'complete' || document.querySelectorAll('body *').length > 50) {
                                        resolve('dom_ready');
                                    } else {
                                        window.addEventListener('DOMContentLoaded', () => resolve('dom_loaded'));
                                        setTimeout(() => resolve('dom_timeout'), 3000);
                                    }
                                })
                            ]);
                        }
                        """
                    )
                    print("   Page is ready for scrolling")
                except Exception as e:
                    print(f"   Readiness wait error: {e} - continuing anyway")
                # One more pass in case a modal popped during readiness wait
                dismiss_kroger_popups(page)

                # Log page and frames
                print(f"page.url: {page.url}")
                print("Frames:\n" + "\n".join([f"  - {f.url or '<no url>'}" for f in page.frames]))

                # Create sanitized search term for filenames
                safe_search_term = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in search_term)

                # Wait a bit longer for stability
                print("   Waiting for page to stabilize...")
                page.wait_for_timeout(5000)  # Reduced from 10000ms to 5000ms
                
                # Verify products actually loaded
                product_count = page.evaluate("""
                    () => document.querySelectorAll('[data-testid*="product"], [class*="product-card"]').length
                """)
                diag.log("products_check", count=product_count)
                
                if product_count == 0:
                    print(f"   ⚠️ WARNING: No product elements found after waiting")
                    # Take screenshot to see what's actually on the page
                    diag.save_forensics(page, "no_products_initial")
                    print(f"   📸 Screenshot saved to diagnostics - check what Kroger is showing")
                    print(f"   Page may not have fully hydrated - waiting additional 10 seconds...")
                    page.wait_for_timeout(10000)
                    
                    # Check again
                    product_count = page.evaluate("""
                        () => document.querySelectorAll('[data-testid*="product"], [class*="product-card"]').length
                    """)
                    diag.log("products_recheck", count=product_count)
                    
                    if product_count == 0:
                        print(f"   ❌ Still no products found - page failed to hydrate")
                        diag.save_forensics(page, "no_products_hydrated")
                        print(f"   📸 Second screenshot saved - check for error messages")
                    else:
                        print(f"   ✅ Found {product_count} products after extended wait")
                else:
                    print(f"   ✅ Found {product_count} products on page")

                # Confirm still logged in
                is_still_logged_in = not page.is_visible("text=Sign In")
                if not is_still_logged_in:
                    print("❌ Session lost during search")
                    record_login_outcome("kroger", search_term, logged_in=False)
                    return False
                print("✅ Still logged in after search")

                # Prepare output dirs and filenames
                file_prefix = f"search_results_{safe_search_term}_{timestamp}"
                main_dir = os.path.join(output_dir, "main")
                toa_dir = os.path.join(output_dir, "TOA")
                os.makedirs(main_dir, exist_ok=True)
                os.makedirs(toa_dir, exist_ok=True)

                # Scroll for full content (human-like native wheel events)
                print("   Scrolling page before screenshot...")
                dismiss_kroger_popups(page)

                # Pre-scroll idle (humans don't scroll instantly)
                diag.log("pre_scroll_idle_start")
                random_delay(2.2, 3.5)

                # Human-like wheel scrolling in bursts
                diag.log("scrolling_start")
                scroll_like_human(page, bursts=random.randint(3, 5),
                                   lines_min=6, lines_max=12)
                diag.log("scrolling_complete")

                # Exploratory behavior: drift reading + back-scroll peek
                drift_reading(page, seconds=random.uniform(1.8, 3.0))
                backscroll_peek(page)

                # Hover on a random product tile (adds realism)
                try:
                    _tiles = page.locator('[data-testid*="product"], [class*="product-card"]')
                    _tile_count = _tiles.count()
                    if _tile_count > 0:
                        _n = random.randint(0, min(5, _tile_count - 1))
                        _tiles.nth(_n).hover()
                        time.sleep(random.uniform(0.4, 0.9))
                except Exception:
                    pass

                # More scrolling to load lazy content
                scroll_like_human(page, bursts=random.randint(2, 3),
                                   lines_min=8, lines_max=14)

                # Idle before capture
                time.sleep(random.uniform(0.5, 0.9))

                # Random mouse movement
                try:
                    page.mouse.move(
                        random.randint(300, 800),
                        random.randint(400, 600)
                    )
                    time.sleep(random.uniform(0.2, 0.4))
                except Exception:
                    pass

                # Scroll back to top for full-page screenshot
                try:
                    page.evaluate("window.scrollTo(0, 0)")
                    page.wait_for_timeout(500)
                except Exception:
                    pass

                print("   Scrolling completed.")

                # Wait for carousel products to load after scrolling (prevents gray boxes in main screenshot)
                try:
                    # Check if there are carousels on the page
                    carousels = page.query_selector_all('div.CuratedCarousel')
                    if carousels:
                        print(f"   Waiting for {len(carousels)} carousel(s) to load...")
                        # Wait for carousel product images to load
                        page.wait_for_selector('img[src*="product/images"]', timeout=3000, state='visible')
                        # Additional wait for images to render
                        page.wait_for_timeout(1500)
                        print("   ✅ Carousels loaded")
                except Exception as carousel_wait_err:
                    print(f"   ⚠️ Carousel loading wait timed out (may not affect screenshot): {carousel_wait_err}")
                    # Continue anyway - not all pages have carousels
                    pass

                # Screenshot main results
                screenshot_path = os.path.join(main_dir, f"{file_prefix}.png")
                page.screenshot(path=screenshot_path, full_page=True)
                print(f"📷 Screenshot saved to {screenshot_path}")

                # TOA detection count (non-fatal)
                toa_divs = page.query_selector_all('div[data-testid="StandardTOA"]')
                print(f"🔍 Found {len(toa_divs)} TOA ads on the page")

                # Carousel capture (FEATURED carousels only - matches HTML parser logic)
                carousel_selectors = [
                    'div.CuratedCarousel'  # Primary selector that matches HTML parser
                ]
                carousel_dir = os.path.join(output_dir, "Carousel")
                os.makedirs(carousel_dir, exist_ok=True)
                carousel_count = 0
                captured_carousel = False
                for selector in carousel_selectors:
                    if captured_carousel:
                        break
                    carousels = page.query_selector_all(selector)
                    if carousels:
                        print(f"🎠 Found {len(carousels)} carousel elements with selector: {selector}")
                        for i, carousel in enumerate(carousels):
                            try:
                                # CRITICAL: Only capture FEATURED/SPONSORED carousels
                                # Check for featured flag/badge (must be explicit, not just text containing "Featured")
                                featured_flag = carousel.query_selector('.CuratedCarousel__featuredFlag, [data-testid="carousel-featured-flag"], [class*="featured" i], [class*="sponsored" i]')
                                
                                # If no featured flag element, check for explicit "Featured" badge text
                                # IMPORTANT: Only check at carousel level, not within product cards
                                if not featured_flag:
                                    # Look for "Featured" badge BEFORE the product content
                                    # The badge should be a direct child, not in product card tags
                                    featured_badge = carousel.evaluate('''el => {
                                        // Look for "Featured" badge at carousel level only
                                        // Check direct children and header siblings, not deep descendants
                                        const header = el.querySelector('.CuratedCarousel__header');
                                        if (header) {
                                            // Check siblings before the header
                                            let sibling = header.previousElementSibling;
                                            while (sibling) {
                                                const text = sibling.textContent.trim();
                                                if (text === "Featured" || text === "Sponsored") {
                                                    return true;
                                                }
                                                sibling = sibling.previousElementSibling;
                                            }
                                        }
                                        return false;
                                    }''')
                                    if not featured_badge:
                                        print(f"⚠️ Skipping carousel {i+1} - not a featured/sponsored carousel (no badge found)")
                                        continue
                                
                                print(f"✅ Carousel {i+1} is featured/sponsored - capturing")
                                
                                page.add_style_tag(content="""
                                    header, .Header, .kds-Header, [data-testid=\"header\"], .kds-StickyHeader,
                                    .SearchFilters, .search-page-filters, [class*=\"sticky\"] { display: none !important; }
                                """)
                                carousel.scroll_into_view_if_needed()
                                
                                # Wait for carousel products to load (prevent gray boxes)
                                # First wait for product links to appear
                                try:
                                    carousel.wait_for_selector('a.kds-Link[aria-label*="title"]', timeout=3000)
                                    # Then wait for images to load
                                    carousel.wait_for_selector('img[src*="product/images"]', timeout=3000)
                                    # Additional wait for images to fully render
                                    page.wait_for_timeout(1000)
                                    print(f"✅ Carousel {i+1} products loaded")
                                except Exception as wait_err:
                                    print(f"⚠️ Carousel {i+1} products may not be fully loaded: {wait_err}")
                                    # Continue anyway with a shorter wait
                                    page.wait_for_timeout(500)
                                
                                # Extract advertiser from product titles (not promotional header)
                                advertiser = "unknown"
                                
                                # Try to get brand from first product title
                                product_links = carousel.query_selector_all('a.kds-Link[aria-label*="title"]')
                                if product_links:
                                    first_product = product_links[0]
                                    # Try to get title from span
                                    title_span = first_product.query_selector('span[data-testid="cart-page-item-description"]')
                                    if title_span:
                                        product_title = title_span.text_content().strip()
                                        if product_title:
                                            # Extract brand from product title using lexicon
                                            brand = canonicalize(product_title)
                                            if brand:
                                                advertiser = brand
                                                print(f"📦 Extracted brand from product: {advertiser}")
                                    elif first_product.get_attribute('aria-label'):
                                        # Fallback to aria-label
                                        aria_label = first_product.get_attribute('aria-label')
                                        brand = canonicalize(aria_label)
                                        if brand:
                                            advertiser = brand
                                            print(f"📦 Extracted brand from aria-label: {advertiser}")
                                
                                # Final fallback: try header text
                                if advertiser == "unknown":
                                    header = carousel.query_selector(
                                        '.CuratedCarousel__header, h2, .header, .kds-Heading, .headerSection-header, [class*="header"], [class*="title"]'
                                    )
                                    if header:
                                        header_text = header.text_content().strip()
                                        if header_text:
                                            brand = canonicalize(header_text)
                                            if brand:
                                                advertiser = brand
                                                print(f"📋 Extracted brand from header: {advertiser}")
                                
                                # Add new brand to lexicon if we found one
                                if advertiser and advertiser != "unknown":
                                    add_brand(advertiser)
                                
                                # Client slug derived from output_dir (e.g., bomb_pop)
                                client_slug = os.path.basename(os.path.normpath(output_dir))
                                
                                # Build the canonical, final filename using the SAME run timestamp
                                filename = generate_ad_filename(
                                    retailer="kroger",
                                    ad_type="carousel",
                                    client=client_slug,
                                    search_term=search_term,   # generator will slug
                                    timestamp=timestamp,       # CRITICAL: reuse run ts, not datetime.now()
                                    index=i+1,                 # 1-based position
                                    extension="png",
                                    advertiser=advertiser,
                                )
                                filepath = os.path.join(carousel_dir, filename)
                                try:
                                    box = carousel.bounding_box()
                                    pad = 16
                                    clip = {
                                        "x": max(0, box["x"] - pad),
                                        "y": max(0, box["y"] - pad),
                                        "width": min(page.viewport_size()["width"] - box["x"] + pad, box["width"] + 2 * pad),
                                        "height": box["height"] + 2 * pad,
                                    }
                                    page.screenshot(path=filepath, clip=clip)
                                    print(f"📸 Carousel screenshot saved to: {filepath}")
                                    carousel_count += 1
                                    captured_carousel = True
                                    break
                                except Exception as e:
                                    print(f"❌ Error taking screenshot with padding: {e}")
                                    try:
                                        carousel.screenshot(path=filepath)
                                        print(f"📸 Carousel screenshot saved to: {filepath} (direct method)")
                                        carousel_count += 1
                                        captured_carousel = True
                                        break
                                    except Exception as e2:
                                        print(f"❌ Error taking direct screenshot: {e2}")
                            except Exception as e:
                                print(f"❌ Error processing carousel {i+1}: {e}")

                if carousel_count == 0:
                    print("⚠️ No carousels found or captured")
                else:
                    print(f"✅ Successfully captured {carousel_count} carousel(s)")

                # Save HTML to the runs directory
                runs_dir = os.path.join(output_dir, "runs")
                os.makedirs(runs_dir, exist_ok=True)  # Create runs directory if it doesn't exist
                html_path = os.path.join(runs_dir, f"{file_prefix}.html")
                page_html = page.content()
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(page_html)
                print(f"💾 HTML saved to {html_path}")

                # Check if the search results page is actually blocked
                srp_blocked, srp_reason = check_and_record(page_html, "kroger", search_term, alert=True)
                if srp_blocked:
                    print(f"❌ Kroger search results blocked: {srp_reason}")
                    print("   Saved HTML is an error page. Profile needs manual re-login.")
                    return False
                else:
                    # Successful page — record healthy outcome
                    check_and_record(page_html, "kroger", search_term, alert=False)
                
                # Save path for post-processing AFTER browser lock is released
                saved_html_path = html_path
                print("✅ Browser work complete - will do post-processing after releasing lock")

            except (TimeoutError, ConnectionError) as e:
                print(f"❌ Network or timeout error during search test: {e}")
                return False
            except (ValueError, TypeError) as e:
                print(f"❌ Value or type error during search test: {e}")
                return False
            except RuntimeError as e:
                print(f"❌ Runtime error during search test: {e}")
                return False
            except Exception as e:
                print(f"❌ Unexpected error during search test: {e}")
                return False
            finally:
                try:
                    # Track post-run cookies before closing
                    try:
                        diag.track_cookies(context, "post")
                    except Exception:
                        pass
                    
                    # Close browser and finalize diagnostics
                    context.close()
                    diag.log("browser_closed")
                    diag.finalize()
                except Exception as diag_err:
                    print(f"⚠️ Diagnostic finalization error: {diag_err}")

# ... (rest of the code remains the same)
    if saved_html_path:
        print("\n🔍 Starting post-processing (browser lock released)...")
        try:
            from process_saved_html import process_specific_html_files
            print(f"Processing HTML: {saved_html_path}")
            print(f"Output dir: {saved_output_dir}")
            
            result = process_specific_html_files([saved_html_path], output_dir=saved_output_dir, force_images=True)
            print(f"Post-processing result: {result}")
            
            # Check for generated images
            import glob
            timestamp_part = os.path.basename(saved_html_path).split('_', 2)[-1].split('.')[0]
            search_term_part = os.path.basename(saved_html_path).split('_', 2)[1]
            
            toa_pattern = os.path.join(saved_output_dir, 'TOA', f"*_{search_term_part}_{timestamp_part}_*.png")
            sky_pattern = os.path.join(saved_output_dir, 'Skyscraper', f"*_{search_term_part}_{timestamp_part}_*.png")
            
            toa_files = glob.glob(toa_pattern)
            sky_files = glob.glob(sky_pattern)
            
            print(f"✅ Found {len(toa_files)} TOA images and {len(sky_files)} Skyscraper images")
            for f in toa_files + sky_files:
                print(f"   - {os.path.basename(f)}")
            
            # Run reconciliation to link images to JSON
            print("\n🔗 Running image reconciliation...")
            try:
                import subprocess
                client_name = os.path.basename(saved_output_dir)
                reconcile_cmd = [
                    "python3",
                    "tools/reconcile_kroger_images_to_json.py",
                    "--client", client_name
                ]
                reconcile_result = subprocess.run(
                    reconcile_cmd,
                    cwd=os.path.dirname(os.path.dirname(saved_output_dir)),
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                if reconcile_result.returncode == 0:
                    print("✅ Image reconciliation complete")
                    # Print last few lines of output
                    output_lines = reconcile_result.stdout.strip().split('\n')
                    for line in output_lines[-5:]:
                        print(f"   {line}")
                else:
                    print(f"⚠️ Reconciliation failed: {reconcile_result.stderr}")
            except Exception as reconcile_err:
                print(f"⚠️ Could not run reconciliation: {reconcile_err}")
            
        except Exception as e:
            import traceback
            print(f"⚠️ Post-processing exception: {e}")
            traceback.print_exc()
    
    return True

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Kroger search and capture script")
    parser.add_argument("--search", "-s", type=str, help="Search term to use")
    parser.add_argument("--output-dir", "-o", type=str, help="Output directory for results")
    args = parser.parse_args()
    
    # Run the search and capture function
    success = search_and_capture(args.search, args.output_dir)
    
    if success:
        print("\n✅ SEARCH AND CAPTURE COMPLETED SUCCESSFULLY")
    else:
        print("\n❌ SEARCH AND CAPTURE FAILED")
