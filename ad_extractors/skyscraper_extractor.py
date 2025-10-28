"""
Skyscraper Ad Extractor

This module provides functionality to extract skyscraper ads from Kroger.com search results.
"""

from bs4 import BeautifulSoup
import re
import os
import requests
from pathlib import Path
from datetime import datetime
from .base_extractor import AdExtractor
from filename_utils import generate_ad_filename

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
        
        # Save the image if URL is available and we have a client context
        if ad.get('image_url') and self.client:
            try:
                client_dir = Path("output") / self.client
                out_dir = client_dir / "Skyscraper"
                out_dir.mkdir(parents=True, exist_ok=True)

                # Use run timestamp from the caller if present; fallback to now
                ts = getattr(self, "run_ts", None)
                if ts is None:
                    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

                # Determine advertiser token to use in filename
                advertiser = None
                if ad.get("brand"):
                    advertiser = ad["brand"]
                elif ad.get("advertisers"):
                    advertiser = ad["advertisers"][0] if isinstance(ad["advertisers"], list) else None
                advertiser = advertiser or "unknown"

                # Build canonical filename and save path
                filename = generate_ad_filename(
                    retailer="kroger",
                    ad_type="skyscraper",
                    client=self.client,
                    search_term=self.search_term or "unknown",
                    timestamp=ts,
                    index=1,  # if you track position, pass it here
                    extension="png",
                    advertiser=advertiser,
                )
                save_path = out_dir / filename

                # Download and save the image
                resp = requests.get(ad["image_url"], timeout=10)
                resp.raise_for_status()
                save_path.write_bytes(resp.content)

                # Canonical image path (relative to client root)
                ad["image_path"] = str(Path("Skyscraper") / filename)
                # Keep type-specific for back-compat
                ad["skyscraper_image_path"] = ad["image_path"]
            except Exception as e:
                print(f"Error saving skyscraper image: {e}")
        
        return ad

# Register this extractor
from . import register_extractor
register_extractor("Skyscraper", SkyscraperExtractor)
