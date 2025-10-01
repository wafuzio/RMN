#!/usr/bin/env python3
"""
Save TOA Images from JSON

This script extracts image URLs from TOA JSON files, opens them in a browser,
and right-clicks to save the images.
"""

import os
import sys
import json
import argparse
import time
from datetime import datetime
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext

def extract_image_urls_from_json(json_file):
    """
    Extract image URLs from a TOA JSON file
    """
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        image_urls = []
        
        # Extract image URLs from the JSON structure
        if "results" in data:
            for result in data["results"]:
                if "ads" in result:
                    for ad in result["ads"]:
                        if "image_url" in ad:
                            image_url = ad["image_url"]
                            # Add domain if it's a relative URL
                            if image_url.startswith('/'):
                                image_url = f"https://www.kroger.com{image_url}"
                            
                            image_urls.append({
                                "url": image_url,
                                "keyword": result.get("keyword", "unknown"),
                                "alt_text": ad.get("message", "")
                            })
        
        return image_urls
    
    except Exception as e:
        print(f"❌ Error extracting image URLs from JSON: {e}")
        return []

def setup_download_listener(page: Page, download_dir: str):
    """
    Set up a download listener for the page
    """
    # Create download directory if it doesn't exist
    os.makedirs(download_dir, exist_ok=True)
    
    # Configure browser to download to the specified directory
    page.context.set_default_timeout(30000)  # Increase timeout for downloads
    
    # Set up download handler
    page.on("download", lambda download: handle_download(download, download_dir))

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

def right_click_save_image(page: Page):
    """
    Right-click on an image and select "Save image as"
    """
    # Wait for the image to be visible
    page.wait_for_selector("img", state="visible", timeout=10000)
    
    # Get image details for logging
    img_src = page.get_attribute("img", "src")
    img_alt = page.get_attribute("img", "alt") or "No alt text"
    
    print(f"🖱️ Right-clicking on image: {img_alt}")
    print(f"🔗 Image source: {img_src}")
    
    # Right-click on the image
    page.click("img", button="right")
    
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

def open_and_save_images(image_urls, output_dir, client=None, headless=False):
    """
    Open image URLs in browser and right-click to save them
    """
    if not image_urls:
        print("❌ No image URLs found")
        return
    
    # Set up output directory
    if client:
        toa_dir = os.path.join(output_dir, client, "TOA")
    else:
        toa_dir = os.path.join(output_dir, "TOA")
    
    os.makedirs(toa_dir, exist_ok=True)
    
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
        setup_download_listener(page, toa_dir)
        
        try:
            for i, image_info in enumerate(image_urls):
                image_url = image_info["url"]
                keyword = image_info["keyword"]
                alt_text = image_info["alt_text"]
                
                print(f"\n📷 Processing image {i+1}/{len(image_urls)}")
                print(f"🔗 URL: {image_url}")
                print(f"🔑 Keyword: {keyword}")
                print(f"📝 Alt text: {alt_text}")
                
                # Navigate to the image URL
                print(f"🌐 Opening image URL")
                page.goto(image_url)
                
                # Wait for the image to load
                page.wait_for_load_state("networkidle")
                
                # Right-click and save the image
                success = right_click_save_image(page)
                
                if success:
                    print("✅ Successfully triggered save dialog")
                else:
                    print("❌ Failed to save image")
                
                # Wait a moment before processing the next image
                time.sleep(2)
            
        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            # Close browser
            browser.close()

def main():
    parser = argparse.ArgumentParser(description="Save TOA images from JSON file")
    parser.add_argument("--json", "-j", required=True, help="Path to TOA JSON file")
    parser.add_argument("--client", "-c", help="Client name for organizing output")
    parser.add_argument("--output", "-o", default="output", help="Output directory (default: output)")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode (no browser UI)")
    args = parser.parse_args()
    
    # Extract image URLs from JSON
    image_urls = extract_image_urls_from_json(args.json)
    
    if not image_urls:
        print("❌ No image URLs found in the JSON file")
        return 1
    
    print(f"✅ Found {len(image_urls)} image URLs in the JSON file")
    
    # Open and save images
    open_and_save_images(
        image_urls=image_urls,
        output_dir=args.output,
        client=args.client,
        headless=args.headless
    )
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
