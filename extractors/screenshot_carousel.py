#!/usr/bin/env python3
"""
Screenshot Carousel Image

This script captures carousel elements from saved HTML files using Playwright.
It takes accurate screenshots of the entire carousel including all product images.
"""

import os
import json
import argparse
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# Set up logging
import logging
import sys
from logging.handlers import RotatingFileHandler

# Constants
DEFAULT_DIR = "output"
DIAGNOSTICS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diagnostics")
os.makedirs(DIAGNOSTICS_DIR, exist_ok=True)

# Configure logging
log_file = os.path.join(DIAGNOSTICS_DIR, f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[
        RotatingFileHandler(log_file, maxBytes=10485760, backupCount=5),
        logging.StreamHandler(sys.stdout)
    ]
)
logging.info(f"Diagnostics dir: {DIAGNOSTICS_DIR}")
logging.info(f"Log file: {log_file}")

def sanitize_filename(text):
    """Sanitize text for use in filenames"""
    if not text:
        return "unknown"
    # Replace non-alphanumeric characters with underscores
    sanitized = re.sub(r'[^a-zA-Z0-9]', '_', text.lower())
    # Replace multiple underscores with a single one
    sanitized = re.sub(r'_+', '_', sanitized)
    # Limit length
    return sanitized[:50]

def get_daily_results_file(output_dir):
    """Get the path to the daily results file"""
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Create TOA subfolder if it doesn't exist
    toa_dir = os.path.join(output_dir, "TOA")
    os.makedirs(toa_dir, exist_ok=True)
    
    return os.path.join(toa_dir, f"toa_results_{today}.json")

