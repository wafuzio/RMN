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
        page.wait_for_timeout(wait_ms * 2)  # Double the wait time for better stability
        
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

def extract_ads_from_html(html):
    """
    Extract all ads from HTML content using registered extractors
    
    Args:
        html (str): HTML content to extract ads from
        
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
        
        # For TOA ads, look for the specific div
        if ad_type == "TOA":
            toa_divs = soup.select('div[data-testid="StandardTOA"]')
            print(f"[{ad_type} Ads Found] {len(toa_divs)}")
            
            for div in toa_divs:
                ad = extractor.extract(str(div))
                if ad:
                    results.append(ad)
        
        # Add more ad type extraction logic here as needed
        
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
