#!/usr/bin/env python3
"""
Instacart search and capture script.
Performs keyword search on Instacart and saves HTML + JSON results.
"""

import os
import sys
import json
import time
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from filename_utils import generate_ad_filename


def force_window_and_metrics(context, page, width=1920, height=1080, dpr=1, log=None):
    """
    In a persistent Chromium context, resize the actual OS window and apply emulation metrics
    so viewport and DPR are exactly what we expect.
    """
    if log is None:
        log = print
    
    try:
        client = context.new_cdp_session(page)
        log(f"   CDP session created")
    except Exception as e:
        log(f"   ⚠️ Failed to create CDP session: {e}")
        return
    
    # 1) Resize the outer browser window (persistent contexts ignore set_viewport_size)
    try:
        win = client.send('Browser.getWindowForTarget')
        log(f"   Window ID: {win.get('windowId')}")
        result = client.send('Browser.setWindowBounds', {
            'windowId': win['windowId'],
            'bounds': {'width': width, 'height': height}
        })
        log(f"   ✅ Window bounds set to {width}x{height}")
    except Exception as e:
        log(f"   ⚠️ Failed to set window bounds: {e}")
    
    # 2) Override device metrics so CSS px math is stable
    try:
        client.send('Emulation.setDeviceMetricsOverride', {
            'width': width,
            'height': height,
            'deviceScaleFactor': dpr,
            'mobile': False,
            'scale': 1
        })
        log(f"   ✅ Device metrics override set: {width}x{height}, DPR={dpr}")
    except Exception as e:
        log(f"   ⚠️ Failed to set device metrics: {e}")
    
    # 3) Reset any persisted page zoom (some profiles save per-origin zoom)
    try:
        client.send('Emulation.setPageScaleFactor', {'pageScaleFactor': 1})
        log(f"   ✅ Page scale factor reset to 1")
    except Exception as e:
        log(f"   ⚠️ Failed to set page scale factor: {e}")
    
    # 4) Verify
    try:
        cur_dpr = page.evaluate('window.devicePixelRatio')
        vp = page.evaluate('() => ({ width: window.innerWidth, height: window.innerHeight })')
        log(f"   ✅ Viewport verified: {vp['width']}x{vp['height']}, DPR: {cur_dpr}")
        
        if vp['width'] != width or vp['height'] != height:
            log(f"   ⚠️ WARNING: Viewport mismatch! Expected {width}x{height}, got {vp['width']}x{vp['height']}")
        if abs(cur_dpr - dpr) > 0.01:
            log(f"   ⚠️ WARNING: DPR mismatch! Expected {dpr}, got {cur_dpr}")
    except Exception as e:
        log(f"   ⚠️ Failed to verify viewport: {e}")


