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
from pathlib import Path
import sys, logging, datetime, json

# --- Diagnostics setup ---
PROJECT_ROOT = Path(__file__).resolve().parent
DIAG_DIR = PROJECT_ROOT / "diagnostics"
DIAG_DIR.mkdir(parents=True, exist_ok=True)

# Timestamped log file
LOG_PATH = DIAG_DIR / f"run_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),  # still echo to terminal
    ]
)
def log(msg: str): logging.info(msg)

log(f"Diagnostics dir: {DIAG_DIR}")
log(f"Log file: {LOG_PATH}")

# Import ad extractors
from ad_extractors import get_all_extractors, get_extractor

# Setup NLTK - only download if not already downloaded
try:
    stop_words = set(stopwords.words('english'))
except LookupError:
    nltk.download('stopwords', quiet=True)
    stop_words = set(stopwords.words('english'))

try:
    word_tokenize("test")
except LookupError:
    nltk.download('punkt', quiet=True)

# Make sure image directory exists
os.makedirs("images", exist_ok=True)

# Import all extractors to ensure they're registered
import ad_extractors.toa_extractor
import ad_extractors.skyscraper_extractor
import ad_extractors.carousel_extractor

def get_rendered_html(url, wait_ms=5000, user_data_dir=None, keep_open=False):
    log(f">>> get_rendered_html called: {url}")
    """
    Get rendered HTML from a URL using Playwright
    
    Args:
        url (str): URL to get HTML from
        wait_ms (int): Time to wait for page to render in milliseconds
        user_data_dir (str): Path to user data directory for persistent browser context
        keep_open (bool): If True, keeps the browser open for debugging until Enter is pressed
        
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
                viewport=None,  # critical for real window sizing
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
                viewport=None,  # critical for real window sizing
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
        page.on("console", lambda m: log(f"[console] {m.type}: {m.text}"))
        
        # Navigate directly to target URL - we should already be logged in
        # Use a less strict wait condition to avoid timeouts
        page.goto(url, wait_until="domcontentloaded")
        page.bring_to_front()
        page.wait_for_load_state("domcontentloaded")
        
        # Choose the correct frame to run in
        frames = [f for f in page.frames if f != page.main_frame]
        app = max(frames, key=lambda f: len(f.url)) if frames else page.main_frame
        log(f"   Using frame: {app.url}")
        
        # Probe to verify we're in the right document
        log(f"   Frame count: {len(page.frames)}")
        log(f"   App URL: {app.url}")
        count_expr = "() => document.querySelectorAll('[data-testid*=\"product\"], [class*=\"product-card\"]').length"
        count = app.evaluate(count_expr)
        log(f"   Probe items: {count}")
        
        # Dismiss cookie banners that steal scroll focus if present (in frame)
        try:
            app.locator('button:has-text("Accept")').first.click(timeout=1500)
        except Exception:
            pass

        # Wait much longer for the page to fully load and become scrollable
        log("   Waiting for page to fully load and become scrollable...")
        page.wait_for_timeout(wait_ms * 3)  # window-level timer is fine

        # Ensure the frame DOM is at least loaded
        try:
            app.wait_for_load_state("domcontentloaded", timeout=10000)
            log("   Frame DOM is ready")
        except Exception as e:
            log(f"   Frame domcontentloaded wait skipped: {e}")
            
        # Wait for any spinners or loading indicators to disappear
        try:
            app.wait_for_selector('[class*="loading"], [class*="spinner"], [class*="Spinner"], [class*="Loading"]', state="detached", timeout=5000)
            log("   Loading indicators gone")
        except Exception:
            pass
            
        # Additional wait to ensure page is fully rendered and interactive
        log("   Final stabilization wait...")
        page.wait_for_timeout(5000)  # 5 seconds
        
        log("   Starting progressive scrolling with product detection...")

        def scroll_in_frame():
            return app.evaluate("""
              (async () => {
                const sleep = ms => new Promise(r => setTimeout(r, ms));

                // Traverse light DOM + shadow DOM to find the tallest scrollable element
                const collect = (root, out) => {
                  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
                  while (walker.nextNode()) {
                    const el = walker.currentNode;
                    out.push(el);
                    if (el.shadowRoot) collect(el.shadowRoot, out);
                  }
                };
                const all = [];
                collect(document, all);

                const isScrollable = el => {
                  if (!el) return false;
                  const cs = getComputedStyle(el);
                  return (cs.overflowY === 'auto' || cs.overflowY === 'scroll') && el.scrollHeight > el.clientHeight + 8;
                };

                // Preferred selectors first (search through shadow DOM too)
                const preferredSelectors = [
                  '[data-testid*="results"]',
                  '[data-test*="results"]',
                  'main',
                  '#main',
                  '[role="main"]'
                ];
                const preferred = preferredSelectors
                  .map(sel => all.find(n => n.matches && n.matches(sel)))
                  .filter(Boolean);

                let container = [...preferred, ...all]
                  .filter(isScrollable)
                  .sort((a, b) => b.scrollHeight - a.scrollHeight)[0]
                  || document.scrollingElement || document.documentElement || document.body;

                // Unlock common scroll locks
                for (const el of [document.documentElement, document.body]) {
                  el.style.overflow = 'auto';
                  el.classList.remove('no-scroll','scroll-lock','modal-open');
                  el.style.scrollBehavior = 'auto';
                }
                if (document.activeElement) document.activeElement.blur();

                container.setAttribute('data-scroll-target','1');

                const countItems = () =>
                  document.querySelectorAll('[data-testid*="product"], [data-test*="product"], [class*="product-card"]').length;

                let lastTop = container.scrollTop;
                let lastCount = countItems();
                let stagnantMoves = 0;
                let stagnantItems = 0;

                // Use only programmatic scroll here; real wheel will be driven from Python
                const stepOnce = () => {
                  const step = Math.max(120, Math.floor(container.clientHeight * 0.8));
                  container.scrollBy(0, step);
                };

                for (let i = 0; i < 80; i++) {
                  stepOnce();
                  await sleep(500);

                  const nowTop = container.scrollTop;
                  const nowMax = container.scrollHeight;
                  const nowCount = countItems();

                  const moved = nowTop - lastTop;
                  if (moved < 1) stagnantMoves++; else stagnantMoves = 0;
                  if (nowCount <= lastCount) stagnantItems++; else stagnantItems = 0;

                  console.log(`loop=${i} top=${nowTop} moved=${moved} items=${nowCount} stagnantMoves=${stagnantMoves} stagnantItems=${stagnantItems}`);

                  const atBottom = nowTop + container.clientHeight >= nowMax - 2;
                  lastTop = nowTop;
                  lastCount = nowCount;

                  if (atBottom) { console.log("Reached bottom"); break; }
                  if (stagnantMoves >= 6 && stagnantItems >= 6) { console.log("Stagnant, stopping"); break; }
                }

                // Cosmetic: return to top
                container.scrollTo(0, 0);
                return { ok: true };
              })();
            """)

        # SIMPLEST APPROACH: Direct body scrolling based on screenshot analysis
        log("\n\n   DIRECT BODY SCROLLING - SIMPLEST SOLUTION")
        
        # Save proof artifacts (screenshots, metrics, HTML)
        before_png = DIAG_DIR / "before.png"
        after_png = DIAG_DIR / "after.png"
        metrics_json = DIAG_DIR / "scroll_metrics.json"
        
        try:
            page.screenshot(path=str(before_png))
            log(f"Saved screenshot: {before_png}")
        except Exception as e:
            log(f"ERROR saving before.png: {e}")
        
        # Get initial scroll position from document
        initial_pos_expr = """
            () => {
                return {
                    scrollY: window.scrollY || window.pageYOffset || document.body.scrollTop,
                    height: document.body.scrollHeight,
                    viewport: window.innerHeight,
                    products: document.querySelectorAll('[data-testid*="product"], [class*="product-card"]').length,
                    ads: document.querySelectorAll('[data-testid="monetization/search-page-top"], [data-testid="StandardTOA"]').length
                };
            }
        """
        initial_pos = app.evaluate(initial_pos_expr)
        log(f"   Initial position: scrollY={initial_pos['scrollY']}, height={initial_pos['height']}, viewport={initial_pos['viewport']}, products={initial_pos['products']}, ads={initial_pos['ads']}")
        
        # Ensure focus is in the document
        app.evaluate("() => document.body.focus()")
        
        # Get initial scroll position and capture before_top for metrics
        before_top = app.evaluate("() => (document.querySelector('[data-scroll-target=\"1\"]')?.scrollTop) ?? -1")
        log(f"Initial scrollTop: {before_top}")
        
        try:
            # Simplified scrolling approach that works directly with body
            scroll_result = app.evaluate("""
              (async () => {
                const sleep = ms => new Promise(r => setTimeout(r, ms));
                const metrics = [];

                // Pick the document scroll element robustly
                const scrollEl = document.scrollingElement || document.documentElement || document.body;

                // Initial capture
                metrics.push({
                  loop: -1,
                  y: scrollEl.scrollTop,
                  height: scrollEl.scrollHeight,
                  viewport: window.innerHeight,
                  products: document.querySelectorAll('[data-testid*="product"], [class*="product-card"]').length,
                  ads: document.querySelectorAll('[data-testid="monetization/search-page-top"], [data-testid="StandardTOA"]').length
                });

                let stagnant = 0;
                let lastHeight = scrollEl.scrollHeight;
                let lastY = scrollEl.scrollTop;

                // Dynamic loop: keep scrolling while content grows or we keep moving
                // Hard caps to avoid infinite loops
                for (let loop = 0; loop < 150 && stagnant < 5; loop++) {
                  const step = Math.max(200, Math.floor(window.innerHeight * 0.85));
                  scrollEl.scrollBy(0, step);
                  await sleep(700);

                  const y = scrollEl.scrollTop;
                  const height = scrollEl.scrollHeight;
                  const products = document.querySelectorAll('[data-testid*="product"], [class*="product-card"]').length;
                  const ads = document.querySelectorAll('[data-testid="monetization/search-page-top"], [data-testid="StandardTOA"]').length;

                  metrics.push({ loop, y, height, products, ads });

                  const moved = Math.abs(y - lastY) >= 2;
                  const grew  = height > lastHeight + 2;
                  if (!moved && !grew) stagnant++; else stagnant = 0;
                  lastY = y; lastHeight = height;
                }

                // Optional cosmetic: return to top (comment out if you want to leave at bottom)
                // scrollEl.scrollTo(0, 0);

                return {
                  done: true,
                  finalY: scrollEl.scrollTop,
                  finalHeight: scrollEl.scrollHeight,
                  loops: metrics.length,
                  metrics
                };
              })();
            """)

            log(f"Scroll result: {scroll_result}")

            # Get after_top for metrics
            after_top = app.evaluate("() => (document.querySelector('[data-scroll-target=\"1\"]')?.scrollTop) ?? -1")
            delta = (after_top or 0) - (before_top or 0)
            log(f"container scrollTop delta = {delta}")

            # Save metrics to file
            try:
                with open(metrics_json, "w", encoding="utf-8") as f:
                    json.dump({
                        "before_top": before_top,
                        "after_top": after_top,
                        "delta": delta,
                        "finalY": scroll_result.get('finalY'),
                        "finalHeight": scroll_result.get('finalHeight'),
                        "scroll_result": scroll_result
                    }, f, indent=2)
                log(f"Saved metrics: {metrics_json}")
            except Exception as e:
                log(f"ERROR capturing scroll metrics: {e}")
        except Exception as e:
            log(f"ERROR during scrolling: {e}")
        
        # Take after screenshot
        try:
            page.screenshot(path=str(after_png))
            log(f"Saved screenshot: {after_png}")
        except Exception as e:
            log(f"ERROR saving after.png: {e}")
        
        # Get final scroll position
        final_pos = app.evaluate("""
            () => {
                const docEl = document.scrollingElement || document.documentElement || document.body;
                return {
                    scrollY: window.pageYOffset || docEl.scrollTop || 0,
                    height: docEl.scrollHeight,
                    viewport: window.innerHeight,
                    products: document.querySelectorAll('[data-testid*="product"], [class*="product-card"]').length
                };
            }
        """)
        log(f"   Final position: scrollY={final_pos['scrollY']}, height={final_pos['height']}, viewport={final_pos['viewport']}, products={final_pos['products']}")
        log(f"   Scroll delta: {final_pos['scrollY'] - initial_pos['scrollY']}")
        log(f"   Product count delta: {final_pos['products'] - initial_pos['products']}")
        
        # Press Home to return to top
        log("   Returning to top...")
        page.keyboard.press("Home")
        page.wait_for_timeout(500)

        # Run the programmatic scroller (works even if wheel listeners are ignored)
        res = scroll_in_frame()
        log(f"   Scroll routine finished: {res}")

        # Backup 1: element-hop if movement was blocked
        try:
            app.wait_for_selector('[data-testid*="product"], [data-test*="product"], [class*="product-card"]', timeout=5000)
            cards = app.locator('[data-testid*="product"], [data-test*="product"], [class*="product-card"]')
            count = cards.count()
            if count:
                log("   Element-hop scroller engaged")
                for _ in range(12):
                    c = cards.count()
                    if not c:
                        break
                    cards.nth(min(c - 1, 24)).scroll_into_view_if_needed()
                    page.wait_for_timeout(600)
        except Exception as e:
            log(f"   Element-hop failed: {e}")

        # Backup 2: if the app uses frame-window scroll, try that once
        try:
            app.evaluate("""
              const el = document.scrollingElement || document.documentElement || document.body;
              el.scrollBy(0, Math.max(200, Math.floor(window.innerHeight * 0.8)));
            """)
        except Exception:
            pass
            
        log("   Scrolled back to top")
        
        # Final wait for any post-scroll loading
        log("   Waiting for final page stabilization...")
        page.wait_for_timeout(2000)  # Additional 2 second wait
        
        # Check if we're still logged in
        if "Sign In" in page.content():
            log("⚠️ Warning: Session appears to be logged out. You may need to re-authenticate.")
        
        html = page.content()
        
        # Save HTML snapshot
        try:
            html_path = DIAG_DIR / "final.html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
            log(f"Saved HTML snapshot: {html_path}")
        except Exception as e:
            log(f"ERROR saving HTML snapshot: {e}")
        
        # Before closing: keep browser open for debugging if requested
        if keep_open:
            log("keep_open=True; waiting for Enter to close browser...")
            try:
                input("Press Enter to close browser...")
            except EOFError:
                pass
        
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

def extract_ads_from_html(html, client=None, search_term=None):
    """
    Extract all ads from HTML content using registered extractors
    
    Args:
        html (str): HTML content to extract from
        client (str, optional): Client name for image saving
        search_term (str, optional): Search term to include in image filenames
        
    Returns:
        list: List of extracted ad data
    """
    soup = BeautifulSoup(html, 'html.parser')
    results = []
    
    # Get all registered extractors
    extractors = get_all_extractors()
    
    # Use each extractor to find its specific ad type
    for ad_type, extractor_class in extractors.items():
        log(f"Looking for {ad_type} ads...")
        extractor = extractor_class()
        
        # Set client name if provided
        if client:
            extractor.client = client
            
        # Set search term for image filenames
        if search_term:
            extractor.search_term = search_term
        
        # For TOA ads, look for the specific div with data-testid="StandardTOA" (confirmed in screenshot)
        if ad_type == "TOA":
            # Primary selector using data-testid attribute (confirmed in screenshot)
            toa_divs = soup.select('div[data-testid="StandardTOA"]')
            
            # Fallback selectors if primary selector doesn't find anything
            if not toa_divs:
                toa_divs = soup.select('div.Standard-TOA')
            
            if not toa_divs:
                toa_divs = soup.select('div[class*="TOA"]')
                
            log(f"[{ad_type} Ads Found] {len(toa_divs)}")
            
            for div in toa_divs:
                # Store the raw HTML for image capture
                raw_html = str(div)
                ad = extractor.extract(raw_html)
                if ad:
                    # Include the raw HTML in the results
                    ad['html'] = raw_html
                    results.append(ad)
        
        # For Skyscraper ads, look for the specific div with data-testid="monetization/search-page-top" (confirmed in screenshot)
        elif ad_type == "Skyscraper":
            # Look for skyscraper ads using the selector confirmed in screenshot
            skyscraper_divs = soup.select('div[data-testid="monetization/search-page-top"]')
            
            # Filter out skyscraper divs that are actually just StandardTOA blocks, not real skyscrapers
            filtered_skyscraper_divs = []
            for div in skyscraper_divs:
                # If the div itself is tagged as StandardTOA, skip it
                if div.get("data-testid") == "StandardTOA":
                    log("Skipping skyscraper div misclassified as StandardTOA to avoid double-counting")
                    continue
                filtered_skyscraper_divs.append(div)
            
            skyscraper_divs = filtered_skyscraper_divs
            
            # Handle hybrid SkyscraperTOA elements (classify as Skyscraper by placement)
            skyscraper_toa_divs = soup.select('div[data-testid="SkyscraperTOA"]')
            if skyscraper_toa_divs:
                # Filter these too to avoid double-counting
                filtered_toa_divs = [div for div in skyscraper_toa_divs if div.get("data-testid") != "StandardTOA"]
                if filtered_toa_divs:
                    log(f"Found {len(filtered_toa_divs)} hybrid SkyscraperTOA elements, classifying as Skyscraper")
                    skyscraper_divs.extend(filtered_toa_divs)
            
            # Fallback to previous selectors if needed
            if not skyscraper_divs:
                fallback_divs = soup.select('div[data-testid="monetization/search-skyscraper-top"]')
                # Filter these too
                skyscraper_divs = [div for div in fallback_divs if div.get("data-testid") != "StandardTOA"]
            
            # Additional fallback selectors
            if not skyscraper_divs:
                fallback_divs = soup.select('div.amp-container[data-testid*="skyscraper"]')
                # Filter these too
                skyscraper_divs = [div for div in fallback_divs if div.get("data-testid") != "StandardTOA"]
                
            if not skyscraper_divs:
                fallback_divs = soup.select('div.amp-container')
                # Filter these too
                skyscraper_divs = [div for div in fallback_divs if div.get("data-testid") != "StandardTOA"]
                
            log(f"[{ad_type} Ads Found] {len(skyscraper_divs)}")
            
            for div in skyscraper_divs:
                # Store the raw HTML for image capture
                raw_html = str(div)
                
                # Try to use the extractor first
                ad = extractor.extract(raw_html)
                
                # If extractor failed, create a basic ad structure
                if not ad:
                    ad = {
                        'type': 'Skyscraper',
                        # 'html': raw_html  # Removed to reduce JSON size
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
                
                # Don't include the raw HTML in the results
                # ad['html'] = raw_html  # Removed to reduce JSON size
                results.append(ad)
                
        # For CuratedCarousel ads
        elif ad_type == "CuratedCarousel":
            # Look for carousel ads with multiple selectors
            carousel_divs = soup.select('div.CuratedCarousel.py-32.bg-accent-more-subtle') or \
                          soup.select('div.CuratedCarousel') or \
                          soup.select('div[class*="Carousel"]') or \
                          soup.select('div[data-testid*="carousel"]')
            
            log(f"[{ad_type} Ads Found] {len(carousel_divs)}")
            
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


if __name__ == "__main__":
    log(">>> __main__ harness starting")
    html = get_rendered_html("https://www.kroger.com/search?query=milk", keep_open=False)
    log(f">>> HTML length: {len(html)}")
