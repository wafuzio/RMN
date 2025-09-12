#!/usr/bin/env python3
"""
Screenshot Ad Images

This script extracts image URLs from ad JSON files, opens them in a browser,
and takes a precise screenshot of just the image without surrounding space.
Handles all ad types with image_url: TOA, Skyscraper, Carousel, etc.
"""

import os
import sys
import json
import argparse
import time
from datetime import datetime
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext

def extract_image_urls_from_json(json_file, html_file=None):
    """
    Extract image URLs from an ad JSON file for all ad types (TOA, Skyscraper, Carousel)
    
    Args:
        json_file (str): Path to the JSON file with TOA data
        html_file (str, optional): Path to specific HTML file to filter by
        
    Returns:
        list: List of image URLs with metadata
    """
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        image_urls = []
        
        # Track seen URLs to avoid duplicates within the same search term
        seen_urls_by_search_term = {}
        
        # Extract image URLs from the JSON structure
        if "results" in data:
            for result in data["results"]:
                # If html_file is specified, only process results from that HTML file
                # Otherwise, process all results regardless of source file
                if html_file:
                    # Normalize paths for comparison
                    source_file = os.path.normpath(result.get("source_file", ""))
                    html_file_norm = os.path.normpath(html_file)
                    
                    # Compare basenames if full paths don't match
                    if source_file != html_file_norm and os.path.basename(source_file) != os.path.basename(html_file_norm):
                        print(f"Skipping result from {source_file} (looking for {html_file_norm})")
                        continue
                    
                # Get search_term from result or keyword as fallback
                search_term = result.get("search_term", result.get("keyword", "unknown"))
                
                # Initialize seen URLs set for this search term if not already present
                if search_term not in seen_urls_by_search_term:
                    seen_urls_by_search_term[search_term] = set()
                
                if "ads" in result:
                    for ad in result["ads"]:
                        if "image_url" in ad:
                            image_url = ad["image_url"]
                            # Add domain if it's a relative URL
                            if image_url.startswith('/'):
                                image_url = f"https://www.kroger.com{image_url}"
                            
                            # Skip duplicates within the same search term
                            if image_url in seen_urls_by_search_term[search_term]:
                                print(f"Skipping duplicate image URL: {image_url}")
                                continue
                            
                            # Add to seen URLs for this search term
                            seen_urls_by_search_term[search_term].add(image_url)
                            
                            # Clean search term for filename use
                            clean_search_term = search_term.replace(" ", "_").lower()
                            
                            # Get ad type (default to TOA if not specified)
                            ad_type = ad.get("type", "TOA")
                            
                            image_urls.append({
                                "url": image_url,
                                "keyword": result.get("keyword", "unknown"),
                                "search_term": search_term,
                                "clean_search_term": clean_search_term,
                                "alt_text": ad.get("message", ""),
                                "source_file": result.get("source_file", ""),
                                "ad_type": ad_type,
                                # Keep the old ID for backward compatibility
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
    
    # Set up base output directory
    if client:
        base_dir = os.path.join(output_dir, client)
    else:
        base_dir = output_dir
    
    # Create directories for each ad type
    toa_dir = os.path.join(base_dir, "TOA")
    skyscraper_dir = os.path.join(base_dir, "Skyscraper")
    carousel_dir = os.path.join(base_dir, "Carousel")
    
    # Ensure all directories exist
    os.makedirs(toa_dir, exist_ok=True)
    os.makedirs(skyscraper_dir, exist_ok=True)
    os.makedirs(carousel_dir, exist_ok=True)
    
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
                
                # Generate output filename with ad type, search_term, date, time, and index
                clean_search_term = image_info.get("clean_search_term", keyword.replace(" ", "_").lower())
                
                # Get current date and time for filename
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                
                # Get ad type (default to 'toa' if not specified)
                ad_type = image_info.get("ad_type", "toa").lower()
                
                # Use the same format as main screenshots: type_search-term_date_time_index
                filename = f"{ad_type}_{clean_search_term}_{timestamp}_{i+1}.png"
                
                # Determine the appropriate directory based on ad type
                ad_type_lower = ad_type.lower()
                
                if "skyscraper" in ad_type_lower:
                    target_dir = skyscraper_dir
                elif "carousel" in ad_type_lower:
                    target_dir = carousel_dir
                else:  # Default to TOA
                    target_dir = toa_dir
                    
                # Full path to save the image
                output_path = os.path.join(target_dir, filename)
                
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
    parser.add_argument("--html", "-f", help="Path to specific HTML file to process")
    parser.add_argument("--client", "-c", help="Client name for organizing output")
    parser.add_argument("--output", "-o", default="output", help="Output directory (default: output)")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode (no browser UI)")
    args = parser.parse_args()
    
    # Extract image URLs from JSON, filtering by HTML file if specified
    image_urls = extract_image_urls_from_json(args.json, args.html)
    
    if not image_urls:
        if args.html:
            print(f"❌ No image URLs found in the JSON file for HTML file: {args.html}")
        else:
            print("❌ No image URLs found in the JSON file")
        return 1
    
    if args.html:
        print(f"✅ Found {len(image_urls)} image URLs in the JSON file for HTML file: {args.html}")
    else:
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
