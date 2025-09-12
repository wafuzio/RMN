#!/usr/bin/env python3
"""
Save TOA Images with Browser Right-Click

This script automates the process of right-clicking and saving TOA banner images
directly from the browser during Kroger.com searches.
"""

import os
import sys
import argparse
import time
from datetime import datetime
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext

def setup_download_listener(page: Page, download_dir: str, client: str = None):
    """
    Set up a download listener for the page
    """
    # Create client-specific TOA directory
    if client:
        toa_dir = os.path.join(download_dir, client, "TOA")
    else:
        toa_dir = os.path.join(download_dir, "TOA")
    
    os.makedirs(toa_dir, exist_ok=True)
    
    # Configure browser to download to the TOA directory
    page.context.set_default_timeout(30000)  # Increase timeout for downloads
    
    # Set up download handler
    page.on("download", lambda download: handle_download(download, toa_dir))
    
    return toa_dir

def handle_download(download, download_dir):
    """
    Handle downloaded files
    """
    # Get suggested filename
    suggested_filename = download.suggested_filename
    
    # Generate a timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    
    # Create a new filename with toa_ prefix and timestamp
    if not suggested_filename.startswith("toa_"):
        new_filename = f"toa_{timestamp}_{suggested_filename}"
    else:
        new_filename = suggested_filename
    
    # Save the file
    download_path = os.path.join(download_dir, new_filename)
    download.save_as(download_path)
    
    print(f"✅ Image saved to: {download_path}")

def right_click_save_image(page: Page, selector: str):
    """
    Right-click on an image and select "Save image as"
    """
    # Wait for the image to be visible
    page.wait_for_selector(selector, state="visible", timeout=10000)
    
    # Get image details for logging
    img_src = page.get_attribute(selector, "src")
    img_alt = page.get_attribute(selector, "alt") or "No alt text"
    
    print(f"🖱️ Right-clicking on image: {img_alt}")
    print(f"🔗 Image source: {img_src}")
    
    # Right-click on the image
    page.click(selector, button="right")
    
    # Wait for context menu to appear
    time.sleep(1)
    
    # This part is OS-dependent
    # For macOS:
    try:
        # Try to find "Save Image As" in the context menu
        save_image_option = page.get_by_text("Save Image As", exact=False)
        if save_image_option:
            save_image_option.click()
        else:
            # Try keyboard shortcut (varies by OS and browser)
            # macOS Chrome: Command+S
            page.keyboard.press("Meta+s")
    except Exception as e:
        print(f"⚠️ Could not find 'Save Image As' option: {e}")
        print("⚠️ Trying keyboard shortcut...")
        # Try different keyboard shortcuts
        try:
            # macOS Chrome/Firefox
            page.keyboard.press("Meta+s")
        except:
            try:
                # Windows/Linux
                page.keyboard.press("Control+s")
            except Exception as e2:
                print(f"❌ Failed to trigger save dialog: {e2}")
                return False
    
    # Wait for the save dialog and download to complete
    time.sleep(3)
    
    return True

def search_and_save_toa_images(search_term, output_dir, client=None, headless=False):
    """
    Search Kroger for a term and save TOA banner images using right-click
    """
    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=headless)
        
        # Create a browser context with download permissions
        context = browser.new_context(
            accept_downloads=True,
            viewport={"width": 1280, "height": 720}
        )
        
        # Create a new page
        page = context.new_page()
        
        # Set up download listener
        toa_dir = setup_download_listener(page, output_dir, client)
        
        try:
            # Navigate to Kroger
            print(f"🌐 Navigating to Kroger.com")
            page.goto("https://www.kroger.com")
            
            # Accept cookies if prompted
            try:
                page.click("button:has-text('Accept')", timeout=5000)
            except:
                pass  # No cookie prompt
            
            # Search for the term
            print(f"🔍 Searching for: {search_term}")
            page.fill("input[type='search']", search_term)
            page.press("input[type='search']", "Enter")
            
            # Wait for search results
            page.wait_for_load_state("networkidle")
            
            # Look for TOA banner images
            toa_selectors = [
                "div[data-testid='StandardTOA'] img.espot-image",
                "div.Standard-TOA img.espot-image",
                "img.espot-image",
                "div[class*='TOA'] img"
            ]
            
            # Try each selector
            toa_found = False
            for selector in toa_selectors:
                if page.is_visible(selector, timeout=1000):
                    print(f"🎯 Found TOA banner with selector: {selector}")
                    
                    # Right-click and save the image
                    success = right_click_save_image(page, selector)
                    
                    if success:
                        print("✅ Successfully triggered save dialog")
                        toa_found = True
                        break
            
            if not toa_found:
                print("❌ No TOA banner found on the page")
            
            # Wait a moment to ensure download completes
            time.sleep(5)
            
            # Take a screenshot for reference
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            if client:
                main_dir = os.path.join(output_dir, client, "main")
                os.makedirs(main_dir, exist_ok=True)
                screenshot_path = os.path.join(main_dir, f"search_results_{search_term.replace(' ', '_')}_{timestamp}.png")
            else:
                screenshot_path = os.path.join(output_dir, f"search_results_{search_term.replace(' ', '_')}_{timestamp}.png")
            
            page.screenshot(path=screenshot_path, full_page=True)
            print(f"📷 Full page screenshot saved to: {screenshot_path}")
            
            # Save HTML for reference
            if client:
                html_path = os.path.join(output_dir, client, f"search_results_{search_term.replace(' ', '_')}_{timestamp}.html")
            else:
                html_path = os.path.join(output_dir, f"search_results_{search_term.replace(' ', '_')}_{timestamp}.html")
            
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(page.content())
            print(f"💾 HTML saved to: {html_path}")
            
        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            # Close browser
            browser.close()

def main():
    parser = argparse.ArgumentParser(description="Save TOA banner images using browser right-click")
    parser.add_argument("--search", "-s", required=True, help="Search term")
    parser.add_argument("--client", "-c", help="Client name for organizing output")
    parser.add_argument("--output", "-o", default="output", help="Output directory (default: output)")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode (no browser UI)")
    args = parser.parse_args()
    
    search_and_save_toa_images(
        search_term=args.search,
        output_dir=args.output,
        client=args.client,
        headless=args.headless
    )

if __name__ == "__main__":
    main()
