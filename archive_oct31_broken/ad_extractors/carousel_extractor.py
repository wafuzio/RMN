"""
CuratedCarousel Ad Extractor

This module provides functionality to extract curated carousel ads from Kroger.com search results.
"""

from bs4 import BeautifulSoup
import re
from .base_extractor import AdExtractor

class CarouselExtractor(AdExtractor):
    """Extractor for CuratedCarousel ads on Kroger.com"""
    
    def __init__(self):
        super().__init__()
        self.ad_type = "CuratedCarousel"
    
    def extract(self, html):
        """
        Extract curated carousel ad data from HTML
        Only extracts SPONSORED/FEATURED carousels (not organic product carousels)
        
        Args:
            html (str): HTML content containing carousel ad
            
        Returns:
            dict or None: Extracted ad data or None if no ad found
        """
        soup = BeautifulSoup(html, 'html.parser')
        
        # Check if this is a carousel ad - look for multiple selectors
        carousel_element = soup.select_one('div.CuratedCarousel.py-32.bg-accent-more-subtle') or \
                          soup.select_one('div.CuratedCarousel') or \
                          soup.select_one('div[class*="Carousel"]') or \
                          soup.select_one('div[data-testid*="carousel"]')
        
        if not carousel_element:
            return None
        
        # CRITICAL: Only extract SPONSORED carousels (marked with "Featured" or "Sponsored")
        # Look for the featured flag element or explicit badge text
        featured_indicator = carousel_element.select_one('.CuratedCarousel__featuredFlag') or \
                            carousel_element.select_one('[data-testid="carousel-featured-flag"]') or \
                            carousel_element.select_one('[class*="featured"]') or \
                            carousel_element.select_one('[class*="sponsored"]')
        
        # If no featured element, check for explicit "Featured" or "Sponsored" badge text
        # IMPORTANT: Only check at carousel level, not within product cards
        if not featured_indicator:
            # Look for "Featured" badge BEFORE the product content section
            # The badge should be a direct child or in the header area, not in product cards
            header_section = carousel_element.find('div', class_='CuratedCarousel__header')
            if header_section:
                # Check if "Featured" appears before the header (as a badge)
                for sibling in header_section.previous_siblings:
                    if hasattr(sibling, 'get_text'):
                        text = sibling.get_text(strip=True)
                        if text in ['Featured', 'Sponsored']:
                            featured_indicator = True
                            break
            
            if not featured_indicator:
                # Not a sponsored carousel - skip it
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
        
        # Process carousel as a whole - outside the product loop
        # Only continue if we found products or have a valid carousel element
        if ad['products'] or carousel_element:
            # NOTE: carousel_image_path is now generated centrally in kroger_ad_core.py
            # after brand extraction with lexicon validation. This ensures:
            # 1. JSON path matches the actual saved file
            # 2. Uses the same run timestamp (not datetime.now())
            # 3. Uses canonical brand name from lexicon
            # 4. Consistent with screenshot script filename generation
            
            return ad
        
        return None

# Register this extractor
from . import register_extractor
register_extractor("CuratedCarousel", CarouselExtractor)
