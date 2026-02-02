#!/usr/bin/env python3
"""
LogoScout: fetch brand logos for your ad cards.

Strategy (per brand):
1) Official website header scrape:
   - Try {brand}.com and look for logo in header (a.logo img, header img, etc.)
   - Fast and gets the actual brand logo as displayed on their site
2) Wikidata:
   - Find entity via wbsearchentities
   - Get P856 (official website) [domain]
   - Get P154 (logo image file) → fetch from Wikimedia Commons if present
3) Clearbit (no API key): https://logo.clearbit.com/<domain> (PNG)

Outputs:
- Saves logo to output/brand_logos/<brand-slug>.svg or .png
- Updates output/brand_logos/brand_logo_database.json with source metadata

Usage example:
  python3 tools/logo_scout.py \
      --api http://localhost:5006 \
      --retailer instacart \
      --client blue_bunny \
      --limit 100
"""

import argparse, json, os, re, sys, time
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime, timezone

import requests
from slugify import slugify

# Use the existing brand logos directory (not a separate one)
LOGOS_DIR = Path("output/brand_logos")
LOGOS_DB = Path("output/brand_logos/brand_logo_database.json")
CARDS_ENDPOINT = "/api/ads/cards"        # your cards API path

WIKIDATA = "https://www.wikidata.org/w/api.php"

