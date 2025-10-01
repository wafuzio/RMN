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
from kroger_login import save_cookies  # Removed load_cookies as it's redundant with user_data_dir

# Constants for file paths
PROJECT_ROOT = Path(__file__).resolve().parent

# Constants
USER_DATA_DIR = os.path.expanduser("~/ChromeProfiles/kroger_clean_profile")
DEFAULT_SEARCH_TERM = "black forest ham"
DEFAULT_OUTPUT_DIR = "output"

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
    try:
        # Expect output_dir like: <project>/output/<client>
        base = os.path.basename(os.path.normpath(output_dir or ''))
        if base and base != 'output':
            return base
        # Fallback: parent of output_dir
        parent = os.path.basename(os.path.dirname(os.path.normpath(output_dir or '')))
        if parent and parent != 'output':
            return parent
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
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-infobars",
                    "--disable-web-security",
                    "--no-first-run",
                    "--disable-default-apps",
                    "--disable-popup-blocking",
                    "--disable-translate",
                    "--disable-background-timer-throttling",
                    "--disable-renderer-backgrounding",
                    "--disable-backgrounding-occluded-windows",
                    "--disable-restore-session-state",
                    "--disable-ipc-flooding-protection",
                    "--window-position=10000,10000",
                    "--window-size=1280,720",
                    "--disable-focus-on-show",
                    "--disable-notifications",
                    "--disable-quic",
                ],
            )
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
    # Enforce a single Chromium across all processes
    with single_browser_lock(timeout=600):
        with sync_playwright() as p:
            client_name = _derive_client_from_output_dir(output_dir)
            print(f"Browser launch: client context = {client_name or 'unknown'}")
            context = _launch_context_resilient(p, client_name)

            try:
                page = context.pages[0] if context.pages else context.new_page()

                # Be more lenient with transient network delays
                try:
                    context.set_default_navigation_timeout(45000)
                except Exception:
                    pass

                # Navigate to Kroger homepage (non-fatal; continue even if it fails)
                try:
                    goto_with_retries(page, "https://www.kroger.com/", attempts=4, wait_until="domcontentloaded", timeout_ms=45000)
                    page.wait_for_timeout(5000)
                    # Dismiss any homepage popups
                    dismiss_kroger_popups(page)
                except Exception as e:
                    print(f"   Homepage navigate failed: {e} — proceeding directly to search.")

                # Logged-in check
                try:
                    is_logged_in = not page.is_visible("text=Sign In")
                except Exception:
                    is_logged_in = False
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
                            print("❌ Still not logged in after waiting. Will proceed but some content may be limited.")
                    except Exception as e:
                        print(f"   Login attempt encountered an issue: {e}")

                # Step 3: Perform the search query
                print("\n🔎 Step 3: Performing search...")
                search_url = "https://www.kroger.com/search?query={}".format(urllib.parse.quote_plus(search_term))
                goto_with_retries(page, search_url, attempts=4, wait_until="domcontentloaded", timeout_ms=45000)
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
                                        if (checkProducts() || attempts >= 10) {
                                            clearInterval(interval);
                                            if (attempts >= 10) resolve('products_timeout');
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

                # Confirm still logged in
                is_still_logged_in = not page.is_visible("text=Sign In")
                if not is_still_logged_in:
                    print("❌ Session lost during search")
                    return False
                print("✅ Still logged in after search")

                # Prepare output dirs and filenames
                file_prefix = f"search_results_{safe_search_term}_{timestamp}"
                main_dir = os.path.join(output_dir, "main")
                toa_dir = os.path.join(output_dir, "TOA")
                os.makedirs(main_dir, exist_ok=True)
                os.makedirs(toa_dir, exist_ok=True)

                # Scroll for full content
                print("   Scrolling page before screenshot...")
                # Ensure no overlays block scrolling/screenshot
                dismiss_kroger_popups(page)
                try:
                    scroll_result = scroll_results(page)
                    print(f"   Scrolling completed. Scrolled to Y={scroll_result['finalY']} of {scroll_result['finalH']}")
                except Exception as e:
                    print(f"   Warning: Scrolling failed: {e}")

                # Screenshot main results
                screenshot_path = os.path.join(main_dir, f"{file_prefix}.png")
                page.screenshot(path=screenshot_path, full_page=True)
                print(f"📷 Screenshot saved to {screenshot_path}")

                # TOA detection count (non-fatal)
                toa_divs = page.query_selector_all('div[data-testid="StandardTOA"]')
                print(f"🔍 Found {len(toa_divs)} TOA ads on the page")

                # Carousel capture (first only)
                carousel_selectors = [
                    'div.CuratedCarousel, div[class*="Carousel"]:has(.kds-Heading--xl)'
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
                                page.add_style_tag(content="""
                                    header, .Header, .kds-Header, [data-testid=\"header\"], .kds-StickyHeader,
                                    .SearchFilters, .search-page-filters, [class*=\"sticky\"] { display: none !important; }
                                """)
                                carousel.scroll_into_view_if_needed()
                                page.wait_for_timeout(500)
                                header = carousel.query_selector(
                                    '.CuratedCarousel__header, h2, .header, .kds-Heading, .headerSection-header, [class*="header"], [class*="title"]'
                                )
                                if not header and len(carousels) > 1:
                                    print(f"⚠️ Skipping carousel {i+1} - no header found")
                                    continue
                                header_text = header.text_content().strip() if header else "main_carousel"
                                if not header_text and len(carousels) > 1:
                                    print(f"⚠️ Skipping carousel {i+1} - empty header text")
                                    continue
                                ts2 = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                                safe_header = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in header_text.lower())[:30]
                                safe_term2 = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in search_term.lower())
                                filename = f"carousel_{safe_header}_{safe_term2}_{ts2}.png"
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
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(page.content())
                print(f"💾 HTML saved to {html_path}")
                
                # Add diagnostic logging to understand what's happening
                print("\n🔍 DIAGNOSTIC: About to attempt post-processing")
                try:
                    # Import the module
                    print("🔍 DIAGNOSTIC: Importing process_saved_html...")
                    from process_saved_html import process_specific_html_files
                    print("🔍 DIAGNOSTIC: Import successful")
                    
                    # Log the parameters
                    print(f"🔍 DIAGNOSTIC: HTML path: {html_path}")
                    print(f"🔍 DIAGNOSTIC: Output dir: {output_dir}")
                    
                    # Call the function
                    print("🔍 DIAGNOSTIC: Calling process_specific_html_files...")
                    result = process_specific_html_files([html_path], output_dir=output_dir, force_images=True)
                    print(f"🔍 DIAGNOSTIC: Function returned: {result}")
                    
                    # Check for images
                    import glob
                    timestamp_part = os.path.basename(html_path).split('_', 2)[-1].split('.')[0]
                    search_term_part = os.path.basename(html_path).split('_', 2)[1]
                    
                    toa_pattern = os.path.join(output_dir, 'TOA', f"*_{search_term_part}_{timestamp_part}_*.png")
                    sky_pattern = os.path.join(output_dir, 'Skyscraper', f"*_{search_term_part}_{timestamp_part}_*.png")
                    
                    toa_files = glob.glob(toa_pattern)
                    sky_files = glob.glob(sky_pattern)
                    
                    print(f"🔍 DIAGNOSTIC: Found {len(toa_files)} TOA images and {len(sky_files)} Skyscraper images")
                    for f in toa_files + sky_files:
                        print(f"   - {os.path.basename(f)}")
                    
                except Exception as e:
                    import traceback
                    print(f"⚠️ Post-processing exception: {e}")
                    print("⚠️ Full traceback:")
                    traceback.print_exc()

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
                    context.close()
                except Exception:
                    pass

            # We've already done the post-processing inside the browser context
            # This ensures it runs before the function returns
                
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
