"""
TOA (Targeted Onsite Ad) Extractor

This module extracts TOA ads from Kroger.com search results.
"""

from bs4 import BeautifulSoup
from .base_extractor import AdExtractor
from . import register_extractor

class TOAExtractor(AdExtractor):
    """Extractor for Targeted Onsite Ads (TOA)"""
    
    def __init__(self):
        """Initialize the TOA extractor"""
        super().__init__()
        self.ad_type = "TOA"
    
    def extract(self, html):
        """
        Extract TOA ad data from HTML content
        
        Args:
            html (str): HTML content to extract from
            
        Returns:
            dict or None: Extracted TOA ad data or None if no TOA ad found
        """
        soup = BeautifulSoup(html, 'html.parser')
        toa_div = soup.find("div", {"data-testid": "StandardTOA"})
        if not toa_div:
            return None

        result = {"type": self.ad_type}

        # Message (header text)
        result["message"] = self.extract_text(toa_div, ".espot-header")
        
        # Description (subtext)
        result["description"] = self.extract_text(toa_div, ".espot-subText")
        
        # CTA (call to action text)
        result["cta"] = self.extract_text(toa_div, ".espot-linkText")
        
        # Image
        img_url = self.extract_attribute(toa_div, "img.espot-image", "src")
        if img_url:
            # Add domain if it's a relative URL
            if img_url.startswith("/"):
                img_url = "https://www.kroger.com" + img_url
                
            result["image_url"] = img_url
            result["image_path"] = self.save_image(img_url)
            
            # Try to extract brand from alt text
            alt_text = self.extract_attribute(toa_div, "img.espot-image", "alt")
            if alt_text:
                brand = self.extract_brand_from_text(alt_text)
                if brand:
                    result["brand"] = brand
        
        # Href (link URL)
        href = self.extract_attribute(toa_div, "a.espot-link", "href")
        if href:
            result["href"] = href
            
            # Try to extract brand from href if not already found
            if "brand" not in result:
                brand = self.extract_brand_from_href(href)
                if brand:
                    result["brand"] = brand
        
        return result

# Register the extractor
register_extractor("TOA", TOAExtractor)
