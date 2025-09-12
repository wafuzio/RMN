"""
Example script demonstrating how to save images directly from a Playwright browser session
"""

from playwright.sync_api import sync_playwright
import os
import requests
from urllib.parse import urljoin
import base64

def save_image_with_right_click(page, selector, output_path):
    """
    Simulate right-click and save image using context menu
    Note: This approach is less reliable as it depends on OS-specific context menus
    """
    # Right-click on the image
    page.click(selector, button="right")
    
    # This part is tricky and OS-dependent
    # For example, on Windows you might need:
    # page.keyboard.press("v")  # For "Save image as" option
    
    # Instead of trying to use the context menu (which is unreliable),
    # we'll use a more reliable approach below
    print("Note: Right-click context menu automation is not recommended")
    print("Using direct image extraction instead")
    
    # Get image src
    img_src = page.get_attribute(selector, "src")
    
    # Download the image
    if img_src.startswith("data:image"):
        # Handle base64 encoded images
        img_data = img_src.split(",")[1]
        with open(output_path, "wb") as f:
            f.write(base64.b64decode(img_data))
    else:
        # Handle regular URLs
        full_url = urljoin(page.url, img_src)
        response = requests.get(full_url)
        with open(output_path, "wb") as f:
            f.write(response.content)
    
    print(f"Image saved to: {output_path}")

def save_image_direct(page, selector, output_path):
    """
    Save image directly by extracting its source - more reliable approach
    """
    # Get image src
    img_src = page.get_attribute(selector, "src")
    
    # Download the image
    if img_src.startswith("data:image"):
        # Handle base64 encoded images
        img_data = img_src.split(",")[1]
        with open(output_path, "wb") as f:
            f.write(base64.b64decode(img_data))
    else:
        # Handle regular URLs
        full_url = urljoin(page.url, img_src)
        response = requests.get(full_url)
        with open(output_path, "wb") as f:
            f.write(response.content)
    
    print(f"Image saved to: {output_path}")

def save_image_with_download_event(page, selector, download_dir):
    """
    Use Playwright's download event to capture downloaded files
    """
    # Set download directory
    page.context.set_default_timeout(30000)  # Increase timeout for downloads
    
    # Create download directory if it doesn't exist
    os.makedirs(download_dir, exist_ok=True)
    
    # Setup download event listener
    with page.expect_download() as download_info:
        # Trigger download (right-click and select "Save image as")
        page.click(selector, button="right")
        
        # This part is OS-specific and unreliable
        # On Chrome you might need:
        # page.keyboard.press("s")  # For "Save image as" option
    
    # Wait for download to complete
    download = download_info.value
    
    # Save the downloaded file
    suggested_filename = download.suggested_filename
    download_path = os.path.join(download_dir, suggested_filename)
    download.save_as(download_path)
    
    print(f"Image downloaded to: {download_path}")

def save_toa_images_from_kroger(search_term, output_dir):
    """
    Search Kroger for a term and save TOA banner images
    """
    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=False)  # Set headless=False to see the browser
        context = browser.new_context(
            viewport={"width": 1280, "height": 720}
        )
        
        # Create a new page
        page = context.new_page()
        
        # Navigate to Kroger
        page.goto("https://www.kroger.com")
        
        # Accept cookies if prompted
        try:
            page.click("button:has-text('Accept')", timeout=5000)
        except:
            pass  # No cookie prompt
        
        # Search for the term
        page.fill("input[type='search']", search_term)
        page.press("input[type='search']", "Enter")
        
        # Wait for search results
        page.wait_for_load_state("networkidle")
        
        # Look for TOA banner
        toa_selector = "div[data-testid='StandardTOA'] img"
        
        try:
            # Wait for TOA banner to appear
            page.wait_for_selector(toa_selector, timeout=10000)
            
            # Create output directory
            os.makedirs(output_dir, exist_ok=True)
            
            # Save the image using direct method (most reliable)
            output_path = os.path.join(output_dir, f"toa_{search_term.replace(' ', '_')}.png")
            save_image_direct(page, toa_selector, output_path)
            
            print(f"Successfully saved TOA image for search: {search_term}")
        except Exception as e:
            print(f"Error saving TOA image: {e}")
        
        # Close browser
        browser.close()

if __name__ == "__main__":
    # Example usage
    search_term = "ice cream"
    output_dir = "output/toa_images"
    
    save_toa_images_from_kroger(search_term, output_dir)