def screenshot_element_beyond_viewport(context, page, handle, out_path, pad=8, log=None):
    """CDP-based screenshot that captures beyond viewport (no reload)."""
    if log is None:
        log = print
    
    # Get element info BEFORE scrolling
    try:
        elem_id = handle.get_attribute('id')
        elem_classes = handle.get_attribute('class')
        log(f"      Element: id={elem_id}, classes={elem_classes[:50] if elem_classes else 'none'}")
    except:
        pass
    
    # Check what's inside the element
    try:
        has_inner = handle.query_selector('[id$="-inner"]')
        has_carousel = handle.query_selector('[data-testid="shoppable-list-sliding-carousel"]')
        has_header = handle.query_selector('h2, [role="heading"]')
        has_logo = handle.query_selector('img[alt*="logo"], img[alt*="Logo"]')
        log(f"      Contains: inner={bool(has_inner)}, carousel={bool(has_carousel)}, header={bool(has_header)}, logo={bool(has_logo)}")
    except Exception as e:
        log(f"      Could not check element contents: {e}")
    
    handle.scroll_into_view_if_needed()
    page.wait_for_timeout(80)
    
    # Freeze motion and avoid smooth-scrolling reflows
    try:
        page.add_style_tag(content="""
            html { scroll-behavior: auto !important; }
            * { transition: none !important; animation: none !important; }
        """)
    except Exception:
        pass
    
    # Hide sticky UI without reflow
    try:
        page.evaluate("""
            () => {
                const hdrs = [
                    document.querySelector('header[class*="sticky"]'),
                    document.querySelector('header[style*="position: fixed"]'),
                    document.querySelector('header[style*="position:fixed"]')
                ];
                hdrs.forEach(h => { if (h) h.style.visibility = 'hidden'; });
                const filters = document.querySelector('[aria-label="Filters"]');
                if (filters) filters.style.visibility = 'hidden';
            }
        """)
    except Exception:
        pass
    
    # Flush layout right before measuring
    try:
        page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
    except Exception:
        pass
    
    # Compute element rect in PAGE coordinates (viewport rect + scrollX/Y)
    # This is critical: CDP captureScreenshot expects page coords, not viewport coords!
    rect = page.evaluate(
        """([el, pad]) => {
            const r = el.getBoundingClientRect();
            const sx = window.scrollX || window.pageXOffset || 0;
            const sy = window.scrollY || window.pageYOffset || 0;
            const x  = Math.max(0, Math.floor(r.left + sx - pad));
            const y  = Math.max(0, Math.floor(r.top  + sy - pad));
            const w  = Math.ceil(r.width  + 2*pad);
            const h  = Math.ceil(r.height + 2*pad);
            return { x, y, width: w, height: h, sx, sy, rt: r.top, rl: r.left, rw: r.width, rh: r.height };
        }""",
        [handle, pad]
    )
    
    if not rect:
        raise RuntimeError("No rect for element")
    
    # Debug logging
    dpr = page.evaluate("window.devicePixelRatio")
    viewport_info = page.evaluate('() => ({ width: window.innerWidth, height: window.innerHeight })')
    log(f"      Viewport: {viewport_info['width']}x{viewport_info['height']}, scrollY={rect['sy']:.1f}, DPR={dpr}")
    log(f"      Element rect (viewport): top={rect['rt']:.1f}, left={rect['rl']:.1f}, w={rect['rw']:.1f}, h={rect['rh']:.1f}")
    log(f"      Clip (page coords): x={rect['x']}, y={rect['y']}, w={rect['width']}, h={rect['height']}")
    
    clip = {
        'x': rect['x'],
        'y': rect['y'],
        'width': rect['width'],
        'height': rect['height'],
        'scale': 1.0,
    }
    
    client = context.new_cdp_session(page)
    shot = client.send('Page.captureScreenshot', {
        'format': 'png',
        'fromSurface': True,
        'captureBeyondViewport': True,
        'clip': clip,
    })
    
    import base64, os
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'wb') as f:
        f.write(base64.b64decode(shot['data']))
    
    # Check actual screenshot dimensions
    try:
        import PIL.Image
        img = PIL.Image.open(out_path)
        log(f"      Screenshot saved: {img.width}x{img.height} pixels")
        if abs(img.width - clip['width']) > 2 or abs(img.height - clip['height']) > 2:
            log(f"      ⚠️  SIZE MISMATCH! Expected {clip['width']:.0f}x{clip['height']:.0f}, got {img.width}x{img.height}")
    except Exception as e:
        log(f"      Could not verify screenshot dimensions: {e}")
    
    return out_path


def _wait_until_home_ready(page, log, timeout_ms=15000):
    """Wait for homepage to be fully loaded and ready."""
    try:
        page.wait_for_load_state("load", timeout=timeout_ms)
        log("Home: load state reached")
    except Exception as e:
        log(f"Home: load state wait skipped/failed: {e}")
    
    selectors = [
        "[data-testid='search-bar-input']",
        "input[placeholder*='Search']",
        "[role='search'] input",
        "header",
    ]
    for sel in selectors:
        try:
            page.wait_for_selector(sel, timeout=4000)
            log(f"Home: ready selector found: {sel}")
            return
        except Exception:
            pass
    
    page.wait_for_timeout(3000)
    log("Home: fallback settle delay used")


def _is_login_modal_visible(page):
    """Check if Instacart login modal is visible."""
    # Known auth modal selectors seen on Instacart
    SELS = [
        ".ReactModalPortal .AuthModal__Overlay",
        "[data-testid='authModalWrapper']",
    ]
    try:
        for sel in SELS:
            el = page.query_selector(sel)
            if el and el.is_visible():
                return True
        return False
    except Exception:
        return False


