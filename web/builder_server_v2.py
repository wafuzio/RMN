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
from datetime import datetime
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
            
            # Extract timestamp from various possible fields
            timestamp = data.get("timestamp") or data.get("ts") or data.get("date")
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
                "timestamp": timestamp,
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
    - client (required): client name
    - term (optional): filter by search term
    - advertiser (optional): filter by advertiser/brand name
    - page (optional): page number (default 1)
    - page_size (optional): items per page (default 24, max 100)
    """
    retailer = (request.args.get("retailer") or "").strip().lower()
    client = (request.args.get("client") or "").strip()
    term = (request.args.get("term") or "").strip().lower()
    advertiser_filter = (request.args.get("advertiser") or "").strip().lower()
    
    try:
        page = max(int(request.args.get("page", 1)), 1)
    except Exception:
        page = 1
    
    try:
        page_size = min(max(int(request.args.get("page_size", 24)), 1), 100)
    except Exception:
        page_size = 24
    
    if not (retailer and client):
        return jsonify({"error": "retailer and client parameters required"}), 400
    
    rdir = runs_dir(retailer, client)
    
    if not os.path.isdir(rdir):
        return jsonify({
            "retailer": retailer,
            "client": client,
            "cards": [],
            "page": page,
            "page_size": page_size,
            "has_more": False,
            "total_cards": 0
        })
    
    # Get all run files (newest first) - handle both flat and nested structures
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
    
    # Collect all cards
    all_cards = []
    for fn, fpath in files:
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
                    has_local_path = True
                    break
                
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
                                # List files and find matches (prefer image extensions over videos)
                                files = os.listdir(search_dir)
                                print(f"🔍 [{retailer}] Found {len(files)} files in {leaf}/, keyword={kw}")
                                # Sort files to prefer .png, .jpg, .jpeg, .webp over .mp4
                                image_exts = ('.png', '.jpg', '.jpeg', '.webp')
                                files_sorted = sorted(files, key=lambda f: (not f.endswith(image_exts), f))
                                for f in files_sorted:
                                    # Match pattern: retailer__*__ad_type__*__keyword__*
                                    # Only match image files (not videos)
                                    if f.startswith(f"{retailer}__") and kw in f.lower() and f.endswith(image_exts):
                                        filename = os.path.join(leaf, f)
                                        print(f"✅ [{retailer}] Matched image: {filename}")
                                        break
                                if not filename:
                                    print(f"⚠️  [{retailer}] No matching image found for keyword={kw} in {leaf}/")
                            except Exception as e:
                                print(f"❌ [{retailer}] Error searching for images: {e}")
                
                # Build API image URL using deterministic path resolution
                image_api = ""
                if filename:
                    # If filename already includes subdir (e.g., "Skyscraper/foo.png"), use as-is
                    if "/" in filename:
                        filename_for_url = filename
                    else:
                        # Use find_image_rel to locate the actual file on disk
                        ad_type_hint = ad.get("type") or ad.get("ad_type") or ""
                        leaf_hint = leaf_for(ad_type_hint)
                        
                        # Extract basename without extension for searching
                        basename_no_ext = os.path.splitext(filename)[0]
                        
                        # Find the actual relative path
                        rel_path = find_image_rel(OUTPUT_ROOT, retailer, client, leaf_hint, basename_no_ext)
                        
                        if rel_path:
                            filename_for_url = rel_path
                        else:
                            # File not found on disk - still include the ad but with empty image_url
                            # This preserves the ad data even if screenshot failed
                            print(f"⚠️  Ad has missing image file: {filename}")
                            filename_for_url = None
                    
                    if filename_for_url:
                        image_api = f"/api/image/{retailer}/{client}/{filename_for_url}"
                        # Add ngrok bypass param so images load without interstitial (images can't set headers)
                        sep = "&" if "?" in image_api else "?"
                        image_api += f"{sep}ngrok-skip-browser-warning=true"
                    else:
                        image_api = ""  # Empty string indicates missing image
                
                # Extract advertisers - handle new array format and legacy fields
                advertisers = ad.get("advertisers")  # New array format
                if not advertisers:
                    # Fallback to legacy fields
                    legacy_brand = ad.get("brand") or ad.get("advertiser") or ad.get("title")
                    advertisers = [legacy_brand] if legacy_brand else []
                
                # Campaign slogan detection - words that indicate this is NOT a brand name
                campaign_keywords = {'halloween', 'christmas', 'holiday', 'summer', 'spring', 'fall', 'winter',
                                    'grab', 'get', 'buy', 'save', 'shop', 'now', 'better', 'best', 'new', 'fresh',
                                    'treats', 'deals', 'sale', 'special', 'limited', 'exclusive', 'discover',
                                    'shop now', 'buy now', 'save now', 'learn more', 'click here'}
                
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
                        advertisers = [adv.replace('_', ' ').title() for adv in parsed_advertisers if adv and adv != 'unknown']
                
                # Format brand string for display
                brand = ' + '.join(advertisers) if advertisers else "Unknown"
                
                # Extract message/headline
                message = ad.get("message") or ad.get("headline") or ad.get("description") or ""
                
                all_cards.append({
                    "retailer": retailer,
                    "client": client,
                    "keyword": data.get("keyword") or data.get("search_term"),
                    "ad_type": ad.get("type") or ad.get("ad_type"),
                    "brand": brand,
                    "advertisers": advertisers,  # NEW: array of advertisers for filtering
                    "message": message,
                    "image_url": image_api,
                    "run_file": fn,
                    "timestamp": data.get("timestamp") or data.get("ts"),
                    "featured": ad.get("featured", False),
                    "ad_index": idx  # Add index for unique identification
                })
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
    Serve ad image with leaf-agnostic fallback.
    
    Strategy:
    1. Try exact path as requested
    2. Fallback: search all allowed subfolders by basename
    3. Try extension variants (.jpg, .jpeg, .png)
    """
    retailer = retailer.lower()
    
    # Decode and normalize filename
    clean = unquote(filename).lstrip("/").replace("\\", "/")
    base = os.path.basename(clean)
    
    # Get allowed subdirs for this retailer
    try:
        leaves = allowed_subdirs(retailer)
    except ValueError:
        return jsonify({"error": f"unknown retailer: {retailer}"}), 404
    
    # 1) Try exact path as requested
    try:
        exact = _safe_join(OUTPUT_ROOT, retailer, client, clean)
        if os.path.isfile(exact):
            return _image_response(exact)
    except (ValueError, OSError):
        pass
    
    # 2) Fallback: search all allowed subfolders for basename
    for leaf in leaves:
        try:
            alt = _safe_join(OUTPUT_ROOT, retailer, client, leaf, base)
            if os.path.isfile(alt):
                return _image_response(alt)
        except (ValueError, OSError):
            continue
    
    # 3) Extension variants (jpg/jpeg/png) if needed
    name, _ext = os.path.splitext(base)
    for leaf in leaves:
        for ext2 in (".png", ".jpg", ".jpeg", ".webp"):
            try:
                alt2 = _safe_join(OUTPUT_ROOT, retailer, client, leaf, name + ext2)
                if os.path.isfile(alt2):
                    return _image_response(alt2)
            except (ValueError, OSError):
                continue
    
    # IMPORTANT: Keep this as a real 404 for API routes (don't let SPA catch-all override)
    return jsonify({"error": "image not found", "requested": clean}), 404

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