def now_iso_z():
    """Return current UTC time in ISO 8601 format with Z suffix"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
COMMONS_FILE_REDIRECT = "https://commons.wikimedia.org/wiki/Special:FilePath/{}"  # returns image bytes

# User-Agent header required by Wikidata
HEADERS = {
    "User-Agent": "LogoScout/1.0 (Retail Ad Monitor; internal tooling)"
}


def ensure_dirs():
    LOGOS_DIR.mkdir(parents=True, exist_ok=True)
    (LOGOS_DIR / "unverified").mkdir(exist_ok=True)
    (LOGOS_DIR / "verified").mkdir(exist_ok=True)


def load_database():
    """Load the brand logo database"""
    if LOGOS_DB.exists():
        try:
            return json.loads(LOGOS_DB.read_text())
        except Exception:
            pass
    return {"brands": {}, "metadata": {"last_updated": None, "total_brands": 0}}


def save_database(db):
    """Save the brand logo database (alphabetically sorted)"""
    from datetime import datetime, timezone
    db["metadata"]["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db["metadata"]["total_brands"] = len(db["brands"])
    
    # Sort brands alphabetically
    sorted_brands = dict(sorted(db["brands"].items(), key=lambda x: x[0].lower()))
    db["brands"] = sorted_brands
    
    LOGOS_DB.write_text(json.dumps(db, indent=2, ensure_ascii=False))


def normalize_brand_key(brand):
    """Normalize brand name to database key format.

    Uses Unicode normalization so that names like 'göt2b' and 'got2b'
    collapse to the same key, while preserving behavior for existing
    ASCII-only keys.
    """
    import unicodedata
    s = (brand or "").strip()
    # Strip accents/diacritics
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    # Existing ASCII normalization
    s = s.lower().replace("'", "").replace("&", "and").replace(".", "").replace(" ", "_")
    return s.strip()


def fetch_cards(api_base, retailer, client, page=1, page_size=100):
    url = f"{api_base}{CARDS_ENDPOINT}?retailer={retailer}&client={client}&page={page}&page_size={page_size}"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.json()


def split_cobrands(brand: str):
    """Split co-branded strings into individual brand names."""
    if not brand:
        return []
    # Split on common co-brand separators (&, /, +, comma, " x ", " and ")
    parts = re.split(r"\s*(?:&|/|,|\+|\band\b| x | X )\s*", brand)
    return [p.strip() for p in parts if p.strip()]


def unique_brands_from_cards(cards):
    brands = set()
    for c in cards:
        b = (c.get("brand") or "").strip()
        if not b:
            continue
        low = b.lower()
        if low in {
            "display ad", "shoppable display ad", "shoppable video ad", "video ad",
            "sponsored product", "sponsored products", "unknown", "n/a"
        } or "shoppable" in low:
            continue
        # Split potential co-brands into separate entries
        for part in split_cobrands(b) or [b]:
            part = part.strip()
            if part:
                brands.add(part)
    return sorted(brands)


def wikidata_search_entity(name):
    params = {
        "action": "wbsearchentities",
        "search": name,
        "language": "en",
        "format": "json",
        "limit": 1,
    }
    r = requests.get(WIKIDATA, params=params, headers=HEADERS, timeout=15)
    r.raise_for_status()
    data = r.json()
    if data.get("search"):
        return data["search"][0]["id"]  # e.g., "Q12345"
    return None


def wikidata_get_entity(qid):
    params = {
        "action": "wbgetentities",
        "ids": qid,
        "format": "json",
        "props": "claims",
    }
    r = requests.get(WIKIDATA, params=params, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()


def wikidata_get_claim_file_name(entities, prop):
    # P154 = logo image (Commons file name)
    # P856 = official website (URL)
    try:
        ent = next(iter(entities["entities"].values()))
        claims = ent.get("claims", {})
        if prop not in claims:
            return None
        mainsnak = claims[prop][0]["mainsnak"]
        if prop == "P154":
            return mainsnak["datavalue"]["value"]  # e.g., 'Blue Bunny logo.svg'
        if prop == "P856":
            return mainsnak["datavalue"]["value"]  # URL
    except Exception:
        return None
    return None


def commons_fetch_file_bytes(file_name):
    # Commons host will redirect to actual file URL
    url = COMMONS_FILE_REDIRECT.format(file_name)
    r = requests.get(url, headers=HEADERS, timeout=30)
    if r.status_code == 200 and r.content:
        # simple content-type check
        ctype = r.headers.get("Content-Type", "")
        return r.content, ctype
    return None, None


def clearbit_logo(domain):
    # No API key required
    # https://logo.clearbit.com/<domain>
    try:
        dom = domain.lower()
        if not dom:
            return None, None
        url = f"https://logo.clearbit.com/{dom}"
        r = requests.get(url, timeout=15)
        if r.status_code == 200 and r.content:
            return r.content, r.headers.get("Content-Type", "image/png")
    except Exception:
        pass
    return None, None


def normalize_ext_from_ctype(ctype):
    if "svg" in ctype:
        return ".svg"
    if "png" in ctype:
        return ".png"
    if "jpeg" in ctype or "jpg" in ctype:
        return ".jpg"
    return ".bin"


def safe_write_logo(brand_key, raw_bytes, ext):
    """Write logo file to output/brand_logos/unverified/ for review"""
    outp = LOGOS_DIR / "unverified" / f"{brand_key}{ext}"
    outp.write_bytes(raw_bytes)
    return outp


def add_logo_to_database(db, brand, logo_path, source_info, retailer):
    """Add logo entry to database"""
    from datetime import datetime, timezone
    brand_key = normalize_brand_key(brand)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    db["brands"][brand_key] = {
        "brand_name": brand,
        "logo_file": f"unverified/{logo_path.name}",
        "retailers": [retailer],
        "first_seen": timestamp,
        "last_seen": timestamp,
        "last_updated": timestamp,
        "source": source_info.get("source"),
        "metadata": source_info
    }


def extract_domain(url):
    try:
        u = urlparse(url)
        host = u.netloc.lower()
        # strip www.
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return None


def scrape_header_logo(brand, domain=None):
    """
    Scrape brand's official website for a logo in the header using Playwright.
    
    STRICT validation:
    - Must have semantic confirmation (alt text, class, or parent with "logo")
    - Must have reasonable aspect ratio (1:1 to 5:1)
    - Must be reasonable size (not tiny icon, not huge banner)
    
    Returns (raw_bytes, content_type, source_url) or (None, None, None)
    """
    from playwright.sync_api import sync_playwright
    from PIL import Image
    from io import BytesIO
    
    # Build candidate domains to try
    slug = slugify(brand).replace("-", "")
    candidates = []
    if domain:
        candidates.append(domain)
    candidates.extend([
        f"{slug}.com",
        f"www.{slug}.com",
        f"{slug.replace('_', '')}.com",
    ])
    
    brand_lower = brand.lower()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = context.new_page()
        
        for dom in candidates:
            try:
                url = f"https://{dom}"
                print(f"    → trying {url} ...", end=" ", flush=True)
                
                try:
                    page.goto(url, timeout=15000, wait_until="domcontentloaded")
                    page.wait_for_timeout(2000)  # Let JS render
                except Exception as e:
                    print(f"({e})")
                    continue
                
                # Find all images with logo indicators
                candidates_found = []
                
                # Get all img elements
                imgs = page.locator("img").all()
                
                for img in imgs:
                    try:
                        src = img.get_attribute("src") or img.get_attribute("data-src") or ""
                        if not src:
                            continue
                        
                        # Skip obvious non-logos
                        src_lower = src.lower()
                        if any(skip in src_lower for skip in [
                            "favicon", "icon", "social", "facebook", "twitter", 
                            "instagram", "1x1", "pixel", "tracking", "analytics",
                            "banner", "hero", "slide", "product", "cart"
                        ]):
                            continue
                        
                        # --- SEMANTIC VALIDATION ---
                        semantic_score = 0
                        
                        # Check img attributes
                        alt = (img.get_attribute("alt") or "").lower()
                        img_class = (img.get_attribute("class") or "").lower()
                        
                        # Alt text contains "logo" or brand name
                        if "logo" in alt:
                            semantic_score += 3
                        if brand_lower in alt:
                            semantic_score += 2
                        
                        # Class contains "logo"
                        if "logo" in img_class:
                            semantic_score += 3
                        
                        # Check if inside header or logo container
                        try:
                            # Check ancestors for logo/header indicators
                            in_header = img.locator("xpath=ancestor::header").count() > 0
                            in_nav = img.locator("xpath=ancestor::nav").count() > 0
                            in_logo_container = img.locator("xpath=ancestor::*[contains(@class, 'logo')]").count() > 0
                            in_home_link = img.locator("xpath=ancestor::a[@href='/']").count() > 0
                            
                            if in_header:
                                semantic_score += 1
                            if in_nav:
                                semantic_score += 1
                            if in_logo_container:
                                semantic_score += 2
                            if in_home_link:
                                semantic_score += 1
                        except:
                            pass
                        
                        # Must have minimum semantic confidence
                        if semantic_score < 2:
                            continue
                        
                        # Get bounding box for size validation
                        bbox = img.bounding_box()
                        if bbox:
                            w, h = bbox["width"], bbox["height"]
                            # Too small = icon
                            if w < 50 or h < 20:
                                continue
                            # Too large = probably not a logo
                            if w > 500 or h > 300:
                                continue
                            # Aspect ratio check (0.5:1 to 5:1)
                            aspect = w / h if h > 0 else 999
                            if aspect < 0.5 or aspect > 5.0:
                                continue
                        
                        candidates_found.append((img, src, semantic_score, bbox))
                        
                    except Exception:
                        continue
                
                # Sort by semantic score (highest first)
                candidates_found.sort(key=lambda x: x[2], reverse=True)
                
                for img, src, score, bbox in candidates_found:
                    # Normalize URL
                    if src.startswith("//"):
                        src = "https:" + src
                    elif src.startswith("/"):
                        src = f"https://{dom}{src}"
                    elif not src.startswith("http"):
                        src = f"https://{dom}/{src}"
                    
                    # Fetch the image
                    try:
                        img_resp = requests.get(src, headers=HEADERS, timeout=8)
                        if img_resp.status_code != 200:
                            continue
                        
                        ctype = img_resp.headers.get("Content-Type", "")
                        raw = img_resp.content
                        
                        # Validate it's an image
                        if not ("image" in ctype or src.endswith((".png", ".jpg", ".jpeg", ".svg", ".webp"))):
                            continue
                        
                        size_kb = len(raw) / 1024
                        dims = f"{bbox['width']:.0f}x{bbox['height']:.0f}" if bbox else "?"
                        print(f"✓ found (score={score}, {dims}, {size_kb:.1f}KB)")
                        
                        browser.close()
                        return raw, ctype, src
                        
                    except Exception:
                        pass
                
                print("no valid logo found")
                
            except Exception as e:
                print(f"error: {e}")
                continue
        
        browser.close()
    
    return None, None, None


def check_existing_logo(db, brand):
    """Check if brand already exists in database"""
    brand_key = normalize_brand_key(brand)
    
    if brand_key in db.get("brands", {}):
        logo_file = db["brands"][brand_key].get("logo_file")
        if logo_file:
            # Handle both absolute and relative paths
            if "/" in logo_file:
                logo_file = logo_file.split("/")[-1]
            
            logo_path = LOGOS_DIR / logo_file
            if logo_path.exists():
                return logo_path
    
    return None


def extract_walmart_sba_logo(brand, brand_key):
    """
    Search Walmart for the brand and extract logo from SBA if present.
    Strategy 1: Look for brand name in SBA container and extract 150x90 logo image
    Strategy 2: Fall back to existing logic (look for matching alt text)
    Returns (logo_path, source_info) or (None, None) if not found.
    """
    try:
        from playwright.sync_api import sync_playwright
        
        # Check if Walmart profile is configured
        walmart_profile = os.environ.get("WALMART_PROFILE_DIR")
        if not walmart_profile or not os.path.exists(walmart_profile):
            print(f"  ⚠️  Walmart profile not configured")
            return None, None
        
        print(f"  🌐 Opening browser (visible)...")
        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                walmart_profile,
                headless=False,  # VISIBLE so you can see what's happening
                args=['--disable-blink-features=AutomationControlled']
            )
            page = browser.new_page()
            
            # Search for the brand
            search_url = f"https://www.walmart.com/search?q={brand.replace(' ', '+')}"
            print(f"  🔍 Searching Walmart for: {brand}")
            print(f"     URL: {search_url}")
            page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2000)  # Quick wait for dynamic content
            
            page_title = page.title()
            print(f"  📄 Page loaded: {page_title}")
            
            # Quick check - if we hit bot detection, bail immediately
            if "robot" in page_title.lower() or "blocked" in page_title.lower():
                print(f"  🤖 Bot detection page - skipping SBA extraction")
                browser.close()
                return None, None
            
            # STRATEGY 1: Look for brand name in SBA container
            print(f"  🎯 Strategy 1: Looking for SBA container with brand name...")
            sba_selectors = [
                '[class*="sba-container"]',
                '[data-testid^="list-view"]',
                '[class*="sponsored"]',
                'div[class*="mb1"]'
            ]
            
            sba_container = None
            for selector in sba_selectors:
                container = page.locator(selector).first
                count = container.count()
                if count > 0:
                    sba_container = container
                    print(f"     ✓ Found container: {selector} (count: {count})")
                    break
                else:
                    print(f"     ✗ Not found: {selector}")
            
            if sba_container:
                # Look for any spans with text content (avoid hashed class names)
                text_spans = sba_container.locator('span').all()
                print(f"     Found {len(text_spans)} text spans to check")
                
                for i, span in enumerate(text_spans):
                    try:
                        text_content = span.inner_text().strip()
                        norm_text = text_content.lower().replace(' ', '').replace('-', '')
                        norm_brand = brand.lower().replace(' ', '').replace('-', '')
                        
                        if norm_brand in norm_text:
                            print(f"     ✓ Match found in span {i}: '{text_content}'")
                            parent = span.locator('xpath=ancestor::*[contains(@class, "sba") or contains(@data-testid, "list-view")]').first
                            if parent.count() > 0:
                                logo_imgs = parent.locator('img[width="150"][height="90"], img[srcset*="odnWidth=150"]').all()
                                print(f"       Found {len(logo_imgs)} logo images (150x90)")
                                
                                for j, img in enumerate(logo_imgs):
                                    logo_src = img.get_attribute('src')
                                    logo_alt = img.get_attribute('alt') or ""
                                    
                                    if logo_src:
                                        print(f"       📥 Downloading logo {j}: {logo_src[:80]}...")
                                        response = requests.get(logo_src, headers=HEADERS, timeout=10)
                                        if response.status_code == 200:
                                            raw = response.content
                                            ctype = response.headers.get('content-type', 'image/png')
                                            ext = normalize_ext_from_ctype(ctype)
                                            logo_path = safe_write_logo(brand_key, raw, ext)
                                            print(f"       ✅ Saved: {logo_path.name}")
                                            
                                            browser.close()
                                            return logo_path, {
                                                "source": "walmart_sba_container",
                                                "logo_url": logo_src,
                                                "alt_text": logo_alt,
                                                "matched_text": text_content
                                            }
                    except Exception as e:
                        print(f"       ⚠️  Error on span {i}: {e}")
                        continue
                
                print(f"     ✗ No matching brand text found in spans")
            else:
                print(f"     ✗ No SBA container found")
            
            # STRATEGY 2: Fallback - look for matching alt text
            print(f"  🎯 Strategy 2: Looking for images with matching alt text...")
            sba_selectors = [
                '[data-testid^="list-view"] img[alt]:not([alt=""])',
                '[data-automation-id="product-title-link"] img[alt]:not([alt=""])',
                'img[src*="advertising.walmart.com"]',
            ]
            
            for selector in sba_selectors:
                try:
                    logo_img = page.locator(selector).first
                    if logo_img.count() > 0:
                        logo_src = logo_img.get_attribute('src')
                        logo_alt = logo_img.get_attribute('alt') or ""
                        
                        norm_alt = logo_alt.lower().replace(' ', '').replace('-', '')
                        norm_brand = brand.lower().replace(' ', '').replace('-', '')
                        
                        if norm_brand in norm_alt or norm_alt in norm_brand:
                            print(f"     ✓ Match found: alt='{logo_alt}'")
                            print(f"     📥 Downloading: {logo_src[:80]}...")
                            response = requests.get(logo_src, headers=HEADERS, timeout=10)
                            if response.status_code == 200:
                                raw = response.content
                                ctype = response.headers.get('content-type', 'image/png')
                                ext = normalize_ext_from_ctype(ctype)
                                logo_path = safe_write_logo(brand_key, raw, ext)
                                print(f"     ✅ Saved: {logo_path.name}")
                                
                                browser.close()
                                return logo_path, {
                                    "source": "walmart_sba_alt_text",
                                    "logo_url": logo_src,
                                    "alt_text": logo_alt
                                }
                except Exception as e:
                    print(f"     ⚠️  Error with selector {selector}: {e}")
                    continue
            
            print(f"  ❌ No logo found via SBA extraction")
            browser.close()
            return None, None
            
    except Exception as e:
        print(f"  ⚠️  Walmart SBA extraction failed: {e}")
        return None, None

def fetch_logo_for_brand(db, brand, retailer="instacart"):
    """
    Fetch logo for brand and add to database.
    Returns tuple: (saved_path, source_note)
    """
    brand_key = normalize_brand_key(brand)
    
    # Check if already in database
    existing_logo = check_existing_logo(db, brand)
    if existing_logo:
        return None, {"source": "existing-database", "file": existing_logo.name}
    
    slug = slugify(brand)

    # 1) Try brand's official website header first
    print(f"  [1] Checking {brand}.com header...")
    raw, ctype, src_url = scrape_header_logo(brand)
    if raw:
        ext = normalize_ext_from_ctype(ctype or "image/png")
        logo_path = safe_write_logo(brand_key, raw, ext)
        source_info = {
            "source": "official-website",
            "url": src_url,
            "ctype": ctype,
        }
        add_logo_to_database(db, brand, logo_path, source_info, retailer)
        return logo_path, source_info

    # 2) Wikidata → official site + logo image
    print(f"  [2] Checking Wikidata...")
    qid = wikidata_search_entity(brand)
    official_domain = None
    if qid:
        ent = wikidata_get_entity(qid)
        # Official website
        site_url = wikidata_get_claim_file_name(ent, "P856")
        if site_url:
            official_domain = extract_domain(site_url)

        # Logo image (Commons)
        file_name = wikidata_get_claim_file_name(ent, "P154")
        if file_name:
            raw, ctype = commons_fetch_file_bytes(file_name)
            if raw:
                ext = normalize_ext_from_ctype(ctype)
                logo_path = safe_write_logo(brand_key, raw, ext)
                source_info = {
                    "source": "wikidata/commons",
                    "qid": qid,
                    "file": file_name,
                    "ctype": ctype,
                }
                add_logo_to_database(db, brand, logo_path, source_info, retailer)
                return logo_path, source_info

    # 3) Clearbit (requires domain)
    if official_domain:
        print(f"  [3] Trying Clearbit for {official_domain}...")
        raw, ctype = clearbit_logo(official_domain)
        if raw:
            ext = normalize_ext_from_ctype(ctype or "image/png")
            logo_path = safe_write_logo(brand_key, raw, ext)
            source_info = {
                "source": "clearbit",
                "domain": official_domain,
                "ctype": ctype or "image/png",
            }
            add_logo_to_database(db, brand, logo_path, source_info, retailer)
            return logo_path, source_info

    # 4) Walmart harvester (checks SBA first, then brand store)
    # Check Walmart harvester
    walmart_failed = db.get("failed_searches", {}).get(brand_key, {}).get("walmart", False)
    
    if walmart_failed:
        print(f"  ⊘ Skipping Walmart (previously failed)")
        return None, {"source": "walmart-previously-failed"}
    
    if not walmart_failed:
        try:
            from walmart_logo_harvester import harvest_walmart_brand_logo
            
            # Check if Walmart profile is configured
            walmart_profile = os.environ.get("WALMART_PROFILE_DIR")
            if not walmart_profile or not os.path.exists(walmart_profile):
                return None, {"source": "not-found"}
            
            result = harvest_walmart_brand_logo(
                brand_keyword=brand,
                profile_dir=walmart_profile,
                headless=False,  # VISIBLE
                logos_dir=str(LOGOS_DIR),
                db_path=str(LOGOS_DB),
            )
            
            if result.get("ok"):
                logo_file = result.get("logo_file")
                if logo_file:
                    logo_path = LOGOS_DIR / logo_file
                    if logo_path.exists():
                        return logo_path, {
                            "source": "walmart_brand_store",
                            "logo_url": result.get("logo_url"),
                        }
            else:
                # Mark Walmart as failed for this brand
                if "failed_searches" not in db:
                    db["failed_searches"] = {}
                if brand_key not in db["failed_searches"]:
                    db["failed_searches"][brand_key] = {}
                db["failed_searches"][brand_key]["walmart"] = True
                db["failed_searches"][brand_key]["last_attempt"] = now_iso_z()
        except Exception as e:
            print(f"     ❌ EXCEPTION in Walmart harvester: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            # Mark Walmart as failed for this brand
            if "failed_searches" not in db:
                db["failed_searches"] = {}
            if brand_key not in db["failed_searches"]:
                db["failed_searches"][brand_key] = {}
            db["failed_searches"][brand_key]["walmart"] = True
            db["failed_searches"][brand_key]["last_attempt"] = now_iso_z()
            db["failed_searches"][brand_key]["error"] = str(e)

    return None, {"source": "not-found"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lexicon", action="store_true", help="Scan brand lexicon instead of API")
    parser.add_argument("--api", help="API base, e.g., http://localhost:5006 (required if not using --lexicon)")
    parser.add_argument("--retailer", help="Retailer (required if not using --lexicon)")
    parser.add_argument("--client", help="Client (required if not using --lexicon)")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--retry-failed", action="store_true", help="Retry brands that previously failed (test new extraction logic)")
    args = parser.parse_args()

    ensure_dirs()
    db = load_database()

    # 1) Gather brands from lexicon or API
    if args.lexicon:
        # Load brands from config/brands.json
        lexicon_path = Path("config/brands.json")
        if not lexicon_path.exists():
            print(f"❌ Lexicon not found: {lexicon_path}")
            return
        
        with open(lexicon_path, 'r') as f:
            lexicon_brands = json.load(f)
        
        brands = set()
        for brand_entry in lexicon_brands:
            brand_name = brand_entry.get('name')
            if brand_name:
                brands.add(brand_name)
        
        brands = sorted(brands)
        print(f"📖 Loaded {len(brands)} brands from lexicon")
    else:
        # Require API parameters if not using lexicon
        if not args.api or not args.retailer or not args.client:
            parser.error("--api, --retailer, and --client are required when not using --lexicon")
        
        # Gather brands from cards (paginate until limit)
        brands = set()
        page = 1
        while len(brands) < args.limit:
            data = fetch_cards(args.api, args.retailer, args.client, page=page, page_size=100)
            cards = data.get("cards", [])
            if not cards:
                break
            for b in unique_brands_from_cards(cards):
                brands.add(b)
                if len(brands) >= args.limit:
                    break
            if not data.get("has_more"):
                break
            page += 1

        brands = sorted(brands)
        print(f"Found {len(brands)} candidate brand(s) from API")

    # 2) Fetch logos
    fetched_count = 0
    skipped_count = 0
    failed_count = 0
    retry_failed = args.retry_failed if hasattr(args, 'retry_failed') else False
    
    for brand in brands:
        brand_key = normalize_brand_key(brand)
        
        # Check if already in database
        if brand_key in db.get("brands", {}):
            print(f"✓ {brand}: already in database")
            skipped_count += 1
            continue
        
        # Check if previously failed (skip to avoid retrying unless --retry-failed)
        if not retry_failed and brand_key in db.get("failed_searches", {}):
            failed_info = db["failed_searches"][brand_key]
            last_attempt = failed_info.get("last_attempt", "unknown")
            print(f"⊘ {brand}: previously failed (last attempt: {last_attempt})")
            failed_count += 1
            continue
        
        # If retrying failed, clear the failed entry for this brand
        if retry_failed and brand_key in db.get("failed_searches", {}):
            print(f"🔄 {brand}: retrying previously failed search...")
            del db["failed_searches"][brand_key]

        print(f"→ fetching logo for {brand} ...")
        retailer = args.retailer if not args.lexicon else "general"
        path, note = fetch_logo_for_brand(db, brand, retailer)
        
        if note.get("source") == "existing-database":
            print(f"  ✓ already exists [{note.get('file')}]")
            skipped_count += 1
        elif path:
            print(f"  ✅ saved: {path.name} [{note['source']}]")
            fetched_count += 1
        else:
            print(f"  ❌ not found (source={note.get('source')})")

    # Save database
    save_database(db)
    print()
    print(f"✅ Database updated: {LOGOS_DB}")
    print(f"   Fetched: {fetched_count} new logos")
    print(f"   Skipped: {skipped_count} existing logos")
    print(f"   Previously failed: {failed_count} brands")
    print(f"   Total brands in database: {len(db['brands'])}")
    print(f"   Total failed searches tracked: {len(db.get('failed_searches', {}))}")


if __name__ == "__main__":
    main()
