#!/usr/bin/env python3
"""
TikTok Shop search and capture script.

Captures:
1. Main page screenshot
2. Product listings with metadata
3. Featured brand carousels

Includes automatic CAPTCHA solving.
"""

import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# Import CAPTCHA solver
sys.path.insert(0, str(Path(__file__).parent))
from tools.tiktok_captcha_solver import solve_captcha, download_image, find_slot_position


def now_iso_z() -> str:
    """Return current timestamp in ISO 8601 format (local time)."""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def build_run_id() -> str:
    """Return 14-digit run ID: YYYYMMDDHHMMSS."""
    return datetime.now().strftime("%Y%m%d%H%M%S")


async def check_and_solve_captcha(page, max_attempts: int = 3, manual_timeout: int = 120) -> bool:
    """
    Check if CAPTCHA is present and attempt to solve it.
    If auto-solve fails, waits for manual intervention.
    Returns True if no CAPTCHA or successfully solved.
    """
    # First check if there's any verification/CAPTCHA screen
    await asyncio.sleep(2)  # Give page time to show CAPTCHA
    
    for attempt in range(max_attempts):
        try:
            # Check for various CAPTCHA/verification indicators
            captcha = page.locator('#captcha_container')
            verify_dialog = page.locator('[class*="captcha"], [class*="verify"], [class*="Verify"]')
            
            captcha_visible = await captcha.is_visible()
            verify_visible = await verify_dialog.first.is_visible() if await verify_dialog.count() > 0 else False
            
            if not captcha_visible and not verify_visible:
                # Check if we're on the actual shop page
                url = page.url
                if 'tiktok.com/shop' in url or 'tiktok.com' in url:
                    return True  # No CAPTCHA, we're good
            
            print(f"[CAPTCHA] Verification screen detected! Attempt {attempt + 1}/{max_attempts}")
            
            # Try auto-solve first
            try:
                success = await solve_captcha(page, timeout=10.0)
                if success:
                    print("[CAPTCHA] ✓ Auto-solved!")
                    await asyncio.sleep(2.0)
                    return True
            except Exception as e:
                print(f"[CAPTCHA] Auto-solve failed: {e}")
            
            # Auto-solve failed - wait for manual intervention
            print(f"\n{'='*50}")
            print("[CAPTCHA] *** MANUAL INTERVENTION REQUIRED ***")
            print(f"[CAPTCHA] Please solve the CAPTCHA in the browser window.")
            print(f"[CAPTCHA] Waiting up to {manual_timeout} seconds...")
            print(f"{'='*50}\n")
            
            # Poll until CAPTCHA disappears or timeout
            for _ in range(manual_timeout):
                await asyncio.sleep(1)
                try:
                    captcha_still_visible = await captcha.is_visible()
                    if not captcha_still_visible:
                        print("[CAPTCHA] ✓ Manually solved!")
                        await asyncio.sleep(2.0)
                        return True
                except:
                    # Page may have navigated
                    return True
                    
        except Exception as e:
            print(f"[CAPTCHA] Error: {e}")
    
    print("[CAPTCHA] ✗ Could not solve after max attempts and manual wait")
    return False


async def extract_products(page) -> list:
    """Extract product listings from the current page."""
    products = []
    
    # TikTok Shop product card selectors (based on actual HTML structure)
    # Products are in cards with rounded corners, contain price and image
    product_selectors = [
        # Main product card container with price info
        'a.group.no-underline[href*="/product/"]',
        # Fallback: cards in the savings/deals sections
        '.rounded-xl.overflow-hidden a[href*="/product/"]',
        # Generic product links
        'a[href*="/product/"]',
    ]
    
    for selector in product_selectors:
        try:
            elements = await page.locator(selector).all()
            if elements:
                print(f"[PRODUCTS] Found {len(elements)} products with selector: {selector}")
                
                for i, elem in enumerate(elements):
                    try:
                        product = await extract_product_data(elem, i)
                        if product:
                            products.append(product)
                    except Exception as e:
                        print(f"[PRODUCTS] Error extracting product {i}: {e}")
                
                break  # Found products, stop trying other selectors
        except Exception:
            continue
    
    return products


