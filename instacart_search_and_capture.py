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
    
    log(f"🔍 Searching Instacart for: '{keyword}'")
    log(f"   Store: {store}")
    log(f"   Profile: {profile_dir}")
    
    # Use Playwright with persistent context (authenticated session)
    log("Starting Playwright...")
    try:
        with sync_playwright() as p:
            # Launch with persistent context (authenticated session)
            context = p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=False,
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
                args=[
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--no-first-run',
                    '--no-default-browser-check',
                    '--disable-session-crashed-bubble',  # Suppress "Restore pages?" prompt
                ],
            )
            
            page = context.pages[0] if context.pages else context.new_page()
            
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
                page.wait_for_selector("div.e-1qzz7bi, div.e-1hv1sre", timeout=8000)
                log("Search: ad containers detected")
            except Exception:
                log("Search: ad containers not detected within 8s; using short settle delay")
                page.wait_for_timeout(3000)
            
            search_url = page.url
            log("✅ Authenticated session active")
            
            # Get page content
            html_content = page.content()
            
            # Save HTML
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"💾 HTML saved: {html_file}")
            
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
            
            # Find all ad containers
            # Note: div.e-1qzz7bi includes both Shoppable Display Ads and Shoppable Video Ads
            ad_selectors = {
                'Shoppable Display Ad': 'div.e-1qzz7bi',
                'Display Ad': 'div.e-1hv1sre',
                'Sponsored Label': 'div.e-cwus85',
            }
            
            for ad_type, selector in ad_selectors.items():
                elements = page.query_selector_all(selector)
                for i, elem in enumerate(elements):
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
                            "selector": selector,
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
                        
                        # Try to extract brand/title
                        try:
                            title_elem = elem.query_selector('h2, [role="heading"]')
                            if title_elem:
                                title = title_elem.inner_text()
                                ad_info["title"] = title
                                # Extract advertiser from title (matching Kroger structure)
                                if title:
                                    advertiser = None
                                    # Method 1: "Brand - Description" format
                                    if ' - ' in title:
                                        parts = title.split(' - ')
                                        if parts and parts[0]:
                                            advertiser = parts[0].strip()
                                    # Method 2: Look for capitalized brand names in title
                                    # e.g., "Unleash spooky Goldfish® fun" → "Goldfish"
                                    # e.g., "Amara Organic Smoothie Melts" → "Amara"
                                    elif not advertiser:
                                        # Look for capitalized words (potential brand names)
                                        words = title.split()
                                        for word in words:
                                            # Remove ® and ™ symbols
                                            clean_word = word.replace('®', '').replace('™', '').strip()
                                            # Check if word is capitalized and not a common word
                                            if (clean_word and clean_word[0].isupper() and 
                                                clean_word.lower() not in ['the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'from', 'by', 'as', 'is', 'was', 'are', 'were', 'been', 'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'unleash', 'love', 'what', 'you', 'your', 'our', 'refrigerated', 'organic', 'spooky', 'fun']):
                                                advertiser = clean_word
                                                break
                                    
                                    if advertiser:
                                        ad_info["advertisers"] = [advertiser]
                        except:
                            pass
                        
                        ad_data["results"][0]["ads"].append(ad_info)
                    except Exception as e:
                        print(f"⚠️  Could not extract data from {ad_type} #{i}: {e}")
            
            ad_count = len(ad_data['results'][0]['ads'])
            ad_data['count'] = ad_count
            print(f"📊 Found {ad_count} ad units")
            
            # Save JSON
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
