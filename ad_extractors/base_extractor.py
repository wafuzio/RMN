"""
Base Ad Extractor

This module provides a base class for all ad extractors with common functionality.
"""

from bs4 import BeautifulSoup
import os
import requests
import re

class AdExtractor:
    """Base class for ad extractors"""
    
    def __init__(self):
        """Initialize the extractor"""
        self.ad_type = "Generic"
        self.client = None
        self.search_term = None
    
    def extract(self, html):
        """
        Extract ad data from HTML content
        
        Args:
            html (str): HTML content to extract from
            
        Returns:
            dict or None: Extracted ad data or None if no ad found
        """
        raise NotImplementedError("Subclasses must implement extract()")
    
    def extract_text(self, element, selector, default=None):
        """
        Extract text from an element using a CSS selector
        
        Args:
            element: BeautifulSoup element to search within
            selector (str): CSS selector to find the target element
            default: Default value if element not found or has no text
            
        Returns:
            str or default: Extracted text or default value
        """
        try:
            found = element.select_one(selector)
            return found.text.strip() if found else default
        except (AttributeError, TypeError, ValueError) as e:
            print(f"[Text Extraction Failed] {selector}: {e}")
            return default
    
    def extract_attribute(self, element, selector, attribute, default=None):
        """
        Extract an attribute from an element using a CSS selector
        
        Args:
            element: BeautifulSoup element to search within
            selector (str): CSS selector to find the target element
            attribute (str): Attribute name to extract
            default: Default value if element or attribute not found
            
        Returns:
            str or default: Extracted attribute value or default value
        """
        try:
            found = element.select_one(selector)
            return found.get(attribute, default) if found else default
        except (AttributeError, TypeError, ValueError) as e:
            print(f"[Attribute Extraction Failed] {selector}.{attribute}: {e}")
            return default
    
    def save_image(self, url, out_dir="images", filename=None, search_term=None):
        """
        Download and save an image from a URL
        
        Args:
            url (str): URL of the image to download
            out_dir (str): Directory to save the image in
            filename (str, optional): Filename to save the image as
            search_term (str, optional): Search term to include in the filename
            
        Returns:
            str or None: Path to the saved image or None if download failed
        """
        try:
            os.makedirs(out_dir, exist_ok=True)
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            if not filename:
                filename = url.split("/")[-1]
                
            # Include search term in filename if provided
            if search_term:
                # Sanitize search term for filename
                safe_search_term = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in search_term)
                name, ext = os.path.splitext(filename)
                filename = f"{name}_{safe_search_term}{ext}"
                
            filepath = os.path.join(out_dir, filename)
            with open(filepath, "wb") as f:
                f.write(response.content)
            return filepath
        except requests.RequestException as e:
            print(f"[Image Request Failed] {url} - {e}")
            return None
        except IOError as e:
            print(f"[Image File Write Failed] {url} - {e}")
            return None
        except ValueError as e:
            print(f"[Image URL Invalid] {url} - {e}")
            return None
            
    def save_image_with_crop(self, url, out_dir="images", filename=None, html_element=None, search_term=None):
        """
        Download and save both the full image and an extracted TOA-only version
        
        Args:
            url (str): URL of the image to download
            out_dir (str): Directory to save the image in
            filename (str, optional): Filename to save the image as
            html_element (BeautifulSoup element, optional): The TOA HTML element for precise extraction
            search_term (str, optional): Search term to include in the filename
            
        Returns:
            dict: Paths to the saved images {'full': full_path, 'toa': toa_path}
        """
        try:
            # Import PIL only when needed to avoid dependency issues
            from PIL import Image
            import io
            
            # Create main and TOA subfolders
            if out_dir:
                main_dir = os.path.join(out_dir, "main")
                toa_dir = os.path.join(out_dir, "TOA")
            else:
                main_dir = "images/main"
                toa_dir = "images/TOA"
                
            os.makedirs(main_dir, exist_ok=True)
            os.makedirs(toa_dir, exist_ok=True)
            
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            if not filename:
                filename = url.split("/")[-1]
            
            # Include search term in filename if provided
            if search_term:
                # Sanitize search term for filename
                safe_search_term = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in search_term)
                name, ext = os.path.splitext(filename)
                filename = f"{name}_{safe_search_term}{ext}"
                
            # Save full image in main subfolder
            full_filepath = os.path.join(main_dir, filename)
            with open(full_filepath, "wb") as f:
                f.write(response.content)
                
            # Create TOA-only version
            try:
                # Get file extension
                name, ext = os.path.splitext(filename)
                toa_filename = f"{name}{ext}"  # No need for _toa suffix since it's in a separate folder
                toa_filepath = os.path.join(toa_dir, toa_filename)
                
                # Open image with PIL
                img = Image.open(io.BytesIO(response.content))
                
                # If we have the HTML element, try to extract just the TOA image dimensions
                if html_element:
                    # Try to get the image dimensions from the HTML element
                    width, height = img.size
                    
                    # Look for width and height attributes or style
                    img_tag = html_element.select_one("img.espot-image")
                    if img_tag:
                        # Try to get dimensions from style attribute
                        style = img_tag.get("style", "")
                        width_match = re.search(r'width:\s*(\d+)px', style)
                        height_match = re.search(r'height:\s*(\d+)px', style)
                        
                        # If found in style, use those dimensions
                        if width_match and height_match:
                            toa_width = int(width_match.group(1))
                            toa_height = int(height_match.group(1))
                            
                            # Calculate position (centered in the original image)
                            left = max(0, (width - toa_width) // 2)
                            top = max(0, (height - toa_height) // 2)
                            
                            # Ensure we don't exceed image bounds
                            right = min(width, left + toa_width)
                            bottom = min(height, top + toa_height)
                            
                            # Crop to TOA dimensions
                            toa = img.crop((left, top, right, bottom))
                        else:
                            # If no style dimensions, look for width/height attributes
                            toa_width = img_tag.get("width")
                            toa_height = img_tag.get("height")
                            
                            if toa_width and toa_height:
                                toa_width = int(toa_width)
                                toa_height = int(toa_height)
                                
                                # Calculate position (centered)
                                left = max(0, (width - toa_width) // 2)
                                top = max(0, (height - toa_height) // 2)
                                
                                # Ensure we don't exceed image bounds
                                right = min(width, left + toa_width)
                                bottom = min(height, top + toa_height)
                                
                                # Crop to TOA dimensions
                                toa = img.crop((left, top, right, bottom))
                            else:
                                # If no dimensions found, use image detection to find the banner
                                # This uses edge detection to find the banner boundaries
                                from PIL import ImageFilter, ImageOps
                                
                                # Convert to grayscale for edge detection
                                gray = ImageOps.grayscale(img)
                                
                                # Apply edge detection
                                edges = gray.filter(ImageFilter.FIND_EDGES)
                                
                                # Find the banner area (look for horizontal lines)
                                # This is a simplified approach - in practice you might need more sophisticated image processing
                                width, height = img.size
                                
                                # For now, just take the top third where TOAs usually appear
                                toa_height = int(height * 0.33)
                                toa = img.crop((0, 0, width, toa_height))
                    else:
                        # If no img tag found, use a default crop of the top third
                        toa_height = int(height * 0.33)
                        toa = img.crop((0, 0, width, toa_height))
                else:
                    # If no HTML element provided, use image analysis to find the banner
                    # For now, use a simple approach of taking the top third
                    width, height = img.size
                    toa_height = int(height * 0.33)
                    toa = img.crop((0, 0, width, toa_height))
                
                # Save TOA image
                toa.save(toa_filepath)
                
                return {
                    "full": full_filepath,
                    "toa": toa_filepath
                }
            except Exception as e:
                print(f"[TOA Extraction Failed] {url} - {e}")
                return {"full": full_filepath}
                
        except requests.RequestException as e:
            print(f"[Image Request Failed] {url} - {e}")
            return None
        except IOError as e:
            print(f"[Image File Write Failed] {url} - {e}")
            return None
        except ValueError as e:
            print(f"[Image URL Invalid] {url} - {e}")
            return None
    
    def extract_brand_from_text(self, text):
        """
        Extract brand name from text (e.g., "Sponsored by Brand")
        
        Args:
            text (str): Text to extract brand from
            
        Returns:
            str or None: Extracted brand name or None if not found
        """
        if not text:
            return None
            
        if "by" in text.lower():
            brand = text.split("by")[-1].strip()
            brand = re.sub(r'\s+', ' ', brand)  # normalize whitespace
            brand = brand.rstrip('.')  # remove trailing periods if any
            return brand
        return None
    
    def extract_brand_from_href(self, href):
        """
        Extract brand name from href URL
        
        Args:
            href (str): URL to extract brand from
            
        Returns:
            str or None: Extracted brand name or None if not found
        """
        if not href:
            return None
            
        try:
            brand_slug = re.search(r'/pr/kpm-([a-z0-9-]+)', href)
            if brand_slug:
                # Convert slug to readable format (e.g., "brand-name" -> "Brand Name")
                brand = brand_slug.group(1).replace('-', ' ').title()
                return brand
        except re.error:
            pass
        return None