async def extract_product_data(elem, index: int) -> dict:
    """Extract data from a single product element."""
    product = {
        "index": index,
        "type": "Products",
    }
    
    # Try to get product name
    name_selectors = ['h3', 'h4', '[class*="title"]', '[class*="name"]', 'a[title]']
    for sel in name_selectors:
        try:
            name_elem = elem.locator(sel).first
            if await name_elem.count() > 0:
                product["name"] = (await name_elem.inner_text()).strip()
                break
        except:
            pass
    
    # Try to get price
    price_selectors = ['[class*="price"]', '[class*="Price"]', 'span[class*="$"]']
    for sel in price_selectors:
        try:
            price_elem = elem.locator(sel).first
            if await price_elem.count() > 0:
                product["price"] = (await price_elem.inner_text()).strip()
                break
        except:
            pass
    
    # Try to get brand
    brand_selectors = ['[class*="brand"]', '[class*="Brand"]', '[class*="shop"]']
    for sel in brand_selectors:
        try:
            brand_elem = elem.locator(sel).first
            if await brand_elem.count() > 0:
                product["brand"] = (await brand_elem.inner_text()).strip()
                break
        except:
            pass
    
    # Try to get rating
    rating_selectors = ['[class*="rating"]', '[class*="Rating"]', '[class*="star"]']
    for sel in rating_selectors:
        try:
            rating_elem = elem.locator(sel).first
            if await rating_elem.count() > 0:
                product["rating"] = (await rating_elem.inner_text()).strip()
                break
        except:
            pass
    
    # Try to get image URL
    try:
        img = elem.locator('img').first
        if await img.count() > 0:
            product["image_url"] = await img.get_attribute('src')
    except:
        pass
    
    # Try to get product link
    try:
        link = elem.locator('a').first
        if await link.count() > 0:
            product["url"] = await link.get_attribute('href')
    except:
        pass
    
    # Get bounding box for screenshot
    try:
        bbox = await elem.bounding_box()
        if bbox:
            product["bbox"] = {
                "x": bbox['x'],
                "y": bbox['y'],
                "width": bbox['width'],
                "height": bbox['height']
            }
    except:
        pass
    
    return product


async def extract_featured_brands(page) -> list:
    """Extract featured brand carousels."""
    brands = []
    
    # Look for carousel/featured sections
    carousel_selectors = [
        '[class*="carousel"]',
        '[class*="Carousel"]',
        '[class*="featured"]',
        '[class*="Featured"]',
        '[class*="brand-list"]',
        '[data-e2e*="brand"]',
    ]
    
    for selector in carousel_selectors:
        try:
            elements = await page.locator(selector).all()
            for i, elem in enumerate(elements):
                try:
                    # Get section title if available
                    title = ""
                    title_elem = elem.locator('h2, h3, [class*="title"]').first
                    if await title_elem.count() > 0:
                        title = (await title_elem.inner_text()).strip()
                    
                    # Get brand items within carousel
                    brand_items = await elem.locator('a, [class*="item"]').all()
                    
                    if brand_items:
                        brand_data = {
                            "type": "Featured_Brands",
                            "section_title": title or f"Featured Section {i+1}",
                            "index": i,
                            "brands": []
                        }
                        
                        for item in brand_items[:10]:  # Limit to 10 brands per carousel
                            try:
                                brand_name = (await item.inner_text()).strip()
                                brand_url = await item.get_attribute('href')
                                if brand_name:
                                    brand_data["brands"].append({
                                        "name": brand_name,
                                        "url": brand_url
                                    })
                            except:
                                pass
                        
                        if brand_data["brands"]:
                            brands.append(brand_data)
                            
                except Exception as e:
                    print(f"[BRANDS] Error extracting carousel {i}: {e}")
                    
        except Exception:
            continue
    
    return brands


async def capture_main_screenshot(page, output_dir: str, timestamp: str) -> str:
    """Capture full page screenshot of main shop page."""
    main_dir = os.path.join(output_dir, "Main")
    os.makedirs(main_dir, exist_ok=True)
    
    screenshot_path = os.path.join(main_dir, f"tiktokshop_main_{timestamp}.png")
    
    await page.screenshot(path=screenshot_path, full_page=True)
    print(f"[SCREENSHOT] Main page saved: {screenshot_path}")
    
    return f"Main/tiktokshop_main_{timestamp}.png"


