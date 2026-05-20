"""
Retailer-Aware API Server for Builder.io Integration

This server provides clean, read-only REST endpoints for Builder.io to access
multi-retailer ad data. It respects the path taxonomy and provides normalized
JSON responses.

Phase 1: Read-only API with retailer/client awareness
Phase 2: Builder.io integration via REST data sources
Phase 3: Live run status (SSE/WebSocket) - optional
Phase 4: Admin writes (POST /api/scrape) - future
"""

import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from flask import Flask, jsonify, request, send_from_directory, make_response, send_file, Response, abort, g
from pathlib import Path
from urllib.parse import unquote, quote
from functools import lru_cache
import json
import glob
import mimetypes
import requests
import re
from datetime import datetime, timezone, timedelta
from time import perf_counter, time
from utils.path_taxonomy import allowed_subdirs, ADTYPE_TO_FOLDER
from core.brands import canonicalize, is_blacklisted, smart_title
import hashlib
_USE_DB = False
try:
    from web.db_store import (
        runs as mf_runs, daily_totals as mf_daily,
        brands as mf_brands, brands_by_client as mf_brands_by_client,
        _db_available, count_ads as db_count_ads,
        get_ad_types as db_get_ad_types, get_brands_filtered as db_get_brands_filtered,
        get_brand_details as db_get_brand_details,
        query_ads as db_query_ads,
        flag_ad_for_review as db_flag_ad_for_review,
        flag_brand_for_review as db_flag_brand_for_review,
    )
    if _db_available():
        _USE_DB = True
        print("✅ Database store connected — using PostgreSQL for run/brand queries")
    else:
        raise ImportError("DB not reachable")
    def mf_unknown_ad_counts(): return {}
    def mf_unknown_ad_counts_by_client(): return {}
except Exception as _db_err:
    print(f"⚠️  Database store unavailable ({_db_err}), falling back to manifest_store")
    from web.manifest_store import (
        runs as mf_runs, daily_totals as mf_daily,
        brands as mf_brands, brands_by_client as mf_brands_by_client,
        unknown_ad_counts as mf_unknown_ad_counts,
        unknown_ad_counts_by_client as mf_unknown_ad_counts_by_client,
    )

# ============================================================================
# Thumbnail Generation
# ============================================================================

from PIL import Image
import io

# Get project root for cache directory
SCRAPER_HOME = os.environ.get("SCRAPER_HOME") or project_root

# Thumbnail cache directory
THUMBNAIL_CACHE = Path(SCRAPER_HOME) / "cache" / "thumbnails"
THUMBNAIL_CACHE.mkdir(parents=True, exist_ok=True)

# Track thumbnail cache statistics
_thumbnail_stats = {
    'hits': 0,      # Served from cache
    'misses': 0,    # Generated new
    'errors': 0     # Failed to generate
}

def get_thumbnail_stats():
    """Get thumbnail cache statistics."""
    total = _thumbnail_stats['hits'] + _thumbnail_stats['misses']
    hit_rate = (_thumbnail_stats['hits'] / total * 100) if total > 0 else 0
    return {
        **_thumbnail_stats,
        'total': total,
        'hit_rate': f"{hit_rate:.1f}%"
    }

def generate_thumbnail(source_path: Path, max_width: int = 800, quality: int = 85) -> Path:
    """
    Generate and cache a thumbnail for an image.
    
    Args:
        source_path: Path to original image
        max_width: Maximum width in pixels (default: 800)
        quality: JPEG quality 1-100 (default: 85)
    
    Returns:
        Path to cached thumbnail
    """
    # Create cache filename: original_name_800.jpg
    cache_filename = f"{source_path.stem}_{max_width}.jpg"
    cache_path = THUMBNAIL_CACHE / cache_filename
    
    # Return cached thumbnail if it exists and is newer than source
    if cache_path.exists():
        cache_mtime = cache_path.stat().st_mtime
        source_mtime = source_path.stat().st_mtime
        if cache_mtime >= source_mtime:
            _thumbnail_stats['hits'] += 1  # Cache hit
            return cache_path
    
    # Generate new thumbnail
    _thumbnail_stats['misses'] += 1  # Cache miss
    
    try:
        # Open image
        img = Image.open(source_path)
        
        # Convert RGBA to RGB (for PNG with transparency)
        if img.mode in ('RGBA', 'LA', 'P'):
            # Create white background
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Resize if needed
        if img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
        
        # Save as optimized JPEG
        img.save(cache_path, 'JPEG', quality=quality, optimize=True)
        
        print(f"✅ Generated thumbnail: {cache_filename} ({cache_path.stat().st_size / 1024:.1f}KB)")
        return cache_path
        
    except Exception as e:
        _thumbnail_stats['errors'] += 1  # Error
        print(f"❌ Thumbnail generation failed for {source_path.name}: {e}")
        # Return original if thumbnail generation fails
        return source_path


def _canon_brand_key(s: str | None) -> str | None:
    """Normalize incoming advertiser param to match brand_index keys."""
    if not s:
        return None
    # Try core.brands.canonicalize if available
    try:
        v = canonicalize(s)
        if v:
            return v.lower()
    except Exception:
        pass
    # Fallback: basic lowercase normalization
    return s.strip().lower()


def _parse_clients(req) -> set[str] | None:
    """
    Parse client filter from request into normalized set.
    
    Supports:
    - client=all → None (no filter)
    - client=blue_bunny → {"blue_bunny"}
    - client=blue_bunny,halo_top → {"blue_bunny", "halo_top"}
    - client=blue_bunny&client=halo_top → {"blue_bunny", "halo_top"}
    
    Returns:
        Set of client slugs, or None for "no filter"
    """
    # Gather raw values (handle both comma-separated and repeated params)
    raw_list = req.args.getlist("client")
    raw_single = req.args.get("client")
    
    items: list[str] = []
    if raw_single:
        items.append(raw_single)
    if raw_list:
        items.extend(raw_list)
    
    if not items:
        return None
    
    # Flatten comma-separated entries
    tokens: list[str] = []
    for it in items:
        tokens.extend([t.strip() for t in it.split(",") if t.strip()])
    
    if not tokens:
        return None
    
    # If any token is "all" → no client filter
    if any(t.lower() == "all" for t in tokens):
        return None
    
    # Return normalized set
    normalized = {t for t in tokens}
    return normalized or None


def _norm_clients_for_cache(clients: set[str] | None) -> str:
    """Normalize client set for cache key."""
    if not clients:
        return "all"
    return ",".join(sorted(clients))


