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

# Add project root to path for imports like browser_lock
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

import re
import json
import time
import argparse
import urllib.request
import urllib.error
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from playwright.sync_api import sync_playwright, Page, BrowserContext
from browser_lock import single_browser_lock, FileLock


def direct_download_image(url: str, dest_path: str, retries: int = 3) -> bool:
    """
    Last resort: direct download using urllib without browser context.
    Returns True on success.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Referer": "https://www.kroger.com/",
    }
    
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    with open(dest_path, 'wb') as f:
                        f.write(response.read())
                    return True
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            print(f"Direct download attempt {attempt+1}/{retries} failed: {e}")
            time.sleep(1)
    return False


def download_image_with_context(
    context: BrowserContext,
    url: str,
    dest_path: str,
    referer: Optional[str] = None,
    retries: int = 3,
    backoff_s: float = 0.8,
) -> bool:
    """
    Fetches image bytes using Playwright's context-bound HTTP client.
    Preserves cookies/session and sets expected headers. Returns True on success.
    """
    headers: Dict[str, str] = {
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Fetch-Dest": "image",
        "Sec-Fetch-Mode": "no-cors",
        "Sec-Fetch-Site": "same-site",
    }
    # Try to reuse the same UA the context was created with (best-effort)
    try:
        ua = context._impl_obj._options.get("userAgent")
    except Exception:
        ua = None
    if ua:
        headers["User-Agent"] = ua
    if referer:
        headers["Referer"] = referer

    current = url
    for attempt in range(1, retries + 1):
        try:
            resp = context.request.get(current, headers=headers, timeout=15000, fail_on_status=False)
            # Follow a single redirect chain
            if resp.status in (301, 302, 303, 307, 308):
                loc = resp.headers.get("location")
                if loc:
                    current = loc
                    time.sleep(backoff_s * attempt)
                    continue
            if 200 <= resp.status < 300:
                with open(dest_path, "wb") as f:
                    f.write(resp.body())
                return True
        except Exception:
            pass
        time.sleep(backoff_s * attempt)
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

    # Priority 2: derive from --output path (handles .../output/<client>/runs/<ts>)
    try:
        outp = os.path.normpath(args.output or '')
        if outp:
            base = os.path.basename(outp)
            parent = os.path.basename(os.path.dirname(outp))
            # .../output/<client>/runs/<ts>
            if parent == 'runs':
                client = os.path.basename(os.path.dirname(os.path.dirname(outp)))
                if client and client != 'output':
                    return _sanitize(client)
            # .../output/<client>
            gp = os.path.basename(os.path.dirname(outp))
            if gp == 'output' and base and base != 'output':
                return _sanitize(base)
    except Exception:
        pass

    # Priority 3: infer from first result source_file
    try:
        if image_urls:
            sf = image_urls[0].get('source_file') or ''
            if sf:
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
    for result in (data.get("results") or []):
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
            # Compare full path or basename
            if not (src == html_file_norm or os.path.basename(src) == os.path.basename(html_file_norm)):
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

            image_urls.append({
                "url": image_url,
                "keyword": keyword,
                "search_term": search_term,
                "clean_search_term": clean_search_term,
                "alt_text": ad.get("message", "") or "",
                "source_file": result.get("source_file", ""),
                "ad_type": ad_type_raw,
                "id": image_url.split('/')[-1].split('.')[0] if '/' in image_url else None
            })

    return image_urls


# ----------------------------
# Screenshot
# ----------------------------

def screenshot_img_element(page: Page, output_path: str) -> bool:
    """
    Try to screenshot only the <img> element on the page.
    Returns True on success.
    """
    try:
        img = page.query_selector("img")
        if not img:
            # Try waiting briefly for late image attach
            page.wait_for_selector("img", state="visible", timeout=5000)
            img = page.query_selector("img")
        if not img:
            return False

        # Take element screenshot
        img.screenshot(path=output_path)
        print(f"✅ Element screenshot saved: {output_path}")
        return True
    except Exception as e:
        print(f"⚠️ Element screenshot failed, will try fallback: {e}")
        return False


def process_images(
    image_urls: List[Dict[str, Any]],
    output_dir: str,
    client: Optional[str] = None,
    headless: bool = False,
    fixed_timestamp: Optional[str] = None,
    bypass_locks: bool = False,
    browser_lock_timeout: int = 600,
    args = None,
) -> None:
    """
    Process image URLs and take screenshots.
    Will:
    - Create per-ad-type folders under output/<client> (or output/)
    - For each URL, navigate and capture a screenshot
      * If the document is an image (Content-Type: image/*), capture full-page
      * Else, try to capture the <img> element; fall back to full-page
    """
    if not image_urls:
        print("❌ No image URLs to process")
        return

    # Base output root
    base_dir = os.path.join(output_dir, client) if client else output_dir

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
                        channel="chrome",
                        args=["--disable-http2"],
                    )
                    page = context.new_page()
                else:
                    browser = p.chromium.launch(headless=headless, args=["--disable-http2"])
                    context = browser.new_context(
                        viewport={"width": 1280, "height": 720},
                        ignore_https_errors=True,
                        extra_http_headers={
                            "Referer": "https://www.kroger.com/",
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                        },
                        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    )
                    page = context.new_page()
                try:
                    context.set_default_navigation_timeout(45000)
                except Exception:
                    pass
                
                # Check if we have cookies for kroger.com
                try:
                    cookies = context.cookies("https://www.kroger.com")
                    print(f"Cookies for kroger.com: {len(cookies)}")
                    if len(cookies) == 0:
                        print("⚠️ No Kroger cookies found - image downloads may fail!")
                except Exception as e:
                    print(f"Cookie check failed: {e}")

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

                    # Legacy-safe file type prefix
                    ad_type_raw = image_info.get("ad_type") or "toa"
                    file_type = legacy_type_token(ad_type_raw)

                    # Filename and target dir (legacy prefixes preserved)
                    filename = f"{file_type}_{clean_search_term}_{timestamp}_{i+1}.png"
                    target_dir = _choose_dir(file_type)
                    output_path = os.path.join(target_dir, filename)

                    # Navigate and screenshot
                    try:
                        print("🌐 Downloading image")
                        # Prefer direct HTTP fetch tied to the browser context (avoids h2 flakiness)
                        referer = "https://www.kroger.com/"
                        ok = download_image_with_context(
                            context=page.context,
                            url=image_url,
                            dest_path=output_path,
                            referer=referer,
                            retries=3,
                            backoff_s=0.8,
                        )
                        
                        if ok:
                            print(f"✅ Image downloaded successfully to: {output_path}")
                        else:
                            # Second attempt: try rendering in a tab (some CDNs require it)
                            print("⚠️ Context download failed, trying browser fallback...")
                            try:
                                # A slightly softer wait avoids h2 reset loops
                                page.goto(image_url, wait_until="domcontentloaded", timeout=20000)
                                page.wait_for_timeout(400)
                                page.screenshot(path=output_path, full_page=False)
                                print(f"✅ Fallback screenshot saved to: {output_path}")
                                ok = True
                            except Exception as e:
                                print(f"❌ Navigation/screenshot fallback error: {e}")
                                # Last resort: direct download without browser context
                                print("⚠️ Browser fallback failed, trying direct download...")
                                ok = direct_download_image(image_url, output_path, retries=3)
                                if ok:
                                    print(f"✅ Direct download successful: {output_path}")
                                else:
                                    print(f"❌ All download methods failed for: {image_url}")
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
                            channel="chrome",
                            args=["--disable-http2"],
                        )
                        page = context.new_page()
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
                            extra_http_headers={
                                "Referer": "https://www.kroger.com/",
                                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                            },
                            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        )
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

                        # Legacy-safe file type prefix
                        ad_type_raw = image_info.get("ad_type") or "toa"
                        file_type = legacy_type_token(ad_type_raw)

                        # Filename and target dir (legacy prefixes preserved)
                        filename = f"{file_type}_{clean_search_term}_{timestamp}_{i+1}.png"
                        target_dir = _choose_dir(file_type)
                        output_path = os.path.join(target_dir, filename)

                        # Navigate and screenshot
                        try:
                            print("🌐 Downloading image")
                            # Prefer direct HTTP fetch tied to the browser context (avoids h2 flakiness)
                            referer = "https://www.kroger.com/"
                            ok = download_image_with_context(
                                context=page.context,
                                url=image_url,
                                dest_path=output_path,
                                referer=referer,
                                retries=3,
                                backoff_s=0.8,
                            )
                            
                            if ok:
                                print(f"✅ Image downloaded successfully to: {output_path}")
                            else:
                                # Second attempt: try rendering in a tab (some CDNs require it)
                                print("⚠️ Context download failed, trying browser fallback...")
                                try:
                                    # A slightly softer wait avoids h2 reset loops
                                    page.goto(image_url, wait_until="domcontentloaded", timeout=20000)
                                    page.wait_for_timeout(400)
                                    page.screenshot(path=output_path, full_page=False)
                                    print(f"✅ Fallback screenshot saved to: {output_path}")
                                    ok = True
                                except Exception as e:
                                    print(f"❌ Navigation/screenshot fallback error: {e}")
                                    # Last resort: direct download without browser context
                                    print("⚠️ Browser fallback failed, trying direct download...")
                                    ok = direct_download_image(image_url, output_path, retries=3)
                                    if ok:
                                        print(f"✅ Direct download successful: {output_path}")
                                    else:
                                        print(f"❌ All download methods failed for: {image_url}")
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
        process_images(
            image_urls=image_urls,
            output_dir=args.output,
            client=args.client,
            headless=args.headless,
            fixed_timestamp=fixed_ts,
            bypass_locks=args.no_lock,
            browser_lock_timeout=args.browser_lock_timeout,
            args=args,
        )
    else:
        with FileLock(path=client_lock_path, timeout=900):
            print("✅ Acquired per-client queue")
            process_images(
                image_urls=image_urls,
                output_dir=args.output,
                client=args.client,
                headless=args.headless,
                fixed_timestamp=fixed_ts,
                bypass_locks=False,
                browser_lock_timeout=args.browser_lock_timeout,
                args=args,
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())