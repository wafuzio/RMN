#!/usr/bin/env python3
"""
Experimental Kroger scraper using curl_cffi with TLS impersonation.

This is a parallel path to test if curl_cffi can bypass Akamai detection
that blocks Playwright. Uses real browser TLS fingerprints without CDP.

Approach:
1. Use Playwright once to get authenticated cookies
2. Use curl_cffi with those cookies to hit Kroger's API
3. No JavaScript execution = No navigator.webdriver detection
4. Perfect TLS fingerprint = Bypasses TLS-based detection

Usage:
    # First, get cookies from a real browser session
    python3 experiments/kroger_curl_cffi_test.py --get-cookies
    
    # Then test API access
    python3 experiments/kroger_curl_cffi_test.py --search "black forest ham"
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any, Optional

try:
    from curl_cffi import requests
except ImportError:
    print("ERROR: curl_cffi not installed")
    print("Install with: pip install curl-cffi")
    sys.exit(1)


COOKIES_FILE = Path(__file__).parent / "kroger_cookies.json"
OUTPUT_DIR = Path(__file__).parent / "curl_cffi_output"


def parse_cookie_string(cookie_str: str) -> Dict[str, str]:
    """Parse 'name=value; name2=value2' into a dict."""
    cookies = {}
    for part in cookie_str.split("; "):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, _, value = part.partition("=")
        cookies[name.strip()] = value.strip()
    return cookies


def save_cookies(cookies: Dict[str, str]):
    """Save cookies to JSON file."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    with open(COOKIES_FILE, "w") as f:
        json.dump(cookies, f, indent=2)
    print(f"✅ Cookies saved to {COOKIES_FILE}")


def load_cookies() -> Optional[Dict[str, str]]:
    """Load cookies from JSON file."""
    if not COOKIES_FILE.exists():
        return None
    with open(COOKIES_FILE) as f:
        return json.load(f)


