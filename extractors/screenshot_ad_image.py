#!/usr/bin/env python3
"""
Screenshot Ad Images

This script extracts image URLs from ad JSON files, opens them in a browser,
and takes a precise screenshot of the image. It handles:
- Direct image URLs (Content-Type: image/*) → full-page screenshot
- HTML docs with <img> → element screenshot of the <img> only

Supported ad types: TOA, Skyscraper, Carousel, etc. (anything with image_url)
"""

import os
import sys
import json
import argparse
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse, urljoin
import urllib.request
import urllib.error

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from filename_utils import generate_ad_filename
from extractors.ocr_brand_detector import detect_brands_from_image

from playwright.sync_api import sync_playwright, BrowserContext
from browser_lock import single_browser_lock, FileLock
import pathlib
# Real browser user agent
REAL_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# Headers that make requests look like real browser image fetches
DEFAULT_HEADERS = {
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    # Sec-Fetch headers removed - servers compute these; mismatches can trigger 403/redirects
}


def infer_retailer_from_output(output_dir: str) -> str:
    """Infer retailer from output directory path (output/<retailer>/...)."""
    parts = os.path.normpath(output_dir).split(os.sep)
    try:
        idx = parts.index("output")
        return parts[idx + 1]
    except Exception:
        return ""


def retailer_homepage(retailer: str) -> str:
    """Return homepage URL for the given retailer."""
    return {
        "kroger": "https://www.kroger.com/",
        "amazon": "https://www.amazon.com/",
        "instacart": "https://www.instacart.com/",
        "walmart": "https://www.walmart.com/",
    }.get(retailer, "about:blank")


def load_srp_url(run_json_path: str) -> str:
    """Load the SRP URL from the run JSON to use as referer and for cookie seeding."""
    try:
        data = json.loads(pathlib.Path(run_json_path).read_text())
        # Try common field names (prioritize explicit url fields)
        for k in ("url", "srp_url", "source_url", "page_url"):
            val = data.get(k)
            if isinstance(val, str) and val.strip():
                return val
    except Exception as e:
        print(f"[warn] Could not load SRP URL from JSON: {e}")
    return ""


def direct_download_image(url: str, dest_path: str, referer: str, retries: int = 3) -> bool:
    """
    Last resort: direct download using urllib without browser context.
    Returns True on success.
    """
    headers = {
        "User-Agent": REAL_UA,
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Referer": referer or "https://www.kroger.com/",
    }
    
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status == 200:
                    with open(dest_path, 'wb') as f:
                        f.write(response.read())
                    return True
                print(f"[urllib] HTTP {response.status}")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            print(f"[urllib] attempt {attempt+1}/{retries} failed: {e}")
            time.sleep(1.0 + attempt)
    return False


def download_image_with_context(
    context: BrowserContext,
    url: str,
    dest_path: str,
    referer: Optional[str] = None,
    retries: int = 3,
    backoff_s: float = 1.0,
) -> bool:
    """
    Fetches image bytes using Playwright's context-bound HTTP client.
    Preserves cookies/session and sets expected headers. Returns True on success.
    """
    headers: Dict[str, str] = {
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        # Keep Sec-Fetch headers out (server sets them). If you insist, use same-origin.
    }
    if referer:
        headers["Referer"] = referer
    # Always send a real UA
    headers["User-Agent"] = REAL_UA

    current = url
    for attempt in range(1, retries + 1):
        try:
            print(f"[ctx] attempt {attempt}/{retries}: {current[:80]}...")
            resp = context.request.get(current, headers=headers, timeout=15000, fail_on_status=False)  # Reduced to 15s
            if resp.status in (301, 302, 303, 307, 308):
                loc = resp.headers.get("location")
                if loc:
                    current = urljoin(current, loc)  # Handle relative redirects
                    print(f"[ctx] redirect {resp.status} -> {current}")
                    time.sleep(backoff_s)
                    continue
            print(f"[ctx] status {resp.status} for {current[:80]}")
            if 200 <= resp.status < 300:
                with open(dest_path, "wb") as f:
                    f.write(resp.body())
                print(f"[ctx] ✅ Downloaded {len(resp.body())} bytes")
                return True
            else:
                print(f"[ctx] ❌ HTTP {resp.status} - not retrying")
                return False  # Don't retry on 4xx/5xx errors
        except Exception as e:
            print(f"[ctx] ⚠️ attempt {attempt} failed: {type(e).__name__}: {str(e)[:100]}")
            if attempt >= retries:
                return False
        time.sleep(backoff_s)  # Fixed delay instead of exponential
    return False


# ----------------------------
# Helpers
# ----------------------------

def legacy_type_token(ad_type: str) -> str:
    t = (ad_type or "").lower()
    if "skyscraper" in t:
        return "skyscraper"
    if "carousel" in t:
        return "carousel"
    # default legacy token
    return "toa"


def _sanitize(name: str) -> str:
    name = name or ''
    return ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in name).strip('_')