def count_from_brand_index(retailer: str|None, clients: set[str]|None, term: str|None, start: str|None, end: str|None, advertiser_in: str) -> int:
    """Count ads using brand index without loading cards."""
    advertiser = _canon_brand_key(advertiser_in)
    if not advertiser:
        return 0
    
    index = load_brand_index()
    if not index:
        return 0
    
    entries = index.get(advertiser, [])
    total = 0
    
    for entry in entries:
        # Filter by retailer
        if retailer and entry.get("retailer") != retailer:
            continue
        
        # Filter by client set
        if clients and entry.get("client") not in clients:
            continue
        
        # Filter by date
        ts = entry.get("timestamp", "")
        day = ts[:10] if ts else ""
        if start and day < start:
            continue
        if end and day > end:
            continue
        
        # If term specified, verify keyword matches
        if term:
            json_path = entry.get("json_path")
            if json_path:
                fp = OUTPUT_ROOT / json_path
                try:
                    with open(fp, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if data.get("keyword") != term:
                        continue
                except Exception:
                    continue
        
        # Count ad indices
        total += len(entry.get("ad_indices", []))
    
    return total


def _entries_for_brand_sorted(retailer, clients, start, end, advertiser_in):
    """Get sorted list of (json_path, ad_idx, retailer, client, timestamp) for a brand."""
    advertiser = _canon_brand_key(advertiser_in)
    if not advertiser:
        return []
    
    index = load_brand_index()
    if not index:
        return []
    
    entries = index.get(advertiser, [])
    
    # Expand to individual ad references
    filtered = []
    for e in entries:
        if retailer and e["retailer"] != retailer:
            continue
        if clients and e["client"] not in clients:
            continue
        if start and e.get("timestamp") and e["timestamp"][:10] < start:
            continue
        if end and e.get("timestamp") and e["timestamp"][:10] > end:
            continue
        
        # Expand each ad index
        for i in e["ad_indices"]:
            filtered.append((e["json_path"], i, e["retailer"], e["client"], e.get("timestamp") or ""))

    # Sort by timestamp desc
    filtered.sort(key=lambda x: x[4], reverse=True)
    return filtered

app = Flask(__name__)

# ============================================================================
# In-Memory Cache (10 min TTL)
# ============================================================================
_cache = {}
_cache_ttl = 600  # seconds (10 minutes)

def _cache_key(params: dict) -> str:
    """Generate cache key from normalized filter params"""
    # Sort keys for consistent hashing
    normalized = {k: v for k, v in sorted(params.items()) if v is not None}
    key_str = json.dumps(normalized, sort_keys=True)
    return hashlib.md5(key_str.encode()).hexdigest()

def _matches_ad_type_filter(ad, types_list):
    """Shared filtering logic to ensure consistency between pre-count and card building"""
    if not types_list:
        return True

    ad_type = ad.get("type") or ad.get("ad_type") or "Main"
    # Canonicalize the ad's type and the filter values for comparison
    ad_canonical = canonicalize_ad_type(ad_type).lower()

    for req_type in types_list:
        req_canonical = canonicalize_ad_type(req_type).lower()
        if req_canonical == ad_canonical or req_canonical in ad_canonical or ad_canonical in req_canonical:
            return True
    return False

def _get_cached(key: str):
    """Get cached result if not expired"""
    if key in _cache:
        result, timestamp = _cache[key]
        if time() - timestamp < _cache_ttl:
            return result
        else:
            del _cache[key]
    return None

def _set_cache(key: str, value):
    """Store result in cache with current timestamp"""
    _cache[key] = (value, time())

# Performance monitoring: Server-Timing header
@app.before_request
def _t0():
    g._t0 = perf_counter()

@app.after_request
def _server_timing(resp):
    try:
        dur = (perf_counter() - g._t0) * 1000
        existing = resp.headers.get('Server-Timing')
        val = f"flaskTotal;dur={dur:.1f}"
        resp.headers['Server-Timing'] = f"{existing}, {val}" if existing else val
    except Exception:
        pass
    return resp

# ============================================================================
# Configuration
# ============================================================================

SCRAPER_HOME = os.environ.get("SCRAPER_HOME", project_root)
OUTPUT_ROOT = Path(os.path.join(SCRAPER_HOME, "output"))
ASSETS_ROOT = os.path.join(SCRAPER_HOME, "web", "assets")
ALLOWED_ORIGINS = set((os.environ.get("ALLOWED_ORIGINS") or "").split(",")) - {""}
API_KEY = os.environ.get("API_KEY")  # For future POST endpoints
BRAND_INDEX_FILE = OUTPUT_ROOT / "brand_index.json"

# ============================================================================
# Brand Index (for fast brand lookups)
# ============================================================================
_brand_index = None
_brand_index_loaded_at = None
_brand_index_ttl = 3600  # Reload index every hour

def load_brand_index():
    """Load brand index from disk (with caching)"""
    global _brand_index, _brand_index_loaded_at
    
    # Check if we need to reload
    now = time()
    if _brand_index is not None and _brand_index_loaded_at is not None:
        if (now - _brand_index_loaded_at) < _brand_index_ttl:
            return _brand_index
    
    # Load from disk
    if not BRAND_INDEX_FILE.exists():
        print(f"⚠️  Brand index not found: {BRAND_INDEX_FILE}")
        print(f"   Run: python3 tools/build_brand_index.py")
        return None
    
    try:
        with open(BRAND_INDEX_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        _brand_index = data.get('index', {})
        _brand_index_loaded_at = now
        
        stats = data.get('stats', {})
        print(f"✅ Brand index loaded: {stats.get('total_brands', 0):,} brands, {stats.get('ads_indexed', 0):,} ads")
        
        return _brand_index
    except Exception as e:
        print(f"❌ Error loading brand index: {e}")
        return None

def lookup_brand_files(brand: str) -> list:
    """
    Look up files containing ads for a specific brand.
    Returns list of dicts with: retailer, client, json_path, ad_indices
    """
    index = load_brand_index()
    if not index:
        return []
    
    # Canonicalize brand name for lookup
    canonical_brand = canonicalize(brand)
    if not canonical_brand:
        # Fallback to simple lowercase if canonicalize returns None
        canonical_brand = brand.strip().lower()
    else:
        canonical_brand = canonical_brand.lower()
    
    return index.get(canonical_brand, [])

# Brand assets/config
BRAND_LOGOS_DIR = Path(os.getenv("BRAND_LOGOS_DIR", os.path.join(SCRAPER_HOME, "output/brand_logos")))
BRAND_LOGO_DB_PATH = Path(os.getenv("BRAND_LOGO_DB_PATH", os.path.join(SCRAPER_HOME, "output/brand_logos/brand_logo_database.json")))
BRAND_LEXICON_PATH = Path(os.getenv("BRAND_LEXICON_PATH", os.path.join(SCRAPER_HOME, "config/brands.json")))

# ============================================================================
# Utility Functions
# ============================================================================

def to_iso_z(ts: str | None, run_id: str | None = None) -> str:
    """
    Normalize legacy timestamps to ISO 8601 Z (UTC).
    Accepts:
      - 2025-10-27T02:56:54Z  (already ISO Z)
      - 2025-10-27 02:56:54   (assume UTC)
      - 2025-10-27_02-56-54   (assume UTC)
    Fallback to run_id or now() in UTC.
    """
    ts = (ts or "").strip()
    try:
        # ISO with Z
        if re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$', ts):
            return ts
        # Space-separated UTC
        m1 = re.match(r'^(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2}):(\d{2})$', ts)
        if m1:
            dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            return dt.isoformat(timespec="seconds").replace("+00:00", "Z")
        # Underscore-separated UTC
        m2 = re.match(r'^(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})$', ts)
        if m2:
            dt = datetime.strptime(ts, "%Y-%m-%d_%H-%M-%S").replace(tzinfo=timezone.utc)
            return dt.isoformat(timespec="seconds").replace("+00:00", "Z")
    except Exception:
        pass
    # Fallback from run_id
    if run_id:
        try:
            dt = datetime.strptime(run_id, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            return dt.isoformat(timespec="seconds").replace("+00:00", "Z")
        except Exception:
            pass
    # Last resort: now UTC
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def iso_to_epoch_ms(iso_z: str) -> int:
    """Convert ISO Z timestamp to epoch milliseconds"""
    try:
        dt = datetime.fromisoformat(iso_z.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except Exception:
        return 0


def parse_utc(iso_z: str) -> datetime:
    """Parse ISO Z timestamp to datetime object"""
    return datetime.fromisoformat(iso_z.replace("Z", "+00:00"))


def utc_range_for(filter_name: str, start: str | None, end: str | None, tz_offset_minutes: int | None = None) -> tuple[datetime, datetime]:
    """
    Get UTC datetime range for filtering.
    filter_name: 'lifetime', 'mtd', 'ytd', or 'custom'
    start/end: YYYY-MM-DD strings for custom range (interpreted as local dates)
    tz_offset_minutes: JavaScript getTimezoneOffset() value (e.g., -360 for UTC-6)
                       Used to convert local dates to UTC. If not provided, assumes start/end are UTC.
    """
    now = datetime.now(timezone.utc)

    if filter_name == "lifetime":
        return datetime.min.replace(tzinfo=timezone.utc), datetime.max.replace(tzinfo=timezone.utc)

    if filter_name == "mtd":
        start_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start_dt, now

    if filter_name == "ytd":
        start_dt = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return start_dt, now

    # Custom yyyy-mm-dd range
    def parse_date_utc(d: str, tz_offset: int | None = None) -> datetime:
        # Parse the date string as a local date
        local_dt = datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc)

        # If timezone offset is provided, adjust to UTC
        # JavaScript's getTimezoneOffset returns minutes AHEAD of UTC as negative
        # E.g., -360 means UTC-6 (6 hours behind UTC)
        # So we need to ADD the offset to convert from local to UTC
        if tz_offset is not None:
            # tz_offset is minutes ahead of UTC (negative for west of UTC)
            # To convert local time to UTC, we ADD the offset
            # E.g., if local is 00:00 and offset is -360 (-6 hours),
            # then UTC is 00:00 + 6 hours = 06:00
            local_dt = local_dt + timedelta(minutes=tz_offset)

        return local_dt

    if start or end:
        # Handle cases where only start or only end is provided
        start_dt = parse_date_utc(start, tz_offset_minutes) if start else parse_date_utc(end, tz_offset_minutes)
        end_dt = parse_date_utc(end, tz_offset_minutes) if end else parse_date_utc(start, tz_offset_minutes)

        # Ensure start <= end
        if start_dt > end_dt:
            start_dt, end_dt = end_dt, start_dt

        # Inclusive end-of-day for end date
        end_dt = end_dt.replace(hour=23, minute=59, second=59)
        return start_dt, end_dt

    # Default: lifetime
    return datetime.min.replace(tzinfo=timezone.utc), datetime.max.replace(tzinfo=timezone.utc)


def brand_slug(name: str) -> str:
    """Normalize to DB's underscore keys: 'Sour Patch Kids' -> 'sour_patch_kids'"""
    return re.sub(r'[^a-z0-9]+', '_', (name or '').lower()).strip('_')


# Patterns that indicate brand-free taglines — canonicalize will spuriously match these
_TAGLINE_PREFIXES = re.compile(
    r'^(?:shop|get|buy|try|save|find|discover|introducing|experience|celebrate|'
    r'power|boost|give|make|fuel|love|hit|live|big|real|same|special|works|a |the )',
    re.IGNORECASE,
)


def _infer_brand_from_ad(ad: dict) -> str | None:
    """Attempt to recover a brand name from ad fields when the brand field is null.

    Strategies (in priority order):
    1. "By / Shop / From X" pattern in title — extract X and canonicalize.
    2. Canonicalize the full title if it isn't a generic tagline and a known brand
       is found without fuzzy ambiguity.
    3. Tile_Takeover: parse ``povid`` URL parameter whose first ``_``-separated
       segment sometimes encodes the brand name.
    Returns None when no confident match is found.
    """
    # Use core.brands.canonicalize which returns None on no match (unlike the
    # server's canonicalize_brand which falls back to the raw input string).
    from core.brands import canonicalize as _exact_canon

    title = (ad.get("title") or ad.get("message") or ad.get("headline") or "").strip()
    if title:
        # Strategy 1: "By/Shop/From/Introducing X" prefix
        prefix_m = re.match(
            r'^(?:by|shop|from|introducing|brought to you by)\s+(.+)',
            title,
            re.IGNORECASE,
        )
        if prefix_m:
            candidate = _exact_canon(prefix_m.group(1).strip())
            if candidate and not candidate.endswith("(?)"):
                return candidate

        # Strategy 2: full-title canonicalize, but reject obvious taglines
        if not _TAGLINE_PREFIXES.match(title):
            candidate = _exact_canon(title)
            if candidate and not candidate.endswith("(?)"):
                return candidate

    # Strategy 3: Tile_Takeover / Marquee_Banner — read povid first segment
    href = ad.get("href") or ""
    if href:
        povid_m = re.search(r'[?&]povid=([^&]+)', href)
        if povid_m:
            segs = povid_m.group(1).split('_')
            # Skip numeric-only segments (category IDs)
            first_word = next((s for s in segs if s and not s.isdigit() and len(s) > 2), None)
            if first_word:
                candidate = _exact_canon(first_word.replace('-', ' '))
                if candidate and not candidate.endswith("(?)"):
                    return candidate

    return None


@lru_cache(maxsize=1)
def get_brand_logo_db() -> dict:
    """Load brand logo database from JSON file"""
    if BRAND_LOGO_DB_PATH.is_file():
        try:
            return json.loads(BRAND_LOGO_DB_PATH.read_text())
        except Exception:
            return {}
    return {}


@lru_cache(maxsize=1)
def get_brand_lexicon() -> dict:
    """
    Returns {'by_name': {canonical_name: set(synonyms...)}, 'by_token': {token: canonical_name}}
    token normalization is lowercase, punctuation-stripped.
    """
    out = {"by_name": {}, "by_token": {}}
    if not BRAND_LEXICON_PATH.is_file():
        return out
    try:
        arr = json.loads(BRAND_LEXICON_PATH.read_text())
    except Exception:
        return out

    def norm_token(s: str) -> str:
        # lower, strip non-alphanumerics (keep letters/numbers only)
        return re.sub(r'[^a-z0-9]+', '', (s or '').lower())

    for entry in arr:
        cname = (entry.get("name") or "").strip()
        if not cname:
            continue
        toks = set()
        toks.add(norm_token(cname))
        for syn in entry.get("synonyms") or []:
            syn = (syn or "").strip()
            if syn:
                toks.add(norm_token(syn))
        out["by_name"].setdefault(cname, set()).update(toks)
        for t in toks:
            out["by_token"][t] = cname
    return out


def canonicalize_brand(raw: str | None) -> str | None:
    """
    Map raw brand to canonical name via brands.json (names + synonyms).
    Uses case-insensitive, punctuation-insensitive matching.
    Falls back to original raw brand if not found in lexicon.
    """
    from utils.brand_utils import normalize_brand_for_matching

    raw = (raw or "").strip()
    if not raw:
        return None

    # Load brands.json directly for case-insensitive matching
    try:
        brands_arr = json.loads(BRAND_LEXICON_PATH.read_text())
    except Exception:
        return raw

    # Use normalization for lexicon matching
    normalized = normalize_brand_for_matching(raw)

    # Check all canonical names and synonyms
    for entry in brands_arr:
        canonical_name = entry.get("name", "").strip()
        if not canonical_name:
            continue

        if normalize_brand_for_matching(canonical_name) == normalized:
            return canonical_name

        for synonym in entry.get("synonyms", []):
            if normalize_brand_for_matching(synonym) == normalized:
                return canonical_name

    # fallback: return original raw brand if not found in lexicon
    return raw


# Canonical ad type mapping: raw DB values → single canonical display name
# Multiple raw values can map to the same canonical name (deduplication)
_AD_TYPE_CANONICAL = {
    "sbv":                    "Sponsored Brand Video",
    "sponsored_brand_video":  "Sponsored Brand Video",
    "shoppable_video_ad":     "Shoppable Video Ad",
    "shoppable_ad_item":      "Shoppable Ad Item",
    "toa":                    "TOA",
    "sba":                    "SBA",
    "sponsored_brand":        "Sponsored Brand",
    "sponsored_brand_card":   "Sponsored Brand Card",
    "sponsored_product":      "Sponsored Product",
    "listingpagebannerad":    "Listing Page Banner Ad",
    "shoppable_display_ad":   "Shoppable Display Ad",
    "sponsored_display":      "Sponsored Display",
    "sponsored_carousel":     "Sponsored Carousel",
    "curatedcarousel":        "Curated Carousel",
    "carousel":               "Carousel",
    "skyscraper":             "Skyscraper",
    "tile_takeover":          "Tile Takeover",
    "sponsored_logo":         "Sponsored Logo",
    "gallery_cards":          "Gallery Cards",
    "product_listing":        "Product Listing",
}


def canonicalize_ad_type(ad_type: str | None) -> str:
    """
    Map a raw ad_type value to its canonical display name.
    Handles case differences, underscores, hyphens, etc.
    Falls back to a cleaned-up version if not in the mapping.
    """
    if not ad_type:
        return ""
    key = ad_type.strip().lower().replace("-", "_").replace(" ", "_")
    canonical = _AD_TYPE_CANONICAL.get(key)
    if canonical:
        return canonical
    # Fallback: replace underscores/hyphens with spaces, title-case
    return ad_type.replace("_", " ").replace("-", " ").strip()


def type_label_for(ad_type: str | None) -> str:
    """
    Convert ad type to human-readable label.
    Uses canonical mapping for known types, falls back to simple cleanup.
    """
    return canonicalize_ad_type(ad_type)


# Blocked brands - ad types and house ads that should never be counted as real brand ads
# IMPORTANT: "kroger" here refers to KROGER HOUSE ADS (retailer marketing materials)
# These are identified by exact message text matching and should be excluded from:
# - Ad counts and analysis
# - Brand performance metrics
# - Frontend display (filtered out by API)
BLOCKED_BRANDS = {
    "display ad",
    "shoppable display ad",
    "shoppable video ad",
    "video ad",
    "sponsored product",
    "sponsored products",
    "sponsored brand",
    "sponsored brand video",
    "carousel",
    "skyscraper",
    "toa",
    "sba",
    "sbv",
    "top banner",
    "kroger",  # Kroger house ads (retailer marketing, not brand ads)
    "walmart",  # Walmart house ads (retailer marketing, not brand ads)
    "instacart",  # Instacart house ads (retailer marketing, not brand ads)
    "tile takeover",
    "featured brand",
    "native ad",
    "display ads",
    "video ads",
    "top of aisle",
    "shelf banner",
    "category banner",
    "unknown",
    "n/a",
}


def normalize_brand(brand: str | None, ad_type: str | None) -> str | None:
    """
    Remove false 'brands' that are actually ad types or placeholders.
    """
    if not brand:
        return None
    b = brand.strip().lower()
    t = type_label_for(ad_type).lower()
    if b == t:
        return None
    if b in BLOCKED_BRANDS:
        return None
    if "shoppable" in b:
        return None
    return brand.strip()


def brand_logo_url_for(brand_canonical: str | None, retailer: str | None) -> str | None:
    """
    Resolve logo file from brand_logo_database.json (by slug of canonical name).
    """
    if not brand_canonical:
        return None
    db = get_brand_logo_db()
    brands = db.get("brands") or {}
    rec = brands.get(brand_slug(brand_canonical))
    if not rec:
        return None
    allowed = rec.get("retailers")
    if allowed and retailer and retailer not in allowed:
        return None
    raw = (rec.get("logo_file") or "").strip()
    if not raw:
        return None
    # Normalize stored path: drop optional "brand_logos/" prefix and treat the
    # remainder as a path relative to BRAND_LOGOS_DIR. This allows values like
    # "verified/foo.png", "unverified/foo.png", or just "foo.png".
    if raw.startswith("brand_logos/"):
        rel = raw.split("/", 1)[1]
    else:
        rel = raw
    if not rel:
        return None
    path = (BRAND_LOGOS_DIR / rel)
    if not path.is_file():
        return None
    return f"/api/brand_logo/{rel}"


def is_blocked_brand(brand_name: str | None) -> bool:
    """
    Check if a brand name is actually an ad type (in blocked list).
    Returns True if brand should be filtered out.
    """
    if not brand_name:
        return True
    normalized = brand_name.lower().strip()
    return normalized in BLOCKED_BRANDS or type_label_for(normalized) in BLOCKED_BRANDS


def resolve_image_path(ad: dict) -> str | None:
    """
    Canonical first, then legacy fallbacks. Returns a path relative to client root:
      e.g., 'SBA/walmart__brand__sba__client__kw__D2025-10-27_T13-22.33_1.png'.
    """
    # Canonical
    p = ad.get("image_path") or ad.get("screenshot")
    if p:
        return p
    # Legacy per-type fallbacks (Walmart, Kroger, etc.)
    for k, v in ad.items():
        if isinstance(k, str) and k.endswith("_image_path") and isinstance(v, str) and v:
            return v
    return None


def client_root_for(retailer: str, client: str) -> Path:
    """Get client root directory"""
    return Path(OUTPUT_ROOT) / retailer / client


def find_image_file(retailer: str, client: str, req_relpath: str) -> tuple[Path | None, str | None]:
    """
    Try to locate the requested image for a retailer/client.
    Returns (absolute_path, relative_path_from_client) or (None, None).
    
    Strategy:
      1) Exact match under client_root
      2) Exact match under nested runs/* directories (Walmart)
      3) Fuzzy match by filename under allowed ad folders (top-level) then nested
    """
    cr = client_root_for(retailer, client)
    req_relpath = req_relpath.strip().lstrip("/")

    # 1) Exact under client root
    p1 = cr / req_relpath
    if p1.is_file():
        return p1, str(Path(req_relpath))

    # 2) Exact under nested runs/<run_id>/
    runs_dir = cr / "runs"
    if runs_dir.is_dir():
        candidates = list(runs_dir.glob(f"*/{req_relpath}"))
        for c in candidates:
            if c.is_file():
                # Return path relative to client root (flattened for API URL)
                rel = str(req_relpath)
                return c, rel

    # 3) Fuzzy by filename
    req_name = Path(req_relpath).name.lower()
    try:
        allowed = allowed_subdirs(retailer)  # e.g., {'SBA','SBV','Tile_Takeover','Main','runs'}
    except ValueError:
        allowed = {'Main', 'runs'}
    
    # Preferred: ad-type folders (not 'runs')
    scan_dirs = [cr / d for d in allowed if d != "runs" and (cr / d).is_dir()]
    
    # Also scan nested runs/<run_id>/<folder>/*
    if runs_dir.is_dir():
        for rd in runs_dir.iterdir():
            if rd.is_dir():
                for d in allowed:
                    if d == "runs":
                        continue
                    psub = rd / d
                    if psub.is_dir():
                        scan_dirs.append(psub)

    # Find best match by exact filename first, then loose contains
    exact_hits = []
    loose_hits = []
    for d in scan_dirs:
        for f in d.glob("*"):
            if not f.is_file():
                continue
            name = f.name.lower()
            if name == req_name:
                exact_hits.append(f)
            elif req_name and (req_name in name or name in req_name):
                loose_hits.append(f)

    # Prefer exact; else first loose
    pick = exact_hits[0] if exact_hits else (loose_hits[0] if loose_hits else None)

    # 4) Brand+timestamp fuzzy match for corrupted filenames
    #    Some JSON image_paths have extra brand names injected into the middle
    #    (e.g. "magic_spoon_optimum_nutritino" instead of "magic_spoon").
    #    Match on retailer__brand prefix + D<date>_T<time>_<idx>.ext suffix.
    if not pick:
        import re
        ts_match = re.search(r'(D\d{4}-\d{2}-\d{2}_T\d{2}-\d{2}\.\d{2}_\d+\.\w+)$', req_name)
        name_parts = req_name.split('__')
        if ts_match and len(name_parts) >= 2:
            ts_suffix = ts_match.group(1).lower()
            brand_prefix = (name_parts[0] + '__' + name_parts[1]).lower()
            req_folder = Path(req_relpath).parts[0].lower() if len(Path(req_relpath).parts) > 1 else ""
            for d in scan_dirs:
                if req_folder and d.name.lower() != req_folder:
                    continue
                for f in d.glob("*"):
                    if not f.is_file():
                        continue
                    fn = f.name.lower()
                    if fn.startswith(brand_prefix) and fn.endswith(ts_suffix):
                        pick = f
                        break
                if pick:
                    break

    if pick:
        # Build relative path from client root (folder/filename)
        try:
            rel = str(pick.relative_to(cr))
        except Exception:
            # When under runs/*/, return folder/filename if possible
            rel = f"{pick.parent.name}/{pick.name}"
        return pick, rel

    return None, None


def is_video_filename(name: str) -> bool:
    """Check if filename is a video file"""
    return str(name).lower().endswith((".mp4", ".webm", ".mov", ".m4v"))


def find_poster_for_video(retailer: str, client: str, rel_video_path: str) -> str | None:
    """
    Try to find a poster image with the same basename as the video.
    Looks in the same folder and in Main/.
    Returns relative path from client root if found, else None.
    """
    base = Path(rel_video_path).with_suffix("")
    # same folder
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        candidate = f"{base}{ext}"
        f2, r2 = find_image_file(retailer, client, candidate)
        if f2:
            return r2
    # fallback: Main/<basename>.png|.jpg...
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        candidate = f"Main/{base.name}{ext}"
        f2, r2 = find_image_file(retailer, client, candidate)
        if f2:
            return r2
    return None


def build_media_urls_for_ad(retailer: str, client: str, ad: dict) -> dict:
    """
    Returns a dict with:
      image_url: str  (always used for grid card)
      video_url: str  (optional; used in modal detail)
      poster_url: str (optional; used in video tag poster)
    """
    media = {}

    rel = (ad.get("image_path") or ad.get("screenshot"))
    if not rel:
        # legacy fallback keys
        for k, v in ad.items():
            if isinstance(k, str) and k.endswith("_image_path") and isinstance(v, str) and v:
                rel = v
                break

    # Debug: log if we found a path
    if rel:
        print(f"[build_media_urls_for_ad] {retailer}/{client}: Found path: {rel}")
    else:
        print(f"[build_media_urls_for_ad] {retailer}/{client}: NO path found in ad")

    # If we have a declared path
    if rel:
        if is_video_filename(rel):
            # Try to attach video_url and find a poster for the image grid
            f, r = find_image_file(retailer, client, rel)
            if f:
                media["video_url"] = f"/api/video/{retailer}/{client}/{r}"
                poster_rel = find_poster_for_video(retailer, client, r)
                if poster_rel:
                    media["image_url"] = f"/api/image/{retailer}/{client}/{poster_rel}"
                    media["poster_url"] = f"/api/image/{retailer}/{client}/{poster_rel}"
            # If no poster found, we will try CDN filename fallback below
        else:
            # It's an image
            f, r = find_image_file(retailer, client, rel)
            if f:
                media["image_url"] = f"/api/image/{retailer}/{client}/{r}"

                # Also search for companion video file with same base name
                # For SBV ads: image is "kroger__brand__sbv__..._0.png" and video is "kroger__brand__sbv__..._0.mp4"
                base_name = Path(r).stem  # Remove extension (e.g., "kroger__brand__sbv__..._0")
                video_file = f"{base_name}.mp4"
                video_f, video_r = find_image_file(retailer, client, video_file)
                if video_f:
                    media["video_url"] = f"/api/video/{retailer}/{client}/{video_r}"
                else:
                    print(f"[build_media_urls] Video file not found: {video_file} for image: {rel}")

    # Fallbacks: if image_url still missing and ad has CDN url, try fuzzy by filename
    if "image_url" not in media:
        cdn = ad.get("image_url")
        if isinstance(cdn, str) and cdn.strip():
            name = Path(cdn.split("?")[0]).name
            if name and not is_video_filename(name):
                f, r = find_image_file(retailer, client, name)
                if f:
                    media["image_url"] = f"/api/image/{retailer}/{client}/{r}"

                    # Also search for companion video file with same base name
                    if "video_url" not in media:
                        base_name = Path(r).stem
                        video_file = f"{base_name}.mp4"
                        video_f, video_r = find_image_file(retailer, client, video_file)
                        if video_f:
                            media["video_url"] = f"/api/video/{retailer}/{client}/{video_r}"

    # Video fallback: prioritize local video_path over CDN video_url
    if "video_url" not in media:
        # First try video_path (local file path)
        local_v = ad.get("video_path")
        if isinstance(local_v, str) and local_v.strip():
            f, r = find_image_file(retailer, client, local_v)
            if f:
                media["video_url"] = f"/api/video/{retailer}/{client}/{r}"
                poster_rel = find_poster_for_video(retailer, client, r)
                if poster_rel:
                    media["poster_url"] = f"/api/image/{retailer}/{client}/{poster_rel}"
        
        # Then try CDN video_url or image_url as filename hint
        if "video_url" not in media:
            cdn_v = ad.get("video_url") or ad.get("image_url")
            if isinstance(cdn_v, str) and is_video_filename(cdn_v):
                name = Path(cdn_v.split("?")[0]).name
                f, r = find_image_file(retailer, client, name)
                if f:
                    media["video_url"] = f"/api/video/{retailer}/{client}/{r}"
                    poster_rel = find_poster_for_video(retailer, client, r)
                    if poster_rel:
                        media["poster_url"] = f"/api/image/{retailer}/{client}/{poster_rel}"

    # Last resort: proxy CDN URL if no local file found
    # This handles Kroger TOA/Skyscraper ads that only have remote URLs
    if "image_url" not in media:
        cdn = ad.get("image_url")
        if isinstance(cdn, str) and cdn.strip():
            # If it's a relative path (starts with /), prepend Kroger domain
            if cdn.startswith("/"):
                full_url = f"https://www.kroger.com{cdn}"
            else:
                full_url = cdn

            # Proxy through Express backend to handle CORS and caching
            media["image_url"] = f"/api/proxy-image?url={quote(full_url, safe='')}"

    return media


def build_image_url_for_ad(retailer: str, client: str, ad: dict) -> str | None:
    """
    DEPRECATED: Use build_media_urls_for_ad() instead.
    Build image URL for an ad, trying canonical path first, then fuzzy matching.
    Returns /api/image/{retailer}/{client}/{path} or None if not resolvable.
    """
    media = build_media_urls_for_ad(retailer, client, ad)
    return media.get("image_url")

# ============================================================================
# Fail-Closed Image Resolution (Always Returns Image URL)
# ============================================================================

# Folder synonyms (plural ��� singular etc.)
FOLDER_SYNONYMS = {
    "Shoppable_Display_Ads": "Shoppable_Display_Ad",
    "Shoppable_Video_Ads": "Shoppable_Video_Ad",
    "Display_Ads": "Display_Ad",
}

def normalize_relpath(rel: str) -> str:
    """Normalize folder names using synonyms (plural/singular)"""
    parts = rel.split("/", 1)
    head = parts[0]
    tail = parts[1] if len(parts) > 1 else ""
    head = FOLDER_SYNONYMS.get(head, head)
    return f"{head}/{tail}" if tail else head

def find_file_fallback(root: Path, rel: str) -> Path | None:
    """
    Try to find the file even if rel has wrong folder (plural/singular) or casing differences.
    Last resort: search by basename under client folder.
    """
    # 1) exact normalized
    rel_norm = normalize_relpath(rel)
    p = (root / rel_norm)
    if p.is_file():
        return p

    # 2) try by basename anywhere under client
    base = Path(rel).name
    if base:
        for pp in root.rglob(base):
            if pp.is_file():
                return pp

    return None

def build_image_fields(retailer: str, client: str, ad: dict) -> tuple[str, bool, str | None, str | None]:
    """
    Returns (image_url: str, has_image: bool, debug_path: str|None, skip_reason: str|None)
    Always returns a non-empty image_url (real file or placeholder).
    Handles local files, CDN/remote URLs, and fallback to placeholder.
    """
    from urllib.parse import quote_plus, quote

    rel = ad.get("image_path") or ad.get("screenshot") or ad.get("display_image_path")
    client_root = (OUTPUT_ROOT / retailer / client)

    # 1) Try to resolve local file first
    if rel:
        p = find_file_fallback(client_root, rel)
        if p and p.is_file():
            rel_url = str(p.relative_to(client_root)).replace("\\", "/")
            return (f"/api/image/{retailer}/{client}/{rel_url}", True, rel, None)

    # 2) If no local file, try to use the media URL building logic (handles CDN/remote URLs)
    media = build_media_urls_for_ad(retailer, client, ad)
    if "image_url" in media:
        return (media["image_url"], True, rel, None)

    # 3) Last resort: return placeholder with debug context
    ad_id = ad.get("id") or ad.get("type") or "noid"
    label = f"{retailer}/{client}/{ad_id}"
    return (f"/api/image/placeholder?text={quote_plus(label)}", False, rel, "file_not_found")

# ============================================================================
# Security & CORS
# ============================================================================

def _is_allowed_origin(origin: str) -> bool:
    """Check if origin is allowed for CORS with credentials"""
    if not origin:
        return False
    if origin.startswith("http://localhost") or origin.startswith("http://127.0.0.1"):
        return True
    if origin.startswith("https://") and "ngrok" in origin:
        return True
    if ALLOWED_ORIGINS:
        return origin in ALLOWED_ORIGINS
    return False  # strict when ALLOWED_ORIGINS set

@app.route("/api/<path:_any>", methods=["OPTIONS"])
def cors_preflight(_any):
    """Handle CORS preflight requests for all /api/* routes"""
    origin = request.headers.get("Origin", "")
    resp = make_response(("", 204))
    
    # Origin + credentials must be set here
    if _is_allowed_origin(origin):
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Credentials"] = "true"
        resp.headers["Vary"] = "Origin"
    else:
        # If you really must allow everyone, do not send credentials with *
        resp.headers["Access-Control-Allow-Origin"] = "*"
        # No credentials header with '*'
    
    # Echo requested headers; otherwise Chrome rejects
    acrh = request.headers.get("Access-Control-Request-Headers", "")
    resp.headers["Access-Control-Allow-Headers"] = acrh or "Content-Type,Authorization,ngrok-skip-browser-warning"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
    resp.headers["Access-Control-Max-Age"] = "86400"
    return resp

@app.after_request
def after_request(resp):
    """Handle CORS on every response (including 204 OPTIONS)"""
    origin = request.headers.get("Origin", "")
    
    if _is_allowed_origin(origin):
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Credentials"] = "true"
        resp.headers["Vary"] = "Origin"
    else:
        resp.headers["Access-Control-Allow-Origin"] = "*"
        # Do NOT set credentials when using '*'
    
    # CORP header to prevent ORB blocking
    resp.headers.setdefault("Cross-Origin-Resource-Policy", "cross-origin")
    
    # Echo preflight-requested headers if present; else defaults
    acrh = request.headers.get("Access-Control-Request-Headers", "")
    resp.headers["Access-Control-Allow-Headers"] = acrh or "Content-Type,Authorization,ngrok-skip-browser-warning"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
    resp.headers["Access-Control-Max-Age"] = "86400"
    return resp

def require_api_key():
    """Validate API key for write operations (future use)"""
    key = (request.headers.get("Authorization") or "").replace("Bearer ", "")
    if API_KEY and key != API_KEY:
        return jsonify({"error": "unauthorized"}), 401
    return None

# ============================================================================
# Path Helpers (Retailer-Aware)
# ============================================================================

# Ad type to leaf folder mapping
LEAF_MAP = {
    "toa": "TOA",
    "skyscraper": "Skyscraper",
    "carousel": "Carousel",
    "curatedcarousel": "Carousel",  # normalize synonyms
    "sponsored_carousel": "Carousel",
    "banner": "Display_Ads",
    "display_ads": "Display_Ads",
    "hero": "Hero",
    "sba": "SBA",
    "sponsored_brand": "SBA",
    "sbv": "SBV",
    "sponsored_brand_video": "SBV",
    "tile_takeover": "Tile_Takeover",
    "sponsored_product": "Sponsored_Product",
    "sponsored_products": "Sponsored_Product",
    "gallery_cards": "Gallery_Cards",
    "gallery_card": "Gallery_Cards",
}

# Extension preference order
EXT_PREF = [".png", ".jpg", ".jpeg", ".webp"]

def _safe_join(*parts) -> str:
    """Safely join path parts and prevent directory traversal"""
    p = os.path.normpath(os.path.join(*parts))
    output_norm = os.path.normpath(OUTPUT_ROOT)
    if not p.startswith(output_norm):
        raise ValueError("path escape detected")
    return p

def leaf_for(ad_type: str) -> str:
    """
    Map ad_type to the correct leaf folder name.
    Normalizes variations and synonyms to canonical folder names.
    """
    key = (ad_type or "").strip().lower().replace(" ", "").replace("_", "")
    return LEAF_MAP.get(key, "Display_Ads")

def _image_response(filepath: str):
    """
    Serve an image file with proper MIME type and CORS/CORP headers.
    Prevents ORB (Opaque Response Blocking) by ensuring correct headers.
    """
    mime = mimetypes.guess_type(filepath)[0] or "application/octet-stream"
    
    # Only serve real images
    if not mime.startswith("image/"):
        return jsonify({"error": "not an image", "path": filepath, "mime": mime}), 415
    
    resp = make_response(send_file(filepath, mimetype=mime, conditional=True))
    
    # CORS/CORP hardening for images
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
    
    # Cache with revalidation - allows browser to check for updates
    # Use ETag from file modification time for efficient revalidation
    resp.headers["Cache-Control"] = "public, max-age=3600, must-revalidate"
    
    return resp

def find_image_rel(output_root: str, retailer: str, client: str, leaf_hint: str, basename: str) -> str | None:
    """
    Find the correct relative path for an image file.
    
    Returns: Relative path like 'Carousel/foo.jpg', or None if not found.
    
    Strategy:
    1. Try the hinted leaf with preferred extensions
    2. Try all allowed leaves with all extensions for this basename
    """
    # Get allowed subdirs for this retailer
    try:
        allowed_leaves = allowed_subdirs(retailer)
    except ValueError:
        allowed_leaves = ["TOA", "Skyscraper", "Carousel", "Display_Ads", "SBA", "SBV", "Tile_Takeover"]
    
    # 1) Try the hinted leaf with preferred extensions
    for ext in EXT_PREF:
        try:
            cand = _safe_join(output_root, retailer, client, leaf_hint, basename + ext)
            if os.path.isfile(cand):
                return f"{leaf_hint}/{basename}{ext}"
        except (ValueError, OSError):
            continue
    
    # 2) Try all leaves/extensions for this basename
    for leaf in allowed_leaves:
        for ext in EXT_PREF:
            try:
                cand = _safe_join(output_root, retailer, client, leaf, basename + ext)
                if os.path.isfile(cand):
                    return f"{leaf}/{basename}{ext}"
            except (ValueError, OSError):
                continue
    
    return None

def list_retailers():
    """List all retailers with output directories"""
    try:
        # Filter out non-retailer directories
        # System directories and legacy brand directories
        exclude = {
            'runs', 'brand_logos', '.DS_Store', '__pycache__',
            # Legacy brand directories (should be moved under retailers)
            'Proactiv', 'land_o_frost', 'pickle'
        }
        return sorted([
            d for d in os.listdir(OUTPUT_ROOT)
            if os.path.isdir(os.path.join(OUTPUT_ROOT, d)) 
            and not d.startswith('.') 
            and d not in exclude
        ])
    except Exception:
        return []

def list_clients(retailer: str):
    """List all clients for a retailer"""
    base = os.path.join(OUTPUT_ROOT, retailer)
    try:
        return sorted([
            d for d in os.listdir(base)
            if os.path.isdir(os.path.join(base, d)) and not d.startswith('.')
        ])
    except Exception:
        return []

def parse_retailer_client_from_path(p: str):
    """Extract retailer and client from a path"""
    parts = Path(p).resolve().parts
    if "output" in parts:
        i = parts.index("output")
        if i + 2 < len(parts):
            return parts[i+1], parts[i+2]
    return None, None

def runs_dir(retailer, client):
    """Get runs directory for retailer/client"""
    return os.path.join(OUTPUT_ROOT, retailer, client, "runs")

def subdir(retailer, client, leaf):
    """Get subdirectory for retailer/client"""
    return os.path.join(OUTPUT_ROOT, retailer, client, leaf)

def subdir_for(retailer: str, ad_type: str) -> str:
    """
    Map ad type to the correct subdirectory for a retailer.
    Returns empty string if no mapping found (fallback to search).
    """
    r = (retailer or "").lower()
    t = (ad_type or "").strip().lower()
    if r == "kroger":
        if "skyscraper" in t: return "Skyscraper"
        if "toa" in t: return "TOA"
        if "carousel" in t: return "Carousel"
        if "display" in t: return "Display_Ads"
    elif r == "instacart":
        if "shoppable video" in t: return "Shoppable_Video_Ads"
        if "shoppable display" in t: return "Shoppable_Display_Ads"
        if "display" in t: return "Display_Ads"
    elif r == "amazon":
        if "skyscraper" in t: return "Skyscraper"
        if "toa" in t or "sponsored brand" in t: return "TOA"
        if "carousel" in t or "sponsored product" in t: return "Carousel"
    elif r == "walmart":
        if "sbv" in t or "video" in t: return "SBV"
        if "sba" in t or "brand" in t: return "SBA"
        if "tile" in t or "takeover" in t: return "Tile_Takeover"
        if "gallery" in t or "card" in t: return "Gallery_Cards"
        if "top" in t or "banner" in t: return "Top_Banner"
    return ""  # fallback: let /api/image search allowed subdirs

# ============================================================================
# API Endpoints
# ============================================================================

@app.route("/")
def index():
    """API documentation"""
    return jsonify({
        "name": "Retail Ad Monitor API",
        "version": "2.0",
        "description": "Retailer-aware REST API for Builder.io integration",
        "endpoints": {
            "GET /api/retailers": "List all retailers",
            "GET /api/clients?retailer=<retailer>": "List clients for a retailer",
            "GET /api/runs?retailer=<retailer>&client=<client>": "List runs for a client",
            "GET /api/terms?retailer=<retailer>&client=<client>": "List search terms for a client",
            "GET /api/advertisers?retailer=<retailer>&client=<client>": "List all advertisers/brands for a client",
            "GET /api/ads/cards?retailer=<retailer>&client=<client>&term=<term>&advertiser=<brand>&page=1&page_size=24": "Get ad cards with filtering",
            "GET /api/image/<retailer>/<client>/<filename>": "Serve ad image",
            "GET /api/video/<retailer>/<client>/<filename>": "Serve ad video (mp4, webm, mov, m4v)"
        },
        "features": {
            "co_branded_ads": "Supports multiple advertisers per ad (e.g., Herdez + Jennie-O)",
            "filename_parsing": "Extracts advertisers from new taxonomy: retailer__advertiser(s)__ad_type__...",
            "advertiser_filtering": "Filter ads by brand name using ?advertiser=<brand>",
            "advertiser_array": "Each ad card includes 'advertisers' array for multi-brand support"
        },
        "environment": {
            "SCRAPER_HOME": str(SCRAPER_HOME),
            "OUTPUT_ROOT": str(OUTPUT_ROOT),
            "ALLOWED_ORIGINS": list(ALLOWED_ORIGINS) if ALLOWED_ORIGINS else ["*"],
            "API_KEY_SET": bool(API_KEY)
        }
    })

@app.route("/api/ping", methods=["GET"])
def api_ping():
    """Simple ping endpoint for CORS testing and health checks"""
    return jsonify({"ok": True, "timestamp": datetime.now().isoformat()})

@app.route("/api/retailers", methods=["GET"])
def api_retailers():
    """List all retailers"""
    retailers = list_retailers()
    return jsonify({
        "retailers": retailers,
        "count": len(retailers)
    })

@app.route("/api/clients", methods=["GET"])
def api_clients():
    """List clients for a retailer"""
    retailer = (request.args.get("retailer") or "").strip().lower()
    if not retailer:
        return jsonify({"error": "retailer parameter required"}), 400
    
    clients = list_clients(retailer)
    return jsonify({
        "retailer": retailer,
        "clients": clients,
        "count": len(clients)
    })

@app.route("/api/runs", methods=["GET"])
def api_runs():
    """List runs and basic metadata for a client"""
    retailer = (request.args.get("retailer") or "").strip().lower()
    client = (request.args.get("client") or "").strip()
    
    if not (retailer and client):
        return jsonify({"error": "retailer and client parameters required"}), 400
    
    rdir = runs_dir(retailer, client)
    
    if not os.path.isdir(rdir):
        return jsonify({
            "retailer": retailer,
            "client": client,
            "runs": [],
            "count": 0
        })
    
    # Find all run_results JSON files (handle both flat and nested structures)
    files = []
    for item in os.listdir(rdir):
        item_path = os.path.join(rdir, item)
        if os.path.isfile(item_path) and item.startswith("run_results_") and item.endswith(".json"):
            files.append((item, item_path))
        elif os.path.isdir(item_path):
            # Check subdirectories (Walmart structure)
            for subitem in os.listdir(item_path):
                if subitem.startswith("run_results_") and subitem.endswith(".json"):
                    files.append((subitem, os.path.join(item_path, subitem)))
    
    # Sort by filename (most recent first)
    files = sorted(files, key=lambda x: x[0], reverse=True)
    
    runs = []
    for fn, fpath in files[:200]:  # Limit to 200 most recent
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Extract and normalize timestamp
            raw_ts = data.get("timestamp") or data.get("ts") or data.get("date")
            run_id = data.get("run_id")
            # Try to extract run_id from filename if not in JSON
            if not run_id:
                run_id_match = re.search(r'(\d{14})', fn)
                if run_id_match:
                    run_id = run_id_match.group(1)
            
            iso_ts = to_iso_z(raw_ts, run_id)
            epoch_ms = iso_to_epoch_ms(iso_ts)
            
            keyword = data.get("keyword") or data.get("search_term") or data.get("term")
            
            # Count ads
            ads_count = 0
            if "ads" in data:
                ads_count = len(data["ads"])
            elif "results" in data:
                for result in data.get("results", []):
                    ads_count += len(result.get("ads", []))
            else:
                ads_count = data.get("count", 0)
            
            runs.append({
                "file": fn,
                "timestamp": iso_ts,  # Normalized ISO Z
                "timestamp_ms": epoch_ms,  # Epoch milliseconds
                "keyword": keyword,
                "url": data.get("url") or data.get("search_url") or data.get("srp_url"),
                "ads_count": ads_count,
                "retailer": data.get("retailer", retailer)
            })
        except Exception as e:
            print(f"Error loading {fn}: {e}")
            pass
    
    return jsonify({
        "retailer": retailer,
        "client": client,
        "runs": runs,
        "count": len(runs)
    })

@app.route("/api/terms", methods=["GET"])
def api_terms():
    """List available search terms for a client"""
    retailer = (request.args.get("retailer") or "").strip().lower()
    client = (request.args.get("client") or "").strip()
    
    if not (retailer and client):
        return jsonify({"error": "retailer and client parameters required"}), 400
    
    rdir = runs_dir(retailer, client)
    terms = set()
    
    if os.path.isdir(rdir):
        # Handle both flat and nested structures
        for item in os.listdir(rdir):
            item_path = os.path.join(rdir, item)
            files_to_check = []
            
            if os.path.isfile(item_path) and item.startswith("run_results_") and item.endswith(".json"):
                files_to_check.append(item_path)
            elif os.path.isdir(item_path):
                # Check subdirectories (Walmart structure)
                for subitem in os.listdir(item_path):
                    if subitem.startswith("run_results_") and subitem.endswith(".json"):
                        files_to_check.append(os.path.join(item_path, subitem))
            
            for fpath in files_to_check:
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    kw = (data.get("keyword") or data.get("search_term") or data.get("term") or "").strip()
                    if kw:
                        terms.add(kw)
                except Exception:
                    pass
    
    return jsonify({
        "retailer": retailer,
        "client": client,
        "terms": sorted(terms),
        "count": len(terms)
    })

@app.route("/api/advertisers", methods=["GET"])
def api_advertisers():
    """
    List all unique advertisers/brands for a client
    
    Query params:
    - retailer (required): retailer slug
    - client (required): client name
    """
    retailer = (request.args.get("retailer") or "").strip().lower()
    client = (request.args.get("client") or "").strip()
    
    if not (retailer and client):
        return jsonify({"error": "retailer and client parameters required"}), 400
    
    rdir = runs_dir(retailer, client)
    advertisers = set()
    
    if os.path.isdir(rdir):
        for item in os.listdir(rdir):
            item_path = os.path.join(rdir, item)
            files_to_check = []
            
            if os.path.isfile(item_path) and item.startswith("run_results_") and item.endswith(".json"):
                files_to_check.append(item_path)
            elif os.path.isdir(item_path):
                # Check subdirectories (Walmart structure)
                for subitem in os.listdir(item_path):
                    if subitem.startswith("run_results_") and subitem.endswith(".json"):
                        files_to_check.append(os.path.join(item_path, subitem))
            
            for fpath in files_to_check:
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    # Extract advertisers from all ads
                    ads = []
                    if "results" in data:
                        for result in data["results"]:
                            ads.extend(result.get("ads", []))
                    else:
                        ads = data.get("ads", [])
                    
                    for ad in ads:
                        # Get advertisers array
                        ad_advertisers = ad.get("advertisers", [])
                        if ad_advertisers:
                            # Canonicalize brand names
                            canonical_names = [canonicalize(adv) or adv for adv in ad_advertisers]
                            advertisers.update(canonical_names)
                        else:
                            # Fallback to legacy fields
                            legacy = ad.get("brand") or ad.get("advertiser")
                            if legacy:
                                canonical = canonicalize(legacy) or legacy
                                advertisers.add(canonical)
                except Exception:
                    pass
    
    return jsonify({
        "retailer": retailer,
        "client": client,
        "advertisers": sorted(advertisers),
        "count": len(advertisers)
    })


@app.route("/api/stats/summary", methods=["GET"])
def api_stats_summary():
    """
    Fast summary endpoint — returns total cards, brand counts, and top brand
    in a single call using only the run manifest. No JSON file loading.

    Query params:
    - retailers (optional): comma-separated list or "all" (default: "all")
    - client (optional): client name or "all" (default: "all")

    Returns: {
      totalCards: number,
      activeBrands: number,
      topBrand: {brand: str, count: number, percentage: number} | null,
      brands: [{brand, count, percentage}, ...],
      builtAt: str | null
    }
    """
    from utils.brand_utils import normalize_brand_for_matching

    retailers_param = (request.args.get("retailers") or "all").strip().lower()
    clients = _parse_clients(request)

    # Determine which retailers to query
    if retailers_param == "all":
        retailers_to_query = list(mf_brands().keys())
    else:
        retailers_to_query = [r.strip() for r in retailers_param.split(",")]

    # ── Total cards from manifest runs ──
    total_cards = 0
    for r in mf_runs():
        if retailers_param != "all" and r["retailer"] not in retailers_to_query:
            continue
        if clients and r["client"] not in clients:
            continue
        total_cards += int(r.get("ad_count") or 0)

    # ── Brands from pre-computed manifest data ──
    brand_counts = {}
    brand_display = {}

    if clients:
        precomputed_by_client = mf_brands_by_client()
        for retailer in retailers_to_query:
            retailer_data = precomputed_by_client.get(retailer, {})
            for client in clients:
                client_brands = retailer_data.get(client, [])
                for b in client_brands:
                    norm_key = normalize_brand_for_matching(b["brand"])
                    if norm_key not in brand_counts:
                        brand_counts[norm_key] = 0
                        brand_display[norm_key] = b["brand"]
                    brand_counts[norm_key] += b["count"]
    else:
        precomputed = mf_brands()
        for retailer in retailers_to_query:
            retailer_brands = precomputed.get(retailer, [])
            for b in retailer_brands:
                norm_key = normalize_brand_for_matching(b["brand"])
                if norm_key not in brand_counts:
                    brand_counts[norm_key] = 0
                    brand_display[norm_key] = b["brand"]
                brand_counts[norm_key] += b["count"]

    # Build sorted brands list
    total_brand_ads = sum(brand_counts.values())
    brands_list = []
    for norm_key, count in sorted(brand_counts.items(), key=lambda x: x[1], reverse=True):
        brands_list.append({
            "brand": brand_display[norm_key],
            "count": count,
            "percentage": round((count / total_brand_ads) * 100, 1) if total_brand_ads > 0 else 0
        })

    top_brand = brands_list[0] if brands_list else None

    client_info = f" (clients: {','.join(clients)})" if clients else ""
    print(f"[stats/summary] {total_cards} cards, {len(brands_list)} brands{client_info}")

    return jsonify({
        "totalCards": total_cards,
        "activeBrands": len(brands_list),
        "topBrand": top_brand,
        "brands": brands_list,
        "builtAt": mf_daily() and None  # placeholder
    })


@app.route("/api/ads/count", methods=["GET"])
def api_ads_count():
    """
    Fast count endpoint using brand index or run manifest.
    Does NOT load cards - only metadata.

    Query params:
    - retailer (required): Retailer name
    - client (optional): Client name or "all"
    - term (optional): Keyword filter
    - advertiser (optional): Brand/advertiser filter
    - start (optional): Start date YYYY-MM-DD (inclusive)
    - end (optional): End date YYYY-MM-DD (inclusive)
    - types (optional): Comma-separated list of ad types to filter by

    Returns: {"total": number, "retailer": str, "client": str, "filters": {...}}
    """
    retailer = request.args.get("retailer") or None
    clients = _parse_clients(request)
    term = request.args.get("term") or None
    start = request.args.get("start") or None
    end = request.args.get("end") or None
    advertiser_in = request.args.get("advertiser") or None
    types_filter = (request.args.get("types") or "").strip()

    brands_filter_raw = (request.args.get("brands") or "").strip()

    # DB fast path: single SQL COUNT for any filter combination
    if _USE_DB:
        types_list = [t.strip().lower() for t in types_filter.split(',') if t.strip()] if types_filter else None
        brands_list = [b.strip() for b in brands_filter_raw.split(',') if b.strip()] if brands_filter_raw else None
        total = db_count_ads(
            retailer=retailer,
            clients=clients if clients else None,
            keyword=term,
            start=start,
            end=end,
            brand=advertiser_in,
            brands=brands_list,
            ad_types=types_list,
        )
        print(f"[ads-count] DB: {total} ads for {retailer} (types={types_filter or 'all'}, brand={advertiser_in or 'all'})")
        return jsonify({
            "total": total,
            "retailer": retailer,
            "client": _norm_clients_for_cache(clients),
            "filters": {"term": term, "advertiser": advertiser_in, "start": start, "end": end, "types": types_filter}
        })

    # --- JSON fallback paths below ---

    # If types filter is specified, we need to load JSONs to filter by ad type
    if types_filter:
        types_list = [t.strip().lower() for t in types_filter.split(',') if t.strip()]

        # For type-filtered queries, count matching ads by loading JSONs
        total = 0
        rows = []

        # Collect matching runs
        for r in mf_runs():
            if retailer and r["retailer"] != retailer:
                continue
            if clients and r["client"] not in clients:
                continue
            if term and r.get("keyword") != term:
                continue
            if start and r["day"] < start:
                continue
            if end and r["day"] > end:
                continue
            rows.append(r)

        # Load each file and count ads that match types filter
        for r in rows:
            fp = OUTPUT_ROOT / r["json_path"]
            try:
                with open(fp, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                ads = data.get("ads") or []
                for ad in ads:
                    if _matches_ad_type_filter(ad, types_list):
                        total += 1
            except Exception as e:
                print(f"[ads-count] Error loading {fp}: {e}")
                continue

        return jsonify({
            "total": total,
            "retailer": retailer,
            "client": _norm_clients_for_cache(clients),
            "filters": {"term": term, "advertiser": advertiser_in, "start": start, "end": end, "types": types_filter}
        })

    # Brand-filtered → use brand index
    if advertiser_in:
        total = count_from_brand_index(retailer, clients, term, start, end, advertiser_in)
        return jsonify({
            "total": total,
            "retailer": retailer,
            "client": _norm_clients_for_cache(clients),
            "filters": {"term": term, "advertiser": advertiser_in, "start": start, "end": end}
        })

    # General → use run manifest (no card loading)
    total = 0
    for r in mf_runs():
        if retailer and r["retailer"] != retailer:
            continue
        if clients and r["client"] not in clients:
            continue
        if term and r.get("keyword") != term:
            continue
        if start and r["day"] < start:
            continue
        if end and r["day"] > end:
            continue
        total += int(r["ad_count"] or 0)

    return jsonify({
        "total": total,
        "retailer": retailer,
        "client": _norm_clients_for_cache(clients),
        "filters": {"term": term, "start": start, "end": end}
    })


@app.route("/api/ads/types", methods=["GET"])
def api_ads_types():
    """
    Fast endpoint to get distinct ad types for a retailer/client.
    Uses run manifest metadata - no JSON file loading required.
    
    Query params:
    - retailer (required): Retailer name
    - client (optional): Client name or "all"
    - start (optional): Start date YYYY-MM-DD
    - end (optional): End date YYYY-MM-DD
    
    Returns: {"types": ["SBV", "TOA", ...], "retailer": str, "client": str}
    """
    retailer = (request.args.get("retailer") or "").strip().lower()
    clients = _parse_clients(request)
    start = request.args.get("start") or None
    end = request.args.get("end") or None
    
    if not retailer:
        return jsonify({"error": "retailer is required"}), 400
    
    # Build cache key
    client_key = _norm_clients_for_cache(clients)
    cache_key = f"types:{retailer}:{client_key}:{start}:{end}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return jsonify(cached)
    
    # DB fast path: single SQL query for distinct ad types
    if _USE_DB:
        types_list = db_get_ad_types(
            retailer=retailer,
            clients=clients if clients else None,
            start=start,
            end=end,
        )
        print(f"[ads-types] DB: {len(types_list)} types for {retailer}")
    else:
        # Fallback: collect distinct ad types from run manifest
        ad_types = set()
        for r in mf_runs():
            if r["retailer"] != retailer:
                continue
            if clients and r["client"] not in clients:
                continue
            if start and r["day"] < start:
                continue
            if end and r["day"] > end:
                continue
            brands_by_type = r.get("brands_by_type", {})
            ad_types.update(brands_by_type.keys())
        types_list = sorted(ad_types)
    
    # Canonicalize and deduplicate ad type names
    canonical_set = set()
    for t in types_list:
        canonical_set.add(canonicalize_ad_type(t))
    canonical_set.discard("")
    types_list = sorted(canonical_set)

    result = {
        "types": types_list,
        "retailer": retailer,
        "client": client_key,
        "filters": {"start": start, "end": end}
    }
    
    _set_cache(cache_key, result)
    return jsonify(result)


@app.route("/api/ads/cards", methods=["GET"])
def api_ads_cards():
    """
    Get ad cards with filtering and pagination

    Query params:
    - retailer (required): retailer slug
    - client (required): client name or "all" for all clients
    - term (optional): filter by search term
    - advertiser (optional): filter by advertiser/brand name
    - brands (optional): comma-separated list of brands to filter by
    - types (optional): comma-separated list of ad types to filter by
    - page (optional): page number (default 1)
    - page_size (optional): items per page (default 24, max 100)
    - start (optional): start date in YYYY-MM-DD format
    - end (optional): end date in YYYY-MM-DD format
    - sort (optional): sort order - "latest" (newest first), "oldest" (oldest first), or "name" (by brand A-Z)
    - include_unresolved (optional): "1", "true", or "yes" to include cards without images (debug mode)

    Note: Sorting is applied to ALL matching cards before pagination, ensuring consistent ordering across pages.
    By default, cards without resolvable images are excluded. Set include_unresolved=1 to include them
    with has_image=False and skip_reason="unresolved_image" for debugging purposes.
    
    PERFORMANCE: Results are cached for 60s. Early-slice stops scanning after finding enough matches.
    """
    retailer = (request.args.get("retailer") or "").strip().lower()
    clients = _parse_clients(request)
    term = (request.args.get("term") or "").strip().lower()
    advertiser_raw = (request.args.get("advertiser") or "").strip()
    advertiser_filter = _canon_brand_key(advertiser_raw) if advertiser_raw else None
    brands_filter = (request.args.get("brands") or "").strip()  # comma-separated list
    types_filter = (request.args.get("types") or "").strip()    # comma-separated list
    start_date = (request.args.get("start") or "").strip()  # YYYY-MM-DD format (in user's local time)
    end_date = (request.args.get("end") or "").strip()      # YYYY-MM-DD format (in user's local time)
    tz_offset_minutes = None  # User's timezone offset (JavaScript getTimezoneOffset)
    try:
        tz_val = request.args.get("tz_offset_minutes")
        if tz_val:
            tz_offset_minutes = int(tz_val)
    except ValueError:
        pass
    sort_order = (request.args.get("sort") or "").strip().lower()  # "latest", "oldest", or "name"
    include_unresolved = request.args.get("include_unresolved") in ("1", "true", "yes")  # Debug mode

    try:
        page = max(int(request.args.get("page", 1)), 1)
    except Exception:
        page = 1

    try:
        page_size = min(max(int(request.args.get("page_size", 24)), 1), 100)
    except Exception:
        page_size = 24
    
    # Check cache first (60s TTL)
    cache_params = {
        "retailer": retailer,
        "client": _norm_clients_for_cache(clients),
        "term": term,
        "advertiser": advertiser_filter,
        "brands": brands_filter,
        "types": types_filter,
        "start": start_date,
        "end": end_date,
        "tz_offset_minutes": tz_offset_minutes,
        "sort": sort_order,
        "page": page,
        "page_size": page_size,
        "include_unresolved": include_unresolved
    }
    cache_key = _cache_key(cache_params)
    cached_result = _get_cached(cache_key)
    
    if cached_result is not None:
        # Cache hit - add Server-Timing header
        response = jsonify(cached_result)
        response.headers["Server-Timing"] = "cache;desc=hit"
        client_str = _norm_clients_for_cache(clients)
        print(f"[{retailer}/{client_str}] ⚡ Cache HIT for page {page}")
        return response
    
    if not retailer:
        return jsonify({"error": "retailer parameter required"}), 400

    # ── DB FAST PATH: SQL filtering + pagination, then resolve images from JSON ──
    if _USE_DB:
        from time import perf_counter as _pc
        _t0 = _pc()
        types_list_db = [t.strip().lower() for t in types_filter.split(',') if t.strip()] if types_filter else None
        brands_list_db = [b.strip() for b in brands_filter.split(',') if b.strip()] if brands_filter else None
        db_result = db_query_ads(
            retailer=retailer,
            clients=clients if clients else None,
            keyword=term if term else None,
            start=start_date if start_date else None,
            end=end_date if end_date else None,
            brand=advertiser_raw if advertiser_raw else None,
            brands=brands_list_db,
            ad_types=types_list_db,
            page=page,
            page_size=page_size,
            sort=sort_order if sort_order else "latest",
        )
        db_ads = db_result.get("ads", [])
        db_total = db_result.get("total", 0)
        db_has_more = db_result.get("has_more", False)

        # Group by json_path to batch-load files
        from collections import defaultdict
        file_groups = defaultdict(list)
        for idx, ad_row in enumerate(db_ads):
            jp = ad_row.get("json_path") or ""
            file_groups[jp].append((idx, ad_row))

        cards = []
        brands_set = set()
        json_cache = {}

        for jp, group in file_groups.items():
            fp = OUTPUT_ROOT / jp if jp else None
            data = None
            if fp and jp not in json_cache:
                try:
                    with open(fp, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    json_cache[jp] = data
                except Exception as e:
                    print(f"[ads-cards] DB path: error loading {jp}: {e}")
                    json_cache[jp] = None
            data = json_cache.get(jp)

            for idx, ad_row in group:
                file_retailer = ad_row["retailer"]
                file_client = ad_row["client"]
                ad_type = canonicalize_ad_type(ad_row.get("ad_type") or "Main")
                brand = ad_row.get("brand") or "Unknown"
                slot = ad_row.get("slot")
                message = ad_row.get("title") or ad_row.get("message") or ad_row.get("description") or ""
                ts = ad_row.get("timestamp") or ""

                # Try to find the original ad dict in the JSON for image/video resolution
                orig_ad = None
                if data:
                    all_ads = data.get("ads") or []
                    oid = ad_row.get("original_id")
                    
                    # First, try exact ID match (works for all retailers)
                    if oid:
                        for a in all_ads:
                            if a.get("id") == oid:
                                orig_ad = a
                                break
                    
                    # Fallback: Try integer index parsing (only for non-Amazon retailers)
                    if not orig_ad and oid is not None:
                        int_idx = None
                        if isinstance(oid, int):
                            int_idx = oid
                        elif isinstance(oid, str) and '::' not in oid:
                            # Parse trailing number from IDs like 'walmart-20260213092946-2'
                            # These IDs are 1-indexed, so subtract 1 for array index
                            parts = oid.rsplit('-', 1)
                            if len(parts) == 2 and parts[1].isdigit():
                                int_idx = int(parts[1]) - 1
                            elif oid.isdigit():
                                int_idx = int(oid)
                        if int_idx is not None and 0 <= int_idx < len(all_ads):
                            orig_ad = all_ads[int_idx]
                    elif brand and brand != "Unknown":
                        # Fallback: match by brand + ad_type (case-insensitive, normalize underscores)
                        # Only use this when we have a real brand name, not "Unknown"
                        _norm = lambda s: s.lower().replace("_", " ")
                        for a in all_ads:
                            ab = (a.get("brand") or a.get("advertiser") or "").strip()
                            at = (a.get("type") or a.get("ad_type") or "")
                            if _norm(at) == _norm(ad_type) and (
                                ab.lower() == brand.lower() or
                                ab.lower() in brand.lower() or
                                brand.lower() in ab.lower()
                            ):
                                orig_ad = a
                                break

                if orig_ad:
                    media_urls = build_media_urls_for_ad(file_retailer, file_client, orig_ad)
                    image_url = media_urls.get("image_url") or media_urls.get("poster_url")
                    if not image_url:
                        image_url, has_image, debug_path, skip_reason = build_image_fields(file_retailer, file_client, orig_ad)
                    video_url_api = media_urls.get("video_url")
                    poster_url = media_urls.get("poster_url")
                    video_overlay = orig_ad.get("video_overlay")
                    card_format = orig_ad.get("card_format")
                    dimensions = orig_ad.get("dimensions")
                    advertisers = orig_ad.get("advertisers") or []
                    if not advertisers and brand and brand != "Unknown":
                        advertisers = [brand]
                    # Use the JSON's semantic slot value. The DB column is integer
                    # so strings like "left_rail" / "bottom" are lost there.
                    # Numeric slots (DOM position indices) are meaningless for
                    # the dashboard — only pass semantic labels to the frontend.
                    json_slot = orig_ad.get("slot")
                    if isinstance(json_slot, str) and json_slot in ("left_rail", "bottom", "top"):
                        slot = json_slot
                    else:
                        slot = None  # strip numeric noise
                else:
                    # No JSON match — build a synthetic ad dict from DB fields
                    # and use build_media_urls_for_ad for proper URL construction
                    synthetic_ad = {}
                    img_path = ad_row.get("image_path") or ""
                    vid_path = ad_row.get("video_path") or ""
                    vid_url = ad_row.get("video_url") or ""
                    raw_img_url = ad_row.get("image_url") or ""
                    if img_path:
                        synthetic_ad["image_path"] = img_path
                    if vid_path:
                        synthetic_ad["video_path"] = vid_path
                    if vid_url:
                        synthetic_ad["video_url"] = vid_url
                    if raw_img_url:
                        synthetic_ad["image_url"] = raw_img_url
                    media_urls = build_media_urls_for_ad(file_retailer, file_client, synthetic_ad)
                    image_url = media_urls.get("image_url") or media_urls.get("poster_url")
                    if not image_url:
                        image_url, has_image, debug_path, skip_reason = build_image_fields(file_retailer, file_client, synthetic_ad)
                    video_url_api = media_urls.get("video_url")
                    poster_url = media_urls.get("poster_url")
                    video_overlay = None
                    card_format = None
                    dimensions = None
                    advertisers = [brand] if brand and brand != "Unknown" else []

                if brand and brand != "Unknown":
                    brands_set.add(brand)

                cards.append({
                    "retailer": file_retailer,
                    "client": file_client,
                    "keyword": ad_row.get("keyword"),
                    "ad_type": ad_type,
                    "slot": slot,
                    "brand": brand,
                    "advertisers": advertisers,
                    "message": message,
                    "image_url": image_url,
                    "video_url": video_url_api,
                    "poster_url": poster_url,
                    "video_overlay": video_overlay,
                    "run_file": os.path.basename(jp) if jp else "",
                    "timestamp": ts,
                    "featured": False,
                    "ad_index": ad_row.get("original_id"),
                    "card_format": card_format,
                    "dimensions": dimensions,
                })

        _elapsed = (_pc() - _t0) * 1000
        result = {
            "retailer": retailer,
            "client": _norm_clients_for_cache(clients),
            "cards": cards,
            "page": page,
            "page_size": page_size,
            "has_more": db_has_more,
            "total_cards": db_total,
            "brands": sorted(list(brands_set)),
            "filters": {"term": term, "advertiser": advertiser_raw or None, "start": start_date, "end": end_date}
        }
        _set_cache(cache_key, result)
        client_str = _norm_clients_for_cache(clients)
        print(f"[{retailer}/{client_str}] DB cards: {len(cards)} cards from {db_total} total "
              f"(page {page}, {len(json_cache)} files loaded) in {_elapsed:.0f}ms")
        return jsonify(result)

    # BRAND INDEX FAST PATH: Paginate at file level, don't load all cards
    if advertiser_filter:
        items = _entries_for_brand_sorted(retailer, clients, start_date, end_date, advertiser_raw)
        
        # Filter by term if specified (requires opening files)
        if term:
            filtered_items = []
            checked_files = set()
            for json_path, ad_idx, file_retailer, file_client, ts in items:
                if json_path not in checked_files:
                    checked_files.add(json_path)
                    fp = OUTPUT_ROOT / json_path
                    try:
                        with open(fp, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        if data.get("keyword") != term:
                            continue
                    except Exception:
                        continue
                filtered_items.append((json_path, ad_idx, file_retailer, file_client, ts))
            items = filtered_items
        
        total = len(items)
        
        # Paginate
        start_idx = max(0, (page - 1) * page_size)
        slice_items = items[start_idx:start_idx + page_size]
        
        # Load only the cards for this page
        from collections import defaultdict
        by_file = defaultdict(list)
        for json_path, ad_index, file_retailer, file_client, ts in slice_items:
            by_file[json_path].append((ad_index, file_retailer, file_client, ts))
        
        cards = []
        for rel, ad_infos in by_file.items():
            fp = OUTPUT_ROOT / rel
            try:
                with open(fp, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                ads = data.get("ads", [])
                for ad_index, file_retailer, file_client, ts in ad_infos:
                    if 0 <= ad_index < len(ads):
                        ad = ads[ad_index]

                        # Apply shared filtering logic
                        types_list = [t.strip().lower() for t in types_filter.split(',') if t.strip()] if types_filter else []
                        if not _matches_ad_type_filter(ad, types_list):
                            continue  # Skip this ad, doesn't match the types filter

                        # Extract ad type for card data (canonicalized)
                        ad_type = canonicalize_ad_type(ad.get("type") or ad.get("ad_type") or "Main")

                        # Build card (simplified, no complex brand extraction)
                        brand = ad.get("brand") or "Unknown"
                        advertisers = ad.get("advertisers") or []
                        
                        # Skip ads where ALL advertisers are blacklisted (house ads)
                        if advertisers and all(is_blacklisted(adv) for adv in advertisers if adv):
                            continue
                        
                        message = ad.get("title") or ad.get("message") or ad.get("description") or ""
                        
                        # Skip ads whose message is blacklisted (MSG: prefix in brand_blacklist.json)
                        if message and is_blacklisted(f"MSG:{message.strip()}"):
                            continue

                        # Build image URL (always returns non-empty URL)
                        image_url, has_image, debug_path, skip_reason = build_image_fields(file_retailer, file_client, ad)

                        # Build video URL using the same logic that finds companion .mp4 files
                        # This handles Instacart where video_path is not in JSON but .mp4 exists alongside .png
                        media_urls = build_media_urls_for_ad(file_retailer, file_client, ad)
                        video_url_api = media_urls.get("video_url")
                        print(f"[API DEBUG] {file_retailer}/{file_client} ad_type={ad_type} media_urls={media_urls}")

                        # Only pass semantic slot labels to the frontend.
                        # Numeric slots (DOM position indices) are noise.
                        raw_slot = ad.get("slot")
                        if isinstance(raw_slot, str) and raw_slot in ("left_rail", "bottom", "top"):
                            slot = raw_slot
                        else:
                            slot = None

                        cards.append({
                            "retailer": file_retailer,
                            "client": file_client,
                            "keyword": data.get("keyword"),
                            "ad_type": ad_type,
                            "slot": slot,
                            "brand": brand,
                            "advertisers": advertisers,
                            "message": message,
                            "image_url": image_url,
                            "video_url": video_url_api,
                            "video_overlay": ad.get("video_overlay"),  # Include overlay metadata
                            "run_file": os.path.basename(rel),
                            "timestamp": (data.get("timestamp") or "").replace("T", " ").replace("Z", ""),
                            "featured": False,
                            "ad_index": ad_index,
                            # Gallery Cards specific fields
                            "card_format": ad.get("card_format"),  # "tile" or "banner"
                            "dimensions": ad.get("dimensions"),     # {"width": int, "height": int}
                        })
            except Exception as e:
                print(f"Error loading {rel}: {e}")
                continue
        
        # Build response
        # has_more: check if there are more items in the index to load (not filtered total)
        # This ensures pagination works correctly when filtering reduces the card count
        result = {
            "retailer": retailer,
            "client": _norm_clients_for_cache(clients),
            "cards": cards,
            "page": page,
            "page_size": page_size,
            "has_more": (start_idx + page_size) < total,
            "total_cards": total,
            "brands": [],  # Not computed for brand-filtered queries
            "filters": {
                "term": term or None,
                "advertiser": advertiser_raw or None,
                "start": start_date,
                "end": end_date
            }
        }
        
        _set_cache(cache_key, result)
        client_str = _norm_clients_for_cache(clients)
        print(f"[{retailer}/{client_str}]  Brand index fast path: {len(cards)} cards from {total} total (page {page})")
        return jsonify(result)
    
    # GENERAL PATH: Manifest-based file-level pagination
    rows = []
    for r in mf_runs():
        if retailer and r["retailer"] != retailer:
            continue
        if clients and r["client"] not in clients:
            continue
        if term and r.get("keyword") != term:
            continue
        if start_date and r["day"] < start_date:
            continue
        if end_date and r["day"] > end_date:
            continue
        rows.append(r)

    # Already sorted newest-first by builder
    total = sum(int(r["ad_count"] or 0) for r in rows)
    offset = (page - 1) * page_size

    if total == 0 or offset >= total:
        result = {
            "retailer": retailer,
            "client": _norm_clients_for_cache(clients),
            "cards": [],
            "page": page,
            "page_size": page_size,
            "has_more": False,
            "total_cards": 0,
            "brands": [],
            "filters": {"term": term, "start": start_date, "end": end_date}
        }
        _set_cache(cache_key, result)
        return jsonify(result)

    # Parse types filter once if needed
    types_list = []
    if types_filter:
        types_list = [t.strip().lower() for t in types_filter.split(',') if t.strip()]
        print(f" [FLASK DEBUG] Applied types filter: {types_list}")


    # FAST PRE-COUNT: Get total matching ads first for accurate pagination
    filtered_total = 0
    if types_filter:
        print(f" [FLASK DEBUG] Pre-counting total matching ads...")
        for r in rows:
            fp = OUTPUT_ROOT / r["json_path"]
            try:
                with open(fp, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                all_ads = data.get("ads") or []
                for ad in all_ads:
                    if _matches_ad_type_filter(ad, types_list):
                        filtered_total += 1
            except Exception:
                continue
        print(f" [FLASK DEBUG] Found {filtered_total} total matching ads")
    else:
        filtered_total = total  # No filter, use original total

    # Now build the actual page of cards
    cards = []
    brands_set = set()
    acc = 0
    need = page_size
    start_needed = offset

    for r in rows:
        run_count = int(r["ad_count"] or 0)

        # Skip runs before our offset
        if start_needed >= run_count:
            start_needed -= run_count
            acc += run_count
            continue

        # This run contains part of the requested slice
        fp = OUTPUT_ROOT / r["json_path"]
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            acc += run_count
            continue

        all_ads = data.get("ads") or []

        # When types filter is active, we need to scan all ads from start_needed onwards
        # to account for filtered-out ads and still get page_size results
        start_idx = start_needed
        for j in range(start_idx, len(all_ads)):
            ad = all_ads[j]
            file_client = r["client"]
            file_retailer = r["retailer"]

            # Apply shared filtering logic
            if not _matches_ad_type_filter(ad, types_list):
                continue  # Skip this ad, doesn't match filter

            # Extract ad type for card data (canonicalized)
            ad_type = canonicalize_ad_type(ad.get("type") or ad.get("ad_type") or "Main")

            # Extract advertisers array (preferred) or fallback to brand field
            advertisers = ad.get("advertisers") or []
            if not advertisers:
                ad_brand = ad.get("brand") or ad.get("advertiser")
                if ad_brand:
                    advertisers = [ad_brand]

            # Skip ads where ALL advertisers are blacklisted (house ads)
            if advertisers and all(is_blacklisted(adv) for adv in advertisers if adv):
                continue

            # Build brand display string from advertisers
            brand = ' + '.join(advertisers) if advertisers else "Unknown"
            
            # Detect Walmart house ads in old data (Gallery Cards with Walmart+ messaging)
            if brand == "Unknown" and file_retailer == "walmart" and ad_type == "Gallery Cards":
                msg_lower = message.lower()
                if "walmart+" in msg_lower or "walmart plus" in msg_lower:
                    brand = "Walmart"
                    advertisers = ["Walmart"]

            # Last-resort: try to infer brand from title / href when still Unknown
            if brand == "Unknown":
                inferred = _infer_brand_from_ad(ad)
                if inferred:
                    brand = inferred
                    advertisers = [inferred]

            # Apply brands filter if specified
            if brands_filter:
                brands_list = [b.strip().lower() for b in brands_filter.split(',') if b.strip()]
                if brands_list:
                    # Check if any advertiser matches any brand in the filter
                    ad_brands_lower = [adv.lower() for adv in advertisers if adv]
                    if not any(ab in brands_list for ab in ad_brands_lower):
                        continue  # Skip this ad, doesn't match brand filter

            # Track unique brands
            for adv in advertisers:
                if adv and adv != "Unknown":
                    brands_set.add(adv)

            message = ad.get("title") or ad.get("message") or ad.get("description") or ""

            # Skip ads whose message is blacklisted (MSG: prefix in brand_blacklist.json)
            if message and is_blacklisted(f"MSG:{message.strip()}"):
                continue

            # Extract slot field — only pass semantic labels, strip numeric noise
            raw_slot = ad.get("slot")
            if isinstance(raw_slot, str) and raw_slot in ("left_rail", "bottom", "top"):
                slot = raw_slot
            else:
                slot = None

            # Build image URL (always returns non-empty URL)
            image_url, has_image, debug_path, skip_reason = build_image_fields(file_retailer, file_client, ad)

            # Build video URL using the same logic that finds companion .mp4 files
            # This handles Instacart where video_path is not in JSON but .mp4 exists alongside .png
            media_urls = build_media_urls_for_ad(file_retailer, file_client, ad)
            video_url_api = media_urls.get("video_url")

            # Normalize timestamp to ISO Z
            raw_ts = data.get("timestamp") or ""
            iso_ts = raw_ts if raw_ts.endswith("Z") else raw_ts.replace(" ", "T") + "Z" if raw_ts else ""

            cards.append({
                "retailer": file_retailer,
                "client": file_client,
                "keyword": data.get("keyword"),
                "ad_type": ad_type,
                "slot": slot,
                "brand": brand,
                "advertisers": advertisers,
                "message": message,
                "image_url": image_url,
                "video_url": video_url_api,
                "video_overlay": ad.get("video_overlay"),  # Include overlay metadata
                "run_file": os.path.basename(r["json_path"]),
                "timestamp": iso_ts,
                "featured": False,
                "ad_index": j,
                # Gallery Cards specific fields
                "card_format": ad.get("card_format"),  # "tile" or "banner"
                "dimensions": ad.get("dimensions"),     # {"width": int, "height": int}
            })

            # Stop when we have enough cards for this page
            if len(cards) >= page_size:
                break

        acc += run_count
        start_needed = 0

        if len(cards) >= page_size:
            break

        # Continue to need more cards if we don't have a full page yet
        need = page_size - len(cards)

    # Use pre-counted filtered total for accurate pagination
    display_total = filtered_total
    has_more = (offset + len(cards)) < display_total

    result = {
        "retailer": retailer,
        "client": _norm_clients_for_cache(clients),
        "cards": cards,
        "page": page,
        "page_size": page_size,
        "has_more": has_more,
        "total_cards": display_total,
        "brands": sorted(list(brands_set)),
        "filters": {"term": term, "start": start_date, "end": end_date}
    }

    _set_cache(cache_key, result)
    client_str = _norm_clients_for_cache(clients)
    filter_note = f" (types filter: {types_filter})" if types_filter else ""
    print(f"[{retailer}/{client_str}] 📊 Manifest pagination: {len(cards)} cards from {display_total} total (page {page}){filter_note}")
    return jsonify(result)
    
    # Support client=all or comma-separated list of clients
    if client.lower() == "all":
        clients_to_query = []
        retailer_root = os.path.join(OUTPUT_ROOT, retailer)
        if os.path.isdir(retailer_root):
            for item in os.listdir(retailer_root):
                item_path = os.path.join(retailer_root, item)
                if os.path.isdir(item_path):
                    clients_to_query.append(item)
    elif "," in client:
        # Parse comma-separated list of clients
        clients_to_query = [c.strip() for c in client.split(",") if c.strip()]
    else:
        clients_to_query = [client]
    
    # Parse date range for early filtering (PERFORMANCE OPTIMIZATION)
    # Filter run files by date BEFORE loading/processing them
    start_dt, end_dt = None, None
    if start_date or end_date:
        try:
            start_dt, end_dt = utc_range_for("custom", start_date, end_date, tz_offset_minutes)
            print(f"[{retailer}/{client}] 📅 Early date filter: {start_dt.isoformat()} to {end_dt.isoformat()} (tz_offset: {tz_offset_minutes} min)")
        except Exception as e:
            print(f"[{retailer}/{client}] ⚠️  Date parse error: {e}")
    
    # BRAND INDEX OPTIMIZATION: If advertiser filter is specified, use brand index for instant lookup
    files = []
    use_brand_index = False
    if advertiser_filter:
        brand_files = lookup_brand_files(advertiser_filter)
        if brand_files:
            use_brand_index = True
            print(f"[{retailer}/{client}] 🚀 Brand index: Found {len(brand_files)} files for '{advertiser_filter}'")
            
            # Filter by retailer and client
            for entry in brand_files:
                if entry['retailer'] != retailer:
                    continue
                if client.lower() != "all" and entry['client'] not in clients_to_query:
                    continue
                
                # Apply date filter if specified
                if start_dt or end_dt:
                    try:
                        entry_ts = entry.get('timestamp')
                        if entry_ts:
                            entry_dt = datetime.fromisoformat(entry_ts.replace('Z', '+00:00'))
                            if start_dt and entry_dt < start_dt:
                                continue
                            if end_dt and entry_dt > end_dt:
                                continue
                    except Exception:
                        pass  # Include if date parsing fails
                
                # Add to files list with ad indices for targeted loading
                json_path = OUTPUT_ROOT / entry['json_path']
                if json_path.exists():
                    files.append((json_path.name, str(json_path), entry['client'], entry.get('ad_indices', [])))
            
            print(f"[{retailer}/{client}] 🚀 Brand index: {len(files)} files after filtering")
    
    # Fallback: Collect files from all clients (original logic)
    if not use_brand_index:
        for client_name in clients_to_query:
            rdir = runs_dir(retailer, client_name)
            
            if not os.path.isdir(rdir):
                continue
            
            # Get all run files (newest first) - handle both canonical and legacy formats
            for item in os.listdir(rdir):
                item_path = os.path.join(rdir, item)
                if os.path.isfile(item_path) and item.startswith("run_results_") and item.endswith(".json"):
                    filename_base = item.replace("run_results_", "").replace(".json", "")
                    
                    # Try canonical format first (run_results_YYYYMMDDHHMMSS.json)
                    if filename_base.isdigit() and len(filename_base) == 14:
                        # PERFORMANCE: Filter by date before adding to files list
                        if start_dt or end_dt:
                            try:
                                # Parse timestamp from filename: YYYYMMDDHHMMSS
                                file_dt = datetime.strptime(filename_base, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
                                if start_dt and file_dt < start_dt:
                                    continue  # Skip files before start date
                                if end_dt and file_dt > end_dt:
                                    continue  # Skip files after end date
                            except Exception:
                                pass  # Include file if date parsing fails
                        files.append((item, item_path, client_name))
                    
                    # Also support legacy format (run_results_{keyword}_YYYY-MM-DD_HH-MM-SS.json)
                    elif "_" in filename_base:
                        # Try to extract date from legacy format
                        parts = filename_base.split("_")
                        if len(parts) >= 3:
                            # Look for date pattern YYYY-MM-DD
                            for i, part in enumerate(parts):
                                if len(part) == 10 and part.count("-") == 2:
                                    try:
                                        # Found date, check if next part is time
                                        date_str = part
                                        time_str = parts[i+1] if i+1 < len(parts) else "00-00-00"
                                        # Parse: 2025-10-24_16-19-00
                                        datetime_str = f"{date_str} {time_str.replace('-', ':')}"
                                        file_dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                                        
                                        # Apply date filter
                                        if start_dt and file_dt < start_dt:
                                            break  # Skip this file
                                        if end_dt and file_dt > end_dt:
                                            break  # Skip this file
                                        
                                        files.append((item, item_path, client_name))
                                        break
                                    except Exception:
                                        # If date parsing fails, include the file anyway
                                        files.append((item, item_path, client_name))
                                        break
                elif os.path.isdir(item_path):
                    # Check subdirectories (Walmart structure)
                    for subitem in os.listdir(item_path):
                        if subitem.startswith("run_results_") and subitem.endswith(".json"):
                            # Same canonical check for nested files
                            filename_base = subitem.replace("run_results_", "").replace(".json", "")
                            if filename_base.isdigit() and len(filename_base) == 14:
                                # PERFORMANCE: Filter by date before adding to files list
                                if start_dt or end_dt:
                                    try:
                                        file_dt = datetime.strptime(filename_base, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
                                        if start_dt and file_dt < start_dt:
                                            continue
                                        if end_dt and file_dt > end_dt:
                                            continue
                                    except Exception:
                                        pass
                                files.append((subitem, os.path.join(item_path, subitem), client_name))
    
    # Sort by filename (most recent first)
    files = sorted(files, key=lambda x: x[0], reverse=True)
    
    print(f"[{retailer}/{client}] 📁 Found {len(files)} run files after date filtering")
    
    # Return empty if no files found
    if not files:
        empty_result = {
            "retailer": retailer,
            "client": client,
            "cards": [],
            "page": page,
            "page_size": page_size,
            "has_more": False,
            "total_cards": 0
        }
        _set_cache(cache_key, empty_result)
        return jsonify(empty_result)
    
    # PERFORMANCE OPTIMIZATION: Early-slice file scanning
    # DISABLED: Early-slice breaks aggregate stats (total count, brand counts, SOV)
    # TODO: Implement proper file-level pagination for non-brand queries
    max_files_to_scan = None
    
    # Collect all cards
    all_cards = []
    files_scanned = 0
    for file_entry in files:
        # Handle both 3-tuple (fallback) and 4-tuple (brand index) formats
        if len(file_entry) == 4:
            fn, fpath, file_client, ad_indices = file_entry
        else:
            fn, fpath, file_client = file_entry
            ad_indices = None  # Load all ads
        # Early-slice: stop if we've scanned enough files
        if max_files_to_scan and files_scanned >= max_files_to_scan:
            print(f"[{retailer}/{client}] ⚡ Early-slice: Stopped after {files_scanned} files")
            break
        files_scanned += 1
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            run_kw = (data.get("keyword") or data.get("search_term") or "").lower()
            
            # Filter by term if specified
            if term and run_kw != term:
                continue
            
            # Extract ads from various JSON structures
            ads = []
            if "ads" in data:
                ads = data["ads"]
            elif "results" in data:
                for result in data.get("results", []):
                    ads.extend(result.get("ads", []))
            
            # WALMART FALLBACK: If no ads found in JSON, create synthetic ads from image files
            if not ads and retailer == "walmart":
                # Look for image files in the same directory as the JSON
                json_dir = os.path.dirname(fpath)
                try:
                    for img_file in os.listdir(json_dir):
                        if img_file.endswith(('.png', '.jpg', '.jpeg')):
                            # Parse ad type from filename: walmart_keyword_adtype_N.png
                            parts = img_file.replace('.png', '').replace('.jpg', '').split('_')
                            ad_type = parts[-2] if len(parts) >= 3 else "unknown"
                            
                            # Create synthetic ad
                            ads.append({
                                "type": ad_type,
                                "ad_type": ad_type,
                                "brand": "Unknown",
                                "screenshot_path": os.path.join(os.path.basename(json_dir), img_file),
                                "image_url": "",
                            })
                except Exception as e:
                    print(f"Error creating synthetic Walmart ads: {e}")
            
            # Get image_paths mapping if available (from migration)
            image_paths_map = data.get("image_paths", {})
            
            # Convert each ad to a card
            for idx, ad in enumerate(ads):
                ad_type = (ad.get("type") or ad.get("ad_type") or "").lower()
                
                # Filter out non-featured tile takeovers for Walmart
                if retailer == "walmart" and "tile" in ad_type:
                    # Only include featured tile takeovers
                    if not ad.get("featured", False):
                        continue
                
                # Filter out Sponsored Label ads for Instacart (not actual ad units)
                if retailer == "instacart" and "sponsored label" in ad_type:
                    continue
                
                # Determine image filename - prioritize local saved paths over remote URLs
                filename = ""
                has_local_path = False
                
                # Try various path fields first (these point to actual saved files)
                for path_field in ["skyscraper_image_path", "carousel_image_path", "main_image_path",
                                   "image_path", "screenshot_path", "screenshot", "filename"]:
                    p = ad.get(path_field)
                    if not p:
                        continue
                    p = str(p).lstrip("./")
                    # Keep retailer subfolder if path is relative (contains '/')
                    if "/" in p and not os.path.isabs(p):
                        filename = p  # e.g., "Skyscraper/file.png" or "SBA/file.png"
                    else:
                        filename = os.path.basename(p)
                    
                    # CRITICAL: Check if this file actually exists on disk
                    # If not, we need to run fallback search (file might be named "unknown")
                    full_path = os.path.join(OUTPUT_ROOT, retailer, file_client, filename)
                    if os.path.exists(full_path):
                        has_local_path = True
                        break
                    else:
                        # Path in JSON but file doesn't exist - clear filename to trigger fallback
                        print(f"⚠️  [{retailer}/{file_client}] Path in JSON doesn't exist: {filename}")
                        filename = ""
                        has_local_path = False
                
                # Fallback to extracting from image_url if no path field found
                # BUT mark it as not having a local path so we can search for taxonomy files
                if not filename and ad.get("image_url"):
                    filename = os.path.basename(str(ad.get("image_url")))
                    has_local_path = False  # This is a remote CDN URL, not a local file
                
                # For Walmart: try to match ad type to image_paths mapping
                if not filename and image_paths_map and retailer == "walmart":
                    ad_type = ad.get("type", "").lower()
                    keyword = data.get("keyword", data.get("search_term", "")).replace(" ", "_")
                    
                    # Try to find matching image in map
                    for old_name, new_path in image_paths_map.items():
                        if ad_type in old_name.lower() and keyword.split("_")[0] in old_name.lower():
                            filename = new_path
                            break
                
                # FALLBACK: If we don't have a local path, search for taxonomy-named files on disk
                # This handles cases where screenshot script saved images but didn't update JSON
                # OR when JSON only has remote CDN URLs (image_url) but local files exist
                if not has_local_path:
                    ad_type_hint = ad.get("type") or ad.get("ad_type") or ""
                    leaf = subdir_for(retailer, ad_type_hint)
                    print(f"🔍 [{retailer}/{file_client}] Searching for image: ad_type={ad_type_hint}, leaf={leaf}")
                    if leaf:
                        # Look for files matching the taxonomy pattern in this ad type folder
                        search_dir = os.path.join(OUTPUT_ROOT, retailer, file_client, leaf)
                        print(f"🔍 [{retailer}/{file_client}] Search dir: {search_dir}, exists={os.path.isdir(search_dir)}")
                        if os.path.isdir(search_dir):
                            try:
                                # Get keyword for matching
                                kw = (data.get("keyword") or data.get("search_term") or "").lower().replace(" ", "_")
                                # For Walmart: strip date suffix if present (e.g., "ice_cream_cones_2025-10-14" -> "ice_cream_cones")
                                if retailer == "walmart" and "_20" in kw:
                                    kw = kw.split("_20")[0]  # Remove date suffix
                                
                                # Get timestamp from JSON for matching
                                timestamp_str = data.get("timestamp", "")
                                # Extract date and hour from timestamp for flexible matching
                                # Screenshots may be taken a few minutes after the scrape
                                import re
                                ts_date = None
                                ts_hour = None
                                ts_minute = None
                                if timestamp_str:
                                    # Try to extract YYYY-MM-DD HH:MM pattern
                                    ts_pattern = re.search(r'(\d{4}-\d{2}-\d{2})\s+(\d{2}):(\d{2})', str(timestamp_str))
                                    if ts_pattern:
                                        ts_date = ts_pattern.group(1)  # 2025-10-23
                                        ts_hour = ts_pattern.group(2)  # 23
                                        ts_minute = int(ts_pattern.group(3))  # 3
                                
                                # Get brand names from ad for matching
                                ad_brands = ad.get("advertisers", [])
                                if not ad_brands:
                                    ad_brands = [ad.get("brand") or ad.get("advertiser") or ""]
                                ad_brands_lower = [b.lower().replace(" ", "_").replace("'", "") for b in ad_brands if b]
                                
                                # List files and find matches (prefer image extensions over videos)
                                files = os.listdir(search_dir)
                                print(f"����� [{retailer}] Found {len(files)} files in {leaf}/, keyword={kw}, timestamp={ts_date}_{ts_hour}:{ts_minute}, brands={ad_brands_lower}")
                                
                                # Sort files to prefer .png, .jpg, .jpeg, .webp over .mp4
                                image_exts = ('.png', '.jpg', '.jpeg', '.webp')
                                files_sorted = sorted(files, key=lambda f: (not f.endswith(image_exts), f))
                                
                                # First pass: Match by timestamp + keyword + brand
                                candidates = []
                                for f in files_sorted:
                                    # Only match image files (not videos)
                                    if not (f.startswith(f"{retailer}__") and kw in f.lower() and f.endswith(image_exts)):
                                        continue
                                    
                                    f_lower = f.lower()
                                    
                                    # Check if timestamp matches (flexible - within 10 minutes)
                                    timestamp_matches = False
                                    if ts_date and ts_hour is not None:
                                        # Extract timestamp from filename: D2025-10-24_T10-36.55
                                        file_ts = re.search(r'D(\d{4}-\d{2}-\d{2})_T(\d{2})-(\d{2})', f)
                                        if file_ts:
                                            file_date = file_ts.group(1)
                                            file_hour = file_ts.group(2)
                                            file_minute = int(file_ts.group(3))
                                            
                                            # Match if same date+hour and within 10 minutes
                                            if file_date == ts_date and file_hour == ts_hour:
                                                minute_diff = abs(file_minute - ts_minute)
                                                if minute_diff <= 10:
                                                    timestamp_matches = True
                                    else:
                                        # No timestamp in JSON, don't filter by timestamp
                                        timestamp_matches = True
                                    
                                    # Check if brand matches
                                    brand_match = any(brand in f_lower for brand in ad_brands_lower if brand)
                                    
                                    # Perfect match: timestamp + keyword + brand
                                    if timestamp_matches and brand_match:
                                        filename = os.path.join(leaf, f)
                                        print(f"✅ [{retailer}] Perfect match (timestamp+brand): {filename}")
                                        break
                                    
                                    # Good match: save as candidate
                                    # Priority: timestamp match > brand match > any match
                                    if timestamp_matches or brand_match:
                                        candidates.append(f)
                                
                                # If no perfect match, use best candidate
                                if not filename and candidates:
                                    filename = os.path.join(leaf, candidates[0])
                                    print(f"⚠️  [{retailer}] Using candidate match: {filename}")
                                
                                if not filename:
                                    print(f"⚠️  [{retailer}] No matching image found for keyword={kw}, timestamp={ts_date}_{ts_hour}:{ts_minute}, brands={ad_brands_lower} in {leaf}/")
                            except Exception as e:
                                print(f"❌ [{retailer}] Error searching for images: {e}")
                
                # Build image fields using fail-closed approach (always returns image_url)
                img_url, has_img, dbg_rel, reason = build_image_fields(retailer, file_client, ad)
                
                # Log misses for monitoring
                if not has_img:
                    print(f"⚠️  [{retailer}/{file_client}] Image miss: {reason} - {dbg_rel or 'no path'}")
                
                # Extract advertisers - handle new array format and legacy fields
                advertisers = ad.get("advertisers")  # New array format
                if not advertisers:
                    # Fallback to legacy fields
                    legacy_brand = ad.get("brand") or ad.get("advertiser") or ad.get("title")
                    advertisers = [legacy_brand] if legacy_brand else []

                # Canonicalize brand names using lexicon
                advertisers = [canonicalize(adv) or adv for adv in (advertisers or []) if adv]

                # Filter out blocked brands (ad types that shouldn't be brand names)
                # CRITICAL: This removes "Kroger" house ads (retailer marketing materials)
                # These are NOT real brand ads and should be excluded from counts/analysis
                advertisers = [adv for adv in advertisers if not is_blocked_brand(adv)]

                # Campaign slogan detection - words that indicate this is NOT a brand name
                campaign_keywords = {'halloween', 'christmas', 'holiday', 'summer', 'spring', 'fall', 'winter',
                                    'grab', 'get', 'buy', 'save', 'shop', 'now', 'better', 'best', 'new', 'fresh',
                                    'treats', 'deals', 'sale', 'special', 'limited', 'exclusive', 'discover',
                                    'shop now', 'buy now', 'save now', 'learn more', 'click here',
                                    'digital deal', 'digital_deal', 'advertisement', 'sponsored',
                                    'kroji holdings', 'kroji_holdings', 'kroji holding', 'kroji_holding', 'kroji'}

                # If advertisers look like campaign slogans, prefer filename parsing
                looks_like_slogan = False
                if advertisers:
                    for adv in advertisers:
                        if adv and any(keyword in adv.lower() for keyword in campaign_keywords):
                            looks_like_slogan = True
                            break

                # If no advertisers OR looks like slogan, try parsing from filename
                if (not advertisers or looks_like_slogan) and filename:
                    # New taxonomy: retailer__advertiser(s)__ad_type__client__search_term__timestamp_index.ext
                    # Advertisers can be: single (herdez) or multiple (herdez+jennie_o)
                    parts = filename.split('__')
                    if len(parts) >= 2:
                        advertiser_segment = parts[1]
                        # Split on + for co-branded ads
                        parsed_advertisers = advertiser_segment.split('+')
                        # Clean up (remove underscores, capitalize)
                        parsed_advertisers = [smart_title(adv.replace('_', ' ')) for adv in parsed_advertisers if adv and adv != 'unknown']
                        # Canonicalize brand names
                        parsed_advertisers = [canonicalize(adv) or adv for adv in parsed_advertisers]
                        # Filter out blocked brands (ad types)
                        advertisers = [adv for adv in parsed_advertisers if not is_blocked_brand(adv)]
                # Drop advertisers that are really just the ad type repeated
                if advertisers:
                    ad_type_val = ad.get("type") or ad.get("ad_type") or ""

                    def _norm_name(s: str) -> str:
                        # Lowercase, strip spaces/underscores for comparison
                        return ''.join((s or "").lower().replace('_', ' ').split())

                    norm_type = _norm_name(ad_type_val)
                    type_label = type_label_for(ad_type_val)
                    norm_label = _norm_name(type_label)

                    advertisers = [
                        adv for adv in advertisers
                        if _norm_name(adv) not in {norm_type, norm_label}
                    ]

                # Format brand string for display
                brand = ' + '.join(advertisers) if advertisers else "Unknown"
                
                # Extract message/headline
                message = ad.get("message") or ad.get("headline") or ad.get("description") or ""
                
                # Detect Walmart house ads in old data (Gallery Cards with Walmart+ messaging)
                ad_type_raw = ad.get("type") or ad.get("ad_type") or ""
                if brand == "Unknown" and retailer == "walmart" and "gallery" in ad_type_raw.lower():
                    msg_lower = message.lower()
                    if "walmart+" in msg_lower or "walmart plus" in msg_lower:
                        brand = "Walmart"
                        advertisers = ["Walmart"]

                # Last-resort: try to infer brand from title / href when still Unknown
                if brand == "Unknown":
                    inferred = _infer_brand_from_ad(ad)
                    if inferred:
                        brand = inferred
                        advertisers = [inferred]
                
                # Skip ads whose message is blacklisted (MSG: prefix in brand_blacklist.json)
                if message and is_blacklisted(f"MSG:{message.strip()}"):
                    continue

                # Normalize timestamp to ISO Z (UTC)
                raw_ts = data.get("timestamp") or data.get("ts") or ""
                run_id = data.get("run_id")
                # Try to extract run_id from filename if not in JSON
                if not run_id:
                    run_id_match = re.search(r'(\d{14})', fn)
                    if run_id_match:
                        run_id = run_id_match.group(1)
                
                iso_ts = to_iso_z(raw_ts, run_id)
                epoch_ms = iso_to_epoch_ms(iso_ts)
                
                # Build card with image (always present - real or placeholder)
                card = {
                    "retailer": retailer,
                    "client": file_client,
                    "keyword": data.get("keyword") or data.get("search_term"),
                    "ad_type": canonicalize_ad_type(ad.get("type") or ad.get("ad_type")),
                    "type": ad.get("type"),  # Original type field (e.g., "Sponsored_Display" for Amazon)
                    "subtype": ad.get("subtype"),  # Original subtype field (e.g., "Display_Ad" for Amazon)
                    "brand": brand,
                    "advertisers": advertisers,  # NEW: array of advertisers for filtering
                    "message": message,
                    "image_url": img_url,  # NEVER empty - real file or placeholder
                    "has_image": has_img,  # true when real file served, false when placeholder
                    "run_file": fn,
                    "timestamp": iso_ts,  # Normalized ISO Z
                    "timestamp_ms": epoch_ms,  # Epoch milliseconds for easy filtering
                    "featured": ad.get("featured", False),
                    "ad_index": idx  # Add index for unique identification
                }

                # Add debug fields for unresolved images
                if not has_img:
                    card["skip_reason"] = reason
                    # Optional: keep original path for audits (only when include_unresolved=1)
                    if include_unresolved and dbg_rel:
                        card["image_path"] = dbg_rel

                # Normalize brand via lexicon and attach logo
                card["type_label"] = type_label_for(card.get("ad_type"))

                # 1) Canonicalize brand via lexicon
                raw_brand = card.get("brand")
                brand_canonical = canonicalize_brand(raw_brand)

                # 2) Drop false brands that equal ad types/placeholders
                brand_canonical = normalize_brand(brand_canonical, card.get("ad_type"))

                # 3) Set brand fields
                card["brand_canonical"] = brand_canonical
                card["brand"] = brand_canonical  # keep brand = canonical for UI simplicity

                # 4) Attach logo URL if present in DB/files
                card["brand_logo_url"] = brand_logo_url_for(brand_canonical, retailer)

                # Build complete media URLs (image, video, poster)
                # Create a temporary ad dict with the resolved filename for media URL building
                ad_for_media = dict(ad)
                if filename:
                    ad_for_media["image_path"] = filename
                media_urls = build_media_urls_for_ad(retailer, file_client, ad_for_media)
                if media_urls.get("video_url"):
                    card["video_url"] = media_urls["video_url"]
                if media_urls.get("poster_url"):
                    card["poster_url"] = media_urls["poster_url"]
                
                # Include video_overlay metadata if present
                # For DB-sourced ads, video_overlay lives inside the metadata JSONB
                _vo = ad.get("video_overlay")
                if not _vo and isinstance(ad.get("metadata"), dict):
                    _vo = ad["metadata"].get("video_overlay")
                if _vo:
                    card["video_overlay"] = _vo

                all_cards.append(card)
        except Exception as e:
            print(f"Error processing {fn}: {e}")
            pass
    
    # Filter by advertiser if specified
    if advertiser_filter:
        print(f"[{retailer}/{client}] 🔍 Filtering {len(all_cards)} cards by advertiser: '{advertiser_filter}'")
        filtered_cards = []
        for idx, card in enumerate(all_cards):
            matched = False
            
            # Check brand field
            brand = (card.get("brand") or "").lower()
            if advertiser_filter in brand or brand in advertiser_filter:
                matched = True
            
            # Check advertisers array
            if not matched:
                advertisers = card.get("advertisers", [])
                for adv in advertisers:
                    adv_lower = adv.lower()
                    # Match if filter contains advertiser OR advertiser contains filter
                    if advertiser_filter in adv_lower or adv_lower in advertiser_filter:
                        matched = True
                        break
            
            if matched:
                filtered_cards.append(card)
        
        print(f"[{retailer}/{client}] ✅ After advertiser filter: {len(filtered_cards)} cards remain")
        all_cards = filtered_cards

    # Filter by brands if specified (comma-separated list)
    if brands_filter:
        brands_list = [b.strip().lower() for b in brands_filter.split(',') if b.strip()]
        if brands_list:
            filtered_cards = []
            for card in all_cards:
                card_brand = (card.get("brand") or "").lower()
                if card_brand in brands_list:
                    filtered_cards.append(card)
            all_cards = filtered_cards

    # Filter by ad types if specified (comma-separated list)
    if types_filter:
        types_list = [t.strip().lower() for t in types_filter.split(',') if t.strip()]
        print(f"🔍 [FLASK DEBUG] types_filter='{types_filter}', types_list={types_list}")
        if types_list:
            filtered_cards = []
            original_count = len(all_cards)
            for card in all_cards:
                card_type = (card.get("ad_type") or "").lower()
                # Normalize for comparison: replace underscores and hyphens with spaces
                card_type_normalized = card_type.replace("_", " ").replace("-", " ")
                # Check if any requested type matches the card type (exact or substring)
                matches = any(req_type in card_type_normalized or card_type_normalized in req_type for req_type in types_list)
                if matches:
                    filtered_cards.append(card)
                # Debug first few cards
                if len(filtered_cards) < 3:
                    print(f"🔍 [FLASK DEBUG] card ad_type='{card.get('ad_type')}' -> normalized='{card_type_normalized}' -> matches={matches}")
            print(f"🔍 [FLASK DEBUG] Filtered {original_count} -> {len(filtered_cards)} cards")
            all_cards = filtered_cards

    # Filter by date range if specified (UTC-aware)
    # If start_date is provided (even without end_date), apply the filter
    # Empty/missing parameters mean lifetime (all dates)
    if start_date or end_date:
        # Log the filtering operation for debugging
        print(f"[{retailer}/{client}] 📅 Date filter requested: start={start_date}, end={end_date}, tz_offset={tz_offset_minutes}")

        # Determine filter type and get UTC range
        filter_name = "custom"  # Default to custom range
        start_dt, end_dt = utc_range_for(filter_name, start_date, end_date, tz_offset_minutes)

        print(f"[{retailer}/{client}] 📅 UTC range: {start_dt.isoformat()} to {end_dt.isoformat()}")
        print(f"[{retailer}/{client}] 📅 Filtering {len(all_cards)} cards...")

        filtered_cards = []
        for card in all_cards:
            timestamp = card.get("timestamp", "")
            if not timestamp:
                continue

            try:
                # Parse normalized ISO Z timestamp
                ad_dt = parse_utc(timestamp)

                # Check if within range (inclusive)
                if start_dt <= ad_dt <= end_dt:
                    filtered_cards.append(card)
            except Exception as e:
                # Skip cards with unparseable timestamps
                print(f"Warning: [{retailer}/{client}] Could not parse timestamp '{timestamp}': {e}")
                continue

        all_cards = filtered_cards
        print(f"[{retailer}/{client}] ✅ After date filtering: {len(all_cards)} cards remain")
    else:
        # No date range filtering - return all cards (lifetime)
        print(f"[{retailer}/{client}] 📅 No date filter specified (lifetime mode) - returning all {len(all_cards)} cards")

    # Apply sorting to all cards (before pagination)
    if sort_order:
        print(f"[{retailer}/{client}] 📊 Sorting cards by: {sort_order}")
        if sort_order == "latest":
            # Sort by timestamp descending (newest first)
            all_cards.sort(key=lambda c: c.get("timestamp_ms", 0), reverse=True)
        elif sort_order == "oldest":
            # Sort by timestamp ascending (oldest first)
            all_cards.sort(key=lambda c: c.get("timestamp_ms", 0))
        elif sort_order == "name":
            # Sort by brand name alphabetically
            all_cards.sort(key=lambda c: (c.get("brand") or "").lower())
        print(f"[{retailer}/{client}] ✅ Cards sorted by {sort_order}")

    # Deduplicate cards based on unique key (run_file + ad_index is the true unique identifier)
    seen = set()
    deduped_cards = []
    duplicates_removed = 0
    for card in all_cards:
        # Create unique key: run_file + ad_index uniquely identifies an ad
        # This prevents the same ad from appearing multiple times even if processed differently
        key = (
            card.get("run_file"),  # The JSON filename
            card.get("ad_index")   # Position in that JSON's ads array
        )
        if key not in seen:
            seen.add(key)
            deduped_cards.append(card)
        else:
            duplicates_removed += 1
    
    all_cards = deduped_cards
    if duplicates_removed > 0:
        print(f"[{retailer}/{client}] ⚠️  Deduplication: Removed {duplicates_removed} duplicate cards")

    # Replace scraper-artifact brand names with "Unknown".
    # These are generic UI words the iframe parser falsely extracted as brands.
    _BOGUS_BRANDS = {"page", "click"}
    for c in all_cards:
        if (c.get("brand") or "").lower() in _BOGUS_BRANDS:
            c["brand"] = "Unknown"

    # Filter out ads whose message is blacklisted (MSG: prefix in brand_blacklist.json)
    pre_house = len(all_cards)
    all_cards = [
        c for c in all_cards
        if not (c.get("message") and is_blacklisted(f"MSG:{(c.get('message') or '').strip()}"))
    ]
    _house_removed = pre_house - len(all_cards)
    if _house_removed > 0:
        print(f"[{retailer}/{client}] 🏠 Filtered {_house_removed} house ads (blacklisted messages)")

    # Calculate brand aggregations from ALL cards (before pagination)
    brand_counts = {}
    for card in all_cards:
        raw_brand = card.get("brand") or card.get("brand_canonical") or "Unknown"
        # Canonicalize brand name to merge case variations
        brand = canonicalize_brand(raw_brand) or raw_brand
        brand_counts[brand] = brand_counts.get(brand, 0) + 1
    
    # Sort brands by count (descending)
    brands_list = [
        {"brand": brand, "count": count, "percentage": round((count / len(all_cards)) * 100, 1) if all_cards else 0}
        for brand, count in sorted(brand_counts.items(), key=lambda x: x[1], reverse=True)
    ]
    
    # Paginate
    start = (page - 1) * page_size
    end = start + page_size
    cards = all_cards[start:end]
    has_more = end < len(all_cards)

    # Probe image dimensions for Sponsored Display cards that lack them.
    # This lets the frontend route portrait (skyscraper) ads to the RHS column.
    # Only runs on the paginated subset (~24 cards) so the cost is minimal.
    for card in cards:
        if card.get("ad_type") in ("Sponsored Display", "Sponsored_Display") and not card.get("dimensions"):
            img_url = card.get("image_url") or ""
            # Extract the file path from the API URL: /api/image/<retailer>/<client>/<folder>/<filename>
            if img_url.startswith("/api/image/"):
                parts = img_url.split("/api/image/", 1)[1].split("/", 1)
                if len(parts) == 2:
                    _ret, _rest = parts[0], parts[1]
                    # Try to find client from the next path segment
                    _rest_parts = _rest.split("/", 1)
                    if len(_rest_parts) == 2:
                        _cli, _rel = _rest_parts
                        _full = OUTPUT_ROOT / _ret / _cli / _rel
                        # Strip query string
                        _full = pathlib.Path(str(_full).split("?")[0])
                        if _full.exists():
                            try:
                                from PIL import Image as _PILImage
                                with _PILImage.open(_full) as _img:
                                    _w, _h = _img.size
                                    card["dimensions"] = {"width": _w, "height": _h}
                                    if _h > _w * 1.5:
                                        card["card_format"] = "tile"  # portrait → RHS column
                            except Exception:
                                pass

    result = {
        "retailer": retailer,
        "client": client,
        "cards": cards,
        "page": page,
        "page_size": page_size,
        "has_more": has_more,
        "total_cards": len(all_cards),
        "brands": brands_list,
        "filters": {
            "term": term or None,
            "advertiser": advertiser_filter or None
        }
    }
    
    # Store in cache (60s TTL)
    _set_cache(cache_key, result)
    
    # Add Server-Timing header for cache miss
    response = jsonify(result)
    response.headers["Server-Timing"] = "cache;desc=miss"
    print(f"[{retailer}/{client}] 💾 Cache MISS for page {page} - stored for 60s")
    
    return response


@app.route("/api/brands", methods=["GET"])
def api_brands():
    """
    Get brands list with counts and percentages

    Query params:
    - retailers (optional): comma-separated list of retailer slugs or "all" (default: "all")
    - client (optional): client name or "all" for all clients (default: "all")
    - advertiser (optional): filter by brand/advertiser name
    - start (optional): start date (YYYY-MM-DD)
    - end (optional): end date (YYYY-MM-DD)
    - term (optional): keyword filter
    - types (optional): comma-separated list of ad types to filter by
    """
    retailers_param = (request.args.get("retailers") or "all").strip().lower()
    clients = _parse_clients(request)
    advertiser = (request.args.get("advertiser") or "").strip()
    start_date = request.args.get("start")
    end_date = request.args.get("end")
    term = (request.args.get("term") or "").strip().lower()
    types_filter = (request.args.get("types") or "").strip()

    # Check cache first
    cache_params = {
        "retailers": retailers_param,
        "client": _norm_clients_for_cache(clients),
        "advertiser": advertiser,
        "start": start_date,
        "end": end_date,
        "term": term,
        "types": types_filter
    }
    cache_key = f"brands_{_cache_key(cache_params)}"
    
    if cache_key in _cache:
        cached_data, cached_time = _cache[cache_key]
        if time() - cached_time < _cache_ttl:
            print(f"[brands] Cache hit for {cache_params}")
            return jsonify(cached_data)

    # Parse retailers
    if retailers_param == "all":
        retailers_to_query = []
        if os.path.isdir(OUTPUT_ROOT):
            for item in os.listdir(OUTPUT_ROOT):
                item_path = os.path.join(OUTPUT_ROOT, item)
                if os.path.isdir(item_path):
                    retailers_to_query.append(item)
    else:
        retailers_to_query = [r.strip() for r in retailers_param.split(",")]

    # DB FAST PATH: handle ALL filter combos with a single SQL query
    if _USE_DB:
        types_list = [t.strip().lower() for t in types_filter.split(',') if t.strip()] if types_filter else None
        brands_list = db_get_brands_filtered(
            retailer=retailers_to_query if retailers_to_query else None,
            clients=clients if clients else None,
            start=start_date,
            end=end_date,
            keyword=term if term else None,
            ad_types=types_list,
        )
        result = {"brands": brands_list}
        _set_cache(cache_key, result)
        print(f"[brands] DB: {len(brands_list)} brands (filters: retailers={retailers_param}, types={types_filter or 'none'}, term={term or 'none'})")
        return jsonify(result)

    # FAST PATH: Use pre-computed brands from manifest when only retailer/client filters
    # (no date, term, advertiser, or types filters)
    has_complex_filters = bool(advertiser or start_date or end_date or term or types_filter)
    if not has_complex_filters:
        from utils.brand_utils import normalize_brand_for_matching
        
        # Merge brands across requested retailers (and optionally filter by clients)
        brand_counts = {}
        brand_display = {}
        
        if clients:
            # Use client-level pre-computed data
            precomputed_by_client = mf_brands_by_client()
            for retailer in retailers_to_query:
                retailer_data = precomputed_by_client.get(retailer, {})
                for client in clients:
                    client_brands = retailer_data.get(client, [])
                    for b in client_brands:
                        norm_key = normalize_brand_for_matching(b["brand"])
                        if norm_key not in brand_counts:
                            brand_counts[norm_key] = 0
                            brand_display[norm_key] = b["brand"]
                        brand_counts[norm_key] += b["count"]
        else:
            # Use retailer-level pre-computed data
            precomputed = mf_brands()
            for retailer in retailers_to_query:
                retailer_brands = precomputed.get(retailer, [])
                for b in retailer_brands:
                    norm_key = normalize_brand_for_matching(b["brand"])
                    if norm_key not in brand_counts:
                        brand_counts[norm_key] = 0
                        brand_display[norm_key] = b["brand"]
                    brand_counts[norm_key] += b["count"]
        
        # Only use fast path if we got data, otherwise fall through to slow path
        if brand_counts:
            # Append Unknown brand count from manifest
            unknown_total = 0
            unk_counts = mf_unknown_ad_counts_by_client() if clients else mf_unknown_ad_counts()
            for retailer in retailers_to_query:
                if clients:
                    retailer_data = unk_counts.get(retailer, {})
                    for client in clients:
                        unknown_total += retailer_data.get(client, 0)
                else:
                    unknown_total += unk_counts.get(retailer, 0)

            # Build response
            total = sum(brand_counts.values()) + unknown_total
            brands_list = []
            for norm_key, count in sorted(brand_counts.items(), key=lambda x: x[1], reverse=True):
                brands_list.append({
                    "brand": brand_display[norm_key],
                    "count": count,
                    "percentage": round((count / total) * 100, 1) if total > 0 else 0
                })
            if unknown_total > 0:
                brands_list.append({
                    "brand": "Unknown",
                    "count": unknown_total,
                    "percentage": round((unknown_total / total) * 100, 1) if total > 0 else 0,
                })
            
            result = {"brands": brands_list}
            _set_cache(cache_key, result)
            client_info = f" (clients: {len(clients)})" if clients else ""
            print(f"[brands] FAST PATH: {len(brands_list)} brands from manifest{client_info}")
            return jsonify(result)
        else:
            print(f"[brands] FAST PATH: No precomputed data, falling back to slow path")

    try:
        # Use brand index for advertiser-filtered queries
        if advertiser:
            brand_counts = {}
            brand_case_map = {}
            
            for retailer in retailers_to_query:
                # Get files from brand index
                brand_files = lookup_brand_files(retailer, advertiser)
                if not brand_files:
                    continue
                
                for fp, ad_indices in brand_files:
                    try:
                        with open(fp, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        # Extract client from path
                        path_parts = Path(fp).parts
                        file_client = path_parts[path_parts.index(retailer) + 1] if retailer in path_parts else "unknown"
                        
                        # Filter by client set
                        if clients and file_client not in clients:
                            continue
                        
                        # Filter by date range
                        run_ts = data.get("timestamp") or ""
                        run_day = run_ts[:10] if len(run_ts) >= 10 else ""
                        if start_date and run_day < start_date:
                            continue
                        if end_date and run_day > end_date:
                            continue
                        
                        # Filter by term
                        run_kw = (data.get("keyword") or "").lower()
                        if term and run_kw != term:
                            continue
                        
                        # Get ads
                        ads = data.get("ads") or []
                        
                        # Process specific ad indices or all ads
                        indices_to_check = ad_indices if ad_indices else range(len(ads))
                        
                        for idx in indices_to_check:
                            if idx >= len(ads):
                                continue
                            ad = ads[idx]

                            # Apply types filter if specified
                            types_list = [t.strip().lower() for t in types_filter.split(',') if t.strip()] if types_filter else []
                            if not _matches_ad_type_filter(ad, types_list):
                                continue

                            # Extract advertisers
                            advertisers = ad.get("advertisers") or []
                            if not advertisers:
                                ad_brand = ad.get("brand") or ad.get("advertiser")
                                if ad_brand:
                                    advertisers = [ad_brand]

                            # Count each advertiser
                            for adv in advertisers:
                                if not adv or adv == "Unknown":
                                    continue
                                from utils.brand_utils import normalize_brand_for_matching
                                canonical_brand = canonicalize_brand(adv)
                                display_name = canonical_brand if canonical_brand else adv
                                # Use normalized key for grouping (handles case/punctuation variations)
                                norm_key = normalize_brand_for_matching(display_name)
                                if norm_key not in brand_counts:
                                    brand_case_map[norm_key] = display_name
                                    brand_counts[norm_key] = 0
                                brand_counts[norm_key] += 1
                    
                    except Exception as e:
                        print(f"[brands] Error processing {fp}: {e}")
                        continue
            
            # Build response
            total = sum(brand_counts.values())
            brands_list = []
            for norm_brand, count in sorted(brand_counts.items(), key=lambda x: x[1], reverse=True):
                brands_list.append({
                    "brand": brand_case_map[norm_brand],
                    "count": count,
                    "percentage": round((count / total) * 100, 1) if total > 0 else 0
                })
            
            result = {"brands": brands_list}
            _set_cache(cache_key, result)
            print(f"[brands] Brand-filtered: {len(brands_list)} brands, {total} ads")
            return jsonify(result)
        
        # FAST PATH: Use manifest runs with per-run brand lists (no file I/O)
        # This handles date/client/term/types filtering without opening JSON files
        # NOTE: Brands in manifest are already canonicalized during build, so we
        # skip expensive canonicalize_brand() calls here for speed
        from utils.brand_utils import normalize_brand_for_matching
        
        # If types_filter is set, use brands_by_type from manifest (still fast - no file I/O)
        if types_filter:
            types_list = [t.strip().lower() for t in types_filter.split(',') if t.strip()]
            brand_counts = {}
            brand_case_map = {}
            runs_matched = 0
            
            for r in mf_runs():
                # Filter by retailer
                if r["retailer"] not in retailers_to_query:
                    continue
                
                # Filter by client set
                if clients and r["client"] not in clients:
                    continue
                
                # Filter by date range
                if start_date and r["day"] < start_date:
                    continue
                if end_date and r["day"] > end_date:
                    continue
                
                # Filter by term
                if term and r.get("keyword", "").lower() != term:
                    continue
                
                runs_matched += 1
                
                # Use brands_by_type from manifest (no file I/O!)
                brands_by_type = r.get("brands_by_type", {})
                
                # Match requested types against available types in this run
                for ad_type, type_brands in brands_by_type.items():
                    ad_type_normalized = ad_type.lower().replace("_", " ").replace("-", " ")
                    
                    # Check if this ad type matches any requested type
                    type_matches = False
                    for req_type in types_list:
                        req_type_normalized = req_type.lower().replace("_", " ").replace("-", " ")
                        if (req_type_normalized == ad_type_normalized or 
                            req_type_normalized in ad_type_normalized or 
                            ad_type_normalized in req_type_normalized):
                            type_matches = True
                            break
                    
                    if not type_matches:
                        continue
                    
                    # Count brands for this matching type
                    for brand_name in type_brands:
                        if not brand_name or brand_name == "Unknown":
                            continue
                        # Brands are already canonicalized in manifest
                        norm_key = normalize_brand_for_matching(brand_name)
                        if norm_key not in brand_counts:
                            brand_case_map[norm_key] = brand_name
                            brand_counts[norm_key] = 0
                        brand_counts[norm_key] += 1
            
            # Build response
            total = sum(brand_counts.values())
            brands_list = []
            for norm_brand, count in sorted(brand_counts.items(), key=lambda x: x[1], reverse=True):
                brands_list.append({
                    "brand": brand_case_map[norm_brand],
                    "count": count,
                    "percentage": round((count / total) * 100, 1) if total > 0 else 0
                })
            
            result = {"brands": brands_list}
            _set_cache(cache_key, result)
            print(f"[brands] Type-filtered FAST: {len(brands_list)} brands, {total} ads, {runs_matched} runs (no file I/O)")
            return jsonify(result)
        
        # No types filter - use fast path with manifest brand lists
        brand_counts = {}
        brand_case_map = {}
        runs_matched = 0
        
        for r in mf_runs():
            # Filter by retailer
            if r["retailer"] not in retailers_to_query:
                continue
            
            # Filter by client set
            if clients and r["client"] not in clients:
                continue
            
            # Filter by date range
            if start_date and r["day"] < start_date:
                continue
            if end_date and r["day"] > end_date:
                continue
            
            # Filter by term
            if term and r.get("keyword", "").lower() != term:
                continue
            
            runs_matched += 1
            
            # Use per-run brand list from manifest (already canonicalized during build!)
            run_brands = r.get("brands", [])
            for brand_name in run_brands:
                if not brand_name or brand_name == "Unknown":
                    continue
                # Skip canonicalize_brand() - brands are pre-canonicalized in manifest
                norm_key = normalize_brand_for_matching(brand_name)
                if norm_key not in brand_counts:
                    brand_case_map[norm_key] = brand_name
                    brand_counts[norm_key] = 0
                brand_counts[norm_key] += 1
        
        # Build response
        total = sum(brand_counts.values())
        brands_list = []
        for norm_brand, count in sorted(brand_counts.items(), key=lambda x: x[1], reverse=True):
            brands_list.append({
                "brand": brand_case_map[norm_brand],
                "count": count,
                "percentage": round((count / total) * 100, 1) if total > 0 else 0
            })
        
        result = {"brands": brands_list}
        _set_cache(cache_key, result)
        print(f"[brands] MANIFEST FAST: {len(brands_list)} brands, {total} ads, {runs_matched} runs (no file I/O)")
        return jsonify(result)
    except Exception as e:
        print(f"[brands] Error fetching brands: {str(e)}")
        return jsonify({"error": f"Failed to fetch brands: {str(e)}"}), 500

@app.route("/api/timeline", methods=["GET"])
def api_timeline():
    """
    Get all timestamps for timeline visualization (lightweight, no card loading).
    
    Query params:
    - retailer (required): retailer slug
    - client (optional): client name or comma-separated list
    - start (optional): start date (YYYY-MM-DD)
    - end (optional): end date (YYYY-MM-DD)
    - term (optional): keyword filter
    - advertiser (optional): brand filter
    
    Returns:
    - timestamps: array of ISO Z timestamps
    """
    retailer = request.args.get("retailer")
    if not retailer:
        return jsonify({"error": "retailer is required"}), 400
    
    clients = _parse_clients(request)
    advertiser = (request.args.get("advertiser") or "").strip()
    start_date = request.args.get("start")
    end_date = request.args.get("end")
    term = (request.args.get("term") or "").strip().lower()
    
    timestamps = []
    
    # Use brand index for advertiser-filtered queries
    if advertiser:
        brand_files = lookup_brand_files(retailer, advertiser)
        if brand_files:
            for fp, ad_indices in brand_files:
                try:
                    with open(fp, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # Extract client from path
                    path_parts = Path(fp).parts
                    file_client = path_parts[path_parts.index(retailer) + 1] if retailer in path_parts else "unknown"
                    
                    # Filter by client set
                    if clients and file_client not in clients:
                        continue
                    
                    # Filter by date range
                    run_ts = data.get("timestamp") or ""
                    run_day = run_ts[:10] if len(run_ts) >= 10 else ""
                    if start_date and run_day < start_date:
                        continue
                    if end_date and run_day > end_date:
                        continue
                    
                    # Filter by term
                    run_kw = (data.get("keyword") or "").lower()
                    if term and run_kw != term:
                        continue
                    
                    # Get ads
                    ads = data.get("ads") or []
                    indices_to_check = ad_indices if ad_indices else range(len(ads))
                    
                    for idx in indices_to_check:
                        if idx >= len(ads):
                            continue
                        ad = ads[idx]
                        # Use run timestamp for each ad
                        timestamps.append(run_ts)
                
                except Exception as e:
                    print(f"[timeline] Error processing {fp}: {e}")
                    continue
    else:
        # Use manifest for general queries
        for r in mf_runs():
            if r["retailer"] != retailer:
                continue
            
            # Filter by client set
            if clients and r["client"] not in clients:
                continue
            
            # Filter by date range
            if start_date and r["day"] < start_date:
                continue
            if end_date and r["day"] > end_date:
                continue
            
            # Filter by term
            if term and r.get("keyword", "").lower() != term:
                continue
            
            # Add one timestamp per ad in this run
            ad_count = int(r.get("ad_count") or 0)
            run_ts = r.get("timestamp") or ""
            for _ in range(ad_count):
                timestamps.append(run_ts)
    
    return jsonify({"timestamps": timestamps})


@app.route("/api/flag-review", methods=["POST"])
def api_flag_review():
    """Flag an ad or brand for re-review.
    Body JSON: { "type": "ad"|"brand", "ad_id": int (for ad), "brand_name": str (for brand), "reason": str (optional) }
    """
    if not _USE_DB:
        return jsonify({"error": "Database not available"}), 503

    data = request.get_json(silent=True) or {}
    flag_type = (data.get("type") or "").strip()
    reason = data.get("reason")

    if flag_type == "ad":
        ad_id = data.get("ad_id")
        if not ad_id:
            return jsonify({"error": "ad_id required for ad flags"}), 400
        ok = db_flag_ad_for_review(int(ad_id), reason)
        if ok:
            print(f"[flag-review] Ad {ad_id} flagged for review")
            return jsonify({"ok": True, "flag_type": "ad", "ad_id": ad_id})
        return jsonify({"error": "Failed to flag ad"}), 500

    elif flag_type == "brand":
        brand_name = (data.get("brand_name") or "").strip()
        if not brand_name:
            return jsonify({"error": "brand_name required for brand flags"}), 400
        ok = db_flag_brand_for_review(brand_name, reason)
        if ok:
            print(f"[flag-review] Brand '{brand_name}' flagged for review")
            return jsonify({"ok": True, "flag_type": "brand", "brand_name": brand_name})
        return jsonify({"error": "Failed to flag brand"}), 500

    return jsonify({"error": "type must be 'ad' or 'brand'"}), 400


@app.route("/api/brand-details", methods=["GET"])
def api_brand_details():
    """
    Get detailed information for a specific brand

    Query params:
    - brand (required): brand name
    - retailers (optional): comma-separated list of retailers or "all" (default: "all")
    - keywords (optional): comma-separated list of keywords to filter monthly_activity by

    Returns:
    - brand: brand name
    - total_ads: total number of ads for this brand
    - retailer_ads: object with retailer names as keys and ad counts as values
    - last_seen: ISO timestamp of most recent ad
    - top_keywords: array of {keyword, count} sorted by count descending
    - top_competitors: array of {brand, keyword, count} representing competitors appearing on same keywords
    - monthly_activity: array of {month, count} with optional keyword filtering
    """
    brand_name = (request.args.get("brand") or "").strip()
    retailers_param = (request.args.get("retailers") or "all").strip().lower()
    keywords_param = (request.args.get("keywords") or "").strip().lower()

    if not brand_name:
        return jsonify({"error": "brand parameter required"}), 400

    cache_params = {
        "endpoint": "brand-details",
        "brand": brand_name.lower(),
        "retailers": retailers_param,
        "keywords": keywords_param or None,
    }
    cache_key = _cache_key(cache_params)
    cached = _get_cached(cache_key)
    if cached is not None:
        return jsonify(cached)

    # Parse keywords filter early if provided (for competitors fetching the brand's data)
    filter_keywords = set()
    if keywords_param:
        filter_keywords = set(kw.strip().lower() for kw in keywords_param.split(",") if kw.strip())

    # Parse retailers
    if retailers_param == "all":
        retailers_to_query = []
        if os.path.isdir(OUTPUT_ROOT):
            for item in os.listdir(OUTPUT_ROOT):
                item_path = os.path.join(OUTPUT_ROOT, item)
                if os.path.isdir(item_path):
                    retailers_to_query.append(item)
    else:
        retailers_to_query = [r.strip() for r in retailers_param.split(",")]

    # DB fast path: 4 SQL queries instead of 3 full filesystem scans
    if _USE_DB:
        from time import perf_counter as _pc
        _t0 = _pc()
        db_retailers = None if retailers_param == "all" else retailers_to_query
        result = db_get_brand_details(
            brand_name=brand_name,
            retailers=db_retailers if db_retailers else None,
            keywords_filter=filter_keywords if filter_keywords else None,
        )
        _elapsed = (_pc() - _t0) * 1000
        if result is not None:
            print(f"[brand-details] DB: {brand_name} → {result['total_ads']} ads, "
                  f"{len(result['top_keywords'])} keywords, {len(result['top_competitors'])} competitors "
                  f"in {_elapsed:.0f}ms")
            _set_cache(cache_key, result)
            return jsonify(result)
        print(f"[brand-details] DB returned None for {brand_name}, falling back to JSON scan")

    try:
        # Collect all ads for this brand across retailers
        brand_ads = []

        for retailer in retailers_to_query:
            retailer_root = os.path.join(OUTPUT_ROOT, retailer)
            if not os.path.isdir(retailer_root):
                continue

            # Iterate through all clients
            for client_item in os.listdir(retailer_root):
                client_path = os.path.join(retailer_root, client_item)
                if not os.path.isdir(client_path):
                    continue

                rdir = runs_dir(retailer, client_item)
                if not os.path.isdir(rdir):
                    continue

                # Get all run files
                for item in os.listdir(rdir):
                    item_path = os.path.join(rdir, item)
                    if os.path.isfile(item_path) and item.startswith("run_results_") and item.endswith(".json"):
                        filename_base = item.replace("run_results_", "").replace(".json", "")
                        if filename_base.isdigit() and len(filename_base) == 14:
                            try:
                                with open(item_path, "r", encoding="utf-8") as f:
                                    data = json.load(f)

                                # Extract ads
                                ads = []
                                if "ads" in data:
                                    ads = data["ads"]
                                elif "results" in data:
                                    for result in data.get("results", []):
                                        ads.extend(result.get("ads", []))

                                # Find matching ads for this brand
                                file_keyword = (data.get("keyword") or data.get("search_term") or "").strip().lower()

                                # Skip this file if keywords_param was provided and this file's keyword is not in the filter
                                if filter_keywords and file_keyword not in filter_keywords:
                                    continue

                                for ad_index, ad in enumerate(ads):
                                    ad_brand = (ad.get("brand") or ad.get("advertiser") or "").strip()
                                    if ad_brand.lower() == brand_name.lower():
                                        timestamp = to_iso_z(ad.get("timestamp"), data.get("run_id"))
                                        # Use file-level keyword, not ad-level
                                        keyword = file_keyword

                                        brand_ads.append({
                                            "retailer": retailer,
                                            "client": client_item,
                                            "timestamp": timestamp,
                                            "keyword": keyword,
                                            "ad": ad
                                        })
                            except Exception as e:
                                print(f"[brand-details] Error processing {item_path}: {e}")
                                continue
                    elif os.path.isdir(item_path):
                        # Walmart nested structure
                        for subitem in os.listdir(item_path):
                            if subitem.startswith("run_results_") and subitem.endswith(".json"):
                                filename_base = subitem.replace("run_results_", "").replace(".json", "")
                                if filename_base.isdigit() and len(filename_base) == 14:
                                    subitem_path = os.path.join(item_path, subitem)
                                    try:
                                        with open(subitem_path, "r", encoding="utf-8") as f:
                                            data = json.load(f)

                                        ads = []
                                        if "ads" in data:
                                            ads = data["ads"]
                                        elif "results" in data:
                                            for result in data.get("results", []):
                                                ads.extend(result.get("ads", []))

                                        file_keyword = (data.get("keyword") or data.get("search_term") or "").strip().lower()

                                        # Skip this file if keywords_param was provided and this file's keyword is not in the filter
                                        if filter_keywords and file_keyword not in filter_keywords:
                                            continue

                                        for ad_index, ad in enumerate(ads):
                                            ad_brand = (ad.get("brand") or ad.get("advertiser") or "").strip()
                                            if ad_brand.lower() == brand_name.lower():
                                                timestamp = to_iso_z(ad.get("timestamp"), data.get("run_id"))
                                                # Use file-level keyword, not ad-level
                                                keyword = file_keyword

                                                brand_ads.append({
                                                    "retailer": retailer,
                                                    "client": client_item,
                                                    "timestamp": timestamp,
                                                    "keyword": keyword,
                                                    "ad": ad
                                                })
                                    except Exception as e:
                                        print(f"[brand-details] Error processing {subitem_path}: {e}")
                                        continue

        # Calculate statistics
        total_ads = len(brand_ads)

        # Count ads by retailer
        retailer_counts = {}
        for item in brand_ads:
            retailer = item["retailer"]
            retailer_counts[retailer] = retailer_counts.get(retailer, 0) + 1

        # Find last seen timestamp
        last_seen = None
        if brand_ads:
            timestamps = [item["timestamp"] for item in brand_ads if item["timestamp"]]
            if timestamps:
                last_seen = max(timestamps)

        # Count keyword frequencies
        keyword_counts = {}
        for item in brand_ads:
            keyword = item["keyword"]
            if keyword:
                keyword_counts[keyword] = keyword_counts.get(keyword, 0) + 1

        top_keywords = [
            {"keyword": kw, "count": count}
            for kw, count in sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        ]

        # brand_ads_filtered is already filtered by keywords_param if provided (filtered during collection)
        # or contains all keywords for the main brand request
        brand_ads_filtered = brand_ads

        # Find keywords and competitors
        # The keyword is stored at the JSON file level (data.get("keyword")),
        # not in individual ads
        keyword_counts = {}
        competitor_map = {}

        # Maps from (retailer, client) -> set of keywords where this brand appears
        brand_keywords = {}

        # First pass: collect all keywords where this brand appears
        for retailer in retailers_to_query:
            try:
                clients_to_query = []
                retailer_root = os.path.join(OUTPUT_ROOT, retailer)
                if os.path.isdir(retailer_root):
                    for item in os.listdir(retailer_root):
                        item_path = os.path.join(retailer_root, item)
                        if os.path.isdir(item_path):
                            clients_to_query.append(item)

                for client_name in clients_to_query:
                    rdir = runs_dir(retailer, client_name)
                    if not os.path.isdir(rdir):
                        continue

                    for item in os.listdir(rdir):
                        item_path = os.path.join(rdir, item)

                        def process_json_file(fpath):
                            try:
                                with open(fpath, "r", encoding="utf-8") as f:
                                    data = json.load(f)

                                # Get keyword from file level (not from ads)
                                keyword = (data.get("keyword") or data.get("search_term") or "").strip().lower()
                                if not keyword:
                                    return

                                # Extract ads
                                ads = []
                                if "ads" in data:
                                    ads = data["ads"]
                                elif "results" in data:
                                    for result in data.get("results", []):
                                        ads.extend(result.get("ads", []))

                                # Check if our brand appears in this keyword
                                for ad in ads:
                                    ad_brand = (ad.get("brand") or ad.get("advertiser") or "").strip()
                                    if ad_brand.lower() == brand_name.lower():
                                        keyword_counts[keyword] = keyword_counts.get(keyword, 0) + 1
                            except Exception:
                                pass

                        if os.path.isfile(item_path) and item.startswith("run_results_") and item.endswith(".json"):
                            filename_base = item.replace("run_results_", "").replace(".json", "")
                            if filename_base.isdigit() and len(filename_base) == 14:
                                process_json_file(item_path)
                        elif os.path.isdir(item_path):
                            # Walmart nested structure
                            for subitem in os.listdir(item_path):
                                if subitem.startswith("run_results_") and subitem.endswith(".json"):
                                    filename_base = subitem.replace("run_results_", "").replace(".json", "")
                                    if filename_base.isdigit() and len(filename_base) == 14:
                                        process_json_file(os.path.join(item_path, subitem))

            except Exception as e:
                print(f"[brand-details] Error querying retailer {retailer}: {e}")

        # Build top keywords
        top_keywords = [
            {"keyword": kw, "count": count}
            for kw, count in sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        ]

        # Second pass: find competitors on those keywords
        target_keywords = set(keyword_counts.keys())

        for retailer in retailers_to_query:
            try:
                clients_to_query = []
                retailer_root = os.path.join(OUTPUT_ROOT, retailer)
                if os.path.isdir(retailer_root):
                    for item in os.listdir(retailer_root):
                        item_path = os.path.join(retailer_root, item)
                        if os.path.isdir(item_path):
                            clients_to_query.append(item)

                for client_name in clients_to_query:
                    rdir = runs_dir(retailer, client_name)
                    if not os.path.isdir(rdir):
                        continue

                    for item in os.listdir(rdir):
                        item_path = os.path.join(rdir, item)

                        def process_competitor_file(fpath):
                            try:
                                with open(fpath, "r", encoding="utf-8") as f:
                                    data = json.load(f)

                                # Get keyword from file level
                                keyword = (data.get("keyword") or data.get("search_term") or "").strip().lower()
                                if keyword not in target_keywords:
                                    return

                                # Extract ads
                                ads = []
                                if "ads" in data:
                                    ads = data["ads"]
                                elif "results" in data:
                                    for result in data.get("results", []):
                                        ads.extend(result.get("ads", []))

                                # Count other brands on this keyword
                                for ad in ads:
                                    ad_brand = (ad.get("brand") or ad.get("advertiser") or "").strip()
                                    if ad_brand and ad_brand.lower() != brand_name.lower():
                                        key = (ad_brand, keyword)
                                        competitor_map[key] = competitor_map.get(key, 0) + 1
                            except Exception:
                                pass

                        if os.path.isfile(item_path) and item.startswith("run_results_") and item.endswith(".json"):
                            filename_base = item.replace("run_results_", "").replace(".json", "")
                            if filename_base.isdigit() and len(filename_base) == 14:
                                process_competitor_file(item_path)
                        elif os.path.isdir(item_path):
                            for subitem in os.listdir(item_path):
                                if subitem.startswith("run_results_") and subitem.endswith(".json"):
                                    filename_base = subitem.replace("run_results_", "").replace(".json", "")
                                    if filename_base.isdigit() and len(filename_base) == 14:
                                        process_competitor_file(os.path.join(item_path, subitem))

            except Exception as e:
                print(f"[brand-details] Error finding competitors for {retailer}: {e}")

        # Aggregate competitors by brand (sum across keywords) and maintain keyword breakdown
        competitors_by_brand = {}
        for (comp_brand, keyword), count in competitor_map.items():
            if comp_brand not in competitors_by_brand:
                competitors_by_brand[comp_brand] = {"total": 0, "keywords": {}}
            competitors_by_brand[comp_brand]["total"] += count
            competitors_by_brand[comp_brand]["keywords"][keyword] = count

        # Sort by total count and get top 10
        top_competitors = [
            {
                "brand": brand,
                "total": data["total"],
                "keywords": data["keywords"]
            }
            for brand, data in sorted(competitors_by_brand.items(), key=lambda x: x[1]["total"], reverse=True)[:10]
        ]

        # Calculate monthly activity for the last 12 months
        monthly_activity = {}
        now = datetime.now(timezone.utc)

        # Initialize all months in the last 12 months with 0 count
        for i in range(12):
            month_date = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
            # Go back i months
            for _ in range(i):
                if month_date.month == 1:
                    month_date = month_date.replace(year=month_date.year - 1, month=12)
                else:
                    month_date = month_date.replace(month=month_date.month - 1)
            month_key = month_date.strftime("%Y-%m")
            monthly_activity[month_key] = 0

        # Count ads per month - use filtered brand ads (already filtered by keywords if keywords_param provided)
        ads_for_monthly = brand_ads_filtered

        for item in ads_for_monthly:

            timestamp = item["timestamp"]
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    month_key = dt.strftime("%Y-%m")
                    if month_key in monthly_activity:
                        monthly_activity[month_key] += 1
                except Exception:
                    pass

        # Convert to sorted list
        monthly_activity_list = [
            {"month": month, "count": count}
            for month, count in sorted(monthly_activity.items())
        ]

        result = {
            "brand": brand_name,
            "total_ads": total_ads,
            "retailer_ads": retailer_counts,
            "last_seen": last_seen,
            "top_keywords": top_keywords,
            "top_competitors": top_competitors,
            "monthly_activity": monthly_activity_list
        }
        _set_cache(cache_key, result)
        return jsonify(result)
    except Exception as e:
        print(f"[brand-details] Error: {str(e)}")
        return jsonify({"error": f"Failed to fetch brand details: {str(e)}"}), 500

@app.route("/api/ads/batch", methods=["GET"])
def api_ads_batch():
    """
    Get ads in batch mode across multiple retailers/clients
    
    Query params:
    - retailers (required): comma-separated list of retailers
    - clients (required): comma-separated list of clients  
    - page (optional): page number (default 1)
    - page_size (optional): items per page (default 100, max 200)
    - start (optional): start date filter (YYYY-MM-DD)
    - end (optional): end date filter (YYYY-MM-DD)
    - search (optional): search term filter
    - types (optional): comma-separated ad types
    - brands (optional): comma-separated brands
    - sort (optional): latest|oldest|name
    - keywords (optional): comma-separated keywords
    """
    retailers_param = (request.args.get("retailers") or "").strip()
    clients_param = (request.args.get("clients") or "").strip()
    
    if not retailers_param or not clients_param:
        return jsonify({"error": "retailers and clients parameters required"}), 400
    
    retailers = [r.strip().lower() for r in retailers_param.split(",") if r.strip()]
    clients = [c.strip() for c in clients_param.split(",") if c.strip()]
    
    try:
        page = max(int(request.args.get("page", 1)), 1)
    except Exception:
        page = 1
    
    try:
        page_size = min(max(int(request.args.get("page_size", 100)), 1), 200)
    except Exception:
        page_size = 100
    
    # Get filter params for caching
    start_date = request.args.get("start")
    end_date = request.args.get("end")
    search_term = request.args.get("search")
    types_param = request.args.get("types")
    brands_param = request.args.get("brands")
    keywords_param = request.args.get("keywords")
    sort_param = request.args.get("sort", "latest")
    
    # Check cache
    cache_params = {
        "endpoint": "batch",
        "retailers": ",".join(sorted(retailers)),
        "clients": ",".join(sorted(clients)),
        "page": page,
        "page_size": page_size,
        "start": start_date,
        "end": end_date,
        "search": search_term,
        "types": types_param,
        "brands": brands_param,
        "keywords": keywords_param,
        "sort": sort_param
    }
    cache_key = _cache_key(cache_params)
    cached = _get_cached(cache_key)
    if cached is not None:
        return jsonify(cached)
    
    # Parse date filters for time-window restriction
    start_dt = None
    end_dt = None
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            pass
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
        except Exception:
            pass
    
    # Parse filter lists
    types_filter = [t.strip() for t in (types_param or "").split(",") if t.strip()]
    brands_filter = [b.strip().lower() for b in (brands_param or "").split(",") if b.strip()]
    keywords_filter = [k.strip().lower() for k in (keywords_param or "").split(",") if k.strip()]
    
    # Collect cards with early termination
    all_cards = []
    needed = page * page_size  # Only need enough for current page
    
    for retailer in retailers:
        for client in clients:
            rdir = runs_dir(retailer, client)
            if not os.path.isdir(rdir):
                continue
            
            # Get run files and filter by date window
            files = []
            for item in os.listdir(rdir):
                item_path = os.path.join(rdir, item)
                if os.path.isfile(item_path) and item.startswith("run_results_") and item.endswith(".json"):
                    filename_base = item.replace("run_results_", "").replace(".json", "")
                    if filename_base.isdigit() and len(filename_base) == 14:
                        # Time-window restrict: check if run_id falls in date range
                        if start_dt or end_dt:
                            try:
                                run_dt = datetime.strptime(filename_base, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
                                if start_dt and run_dt < start_dt:
                                    continue
                                if end_dt and run_dt > end_dt:
                                    continue
                            except Exception:
                                pass
                        files.append((item, item_path))
                elif os.path.isdir(item_path):
                    for subitem in os.listdir(item_path):
                        if subitem.startswith("run_results_") and subitem.endswith(".json"):
                            filename_base = subitem.replace("run_results_", "").replace(".json", "")
                            if filename_base.isdigit() and len(filename_base) == 14:
                                # Time-window restrict
                                if start_dt or end_dt:
                                    try:
                                        run_dt = datetime.strptime(filename_base, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
                                        if start_dt and run_dt < start_dt:
                                            continue
                                        if end_dt and run_dt > end_dt:
                                            continue
                                    except Exception:
                                        pass
                                files.append((subitem, os.path.join(item_path, subitem)))
            
            # Sort files by timestamp (newest first for early termination)
            files.sort(key=lambda x: x[0], reverse=True)
            
            # Process files with early termination
            for _, fpath in files:
                # Early termination: stop if we have enough cards
                if len(all_cards) >= needed:
                    break
                    
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # Handle both canonical and legacy structures
                    ads = data.get("ads", [])
                    if not ads and "results" in data:
                        for result in data["results"]:
                            ads.extend(result.get("ads", []))
                    
                    # Build cards with filtering
                    for ad in ads:
                        # Early termination check
                        if len(all_cards) >= needed:
                            break
                        
                        # Apply filters
                        if types_filter and ad.get("type") not in types_filter:
                            continue
                        if brands_filter and ad.get("brand", "").lower() not in brands_filter:
                            continue
                        if keywords_filter:
                            ad_text = f"{ad.get('title', '')} {ad.get('description', '')} {ad.get('brand', '')}".lower()
                            if not any(kw in ad_text for kw in keywords_filter):
                                continue
                        if search_term:
                            ad_text = f"{ad.get('title', '')} {ad.get('description', '')} {ad.get('brand', '')}".lower()
                            if search_term.lower() not in ad_text:
                                continue
                        
                        image_url = build_image_url_for_ad(retailer, client, ad)
                        if image_url:  # Only include ads with resolvable images
                            all_cards.append({
                                "id": ad.get("id", ""),
                                "retailer": retailer,
                                "client": client,
                                "type": ad.get("type", ""),
                                "brand": ad.get("brand", ""),
                                "image_url": image_url,
                                "timestamp": ad.get("timestamp", ""),
                                "advertisers": ad.get("advertisers", [])
                            })
                except Exception:
                    continue
            
            # Early termination: stop scanning clients if we have enough
            if len(all_cards) >= needed:
                break
        
        # Early termination: stop scanning retailers if we have enough
        if len(all_cards) >= needed:
            break
    
    # Sort by timestamp (newest first by default)
    if sort_param == "oldest":
        all_cards.sort(key=lambda x: x.get("timestamp", ""))
    elif sort_param == "name":
        all_cards.sort(key=lambda x: x.get("brand", "").lower())
    else:  # latest (default)
        all_cards.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    
    # Paginate
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_cards = all_cards[start_idx:end_idx]
    
    result = {
        "cards": page_cards,
        "page": page,
        "page_size": page_size,
        "has_more": end_idx < len(all_cards),
        "total_cards": len(all_cards)
    }
    
    # Cache the result
    _set_cache(cache_key, result)
    
    return jsonify(result)

@app.route("/api/ads/stats", methods=["GET"])
def api_ads_stats():
    """
    Get statistics for ads across retailers/clients
    
    Query params:
    - retailers (required): comma-separated list of retailers
    - clients (required): comma-separated list of clients
    - start (optional): start date filter
    - end (optional): end date filter
    - search (optional): search term filter
    - types (optional): comma-separated ad types
    - brands (optional): comma-separated brands
    """
    retailers_param = (request.args.get("retailers") or "").strip()
    clients_param = (request.args.get("clients") or "").strip()
    
    if not retailers_param or not clients_param:
        return jsonify({"error": "retailers and clients parameters required"}), 400
    
    retailers = [r.strip().lower() for r in retailers_param.split(",") if r.strip()]
    clients = [c.strip() for c in clients_param.split(",") if c.strip()]
    
    total_ads = 0
    total_brands = set()
    total_types = set()
    
    for retailer in retailers:
        for client in clients:
            rdir = runs_dir(retailer, client)
            if not os.path.isdir(rdir):
                continue
            
            # Get run files
            files = []
            for item in os.listdir(rdir):
                item_path = os.path.join(rdir, item)
                if os.path.isfile(item_path) and item.startswith("run_results_") and item.endswith(".json"):
                    filename_base = item.replace("run_results_", "").replace(".json", "")
                    if filename_base.isdigit() and len(filename_base) == 14:
                        files.append(item_path)
                elif os.path.isdir(item_path):
                    for subitem in os.listdir(item_path):
                        if subitem.startswith("run_results_") and subitem.endswith(".json"):
                            filename_base = subitem.replace("run_results_", "").replace(".json", "")
                            if filename_base.isdigit() and len(filename_base) == 14:
                                files.append(os.path.join(item_path, subitem))
            
            # Count ads and collect metadata
            for fpath in files:
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    ads = data.get("ads", [])
                    if not ads and "results" in data:
                        for result in data["results"]:
                            ads.extend(result.get("ads", []))
                    
                    total_ads += len(ads)
                    for ad in ads:
                        if ad.get("brand"):
                            total_brands.add(ad["brand"])
                        if ad.get("type"):
                            total_types.add(ad["type"])
                except Exception:
                    continue
    
    return jsonify({
        "total_ads": total_ads,
        "total_brands": len(total_brands),
        "total_types": len(total_types),
        "brands": sorted(list(total_brands)),
        "types": sorted(list(total_types))
    })

@app.route("/api/image/<retailer>/<client>/<path:filename>", methods=["GET"])
def api_image(retailer, client, filename):
    """
    Serve ad image with robust resolution for Walmart nested directories.
    
    Strategy:
    1. Exact match under client_root
    2. Exact match under nested runs/<run_id>/ (Walmart)
    3. Fuzzy match by filename across all allowed folders
    
    Query Parameters:
    - thumbnail: "true" (default) or "false" - serve thumbnail or full-size
    """
    # Normalize
    retailer = (retailer or "").lower()
    client = (client or "").strip()
    if not retailer or not client or not filename:
        abort(400, description="Missing retailer/client/path")

    # Lookup using robust resolver
    fpath, rel = find_image_file(retailer, client, filename)
    if not fpath or not fpath.is_file():
        return jsonify({"error": "image not found", "requested": filename}), 404

    # Check if thumbnail requested (default: true for grid view)
    thumbnail_param = request.args.get('thumbnail', 'true').lower()
    use_thumbnail = thumbnail_param in ('true', '1', 'yes')
    
    # Generate thumbnail for image files if requested
    if use_thumbnail and fpath.suffix.lower() in ['.png', '.jpg', '.jpeg', '.webp']:
        try:
            thumbnail_path = generate_thumbnail(fpath, max_width=800, quality=85)
            fpath = thumbnail_path
            ctype = 'image/jpeg'  # Thumbnails are always JPEG
        except Exception as e:
            print(f"⚠️  Thumbnail generation failed, serving original: {e}")
            # Continue with original file
            ctype = mimetypes.guess_type(str(fpath))[0] or "application/octet-stream"
    else:
        # Serve original file
        ctype = mimetypes.guess_type(str(fpath))[0] or "application/octet-stream"
    
    # Serve the file (original or thumbnail)
    resp = make_response(send_file(str(fpath), mimetype=ctype, as_attachment=False, conditional=True))
    
    # CORS/CORP hardening for images
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
    
    # Aggressive caching for immutable assets
    # Images are immutable (filename includes timestamp)
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    resp.headers["ETag"] = f'"{fpath.stat().st_mtime}-{fpath.stat().st_size}"'
    
    return resp

@app.route("/api/video/<retailer>/<client>/<path:req_relpath>", methods=["GET"])
def api_video(retailer, client, req_relpath):
    """
    Serve ad video with same robust resolution as images.
    Supports .mp4, .webm, .mov, .m4v files.
    """
    retailer = (retailer or "").lower().strip()
    client = (client or "").strip()
    if not retailer or not client or not req_relpath:
        abort(400, description="Missing retailer/client/path")

    fpath, rel = find_image_file(retailer, client, req_relpath)
    if not fpath or not fpath.is_file():
        abort(404, description=f"Video not found: {req_relpath}")

    ctype = "video/mp4" if str(fpath).lower().endswith(".mp4") else (mimetypes.guess_type(str(fpath))[0] or "application/octet-stream")
    resp = send_file(str(fpath), mimetype=ctype, as_attachment=False, conditional=True)

    # Set CORS and caching headers for video streaming
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, HEAD, OPTIONS"
    resp.headers["Cache-Control"] = "public, max-age=86400"
    resp.headers["Accept-Ranges"] = "bytes"

    return resp

@app.route("/api/image/placeholder")
def api_image_placeholder():
    """
    Generate a placeholder image with debug text.
    Used when actual image file cannot be found.
    """
    from io import BytesIO
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        # Fallback if PIL not installed
        return Response("MISSING IMAGE", mimetype="text/plain", status=200)
    
    text = request.args.get("text", "MISSING")
    w = int(request.args.get("w", 640))
    h = int(request.args.get("h", 360))
    bg = (240, 243, 247)  # light gray
    fg = (60, 65, 70)
    
    img = Image.new("RGB", (max(100, w), max(60, h)), color=bg)
    draw = ImageDraw.Draw(img)
    
    # Use default font
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    
    # Simple text centering
    try:
        # Modern PIL uses textbbox
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
    except AttributeError:
        # Older PIL uses textsize
        tw, th = draw.textsize(text, font=font)
    
    x = (img.width - tw) // 2
    y = (img.height - th) // 2
    draw.text((x, y), text, fill=fg, font=font)
    
    bio = BytesIO()
    img.save(bio, format="PNG", optimize=True)
    bio.seek(0)
    
    resp = Response(bio.read(), mimetype="image/png")
    resp.headers["Cache-Control"] = "public, max-age=300"
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
    return resp

@app.route("/proxy-image")
@app.route("/api/proxy-image")
def proxy_image():
    """
    Proxy for absolute image URLs (e.g., historical ngrok URLs).
    Fetches the image server-side with proper headers and returns it with CORS/CORP.
    """
    url = request.args.get("url")
    if not url:
        return jsonify(error="missing url"), 400

    try:
        upstream = requests.get(url, stream=True, timeout=15, headers={
            'ngrok-skip-browser-warning': 'true'
        })
        if not upstream.ok:
            abort(upstream.status_code)

        ct = upstream.headers.get('Content-Type', '')
        if not ct.startswith('image/'):
            return jsonify(error='upstream not image', content_type=ct), 415

        resp = Response(upstream.iter_content(64 * 1024), status=200, mimetype=ct)
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Cross-Origin-Resource-Policy'] = 'cross-origin'
        resp.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        return resp
    except requests.RequestException as e:
        return jsonify(error='upstream request failed', details=str(e)), 502

@app.route("/api/proxy-json")
def proxy_json():
    """
    JSON proxy endpoint for Builder.io to avoid CORS/headers issues.
    Proxies whitelisted internal API paths with ACAO: *.
    """
    from urllib.parse import urljoin
    
    # Get path parameter
    path = request.args.get("path", "")
    
    # Whitelist only /api/ paths to prevent SSRF
    if not path.startswith("/api/"):
        return jsonify({"error": "invalid path - must start with /api/"}), 400
    
    # Build upstream URL
    upstream_url = urljoin("http://localhost:5006", path)
    
    try:
        # Forward the request to local Flask
        r = requests.get(
            upstream_url,
            timeout=10,
            headers={'ngrok-skip-browser-warning': 'true'}
        )
        
        # Return response with permissive CORS
        return Response(
            r.content,
            status=r.status_code,
            headers={
                "Content-Type": r.headers.get("Content-Type", "application/json"),
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            }
        )
    except requests.RequestException as e:
        return jsonify({"error": "upstream request failed", "details": str(e)}), 502

@app.route("/api/logo/<retailer>", methods=["GET"])
def api_logo(retailer):
    """
    Serve retailer logo
    
    Looks for logo file in web/assets/logos/ with various naming patterns
    """
    retailer_lower = retailer.lower()
    
    # Mapping of retailer IDs to actual filenames
    logo_map = {
        'kroger': 'Kroger_Cart.png',
        'walmart': 'WMT.png',
        'amazon': 'AMZ.png',
        'amazonfresh': 'AMZFresh.png',
        'instacart': 'Instacart_Carrot.png',
        'target': 'Target.png',
        'albertsons': 'Albertsons_(logo).svg.png',
        'meijer': 'Meijer.png',
        'doordash': 'Doordash.png',
        'gopuff': 'gopuff.png',
        'hyvee': 'Hyvee.png',
        'ahold': 'Ahold.png',
        'absco': 'ABSCO.png'
    }
    
    # Try mapped filename first
    if retailer_lower in logo_map:
        filename = logo_map[retailer_lower]
        logo_path = os.path.join(ASSETS_ROOT, "logos", filename)
        if os.path.exists(logo_path):
            return _image_response(logo_path)
    
    # Try common patterns
    patterns = [
        f"{retailer}.png",
        f"{retailer}.svg",
        f"{retailer}.jpg",
        f"{retailer.upper()}.png",
        f"{retailer.capitalize()}.png"
    ]
    
    for pattern in patterns:
        logo_path = os.path.join(ASSETS_ROOT, "logos", pattern)
        if os.path.exists(logo_path):
            return _image_response(logo_path)
    
    return jsonify({"error": f"logo not found for {retailer}"}), 404


@app.route("/api/logo/brand/<path:brand_name>")
@app.route("/api/brand_logo/<path:brand_name>")
def api_brand_logo(brand_name: str):
    """Serve brand logo files from output/brand_logos.

    Accepts either a brand name (e.g., "Outshine") or a relative filename
    (e.g., "verified/outshine.png"). The latter is used when the database
    stores a subdirectory under BRAND_LOGOS_DIR such as verified/ or
    unverified/.
    """

    # Basic path traversal guard: reject any ".." segments
    parts = [p for p in brand_name.split("/") if p]
    if any(p == ".." for p in parts):
        abort(400)

    # If it already has an extension, try to serve it directly as a path
    # relative to BRAND_LOGOS_DIR. This allows URLs like
    # /api/brand_logo/unverified/foo.png or /api/brand_logo/verified/foo.png.
    if "." in brand_name:
        direct_path = (BRAND_LOGOS_DIR / "/".join(parts)).resolve()
        if direct_path.exists() and direct_path.is_file():
            return send_file(direct_path, as_attachment=False)
    
    # Otherwise, look up the brand in the database
    db = get_brand_logo_db()
    brand_key = brand_slug(brand_name)  # Normalize to database key format
    
    if brand_key in db.get("brands", {}):
        logo_file = (db["brands"][brand_key].get("logo_file") or "").strip()
        if logo_file:
            # Normalize optional "brand_logos/" prefix and treat remaining
            # portion as a path relative to BRAND_LOGOS_DIR.
            if logo_file.startswith("brand_logos/"):
                rel = logo_file.split("/", 1)[1]
            else:
                rel = logo_file
            logo_path = (BRAND_LOGOS_DIR / rel).resolve()
            if logo_path.exists() and logo_path.is_file():
                return send_file(logo_path, as_attachment=False)
    
    # Fallback: try case-insensitive filename match anywhere under
    # BRAND_LOGOS_DIR (supports nested verified/unverified folders).
    for file in BRAND_LOGOS_DIR.rglob("*"):
        if file.is_file() and file.stem.lower() == brand_name.lower():
            return send_file(file.resolve(), as_attachment=False)
    
    abort(404)



@app.route("/api/brand-logos/status")
def api_brand_logos_status():
    """Coverage API to see what brands are missing logos"""
    retailer = request.args.get("retailer") or "instacart"
    client = request.args.get("client")
    
    # Gather brands from cards API (one page is fine for a snapshot)
    url = f"{request.host_url.rstrip('/')}/api/ads/cards?retailer={retailer}&client={client}&page_size=500"
    try:
        resp = requests.get(url, timeout=10)
        cards = resp.json().get("cards", [])
    except Exception:
        cards = []

    L = get_brand_lexicon()
    db = get_brand_logo_db().get("brands", {})
    seen = {}
    for c in cards:
        rb = (c.get("brand") or c.get("brand_canonical") or "").strip()
        if not rb:
            continue
        canon = canonicalize_brand(rb)
        canon = normalize_brand(canon, c.get("ad_type"))
        if not canon:
            continue
        slug = brand_slug(canon)
        has_logo = slug in db
        seen.setdefault(slug, {"brand": canon, "has_logo": has_logo, "count": 0})
        seen[slug]["count"] += 1

    total = len(seen)
    covered = sum(1 for v in seen.values() if v["has_logo"])
    return jsonify({
        "retailer": retailer,
        "client": client,
        "total_canonical_brands": total,
        "covered": covered,
        "coverage_pct": (covered / total * 100.0) if total else 0.0,
        "brands": sorted(seen.values(), key=lambda x: (-x["has_logo"], -x["count"], x["brand"].lower()))
    })


# ============================================================================
# Legacy Endpoints (for backward compatibility)
# ============================================================================

@app.route('/api/ads', methods=['GET'])
def legacy_get_ads():
    """Legacy endpoint - redirects to /api/retailers"""
    return jsonify({
        "message": "This endpoint is deprecated. Use /api/retailers instead.",
        "retailers": list_retailers()
    })

@app.route('/api/ads/<client>', methods=['GET'])
def legacy_get_client_ads(client):
    """Legacy endpoint - needs retailer context"""
    # Try to find the client in any retailer
    for retailer in list_retailers():
        if client in list_clients(retailer):
            return jsonify({
                "message": "This endpoint is deprecated. Use /api/runs?retailer=<retailer>&client=<client> instead.",
                "redirect": f"/api/runs?retailer={retailer}&client={client}"
            })
    
    return jsonify({"error": "Client not found"}), 404

# ============================================================================
# Health & Status
# ============================================================================

@app.route("/api/debug/resolve", methods=["GET"])
def debug_resolve():
    """
    Debug endpoint to pinpoint image path mismatches.
    
    Returns detailed info about whether the requested path exists,
    and if not, where the file actually lives (leaf mismatch, extension variant, etc.)
    """
    retailer = (request.args.get("retailer") or "").lower().strip()
    client = (request.args.get("client") or "").strip()
    filename = (request.args.get("filename") or "").strip()
    
    if not (retailer and client and filename):
        return jsonify({"error": "retailer, client, filename required"}), 400
    
    # Decode and normalize
    rel = unquote(filename).lstrip("/").replace("\\", "/")
    base = os.path.basename(rel)
    
    try:
        leaves = allowed_subdirs(retailer)
    except ValueError:
        return jsonify({"error": f"unknown retailer: {retailer}"}), 404
    
    tried = []
    
    # 1) Try exact path as requested
    try:
        exact = _safe_join(OUTPUT_ROOT, retailer, client, rel)
        tried.append(exact)
        if os.path.isfile(exact):
            st = os.stat(exact)
            return jsonify({
                "exists": True,
                "where": "exact",
                "path": exact,
                "leaf": os.path.basename(os.path.dirname(exact)),
                "size": st.st_size,
                "requested": rel
            })
    except (ValueError, OSError):
        pass
    
    # 2) Try other leaves with same basename (leaf mismatch)
    for leaf in leaves:
        try:
            alt = _safe_join(OUTPUT_ROOT, retailer, client, leaf, base)
            tried.append(alt)
            if os.path.isfile(alt):
                st = os.stat(alt)
                return jsonify({
                    "exists": True,
                    "where": "leaf_mismatch",
                    "path": alt,
                    "leaf": leaf,
                    "size": st.st_size,
                    "requested": rel,
                    "note": f"Requested path had wrong leaf folder"
                })
        except (ValueError, OSError):
            continue
    
    # 3) Try extension variants
    name, ext = os.path.splitext(base)
    for leaf in leaves:
        for ext2 in (".jpg", ".jpeg", ".png", ".webp"):
            try:
                alt2 = _safe_join(OUTPUT_ROOT, retailer, client, leaf, name + ext2)
                tried.append(alt2)
                if os.path.isfile(alt2):
                    st = os.stat(alt2)
                    return jsonify({
                        "exists": True,
                        "where": "ext_variant",
                        "path": alt2,
                        "leaf": leaf,
                        "size": st.st_size,
                        "requested": rel,
                        "note": f"Found with extension {ext2} instead of {ext}"
                    })
            except (ValueError, OSError):
                continue
    
    # 4) Not found anywhere
    return jsonify({
        "exists": False,
        "path_requested": rel,
        "tried": tried[:20],  # Show first 20 attempts
        "allowed_subdirs": leaves,
        "note": "File not found on disk - may not have been scraped or filename differs"
    }), 404

@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "retailers_available": len(list_retailers())
    })

@app.route("/api/audit/images")
def api_audit_images():
    """
    Audit endpoint to measure image resolution coverage.
    Returns counts of resolvable vs. missing images for a retailer/client.
    """
    retailer = request.args.get("retailer")
    client = request.args.get("client")
    if not retailer or not client:
        abort(400, description="retailer and client are required")

    data = {
        "retailer": retailer,
        "client": client,
        "total_cards": 0,
        "resolvable": 0,
        "missing": 0,
        "examples": []
    }

    # Fetch cards with include_unresolved=1 to see all cards
    try:
        import requests as _r
        base = request.host_url.rstrip("/")
        r = _r.get(
            f"{base}/api/ads/cards",
            params={
                "retailer": retailer,
                "client": client,
                "page_size": 1000,
                "include_unresolved": "1"
            },
            timeout=15
        )
        cards = r.json().get("cards", [])
    except Exception as e:
        return jsonify({"error": "Failed to fetch cards", "details": str(e)}), 500

    data["total_cards"] = len(cards)
    for c in cards:
        if c.get("has_image") is True:
            data["resolvable"] += 1
        else:
            data["missing"] += 1
            if len(data["examples"]) < 10:
                data["examples"].append({
                    "ad_type": c.get("ad_type"),
                    "brand": c.get("brand"),
                    "image_path": c.get("image_path"),
                    "skip_reason": c.get("skip_reason"),
                    "run_file": c.get("run_file")
                })
    
    data["coverage_pct"] = (data["resolvable"] / data["total_cards"] * 100.0) if data["total_cards"] else 0.0
    return jsonify(data)

# ============================================================================
# Error Handlers
# ============================================================================

@app.errorhandler(404)
def not_found(e):
    """
    Handle 404 errors - prevent SPA catch-all from serving HTML for API routes.
    This ensures API 404s stay as JSON 404s and don't get rewritten to index.html.
    """
    if request.path.startswith("/api/"):
        return jsonify({"error": "not found", "path": request.path}), 404
    
    # For non-API routes, you could serve SPA index.html here if needed
    # return send_from_directory("client/dist", "index.html"), 200
    return jsonify({"error": "not found"}), 404

# ============================================================================
# Thumbnail Stats Endpoint
# ============================================================================

@app.route("/api/thumbnail/stats", methods=["GET"])
def api_thumbnail_stats():
    """Get thumbnail cache statistics."""
    stats = get_thumbnail_stats()
    cache_size = sum(f.stat().st_size for f in THUMBNAIL_CACHE.glob("*.jpg"))
    
    return jsonify({
        **stats,
        'cache_size_mb': round(cache_size / 1024 / 1024, 2),
        'cache_files': len(list(THUMBNAIL_CACHE.glob("*.jpg")))
    })

# ============================================================================
# Main
# ============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("Retail Ad Monitor API Server v2.0")
    print("=" * 60)
    print(f"SCRAPER_HOME: {SCRAPER_HOME}")
    print(f"OUTPUT_ROOT: {OUTPUT_ROOT}")
    print(f"ALLOWED_ORIGINS: {ALLOWED_ORIGINS or ['*']}")
    print(f"API_KEY: {'SET' if API_KEY else 'NOT SET'}")
    print()
    print("Available retailers:")
    for r in list_retailers():
        clients = list_clients(r)
        print(f"  - {r}: {len(clients)} client(s)")
    print()
    print("Starting server on http://0.0.0.0:5006")
    print("=" * 60)
    
    # Note: debug=True with threaded=True can cause issues
    # Using use_reloader=False to prevent double-loading issues
    app.run(host='0.0.0.0', port=5006, debug=False, threaded=True)
