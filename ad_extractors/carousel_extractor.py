"""
CuratedCarousel Ad Extractor

This module provides functionality to extract curated carousel ads from Kroger.com search results.
"""

from bs4 import BeautifulSoup
import re
import os
from datetime import datetime
from .base_extractor import AdExtractor

class CarouselExtractor(AdExtractor):
    """Extractor for CuratedCarousel ads on Kroger.com"""
    
    def __init__(self):
        super().__init__()
        self.ad_type = "CuratedCarousel"
    
    def extract(self, html):
        """
        Extract curated carousel ad data from HTML
        
        Args:
            html (str): HTML content containing carousel ad
            
        Returns:
            dict or None: Extracted ad data or None if no ad found
        """
        soup = BeautifulSoup(html, 'html.parser')
        
        # Check if this is a carousel ad - look for multiple selectors
        carousel_element = soup.select_one('div.CuratedCarousel') or \
                          soup.select_one('div[class*="Carousel"]') or \
                          soup.select_one('div[data-testid*="carousel"]')
        
        if not carousel_element:
            return None
        
        # Initialize ad data
        ad = {
            'type': self.ad_type,
            'products': []
        }
        
        # Extract carousel header
        header = soup.select_one('.CuratedCarousel__header')
        if header:
            ad['header'] = header.get_text(strip=True)
        
        # Extract carousel subheader
        subheader = soup.select_one('.CuratedCarousel__subheader')
        if subheader:
            ad['subheader'] = subheader.get_text(strip=True)
        
        # Extract products in the carousel
        product_links = soup.select('a.kds-Link[aria-label*="title"]')
        
        for link in product_links:
            product = {
                'href': link.get('href', '')
            }
            
            # Extract product title
            title_span = link.select_one('span[data-testid="cart-page-item-description"]')
            if title_span:
                product['title'] = title_span.get_text(strip=True)
            elif link.get('aria-label'):
                # Extract from aria-label as fallback
                aria_label = link.get('aria-label')
                if 'title' in aria_label:
                    product['title'] = aria_label.split('title')[0].strip()
            
            # Extract product image
            img = link.select_one('img') or soup.select_one(f'img[alt*="{product.get("title", "")}"]')
            if img and img.get('src'):
                product['image_url'] = img.get('src')
            
            # Extract product price
            price_elem = soup.select_one(f'[data-testid="cart-page-item-unit-price"]') or \
                         soup.select_one('.kds-Price')
            if price_elem:
                product['price'] = price_elem.get_text(strip=True)
            
            # Add product to list if we have at least a title
            if product.get('title'):
                ad['products'].append(product)
        
        # Only return ad if we found products
        if ad['products']:
            # Save screenshot path for the carousel
            if self.client:
                try:
                    # Create client directory structure if it doesn't exist
                    client_dir = os.path.join("output", self.client)
                    os.makedirs(client_dir, exist_ok=True)
                    
                    # Create carousel directory
                    carousel_dir = os.path.join(client_dir, "Carousel")
                    os.makedirs(carousel_dir, exist_ok=True)
                    
                    # Generate filename
                    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    header_text = ad.get('header', '').lower()
                    
                    if header_text:
                        # Clean header for filename
                        clean_header = re.sub(r'[^a-z0-9]', '_', header_text)
                        clean_header = re.sub(r'_+', '_', clean_header)  # Replace multiple underscores
                        clean_header = clean_header[:30]  # Limit length
                        filename = f"carousel_{clean_header}_{timestamp}.png"
                    else:
                        filename = f"carousel_{timestamp}.png"
                    
                    # Full path to save the image
                    image_path = os.path.join(carousel_dir, filename)
                    
                    # Save image path in ad data
                    ad['carousel_image_path'] = image_path
                    
                except Exception as e:
                    print(f"Error preparing carousel image path: {e}")
            
            return ad
        
        return None

# Register this extractor
from . import register_extractor
register_extractor("CuratedCarousel", CarouselExtractor)
