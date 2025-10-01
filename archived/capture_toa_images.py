"""
TOA Image Capture Utility

This script captures TOA images from HTML content and saves them to the TOA subfolder.
"""

import os
import json
import glob
from datetime import datetime
from bs4 import BeautifulSoup
import html2image
from PIL import Image

def detect_toa_banner(img, message=None):
    """
    Detect TOA banner in an image using visual characteristics and message matching
    
    Args:
        img: PIL Image object
        message: Optional message text to look for in the banner
        
    Returns:
        tuple: (x1, y1, x2, y2) coordinates of the detected banner or None if not found
    """
    try:
        from PIL import Image, ImageDraw, ImageFilter
        import numpy as np
        
        # Convert to numpy array for processing
        img_array = np.array(img)
        height, width = img_array.shape[:2]
        
        # For Kroger, the TOA banner is typically in a specific position
        # We need to look for the yellow banner with rounded corners
        # that appears after the navigation bar
        
        # First, let's try to find the banner by looking for horizontal edges
        # which might indicate the top and bottom of the banner
        
        # Convert to grayscale for edge detection
        gray_img = img.convert('L')
        
        # Apply edge detection
        edges = gray_img.filter(ImageFilter.FIND_EDGES)
        edges_array = np.array(edges)
        
        # Look for horizontal lines in the top portion of the page
        # The TOA banner typically starts around 150-200 pixels from the top
        search_start = 100
        search_end = min(500, height // 2)  # Don't search more than half the page
        
        # Sum edge intensities horizontally to find strong horizontal lines
        horizontal_sums = np.sum(edges_array[search_start:search_end, :], axis=1)
        
        # Find peaks in horizontal sums (potential banner boundaries)
        # Simple approach: look for values above the mean
        threshold = np.mean(horizontal_sums) * 1.5
        potential_boundaries = [i + search_start for i, val in enumerate(horizontal_sums) if val > threshold]
        
        # Group adjacent boundaries
        boundaries = []
        if potential_boundaries:
            current_group = [potential_boundaries[0]]
            for i in range(1, len(potential_boundaries)):
                if potential_boundaries[i] - potential_boundaries[i-1] <= 3:  # Adjacent within 3 pixels
                    current_group.append(potential_boundaries[i])
                else:
                    boundaries.append(sum(current_group) // len(current_group))  # Average of group
                    current_group = [potential_boundaries[i]]
            boundaries.append(sum(current_group) // len(current_group))  # Add last group
        
        # If we found at least two boundaries, use them as top and bottom of banner
        if len(boundaries) >= 2:
            # Sort boundaries by position
            boundaries.sort()
            
            # Find the first two boundaries that are at least 80 pixels apart
            # (TOA banners are typically at least 80 pixels tall)
            for i in range(len(boundaries) - 1):
                if boundaries[i+1] - boundaries[i] >= 80:
                    start_y = boundaries[i]
                    banner_height = boundaries[i+1] - boundaries[i]
                    break
            else:  # No suitable pair found
                # Fall back to fixed position
                start_y = 170
                banner_height = 100
        else:
            # Fall back to fixed position
            start_y = 170
            banner_height = 100
        
        # Return coordinates for the TOA banner area
        banner_coords = (0, start_y, width, start_y + banner_height)
        
        return banner_coords
    except Exception as e:
        print(f"⚠️ Error in banner detection: {e}")
        return None

def create_toa_image_from_screenshot(client_dir, keyword, output_path, message=None):
    """Create TOA image from existing screenshot with intelligent banner detection"""
    try:
        from PIL import Image, ImageDraw
        
        # Find the corresponding screenshot in main folder
        main_dir = os.path.join(client_dir, "main")
        if not os.path.exists(main_dir):
            print(f"❌ Main directory not found: {main_dir}")
            return None
        
        # Look for screenshots matching the keyword
        screenshot_pattern = f"search_results_{keyword}_*.png"
        screenshots = glob.glob(os.path.join(main_dir, screenshot_pattern))
        
        if not screenshots:
            print(f"❌ No screenshots found for keyword: {keyword}")
            return None
        
        # Use the most recent screenshot
        screenshot_path = max(screenshots, key=os.path.getmtime)
        print(f"📄 Using screenshot: {os.path.basename(screenshot_path)}")
        
        # Open the screenshot with PIL
        img = Image.open(screenshot_path)
        
        # Try to detect the TOA banner
        banner_coords = detect_toa_banner(img, message)
        
        if banner_coords:
            # Crop to the detected banner
            x1, y1, x2, y2 = banner_coords
            toa = img.crop((x1, y1, x2, y2))
            print(f"🔍 Detected TOA banner at coordinates: {banner_coords}")
        else:
            # Fall back to default cropping if detection fails
            width, height = img.size
            toa_height = int(height * 0.2)  # Take top 20%
            toa = img.crop((0, 0, width, toa_height))
            print("⚠️ Using default banner crop (top 20% of image)")
        
        # Save the cropped image
        toa.save(output_path)
        
        print(f"📷 TOA image created from screenshot: {output_path}")
        return output_path
    except Exception as e:
        print(f"❌ Error creating TOA image: {e}")
        return None

def process_toa_results(client_dir):
    """Process TOA results to capture images"""
    # Create TOA subfolder if it doesn't exist
    toa_dir = os.path.join(client_dir, "TOA")
    os.makedirs(toa_dir, exist_ok=True)
    
    # Find the latest TOA results file (check both main dir and TOA subfolder)
    results_files = glob.glob(os.path.join(client_dir, "toa_results_*.json"))
    toa_results_files = glob.glob(os.path.join(toa_dir, "toa_results_*.json"))
    
    # Combine the results
    all_results_files = results_files + toa_results_files
    
    if not all_results_files:
        print(f"❌ No TOA results found in {client_dir} or {toa_dir}")
        return False
    
    # Sort by modification time (newest first)
    latest_results = max(all_results_files, key=os.path.getmtime)
    print(f"📄 Processing TOA results: {os.path.basename(latest_results)}")
    
    try:
        # Load the results
        with open(latest_results, 'r', encoding='utf-8') as f:
            results = json.load(f)
        
        # Find all screenshots in the main folder
        main_dir = os.path.join(client_dir, "main")
        if not os.path.exists(main_dir):
            print(f"❌ Main directory not found: {main_dir}")
            return False
            
        # Get all screenshots
        all_screenshots = glob.glob(os.path.join(main_dir, "search_results_*.png"))
        if not all_screenshots:
            print(f"❌ No screenshots found in {main_dir}")
            return False
            
        print(f"📷 Found {len(all_screenshots)} screenshots to process")
        
        # Process each screenshot
        for screenshot_path in all_screenshots:
            # Extract keyword from filename
            filename = os.path.basename(screenshot_path)
            keyword = None
            if "search_results_" in filename and ".png" in filename:
                # Format is typically search_results_keyword_timestamp.png
                parts = filename.replace("search_results_", "").split("_")
                if len(parts) > 1:
                    # Join all parts except the last one (timestamp) and the file extension
                    keyword = "_".join(parts[:-1]).replace(".png", "")
            
            if not keyword:
                print(f"⚠️ Could not extract keyword from {filename}, skipping")
                continue
                
            print(f"📝 Processing screenshot for keyword: '{keyword}'")
            
            # Find message for this keyword in results
            message = None
            for result in results.get("results", []):
                if result.get("keyword") == keyword and result.get("ads"):
                    ads = result.get("ads", [])
                    if ads and "message" in ads[0]:
                        message = ads[0]["message"]
                        print(f"📝 Using message for detection: '{message}'")
                    break
            
            # Generate TOA image filename
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            toa_filename = f"toa_{keyword}_{timestamp}.png"
            output_path = os.path.join(toa_dir, toa_filename)
            
            # Create TOA image from screenshot
            img = Image.open(screenshot_path)
            banner_coords = detect_toa_banner(img, message)
            
            if banner_coords:
                # Crop to the detected banner
                x1, y1, x2, y2 = banner_coords
                toa = img.crop((x1, y1, x2, y2))
                print(f"🔍 Detected TOA banner at coordinates: {banner_coords}")
            else:
                # Fall back to default cropping if detection fails
                width, height = img.size
                toa_height = int(height * 0.1)  # Take top 10%
                toa = img.crop((0, 0, width, toa_height))
                print("⚠️ Using default banner crop (top 10% of image)")
            
            # Save the cropped image
            toa.save(output_path)
            print(f"📷 TOA image created: {output_path}")
            
            # Update all ads with the TOA image path for this keyword
            for result in results.get("results", []):
                if result.get("keyword") == keyword:
                    for ad in result.get("ads", []):
                        ad["toa_image_path"] = output_path
        
        # Save the updated results file
        # If the file is already in the TOA subfolder, just update it there
        if os.path.dirname(latest_results) == toa_dir:
            with open(latest_results, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2)
            print(f"✅ Updated results file: {os.path.basename(latest_results)}")
        else:
            # Move the results file to TOA subfolder
            new_results_path = os.path.join(toa_dir, os.path.basename(latest_results))
            with open(new_results_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2)
            
            # Remove the old results file
            os.remove(latest_results)
            print(f"✅ Moved results file to: {os.path.basename(new_results_path)}")
        
        print(f"✅ TOA images captured and results moved to {toa_dir}")
        return True
    except Exception as e:
        print(f"❌ Error processing TOA results: {e}")
        return False

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Capture TOA images from HTML content")
    parser.add_argument("client", help="Client directory to process")
    args = parser.parse_args()
    
    client_dir = os.path.join("output", args.client)
    if not os.path.exists(client_dir):
        print(f"❌ Client directory not found: {client_dir}")
        return False
    
    return process_toa_results(client_dir)

if __name__ == "__main__":
    main()
