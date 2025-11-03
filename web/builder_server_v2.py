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

from flask import Flask, jsonify, request, send_from_directory, make_response, send_file, Response, abort
from pathlib import Path
from urllib.parse import unquote, quote
from functools import lru_cache
import json
import glob
import mimetypes
import requests
import re
from datetime import datetime, timezone
from utils.path_taxonomy import allowed_subdirs, ADTYPE_TO_FOLDER
from core.brands import canonicalize

app = Flask(__name__)

# ============================================================================
# Configuration
# ============================================================================

SCRAPER_HOME = os.environ.get("SCRAPER_HOME", project_root)
OUTPUT_ROOT = Path(os.path.join(SCRAPER_HOME, "output"))
ASSETS_ROOT = os.path.join(SCRAPER_HOME, "web", "assets")
ALLOWED_ORIGINS = set((os.environ.get("ALLOWED_ORIGINS") or "").split(",")) - {""}
API_KEY = os.environ.get("API_KEY")  # For future POST endpoints

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


def utc_range_for(filter_name: str, start: str | None, end: str | None) -> tuple[datetime, datetime]:
    """
    Get UTC datetime range for filtering.
    filter_name: 'lifetime', 'mtd', 'ytd', or 'custom'
    start/end: YYYY-MM-DD strings for custom range
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
    def parse_date_utc(d: str) -> datetime:
        return datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    if start or end:
        # Handle cases where only start or only end is provided
        start_dt = parse_date_utc(start) if start else parse_date_utc(end)
        # If only start is provided, use it as the end date too (same day)
        # If only end is provided, use it as the start date too (same day)
        # If both are provided, use both with inclusive end-of-day
        end_dt = parse_date_utc(end) if end else parse_date_utc(start)

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
    Falls back to titlecase raw if not found.
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    L = get_brand_lexicon()
    token = re.sub(r'[^a-z0-9]+', '', raw.lower())
    cname = L["by_token"].get(token)
    if cname:
        return cname
    # fallback: return cleaned raw (retain user-friendly casing if it looks like a real word)
    return raw


def type_label_for(ad_type: str | None) -> str:
    """
    Convert ad type to human-readable label.
    Replaces underscores and hyphens with spaces, strips whitespace.
    """
    return (ad_type or "").replace("_", " ").replace("-", " ").strip()


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
    filename = os.path.basename(rec.get("logo_file") or "")
    if not filename:
        return None
    path = (BRAND_LOGOS_DIR / filename)
    if not path.is_file():
        return None
    return f"/api/brand_logo/{filename}"


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

    # Fallbacks: if image_url still missing and ad has CDN url, try fuzzy by filename
    if "image_url" not in media:
        cdn = ad.get("image_url")
        if isinstance(cdn, str) and cdn.strip():
            name = Path(cdn.split("?")[0]).name
            if name and not is_video_filename(name):
                f, r = find_image_file(retailer, client, name)
                if f:
                    media["image_url"] = f"/api/image/{retailer}/{client}/{r}"

    # Video fallback by CDN filename (optional convenience)
    if "video_url" not in media:
        cdn_v = ad.get("video_url") or ad.get("image_url")
        if isinstance(cdn_v, str) and is_video_filename(cdn_v):
            name = Path(cdn_v.split("?")[0]).name
            f, r = find_image_file(retailer, client, name)
            if f:
                media["video_url"] = f"/api/video/{retailer}/{client}/{r}"
                # Try a poster
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

# Folder synonyms (plural ↔ singular etc.)
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
            "GET /api/image/<retailer>/<client>/<filename>": "Serve ad image"
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
    """
    retailer = (request.args.get("retailer") or "").strip().lower()
    client = (request.args.get("client") or "").strip()
    term = (request.args.get("term") or "").strip().lower()
    advertiser_filter = (request.args.get("advertiser") or "").strip().lower()
    brands_filter = (request.args.get("brands") or "").strip()  # comma-separated list
    types_filter = (request.args.get("types") or "").strip()    # comma-separated list
    start_date = (request.args.get("start") or "").strip()  # YYYY-MM-DD format
    end_date = (request.args.get("end") or "").strip()      # YYYY-MM-DD format
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
    
    if not retailer:
        return jsonify({"error": "retailer parameter required"}), 400
    
    if not client:
        return jsonify({"error": "client parameter required"}), 400
    
    # Support client=all to query across all clients
    if client.lower() == "all":
        clients_to_query = []
        retailer_root = os.path.join(OUTPUT_ROOT, retailer)
        if os.path.isdir(retailer_root):
            for item in os.listdir(retailer_root):
                item_path = os.path.join(retailer_root, item)
                if os.path.isdir(item_path):
                    clients_to_query.append(item)
    else:
        clients_to_query = [client]
    
    # Collect files from all clients
    files = []
    for client_name in clients_to_query:
        rdir = runs_dir(retailer, client_name)
        
        if not os.path.isdir(rdir):
            continue
        
        # Get all run files (newest first) - handle both flat and nested structures
        # Prefer canonical files (run_results_YYYYMMDDHHMMSS.json) over legacy files
        for item in os.listdir(rdir):
            item_path = os.path.join(rdir, item)
            if os.path.isfile(item_path) and item.startswith("run_results_") and item.endswith(".json"):
                # Only include canonical format (run_results_YYYYMMDDHHMMSS.json)
                # Skip legacy format (run_results_{keyword}_{timestamp}.json)
                filename_base = item.replace("run_results_", "").replace(".json", "")
                # Canonical format is exactly 14 digits (YYYYMMDDHHMMSS)
                if filename_base.isdigit() and len(filename_base) == 14:
                    files.append((item, item_path, client_name))
            elif os.path.isdir(item_path):
                # Check subdirectories (Walmart structure)
                for subitem in os.listdir(item_path):
                    if subitem.startswith("run_results_") and subitem.endswith(".json"):
                        # Same canonical check for nested files
                        filename_base = subitem.replace("run_results_", "").replace(".json", "")
                        if filename_base.isdigit() and len(filename_base) == 14:
                            files.append((subitem, os.path.join(item_path, subitem), client_name))
    
    # Sort by filename (most recent first)
    files = sorted(files, key=lambda x: x[0], reverse=True)
    
    # Return empty if no files found
    if not files:
        return jsonify({
            "retailer": retailer,
            "client": client,
            "cards": [],
            "page": page,
            "page_size": page_size,
            "has_more": False,
            "total_cards": 0
        })
    
    # Collect all cards
    all_cards = []
    for fn, fpath, file_client in files:
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
                    full_path = os.path.join(OUTPUT_ROOT, retailer, client, filename)
                    if os.path.exists(full_path):
                        has_local_path = True
                        break
                    else:
                        # Path in JSON but file doesn't exist - clear filename to trigger fallback
                        print(f"⚠️  [{retailer}] Path in JSON doesn't exist: {filename}")
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
                    print(f"🔍 [{retailer}] Searching for image: ad_type={ad_type_hint}, leaf={leaf}")
                    if leaf:
                        # Look for files matching the taxonomy pattern in this ad type folder
                        search_dir = os.path.join(OUTPUT_ROOT, retailer, client, leaf)
                        print(f"🔍 [{retailer}] Search dir: {search_dir}, exists={os.path.isdir(search_dir)}")
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
                        parsed_advertisers = [adv.replace('_', ' ').title() for adv in parsed_advertisers if adv and adv != 'unknown']
                        # Canonicalize brand names
                        parsed_advertisers = [canonicalize(adv) or adv for adv in parsed_advertisers]
                        # Filter out blocked brands (ad types)
                        advertisers = [adv for adv in parsed_advertisers if not is_blocked_brand(adv)]

                # Format brand string for display
                brand = ' + '.join(advertisers) if advertisers else "Unknown"
                
                # Extract message/headline
                message = ad.get("message") or ad.get("headline") or ad.get("description") or ""
                
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
                    "ad_type": ad.get("type") or ad.get("ad_type"),
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
                
                # Note: Video/poster support can be added later if needed
                # For now, focus on ensuring every card has an image
                
                all_cards.append(card)
        except Exception as e:
            print(f"Error processing {fn}: {e}")
            pass
    
    # Filter by advertiser if specified
    if advertiser_filter:
        filtered_cards = []
        for card in all_cards:
            # Check if any advertiser in the array matches the filter
            advertisers = card.get("advertisers", [])
            if any(advertiser_filter in adv.lower() for adv in advertisers):
                filtered_cards.append(card)
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
        if types_list:
            filtered_cards = []
            for card in all_cards:
                card_type = (card.get("ad_type") or "").lower()
                # Normalize for comparison: replace underscores and hyphens with spaces
                card_type_normalized = card_type.replace("_", " ").replace("-", " ")
                # Check if any requested type matches the card type (exact or substring)
                if any(req_type in card_type_normalized or card_type_normalized in req_type for req_type in types_list):
                    filtered_cards.append(card)
            all_cards = filtered_cards

    # Filter by date range if specified (UTC-aware)
    # If start_date is provided (even without end_date), apply the filter
    # Empty/missing parameters mean lifetime (all dates)
    if start_date or end_date:
        # Log the filtering operation for debugging
        print(f"[{retailer}/{client}] 📅 Date filter requested: start={start_date}, end={end_date}")

        # Determine filter type and get UTC range
        filter_name = "custom"  # Default to custom range
        start_dt, end_dt = utc_range_for(filter_name, start_date, end_date)

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
    
    # Calculate brand aggregations from ALL cards (before pagination)
    brand_counts = {}
    for card in all_cards:
        brand = card.get("brand") or card.get("brand_canonical") or "Unknown"
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
    
    return jsonify({
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
    })

