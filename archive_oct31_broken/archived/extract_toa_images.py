#!/usr/bin/env python3
"""
Extract TOA Images

Command-line tool to extract TOA banner images from HTML files using local screenshots.
"""

import os
import sys
import argparse
import glob
import re
from datetime import datetime
import json
from bs4 import BeautifulSoup
from PIL import Image

def find_matching_screenshot(html_file, client_dir):
    """
    Find the matching screenshot for an HTML file
    """
    # Get the base filename without extension
    base_name = os.path.splitext(os.path.basename(html_file))[0]
    
    # Look for matching screenshot in main folder
    main_dir = os.path.join(client_dir, "main")
    if os.path.exists(main_dir):
        screenshot_path = os.path.join(main_dir, f"{base_name}.png")
        if os.path.exists(screenshot_path):
            return screenshot_path
    
    # Look for screenshot in client root as fallback
    screenshot_path = os.path.join(client_dir, f"{base_name}.png")
    if os.path.exists(screenshot_path):
        return screenshot_path
    
    return None

def extract_toa_banner_position(html):
    """
    Extract the position of the TOA banner from HTML
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Try to find the TOA banner
    toa_div = soup.select_one('div[data-testid="StandardTOA"]')
    if not toa_div:
        # Try alternative selectors
        toa_div = soup.select_one('div.Standard-TOA')
        if not toa_div:
            return None
    
    # Find the image within the TOA div
    img = toa_div.select_one('img.espot-image')
    if not img:
        img = toa_div.select_one('img')
        if not img:
            return None
    
    # Extract image metadata
    alt_text = img.get('alt', '')
    img_src = img.get('src', '')
    
    # Extract image ID if available
    img_id = None
    if img_src:
        id_match = re.search(r'monetization-v1/([a-f0-9-]+)\.(jpg|png)', img_src)
        if id_match:
            img_id = id_match.group(1)
    
    # For now, we'll use a fixed position for the TOA banner
    # In a real implementation, you would use JavaScript to get the actual position
    # or use image recognition to find the banner
    banner_position = {
        'y': 150,  # Start Y position (after navigation)
        'height': 120  # Banner height
    }
    
    return {
        'position': banner_position,
        'alt_text': alt_text,
        'img_src': img_src,
        'img_id': img_id
    }

def extract_toa_from_screenshot(screenshot_path, banner_info, output_path):
    """
    Extract TOA banner from screenshot using position information
    """
    try:
        # Open the screenshot
        img = Image.open(screenshot_path)
        width, height = img.size
        
        # Get banner position
        y_pos = banner_info['position']['y']
        banner_height = banner_info['position']['height']
        
        # Crop the image to just the TOA banner
        toa_img = img.crop((0, y_pos, width, y_pos + banner_height))
        
        # Save the cropped image
        toa_img.save(output_path)
        
        return True
    except Exception as e:
        print(f"❌ Error cropping TOA image: {e}")
        return False

def process_html_file(html_file, client=None, output_dir=None):
    """
    Process an HTML file to extract TOA banner
    """
    try:
        # Read the HTML file
        with open(html_file, 'r', encoding='utf-8') as f:
            html = f.read()
        
        # Extract client from directory path if not provided
        if client is None:
            dir_path = os.path.dirname(html_file)
            if "output" in dir_path:
                parts = dir_path.split(os.path.sep)
                output_idx = parts.index("output")
                if len(parts) > output_idx + 1:
                    client = parts[output_idx + 1]
        
        # Set up output directory
        if output_dir is None:
            if client:
                output_dir = os.path.join("output", client)
            else:
                output_dir = os.path.dirname(html_file)
        
        # Create TOA subfolder
        toa_dir = os.path.join(output_dir, "TOA")
        os.makedirs(toa_dir, exist_ok=True)
        
        # Find the matching screenshot
        client_dir = os.path.join("output", client) if client else os.path.dirname(html_file)
        screenshot_path = find_matching_screenshot(html_file, client_dir)
        
        if not screenshot_path:
            return [{
                "success": False,
                "error": f"No matching screenshot found for {os.path.basename(html_file)}"
            }]
        
        # Extract TOA banner position from HTML
        banner_info = extract_toa_banner_position(html)
        
        if not banner_info:
            return [{
                "success": False,
                "error": "No TOA banner found in HTML"
            }]
        
        # Generate output filename
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        if banner_info['img_id']:
            filename = f"toa_{banner_info['img_id']}_{timestamp}.png"
        else:
            # Create a filename based on HTML file
            base_name = os.path.splitext(os.path.basename(html_file))[0]
            filename = f"toa_{base_name}_{timestamp}.png"
        
        # Full path to save the image
        output_path = os.path.join(toa_dir, filename)
        
        # Extract TOA from screenshot
        success = extract_toa_from_screenshot(screenshot_path, banner_info, output_path)
        
        if success:
            return [{
                "success": True,
                "image_path": output_path,
                "alt_text": banner_info['alt_text'],
                "img_src": banner_info['img_src'],
                "img_id": banner_info['img_id']
            }]
        else:
            return [{
                "success": False,
                "error": "Failed to extract TOA from screenshot"
            }]
    
    except Exception as e:
        return [{
            "success": False,
            "error": str(e)
        }]

def main():
    parser = argparse.ArgumentParser(description="Extract TOA banner images from HTML files using local screenshots")
    parser.add_argument("--input", "-i", help="HTML file or directory containing HTML files")
    parser.add_argument("--client", "-c", help="Client name for organizing output")
    parser.add_argument("--output", "-o", help="Output directory (default: output/<client>)")
    parser.add_argument("--latest", "-l", action="store_true", help="Process only the latest HTML file")
    args = parser.parse_args()
    
    # Set default input directory if not provided
    if not args.input:
        args.input = "output"
        if args.client:
            args.input = os.path.join(args.input, args.client)
    
    # Set default output directory if not provided
    if not args.output and args.client:
        args.output = os.path.join("output", args.client)
    
    # Process input
    if os.path.isfile(args.input):
        # Process single file
        html_files = [args.input]
    else:
        # Process directory
        html_files = glob.glob(os.path.join(args.input, "*.html"))
        
        if not html_files:
            print(f"❌ No HTML files found in {args.input}")
            return 1
        
        # Sort by modification time (newest first)
        html_files.sort(key=os.path.getmtime, reverse=True)
        
        # Process only the latest file if requested
        if args.latest:
            html_files = html_files[:1]
            print(f"📄 Processing latest HTML file: {os.path.basename(html_files[0])}")
    
    # Process each HTML file
    total_images = 0
    successful_images = 0
    
    for html_file in html_files:
        print(f"\n📄 Processing HTML file: {os.path.basename(html_file)}")
        
        results = process_html_file(
            html_file,
            client=args.client,
            output_dir=args.output
        )
        
        total_images += len(results)
        successful_images += sum(1 for r in results if r.get("success", False))
        
        for i, result in enumerate(results):
            if result.get("success", False):
                print(f"  ✅ TOA Image #{i+1}: {os.path.basename(result['image_path'])}")
                print(f"     Alt text: {result.get('alt_text', 'None')}")
            else:
                print(f"  ❌ TOA Image #{i+1}: Failed - {result.get('error', 'Unknown error')}")

        # Save per-run snapshot JSON file
        # Use timestamp for filename
        snapshot_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        html_dir = os.path.dirname(html_file)
        snapshot_filename = f"toa_results_{snapshot_ts}.json"
        snapshot_path = os.path.join(html_dir, snapshot_filename)
        try:
            with open(snapshot_path, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"  💾 Results snapshot saved: {snapshot_path}")
        except Exception as e:
            print(f"  ❌ Failed to save snapshot: {e}")
    
    print(f"\n📊 Summary: Extracted {successful_images} of {total_images} TOA images")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
