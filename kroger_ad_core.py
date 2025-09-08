"""
Kroger Ad Core Module

This module provides core functionality for extracting ads from Kroger.com search results.
It serves as the main entry point for ad extraction and provides shared utilities.
"""

from bs4 import BeautifulSoup
from collections import Counter
from playwright.sync_api import sync_playwright
import nltk
from nltk.tokenize import word_tokenize
from nltk.util import ngrams
from nltk.corpus import stopwords
import requests
import os
import re
import json
import importlib

# Import ad extractors
from ad_extractors import get_all_extractors, get_extractor

# Setup NLTK
nltk.download('punkt', quiet=True)
nltk.download('stopwords', quiet=True)
stop_words = set(stopwords.words('english'))

# Make sure image directory exists
os.makedirs("images", exist_ok=True)

# Import all extractors to ensure they're registered
import ad_extractors.toa_extractor
import ad_extractors.skyscraper_extractor
import ad_extractors.carousel_extractor

def get_rendered_html(url, wait_ms=5000, user_data_dir=None):
    """
    Get rendered HTML from a URL using Playwright
    
    Args:
        url (str): URL to get HTML from
        wait_ms (int): Time to wait for page to render in milliseconds
        user_data_dir (str): Path to user data directory for persistent browser context
        
    Returns:
        str: Rendered HTML content
    """
    if user_data_dir is None:
        user_data_dir = os.path.expanduser("~/ChromeProfiles/kroger_clean_profile")
    
    with sync_playwright() as p:
        # Try to launch using Playwright's default browser first
        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-infobars",
                    "--disable-web-security",
                ]
            )
        except Exception as e:
            print(f"Error launching browser with default settings: {e}")
            print("Trying alternative browser launch method...")
            # Fall back to using system Chrome if available
            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=False,
                channel="chrome",  # Try using the system Chrome
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-infobars",
                    "--disable-web-security",
                ]
            )
        
        page = context.pages[0] if context.pages else context.new_page()
        
        # Navigate directly to target URL - we should already be logged in
        # Use a less strict wait condition to avoid timeouts
        page.goto(url, wait_until="domcontentloaded")
        
        # Wait longer for the page to stabilize
        print("   Waiting for page to stabilize...")
        page.wait_for_timeout(wait_ms * 4)  # Triple the wait time for better stability
        print("   Waiting one additional second for complete loading...")
        page.wait_for_timeout(2000)  # Additional 1 second wait
        
        # Check if we're still logged in
        if "Sign In" in page.content():
            print("⚠️ Warning: Session appears to be logged out. You may need to re-authenticate.")
        
        html = page.content()
        context.close()
        return html

def extract_common_words_and_phrases(titles):
    """
    Extract common words and phrases from a list of titles
    
    Args:
        titles (list): List of title strings to analyze
        
    Returns:
        dict: Analysis results with common words and phrases
    """
    words = []
    for title in titles:
        tokens = word_tokenize(title.lower())
        words.extend([word for word in tokens if word.isalpha() and word not in stop_words])

    word_freq = Counter(words).most_common(10)

    phrases = []
    for title in titles:
        tokens = word_tokenize(title.lower())
        two_grams = list(ngrams(tokens, 2))
        three_grams = list(ngrams(tokens, 3))
        phrases.extend([" ".join(gram) for gram in two_grams + three_grams])

    phrase_freq = Counter(phrases).most_common(10)

    return {
        "common_words": word_freq,
        "common_phrases": phrase_freq
    }

