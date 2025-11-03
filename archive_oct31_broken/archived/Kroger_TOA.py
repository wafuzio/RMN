 
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

 

# Setup NLTK
nltk.download('punkt')
nltk.download('stopwords')
stop_words = set(stopwords.words('english'))

# Make sure image directory exists
os.makedirs("images", exist_ok=True)

def get_rendered_html(url, wait_ms=5000, user_data_dir=None):
    if user_data_dir is None:
        user_data_dir = os.path.expanduser("~/ChromeProfiles/kroger_clean_profile")
    
    with sync_playwright() as p:
        # Use the same user_data_dir as in Kroger_login.py
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
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

def save_image(url, out_dir="images", filename=None):
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

def extract_toa_ad(html):
    soup = BeautifulSoup(html, 'html.parser')
    toa_div = soup.find("div", {"data-testid": "StandardTOA"})
    if not toa_div:
        return None

    result = {"type": "TOA"}

    # Message
    try:
        header = toa_div.select_one(".espot-header")
        result["message"] = header.text.strip() if header else None
    except AttributeError as e:
        print(f"[Message Extraction Failed] Element structure issue: {e}")
        result["message"] = None
    except (TypeError, ValueError) as e:
        print(f"[Message Extraction Failed] Data type issue: {e}")
        result["message"] = None

    # Description
    try:
        desc = toa_div.select_one(".espot-subText")
        result["description"] = desc.text.strip() if desc else None
    except AttributeError as e:
        print(f"[Description Extraction Failed] Element structure issue: {e}")
        result["description"] = None
    except (TypeError, ValueError) as e:
        print(f"[Description Extraction Failed] Data type issue: {e}")
        result["description"] = None

    # CTA
    try:
        cta = toa_div.select_one(".espot-linkText")
        result["cta"] = cta.text.strip() if cta else None
    except AttributeError as e:
        print(f"[CTA Extraction Failed] Element structure issue: {e}")
        result["cta"] = None
    except (TypeError, ValueError) as e:
        print(f"[CTA Extraction Failed] Data type issue: {e}")
        result["cta"] = None

    # Image
    try:
        img = toa_div.select_one("img.espot-image")
        if img:
            img_url = "https://www.kroger.com" + img.get("src", "")
            result["image_url"] = img_url
            result["image_path"] = save_image(img_url)
            
            # Try to extract brand from alt text
            alt_text = img.get("alt", "")
            if alt_text and "by" in alt_text.lower():
                brand = alt_text.split("by")[-1].strip()
                brand = re.sub(r'\s+', ' ', brand)  # normalize whitespace
                brand = brand.rstrip('.')  # remove trailing periods if any
                result["brand"] = brand
    except AttributeError as e:
        print(f"[Image Extraction Failed] Element structure issue: {e}")
    except (TypeError, ValueError) as e:
        print(f"[Image Extraction Failed] Data type issue: {e}")
    except KeyError as e:
        print(f"[Image Extraction Failed] Missing key: {e}")

    # Href
    try:
        link = toa_div.select_one("a.espot-link")
        if link:
            result["href"] = link.get("href")
            
            # Try to extract brand from href if not already found
            if "brand" not in result and "href" in result:
                brand_slug = re.search(r'/pr/kpm-([a-z0-9]+)', result["href"])
                if brand_slug:
                    result["brand"] = brand_slug.group(1).capitalize()
    except AttributeError as e:
        print(f"[Href Extraction Failed] Element structure issue: {e}")
    except (TypeError, ValueError) as e:
        print(f"[Href Extraction Failed] Data type issue: {e}")
    except KeyError as e:
        print(f"[Href Extraction Failed] Missing key: {e}")
    except re.error as e:
        print(f"[Href Extraction Failed] Regex error: {e}")

    return result

def extract_common_words_and_phrases(titles):
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
        phrases.extend([' '.join(g) for g in two_grams + three_grams])

    phrase_freq = Counter(phrases).most_common(10)

    return {
        'words': [{'word': word, 'count': count} for word, count in word_freq],
        'phrases': [{'phrase': phrase, 'count': count} for phrase, count in phrase_freq]
    }

def extract_toa_ads_from_url(url, user_data_dir=None):
    html = get_rendered_html(url, user_data_dir=user_data_dir)
    soup = BeautifulSoup(html, 'html.parser')
    toa_divs = soup.select('div[data-testid="StandardTOA"]')

    print(f"[TOA Ads Found] {len(toa_divs)}")

    results = []
    for div in toa_divs:
        ad = extract_toa_ad(str(div))
        if ad:
            results.append(ad)

    titles = [ad['message'] for ad in results if ad.get('message')]
    analysis = extract_common_words_and_phrases(titles)

    return {
        'ads': results,
        'analysis': analysis,
        'count': len(results)
    }

 

 