def load_results(results_path):
    """Load results from the JSON file"""
    if os.path.exists(results_path):
        try:
            with open(results_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logging.error(f"Error loading results: {e}")
    return None

def screenshot_carousel(html_file, output_dir=None, search_term=None):
    """
    Take screenshots of carousel elements in the HTML file
    
    Args:
        html_file (str): Path to the HTML file
        output_dir (str, optional): Directory to save screenshots
        search_term (str, optional): Search term to include in filenames
    """
    if not output_dir:
        output_dir = os.path.dirname(html_file)
    
    # Create carousel directory
    carousel_dir = os.path.join(output_dir, "Carousel")
    os.makedirs(carousel_dir, exist_ok=True)
    
    # Get the absolute path to the HTML file
    html_path = os.path.abspath(html_file)
    file_url = f"file://{html_path}"
    
    # Extract search term from filename if not provided
    if not search_term:
        filename = os.path.basename(html_file)
        if filename.startswith("search_results_"):
            # Extract search term from filename
            # Format is typically search_results_SEARCH_TERM_TIMESTAMP.html
            timestamp_pattern = r'_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}'
            match = re.search(timestamp_pattern, filename)
            
            if match:
                # Get everything between 'search_results_' and the timestamp
                keyword_part = filename[len('search_results_'):match.start()]
                search_term = keyword_part.replace('_', ' ').strip()
    
    # Launch Playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
        page = context.new_page()
        
        try:
            # Navigate to the HTML file
            print(f"🌐 Opening HTML file: {file_url}")
            page.goto(file_url, wait_until="domcontentloaded", timeout=30000)
            
            # Wait for the page to be fully loaded
            page.wait_for_load_state("networkidle", timeout=30000)
            
            # Add styling fixes to make the saved HTML render properly
            print("📝 Adding styling fixes to HTML...")
            
            # 1. Disable Content Security Policy to allow loading external resources
            page.add_script_tag(content="""
                // Remove existing CSP meta tags
                document.querySelectorAll('meta[http-equiv="Content-Security-Policy"]').forEach(tag => tag.remove());
                
                // Add a meta tag that allows everything
                const meta = document.createElement('meta');
                meta.setAttribute('http-equiv', 'Content-Security-Policy');
                meta.setAttribute('content', "default-src * 'unsafe-inline' 'unsafe-eval' data: blob:");
                document.head.appendChild(meta);
            """)
            
            # 2. Add base href to resolve relative URLs
            page.add_script_tag(content="""
                // Add base href if it doesn't exist
                if (!document.querySelector('base')) {
                    const base = document.createElement('base');
                    base.href = 'https://www.kroger.com/';
                    document.head.prepend(base);
                }
            """)
            
            # 3. Fetch and inline all stylesheets
            page.add_script_tag(content="""
                async function fetchAndInlineStyles() {
                    const linkTags = Array.from(document.querySelectorAll('link[rel="stylesheet"]'));
                    
                    for (const linkTag of linkTags) {
                        try {
                            const href = linkTag.href;
                            if (!href) continue;
                            
                            console.log('Fetching stylesheet:', href);
                            const response = await fetch(href);
                            if (!response.ok) continue;
                            
                            const cssText = await response.text();
                            
                            // Create a style element with the fetched CSS
                            const style = document.createElement('style');
                            style.textContent = cssText;
                            
                            // Replace the link tag with the style tag
                            linkTag.parentNode.insertBefore(style, linkTag);
                            linkTag.remove();
                            
                            console.log('Inlined stylesheet:', href);
                        } catch (error) {
                            console.error('Error inlining stylesheet:', error);
                        }
                    }
                }
                
                fetchAndInlineStyles();
            """)
            
            # Wait for styles to be applied
            print("⏳ Waiting for styles to be applied...")
            page.wait_for_timeout(2000)  # Give time for styles to be fetched and applied
            
            # Find carousel elements
            selectors = [
                'div.CuratedCarousel.py-32.bg-accent-more-subtle',
                'div.CuratedCarousel',
                'div[class*="Carousel"]',
                'div[data-testid*="carousel"]'
            ]
            
            carousel_count = 0
            
            for selector in selectors:
                carousels = page.locator(selector).all()
                
                if not carousels:
                    continue
                
                print(f"🎠 Found {len(carousels)} carousel(s) with selector: {selector}")
                
                for i, carousel in enumerate(carousels):
                    try:
                        # Wait for the carousel to be visible
                        carousel.wait_for(state="visible", timeout=5000)
                        
                        # Scroll the carousel into view
                        carousel.scroll_into_view_if_needed()
                        
                        # Wait for images inside to finish loading
                        page.wait_for_load_state("networkidle", timeout=5000)
                        page.wait_for_timeout(500)  # Additional wait for any animations
                        
                        # Get carousel header text if available
                        header_text = "unknown"
                        try:
                            header = carousel.locator('.CuratedCarousel__header, h2, .header').first
                            if header:
                                header_text = header.text_content().strip()
                        except Exception as e:
                            print(f"   Note: Could not extract header text: {e}")
                        
                        # Generate filename
                        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                        safe_header = sanitize_filename(header_text)
                        
                        # Include search term in filename if available
                        search_term_part = ""
                        if search_term:
                            safe_search_term = sanitize_filename(search_term)
                            search_term_part = f"_{safe_search_term}"
                        
                        filename = f"carousel_{safe_header}{search_term_part}_{timestamp}.png"
                        filepath = os.path.join(carousel_dir, filename)
                        
                        # Take screenshot with padding
                        try:
                            # Get bounding box
                            box = carousel.bounding_box()
                            pad = 16  # Add padding around the element
                            
                            # Create clip area with padding
                            clip = {
                                "x": max(0, box["x"] - pad),
                                "y": max(0, box["y"] - pad),
                                "width": min(page.viewport_size()["width"] - box["x"] + pad, box["width"] + 2 * pad),
                                "height": box["height"] + 2 * pad
                            }
                            
                            # Take screenshot with clip area
                            page.screenshot(path=filepath, clip=clip)
                            print(f"📸 Carousel screenshot saved to: {filepath}")
                            carousel_count += 1
                            
                        except Exception as e:
                            print(f"❌ Error taking screenshot with padding: {e}")
                            
                            # Fallback: take direct element screenshot
                            try:
                                carousel.screenshot(path=filepath)
                                print(f"📸 Carousel screenshot saved to: {filepath} (direct method)")
                                carousel_count += 1
                            except Exception as e2:
                                print(f"❌ Error taking direct screenshot: {e2}")
                    
                    except Exception as e:
                        print(f"❌ Error processing carousel {i+1}: {e}")
            
            if carousel_count == 0:
                print("⚠️ No carousels found or captured")
            else:
                print(f"✅ Successfully captured {carousel_count} carousel(s)")
                
        except Exception as e:
            print(f"❌ Error processing HTML file: {e}")
        
        finally:
            browser.close()

def process_results_file(results_path, output_dir=None):
    """Process carousel data from the results file"""
    results = load_results(results_path)
    if not results:
        print("❌ No results found")
        return False
    
    # Process each result
    for result in results.get("results", []):
        html_file = result.get("source_file")
        search_term = result.get("keyword")
        
        if html_file and os.path.exists(html_file):
            screenshot_carousel(html_file, output_dir, search_term)
    
    return True

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Screenshot carousel elements from HTML files")
    parser.add_argument("--input", "-i", type=str, help="HTML file to process")
    parser.add_argument("--results", "-r", type=str, help="Results JSON file to process")
    parser.add_argument("--output-dir", "-o", type=str, help="Output directory for screenshots")
    parser.add_argument("--search-term", "-s", type=str, help="Search term to include in filenames")
    args = parser.parse_args()
    
    # Process a single HTML file
    if args.input:
        if not os.path.exists(args.input):
            print(f"❌ HTML file not found: {args.input}")
            return False
        
        screenshot_carousel(args.input, args.output_dir, args.search_term)
        return True
    
    # Process results file
    if args.results:
        results_path = args.results
    else:
        # Use default results file
        output_dir = args.output_dir or DEFAULT_DIR
        results_path = get_daily_results_file(output_dir)
    
    if not os.path.exists(results_path):
        print(f"❌ Results file not found: {results_path}")
        return False
    
    return process_results_file(results_path, args.output_dir)

if __name__ == "__main__":
    print("\n" + "="*50)
    print("CAROUSEL SCREENSHOT TOOL")
    print("="*50)
    
    success = main()
    
    if success:
        print("\n✅ CAROUSEL SCREENSHOT COMPLETED SUCCESSFULLY")
    else:
        print("\n❌ CAROUSEL SCREENSHOT FAILED")
