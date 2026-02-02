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

from filename_utils import generate_ad_filename


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
        return {"shoppable_display": 0, "shoppable_video": 0, "display_ad": 0, "shoppable_recipe": 0}
    
    # Create output directories - Instacart-specific folders
    shoppable_display_dir = os.path.join(output_dir, "Shoppable_Display_Ads")
    shoppable_video_dir = os.path.join(output_dir, "Shoppable_Video_Ads")
    display_ad_dir = os.path.join(output_dir, "Display_Ads")
    shoppable_recipe_dir = os.path.join(output_dir, "Shoppable_Recipe_Ads")
    main_dir = os.path.join(output_dir, "Main")  # For full-page screenshot
    
    for d in [shoppable_display_dir, shoppable_video_dir, display_ad_dir, shoppable_recipe_dir, main_dir]:
        os.makedirs(d, exist_ok=True)
    
    counts = {"shoppable_display": 0, "shoppable_video": 0, "display_ad": 0, "shoppable_recipe": 0}
    
    # Extract keyword and timestamp from JSON for file naming
    keyword = ad_data.get('keyword', 'unknown').replace(' ', '_')
    timestamp_str = ad_data.get('timestamp', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    # Extract client name from output_dir (e.g., output/instacart/bomb_pop -> bomb_pop)
    client_name = os.path.basename(output_dir)
    
    # Clean up stale lock file if it exists
    if profile_dir and os.path.isdir(profile_dir):
        lock_file = os.path.join(profile_dir, 'SingletonLock')
        # Use lexists() instead of exists() to catch broken symlinks
        if os.path.lexists(lock_file):
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
            
            # Take full-page screenshot with standardized naming
            fullpage_filename = generate_ad_filename(
                retailer='instacart',
                ad_type='main',
                client=client_name,
                search_term=keyword,
                timestamp=timestamp_str,
                index=1,
                extension='png',
                advertiser=None  # No advertiser for full page
            )
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
        
        # Screenshot shoppable ads with standardized naming
        for i, ad in enumerate(shoppable_ads):
            try:
                # Scroll element into view to ensure it's fully visible
                ad.scroll_into_view_if_needed()
                page.wait_for_timeout(500)  # Let it settle
                
                # Determine if this is a video ad or display ad
                is_video = ad.query_selector('video') is not None
                ad_type = 'shoppable_video_ad' if is_video else 'shoppable_display_ad'
                output_folder = shoppable_video_dir if is_video else shoppable_display_dir
                
                # Try to extract advertiser/brand from the ad
                advertiser = None
                try:
                    import re
                    
                    # Strategy 1: Extract from product carousel items (most reliable)
                    products = ad.query_selector_all('[data-testid^="item_list_item"]')
                    if products and len(products) > 0:
                        # Get first product's text
                        first_product = products[0]
                        product_text = first_product.inner_text()
                        lines = [line.strip() for line in product_text.split('\n') if line.strip()]
                        
                        # Find the product name line - it should be longer and contain actual product info
                        # Skip promotional text, prices, ratings, and generic UI elements
                        for line in lines:
                            if (len(line) > 15 and  # Product names are usually longer
                                not line.startswith('$') and 
                                not line.startswith('★') and
                                not line.startswith('(') and
                                not 'Current price' in line and
                                not 'Spend' in line and
                                not line.endswith('oz') and
                                not line == 'Add' and
                                not 'save' in line.lower() and
                                not 'See eligible' in line):
                                
                                # This should be a product name like "Tropicana Pure Premium Orange Juice"
                                # Extract brand (first 1-2 capitalized words before descriptive words)
                                words = line.split()
                                if words and len(words) >= 2:
                                    # Take first 1-2 capitalized words as brand
                                    # Stop at common descriptive words
                                    descriptive_words = {'Fresh', 'Cut', 'Pure', 'Premium', 'Original', 'Classic', 
                                                        'Natural', 'Organic', 'Whole', 'Sliced', 'Diced', 'Chopped'}
                                    brand_words = []
                                    for word in words[:3]:
                                        if word and word[0].isupper() and word not in descriptive_words:
                                            brand_words.append(word)
                                            # Stop after 2 words or if we hit a descriptive word
                                            if len(brand_words) == 2:
                                                break
                                        elif word in descriptive_words:
                                            break
                                    
                                    if brand_words:
                                        advertiser = ' '.join(brand_words)
                                        break
                    
                    # Strategy 2: Look for brand link
                    if not advertiser:
                        brand_link = ad.query_selector('a[href*="/brands/"]')
                        if brand_link:
                            href = brand_link.get_attribute('href') or ''
                            # Extract brand from URL: /store/publix/brands/del-monte
                            brand_match = re.search(r'/brands/([^/?]+)', href)
                            if brand_match:
                                brand_slug = brand_match.group(1)
                                # Convert slug to proper name: del-monte -> Del Monte
                                advertiser = brand_slug.replace('-', ' ').title()
                    
                    # Strategy 3: Look for heading with brand name
                    if not advertiser:
                        heading = ad.query_selector('h2, h3, [class*="heading"]')
                        if heading:
                            heading_text = heading.inner_text()
                            # Common patterns: "Stock Up On [Brand]", "Shop [Brand]"
                            brand_match = re.search(r'(?:Stock Up On|Shop|Discover|Try|from)\s+([A-Z][a-zA-Z\s&\'\.]+?)(?:\s*$|\s+Products|\s+Items)', heading_text, re.IGNORECASE)
                            if brand_match:
                                advertiser = brand_match.group(1).strip()
                except:
                    pass
                
                # Fallback to "unknown" if extraction failed
                if not advertiser:
                    advertiser = "unknown"
                
                # Generate standardized filename
                filename = generate_ad_filename(
                    retailer='instacart',
                    ad_type=ad_type,
                    client=client_name,
                    search_term=keyword,
                    timestamp=timestamp_str,
                    index=i+1,
                    extension='png',
                    advertiser=advertiser
                )
                filepath = os.path.join(output_folder, filename)
                ad.screenshot(path=filepath)
                
                # Update counts
                if is_video:
                    counts["shoppable_video"] += 1
                    print(f"  ✅ Shoppable Video {i+1}: {filename}")
                else:
                    counts["shoppable_display"] += 1
                    print(f"  ✅ Shoppable Display {i+1}: {filename}")
            except Exception as e:
                print(f"  ❌ Error screenshotting shoppable ad {i+1}: {e}")
        
        # Screenshot display ads with standardized naming
        for i, ad in enumerate(display_ads):
            try:
                # Scroll element into view to ensure it's fully visible
                ad.scroll_into_view_if_needed()
                page.wait_for_timeout(500)  # Let it settle
                
                # Try to extract advertiser/brand from the ad
                advertiser = None
                try:
                    import re
                    
                    # Strategy 0: Extract from advertiser logo alt text (MOST RELIABLE for Display Ads)
                    # Display ads have a logo with alt text like <img alt="Stonyfield Organic">
                    logo_img = ad.query_selector('img[alt]:not([alt=""])')
                    if logo_img:
                        alt_text = logo_img.get_attribute('alt')
                        if alt_text and alt_text.strip() and len(alt_text) > 2:
                            # Check if it's purely generic (single word like "logo", "image")
                            generic_alts = ['logo', 'image', 'ad', 'banner', 'sponsored', 'advertisement']
                            
                            # If alt text is a single generic word, skip it
                            if alt_text.lower() in generic_alts:
                                pass  # Skip purely generic alt text
                            # If alt text contains descriptive words (e.g., "New York Bakery Logo"), extract the brand
                            elif any(generic in alt_text.lower() for generic in ['logo', 'brand', 'image']):
                                # Remove generic descriptive words and extract brand
                                cleaned = alt_text
                                for word in ['Logo', 'logo', 'Brand', 'brand', 'Image', 'image']:
                                    cleaned = cleaned.replace(word, '').strip()
                                
                                if cleaned and len(cleaned) > 2:
                                    alt_text = cleaned  # Use cleaned version
                                    # Continue with normal extraction logic below
                            
                            # Now process the (possibly cleaned) alt text
                            if alt_text and alt_text.lower() not in generic_alts:
                                # If alt text is short and clean, use it directly
                                if len(alt_text) < 30 and '&' not in alt_text:
                                    advertiser = alt_text.strip()
                                else:
                                    # For longer descriptive alt text, try multiple strategies:
                                    # 1. Look for brand after " - " separator (e.g., "Frighteningly Delicious Treats - Sour Patch Kids")
                                    # 2. Look for brand at the beginning (e.g., "Sour Patch Kids & Swedish Fish candies")
                                    
                                    brand_candidate = None
                                    
                                    # Strategy: Check for " - " separator (brand often comes after)
                                    if ' - ' in alt_text:
                                        parts = alt_text.split(' - ')
                                        # Brand is usually after the dash
                                        if len(parts) > 1:
                                            brand_part = parts[-1].strip()  # Take last part after dash
                                            # Extract first 1-3 capitalized words from this part
                                            words = brand_part.split()
                                            brand_words = []
                                            for word in words[:3]:
                                                if word and word[0].isupper():
                                                    brand_words.append(word)
                                                else:
                                                    break
                                            if brand_words:
                                                brand_candidate = ' '.join(brand_words)
                                    
                                    # Fallback: Extract from beginning (before '&' or descriptive words)
                                    if not brand_candidate:
                                        words = alt_text.split()
                                        descriptive_words = {'in', 'on', 'with', 'and', 'or', 'the', 'a', 'an', 'for', 'at', 
                                                           'candies', 'candy', 'products', 'product', 'items', 'item',
                                                           'costumes', 'costume', 'packages', 'package', 'bottles', 'bottle',
                                                           'treats', 'treat', 'delicious', 'frighteningly'}
                                        brand_words = []
                                        for word in words[:5]:  # Look at first 5 words
                                            # Stop at '&' or descriptive words
                                            if word in ['&', 'and', '-'] or word.lower() in descriptive_words:
                                                break
                                            # Collect capitalized words
                                            if word and word[0].isupper():
                                                brand_words.append(word)
                                                if len(brand_words) >= 3:  # Max 3 words for brand
                                                    break
                                        
                                        if brand_words:
                                            brand_candidate = ' '.join(brand_words)
                                    
                                    if brand_candidate:
                                        advertiser = brand_candidate
                    
                    # Strategy 1: Extract from product carousel items (for shoppable ads)
                    if not advertiser:
                        products = ad.query_selector_all('[data-testid^="item_list_item"]')
                        if products and len(products) > 0:
                            first_product = products[0]
                            product_text = first_product.inner_text()
                            lines = [line.strip() for line in product_text.split('\n') if line.strip()]
                            
                            for line in lines:
                                if (len(line) > 15 and 
                                    not line.startswith('$') and 
                                    not line.startswith('★') and
                                    not line.startswith('(') and
                                    not 'Current price' in line and
                                    not 'Spend' in line and
                                    not line.endswith('oz') and
                                    not line == 'Add' and
                                    not 'save' in line.lower() and
                                    not 'See eligible' in line):
                                    
                                    words = line.split()
                                    if words and len(words) >= 2:
                                        descriptive_words = {'Fresh', 'Cut', 'Pure', 'Premium', 'Original', 'Classic', 
                                                            'Natural', 'Organic', 'Whole', 'Sliced', 'Diced', 'Chopped'}
                                        brand_words = []
                                        for word in words[:3]:
                                            if word and word[0].isupper() and word not in descriptive_words:
                                                brand_words.append(word)
                                                if len(brand_words) == 2:
                                                    break
                                            elif word in descriptive_words:
                                                break
                                        
                                        if brand_words:
                                            advertiser = ' '.join(brand_words)
                                            break
                    
                    # Strategy 2: Look for brand link
                    if not advertiser:
                        brand_link = ad.query_selector('a[href*="/brands/"]')
                        if brand_link:
                            href = brand_link.get_attribute('href') or ''
                            brand_match = re.search(r'/brands/([^/?]+)', href)
                            if brand_match:
                                brand_slug = brand_match.group(1)
                                advertiser = brand_slug.replace('-', ' ').title()
                    
                    # Strategy 3: Look for heading with brand name
                    if not advertiser:
                        heading = ad.query_selector('h2, h3, [class*="heading"]')
                        if heading:
                            heading_text = heading.inner_text()
                            brand_match = re.search(r'(?:Stock Up On|Shop|Discover|Try|from)\s+([A-Z][a-zA-Z\s&\'\.]+?)(?:\s*$|\s+Products|\s+Items)', heading_text, re.IGNORECASE)
                            if brand_match:
                                advertiser = brand_match.group(1).strip()
                except:
                    pass
                
                # Fallback to "unknown" if extraction failed
                if not advertiser:
                    advertiser = "unknown"
                
                # Generate standardized filename
                filename = generate_ad_filename(
                    retailer='instacart',
                    ad_type='display_ad',
                    client=client_name,
                    search_term=keyword,
                    timestamp=timestamp_str,
                    index=i+1,
                    extension='png',
                    advertiser=advertiser
                )
                filepath = os.path.join(display_ad_dir, filename)
                ad.screenshot(path=filepath)
                counts["display_ad"] += 1
                print(f"  ✅ Display Ad {i+1}: {filename}")
            except Exception as e:
                print(f"  ❌ Error screenshotting display ad {i+1}: {e}")
        
        # Screenshot Shoppable Recipe ads
        print("\n   Querying Shoppable Recipe ads...")
        recipe_containers = page.query_selector_all('div.e-1yrpusx')
        recipe_ads = []
        
        # Filter for actual recipe ads (have "Related recipe" heading and "Sponsored" label)
        for container in recipe_containers:
            try:
                heading = container.query_selector('h2.e-5ieped')
                sponsored = container.query_selector('span.e-yrjvxu')
                if heading and sponsored:
                    heading_text = heading.inner_text()
                    sponsored_text = sponsored.inner_text()
                    if 'Related recipe' in heading_text and 'Sponsored' in sponsored_text:
                        recipe_ads.append(container)
            except:
                pass
        
        print(f"   Found {len(recipe_ads)} shoppable recipe ads")
        
        for i, ad in enumerate(recipe_ads):
            try:
                ad.scroll_into_view_if_needed()
                page.wait_for_timeout(500)
                
                # Extract advertiser/brand from recipe image alt text
                advertiser = None
                try:
                    import re
                    
                    # Strategy 1: Look for image with alt text (brand name)
                    recipe_img = ad.query_selector('img[alt]')
                    if recipe_img:
                        alt_text = recipe_img.get_attribute('alt')
                        if alt_text and alt_text.strip():
                            advertiser = alt_text.strip()
                    
                    # Strategy 2: Look for brand link
                    if not advertiser:
                        brand_link = ad.query_selector('a[href*="/brands/"]')
                        if brand_link:
                            href = brand_link.get_attribute('href') or ''
                            brand_match = re.search(r'/brands/([^/?]+)', href)
                            if brand_match:
                                brand_slug = brand_match.group(1)
                                advertiser = brand_slug.replace('-', ' ').title()
                except:
                    pass
                
                if not advertiser:
                    advertiser = "unknown"
                
                # Generate standardized filename
                filename = generate_ad_filename(
                    retailer='instacart',
                    ad_type='shoppable_recipe_ad',
                    client=client_name,
                    search_term=keyword,
                    timestamp=timestamp_str,
                    index=i+1,
                    extension='png',
                    advertiser=advertiser
                )
                filepath = os.path.join(shoppable_recipe_dir, filename)
                ad.screenshot(path=filepath)
                counts["shoppable_recipe"] += 1
                print(f"  ✅ Shoppable Recipe Ad {i+1}: {filename}")
            except Exception as e:
                print(f"  ❌ Error screenshotting shoppable recipe ad {i+1}: {e}")
        
        # Close browser
        if profile_dir:
            context.close()
        else:
            browser.close()
    
    print(f"\n📊 Screenshot Summary:")
    print(f"   Shoppable Display Ads: {counts['shoppable_display']}")
    print(f"   Shoppable Video Ads: {counts['shoppable_video']}")
    print(f"   Display Ads: {counts['display_ad']}")
    print(f"   Shoppable Recipe Ads: {counts['shoppable_recipe']}")
    
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
    total_ads = counts['shoppable_display'] + counts['shoppable_video'] + counts['display_ad'] + counts['shoppable_recipe']
    if total_ads > 0:
        sys.exit(0)
    else:
        print("\n⚠️  No ads captured")
        sys.exit(1)
