#!/usr/bin/env python3
"""
Screenshot Instacart ad units from saved HTML.
Simple and fast - directly screenshots ad elements.
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def screenshot_instacart_ads(json_path: str, html_path: str, output_dir: str, profile_dir: str = None, headless: bool = True):
    """
    Screenshot Instacart ad units from saved HTML.
    
    Args:
        json_path: Path to run_results_*.json with ad metadata
        html_path: Path to search_results_*.html
        output_dir: Base output directory (e.g., output/instacart/client)
        profile_dir: Optional profile directory for authenticated session
        headless: Run browser in headless mode
    
    Returns:
        dict: Counts of screenshots taken by type
    """
    
    print(f"📸 Instacart Ad Screenshot Extractor")
    print(f"   JSON: {os.path.basename(json_path)}")
    print(f"   HTML: {os.path.basename(html_path)}")
    print(f"   Output: {output_dir}")
    
    # Load JSON metadata
    with open(json_path, 'r', encoding='utf-8') as f:
        ad_data = json.load(f)
    
    # Support both old flat structure and new Kroger-style nested structure
    if 'results' in ad_data and ad_data['results']:
        ads = ad_data['results'][0].get('ads', [])
    else:
        ads = ad_data.get('ads', [])
    
    url = ad_data.get('url')
    
    print(f"   Found {len(ads)} ads in JSON")
    print(f"   URL: {url}")
    
    if not ads:
        print("⚠️  No ads to screenshot")
        return {"shoppable_display": 0, "shoppable_video": 0, "display_ad": 0}
    
    # Create output directories - Instacart-specific folders
    shoppable_display_dir = os.path.join(output_dir, "Shoppable_Display_Ads")
    shoppable_video_dir = os.path.join(output_dir, "Shoppable_Video_Ads")
    display_ad_dir = os.path.join(output_dir, "Display_Ads")
    main_dir = os.path.join(output_dir, "Main")  # For full-page screenshot
    
    for d in [shoppable_display_dir, shoppable_video_dir, display_ad_dir, main_dir]:
        os.makedirs(d, exist_ok=True)
    
    counts = {"shoppable_display": 0, "shoppable_video": 0, "display_ad": 0}
    
    # Extract keyword and timestamp from JSON for file naming
    keyword = ad_data.get('keyword', 'unknown').replace(' ', '_')
    timestamp = ad_data.get('timestamp', datetime.now().strftime("%Y%m%d_%H%M%S"))
    
    # Clean up stale lock file if it exists
    if profile_dir and os.path.isdir(profile_dir):
        lock_file = os.path.join(profile_dir, 'SingletonLock')
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
                print(f"   Removed stale lock file")
            except Exception as e:
                print(f"   Warning: Could not remove lock file: {e}")
    
    # Launch Playwright
    with sync_playwright() as p:
        if profile_dir and os.path.isdir(profile_dir):
            # Use persistent context for authenticated session
            context = p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=headless,
                viewport={'width': 1920, 'height': 1080}
            )
            page = context.pages[0] if context.pages else context.new_page()
        else:
            # Use regular browser
            browser = p.chromium.launch(headless=headless)
            page = browser.new_page(viewport={'width': 1920, 'height': 1080})
        
        # Navigate to the actual URL (like the test does)
        if url:
            print(f"   Loading page: {url}")
            page.goto(url, wait_until='domcontentloaded', timeout=30000)
            page.wait_for_timeout(3000)  # Wait for ads to load
        else:
            # Fallback: load HTML content
            print("   No URL in JSON, loading from HTML file")
            with open(html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            page.set_content(html_content, wait_until='domcontentloaded')
            page.wait_for_timeout(2000)
        
        # Take full-page screenshot (scroll to bottom then back up like Kroger)
        print("\n   Taking full-page screenshot...")
        try:
            # Scroll to bottom to load all content
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1000)
            
            # Scroll back to top
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(500)
            
            # Take full-page screenshot with Kroger-style naming
            fullpage_filename = f"FullPage_{keyword}_{timestamp}.png"
            fullpage_path = os.path.join(main_dir, fullpage_filename)
            page.screenshot(path=fullpage_path, full_page=True)
            print(f"  ✅ Full page: Main/{fullpage_filename}")
        except Exception as e:
            print(f"  ⚠️  Could not capture full page: {e}")
        
        # Screenshot ad containers (like the test does)
        # Query all major ad containers at once
        print("\n   Querying ad containers...")
        shoppable_ads = page.query_selector_all('div.e-1qzz7bi')  # Shoppable Display + Video
        display_ads = page.query_selector_all('div.e-1hv1sre')    # Display Ads (banners)
        
        print(f"   Found {len(shoppable_ads)} shoppable ads")
        print(f"   Found {len(display_ads)} display ads")
        
        # Screenshot shoppable ads with Kroger-style naming
        for i, ad in enumerate(shoppable_ads):
            try:
                # Scroll element into view to ensure it's fully visible
                ad.scroll_into_view_if_needed()
                page.wait_for_timeout(500)  # Let it settle
                
                # Kroger-style naming: Type_SearchTerm_Date_Time
                filename = f"ShoppableDisplayAd_{keyword}_{timestamp}_{i+1}.png"
                filepath = os.path.join(shoppable_display_dir, filename)
                ad.screenshot(path=filepath)
                counts["shoppable_display"] += 1
                print(f"  ✅ Shoppable Display {i+1}: {filename}")
            except Exception as e:
                print(f"  ❌ Error screenshotting shoppable ad {i+1}: {e}")
        
        # Screenshot display ads with Kroger-style naming
        for i, ad in enumerate(display_ads):
            try:
                # Scroll element into view to ensure it's fully visible
                ad.scroll_into_view_if_needed()
                page.wait_for_timeout(500)  # Let it settle
                
                # Kroger-style naming: Type_SearchTerm_Date_Time
                filename = f"DisplayAd_{keyword}_{timestamp}_{i+1}.png"
                filepath = os.path.join(display_ad_dir, filename)
                ad.screenshot(path=filepath)
                counts["display_ad"] += 1
                print(f"  ✅ Display Ad {i+1}: {filename}")
            except Exception as e:
                print(f"  ❌ Error screenshotting display ad {i+1}: {e}")
        
        # Close browser
        if profile_dir:
            context.close()
        else:
            browser.close()
    
    print(f"\n📊 Screenshot Summary:")
    print(f"   Shoppable Display Ads: {counts['shoppable_display']}")
    print(f"   Shoppable Video Ads: {counts['shoppable_video']}")
    print(f"   Display Ads: {counts['display_ad']}")
    
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Screenshot Instacart ads from saved HTML')
    parser.add_argument('--json', required=True, help='Path to run_results_*.json')
    parser.add_argument('--html', required=True, help='Path to search_results_*.html')
    parser.add_argument('--output', required=True, help='Output directory')
    parser.add_argument('--profile-dir', help='Profile directory for authenticated session')
    parser.add_argument('--headless', action='store_true', default=True, help='Run headless')
    parser.add_argument('--no-headless', dest='headless', action='store_false', help='Show browser')
    
    args = parser.parse_args()
    
    counts = screenshot_instacart_ads(
        json_path=args.json,
        html_path=args.html,
        output_dir=args.output,
        profile_dir=args.profile_dir,
        headless=args.headless
    )
    
    # Exit with success if we got at least one ad
    total_ads = counts['shoppable_display'] + counts['shoppable_video'] + counts['display_ad']
    if total_ads > 0:
        sys.exit(0)
    else:
        print("\n⚠️  No ads captured")
        sys.exit(1)