@app.route("/api/brands", methods=["GET"])
def api_brands():
    """
    Get brands list with counts and percentages

    Query params:
    - retailers (optional): comma-separated list of retailer slugs or "all" (default: "all")
    - client (optional): client name or "all" for all clients (default: "all")
    """
    retailers_param = (request.args.get("retailers") or "all").strip().lower()
    client = (request.args.get("client") or "").strip() or "all"

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

    try:
        # Collect all cards from all retailers and clients to aggregate brands
        all_cards = []

        for retailer in retailers_to_query:
            # Support client=all to query across all clients
            if client.lower() == "all":
                clients_to_query = []
                retailer_root = os.path.join(OUTPUT_ROOT, retailer)
                if os.path.isdir(retailer_root):
                    for item in os.listdir(retailer_root):
                        item_path = os.path.join(retailer_root, item)
                        if os.path.isdir(item_path):
                            clients_to_query.append(item)
            else:
                clients_to_query = [client]

            for client_name in clients_to_query:
                rdir = runs_dir(retailer, client_name)

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

                                # Extract ads from various JSON structures
                                ads = []
                                if "ads" in data:
                                    ads = data["ads"]
                                elif "results" in data:
                                    for result in data.get("results", []):
                                        ads.extend(result.get("ads", []))

                                # Process each ad into a card
                                for ad_index, ad in enumerate(ads):
                                    brand = (ad.get("brand") or ad.get("advertiser") or "Unknown").strip()
                                    timestamp = to_iso_z(ad.get("timestamp"), data.get("run_id"))

                                    all_cards.append({
                                        "brand": brand,
                                        "timestamp": timestamp,
                                        "run_file": item,
                                        "ad_index": ad_index,
                                        "client": client_name,
                                        "retailer": retailer
                                    })
                            except Exception as e:
                                print(f"[brands] Error processing file {item_path}: {e}")
                                continue
                    elif os.path.isdir(item_path):
                        # Check subdirectories (Walmart structure)
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

                                        for ad_index, ad in enumerate(ads):
                                            brand = (ad.get("brand") or ad.get("advertiser") or "Unknown").strip()
                                            timestamp = to_iso_z(ad.get("timestamp"), data.get("run_id"))

                                            all_cards.append({
                                                "brand": brand,
                                                "timestamp": timestamp,
                                                "run_file": subitem,
                                                "ad_index": ad_index,
                                                "client": client_name,
                                                "retailer": retailer
                                            })
                                    except Exception as e:
                                        print(f"[brands] Error processing file {subitem_path}: {e}")
                                        continue

        # Deduplicate cards
        seen = set()
        deduped_cards = []
        for card in all_cards:
            key = (card.get("retailer"), card.get("run_file"), card.get("ad_index"))
            if key not in seen:
                seen.add(key)
                deduped_cards.append(card)

        # Calculate brand aggregations
        brand_counts = {}
        for card in deduped_cards:
            brand = card.get("brand") or "Unknown"
            brand_counts[brand] = brand_counts.get(brand, 0) + 1

        # Sort brands alphabetically (by brand name)
        brands_list = [
            {"brand": brand, "count": count, "percentage": round((count / len(deduped_cards)) * 100, 1) if deduped_cards else 0}
            for brand, count in sorted(brand_counts.items(), key=lambda x: x[0].lower())
        ]

        return jsonify({
            "retailers": retailers_param,
            "client": client,
            "brands": brands_list
        })
    except Exception as e:
        print(f"[brands] Error fetching brands: {str(e)}")
        return jsonify({"error": f"Failed to fetch brands: {str(e)}"}), 500

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

        # Filter brand_ads to only top keywords for consistency (case-insensitive)
        top_keywords_set = set(kw["keyword"].lower() for kw in top_keywords)
        brand_ads_filtered = [ad for ad in brand_ads if ad["keyword"].lower() in top_keywords_set]

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

        # Parse keywords filter if provided (for competitors fetching the brand's data)
        filter_keywords = set()
        if keywords_param:
            filter_keywords = set(kw.strip().lower() for kw in keywords_param.split(",") if kw.strip())

        # Count ads per month - use filtered brand ads (only top keywords for consistency)
        ads_for_monthly = brand_ads_filtered
        if filter_keywords:
            # If keywords param provided (competitor request), filter further
            ads_for_monthly = [ad for ad in brand_ads_filtered if ad["keyword"].lower() in filter_keywords]

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

        return jsonify({
            "brand": brand_name,
            "total_ads": total_ads,
            "retailer_ads": retailer_counts,
            "last_seen": last_seen,
            "top_keywords": top_keywords,
            "top_competitors": top_competitors,
            "monthly_activity": monthly_activity_list
        })
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
    
    try:
        page = max(int(request.args.get("page", 1)), 1)
    except Exception:
        page = 1
    
    try:
        page_size = min(max(int(request.args.get("page_size", 100)), 1), 200)
    except Exception:
        page_size = 100
    
    # Collect all cards from all retailer/client combinations
    all_cards = []
    for retailer in retailers:
        for client in clients:
            # Reuse the cards endpoint logic
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
                        files.append((item, item_path))
                elif os.path.isdir(item_path):
                    for subitem in os.listdir(item_path):
                        if subitem.startswith("run_results_") and subitem.endswith(".json"):
                            filename_base = subitem.replace("run_results_", "").replace(".json", "")
                            if filename_base.isdigit() and len(filename_base) == 14:
                                files.append((subitem, os.path.join(item_path, subitem)))
            
            # Process each file
            for _, fpath in files:
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # Handle both canonical and legacy structures
                    ads = data.get("ads", [])
                    if not ads and "results" in data:
                        for result in data["results"]:
                            ads.extend(result.get("ads", []))
                    
                    # Build cards
                    for ad in ads:
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
    
    # Sort by timestamp (newest first)
    all_cards.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    
    # Paginate
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_cards = all_cards[start_idx:end_idx]
    
    return jsonify({
        "cards": page_cards,
        "page": page,
        "page_size": page_size,
        "has_more": end_idx < len(all_cards),
        "total_cards": len(all_cards)
    })

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

    # Content type
    ctype = mimetypes.guess_type(str(fpath))[0] or "application/octet-stream"
    return send_file(str(fpath), mimetype=ctype, as_attachment=False, conditional=True)

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
    return send_file(str(fpath), mimetype=ctype, as_attachment=False, conditional=True)

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
        'kroger': 'Kroger.png',
        'walmart': 'WMT.png',
        'amazon': 'AMZ.png',
        'amazonfresh': 'AMZFresh.png',
        'instacart': 'Instacart Long.png',
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


