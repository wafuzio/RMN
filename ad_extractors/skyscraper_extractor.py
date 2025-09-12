"""
Skyscraper Ad Extractor

This module provides functionality to extract skyscraper ads from Kroger.com search results.
"""

from bs4 import BeautifulSoup
import re
import os
from datetime import datetime
from .base_extractor import AdExtractor

class SkyscraperExtractor(AdExtractor):
    """Extractor for Skyscraper ads on Kroger.com"""
    
    def __init__(self):
        super().__init__()
        self.ad_type = "Skyscraper"
    
    def extract(self, html):
        """
        Extract skyscraper ad data from HTML
        
        Args:
            html (str): HTML content containing skyscraper ad
            
        Returns:
            dict or None: Extracted ad data or None if no ad found
        """
        soup = BeautifulSoup(html, 'html.parser')
        
        # Check if this is a skyscraper ad
        if not soup.select_one('div[data-testid*="skyscraper"]') and not soup.select_one('div.amp-container'):
            return None
        
        # Initialize ad data
        ad = {
            'type': self.ad_type,
        }
        
        # Extract image URL
        img = soup.select_one('img')
        if img and img.get('src'):
            image_url = img.get('src')
            # Add domain if it's a relative URL
            if image_url.startswith('/'):
                image_url = f"https://www.kroger.com{image_url}"
            ad['image_url'] = image_url
        
        # Extract link URL
        link = soup.select_one('a')
        if link and link.get('href'):
            href = link.get('href')
            # Add domain if it's a relative URL
            if href.startswith('/'):
                href = f"https://www.kroger.com{href}"
            ad['href'] = href
        
        # Extract message/title
        title = soup.select_one('h2') or soup.select_one('.espot-header')
        if title:
            ad['message'] = title.get_text(strip=True)
        
        # Extract description
        desc = soup.select_one('.espot-subText') or soup.select_one('span')
        if desc:
            ad['description'] = desc.get_text(strip=True)
        
        # Extract CTA
        cta = soup.select_one('.espot-linkText')
        if cta:
            ad['cta'] = cta.get_text(strip=True)
        
        # Extract brand if available
        brand_elem = soup.select_one('.brand-name') or soup.select_one('[class*="brand"]')
        if brand_elem:
            ad['brand'] = brand_elem.get_text(strip=True)
        
        # Save the image if URL is available
        if 'image_url' in ad and self.client:
            try:
                # Create client directory structure if it doesn't exist
                client_dir = os.path.join("output", self.client)
                os.makedirs(client_dir, exist_ok=True)
                
                # Create skyscraper directory
                skyscraper_dir = os.path.join(client_dir, "Skyscraper")
                os.makedirs(skyscraper_dir, exist_ok=True)
                
                # Generate filename
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                
                # Include search term if available
                search_term_part = ""
                if hasattr(self, 'search_term') and self.search_term:
                    # Sanitize search term for filename
                    safe_search_term = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in self.search_term)
                    search_term_part = f"_{safe_search_term}"
                
                # Try to extract image ID from URL
                img_id = None
                if ad['image_url']:
                    id_match = re.search(r'monetization-v1/([a-f0-9-]+)\.(jpg|png)', ad['image_url'])
                    if id_match:
                        img_id = id_match.group(1)
                
                if img_id:
                    filename = f"skyscraper_{img_id}{search_term_part}_{timestamp}.jpg"
                else:
                    # Use message or generic name
                    message = ad.get('message', '').lower()
                    if message:
                        # Clean message for filename
                        clean_message = re.sub(r'[^a-z0-9]', '_', message)
                        clean_message = re.sub(r'_+', '_', clean_message)  # Replace multiple underscores
                        clean_message = clean_message[:30]  # Limit length
                        filename = f"skyscraper_{clean_message}{search_term_part}_{timestamp}.jpg"
                    else:
                        filename = f"skyscraper_ad{search_term_part}_{timestamp}.jpg"
                
                # Full path to save the image
                image_path = os.path.join(skyscraper_dir, filename)
                
                # Save image path in ad data
                ad['skyscraper_image_path'] = image_path
                
            except Exception as e:
                print(f"Error preparing skyscraper image path: {e}")
        
        return ad

# Register this extractor
from . import register_extractor
register_extractor("Skyscraper", SkyscraperExtractor)