def _prompt_user_login(page, log, max_wait_sec=300):
    """
    When a login modal is present, bring the browser to the foreground,
    instruct the user to complete login, and wait until the modal disappears.
    Returns True if login modal disappears, False on timeout.
    """
    try:
        page.bring_to_front()
    except Exception:
        pass
    
    log("⚠️ Login required: A login modal is visible.")
    log("Please complete the Instacart login in the visible browser window.")
    log("After you finish, the scraper will continue automatically.")
    log(f"Timeout in {max_wait_sec} seconds.")
    
    deadline = time.time() + max_wait_sec
    last_report = 0
    while time.time() < deadline:
        if not _is_login_modal_visible(page):
            log("✅ Login modal no longer visible — continuing.")
            return True
        # Report every ~10 seconds so logs show progress
        now = time.time()
        if now - last_report >= 10:
            remaining = int(deadline - now)
            log(f"Waiting for login to complete... ({remaining}s remaining)")
            last_report = now
        page.wait_for_timeout(1000)
    
    log("❌ Login prompt timeout — no change detected. You may need to re-run auth:")
    log("   ./scripts/setup_instacart_profile.sh")
    return False


def _handle_login_if_needed(page, log, max_wait_sec=300):
    """Check for login modal and prompt user if visible. Returns True if OK to continue."""
    try:
        if _is_login_modal_visible(page):
            return _prompt_user_login(page, log, max_wait_sec=max_wait_sec)
        return True
    except Exception as e:
        log(f"Login check failed: {e}")
        return False