@app.route("/api/brand_logo/<path:brand_name>")
def api_brand_logo(brand_name: str):
    """
    Serve brand logo files from output/brand_logos.
    Accepts either a brand name (e.g., "Outshine") or filename (e.g., "outshine.png").
    Looks up the actual filename in the brand logo database.
    """
    brand_name = os.path.basename(brand_name)  # Security: prevent path traversal
    
    # If it already has an extension, try to serve it directly
    if '.' in brand_name:
        path = (BRAND_LOGOS_DIR / brand_name).resolve()
        if path.exists() and path.is_file():
            return send_file(path, as_attachment=False)
    
    # Otherwise, look up the brand in the database
    db = get_brand_logo_db()
    brand_key = brand_slug(brand_name)  # Normalize to database key format
    
    if brand_key in db.get("brands", {}):
        logo_file = db["brands"][brand_key].get("logo_file")
        if logo_file:
            path = (BRAND_LOGOS_DIR / logo_file).resolve()
            if path.exists() and path.is_file():
                return send_file(path, as_attachment=False)
    
    # Fallback: try case-insensitive filename match
    for file in BRAND_LOGOS_DIR.glob("*"):
        if file.stem.lower() == brand_name.lower():
            return send_file(file, as_attachment=False)
    
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
    
    app.run(host='0.0.0.0', port=5006, debug=True)