def _derive_client(args: argparse.Namespace, image_urls: List[Dict[str, Any]]) -> str:
    # Priority 1: explicit --client
    if args.client:
        return _sanitize(args.client)

    # Priority 2: derive from --output path
    # Handles both old (.../output/<client>) and new (.../output/<retailer>/<client>) layouts
    try:
        outp = os.path.normpath(args.output or '')
        if outp:
            parts = outp.split(os.sep)
            try:
                idx = parts.index("output")
                # New layout: output/<retailer>/<client>/...
                if idx + 2 < len(parts) and parts[idx + 1] not in ('runs', ''):
                    # Check if parts[idx+1] looks like a retailer (kroger, walmart, etc.)
                    potential_retailer = parts[idx + 1].lower()
                    known_retailers = {'kroger', 'walmart', 'amazon', 'instacart', 'target', 'albertsons'}
                    if potential_retailer in known_retailers:
                        client = parts[idx + 2]
                        if client and client not in ('runs', 'output', ''):
                            return _sanitize(client)
                # Old layout: output/<client>/...
                if idx + 1 < len(parts):
                    client = parts[idx + 1]
                    if client and client not in ('runs', 'output', ''):
                        return _sanitize(client)
            except ValueError:
                pass
            
            # Fallback: basename logic for runs/ paths
            base = os.path.basename(outp)
            parent = os.path.basename(os.path.dirname(outp))
            if parent == 'runs':
                client = os.path.basename(os.path.dirname(os.path.dirname(outp)))
                if client and client != 'output':
                    return _sanitize(client)
    except Exception:
        pass

    # Priority 3: infer from first result source_file
    try:
        if image_urls:
            sf = image_urls[0].get('source_file') or ''
            if sf:
                # Try new layout first
                parts = os.path.normpath(sf).split(os.sep)
                try:
                    idx = parts.index("output")
                    known_retailers = {'kroger', 'walmart', 'amazon', 'instacart', 'target', 'albertsons'}
                    if idx + 2 < len(parts) and parts[idx + 1].lower() in known_retailers:
                        client = parts[idx + 2]
                        if client and client not in ('runs', 'output', ''):
                            return _sanitize(client)
                except ValueError:
                    pass
                # Fallback
                cand = os.path.basename(os.path.dirname(os.path.normpath(sf)))
                if cand and cand != 'output':
                    return _sanitize(cand)
    except Exception:
        pass

    return 'default'


# ----------------------------
# Extraction
# ----------------------------

