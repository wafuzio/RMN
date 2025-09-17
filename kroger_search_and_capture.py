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

def scroll_results(page, max_loops=120, step_ratio=0.85, sleep_ms=600):
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
            await sleep(sleepMs + Math.floor(Math.random() * 250)); // tiny jitter

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
          await sleep(500); // Wait for scroll to complete
        
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
                    "--window-position=10000,10000",  # Position window off-screen
                    "--window-size=1280,720",         # Set reasonable size
                    "--disable-focus-on-show",        # Prevent focus stealing
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
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-infobars",
                    "--disable-web-security",
                    "--window-position=10000,10000",  # Position window off-screen
                    "--window-size=1280,720",         # Set reasonable size
                    "--disable-focus-on-show",        # Prevent focus stealing
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
            
            # Short, "whichever happens first" readiness wait
            print("   Waiting for page to be ready...")
            try:
                # Use Promise.race in JavaScript to implement "whichever happens first"
                page.evaluate("""
                async () => {
                    return await Promise.race([
                        // Option 1: Wait for products to appear (up to 3s)
                        new Promise(resolve => {
                            const checkProducts = () => {
                                const products = document.querySelectorAll('[data-testid*="product"], [class*="product-card"]');
                                if (products.length > 0) {
                                    console.log(`Found ${products.length} products`); 
                                    resolve('products_found');
                                    return true;
                                }
                                return false;
                            };
                            
                            // Check immediately
                            if (checkProducts()) return;
                            
                            // Check every 300ms for 3s
                            let attempts = 0;
                            const interval = setInterval(() => {
                                attempts++;
                                if (checkProducts() || attempts >= 10) {
                                    clearInterval(interval);
                                    if (attempts >= 10) resolve('products_timeout');
                                }
                            }, 300);
                        }),
                        
                        // Option 2: DOM is ready enough
                        new Promise(resolve => {
                            if (document.readyState === 'complete' || 
                                document.querySelectorAll('body *').length > 50) {
                                resolve('dom_ready');
                            } else {
                                window.addEventListener('DOMContentLoaded', () => resolve('dom_loaded'));
                                // Backup timeout
                                setTimeout(() => resolve('dom_timeout'), 3000);
                            }
                        })
                    ]);
                }
                """)
                print("   Page is ready for scrolling")
            except Exception as e:
                print(f"   Readiness wait error: {e} - continuing anyway")
                
            # Log the page and frame information
            print(f"page.url: {page.url}")
            print("Frames:\n" + "\n".join([f"  - {f.url or '<no url>'}" for f in page.frames]))

            # Product grid check already done above

            # Create sanitized search term for filenames
            safe_search_term = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in search_term)
            
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
            # Note: We already created safe_search_term above, so we'll reuse it
            file_prefix = f"search_results_{safe_search_term}_{timestamp}"
            
            # Create main and TOA subfolders if they don't exist
            main_dir = os.path.join(output_dir, "main")
            toa_dir = os.path.join(output_dir, "TOA")
            os.makedirs(main_dir, exist_ok=True)
            os.makedirs(toa_dir, exist_ok=True)
            
            # Use scroll_results to scroll the page before screenshot capture
            print("   Scrolling page before screenshot...")
            try:
                # Scroll the page to load all content
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
            
            # Use a single, comprehensive selector for the main carousel
            # This prevents duplicate captures of the same carousel
            carousel_selectors = [
                'div.CuratedCarousel, div[class*="Carousel"]:has(.kds-Heading--xl)'  # Main carousel with heading
            ]
            
            # Create carousel directory
            carousel_dir = os.path.join(output_dir, "Carousel")
            os.makedirs(carousel_dir, exist_ok=True)
            
            # Try each selector
            carousel_count = 0
            captured_carousel = False  # Flag to track if we've already captured a carousel
            for selector in carousel_selectors:
                # Skip if we've already captured a carousel
                if captured_carousel:
                    break
                    
                carousels = page.query_selector_all(selector)
                if carousels:
                    print(f"🎠 Found {len(carousels)} carousel elements with selector: {selector}")
                    
                    for i, carousel in enumerate(carousels):
                        try:
                            # Inject CSS to hide sticky headers/filters before scrolling carousel into view
                            page.add_style_tag(content="""
                                header,
                                .Header,
                                .kds-Header,
                                [data-testid="header"],
                                .kds-StickyHeader,
                                .SearchFilters,
                                .search-page-filters,
                                [class*="sticky"]
                                {
                                  display: none !important;
                                }
                            """)
                            # Scroll the carousel into view
                            carousel.scroll_into_view_if_needed()
                            
                            # Wait a moment for any animations or lazy-loaded content
                            page.wait_for_timeout(500)
                            
                            # Get carousel header text if available - expanded selector list
                            header = carousel.query_selector(
                                '.CuratedCarousel__header, h2, .header, .kds-Heading, .headerSection-header, [class*="header"], [class*="title"]'
                            )
                            
                            # Skip carousels without headers only if we have multiple carousels
                            if not header and len(carousels) > 1:
                                print(f"⚠️ Skipping carousel {i+1} - no header found")
                                continue
                                
                            # If no header found but this is the only carousel, proceed anyway
                            header_text = header.text_content().strip() if header else "main_carousel"
                            
                            # Skip carousels with empty headers only if we have multiple carousels
                            if not header_text and len(carousels) > 1:
                                print(f"⚠️ Skipping carousel {i+1} - empty header text")
                                continue
                                
                            # Generate filename
                            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                            safe_header = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in header_text.lower())
                            safe_header = safe_header[:30]  # Limit length
                            
                            # Include search term in filename
                            safe_search_term = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in search_term.lower())
                            
                            filename = f"carousel_{safe_header}_{safe_search_term}_{timestamp}.png"
                            filepath = os.path.join(carousel_dir, filename)
                            
                            # Take screenshot of the entire carousel as a single image
                            try:
                                # Get bounding box
                                box = carousel.bounding_box()
                                pad = 16  # Add padding around the element
                                
                                # Create clip area with padding
                                clip = {
                                    "x": max(0, box["x"] - pad),
                                    "y": max(0, box["y"] - pad),
                                    "width": min(page.viewport_size()["width"] - box["x"] + pad, box["width"] + 2 * pad),
                                    "height": box["height"] + 2 * pad
                                }
                                
                                # Take screenshot with clip area - capturing the entire carousel
                                page.screenshot(path=filepath, clip=clip)
                                print(f"📸 Carousel screenshot saved to: {filepath}")
                                carousel_count += 1
                                captured_carousel = True  # Mark that we've captured a carousel
                                
                                # Break after capturing the first carousel
                                break
                                
                            except Exception as e:
                                print(f"❌ Error taking screenshot with padding: {e}")
                                
                                # Fallback: take direct element screenshot
                                try:
                                    carousel.screenshot(path=filepath)
                                    print(f"📸 Carousel screenshot saved to: {filepath} (direct method)")
                                    carousel_count += 1
                                    captured_carousel = True  # Mark that we've captured a carousel
                                    break  # Break after capturing the first carousel
                                except Exception as e2:
                                    print(f"❌ Error taking direct screenshot: {e2}")
                        
                        except Exception as e:
                            print(f"❌ Error processing carousel {i+1}: {e}")
            
            if carousel_count == 0:
                print("⚠️ No carousels found or captured")
            else:
                print(f"✅ Successfully captured {carousel_count} carousel(s)")
            
            # Save HTML content to file
            html_path = os.path.join(output_dir, f"{file_prefix}.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(page.content())
            print("💾 HTML saved to {}".format(html_path))
            
            # Process the HTML file to extract TOAs with search term
            try:
                from process_saved_html import extract_ads_from_html_file
                # Pass the HTML file path to ensure only this run's results are processed for images
                extract_ads_from_html_file(html_path, process_images_for_html=html_path)
            except Exception as e:
                print(f"   Note: Could not process HTML file immediately: {e}")
            
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
