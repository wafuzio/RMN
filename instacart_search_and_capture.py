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
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


def search_and_capture(keyword: str, output_dir: str, store: str = None) -> bool:
    """
    Search Instacart for a keyword and capture the results page.
    
    Args:
        keyword: Search term
        output_dir: Base output directory (e.g., output/instacart/client_name)
        store: Store slug (e.g., 'publix'). Defaults to INSTACART_STORE env var or 'publix'
    
    Returns:
        True if successful, False otherwise
    """
    
    # Get store from parameter or environment
    if store is None:
        store = os.environ.get('INSTACART_STORE', 'publix')
    
    # Get profile directory
    profile_dir = os.environ.get('INSTACART_PROFILE_DIR')
    if not profile_dir or not os.path.isdir(profile_dir):
        print(f"❌ INSTACART_PROFILE_DIR not set or invalid: {profile_dir}")
        print("Run: ./scripts/setup_instacart_profile.sh")
        return False
    
    # Create runs directory
    runs_dir = os.path.join(output_dir, "runs")
    os.makedirs(runs_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    html_file = os.path.join(runs_dir, f"search_results_{timestamp}.html")
    json_file = os.path.join(runs_dir, f"run_results_{timestamp}.json")
    
    print(f"🔍 Searching Instacart for: '{keyword}'")
    print(f"   Store: {store}")
    print(f"   Profile: {profile_dir}")
    
    try:
        with sync_playwright() as p:
            # Launch with persistent context (authenticated session)
            context = p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=False,
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
            )
            
            page = context.pages[0] if context.pages else context.new_page()
            
            # Navigate to search page
            # URL pattern: https://www.instacart.com/store/{store}/s?k={keyword}
            search_url = f'https://www.instacart.com/store/{store}/s?k={keyword}'
            print(f"   URL: {search_url}")
            
            # Navigate (don't wait for networkidle - Instacart has lots of dynamic content)
            page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
            
            # Wait for content to load
            time.sleep(8)
            
            # Check if we're logged in
            login_modal = page.query_selector('text=/sign up/i, text=/log in/i')
            if login_modal and login_modal.is_visible():
                print("❌ Login modal detected - authentication required")
                print("Run: ./scripts/setup_instacart_profile.sh")
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
            ad_selectors = {
                'shoppable_display': 'div.e-1qzz7bi',
                'top_banner': 'div.e-1hv1sre',
                'sponsored_label': 'div.e-cwus85',
            }
            
            for ad_type, selector in ad_selectors.items():
                elements = page.query_selector_all(selector)
                for i, elem in enumerate(elements):
                    try:
                        # Get ad ID if available
                        ad_id = elem.get_attribute('id') or f"{ad_type}_{i}"
                        
                        # Get bounding box for screenshot coordinates
                        bbox = elem.bounding_box()
                        
                        ad_info = {
                            "type": ad_type,
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
        print(f"❌ Timeout: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
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
