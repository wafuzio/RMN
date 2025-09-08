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
import json
import urllib.parse
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright
from playwright._impl._errors import Error as PWError
from Kroger_login import save_cookies  # Removed load_cookies as it's redundant with user_data_dir

# --- Lightweight diagnostics (screenshots + metrics) ---
PROJECT_ROOT = Path(__file__).resolve().parent
DIAG_DIR = PROJECT_ROOT / "diagnostics"
DIAG_DIR.mkdir(parents=True, exist_ok=True)

def dlog(msg: str):
    from datetime import datetime as _dt
    ts = _dt.now().strftime("%H:%M:%S")
    print(f"[scroll] {ts} {msg}")

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

def scroll_results(page, max_loops=120, step_ratio=0.85, sleep_ms=600):
    """
    Scroll the top-level document in controlled steps, backing off when no progress.
    Returns a dict with metrics you can save.
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
          const metrics = [];

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
            await sleep(sleepMs + Math.floor(Math.random() * 250)); // tiny jitter

            const y = scrollEl.scrollTop;
            const h = scrollEl.scrollHeight;
            const products = document.querySelectorAll('[data-testid*="product"], [class*="product-card"]').length;
            const ads = document.querySelectorAll('[data-testid="monetization/search-page-top"], [data-testid="StandardTOA"]').length;

            metrics.push({ loop: i, y, h, products, ads });

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
          await sleep(500); // Wait for scroll to complete
        
          // Verify we're at the top
          const finalY = (document.scrollingElement || document.documentElement || document.body).scrollTop;
          const finalH = (document.scrollingElement || document.documentElement || document.body).scrollHeight;
          console.log(`After scrolling back to top: Y=${finalY} of ${finalH}`);

          return {
            finalY: finalY,
            finalH: finalH,
            metrics
          };
        }
        """,
        {"maxLoops": max_loops, "stepRatio": step_ratio, "sleepMs": sleep_ms},
    )

