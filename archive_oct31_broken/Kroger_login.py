from playwright.sync_api import sync_playwright, Playwright
import os
import json
import time
from datetime import datetime

STEALTH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# Cookie file path
COOKIE_FILE = "cookies_kroger.json"

def save_cookies(context, filename=COOKIE_FILE):
    """Save cookies from browser context to a file"""
    cookies = context.cookies()
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(cookies, f, indent=2)
    print("✅ Saved {} cookies to {}".format(len(cookies), filename))
    return cookies

def load_cookies(context, filename=COOKIE_FILE):
    """Load cookies from file into browser context"""
    try:
        if not os.path.exists(filename):
            print("⚠️ Cookie file {} not found".format(filename))
            return False
            
        with open(filename, "r", encoding="utf-8") as f:
            cookies = json.load(f)
            
        if not cookies:
            print("⚠️ No cookies found in file")
            return False
        
        # Fix sameSite property - Playwright expects "None", "Lax", or "Strict" as strings
        for cookie in cookies:
            if "sameSite" in cookie and cookie["sameSite"] is None:
                cookie["sameSite"] = "None"  # Convert null to string "None"
            
        context.add_cookies(cookies)
        print("✅ Loaded {} cookies from {}".format(len(cookies), filename))
        return True
    except FileNotFoundError as e:
        print("❌ Cookie file not found: {}".format(e))
        return False
    except json.JSONDecodeError as e:
        print("❌ Invalid cookie file format: {}".format(e))
        return False
    except IOError as e:
        print("❌ Error reading cookie file: {}".format(e))
        return False
    except ValueError as e:
        print("❌ Invalid cookie data: {}".format(e))
        return False

def get_authenticated_context(user_data_dir: str):
    def _inner(playwright, user_data_dir):
        assert user_data_dir, "user_data_dir must be provided for bot avoidance"

        user_data_dir = os.path.expanduser(user_data_dir)
        os.makedirs(user_data_dir, exist_ok=True)
        
        # Launch browser with persistent context
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
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
        
        # Try to load cookies first
        cookies_loaded = load_cookies(context)
        
        # Navigate to Kroger homepage
        page.goto("https://www.kroger.com/", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        
        # Check if we're already logged in by looking for account elements
        is_logged_in = "Sign In" not in page.content()
        
        if not is_logged_in:
            print("⚠️ Not logged in, attempting login process...")
            try:
                # Click top-right profile dropdown trigger
                page.click("text=Sign In")
                page.wait_for_timeout(1000)  # wait for dropdown

                # Click actual Sign In button inside dropdown
                page.click('[data-testid="WelcomeMenuButtonSignIn"]')
            except TimeoutError as e:
                print("⚠️ Timed out waiting for Sign In button - please log in manually.")
                print("Error: {}".format(e))
            except ValueError as e:
                print("⚠️ Invalid selector for Sign In button - please log in manually.")
                print("Error: {}".format(e))
            except Exception as e:
                print("⚠️ Could not click one of the Sign In buttons – please log in manually.")
                print("Error: {}".format(e))
            
            print("⚠️ Please log in manually in the opened browser...")
            page.wait_for_timeout(90000)  # Give 90s for manual login
            
            # After login, save cookies for future use
            save_cookies(context)
            
            # Wait a bit more to ensure everything is saved properly
            page.wait_for_timeout(5000)
        else:
            print("✅ Already logged in!")

        return context, page

    with sync_playwright() as playwright:
        return _inner(playwright, user_data_dir)

if __name__ == "__main__":
    get_authenticated_context(user_data_dir="~/ChromeProfiles/kroger_clean_profile")