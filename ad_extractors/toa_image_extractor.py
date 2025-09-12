"""
TOA Image Extractor

This module provides functions to extract TOA banner images directly from HTML.
"""

import os
import requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import re
from datetime import datetime

def extract_toa_image_from_html(html, base_url="https://www.kroger.com", output_dir=None, client=None):
    """
    Extract TOA banner image from HTML and save it
    
    Args:
        html (str): HTML content containing TOA banner
        base_url (str): Base URL for resolving relative image URLs
        output_dir (str): Directory to save the image
        client (str): Client name for organizing output
        
    Returns:
        dict: Information about the extracted image including path
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Try multiple selector patterns to find the TOA banner image
    selectors = [
        # Primary selector for TOA banner images
        "div[data-testid='StandardTOA'] img.espot-image",
        # Backup selector if data-testid is missing
        "div.Standard-TOA img.espot-image",
        # More general selector as fallback
        "img.espot-image",
        # Last resort - any image in a div with "TOA" in class or attributes
        "div[class*='TOA'] img"
    ]
    
    # Try each selector until we find a match
    img_tag = None
    for selector in selectors:
        img_tags = soup.select(selector)
        if img_tags:
            img_tag = img_tags[0]
            break
    
    if not img_tag:
        return {"error": "No TOA banner image found in HTML"}
    
    # Extract image URL
    img_src = img_tag.get('src')
    if not img_src:
        return {"error": "Image tag found but no src attribute"}
    
    # Extract alt text for metadata
    alt_text = img_tag.get('alt', '')
    
    # Extract dimensions if available
    width = img_tag.get('width', '')
    height = img_tag.get('height', '')
    
    # Create full URL if it's a relative path
    if img_src.startswith('/'):
        img_src = urljoin(base_url, img_src)
    
    # Extract image ID from URL if possible
    img_id = None
    id_match = re.search(r'monetization-v1/([a-f0-9-]+)\.jpg', img_src)
    if id_match:
        img_id = id_match.group(1)
    
    # Set up output directory
    if output_dir is None:
        output_dir = "output"
    
    # Add client subfolder if provided
    if client:
        output_dir = os.path.join(output_dir, client)
    
    # Create TOA subfolder
    toa_dir = os.path.join(output_dir, "TOA")
    os.makedirs(toa_dir, exist_ok=True)
    
    # Generate filename
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    if img_id:
        filename = f"toa_{img_id}_{timestamp}.jpg"
    else:
        # Create a filename based on alt text or timestamp
        if alt_text:
            # Clean alt text for filename
            clean_alt = re.sub(r'[^a-zA-Z0-9]', '_', alt_text)
            clean_alt = re.sub(r'_+', '_', clean_alt)  # Replace multiple underscores with one
            clean_alt = clean_alt[:30]  # Limit length
            filename = f"toa_{clean_alt}_{timestamp}.jpg"
        else:
            filename = f"toa_banner_{timestamp}.jpg"
    
    # Full path to save the image
    output_path = os.path.join(toa_dir, filename)
    
    # Download and save the image
    try:
        response = requests.get(img_src, timeout=10)
        response.raise_for_status()
        
        with open(output_path, "wb") as f:
            f.write(response.content)
        
        print(f"✅ TOA image saved to: {output_path}")
        
        return {
            "success": True,
            "image_path": output_path,
            "image_url": img_src,
            "alt_text": alt_text,
            "width": width,
            "height": height,
            "image_id": img_id
        }
    
    except Exception as e:
        print(f"❌ Error downloading TOA image: {e}")
        return {
            "success": False,
            "error": str(e),
            "image_url": img_src
        }

def extract_toa_images_from_file(html_file, base_url="https://www.kroger.com", output_dir=None, client=None):
    """
    Extract TOA banner images from an HTML file
    
    Args:
        html_file (str): Path to HTML file
        base_url (str): Base URL for resolving relative image URLs
        output_dir (str): Directory to save images
        client (str): Client name for organizing output
        
    Returns:
        list: Information about extracted images
    """
    try:
        with open(html_file, 'r', encoding='utf-8') as f:
            html = f.read()
        
        # Extract client from directory path if not provided
        if client is None and output_dir is None:
            dir_path = os.path.dirname(html_file)
            if "output" in dir_path:
                parts = dir_path.split(os.path.sep)
                output_idx = parts.index("output")
                if len(parts) > output_idx + 1:
                    client = parts[output_idx + 1]
                    output_dir = os.path.join(*parts[:output_idx+1])
        
        # Find all TOA divs
        soup = BeautifulSoup(html, 'html.parser')
        toa_divs = soup.select('div[data-testid="StandardTOA"]')
        
        results = []
        
        if toa_divs:
            for i, div in enumerate(toa_divs):
                result = extract_toa_image_from_html(
                    str(div), 
                    base_url=base_url,
                    output_dir=output_dir,
                    client=client
                )
                result["toa_index"] = i
                results.append(result)
        else:
            # Try extracting from the whole HTML if no TOA divs found
            result = extract_toa_image_from_html(
                html, 
                base_url=base_url,
                output_dir=output_dir,
                client=client
            )
            results.append(result)
        
        return results
    
    except Exception as e:
        print(f"❌ Error processing HTML file: {e}")
        return [{"success": False, "error": str(e)}]

if __name__ == "__main__":
    # Example usage
    import sys
    
    if len(sys.argv) > 1:
        html_file = sys.argv[1]
        client = sys.argv[2] if len(sys.argv) > 2 else None
        
        results = extract_toa_images_from_file(html_file, client=client)
        
        for i, result in enumerate(results):
            if result.get("success", False):
                print(f"TOA Image #{i+1}: {result['image_path']}")
            else:
                print(f"TOA Image #{i+1}: Failed - {result.get('error', 'Unknown error')}")
    else:
        print("Usage: python toa_image_extractor.py <html_file> [client_name]")