def search_and_capture(search_term=None, output_dir=None):
    """Test if the session persists between browser launches"""
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
    with sync_playwright() as p:
        # Try to launch using Playwright's default browser first
        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir=USER_DATA_DIR,
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-infobars",
                    "--disable-web-security",
                ]
            )
        except Exception as e:
            print(f"Error launching browser with default settings: {e}")
            print("Trying alternative browser launch method...")
            # Fall back to using system Chrome if available
            context = p.chromium.launch_persistent_context(
                user_data_dir=USER_DATA_DIR,
                headless=False,
                channel="chrome",  # Try using the system Chrome
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-infobars",
                    "--disable-web-security",
                ]
            )
        
        page = context.pages[0] if context.pages else context.new_page()
        
        # No need to load cookies manually when using user_data_dir
        # Playwright already loads cookies from the persistent profile
        
        # Navigate to Kroger homepage
        page.goto("https://www.kroger.com/", wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        
        # Check if we're logged in using selector-based check (more efficient)
        is_logged_in = not page.is_visible("text=Sign In")
        
        if is_logged_in:
            print("✅ Already logged in! Session persistence is working.")
        else:
            print("⚠️ Not logged in. Will attempt login process...")
            try:
                # Click top-right profile dropdown trigger
                page.click("text=Sign In")
                page.wait_for_timeout(1000)  # wait for dropdown

                # Click actual Sign In button inside dropdown
                page.click('[data-testid="WelcomeMenuButtonSignIn"]')
                
                print("⚠️ Please log in manually in the opened browser...")
                print("   Waiting 90 seconds for manual login...")
                page.wait_for_timeout(90000)  # Give 90s for manual login
                
                # Check again if we're logged in using selector-based check
                is_logged_in = not page.is_visible("text=Sign In")
                if is_logged_in:
                    print("✅ Successfully logged in manually")
                    # Save cookies for future use
                    save_cookies(context)
                else:
                    print("❌ Login failed. Test cannot continue.")
                    context.close()
                    return False
            except TimeoutError as e:
                print("❌ Timeout error during login process: {}".format(e))
                context.close()
                return False
            except (ValueError, TypeError) as e:
                print("❌ Value or type error during login process: {}".format(e))
                context.close()
                return False
            except (ConnectionError, ConnectionRefusedError) as e:
                print("❌ Connection error during login process: {}".format(e))
                context.close()
                return False
            except RuntimeError as e:
                print("❌ Runtime error during login process: {}".format(e))
                context.close()
                return False
        
        # Step 3: Perform the search query
        print("\n🔎 Step 3: Performing search...")
        search_url = "https://www.kroger.com/search?query={}".format(urllib.parse.quote_plus(search_term))
        
        try:
            # Use simpler wait conditions to avoid timeouts
            page.goto(search_url, wait_until="domcontentloaded")
            
            # Wait for the page to stabilize without strict URL matching
            print("   Waiting for page to stabilize...")
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception as e:
                print(f"   Network idle wait timed out: {e} - continuing anyway")
                
            # Check if we're on the right page by looking for product grid
            print("   Checking for product grid...")
            try:
                page.wait_for_selector('[data-testid*="product"], [class*="product-card"]', timeout=10000)
                print("   Product grid found")
            except Exception:
                print("   No product grid found within timeout - continuing anyway")
            
            # Log the page and frame information
            print(f"page.url: {page.url}")
            print("Frames:\n" + "\n".join([f"  - {f.url or '<no url>'}" for f in page.frames]))
            
            # Wait longer for the page to stabilize
            print("   Waiting for page to stabilize...")
            page.wait_for_timeout(5000)

            # Product grid check already done above

            # Scroll results before capture and write lightweight diagnostics
            try:
                before_png = DIAG_DIR / "before.png"
                after_png = DIAG_DIR / "after.png"
                metrics_json = DIAG_DIR / "scroll_metrics.json"

                page.screenshot(path=str(before_png), full_page=False)
                dlog(f"Saved {before_png}")

                m = scroll_results(page)  # perform body scrolling on current page
                dlog(f"finalY={m.get('finalY')} finalH={m.get('finalH')} steps={len(m.get('metrics') or [])}")

                with open(metrics_json, "w", encoding="utf-8") as f:
                    json.dump(m, f, indent=2)
                dlog(f"Saved {metrics_json}")

                page.screenshot(path=str(after_png), full_page=False)
                dlog(f"Saved {after_png}")
            except Exception as e:
                print(f"   Scroll step skipped due to error: {e}")
            
            # Wait longer for the page to stabilize
            print("   Waiting for page to stabilize...")
            page.wait_for_timeout(10000)
            
            # Check if we're still logged in after search using selector-based check
            is_still_logged_in = not page.is_visible("text=Sign In")
            
            if is_still_logged_in:
                print("✅ Still logged in after search")
            else:
                print("❌ Session lost during search")
                context.close()
                return False
                
            # Create search-specific filename with sanitized search term
            safe_search_term = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in search_term)
            file_prefix = f"search_results_{safe_search_term}_{timestamp}"
            
            # Create main and TOA subfolders if they don't exist
            main_dir = os.path.join(output_dir, "main")
            toa_dir = os.path.join(output_dir, "TOA")
            os.makedirs(main_dir, exist_ok=True)
            os.makedirs(toa_dir, exist_ok=True)
            
            # Use scroll_results to scroll the page before screenshot capture
            print("   Scrolling page before screenshot...")
            try:
                scroll_result = scroll_results(page)
                print(f"   Scrolling completed. Scrolled to Y={scroll_result['finalY']} of {scroll_result['finalH']}")
            except Exception as e:
                print(f"   Warning: Scrolling failed: {e}")
            
            # Take a screenshot of the search results and save in main subfolder
            screenshot_path = os.path.join(main_dir, f"{file_prefix}.png")
            page.screenshot(path=screenshot_path, full_page=True)
            print("📷 Screenshot saved to {}".format(screenshot_path))
            
            # Check for TOA ads
            toa_divs = page.query_selector_all('div[data-testid="StandardTOA"]')
            print("🔍 Found {} TOA ads on the page".format(len(toa_divs)))
            
            # Save HTML for inspection (keep in root directory for compatibility)
            html_path = os.path.join(output_dir, f"{file_prefix}.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(page.content())
            print("💾 HTML saved to {}".format(html_path))
            
        except (TimeoutError, ConnectionError) as e:
            print("❌ Network or timeout error during search test: {}".format(e))
            context.close()
            return False
        except (ValueError, TypeError) as e:
            print("❌ Value or type error during search test: {}".format(e))
            context.close()
            return False
        except RuntimeError as e:
            print("❌ Runtime error during search test: {}".format(e))
            context.close()
            return False
        except Exception as e:
            print("❌ Unexpected error during search test: {}".format(e))
            context.close()
            return False
        
        # Step 4: Skip the TOA extraction function test in this run to avoid asyncio error
        print("\n🧪 Step 4: Skipping TOA extraction function test to avoid asyncio error")
        print("   The TOA extraction can be tested separately with a dedicated script")
        
        # Close the browser
        context.close()
        
        # Mark test as successful since we've verified the main session persistence
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