def get_cookies_from_playwright():
    """
    Use Playwright to authenticate and extract cookies.
    This is a one-time setup step.
    """
    print("🔐 Launching Playwright to get authenticated cookies...")
    print("   You'll need to log in manually if not already logged in.")
    
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: Playwright not installed")
        print("Install with: pip install playwright")
        sys.exit(1)
    
    with sync_playwright() as p:
        # Use persistent context with existing profile
        profile_dir = os.path.expanduser("~/ChromeProfiles/kroger_clean_profile")
        
        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=False,
                channel="chrome",
            )
            
            page = context.pages[0] if context.pages else context.new_page()
            
            print("   Navigating to Kroger homepage...")
            page.goto("https://www.kroger.com/", wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            
            # Check if logged in
            is_logged_in = not page.is_visible("text=Sign In")
            if not is_logged_in:
                print("   ⚠️ Not logged in - please log in manually")
                print("   Press Enter when logged in...")
                input()
            
            # Extract cookies
            print("   Extracting cookies...")
            cookies_list = context.cookies("https://www.kroger.com/")
            cookies = {c["name"]: c["value"] for c in cookies_list}
            
            print(f"   ✅ Extracted {len(cookies)} cookies")
            
            # Show Akamai cookies
            akamai_cookies = [k for k in cookies.keys() if k.startswith(("_abck", "bm_", "ak_"))]
            if akamai_cookies:
                print(f"   Akamai cookies: {', '.join(akamai_cookies)}")
            
            context.close()
            save_cookies(cookies)
            return cookies
            
        except Exception as e:
            print(f"❌ Error getting cookies: {e}")
            return None


def test_homepage_access(cookies: Dict[str, str], impersonate: str = "chrome124"):
    """
    Test basic homepage access with curl_cffi.
    """
    print(f"\n🌐 Testing homepage access with impersonate='{impersonate}'...")
    
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "max-age=0",
        "sec-ch-ua": '"Google Chrome";v="124", "Chromium";v="124", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    }
    
    try:
        with requests.Session(impersonate=impersonate) as session:
            response = session.get(
                "https://www.kroger.com/",
                headers=headers,
                cookies=cookies,
                timeout=30,
            )
            
            print(f"   Status: {response.status_code}")
            print(f"   Content-Length: {len(response.text)}")
            
            # Check for Akamai block
            if "Access Denied" in response.text:
                print("   ❌ BLOCKED: Access Denied page detected")
                return False
            elif "errors.edgesuite.net" in response.text:
                print("   ❌ BLOCKED: Akamai CDN error page")
                return False
            elif len(response.text) < 1000:
                print(f"   ⚠️ WARNING: Suspiciously small page ({len(response.text)} bytes)")
                return False
            else:
                print("   ✅ SUCCESS: Homepage loaded")
                
                # Save response for inspection
                OUTPUT_DIR.mkdir(exist_ok=True)
                output_file = OUTPUT_DIR / "homepage_response.html"
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(response.text)
                print(f"   Saved to: {output_file}")
                return True
                
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        return False


def find_search_api(cookies: Dict[str, str]):
    """
    Attempt to find Kroger's search API endpoint.
    This requires reverse-engineering their API.
    """
    print("\n🔍 Attempting to find search API endpoint...")
    print("   Note: This requires reverse-engineering Kroger's API")
    print("   You may need to inspect network requests in browser DevTools")
    
    # Common API patterns to try
    potential_endpoints = [
        "https://www.kroger.com/products/api/search",
        "https://www.kroger.com/api/v1/products/search",
        "https://www.kroger.com/search/api",
        "https://api.kroger.com/v1/products",
    ]
    
    headers = {
        "accept": "application/json",
        "accept-language": "en-US,en;q=0.9",
        "referer": "https://www.kroger.com/",
        "sec-ch-ua": '"Google Chrome";v="124", "Chromium";v="124", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    }
    
    with requests.Session(impersonate="chrome124") as session:
        for endpoint in potential_endpoints:
            print(f"   Trying: {endpoint}")
            try:
                response = session.get(
                    endpoint,
                    params={"q": "test"},
                    headers=headers,
                    cookies=cookies,
                    timeout=10,
                )
                print(f"      Status: {response.status_code}")
                
                if response.status_code == 200:
                    print(f"      ✅ Found working endpoint!")
                    print(f"      Response preview: {response.text[:200]}")
                    return endpoint
                    
            except Exception as e:
                print(f"      ❌ Error: {e}")
    
    print("\n   ⚠️ No working API endpoint found")
    print("   Next steps:")
    print("   1. Open Kroger in browser DevTools")
    print("   2. Search for a product")
    print("   3. Look for XHR/Fetch requests in Network tab")
    print("   4. Find the API endpoint that returns product data")
    return None


def main():
    parser = argparse.ArgumentParser(description="Experimental Kroger curl_cffi scraper")
    parser.add_argument("--get-cookies", action="store_true", help="Get cookies from Playwright")
    parser.add_argument("--search", type=str, help="Search term to test")
    parser.add_argument("--impersonate", type=str, default="chrome124", 
                       help="Browser to impersonate (chrome124, edge, firefox)")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Kroger curl_cffi Experimental Scraper")
    print("=" * 60)
    
    if args.get_cookies:
        cookies = get_cookies_from_playwright()
        if not cookies:
            sys.exit(1)
        return
    
    # Load cookies
    cookies = load_cookies()
    if not cookies:
        print("❌ No cookies found")
        print("   Run with --get-cookies first")
        sys.exit(1)
    
    print(f"✅ Loaded {len(cookies)} cookies from {COOKIES_FILE}")
    
    # Test homepage access
    success = test_homepage_access(cookies, args.impersonate)
    
    if success:
        # Try to find search API
        find_search_api(cookies)
    
    print("\n" + "=" * 60)
    print("Test complete")
    print("=" * 60)


if __name__ == "__main__":
    main()