def extract_image_urls_from_json(
    json_file: str,
    html_file: Optional[str] = None,
    time_window_minutes: int = 10,
    max_per_type: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Extract image URLs from an ad JSON file.

    - If html_file is provided, only results from that HTML are used.
      In that mode, optionally cap images per ad type via max_per_type.
      Time window is skipped when html_file is provided.
    - If html_file is not provided, only results newer than (now - time_window) are used.

    Returns a list of dicts: {
        "url", "keyword", "search_term", "clean_search_term",
        "alt_text", "source_file", "ad_type", "id"
    }
    """
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Failed to read JSON: {e}")
        return []

    image_urls: List[Dict[str, Any]] = []
    seen_urls_by_search_term: Dict[str, set] = {}

    # Prepare the time cutoff only if not filtering by a specific HTML file
    cutoff_time: Optional[datetime] = None
    if not html_file:
        cutoff_time = datetime.now() - timedelta(minutes=time_window_minutes)
        print(f"🕒 Processing results newer than {cutoff_time:%Y-%m-%d %H:%M:%S} "
              f"(within {time_window_minutes} minutes)")

    # If filtering a specific HTML file, enforce a per-type cap across the WHOLE file
    per_type_counts: Optional[Dict[str, int]] = {} if (html_file and max_per_type is not None) else None

    def _normalize_path(p: str) -> str:
        try:
            return os.path.normpath(p or '')
        except Exception:
            return p or ''

    html_file_norm = _normalize_path(html_file) if html_file else None

    # Walk results
    results_iter = data.get("results") or []
    if not results_iter:
        ads_top = data.get("ads") or []
        if isinstance(ads_top, list) and ads_top:
            pseudo_result = {
                "timestamp": data.get("timestamp", ""),
                "source_file": html_file or data.get("source_file", ""),
                "search_term": data.get("search_term", data.get("keyword", "unknown")),
                "keyword": data.get("keyword", "unknown"),
                "ads": ads_top,
            }
            results_iter = [pseudo_result]

    for result in results_iter:
        # Time window gating (only if not using a specific html target)
        if cutoff_time is not None:
            ts_str = result.get("timestamp", "")
            if ts_str:
                try:
                    ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                    if ts < cutoff_time:
                        print(f"⏭️ Skipping old result from {ts_str}")
                        continue
                    else:
                        print(f"✅ Using recent result from {ts_str}")
                except ValueError:
                    print(f"⚠️ Unparseable timestamp '{ts_str}' — keeping the result")

        # If html_file is specified, only accept matching source_file
        if html_file_norm:
            src = _normalize_path(result.get("source_file", ""))
            # Compare full path or basename (case-insensitive for cross-platform compatibility)
            if not (src.lower() == html_file_norm.lower() or 
                    os.path.basename(src).lower() == os.path.basename(html_file_norm).lower()):
                continue

        search_term = result.get("search_term", result.get("keyword", "unknown"))
        if search_term not in seen_urls_by_search_term:
            seen_urls_by_search_term[search_term] = set()

        for ad in (result.get("ads") or []):
            if "image_url" not in ad:
                continue

            image_url = ad["image_url"]
            if image_url.startswith('/'):
                # Kroger relative → absolute
                image_url = f"https://www.kroger.com{image_url}"

            # Dedup within search term scope
            if image_url in seen_urls_by_search_term[search_term]:
                continue
            seen_urls_by_search_term[search_term].add(image_url)

            # Per-type cap when html_file is provided
            ad_type_raw = ad.get("type", "TOA")
            ad_type_key = (ad_type_raw or "TOA").lower()
            if per_type_counts is not None and max_per_type is not None:
                cnt = per_type_counts.get(ad_type_key, 0)
                if cnt >= max_per_type:
                    continue
                per_type_counts[ad_type_key] = cnt + 1

            keyword = result.get("keyword", "unknown")
            clean_search_term = (search_term or keyword).replace(" ", "_").lower()

            # Handle advertisers (can be array or single string for backwards compatibility)
            advertisers = ad.get("advertisers")
            if not advertisers:
                # Fallback to old 'advertiser' field for backwards compatibility
                advertiser_single = ad.get("advertiser")
                advertisers = [advertiser_single] if advertiser_single else None
            
            image_urls.append({
                "url": image_url,
                "keyword": keyword,
                "search_term": search_term,
                "clean_search_term": clean_search_term,
                "alt_text": ad.get("message", "") or "",
                "source_file": result.get("source_file", ""),
                "ad_type": ad_type_raw,
                "position": ad.get("position"),  # Include position for matching
                "advertisers": advertisers,  # Array of brand names (can be None)
                "retailer": data.get("retailer", "kroger"),  # Retailer name from top-level JSON
                "id": image_url.split('/')[-1].split('.')[0] if '/' in image_url else None
            })

    return image_urls


# ----------------------------
# JSON Update
# ----------------------------

def update_json_with_image_paths(json_file: str, image_urls: List[Dict[str, Any]]):
    """
    Update the JSON file with saved image paths.
    Maps each ad to its corresponding image file path.
    """
    print(f"\n💾 Updating JSON with image paths: {json_file}")
    
    try:
        with open(json_file, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Failed to read JSON: {e}")
        return
    
    # Build a mapping of ad info to saved paths
    # image_urls contains: ad_type, position, url, saved_image_path
    path_map = {}
    for img_info in image_urls:
        if 'saved_image_path' not in img_info:
            continue
        
        ad_type = img_info.get('ad_type', 'TOA')
        position = img_info.get('position')
        image_url = img_info.get('url', '')
        saved_path = img_info['saved_image_path']
        
        # Create keys to match ads (type + position + url)
        key_full = (ad_type, position, image_url)
        path_map[key_full] = saved_path

        # Also support Kroger-style relative URLs stored in JSON (e.g., /content/...) 
        if isinstance(image_url, str):
            idx = image_url.find("/content/")
            if idx != -1:
                rel_url = image_url[idx:]
                key_rel = (ad_type, position, rel_url)
                if key_rel not in path_map:
                    path_map[key_rel] = saved_path
    
    if not path_map:
        print("⚠️ No saved paths to update")
        return
    
    print(f"📋 Found {len(path_map)} image paths to save")
    
    # Update ads in JSON
    updated_count = 0
    for result in data.get('results', []):
        for ad in result.get('ads', []):
            ad_type = ad.get('type')
            position = ad.get('position')
            image_url = ad.get('image_url', '')
            
            # Try to match this ad
            key = (ad_type, position, image_url)
            if key in path_map:
                saved_path = path_map[key]
                
                # Use canonical 'image_path' field (not type-specific fields)
                field_name = 'image_path'
                
                # Save relative path (from output/ directory)
                # Convert absolute path to relative: /path/to/output/kroger/client/TOA/file.png -> TOA/file.png
                try:
                    # Extract just the last 2-3 parts (ad_type/filename or client/ad_type/filename)
                    parts = saved_path.split(os.sep)
                    if 'TOA' in parts:
                        idx = parts.index('TOA')
                        relative_path = os.sep.join(parts[idx:])
                    elif 'Skyscraper' in parts:
                        idx = parts.index('Skyscraper')
                        relative_path = os.sep.join(parts[idx:])
                    elif 'Carousel' in parts:
                        idx = parts.index('Carousel')
                        relative_path = os.sep.join(parts[idx:])
                    else:
                        relative_path = os.path.basename(saved_path)
                except Exception:
                    relative_path = os.path.basename(saved_path)
                
                ad[field_name] = relative_path
                updated_count += 1
                print(f"  ✓ Updated {ad_type} ad (position {position}): {field_name} = {relative_path}")

    top_ads = data.get('ads')
    if isinstance(top_ads, list):
        for ad in top_ads:
            ad_type = ad.get('type')
            position = ad.get('position')
            image_url = ad.get('image_url', '')
            
            key = (ad_type, position, image_url)
            if key in path_map:
                saved_path = path_map[key]
                
                field_name = 'image_path'
                
                try:
                    parts = saved_path.split(os.sep)
                    if 'TOA' in parts:
                        idx = parts.index('TOA')
                        relative_path = os.sep.join(parts[idx:])
                    elif 'Skyscraper' in parts:
                        idx = parts.index('Skyscraper')
                        relative_path = os.sep.join(parts[idx:])
                    elif 'Carousel' in parts:
                        idx = parts.index('Carousel')
                        relative_path = os.sep.join(parts[idx:])
                    else:
                        relative_path = os.path.basename(saved_path)
                except Exception:
                    relative_path = os.path.basename(saved_path)
                
                ad[field_name] = relative_path
                updated_count += 1
                print(f"  ✓ Updated {ad_type} ad (position {position}): {field_name} = {relative_path}")
    
    # Save updated JSON
    try:
        with open(json_file, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"✅ JSON updated successfully ({updated_count} ads)")
    except Exception as e:
        print(f"❌ Failed to write JSON: {e}")


# ----------------------------
# Screenshot / Process
# ----------------------------

def process_images(
    image_urls: List[Dict[str, Any]],
    output_dir: str,
    client: Optional[str] = None,
    headless: bool = False,
    fixed_timestamp: Optional[str] = None,
    bypass_locks: bool = False,
    browser_lock_timeout: int = 600,
    args = None,
) -> int:
    """
    Process image URLs and take screenshots.
    Will:
    - Create per-ad-type folders under output/<client> (or output/)
    - For each URL, navigate and capture a screenshot
      * If the document is an image (Content-Type: image/*), capture full-page
      * Else, try to capture the <img> element; fall back to full-page
    
    Returns: Number of images successfully saved
    """
    if not image_urls:
        print("❌ No image URLs to process")
        return 0
    
    saved_count = 0

    # Base output root
    # If output_dir already ends with the client name, don't add it again
    if client and not output_dir.endswith(os.path.sep + client):
        base_dir = os.path.join(output_dir, client)
    else:
        base_dir = output_dir

    # Per-type folders
    toa_dir = os.path.join(base_dir, "TOA")
    skyscraper_dir = os.path.join(base_dir, "Skyscraper")
    carousel_dir = os.path.join(base_dir, "Carousel")
    os.makedirs(toa_dir, exist_ok=True)
    os.makedirs(skyscraper_dir, exist_ok=True)
    os.makedirs(carousel_dir, exist_ok=True)

    # Helper to map legacy token to directory
    def _choose_dir(file_type: str) -> str:
        if file_type == "skyscraper":
            return skyscraper_dir
        if file_type == "carousel":
            return carousel_dir
        return toa_dir

    # Compute SRP URL once for all images
    srp_url = load_srp_url(args.json) or ""
    print(f"[session] srp_url={srp_url or '<none>'}")
    
    # Infer retailer from output directory for fallback homepage
    retailer = infer_retailer_from_output(output_dir)
    print(f"[session] retailer={retailer or '<unknown>'}")
    
    if bypass_locks:
        print("⚠️ Bypassing browser lock as requested")
        # Run without the browser lock
        with sync_playwright() as p:
            browser = None
            context = None
            page = None
            try:
                print(f"Profile dir: {args.profile_dir or '<none>'}")
                
                if args.profile_dir and os.path.isdir(args.profile_dir):
                    # Reuse cookies/session exactly like the scraper
                    print(f"🔑 Using persistent profile: {args.profile_dir}")
                    context = p.chromium.launch_persistent_context(
                        user_data_dir=args.profile_dir,
                        headless=headless,
                        viewport={"width": 1440, "height": 900},
                        user_agent=REAL_UA,
                        ignore_https_errors=True,
                        args=[
                            "--disable-dev-shm-usage",
                            "--no-sandbox",
                            "--disable-blink-features=AutomationControlled",
                            "--disable-features=SameSiteByDefaultCookies,CookiesWithoutSameSiteMustBeSecure",
                            "--no-first-run",
                            "--no-default-browser-check",
                            "--disable-session-crashed-bubble",
                            "--disable-renderer-backgrounding",
                            "--disable-backgrounding-occluded-windows",
                            # Focus prevention - don't steal focus from user's active window
                            "--no-startup-window",
                            "--silent-launch",
                            "--disable-focus-on-load",
                            "--noerrdialogs",
                        ],
                    )
                    page = context.pages[0] if context.pages else context.new_page()
                    page.set_default_timeout(15000)
                    page.set_default_navigation_timeout(45000)
                    
                    # Seed cookies robustly - try SRP URL first, then retailer homepage
                    seed_candidates = [srp_url] if srp_url else []
                    seed_candidates.append(retailer_homepage(retailer))
                    
                    # Optional override for devs
                    override_seed = os.environ.get("SEED_URL_OVERRIDE")
                    if override_seed:
                        seed_candidates.insert(0, override_seed)
                    
                    if not srp_url:
                        print("⚠️ No SRP URL found in JSON; seeding cookies with retailer homepage")
                    else:
                        print(f"Seeding cookies from SRP URL: {srp_url}")
                    
                    cookies_ok = False
                    for seed in seed_candidates:
                        try:
                            print(f"[session] Seeding cookies from: {seed}")
                            page.goto(seed, wait_until="commit", timeout=60000)  # commit is more reliable
                            page.wait_for_timeout(1200)
                            cookies = context.cookies("https://www.kroger.com")
                            print(f"[cookies] kroger.com={len(cookies)} -> {[c['name'] for c in cookies[:6]]}")
                            if len(cookies) > 0:
                                cookies_ok = True
                                break
                        except Exception as e:
                            print(f"[warn] Seed failed for {seed}: {e}")
                    
                    if not cookies_ok:
                        print("⚠️ No cookies after seeding attempts. Image downloads may hang.")
                    
                    # Set headers for all subsequent requests
                    context.set_extra_http_headers({
                        **DEFAULT_HEADERS,
                        "Referer": srp_url or "https://www.kroger.com/",
                        "User-Agent": REAL_UA
                    })
                else:
                    browser = p.chromium.launch(headless=headless, args=["--disable-http2"])
                    context = browser.new_context(
                        viewport={"width": 1280, "height": 720},
                        ignore_https_errors=True,
                        user_agent=REAL_UA,
                    )
                    
                    # Seed cookies robustly - try SRP URL first, then retailer homepage
                    seed_candidates = [srp_url] if srp_url else []
                    seed_candidates.append(retailer_homepage(retailer))
                    
                    # Optional override for devs
                    override_seed = os.environ.get("SEED_URL_OVERRIDE")
                    if override_seed:
                        seed_candidates.insert(0, override_seed)
                    
                    if not srp_url:
                        print("⚠️ No SRP URL found in JSON; seeding cookies with retailer homepage")
                    else:
                        print(f"Seeding cookies from SRP URL: {srp_url}")
                    
                    cookies_ok = False
                    tmp = context.new_page()
                    for seed in seed_candidates:
                        try:
                            print(f"[session] Seeding cookies from: {seed}")
                            tmp.goto(seed, wait_until="commit", timeout=60000)  # commit is more reliable
                            tmp.wait_for_timeout(1200)
                            cookies = context.cookies("https://www.kroger.com")
                            print(f"[cookies] kroger.com={len(cookies)} -> {[c['name'] for c in cookies[:6]]}")
                            if len(cookies) > 0:
                                cookies_ok = True
                                break
                        except Exception as e:
                            print(f"[warn] Seed failed for {seed}: {e}")
                    tmp.close()
                    
                    if not cookies_ok:
                        print("⚠️ No cookies after seeding attempts. Image downloads may hang.")
                    
                    # Set headers for ALL subsequent requests
                    context.set_extra_http_headers({
                        **DEFAULT_HEADERS,
                        "Referer": srp_url or "https://www.kroger.com/",
                        "User-Agent": REAL_UA
                    })
                    
                    page = context.new_page()
                try:
                    context.set_default_navigation_timeout(45000)
                except Exception:
                    pass

                # Process each image URL
                for i, image_info in enumerate(image_urls):
                    image_url = image_info["url"]
                    keyword = image_info["keyword"]
                    alt_text = image_info["alt_text"]

                    print(f"\n📷 Processing image {i+1}/{len(image_urls)}")
                    print(f"🔗 URL: {image_url}")
                    print(f"🔑 Keyword: {keyword}")
                    if alt_text:
                        print(f"📝 Alt text: {alt_text}")

                    # Clean search term for filename
                    clean_search_term = image_info.get("clean_search_term", keyword.replace(" ", "_").lower())

                    # Timestamp (prefer fixed)
                    timestamp = fixed_timestamp or datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

                    # Get ad metadata
                    ad_type_raw = image_info.get("ad_type") or "toa"
                    file_type = legacy_type_token(ad_type_raw)
                    retailer = image_info.get("retailer", "kroger")
                    advertisers = image_info.get("advertisers") or ["unknown"]
                    
                    # Generate filename using new taxonomy
                    # Pass advertisers as list (can be single or multiple brands)
                    filename = generate_ad_filename(
                        retailer=retailer,
                        ad_type=ad_type_raw,
                        client=client,
                        search_term=keyword,
                        timestamp=timestamp,
                        index=i+1,
                        extension='png',
                        advertiser=advertisers  # Pass as list
                    )
                    target_dir = _choose_dir(file_type)
                    output_path = os.path.join(target_dir, filename)

                    # Navigate and screenshot
                    try:
                        print("🌐 Downloading image")
                        ok = False
                        
                        # Fast path: try context.request once with short timeout
                        try:
                            resp = page.context.request.get(image_url, timeout=5000)
                            if resp.ok:
                                with open(output_path, "wb") as f:
                                    f.write(resp.body())
                                print(f"✅ [fast] Image downloaded via context.request")
                                saved_count += 1
                                ok = True
                        except Exception as e:
                            print(f"[fast] context.request failed or timed out: {e}")
                        
                        # Fallback: direct urllib download with proper referer (Kroger blocks browser navigation)
                        if not ok:
                            print("[urllib] Trying direct download with referer...")
                            ok = direct_download_image(image_url, output_path, referer=srp_url or "https://www.kroger.com/", retries=3)
                            if ok:
                                print(f"✅ [urllib] Direct download successful")
                                saved_count += 1
                            else:
                                print(f"❌ All download methods failed for: {image_url}")
                        
                        # Save the output path for JSON update (do this FIRST, before OCR)
                        if ok and os.path.exists(output_path):
                            image_info['saved_image_path'] = output_path
                            
                            # OCR brand detection for co-branded ads
                            try:
                                print("🔍 Running OCR brand detection...")
                                detected_brands = detect_brands_from_image(output_path)
                                
                                if detected_brands and len(detected_brands) > 1:
                                    print(f"✓ Co-branded ad detected: {' + '.join(detected_brands)}")
                                    
                                    # Update the image_info with detected brands for JSON update
                                    image_info['advertisers'] = detected_brands
                                    
                                    # Regenerate filename with all detected brands
                                    new_filename = generate_ad_filename(
                                        retailer=retailer,
                                        ad_type=ad_type_raw,
                                        client=client,
                                        search_term=keyword,
                                        timestamp=timestamp,
                                        index=i+1,
                                        extension='png',
                                        advertiser=detected_brands  # Use OCR-detected brands
                                    )
                                    new_output_path = os.path.join(target_dir, new_filename)
                                    
                                    # Rename file if different
                                    if new_output_path != output_path:
                                        os.rename(output_path, new_output_path)
                                        print(f"✓ Renamed to: {new_filename}")
                                        output_path = new_output_path
                                        # Update saved path with new filename
                                        image_info['saved_image_path'] = output_path
                                elif detected_brands and len(detected_brands) == 1:
                                    print(f"✓ Single brand confirmed: {detected_brands[0]}")
                                    # Update with single detected brand
                                    image_info['advertisers'] = detected_brands
                            except Exception as ocr_err:
                                print(f"⚠️ OCR detection skipped: {ocr_err}")
                    except Exception as e:
                        print(f"❌ Image download error: {e}")

                    time.sleep(1)

            except Exception as e:
                print(f"❌ Error: {e}")
            finally:
                try:
                    if context:
                        context.close()
                except Exception:
                    pass
                try:
                    if browser:
                        browser.close()
                except Exception:
                    pass

    else:
        # Serialize browser usage across all processes/modes
        with single_browser_lock(timeout=browser_lock_timeout):
            with sync_playwright() as p:
                browser = None
                context = None
                page = None
                try:
                    if args.profile_dir and os.path.isdir(args.profile_dir):
                        # Reuse cookies/session exactly like the scraper
                        print(f"🔑 Using persistent profile: {args.profile_dir}")
                        context = p.chromium.launch_persistent_context(
                            user_data_dir=args.profile_dir,
                            headless=headless,
                            viewport={"width": 1440, "height": 900},
                            user_agent=REAL_UA,
                            ignore_https_errors=True,
                            args=[
                                "--disable-dev-shm-usage",
                                "--no-sandbox",
                                "--disable-blink-features=AutomationControlled",
                                "--disable-features=SameSiteByDefaultCookies,CookiesWithoutSameSiteMustBeSecure",
                                "--no-first-run",
                                "--no-default-browser-check",
                                "--disable-session-crashed-bubble",
                            ],
                        )
                        page = context.pages[0] if context.pages else context.new_page()
                        page.set_default_timeout(15000)
                        page.set_default_navigation_timeout(45000)
                        
                        # Seed cookies robustly - try SRP URL first, then retailer homepage
                        seed_candidates = [srp_url] if srp_url else []
                        seed_candidates.append(retailer_homepage(retailer))
                        
                        # Optional override for devs
                        override_seed = os.environ.get("SEED_URL_OVERRIDE")
                        if override_seed:
                            seed_candidates.insert(0, override_seed)
                        
                        # Check if we already have cookies (persistent profile)
                        existing_cookies = context.cookies(f"https://www.{retailer}.com" if retailer else "https://www.kroger.com")
                        if existing_cookies and len(existing_cookies) > 0:
                            print(f"✅ Using existing cookies from persistent profile ({len(existing_cookies)} cookies)")
                            print(f"[cookies] {retailer or 'kroger'}.com cookies: {[c['name'] for c in existing_cookies[:6]]}")
                            cookies_ok = True
                        else:
                            if not srp_url:
                                print("⚠️ No SRP URL found in JSON; seeding cookies with retailer homepage")
                            else:
                                print(f"Seeding cookies from SRP URL: {srp_url}")
                            
                            cookies_ok = False
                            for seed in seed_candidates:
                                try:
                                    print(f"[session] Seeding cookies from: {seed}")
                                    page.goto(seed, wait_until="commit", timeout=30000)  # Reduced to 30s
                                    page.wait_for_timeout(1200)
                                    cookies = context.cookies(f"https://www.{retailer}.com" if retailer else "https://www.kroger.com")
                                    print(f"[cookies] {retailer or 'kroger'}.com={len(cookies)} -> {[c['name'] for c in cookies[:6]]}")
                                    if len(cookies) > 0:
                                        cookies_ok = True
                                        break
                                except Exception as e:
                                    print(f"[warn] Seed failed for {seed}: {e}")
                        
                        if not cookies_ok:
                            print("⚠️ No cookies after seeding attempts. Image downloads may hang.")
                        
                        # Set headers for all subsequent requests
                        context.set_extra_http_headers({
                            **DEFAULT_HEADERS,
                            "Referer": srp_url or "https://www.kroger.com/",
                            "User-Agent": REAL_UA
                        })
                    else:
                        # Launch browser with stability flags
                        browser = p.chromium.launch(
                            headless=headless,
                            args=["--disable-quic", "--disable-notifications", "--disable-http2"]
                        )

                        # Create a browser context
                        context = browser.new_context(
                            viewport={"width": 1280, "height": 720},
                            ignore_https_errors=True,
                            user_agent=REAL_UA,
                        )
                        
                        # Seed cookies by visiting the SRP page once
                        try:
                            print(f"[session] Seeding cookies from: {srp_url}")
                            tmp = context.new_page()
                            tmp.goto(srp_url, wait_until="domcontentloaded", timeout=45000)
                            tmp.wait_for_timeout(1000)
                            tmp.close()
                            cookies = context.cookies("https://www.kroger.com")
                            print(f"[cookies] kroger.com={len(cookies)} -> {[c['name'] for c in cookies[:5]]}")
                        except Exception as e:
                            print(f"[warn] Could not preload SRP: {e}")
                        
                        # Set headers for ALL subsequent requests
                        context.set_extra_http_headers({
                            **DEFAULT_HEADERS,
                            "Referer": srp_url,
                            "User-Agent": REAL_UA
                        })
                    
                    try:
                        context.set_default_navigation_timeout(45000)
                    except Exception:
                        pass

                    # Create a new page
                    page = context.new_page()

                    # IMPORTANT: all of the per-image work stays inside the loop
                    for i, image_info in enumerate(image_urls):
                        image_url = image_info["url"]
                        keyword = image_info["keyword"]
                        alt_text = image_info["alt_text"]

                        print(f"\n📷 Processing image {i+1}/{len(image_urls)}")
                        print(f"🔗 URL: {image_url}")
                        print(f"🔑 Keyword: {keyword}")
                        if alt_text:
                            print(f"📝 Alt text: {alt_text}")

                        clean_search_term = image_info.get("clean_search_term", keyword.replace(" ", "_").lower())

                        # Timestamp (prefer fixed)
                        timestamp = fixed_timestamp or datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

                        # Get ad metadata
                        ad_type_raw = image_info.get("ad_type") or "toa"
                        file_type = legacy_type_token(ad_type_raw)
                        retailer = image_info.get("retailer", "kroger")
                        advertisers = image_info.get("advertisers") or ["unknown"]
                        
                        # Generate filename using new taxonomy
                        # Pass advertisers as list (can be single or multiple brands)
                        filename = generate_ad_filename(
                            retailer=retailer,
                            ad_type=ad_type_raw,
                            client=client,
                            search_term=keyword,
                            timestamp=timestamp,
                            index=i+1,
                            extension='png',
                            advertiser=advertisers  # Pass as list
                        )
                        target_dir = _choose_dir(file_type)
                        output_path = os.path.join(target_dir, filename)

                        # Navigate and screenshot
                        try:
                            print("🌐 Downloading image")
                            # Prefer direct HTTP fetch tied to the browser context (avoids h2 flakiness)
                            ok = download_image_with_context(
                                context=page.context,
                                url=image_url,
                                dest_path=output_path,
                                referer=srp_url,
                                retries=3,
                                backoff_s=1.0,
                            )
                            
                            if ok:
                                print(f"✅ Image downloaded successfully to: {output_path}")
                                saved_count += 1
                            else:
                                # Second attempt: try rendering in a tab (some CDNs require it)
                                print("⚠️ Context download failed, trying browser fallback...")
                                try:
                                    # Image docs don't reliably fire domcontentloaded; use commit
                                    page.goto(image_url, wait_until="commit", timeout=30000)
                                    page.wait_for_timeout(400)
                                    
                                    # Try to find and screenshot just the img element to avoid black borders
                                    try:
                                        img_element = page.locator("img").first
                                        if img_element:
                                            # Wait for image to load
                                            page.wait_for_load_state("networkidle", timeout=5000)
                                            img_element.screenshot(path=output_path)
                                            print(f"✅ Element screenshot saved to: {output_path}")
                                        else:
                                            # No img element, use full viewport
                                            page.screenshot(path=output_path, full_page=False)
                                            print(f"✅ Viewport screenshot saved to: {output_path}")
                                    except Exception as elem_err:
                                        # Fallback to viewport screenshot
                                        print(f"⚠️ Element screenshot failed ({elem_err}), using viewport")
                                        page.screenshot(path=output_path, full_page=False)
                                        print(f"✅ Fallback screenshot saved to: {output_path}")
                                    
                                    ok = True
                                    saved_count += 1
                                except Exception as e:
                                    print(f"❌ Navigation/screenshot fallback error: {e}")
                                    # Last resort: direct download without browser context
                                    print("⚠️ Browser fallback failed, trying direct download...")
                                    ok = direct_download_image(image_url, output_path, referer=srp_url, retries=3)
                                    if ok:
                                        print(f"✅ Direct download successful: {output_path}")
                                        saved_count += 1
                                    else:
                                        print(f"❌ All download methods failed for: {image_url}")
                            
                            # Save the final output path for JSON update
                            if ok:
                                image_info['saved_image_path'] = output_path
                        except Exception as e:
                            print(f"❌ Image download error: {e}")

                        time.sleep(1)

                except Exception as e:
                    print(f"❌ Error: {e}")
                finally:
                    try:
                        if context:
                            context.close()
                    except Exception:
                        pass
                    try:
                        if browser:
                            browser.close()
                    except Exception:
                        pass
    
    print(f"\n📊 Summary: {saved_count}/{len(image_urls)} images saved successfully")
    
    # Update JSON with saved image paths
    if saved_count > 0:
        try:
            update_json_with_image_paths(args.json, image_urls)
        except Exception as e:
            print(f"⚠️ Failed to update JSON with image paths: {e}")
    
    return saved_count


# ----------------------------
# CLI / Main
# ----------------------------

def main() -> int:
    import sys
    try:
        import playwright
    except Exception:
        playwright = None

    print(f"Runtime: {sys.executable}")
    print(f"Playwright: {getattr(playwright, '__version__', 'unknown')}")
    parser = argparse.ArgumentParser(description="Screenshot ad images from a JSON file")
    parser.add_argument("--json", "-j", required=True, help="Path to ad results JSON")
    parser.add_argument("--html", "-f", help="Path to specific HTML file to process")
    parser.add_argument("--client", "-c", help="Client name (used for output folder)")
    parser.add_argument("--output", "-o", default="output", help="Output directory (default: output)")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    parser.add_argument("--time-window", "-t", type=int, default=10, help="Time window (minutes) when --html is not set")
    parser.add_argument("--timestamp", "-s", help="Timestamp (YYYY-MM-DD_HH-MM-SS) for output filenames")
    parser.add_argument("--allow-batch", action="store_true", help="Allow processing without --html (batch mode)")
    parser.add_argument("--max-per-type", type=int, default=1, help="Cap images per ad type when --html is set")
    parser.add_argument("--no-lock", action="store_true", help="Bypass all locks (use with caution)")
    parser.add_argument("--browser-lock-timeout", type=int, default=600, help="Global browser lock timeout seconds")
    parser.add_argument(
        "--profile-dir",
        default=os.getenv("KROGER_PROFILE_DIR"),
        help="Path to a persistent Chrome/Chromium user data dir (reuse cookies/session)"
    )
    args = parser.parse_args()

    # Safety: require --html unless explicitly allowed
    if not args.html and not args.allow_batch:
        print("❌ Refusing to run without --html. Use --allow-batch to override.")
        return 2

    # Extract
    image_urls = extract_image_urls_from_json(
        json_file=args.json,
        html_file=args.html,
        time_window_minutes=args.time_window,
        max_per_type=(args.max_per_type if args.html else None),
    )

    if not image_urls:
        if args.html:
            print(f"❌ No image URLs found for HTML: {args.html}")
        else:
            print("❌ No image URLs found")
        return 1

    # Determine effective timestamp
    fixed_ts = args.timestamp
    if not fixed_ts and args.html:
        try:
            base = os.path.basename(args.html)
            m = re.search(r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})", base)
            if m:
                fixed_ts = m.group(1)
        except Exception:
            fixed_ts = None

    # Per-client queue lock
    client_for_lock = _derive_client(args, image_urls)
    locks_root = os.path.join(os.environ.get('SCRAPER_HOME', os.getcwd()), 'logs', 'locks')
    os.makedirs(locks_root, exist_ok=True)
    client_lock_path = os.path.join(locks_root, f"{client_for_lock}_image_extraction.lock")

    # image_urls should already be built here
    if not image_urls:
        print("WARN: No image candidates found (TOA/Skyscraper/Carousel = 0).")
        # exit non-zero so GUI treats this as failure and logs once
        return 3

    print(f"INFO: Prepared {len(image_urls)} image tasks.")
    for t in image_urls[:5]:
        print("  -", t.get("ad_type"), t.get("url"))

    print(f"🔒 Queuing for client '{client_for_lock}' at {client_lock_path}")
    if args.no_lock:
        saved = process_images(
            image_urls=image_urls,
            output_dir=args.output,
            client=client_for_lock,  # Use derived client, not args.client
            headless=args.headless,
            fixed_timestamp=fixed_ts,
            bypass_locks=args.no_lock,
            browser_lock_timeout=args.browser_lock_timeout,
            args=args,
        )
    else:
        with FileLock(path=client_lock_path, timeout=900):
            print("✅ Acquired per-client queue")
            saved = process_images(
                image_urls=image_urls,
                output_dir=args.output,
                client=client_for_lock,  # Use derived client, not args.client
                headless=args.headless,
                fixed_timestamp=fixed_ts,
                bypass_locks=False,
                browser_lock_timeout=args.browser_lock_timeout,
                args=args,
            )
    
    if saved == 0:
        print("❌ No images saved; exiting with failure for orchestrator.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())