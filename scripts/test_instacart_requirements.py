#!/usr/bin/env python3
"""
Test script to determine Instacart's requirements for ad visibility.

This script checks:
1. Can we access search results without login?
2. Does Instacart require store/location selection?
3. Are ads visible without authentication?
4. What URL patterns work for search?

Usage:
    python3 scripts/test_instacart_requirements.py
"""

import asyncio
from playwright.async_api import async_playwright
import json
from pathlib import Path


async def test_instacart_requirements():
    """Test Instacart's requirements for accessing search and ads."""
    
    results = {
        "no_login_access": False,
        "requires_store_selection": False,
        "requires_location": False,
        "ads_visible_without_login": False,
        "working_url_patterns": [],
        "notes": []
    }
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )
        page = await context.new_page()
        
        print("=" * 80)
        print("INSTACART REQUIREMENTS TEST")
        print("=" * 80)
        
        # Test 1: Direct search without store
        print("\n[Test 1] Trying direct search URL without store selection...")
        try:
            await page.goto('https://www.instacart.com/search?q=eggs', wait_until='networkidle')
            await page.wait_for_timeout(3000)
            
            # Check if we're redirected or blocked
            current_url = page.url
            print(f"  Current URL: {current_url}")
            
            # Check for login/signup modal
            login_modal = await page.query_selector('text=/sign up/i, text=/log in/i, input[type="email"]')
            if login_modal:
                results["notes"].append("⚠️  Login/signup modal blocks content - authentication required")
                print("  ⚠️  Login modal detected - authentication likely required for ads")
            
            # Check for store selection prompt
            store_selector = await page.query_selector('text=/select.*store/i')
            if store_selector:
                results["requires_store_selection"] = True
                results["notes"].append("Store selection required before search")
                print("  ❌ Store selection required")
            else:
                results["no_login_access"] = True
                results["working_url_patterns"].append("https://www.instacart.com/search?q={keyword}")
                print("  ✅ Direct search URL accessible (but may need login for content)")
                
        except Exception as e:
            results["notes"].append(f"Direct search failed: {str(e)}")
            print(f"  ❌ Error: {e}")
        
        # Test 2: Search with store specified
        print("\n[Test 2] Trying search with store (Publix)...")
        try:
            await page.goto('https://www.instacart.com/store/publix/search?q=eggs', wait_until='networkidle')
            await page.wait_for_timeout(3000)
            
            current_url = page.url
            print(f"  Current URL: {current_url}")
            
            # Check for location prompt
            location_prompt = await page.query_selector('text=/enter.*address/i, text=/zip.*code/i')
            if location_prompt:
                results["requires_location"] = True
                results["notes"].append("Location/zip code required for store-specific search")
                print("  ⚠️  Location prompt detected")
            else:
                results["working_url_patterns"].append("https://www.instacart.com/store/{store}/search?q={keyword}")
                print("  ✅ Store-specific search works")
            
            # Check for search results
            search_results = await page.query_selector('[data-testid*="item"], .e-fsno8i, [role="group"]')
            if search_results:
                print("  ✅ Search results visible")
                results["no_login_access"] = True
            else:
                print("  ❌ No search results found")
                
        except Exception as e:
            results["notes"].append(f"Store search failed: {str(e)}")
            print(f"  ❌ Error: {e}")
        
        # Test 3: Check for ads
        print("\n[Test 3] Checking for sponsored ads...")
        try:
            # Look for sponsored indicators from your HTML examples
            ad_selectors = [
                'div.e-1qzz7bi',  # Shoppable display ads
                'div.e-1hv1sre',  # Top banner ads
                'text=/sponsored/i',  # Sponsored text
                'div.e-cwus85',  # Sponsored label container
            ]
            
            ads_found = []
            for selector in ad_selectors:
                elements = await page.query_selector_all(selector)
                if elements:
                    ads_found.append(f"{selector}: {len(elements)} found")
                    print(f"  ✅ Found {len(elements)} elements matching: {selector}")
            
            if ads_found:
                results["ads_visible_without_login"] = True
                results["notes"].extend(ads_found)
            else:
                print("  ❌ No ads detected")
                
        except Exception as e:
            results["notes"].append(f"Ad detection failed: {str(e)}")
            print(f"  ❌ Error: {e}")
        
        # Test 4: Take screenshots for manual inspection
        print("\n[Test 4] Taking screenshots for manual review...")
        screenshot_dir = Path(__file__).parent.parent / "docs" / "instacart_test_screenshots"
        screenshot_dir.mkdir(exist_ok=True)
        
        await page.screenshot(path=screenshot_dir / "instacart_search_page.png", full_page=True)
        print(f"  📸 Screenshot saved to: {screenshot_dir / 'instacart_search_page.png'}")
        
        # Get page HTML for analysis
        html_content = await page.content()
        html_file = screenshot_dir / "instacart_search_page.html"
        html_file.write_text(html_content, encoding='utf-8')
        print(f"  💾 HTML saved to: {html_file}")
        
        await browser.close()
    
    # Print summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Can access without login: {results['no_login_access']}")
    print(f"Requires store selection: {results['requires_store_selection']}")
    print(f"Requires location/zip: {results['requires_location']}")
    print(f"Ads visible without login: {results['ads_visible_without_login']}")
    print(f"\nWorking URL patterns:")
    for pattern in results['working_url_patterns']:
        print(f"  - {pattern}")
    
    # Save results
    results_file = Path(__file__).parent.parent / "docs" / "instacart_requirements_test.json"
    results_file.write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(f"\n📊 Full results saved to: {results_file}")
    
    return results


if __name__ == "__main__":
    asyncio.run(test_instacart_requirements())
