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
from urllib.parse import unquote
import json
import glob
import mimetypes
import requests
import re
from datetime import datetime, timezone
from utils.path_taxonomy import allowed_subdirs

app = Flask(__name__)

# ============================================================================
# Configuration
# ============================================================================

SCRAPER_HOME = os.environ.get("SCRAPER_HOME", project_root)
OUTPUT_ROOT = os.path.join(SCRAPER_HOME, "output")
ASSETS_ROOT = os.path.join(SCRAPER_HOME, "web", "assets")
ALLOWED_ORIGINS = set((os.environ.get("ALLOWED_ORIGINS") or "").split(",")) - {""}
API_KEY = os.environ.get("API_KEY")  # For future POST endpoints

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
    
    if start and end:
        start_dt = parse_date_utc(start)  # 00:00Z that day
        # Inclusive end-of-day
        end_dt = parse_date_utc(end).replace(hour=23, minute=59, second=59)
        return start_dt, end_dt
    
    # Default: lifetime
    return datetime.min.replace(tzinfo=timezone.utc), datetime.max.replace(tzinfo=timezone.utc)


def type_label_for(ad_type: str | None) -> str:
    """
    Convert ad type to human-readable label.
    Replaces underscores and hyphens with spaces, strips whitespace.
    """
    return (ad_type or "").replace("_", " ").replace("-", " ").strip()


# Blocked brands - ad types that should never be used as brand names
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
    "tile takeover",
    "featured brand",
    "native ad",
    "display ads",
    "video ads",
    "top of aisle",
    "shelf banner",
    "category banner",
}


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
        exclude = {'runs', '.DS_Store', '__pycache__'}
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
            "SCRAPER_HOME": SCRAPER_HOME,
            "OUTPUT_ROOT": OUTPUT_ROOT,
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
                            advertisers.update(ad_advertisers)
                        else:
                            # Fallback to legacy fields
                            legacy = ad.get("brand") or ad.get("advertiser")
                            if legacy:
                                advertisers.add(legacy)
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
    - page (optional): page number (default 1)
    - page_size (optional): items per page (default 24, max 100)
    """
    retailer = (request.args.get("retailer") or "").strip().lower()
    client = (request.args.get("client") or "").strip()
    term = (request.args.get("term") or "").strip().lower()
    advertiser_filter = (request.args.get("advertiser") or "").strip().lower()
    start_date = (request.args.get("start") or "").strip()  # YYYY-MM-DD format
    end_date = (request.args.get("end") or "").strip()      # YYYY-MM-DD format

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
        for item in os.listdir(rdir):
            item_path = os.path.join(rdir, item)
            if os.path.isfile(item_path) and item.startswith("run_results_") and item.endswith(".json"):
                files.append((item, item_path, client_name))
            elif os.path.isdir(item_path):
                # Check subdirectories (Walmart structure)
                for subitem in os.listdir(item_path):
                    if subitem.startswith("run_results_") and subitem.endswith(".json"):
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
                                print(f"��� [{retailer}] Found {len(files)} files in {leaf}/, keyword={kw}, timestamp={ts_date}_{ts_hour}:{ts_minute}, brands={ad_brands_lower}")
                                
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
                
                # Build media URLs (image for grid, optional video for modal)
                media = build_media_urls_for_ad(retailer, file_client, ad)
                
                # Only include cards with an image for the grid (skip if no image available)
                image_api = media.get("image_url")
                if not image_api:
                    continue
                
                # Extract advertisers - handle new array format and legacy fields
                advertisers = ad.get("advertisers")  # New array format
                if not advertisers:
                    # Fallback to legacy fields
                    legacy_brand = ad.get("brand") or ad.get("advertiser") or ad.get("title")
                    advertisers = [legacy_brand] if legacy_brand else []

                # Filter out blocked brands (ad types that shouldn't be brand names)
                advertisers = [adv for adv in (advertisers or []) if adv and not is_blocked_brand(adv)]

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
                
                # Build card with image (required) and optional video/poster
                card = {
                    "retailer": retailer,
                    "client": file_client,
                    "keyword": data.get("keyword") or data.get("search_term"),
                    "ad_type": ad.get("type") or ad.get("ad_type"),
                    "brand": brand,
                    "advertisers": advertisers,  # NEW: array of advertisers for filtering
                    "message": message,
                    "image_url": image_api,
                    "run_file": fn,
                    "timestamp": iso_ts,  # Normalized ISO Z
                    "timestamp_ms": epoch_ms,  # Epoch milliseconds for easy filtering
                    "featured": ad.get("featured", False),
                    "ad_index": idx  # Add index for unique identification
                }
                
                # Attach optional video for modal/detail use
                if media.get("video_url"):
                    card["video_url"] = media["video_url"]
                if media.get("poster_url"):
                    card["poster_url"] = media["poster_url"]
                
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

    # Filter by date range if specified (UTC-aware)
    if start_date or end_date:
        # Determine filter type and get UTC range
        filter_name = "custom"  # Default to custom range
        start_dt, end_dt = utc_range_for(filter_name, start_date, end_date)
        
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
                print(f"Warning: Could not parse timestamp '{timestamp}': {e}")
                continue
        
        all_cards = filtered_cards

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
        "filters": {
            "term": term or None,
            "advertiser": advertiser_filter or None
        }
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

@app.route("/proxy-image")
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