def extract_ads_from_html(html, client=None):
    """
    Extract all ads from HTML content using registered extractors
    
    Args:
        html (str): HTML content to extract ads from
        client (str, optional): Client name for organizing output
        
    Returns:
        list: List of extracted ad data
    """
    soup = BeautifulSoup(html, 'html.parser')
    results = []
    
    # Get all registered extractors
    extractors = get_all_extractors()
    
    # Use each extractor to find its specific ad type
    for ad_type, extractor_class in extractors.items():
        print(f"Looking for {ad_type} ads...")
        extractor = extractor_class()
        
        # Set client name if provided
        if client:
            extractor.client = client
        
        # For TOA ads, look for the specific div with data-testid="StandardTOA"
        if ad_type == "TOA":
            # Primary selector using data-testid attribute
            toa_divs = soup.select('div[data-testid="StandardTOA"]')
            
            # Fallback selectors if primary selector doesn't find anything
            if not toa_divs:
                toa_divs = soup.select('div.Standard-TOA')
            
            if not toa_divs:
                toa_divs = soup.select('div[class*="TOA"]')
                
            print(f"[{ad_type} Ads Found] {len(toa_divs)}")
            
            for div in toa_divs:
                # Store the raw HTML for image capture
                raw_html = str(div)
                ad = extractor.extract(raw_html)
                if ad:
                    # Include the raw HTML in the results
                    ad['html'] = raw_html
                    results.append(ad)
        
        # For Skyscraper ads, look for the specific div with data-testid="monetization/search-skyscraper-top"
        elif ad_type == "Skyscraper":
            # Look for skyscraper ads
            skyscraper_divs = soup.select('div[data-testid="monetization/search-skyscraper-top"]')
            
            # Fallback selectors
            if not skyscraper_divs:
                skyscraper_divs = soup.select('div.amp-container[data-testid*="skyscraper"]')
                
            if not skyscraper_divs:
                skyscraper_divs = soup.select('div.amp-container')
                
            print(f"[{ad_type} Ads Found] {len(skyscraper_divs)}")
            
            for div in skyscraper_divs:
                # Store the raw HTML for image capture
                raw_html = str(div)
                
                # Try to use the extractor first
                ad = extractor.extract(raw_html)
                
                # If extractor failed, create a basic ad structure
                if not ad:
                    ad = {
                        'type': 'Skyscraper',
                        'html': raw_html
                    }
                    
                    # Try to extract image URL
                    img = div.select_one('img')
                    if img and img.get('src'):
                        ad['image_url'] = img.get('src')
                    
                    # Try to extract link URL
                    link = div.select_one('a')
                    if link and link.get('href'):
                        ad['href'] = link.get('href')
                    
                    # Try to extract message/title
                    title = div.select_one('h2') or div.select_one('.espot-header')
                    if title:
                        ad['message'] = title.get_text(strip=True)
                    
                    # Try to extract description
                    desc = div.select_one('.espot-subText') or div.select_one('span')
                    if desc:
                        ad['description'] = desc.get_text(strip=True)
                    
                    # Try to extract CTA
                    cta = div.select_one('.espot-linkText')
                    if cta:
                        ad['cta'] = cta.get_text(strip=True)
                
                # Include the raw HTML in the results
                ad['html'] = raw_html
                results.append(ad)
                
        # For CuratedCarousel ads
        elif ad_type == "CuratedCarousel":
            # Look for carousel ads with multiple selectors
            carousel_divs = soup.select('div.CuratedCarousel') or \
                          soup.select('div[class*="Carousel"]') or \
                          soup.select('div[data-testid*="carousel"]')
            
            print(f"[{ad_type} Ads Found] {len(carousel_divs)}")
            
            for div in carousel_divs:
                # Store the raw HTML for image capture
                raw_html = str(div)
                
                # Try to use the extractor
                ad = extractor.extract(raw_html)
                
                if ad:
                    # Include the raw HTML in the results
                    ad['html'] = raw_html
                    results.append(ad)
        
    return results

# For backward compatibility
def extract_toa_ad(html):
    """
    Extract a TOA ad from HTML content (for backward compatibility)
    
    Args:
        html (str): HTML content to extract from
        
    Returns:
        dict or None: Extracted TOA ad data or None if no TOA ad found
    """
    toa_extractor = get_extractor("TOA")()
    return toa_extractor.extract(html)