def search_and_capture(keyword: str, output_dir: str, store: str = None) -> bool:
    """
    Search Instacart for a keyword and capture the results.
    
    Args:
        keyword: Search term
        output_dir: Directory to save results
        store: Store slug (e.g., 'publix', 'kroger'). Defaults to INSTACART_STORE env var or 'publix'
    
    Returns:
        True if successful, False otherwise
    """
    
    # Set up debug logging
    debug_log = os.path.join(output_dir, "debug_search.log")
    os.makedirs(output_dir, exist_ok=True)
    
    def log(msg):
        """Log to both stdout and debug file"""
        print(msg)
        try:
            with open(debug_log, 'a', encoding='utf-8') as f:
                f.write(f"{datetime.now().isoformat()} {msg}\n")
        except:
            pass
    
    log(f"=== SEARCH START: {keyword} ===")
    
    # Get store from parameter or environment
    if store is None:
        store = os.environ.get('INSTACART_STORE', 'publix')
    log(f"Store: {store}")
    
    # Get profile directory
    profile_dir = os.environ.get('INSTACART_PROFILE_DIR')
    log(f"Profile dir: {profile_dir}")
    if not profile_dir or not os.path.isdir(profile_dir):
        log(f"❌ INSTACART_PROFILE_DIR not set or invalid: {profile_dir}")
        log("Run: ./scripts/setup_instacart_profile.sh")
        return False
    log(f"✅ Profile directory valid")
    
    # Clean up stale lock file if it exists
    lock_file = os.path.join(profile_dir, 'SingletonLock')
    if os.path.exists(lock_file):
        try:
            os.remove(lock_file)
            print(f"   Removed stale lock file: {lock_file}")
        except Exception as e:
            print(f"   Warning: Could not remove lock file: {e}")
    
    # Create runs directory
    runs_dir = os.path.join(output_dir, "runs")
    os.makedirs(runs_dir, exist_ok=True)
    log(f"Runs directory: {runs_dir}")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    html_file = os.path.join(runs_dir, f"search_results_{timestamp}.html")
    json_file = os.path.join(runs_dir, f"run_results_{timestamp}.json")
        
    # Extract client name from output directory (e.g., /path/to/output/instacart/pickle -> pickle)
    client_name = os.path.basename(output_dir)
    
    log(f"🔍 Searching Instacart for: '{keyword}'")
    log(f"   Store: {store}")
    log(f"   Profile: {profile_dir}")
    
    # Use Playwright with persistent context (authenticated session)
    log("Starting Playwright...")
    try:
        with sync_playwright() as p:
            # Launch with persistent context (authenticated session)
            log("🖥️  Launching with viewport: 1920x1080, DPR: 1")
            context = p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=False,
                viewport={'width': 1920, 'height': 1080},
                device_scale_factor=1,  # Pin DPR to 1
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
                locale='en-US',
                args=[
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--no-first-run',
                    '--no-default-browser-check',
                    '--disable-session-crashed-bubble',
                    '--window-size=1920,1080',  # Force initial outer window size
                    '--force-device-scale-factor=1',  # Force DPR
                    '--high-dpi-support=1',
                ],
            )
            
            page = context.pages[0] if context.pages else context.new_page()
            
            # Force window and metrics via CDP (this works in persistent contexts)
            log("🖥️  Forcing window bounds and device metrics via CDP...")
            force_window_and_metrics(context, page, 1920, 1080, 1, log=log)
            
            # Visit homepage (organic navigation)
            log("Loading homepage...")
            page.goto(f'https://www.instacart.com/store/{store}', wait_until='domcontentloaded', timeout=15000)
            
            # Don't rush off the home page
            _wait_until_home_ready(page, log, timeout_ms=15000)
            
            # If a login modal is present on home, pause for interactive login
            if not _handle_login_if_needed(page, log, max_wait_sec=300):
                context.close()
                return False
            
            # Organic search interaction (robust version)
            log(f"Searching for: {keyword}")
            try:
                # 0) Cookie banner can block the header — dismiss if present (best-effort)
                cookie_ctas = [
                    "button:has-text('Accept')",
                    "button:has-text('Agree')",
                    "[data-testid*='accept']",
                    "button[aria-label*='Accept']",
                ]
                for cta in cookie_ctas:
                    try:
                        if page.locator(cta).first.is_visible():
                            log(f"   Dismissing cookie banner via {cta}")
                            page.locator(cta).first.click(timeout=1000)
                            page.wait_for_timeout(300)
                            break
                    except Exception:
                        pass
                
                # 1) Some variants gate the input behind a search-toggle button
                toggle_selectors = [
                    "button[aria-label*='Search']",
                    "[data-testid='search-bar-button']",
                    "[data-testid='search-input-toggle']",
                    "button:has(svg[aria-label='Search'])",
                ]
                for tsel in toggle_selectors:
                    try:
                        if page.locator(tsel).first.is_visible():
                            log(f"   Clicking search toggle: {tsel}")
                            page.locator(tsel).first.click(timeout=1500)
                            page.wait_for_timeout(300)
                            break
                    except Exception:
                        pass
                
                # 2) Broad input/combobox selector (covers most site variants)
                search_selector = (
                    "[data-testid='search-bar-input'], "
                    "input[type='search'], "
                    "input[placeholder*='Search'], "
                    "input[aria-label*='Search'], "
                    "[role='search'] input, "
                    "[contenteditable='true'][role='combobox']"
                )
                search_input = page.locator(search_selector).filter(
                    has_not=page.locator("[aria-hidden='true']")
                ).first
                
                log("   Looking for search input...")
                search_input.wait_for(state="visible", timeout=6000)
                log("   Search input found and visible")
                
                # 3) Ensure it's interactable
                try:
                    search_input.scroll_into_view_if_needed(timeout=1500)
                except Exception:
                    pass
                search_input.click(timeout=2000)
                log("   Clicked search input")
                
                # 4) Type/fill and submit
                try:
                    search_input.fill("")  # clear if anything prefilled
                except Exception:
                    pass
                search_input.fill(keyword)
                log(f"   Filled keyword: {keyword}")
                page.wait_for_timeout(200)
                search_input.press("Enter")
                log("   Pressed Enter on input")
                
                # 5) Wait for results URL
                page.wait_for_url("**/s?k=**", timeout=12000)
                log("   ✅ Navigated to search results via organic search")
                
            except Exception as e:
                log(f"   ❌ Search box interaction failed: {type(e).__name__}: {e}")
                try:
                    # Drop a screenshot so we can see what blocked us
                    shot = os.path.join(runs_dir, "home_before_fallback.png")
                    page.screenshot(path=shot, full_page=False)
                    log(f"   Saved debug screenshot: {shot}")
                except Exception:
                    pass
                log("   Falling back to direct navigation...")
                search_url = f"https://www.instacart.com/store/{store}/s?k={keyword}"
                page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                log("   Direct navigation completed")
            
            # Some flows can trigger the auth modal on the results page — handle again
            if not _handle_login_if_needed(page, log, max_wait_sec=300):
                context.close()
                return False
            
            # Prefer to see ad containers; fallback to a short settle delay
            try:
                page.wait_for_selector('[role="region"][aria-label*="carousel"]', timeout=8000)
                log("Search: ad containers detected")
            except Exception:
                log("Search: ad containers not detected within 8s; using short settle delay")
                page.wait_for_timeout(3000)
            
            search_url = page.url
            log("✅ Authenticated session active")
            
            # Extract ad data for JSON (matching Kroger structure)
            ad_data = {
                "keyword": keyword,
                "search_term": keyword,
                "store": store,
                "timestamp": timestamp,
                "retailer": "instacart",
                "url": search_url,
                "source_file": html_file,
                "results": [{"ads": []}]  # Nested structure like Kroger
            }
            
            # Find all ad containers using structural selectors (hash classes change)
            log("🧭 Finding ad containers via structural navigation...")
            
            # Find all divs with UUID IDs that have -inner children
            elements = []
            all_divs = page.query_selector_all('div[id]')
            log(f"   Checking {len(all_divs)} divs with IDs...")
            
            for div in all_divs:
                try:
                    div_id = div.get_attribute('id')
                    if not div_id or '-' not in div_id:
                        continue
                    
                    # Check if this div has a child with id="{div_id}-inner"
                    inner = div.query_selector(f'[id="{div_id}-inner"]')
                    if not inner:
                        continue
                    
                    # Check if the inner contains a carousel
                    carousel = inner.query_selector('[data-testid="shoppable-list-sliding-carousel"]')
                    if not carousel:
                        continue
                    
                    # This is a border container with a carousel!
                    try:
                        div_bbox = div.bounding_box()
                        log(f"\n✅ Found ad container: id={div_id}")
                        log(f"   ↳ Bbox: x={div_bbox['x']:.1f}, y={div_bbox['y']:.1f}, w={div_bbox['width']:.1f}, h={div_bbox['height']:.1f}")
                    except:
                        pass
                    
                    elements.append(('Shoppable Display Ad', div))
                    
                except Exception as e:
                    continue
            
            log(f"\n✅ Found {len(elements)} ad containers total")
            
            for ad_type, elem in elements:
                i = elements.index((ad_type, elem))
                try:
                    # Get ad ID if available
                    ad_id = elem.get_attribute('id') or f"{ad_type}_{i}"
                    
                    # For Shoppable Display Ads, check if it contains video
                    actual_ad_type = ad_type
                    if ad_type == 'Shoppable Display Ad':
                        # Check if this ad contains a video player
                        video_player = elem.query_selector('div[id^="video-player-"]')
                        if video_player:
                            actual_ad_type = 'Shoppable Video Ad'
                    
                    # Get bounding box for screenshot coordinates
                    bbox = elem.bounding_box()
                    
                    ad_info = {
                        "type": actual_ad_type,
                        "selector": "structural",
                        "id": ad_id,
                        "index": i,
                    }
                    
                    if bbox:
                        ad_info["bbox"] = {
                            "x": bbox['x'],
                            "y": bbox['y'],
                            "width": bbox['width'],
                            "height": bbox['height']
                        }
                    
                    # Try to extract brand/advertiser with multiple strategies
                    advertiser = None
                    
                    # STRATEGY 1: Extract from brand_link (most reliable for shoppable ads)
                    try:
                        brand_link_elem = elem.query_selector('a[href*="/store/"][href*="/brands/"]')
                        if brand_link_elem:
                            brand_link = brand_link_elem.get_attribute('href') or ""
                            if brand_link:
                                brand_match = re.search(r'/brands/([^/?]+)', brand_link)
                                if brand_match:
                                    brand_slug = brand_match.group(1)
                                    # Clean up brand slug - remove company prefixes like "dgic-"
                                    if '-' in brand_slug:
                                        parts = brand_slug.split('-')
                                        if len(parts) > 1 and len(parts[0]) <= 4:
                                            brand_slug = '-'.join(parts[1:])
                                    advertiser = brand_slug.replace('-', ' ').title()
                                    log(f"      📌 Brand from link: {advertiser}")
                    except Exception as e:
                        log(f"      ⚠️  Brand link extraction failed: {e}")
                    
                    # STRATEGY 2: Extract from logo alt text (reliable for display ads)
                    if not advertiser:
                        try:
                            logo_img = elem.query_selector('img[alt]:not([alt=""])')
                            if logo_img:
                                alt_text = logo_img.get_attribute('alt')
                                if alt_text and alt_text.strip() and len(alt_text) > 2:
                                    # Clean generic descriptive words FIRST (e.g., "goodpop logo" -> "goodpop")
                                    cleaned = alt_text
                                    for word in ['Logo', 'logo', 'Brand', 'brand', 'Image', 'image']:
                                        cleaned = cleaned.replace(word, '').strip()
                                    
                                    # Use cleaned version if it's not empty
                                    if cleaned and len(cleaned) > 2:
                                        alt_text = cleaned
                                    
                                    # NOW check if the cleaned text is purely generic
                                    generic_alts = ['ad', 'banner', 'sponsored', 'advertisement']
                                    
                                    if alt_text.lower() not in generic_alts:
                                        
                                        # Use short, clean alt text directly
                                        if len(alt_text) < 30 and '&' not in alt_text:
                                            advertiser = alt_text.strip()
                                            # Capitalize if all lowercase (e.g., "goodpop" -> "Goodpop")
                                            if advertiser.islower():
                                                advertiser = advertiser.capitalize()
                                            log(f"      📌 Brand from logo alt: {advertiser}")
                                        else:
                                            # For longer alt text, extract brand intelligently
                                            # Strategy: Check for " - " separator (brand often comes after)
                                            if ' - ' in alt_text:
                                                parts = alt_text.split(' - ')
                                                if len(parts) > 1:
                                                    brand_part = parts[-1].strip()
                                                    words = brand_part.split()
                                                    brand_words = []
                                                    for word in words[:3]:
                                                        if word and word[0].isupper():
                                                            brand_words.append(word)
                                                        else:
                                                            break
                                                    if brand_words:
                                                        advertiser = ' '.join(brand_words)
                                                        log(f"      📌 Brand from logo alt (after dash): {advertiser}")
                                            
                                            # Fallback: Extract from beginning (before '&' or descriptive words)
                                            if not advertiser:
                                                words = alt_text.split()
                                                descriptive_words = {'in', 'on', 'with', 'and', 'or', 'the', 'a', 'an', 'for', 'at',
                                                                   'candies', 'candy', 'products', 'product', 'items', 'item',
                                                                   'treats', 'treat', 'delicious', 'frighteningly'}
                                                brand_words = []
                                                for word in words[:5]:
                                                    if word in ['&', 'and', '-'] or word.lower() in descriptive_words:
                                                        break
                                                    if word and word[0].isupper():
                                                        brand_words.append(word)
                                                        if len(brand_words) >= 3:
                                                            break
                                                if brand_words:
                                                    advertiser = ' '.join(brand_words)
                                                    log(f"      📌 Brand from logo alt (beginning): {advertiser}")
                        except:
                            pass
                    
                    # STRATEGY 3: Extract from carousel products (check if all products start with same brand)
                    if not advertiser:
                        try:
                            # Get all product titles in the carousel
                            product_elems = elem.query_selector_all('[data-testid="shoppable-list-sliding-carousel"] [role="group"] h3, [data-testid="shoppable-list-sliding-carousel"] [role="group"] [class*="title"]')
                            if product_elems and len(product_elems) > 0:
                                product_titles = []
                                for prod in product_elems[:5]:  # Check first 5 products
                                    try:
                                        title = prod.inner_text()
                                        if title:
                                            product_titles.append(title)
                                    except:
                                        pass
                                
                                if product_titles:
                                    # Extract potential brand from first product (first 1-2 capitalized words)
                                    first_title = product_titles[0]
                                    words = first_title.split()
                                    brand_candidate = None
                                    
                                    # Try 2-word brand first, then 1-word
                                    for num_words in [2, 1]:
                                        if len(words) >= num_words:
                                            potential_brand = ' '.join(words[:num_words])
                                            # Check if all products start with this brand
                                            if all(title.startswith(potential_brand) for title in product_titles):
                                                brand_candidate = potential_brand
                                                break
                                    
                                    if brand_candidate:
                                        advertiser = brand_candidate
                                        log(f"      📌 Brand from carousel (all products start with '{advertiser}')")
                        except:
                            pass
                    
                    # STRATEGY 4: Extract from header text (LAST RESORT - only if ® or ™ present)
                    if not advertiser:
                        try:
                            title_elem = elem.query_selector('h2, [role="heading"]')
                            if title_elem:
                                title = title_elem.inner_text()
                                ad_info["title"] = title
                                if title:
                                    # Only extract from header if it contains trademark symbols
                                    if '®' in title or '™' in title:
                                        # Look for "Brand - Description" format
                                        if ' - ' in title:
                                            parts = title.split(' - ')
                                            if parts and parts[0]:
                                                # Check if first part has trademark
                                                if '®' in parts[0] or '™' in parts[0]:
                                                    advertiser = parts[0].replace('®', '').replace('™', '').strip()
                                                    log(f"      📌 Brand from header with ® (dash): {advertiser}")
                                        
                                        # Look for word with ® or ™ symbol
                                        if not advertiser:
                                            words = title.split()
                                            for word in words:
                                                if '®' in word or '™' in word:
                                                    clean_word = word.replace('®', '').replace('™', '').strip()
                                                    if clean_word and clean_word[0].isupper():
                                                        advertiser = clean_word
                                                        log(f"      📌 Brand from header with ® or ™: {advertiser}")
                                                        break
                        except:
                            pass
                    
                    # Add advertiser to ad_info if we found one
                    if advertiser:
                        ad_info["advertisers"] = [advertiser]
                        ad_info["brand"] = advertiser
                    else:
                        log(f"      ⚠️  No brand extracted for ad #{i} (title: {ad_info.get('title', 'NO TITLE')})")
                    
                    ad_data["results"][0]["ads"].append(ad_info)
                except Exception as e:
                    print(f"⚠️  Could not extract data from {ad_type} #{i}: {e}")
            
            ad_count = len(ad_data['results'][0]['ads'])
            ad_data['count'] = ad_count
            print(f"📊 Found {ad_count} ad units")
            
            # Save HTML AFTER all ad extraction (includes all lazy-loaded content)
            log("\n💾 Saving HTML with all lazy-loaded content...")
            html_content = page.content()
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            log(f"   ✅ HTML saved: {html_file}")
            
            # Take screenshots of ads
            log("\n📸 Taking screenshots...")
            log(f"   Total elements to screenshot: {len(elements)}")
            
            # Force window and metrics again before screenshots (site may have changed them)
            log("   Forcing window bounds and metrics via CDP before screenshots...")
            force_window_and_metrics(context, page, 1920, 1080, 1, log=log)
            
            # Create output directories
            shoppable_display_dir = os.path.join(output_dir, "Shoppable_Display_Ads")
            shoppable_video_dir = os.path.join(output_dir, "Shoppable_Video_Ads")
            main_dir = os.path.join(output_dir, "Main")
            os.makedirs(shoppable_display_dir, exist_ok=True)
            os.makedirs(shoppable_video_dir, exist_ok=True)
            os.makedirs(main_dir, exist_ok=True)
            log(f"   Display dir: {shoppable_display_dir}")
            log(f"   Video dir: {shoppable_video_dir}")
            log(f"   Main dir: {main_dir}")
            
            # Take full page screenshot first
            try:
                log("\n📸 Taking full page screenshot...")
                fullpage_filename = generate_ad_filename(
                    retailer='instacart',
                    ad_type='main',
                    client=client_name,
                    search_term=keyword,
                    timestamp=timestamp,
                    index=1,
                    extension='png',
                    advertiser=None
                )
                fullpage_path = os.path.join(main_dir, fullpage_filename)
                page.screenshot(path=fullpage_path, full_page=True)
                log(f"   ✅ Full page: {fullpage_filename}")
            except Exception as e:
                log(f"   ⚠️ Full page screenshot failed: {e}")
            
            # Screenshot each ad
            for idx, (ad_type, elem) in enumerate(elements):
                log(f"\n📸 Screenshot {idx + 1}/{len(elements)}")
                try:
                    # Determine actual ad type (check for video)
                    is_video = elem.query_selector('video') is not None
                    actual_ad_type = 'Shoppable Video Ad' if is_video else 'Shoppable Display Ad'
                    output_folder = shoppable_video_dir if is_video else shoppable_display_dir
                    ad_type_slug = 'shoppable_video_ad' if is_video else 'shoppable_display_ad'
                    log(f"   Ad type: {actual_ad_type} (video={is_video})")
                    
                    # Extract advertiser from ad data if available
                    advertiser = None
                    if idx < len(ad_data['results'][0]['ads']):
                        ad_info = ad_data['results'][0]['ads'][idx]
                        if 'advertisers' in ad_info and ad_info['advertisers']:
                            advertiser = ad_info['advertisers'][0]
                            log(f"   Advertiser: {advertiser}")
                    
                    # Generate filename
                    screenshot_filename = generate_ad_filename(
                        retailer='instacart',
                        ad_type=ad_type_slug,
                        client=client_name,
                        search_term=keyword,
                        timestamp=timestamp,
                        index=idx + 1,
                        extension='png',
                        advertiser=advertiser
                    )
                    screenshot_path = os.path.join(output_folder, screenshot_filename)
                    log(f"   Filename: {screenshot_filename}")
                    
                    # CDP screenshot (captures beyond viewport, no reload)
                    log(f"   Taking CDP screenshot (beyond viewport)...")
                    screenshot_element_beyond_viewport(context, page, elem, screenshot_path, pad=8, log=log)
                    log(f"   ✅ Screenshot (CDP beyond-viewport): {os.path.basename(screenshot_path)}")
                    
                    # Verify file was created
                    if os.path.exists(screenshot_path):
                        file_size = os.path.getsize(screenshot_path)
                        log(f"   ✅ Screenshot saved: {screenshot_filename} ({file_size} bytes)")
                    else:
                        log(f"   ⚠️ Screenshot file not found: {screenshot_path}")
                    
                    # Add screenshot path to ad_info
                    if idx < len(ad_data['results'][0]['ads']):
                        rel_path = os.path.relpath(screenshot_path, output_dir)
                        ad_data['results'][0]['ads'][idx]['screenshot'] = rel_path
                        log(f"   Added to JSON: {rel_path}")
                        
                except Exception as e:
                    log(f"   ⚠️ Screenshot failed for ad #{idx + 1}: {e}")
                    import traceback
                    log(f"   Traceback: {traceback.format_exc()}")
            
            # Save JSON (with screenshot paths now included)
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(ad_data, f, indent=2)
            print(f"💾 JSON saved: {json_file}")
            
            context.close()
            
            return True
            
    except PlaywrightTimeout as e:
        log(f"❌ Timeout: {e}")
        return False
    except Exception as e:
        error_msg = str(e)
        log(f"❌ EXCEPTION: {type(e).__name__}: {error_msg}")
        
        # Don't print full traceback for known errors
        if "ProcessSingleton" in error_msg or "SingletonLock" in error_msg:
            log("   Profile is locked by another browser instance.")
            log("   Close all Chromium windows and try again.")
        elif "Target page, context or browser has been closed" in error_msg:
            log("   Browser was closed unexpectedly.")
        else:
            # Print traceback for unexpected errors
            import traceback
            tb = traceback.format_exc()
            log(f"TRACEBACK:\n{tb}")
        
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Search Instacart and capture results')
    parser.add_argument('keyword', help='Search keyword')
    parser.add_argument('--output-dir', required=True, help='Output directory')
    parser.add_argument('--store', help='Store slug (default: publix or INSTACART_STORE env var)')
    
    args = parser.parse_args()
    
    success = search_and_capture(args.keyword, args.output_dir, args.store)
    sys.exit(0 if success else 1)
