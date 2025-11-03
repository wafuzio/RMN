#!/usr/bin/env python3
"""
Instacart search and capture script.
Performs keyword search on Instacart and saves HTML + JSON results.

THIS IS THE OLD WORKING VERSION FROM COMMIT 7fb7fa9
"""

import os
import sys
import json
import time
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


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
            time.sleep(2)
            
            # Find and click search input (organic interaction)
            log(f"Searching for: {keyword}")
            try:
                # Instacart search input selectors
                search_input = page.locator('input[placeholder*="Search"], input[type="search"], input[aria-label*="Search"]').first
                search_input.click()
                time.sleep(0.5)
                
                # Type keyword with human-like delays
                search_input.type(keyword, delay=100)
                time.sleep(0.5)
                
                # Press Enter to submit (organic form submission)
                page.keyboard.press("Enter")
                log("   Submitted search via Enter key")
                
                # Wait for navigation to search results
                page.wait_for_url('**/s?k=**', timeout=10000)
                log("   Navigated to search results")
                
            except Exception as e:
                log(f"   Search box interaction failed: {e}")
                log("   Falling back to direct navigation...")
                # Fallback to direct navigation if search box not found
                search_url = f'https://www.instacart.com/store/{store}/s?k={keyword}'
                page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
            
            # Wait for content to load
            time.sleep(5)
            search_url = page.url
            
            # Check if we're logged in - look for login modal
            login_modal = page.query_selector('.ReactModalPortal .AuthModal__Overlay, [data-testid="authModalWrapper"]')
            if login_modal and login_modal.is_visible():
                print("❌ Login modal detected - session expired")
                print("   Please re-authenticate by running:")
                print("   ./scripts/setup_instacart_profile.sh")
                context.close()
                return False
            
            print("✅ Authenticated session active")
            
            # Get page content
            html_content = page.content()
            
            # Save HTML
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"💾 HTML saved: {html_file}")
            
            # Extract ad data for JSON
            ad_data = {
                "keyword": keyword,
                "store": store,
                "timestamp": timestamp,
                "url": search_url,
                "ads": []
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
                                ad_info["title"] = title_elem.inner_text()
                        except:
                            pass
                        
                        ad_data["ads"].append(ad_info)
                    except Exception as e:
                        print(f"⚠️  Could not extract data from {ad_type} #{i}: {e}")
            
            print(f"📊 Found {len(ad_data['ads'])} ad units")
            
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
