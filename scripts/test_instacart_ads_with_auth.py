#!/usr/bin/env python3
"""
Test script to verify Instacart ads are visible with authenticated session.

Usage:
    python3 scripts/test_instacart_ads_with_auth.py
"""

import asyncio
import os
from pathlib import Path
from playwright.async_api import async_playwright
import json


async def test_instacart_ads_with_auth():
    """Test that ads are visible with authenticated profile."""
    
    profile_dir = os.environ.get('INSTACART_PROFILE_DIR', 
                                  os.path.expanduser('~/Documents/Amazon_Scrape/profiles/instacart'))
    store = os.environ.get('INSTACART_STORE', 'publix')
    
    if not Path(profile_dir).exists():
        print(f"❌ Profile directory not found: {profile_dir}")
        print("Run: ./scripts/setup_instacart_profile.sh")
        return False
    
    print("=" * 80)
    print("INSTACART AD VISIBILITY TEST (WITH AUTH)")
    print("=" * 80)
    print(f"Profile: {profile_dir}")
    print(f"Store: {store}")
    print()
    
    results = {
        "authenticated": False,
        "ads_found": [],
        "ad_count": 0,
        "test_keyword": "eggs",
    }
    
    async with async_playwright() as p:
        # Launch with persistent context (authenticated session)
        context = await p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=False,
            viewport={'width': 1920, 'height': 1080},
        )
        
        page = context.pages[0] if context.pages else await context.new_page()
        
        # Test search with authentication
        # Correct URL format: /store/{store}/s?k={keyword}
        search_url = f'https://www.instacart.com/store/{store}/s?k=eggs'
        print(f"[1] Navigating to: {search_url}")
        
        try:
            # Don't wait for networkidle - Instacart has lots of dynamic content
            await page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(8000)  # Wait for dynamic content and ads to load
            
            # Check if we're logged in
            print("\n[2] Checking authentication status...")
            login_modal = await page.query_selector('text=/sign up/i, text=/log in/i')
            if login_modal and await login_modal.is_visible():
                print("  ❌ Login modal still visible - authentication may have failed")
                results["authenticated"] = False
            else:
                print("  ✅ No login modal - authenticated session active")
                results["authenticated"] = True
            
            # Look for ads using your HTML patterns
            print("\n[3] Scanning for ad units...")
            
            ad_selectors = {
                'Shoppable Display Ads (div.e-1qzz7bi)': 'div.e-1qzz7bi',
                'Top Banner Ads (div.e-1hv1sre)': 'div.e-1hv1sre',
                'Sponsored Labels (div.e-cwus85)': 'div.e-cwus85',
                'Video Ads (div[id^="video-player"])': 'div[id^="video-player"]',
            }
            
            for ad_type, selector in ad_selectors.items():
                elements = await page.query_selector_all(selector)
                if elements:
                    count = len(elements)
                    print(f"  ✅ {ad_type}: {count} found")
                    results["ads_found"].append({
                        "type": ad_type,
                        "selector": selector,
                        "count": count
                    })
                    results["ad_count"] += count
                else:
                    print(f"  ⚠️  {ad_type}: 0 found")
            
            # Take screenshots
            print("\n[4] Taking screenshots...")
            screenshot_dir = Path(__file__).parent.parent / "docs" / "instacart_auth_test"
            screenshot_dir.mkdir(exist_ok=True)
            
            await page.screenshot(
                path=screenshot_dir / "instacart_authenticated_search.png",
                full_page=True
            )
            print(f"  📸 Full page: {screenshot_dir / 'instacart_authenticated_search.png'}")
            
            # Screenshot each ad unit
            ad_containers = await page.query_selector_all('div.e-1qzz7bi, div.e-1hv1sre')
            for i, ad in enumerate(ad_containers[:5], 1):  # First 5 ads
                try:
                    await ad.screenshot(path=screenshot_dir / f"ad_unit_{i}.png")
                    print(f"  📸 Ad unit {i}: {screenshot_dir / f'ad_unit_{i}.png'}")
                except Exception as e:
                    print(f"  ⚠️  Could not screenshot ad {i}: {e}")
            
            # Save HTML
            html_content = await page.content()
            screenshot_dir.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
            html_file = screenshot_dir / "instacart_authenticated_search.html"
            html_file.write_text(html_content, encoding='utf-8')
            print(f"  💾 HTML: {html_file}")
            
        except Exception as e:
            print(f"\n❌ Error during test: {e}")
            results["error"] = str(e)
        
        await context.close()
    
    # Print summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Authenticated: {results['authenticated']}")
    print(f"Total ads found: {results['ad_count']}")
    
    if results['ad_count'] > 0:
        print("\n✅ SUCCESS: Ads are visible with authenticated session!")
        print("\nAd breakdown:")
        for ad in results['ads_found']:
            print(f"  - {ad['type']}: {ad['count']}")
    else:
        print("\n⚠️  WARNING: No ads detected")
        print("This could mean:")
        print("  1. No ads for this keyword/store combination")
        print("  2. Ads load dynamically (may need longer wait)")
        print("  3. Different selectors needed")
    
    # Save results
    results_dir = Path(__file__).parent.parent / "docs" / "instacart_auth_test"
    results_dir.mkdir(parents=True, exist_ok=True)
    results_file = results_dir / "test_results.json"
    results_file.write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(f"\n📊 Full results: {results_file}")
    
    return results['ad_count'] > 0


if __name__ == "__main__":
    success = asyncio.run(test_instacart_ads_with_auth())
    exit(0 if success else 1)
