#!/usr/bin/env python3
"""
LogoScout: fetch brand logos for your ad cards.

Strategy (per brand):
1) Wikidata:
   - Find entity via wbsearchentities
   - Get P856 (official website) [domain]
   - Get P154 (logo image file) → fetch from Wikimedia Commons if present
2) Clearbit (no API key): https://logo.clearbit.com/<domain> (PNG)
3) (Optional TODO fallback) simple web search for /logo.(svg|png) on the official site

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

import requests
from slugify import slugify

# Use the existing brand logos directory (not a separate one)
LOGOS_DIR = Path("output/brand_logos")
LOGOS_DB = Path("output/brand_logos/brand_logo_database.json")
CARDS_ENDPOINT = "/api/ads/cards"        # your cards API path

WIKIDATA = "https://www.wikidata.org/w/api.php"
COMMONS_FILE_REDIRECT = "https://commons.wikimedia.org/wiki/Special:FilePath/{}"  # returns image bytes

# User-Agent header required by Wikidata
HEADERS = {
    "User-Agent": "LogoScout/1.0 (Retail Ad Monitor; internal tooling)"
}


def ensure_dirs():
    LOGOS_DIR.mkdir(parents=True, exist_ok=True)


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
    """Normalize brand name to database key format"""
    return brand.lower().replace("'", "").replace("&", "and").replace(".", "").replace(" ", "_").strip()


def fetch_cards(api_base, retailer, client, page=1, page_size=100):
    url = f"{api_base}{CARDS_ENDPOINT}?retailer={retailer}&client={client}&page={page}&page_size={page_size}"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.json()


def unique_brands_from_cards(cards):
    brands = set()
    for c in cards:
        b = (c.get("brand") or "").strip()
        if b and b.lower() not in {
            "display ad", "shoppable display ad", "shoppable video ad", "video ad",
            "sponsored product", "sponsored products", "unknown", "n/a"
        } and "shoppable" not in b.lower():
            brands.add(b)
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
    """Write logo file to output/brand_logos/"""
    outp = LOGOS_DIR / f"{brand_key}{ext}"
    outp.write_bytes(raw_bytes)
    return outp


def add_logo_to_database(db, brand, logo_path, source_info, retailer):
    """Add logo entry to database"""
    from datetime import datetime, timezone
    brand_key = normalize_brand_key(brand)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    db["brands"][brand_key] = {
        "logo_file": logo_path.name,
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

    # 1) Wikidata → official site + logo image
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

    # 2) Clearbit (requires domain)
    if official_domain:
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

    # 3) Walmart brand store fallback
    try:
        from tools.walmart_logo_harvester import harvest_walmart_brand_logo
        
        # Check if Walmart profile is configured
        walmart_profile = os.environ.get("WALMART_PROFILE_DIR")
        if walmart_profile and os.path.exists(walmart_profile):
            result = harvest_walmart_brand_logo(
                brand_keyword=brand,
                profile_dir=walmart_profile,
                headless=True,
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
    except Exception as e:
        # Silently skip Walmart fallback if it fails
        pass

    return None, {"source": "not-found"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", required=True, help="API base, e.g., http://localhost:5006")
    parser.add_argument("--retailer", required=True)
    parser.add_argument("--client", required=True)
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()

    ensure_dirs()
    db = load_database()

    # 1) Gather brands from cards (paginate until limit)
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
    print(f"Found {len(brands)} candidate brand(s): {brands}")

    # 2) Fetch logos
    fetched_count = 0
    skipped_count = 0
    
    for brand in brands:
        brand_key = normalize_brand_key(brand)
        
        # Check if already in database
        if brand_key in db.get("brands", {}):
            print(f"✓ {brand}: already in database")
            skipped_count += 1
            continue

        print(f"→ fetching logo for {brand} ...")
        path, note = fetch_logo_for_brand(db, brand, args.retailer)
        
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
    print(f"   Total brands in database: {len(db['brands'])}")


if __name__ == "__main__":
    main()
