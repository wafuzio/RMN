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
from playwright.sync_api import sync_playwright
from Kroger_login import save_cookies  # Removed load_cookies as it's redundant with user_data_dir

# Constants
USER_DATA_DIR = os.path.expanduser("~/ChromeProfiles/kroger_clean_profile")
DEFAULT_SEARCH_TERM = "black forest ham"
DEFAULT_OUTPUT_DIR = "output"

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
            # Use a less strict wait_until parameter
            page.goto(search_url, wait_until="domcontentloaded")
            
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
            
            # Take a screenshot of the search results
            screenshot_path = os.path.join(output_dir, f"{file_prefix}.png")
            page.screenshot(path=screenshot_path, full_page=True)
            print("📷 Screenshot saved to {}".format(screenshot_path))
            
            # Check for TOA ads
            toa_divs = page.query_selector_all('div[data-testid="StandardTOA"]')
            print("🔍 Found {} TOA ads on the page".format(len(toa_divs)))
            
            # Save HTML for inspection
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
