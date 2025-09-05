"""
Base Ad Extractor

This module provides a base class for all ad extractors with common functionality.
"""

from bs4 import BeautifulSoup
import os
import requests
import re

class AdExtractor:
    """Base class for all ad extractors"""
    
    def __init__(self):
        """Initialize the ad extractor"""
        self.ad_type = "base"  # Override in subclasses
    
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
    
    def save_image(self, url, out_dir="images", filename=None):
        """
        Download and save an image from a URL
        
        Args:
            url (str): URL of the image to download
            out_dir (str): Directory to save the image in
            filename (str, optional): Filename to save the image as
            
        Returns:
            str or None: Path to the saved image or None if download failed
        """
        try:
            os.makedirs(out_dir, exist_ok=True)
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            if not filename:
                filename = url.split("/")[-1]
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