async def capture_product_screenshots(page, products: list, output_dir: str, timestamp: str) -> list:
    """Capture individual product screenshots."""
    products_dir = os.path.join(output_dir, "Products")
    os.makedirs(products_dir, exist_ok=True)
    
    updated_products = []
    
    for product in products:
        if "bbox" in product:
            try:
                # Generate filename
                brand = product.get("brand", "unknown").replace(" ", "_")[:20]
                name = product.get("name", "product").replace(" ", "_")[:30]
                name = re.sub(r'[^\w\-]', '', name)
                
                filename = f"{brand}_{name}_{timestamp}_{product['index']}.png"
                filepath = os.path.join(products_dir, filename)
                
                # Capture element screenshot
                bbox = product["bbox"]
                await page.screenshot(
                    path=filepath,
                    clip={
                        "x": bbox["x"],
                        "y": bbox["y"],
                        "width": bbox["width"],
                        "height": bbox["height"]
                    }
                )
                
                product["image_path"] = f"Products/{filename}"
                print(f"[SCREENSHOT] Product {product['index']}: {filename}")
                
            except Exception as e:
                print(f"[SCREENSHOT] Failed for product {product['index']}: {e}")
        
        updated_products.append(product)
    
    return updated_products


async def search_and_capture_async(keyword: str, output_dir: str, **kwargs) -> bool:
    """
    Main async function to search TikTok Shop and capture results.
    """
    profile_dir = os.environ.get('TIKTOKSHOP_PROFILE_DIR')
    if not profile_dir or not os.path.isdir(profile_dir):
        print(f"❌ TIKTOKSHOP_PROFILE_DIR not set or invalid: {profile_dir}")
        print("Run: ./scripts/setup_tiktokshop_profile.sh")
        return False
    
    # Create output directories
    runs_dir = os.path.join(output_dir, "runs")
    os.makedirs(runs_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = build_run_id()
    
    print(f"🔍 TikTok Shop Capture")
    print(f"   Keyword: '{keyword}'")
    print(f"   Profile: {profile_dir}")
    print(f"   Output: {output_dir}")
    
    try:
        async with async_playwright() as p:
            # Launch with persistent context using stealth settings
            # Use real Chrome to avoid Google OAuth detection
            context = await p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=False,
                channel='chrome',  # Use real Chrome instead of Chromium
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
                args=[
                    '--disable-blink-features=AutomationControlled',  # Hide automation
                    '--disable-dev-shm-usage',
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--no-sandbox',  # Required for Playwright, suppresses warning
                ],
                ignore_default_args=['--enable-automation'],  # Remove automation flag
            )
            
            page = context.pages[0] if context.pages else await context.new_page()
            
            # Override navigator.webdriver to hide automation
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            
            # Navigate to TikTok Shop
            if keyword.lower() in ['main', 'home', '']:
                # Just capture main page
                shop_url = 'https://www.tiktok.com/shop'
            else:
                # Search for keyword (updated URL structure: /shop/s instead of /shop/search)
                shop_url = f'https://www.tiktok.com/shop/s?q={quote_plus(keyword)}'
            
            print(f"   URL: {shop_url}")
            
            await page.goto(shop_url, wait_until='domcontentloaded', timeout=30000)
            
            # Check for and solve CAPTCHA
            if not await check_and_solve_captcha(page):
                print("❌ Could not bypass CAPTCHA")
                await context.close()
                return False
            
            # Wait for any redirects to complete
            await asyncio.sleep(3)
            
            # Login state check — Check URL for login redirect AND login button
            current_url = page.url
            is_login_redirect = '/login' in current_url or 'waf_force_login' in current_url
            
            if is_login_redirect:
                print(f"   ⚠️ Redirected to login page: {current_url}")
                print("   ⚠️ Not logged in — TikTok requires authentication")
                print("\n" + "="*60)
                print("   🔐 PLEASE LOG IN TO TIKTOK SHOP")
                print("   1. Complete the login process in the browser window")
                print("   2. Wait for the search results page to load")
                print("   3. CLOSE THE BROWSER WINDOW when ready")
                print("   (The scraper will wait indefinitely)")
                print("="*60 + "\n")
                
                try:
                    await page.bring_to_front()
                except Exception:
                    pass
                
                # Wait indefinitely for user to close the window
                try:
                    while True:
                        await asyncio.sleep(1)
                        # Check if page is still alive
                        try:
                            _ = page.url
                        except Exception:
                            # Page/context closed by user
                            print("   ✅ Browser closed by user - assuming login complete")
                            break
                except Exception:
                    pass
                
                # User closed browser - relaunch and navigate to search
                print(f"   ↻ Relaunching browser and navigating to search...")
                await context.close()
                
                # Relaunch with same profile
                context = await browser.new_context(
                    user_data_dir=profile_dir,
                    viewport={'width': 1912, 'height': 1417},
                    locale='en-US',
                )
                page = await context.new_page()
                await page.goto(shop_url, wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(3)
            else:
                # Check for "Log in" button in header as secondary check
                try:
                    login_button = page.locator('button:has-text("Log in"), a:has-text("Log in")').first
                    is_login_visible = await login_button.is_visible(timeout=2000)
                    
                    if is_login_visible:
                        print("   ⚠️ Not logged in — 'Log in' button visible")
                        try:
                            from utils.profile_health import prompt_relogin_async
                            _relogged = await prompt_relogin_async(page, "tiktokshop", keyword, timeout_sec=600)
                            if not _relogged:
                                from utils.profile_health import record_login_outcome
                                record_login_outcome("tiktokshop", keyword, logged_in=False)
                                print("   ❌ Login required but user declined. Exiting.")
                                await context.close()
                                return False
                        except Exception as e:
                            print(f"   ⚠️ Re-login prompt failed: {e}")
                            await context.close()
                            return False
                    else:
                        print("   ✅ Logged-in session detected")
                except Exception as e:
                    print(f"   ⚠️ Could not verify login status: {e}")
                    print("   ⚠️ Proceeding anyway - results may be limited if not logged in")

            # Wait for content to load
            await asyncio.sleep(2)
            
            # Scroll to load more content
            print("[SCROLL] Loading more content...")
            for _ in range(3):
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await asyncio.sleep(1)
            
            # Scroll back to top
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(0.5)
            
            # Capture main screenshot
            main_image_path = await capture_main_screenshot(page, output_dir, timestamp)
            
            # Extract products
            print("[EXTRACT] Finding products...")
            products = await extract_products(page)
            print(f"[EXTRACT] Found {len(products)} products")
            
            # Capture product screenshots
            if products:
                products = await capture_product_screenshots(page, products, output_dir, timestamp)
            
            # Extract featured brands
            print("[EXTRACT] Finding featured brands...")
            featured_brands = await extract_featured_brands(page)
            print(f"[EXTRACT] Found {len(featured_brands)} brand sections")
            
            # Build result JSON
            result = {
                "retailer": "tiktokshop",
                "keyword": keyword,
                "timestamp": now_iso_z(),
                "run_id": run_id,
                "url": page.url,
                "main_screenshot": main_image_path,
                "ads": products + featured_brands,  # Combine for canonical schema
                "products": products,
                "featured_brands": featured_brands,
            }
            
            # Save JSON
            json_file = os.path.join(runs_dir, f"run_results_{timestamp}.json")
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2)
            print(f"💾 JSON saved: {json_file}")
            
            # Save HTML
            html_content = await page.content()
            html_file = os.path.join(runs_dir, f"search_results_{timestamp}.html")
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"💾 HTML saved: {html_file}")
            
            await context.close()
            
            print(f"\n✅ Capture complete!")
            print(f"   Products: {len(products)}")
            print(f"   Brand sections: {len(featured_brands)}")
            
            return True
            
    except PlaywrightTimeout as e:
        print(f"❌ Timeout: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def search_and_capture(keyword: str, output_dir: str, **kwargs) -> bool:
    """Synchronous wrapper for async search_and_capture."""
    return asyncio.run(search_and_capture_async(keyword, output_dir, **kwargs))


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Search TikTok Shop and capture results')
    parser.add_argument('keyword', nargs='?', default='main', 
                       help='Search keyword (use "main" for homepage)')
    parser.add_argument('--output-dir', required=True, help='Output directory')
    
    args = parser.parse_args()
    
    success = search_and_capture(args.keyword, args.output_dir)
    sys.exit(0 if success else 1)
