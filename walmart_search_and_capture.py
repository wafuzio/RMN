#!/usr/bin/env python3
"""
Walmart search and capture script.
Navigates to Walmart search, captures HTML and detects ad modules.
"""
import os
import sys
import time
import json
import argparse
from datetime import datetime
from urllib.parse import quote_plus
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


DEFAULT_PROFILE = os.path.expanduser("~/Library/Application Support/RMN/profiles/walmart")


def search_and_capture(keyword: str, output_dir: str, profile_dir: str = None) -> bool:
    """
    Search Walmart for keyword and capture HTML.
    
    Args:
        keyword: Search term
        output_dir: Directory to save results
        profile_dir: Optional persistent profile directory
        
    Returns:
        True if successful, False otherwise
    """
    if not profile_dir:
        profile_dir = DEFAULT_PROFILE
    
    os.makedirs(output_dir, exist_ok=True)
    runs_dir = os.path.join(output_dir, "runs")
    os.makedirs(runs_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_keyword = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in keyword)
    
    # Build search URL
    search_url = f"https://www.walmart.com/search?q={quote_plus(keyword)}"
    
    print(f"Searching Walmart for: {keyword}")
    print(f"URL: {search_url}")
    
    with sync_playwright() as p:
        # Launch with persistent context
        context = p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=False,
            viewport={'width': 1920, 'height': 1080},
            locale='en-US',
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
            ],
        )
        
        page = context.pages[0] if context.pages else context.new_page()
        
        try:
            # Navigate to search
            print(f"Navigating to: {search_url}")
            page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
            
            # Wait for results to load
            try:
                page.wait_for_selector('[data-testid="list-view"]', timeout=10000)
            except PlaywrightTimeout:
                print("⚠️ Results container not found, continuing anyway...")
            
            # Small settle time
            time.sleep(2)
            
            # Capture HTML
            html_path = os.path.join(runs_dir, f"search_results_{safe_keyword}_{timestamp}.html")
            html_content = page.content()
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"✅ HTML saved: {html_path}")
            
            # Capture metadata
            meta = {
                "keyword": keyword,
                "url": search_url,
                "timestamp": timestamp,
                "html_file": os.path.basename(html_path),
            }
            
            json_path = os.path.join(runs_dir, f"run_results_{safe_keyword}_{timestamp}.json")
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(meta, f, indent=2)
            print(f"✅ Metadata saved: {json_path}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error during search: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            context.close()


def main():
    parser = argparse.ArgumentParser(description="Walmart search and capture")
    parser.add_argument("keyword", help="Search keyword")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--profile-dir", help="Profile directory (optional)")
    
    args = parser.parse_args()
    
    success = search_and_capture(
        keyword=args.keyword,
        output_dir=args.output_dir,
        profile_dir=args.profile_dir
    )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
