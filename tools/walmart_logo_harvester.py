#!/usr/bin/env python3
"""
Walmart Brand Logo Harvester

Searches Walmart for a brand, navigates to the brand store page,
and downloads the official brand logo.

Flow:
  1) Search Walmart for brand keyword
  2) Click top product result
  3) On PDP, find brand link
  4) If facet link (/browse?facet=brand:...) → abort (no store)
  5) If store link (/brand/<slug>/<id>) → navigate
  6) Find logo <img alt="...logo">
  7) Download and save to brand_logos/

Can be used standalone or as fallback in logo_scout.py
"""

import os
import sys
import json
import time
import random
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import requests

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
except ImportError:
    print("ERROR: playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)

# Try to import from main scraper
try:
    from walmart_search_and_capture import (
        PROFILE_ENV, BROWSER_UA, HEADERS,
        _launch, _goto_home, _still_px_modal, _solve_px_until_clear,
        _search_url, _wait_for_search_results, _get_proxy_config,
        safe_filename, canonicalize_brand
    )
    SCRAPER_IMPORTS_OK = True
except ImportError:
    SCRAPER_IMPORTS_OK = False
    PROFILE_ENV = "WALMART_PROFILE_DIR"
    BROWSER_UA = {"ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    HEADERS = {"user-agent": BROWSER_UA["ua"]}


# --- Brand Logo DB Helpers ---

def _brand_slug(name: str) -> str:
    """Normalize brand name to slug"""
    import unicodedata
    s = (name or "").strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r'[^a-z0-9]+', '_', s.lower()).strip('_')
    return s


def _norm_brand_for_match(name: str) -> str:
    """Normalize brand names for matching (lowercase, strip punctuation/whitespace).

    This is stricter than display but lenient enough to treat 'Band-Aid',
    'BAND AID', and 'Band Aid Brand Adhesive Bandages' as the same core brand
    while still distinguishing 'Welly' from 'Band Aid'.
    """
    if not name:
        return ""
    s = name.lower()
    # Remove common decorations
    for ch in ["®", "™"]:
        s = s.replace(ch, "")
    s = s.replace("&", "and")
    # Keep only letters/digits
    s = re.sub(r"[^a-z0-9]", "", s)
    return s.strip()


def _timestamp_iso() -> str:
    """ISO timestamp with Z"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_dirs(db_path: str, logos_dir: str):
    """Create directories if needed"""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    os.makedirs(logos_dir, exist_ok=True)


def _load_brand_logo_db(db_path: str) -> dict:
    """Load brand logo database"""
    if os.path.isfile(db_path):
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"brands": {}, "metadata": {"last_updated": None, "total_brands": 0}}
    return {"brands": {}, "metadata": {"last_updated": None, "total_brands": 0}}


def _save_brand_logo_db(db_path: str, db: dict):
    """Save brand logo database with metadata"""
    db["metadata"]["last_updated"] = _timestamp_iso()
    db["metadata"]["total_brands"] = len(db.get("brands", {}))
    
    # Sort brands alphabetically
    if "brands" in db:
        db["brands"] = dict(sorted(db["brands"].items(), key=lambda x: x[0].lower()))
    
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)


def _update_brand_logo_db(
    db_path: str,
    brand: str,
    logo_url: str,
    logo_file: str,
    retailer: str,
    metadata: dict
):
    """Update brand logo database entry"""
    db = _load_brand_logo_db(db_path)
    brands = db.setdefault("brands", {})
    slug = _brand_slug(brand)
    now_iso = _timestamp_iso()
    
    if slug in brands:
        # Update existing
        rec = brands[slug]
        rec["logo_url"] = logo_url
        rec["logo_file"] = logo_file
        rec["last_seen"] = now_iso
        rec["last_updated"] = now_iso
        
        # Union retailers
        retailers = set(rec.get("retailers", []))
        retailers.add(retailer)
        rec["retailers"] = sorted(retailers)
        
        # Merge metadata
        rec.setdefault("metadata", {}).update(metadata)
    else:
        # Create new
        brands[slug] = {
            "logo_file": logo_file,
            "retailers": [retailer],
            "first_seen": now_iso,
            "last_seen": now_iso,
            "last_updated": now_iso,
            "source": "walmart_brand_store",
            "metadata": metadata
        }
    
    _save_brand_logo_db(db_path, db)
    return brands[slug]


def _download_logo(src_url: str, dest_path: str, referer: str, user_agent: str, timeout: int = 25) -> bool:
    """Download logo image to file"""
    try:
        hdrs = {
            "User-Agent": user_agent,
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": referer,
        }
        r = requests.get(src_url, headers=hdrs, timeout=timeout)
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            f.write(r.content)
        return True
    except Exception as e:
        print(f"  Download failed: {e}")
        return False


def _ext_from_url(url: str) -> str:
    """Determine file extension from URL"""
    url = url.split("?")[0].lower()
    if url.endswith(".svg"):
        return ".svg"
    if url.endswith(".png"):
        return ".png"
    if url.endswith(".jpg") or url.endswith(".jpeg"):
        return ".jpg"
    return ".png"


# --- Walmart Scraper Fallbacks (if imports failed) ---

if not SCRAPER_IMPORTS_OK:
    def safe_filename(s: str) -> str:
        return re.sub(r'[^\w\-_.]', '_', s)
    
    def canonicalize_brand(brand: str) -> str:
        return brand.strip()
    
    def _launch(p, profile_dir, headless, proxy_config, net_counters):
        """Minimal launcher"""
        browser = p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        return browser, browser, page, True
    
    def _goto_home(page, SL=None):
        page.goto("https://www.walmart.com", wait_until="domcontentloaded")
    
    def _still_px_modal(page):
        return False
    
    def _solve_px_until_clear(page, say, SL=None):
        return True
    
    def _search_url(keyword):
        from urllib.parse import quote_plus
        return f"https://www.walmart.com/search?q={quote_plus(keyword)}"
    
    def _wait_for_search_results(page, timeout_ms=20000):
        try:
            page.wait_for_selector('a[link-identifier]', timeout=timeout_ms)
            return True, "results"
        except:
            return False, None
    
    def _get_proxy_config():
        return None


# --- Main Harvester ---

def harvest_walmart_brand_logo(
    brand_keyword: str,
    profile_dir: Optional[str] = None,
    headless: bool = True,
    logos_dir: str = "output/brand_logos",
    db_path: str = "output/brand_logos/brand_logo_database.json",
) -> Dict[str, Any]:
    """
    Harvest brand logo from Walmart brand store page.
    
    Returns:
        {
            "ok": bool,
            "brand": str,
            "logo_file": str | None,
            "logo_url": str | None,
            "reason": str | None
        }
    """
    _ensure_dirs(db_path, logos_dir)
    
    # Canonicalize brand
    brand_canonical = canonicalize_brand(brand_keyword) if SCRAPER_IMPORTS_OK else brand_keyword
    brand_slug = brand_canonical.lower().replace(' ', '_').replace('-', '_').replace("'", "")
    retailer = "walmart"
    
    print(f"→ Harvesting logo for: {brand_keyword}")
    
    page = None
    ctx = None
    browser = None
    
    try:
        with sync_playwright() as p:
            # Launch browser
            profile = profile_dir or os.environ.get(PROFILE_ENV)
            if not profile:
                return {
                    "ok": False,
                    "brand": brand_canonical,
                    "logo_file": None,
                    "logo_url": None,
                    "reason": "no_profile_dir"
                }
            
            net_counters = {"req_failed": 0, "resp_doc": 0, "route_errors": 0}
            browser, ctx, page, _ = _launch(
                p, profile, headless,
                _get_proxy_config() if SCRAPER_IMPORTS_OK else None,
                net_counters
            )
            
            if not page:
                return {
                    "ok": False,
                    "brand": brand_canonical,
                    "logo_file": None,
                    "logo_url": None,
                    "reason": "launch_failed"
                }
            
            # Go to home and handle PX
            _goto_home(page, SL=None)
            time.sleep(random.uniform(0.8, 1.5))
            
            if _still_px_modal(page):
                if not _solve_px_until_clear(page, lambda k, m: None):
                    return {
                        "ok": False,
                        "brand": brand_canonical,
                        "logo_file": None,
                        "logo_url": None,
                        "reason": "px_on_home"
                    }
            
            # Search for brand
            search_url = _search_url(brand_keyword)
            page.goto(search_url, wait_until="domcontentloaded")
            time.sleep(random.uniform(1.0, 2.0))
            
            if _still_px_modal(page):
                if not _solve_px_until_clear(page, lambda k, m: None):
                    return {
                        "ok": False,
                        "brand": brand_canonical,
                        "logo_file": None,
                        "logo_url": None,
                        "reason": "px_on_search"
                    }
            
            # Wait for results
            ready, _ = _wait_for_search_results(page, timeout_ms=20000)
            if not ready:
                return {
                    "ok": False,
                    "brand": brand_canonical,
                    "logo_file": None,
                    "logo_url": None,
                    "reason": "no_search_results"
                }
            
            # FIRST: Check for SBA ad with brand logo (fast path)
            print(f"  Checking for SBA ad with brand logo...")
            try:
                # Look for SBA container
                sba_selectors = [
                    '[data-testid="sba-container"]',
                    '[class*="sba-container"]',
                ]
                
                sba_container = None
                for selector in sba_selectors:
                    container = page.locator(selector).first
                    if container.count() > 0:
                        sba_container = container
                        print(f"    SBA container found with selector: {selector}")
                        break
                
                if sba_container:
                    # Look for brand name in any span
                    text_spans = sba_container.locator('span').all()
                    print(f"    Checking {len(text_spans)} text spans for brand match...")
                    
                    found_match = False
                    for span in text_spans:
                        try:
                            text_content = span.inner_text().strip()
                            if not text_content:
                                continue
                            norm_text = text_content.lower().replace(' ', '').replace('-', '')
                            norm_brand = brand_keyword.lower().replace(' ', '').replace('-', '')
                            
                            # Debug: show first few text spans
                            if len(text_content) > 5:
                                print(f"      Checking span: '{text_content[:50]}' (looking for '{brand_keyword}')")
                            
                            if norm_brand in norm_text:
                                found_match = True
                                print(f"    Found brand match in SBA: '{text_content}'")
                                # Get ALL images and filter for logo (odnWidth=150)
                                try:
                                    all_imgs = sba_container.locator('img').all()
                                    print(f"    Total images in SBA: {len(all_imgs)}")
                                    
                                    logo_imgs = []
                                    for i, img in enumerate(all_imgs):
                                        src = img.get_attribute('src') or ''
                                        srcset = img.get_attribute('srcset') or ''
                                        alt = img.get_attribute('alt') or ''
                                        width = img.get_attribute('width') or ''
                                        height = img.get_attribute('height') or ''
                                        
                                        # Check if it's a logo: ONLY 150x90 dimensions (not 150x150 products)
                                        is_logo = (width == '150' and height == '90')
                                        print(f"      Image {i}: width={width}, height={height}, alt={alt[:30]}, is_logo={is_logo}")
                                        
                                        if is_logo:
                                            logo_imgs.append(img)
                                    
                                    print(f"    Logo images found: {len(logo_imgs)}")
                                except Exception as e:
                                    print(f"    ERROR getting images: {type(e).__name__}: {e}")
                                    raise
                                
                                if len(logo_imgs) > 0:
                                    
                                    for img in logo_imgs:
                                        logo_src = img.get_attribute('src')
                                        if logo_src:
                                            print(f"    Downloading SBA logo: {logo_src[:60]}...")
                                            try:
                                                response = requests.get(logo_src, headers=HEADERS, timeout=10)
                                                print(f"    Response status: {response.status_code}")
                                            except Exception as e:
                                                print(f"    Download failed: {e}")
                                                continue
                                            if response.status_code == 200:
                                                # Save the logo
                                                ext = ".png"
                                                if "image/svg" in response.headers.get('content-type', ''):
                                                    ext = ".svg"
                                                elif "image/jpeg" in response.headers.get('content-type', ''):
                                                    ext = ".jpg"
                                                
                                                logo_filename = f"{brand_slug}{ext}"
                                                logo_path = os.path.join(logos_dir, logo_filename)
                                                with open(logo_path, 'wb') as f:
                                                    f.write(response.content)
                                                
                                                print(f"    ✅ Saved SBA logo: {logo_filename}")
                                                
                                                # Update database
                                                _update_brand_logo_db(
                                                    db_path=db_path,
                                                    brand=brand_canonical,
                                                    logo_url=logo_src,
                                                    logo_file=logo_filename,
                                                    retailer=retailer,
                                                    metadata={"source": "walmart_sba", "matched_text": text_content}
                                                )
                                                
                                                # SUCCESS - return immediately
                                                return {
                                                    "ok": True,
                                                    "brand": brand_canonical,
                                                    "logo_file": logo_filename,
                                                    "logo_url": logo_src,
                                                    "source": "walmart_sba"
                                                }
                        except Exception as e:
                            print(f"    ⚠️  Error processing span: {type(e).__name__}: {e}")
                            import traceback
                            traceback.print_exc()
                            continue
                    
                    if not found_match:
                        print(f"    ✗ No brand match found in {len(text_spans)} spans")
                else:
                    print(f"    ✗ No SBA container found")
                
                print(f"    → Continuing to brand store...")
            except Exception as e:
                print(f"    SBA check failed: {e}, continuing to brand store...")
            
            # FALLBACK: Find first product link and go to brand store
            print(f"  Finding first product...")
            product_link = None
            
            # Try different selectors
            selectors = [
                'a[link-identifier][href*="/ip/"]',
                '[data-testid="list-view"] a[href*="/ip/"]',
                '#results-container a[href*="/ip/"]',
            ]
            
            for selector in selectors:
                loc = page.locator(selector).first
                if loc.count() > 0:
                    product_link = loc
                    break
            
            if not product_link:
                return {
                    "ok": False,
                    "brand": brand_canonical,
                    "logo_file": None,
                    "logo_url": None,
                    "reason": "no_product_link"
                }
            
            # Get the href and navigate directly (avoid click interception)
            href = product_link.get_attribute("href")
            if href:
                # Handle tracking URLs - extract real URL from rd parameter
                if "/sp/track?" in href and "rd=" in href:
                    from urllib.parse import urlparse, parse_qs, unquote
                    parsed = urlparse(href)
                    params = parse_qs(parsed.query)
                    if "rd" in params:
                        href = unquote(params["rd"][0])
                
                # Ensure it's a full URL
                if not href.startswith("http"):
                    href = f"https://www.walmart.com{href}"
                
                print(f"  Navigating to product page...")
                page.goto(href, wait_until="domcontentloaded")
            page.wait_for_load_state("domcontentloaded", timeout=20000)
            time.sleep(random.uniform(0.6, 1.2))
            
            if _still_px_modal(page):
                if not _solve_px_until_clear(page, lambda k, m: None):
                    return {
                        "ok": False,
                        "brand": brand_canonical,
                        "logo_file": None,
                        "logo_url": None,
                        "reason": "px_on_pdp"
                    }
            
            # Find brand link on PDP
            brand_link = page.locator('a[data-dca-name="ItemBrandLink"]').first
            if brand_link.count() == 0:
                return {
                    "ok": False,
                    "brand": brand_canonical,
                    "logo_file": None,
                    "logo_url": None,
                    "reason": "no_brand_link"
                }
            
            href = brand_link.get_attribute("href") or ""

            # Extra safety: verify PDP brand text actually matches requested brand.
            try:
                pdp_brand_text = (brand_link.inner_text() or "").strip()
            except Exception:
                pdp_brand_text = ""

            norm_target = _norm_brand_for_match(brand_canonical)
            norm_pdp = _norm_brand_for_match(pdp_brand_text)

            if norm_target and norm_pdp and not (
                norm_target in norm_pdp or norm_pdp in norm_target
            ):
                print(f"  ❌ PDP brand mismatch: wanted='{brand_canonical}' got='{pdp_brand_text}'")
                return {
                    "ok": False,
                    "brand": brand_canonical,
                    "logo_file": None,
                    "logo_url": None,
                    "reason": f"pdp_brand_mismatch:{pdp_brand_text}",
                }
            
            # Check if it's a real store link
            if not href.startswith("/brand/"):
                print(f"  ❌ Not a store link (facet link): {href}")
                return {
                    "ok": False,
                    "brand": brand_canonical,
                    "logo_file": None,
                    "logo_url": None,
                    "reason": "not_a_store_link"
                }
            
            # Navigate to brand store
            store_url = "https://www.walmart.com" + href
            print(f"  Navigating to brand store: {store_url}")
            page.goto(store_url, wait_until="domcontentloaded")
            time.sleep(random.uniform(0.8, 1.6))
            
            if _still_px_modal(page):
                if not _solve_px_until_clear(page, lambda k, m: None):
                    return {
                        "ok": False,
                        "brand": brand_canonical,
                        "logo_file": None,
                        "logo_url": None,
                        "reason": "px_on_store"
                    }
            
            # Find logo image
            logos = page.locator('img[alt*="logo" i]').all()
            if not logos:
                return {
                    "ok": False,
                    "brand": brand_canonical,
                    "logo_file": None,
                    "logo_url": None,
                    "reason": "no_logo_img"
                }
            
            # Prefer advertising.walmart.com CDN
            logo_img = None
            for img in logos:
                try:
                    src = img.get_attribute("src") or ""
                    if "advertising.walmart.com" in src:
                        logo_img = img
                        break
                except Exception:
                    continue
            
            if not logo_img:
                logo_img = logos[0]
            
            src = logo_img.get_attribute("src") or ""
            if not src:
                return {
                    "ok": False,
                    "brand": brand_canonical,
                    "logo_file": None,
                    "logo_url": None,
                    "reason": "logo_src_missing"
                }
            
            # Download logo
            slug = _brand_slug(brand_canonical)
            ext = _ext_from_url(src)
            logo_filename = f"{slug}{ext}"
            logo_path = os.path.join(logos_dir, logo_filename)
            
            print(f"  Downloading logo: {src}")
            ua = BROWSER_UA.get("ua", "Mozilla/5.0")
            ok = _download_logo(src, logo_path, referer=page.url, user_agent=ua)
            
            if not ok:
                return {
                    "ok": False,
                    "brand": brand_canonical,
                    "logo_file": None,
                    "logo_url": src,
                    "reason": "download_failed"
                }
            
            # Update database
            metadata = {
                "source": "walmart_brand_store",
                "keyword": brand_keyword,
                "timestamp": _timestamp_iso(),
                "store_url": store_url,
            }
            
            _update_brand_logo_db(db_path, brand_canonical, src, logo_filename, retailer, metadata)
            
            print(f"  ✅ Logo saved: {logo_filename}")
            return {
                "ok": True,
                "brand": brand_canonical,
                "logo_file": logo_filename,
                "logo_url": src,
                "reason": None
            }
    
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return {
            "ok": False,
            "brand": brand_canonical,
            "logo_file": None,
            "logo_url": None,
            "reason": f"fatal:{e}"
        }
    
    finally:
        try:
            if ctx:
                ctx.close()
        except Exception:
            pass
        try:
            if browser and not isinstance(browser, type(ctx)):
                browser.close()
        except Exception:
            pass


def main():
    """CLI entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Harvest brand logos from Walmart")
    parser.add_argument("brand", help="Brand name to search for")
    parser.add_argument("--profile-dir", help="Chrome profile directory")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    parser.add_argument("--logos-dir", default="output/brand_logos", help="Logo output directory")
    parser.add_argument("--db-path", default="output/brand_logos/brand_logo_database.json", help="Database path")
    
    args = parser.parse_args()
    
    result = harvest_walmart_brand_logo(
        brand_keyword=args.brand,
        profile_dir=args.profile_dir,
        headless=args.headless,
        logos_dir=args.logos_dir,
        db_path=args.db_path,
    )
    
    print()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
