"""
Template Ad Extractor

This is a template for creating new ad type extractors.
Copy this file and modify it to create a new ad type extractor.
"""

from bs4 import BeautifulSoup
from .base_extractor import AdExtractor
from . import register_extractor

class TemplateExtractor(AdExtractor):
    """Template for creating new ad type extractors"""
    
    def __init__(self):
        """Initialize the template extractor"""
        super().__init__()
        self.ad_type = "TEMPLATE"  # Change this to your ad type
    
    def extract(self, html):
        """
        Extract ad data from HTML content
        
        Args:
            html (str): HTML content to extract from
            
        Returns:
            dict or None: Extracted ad data or None if no ad found
        """
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find the ad element - replace with your own selector
        ad_element = soup.find("div", {"data-testid": "YourAdTypeSelector"})
        if not ad_element:
            return None

        # Initialize result with ad type
        result = {"type": self.ad_type}

        # Extract ad properties - customize these for your ad type
        # Example: Extract title/message
        result["message"] = self.extract_text(ad_element, ".your-title-selector")
        
        # Example: Extract description
        result["description"] = self.extract_text(ad_element, ".your-description-selector")
        
        # Example: Extract call-to-action text
        result["cta"] = self.extract_text(ad_element, ".your-cta-selector")
        
        # Example: Extract image
        img_url = self.extract_attribute(ad_element, "img.your-image-selector", "src")
        if img_url:
            # Add domain if it's a relative URL
            if img_url.startswith("/"):
                img_url = "https://www.kroger.com" + img_url
                
            result["image_url"] = img_url
            result["image_path"] = self.save_image(img_url)
            
            # Try to extract brand from alt text
            alt_text = self.extract_attribute(ad_element, "img.your-image-selector", "alt")
            if alt_text:
                brand = self.extract_brand_from_text(alt_text)
                if brand:
                    result["brand"] = brand
        
        # Example: Extract link URL
        href = self.extract_attribute(ad_element, "a.your-link-selector", "href")
        if href:
            result["href"] = href
            
            # Try to extract brand from href if not already found
            if "brand" not in result:
                brand = self.extract_brand_from_href(href)
                if brand:
                    result["brand"] = brand
        
        # Add any additional ad-specific properties here
        
        return result

# Uncomment and modify to register your extractor
# register_extractor("YOUR_AD_TYPE", TemplateExtractor)
