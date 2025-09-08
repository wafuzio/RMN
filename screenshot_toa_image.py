#!/usr/bin/env python3
"""
Screenshot TOA Images

This script extracts image URLs from TOA JSON files, opens them in a browser,
and takes a precise screenshot of just the image without surrounding space.
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
                                "alt_text": ad.get("message", ""),
                                "id": image_url.split('/')[-1].split('.')[0] if '/' in image_url else None
                            })
        
        return image_urls
    
    except Exception as e:
        print(f"❌ Error extracting image URLs from JSON: {e}")
        return []

def screenshot_image(page: Page, output_path: str):
    """
    Take a precise screenshot of just the image element
    """
    try:
        # Wait for the image to be visible
        page.wait_for_selector("img", state="visible", timeout=10000)
        
        # Get image element
        img_element = page.query_selector("img")
        if not img_element:
            print("❌ Image element not found")
            return False
        
        # Get image dimensions and position
        bbox = img_element.bounding_box()
        if not bbox:
            print("❌ Could not get image bounding box")
            return False
        
        # Take screenshot of just the image element
        img_element.screenshot(path=output_path)
        
        print(f"✅ Image screenshot saved to: {output_path}")
        return True
    
    except Exception as e:
        print(f"❌ Error taking screenshot: {e}")
        return False

def process_images(image_urls, output_dir, client=None, headless=False):
    """
    Process image URLs and take screenshots
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
        
        # Create a browser context
        context = browser.new_context(
            viewport={"width": 1280, "height": 720}
        )
        
        # Create a new page
        page = context.new_page()
        
        try:
            for i, image_info in enumerate(image_urls):
                image_url = image_info["url"]
                keyword = image_info["keyword"]
                alt_text = image_info["alt_text"]
                img_id = image_info["id"]
                
                print(f"\n📷 Processing image {i+1}/{len(image_urls)}")
                print(f"🔗 URL: {image_url}")
                print(f"🔑 Keyword: {keyword}")
                print(f"📝 Alt text: {alt_text}")
                
                # Navigate to the image URL
                print(f"🌐 Opening image URL")
                page.goto(image_url)
                
                # Wait for the image to load
                page.wait_for_load_state("networkidle")
                
                # Generate output filename
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                if img_id:
                    filename = f"toa_{img_id}_{timestamp}.png"
                else:
                    # Create a filename based on keyword
                    filename = f"toa_{keyword}_{timestamp}.png"
                
                # Full path to save the image
                output_path = os.path.join(toa_dir, filename)
                
                # Take screenshot of just the image
                success = screenshot_image(page, output_path)
                
                if not success:
                    print("❌ Failed to screenshot image")
                
                # Wait a moment before processing the next image
                time.sleep(2)
            
        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            # Close browser
            browser.close()

def main():
    parser = argparse.ArgumentParser(description="Screenshot TOA images from JSON file")
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
    
    # Process images
    process_images(
        image_urls=image_urls,
        output_dir=args.output,
        client=args.client,
        headless=args.headless
    )
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
