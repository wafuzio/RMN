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

from flask import Flask, jsonify, request, send_from_directory
from pathlib import Path
import json
import glob
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

@app.after_request
def after_request(resp):
    """Handle CORS with environment-driven allowlist"""
    origin = request.headers.get("Origin", "")
    
    # Development: allow localhost
    if not ALLOWED_ORIGINS or origin.startswith("http://localhost") or origin.startswith("http://127.0.0.1"):
        resp.headers["Access-Control-Allow-Origin"] = origin or "*"
    elif origin in ALLOWED_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
    else:
        # Allow Builder.io and ngrok domains
        resp.headers["Access-Control-Allow-Origin"] = "*"
    
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization,ngrok-skip-browser-warning"
    resp.headers["Access-Control-Allow-Methods"] = "GET,PUT,POST,DELETE,OPTIONS"
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
            "GET /api/ads/cards?retailer=<retailer>&client=<client>&term=<term>&page=1&page_size=24": "Get ad cards",
            "GET /api/image/<retailer>/<client>/<filename>": "Serve ad image"
        },
        "environment": {
            "SCRAPER_HOME": SCRAPER_HOME,
            "OUTPUT_ROOT": OUTPUT_ROOT,
            "ALLOWED_ORIGINS": list(ALLOWED_ORIGINS) if ALLOWED_ORIGINS else ["*"],
            "API_KEY_SET": bool(API_KEY)
        }
    })

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

@app.route("/api/ads/cards", methods=["GET"])
def api_ads_cards():
    """
    Get ad cards with filtering and pagination
    
    Query params:
    - retailer (required): retailer slug
    - client (required): client name
    - term (optional): filter by search term
    - page (optional): page number (default 1)
    - page_size (optional): items per page (default 24, max 100)
    """
    retailer = (request.args.get("retailer") or "").strip().lower()
    client = (request.args.get("client") or "").strip()
    term = (request.args.get("term") or "").strip().lower()
    
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
            
            # Get image_paths mapping if available (from migration)
            image_paths_map = data.get("image_paths", {})
            
            # Convert each ad to a card
            for idx, ad in enumerate(ads):
                # Determine image filename - prioritize local saved paths over remote URLs
                filename = ""
                
                # Try various path fields first (these point to actual saved files)
                for path_field in ["skyscraper_image_path", "carousel_image_path", "main_image_path", 
                                   "image_path", "screenshot_path", "filename"]:
                    if ad.get(path_field):
                        filename = os.path.basename(str(ad.get(path_field)))
                        break
                
                # Fallback to extracting from image_url if no path field found
                if not filename and ad.get("image_url"):
                    filename = os.path.basename(str(ad.get("image_url")))
                
                # For Walmart: try to match ad type to image_paths mapping
                if not filename and image_paths_map and retailer == "walmart":
                    ad_type = ad.get("type", "").lower()
                    keyword = data.get("keyword", data.get("search_term", "")).replace(" ", "_")
                    
                    # Try to find matching image in map
                    for old_name, new_path in image_paths_map.items():
                        if ad_type in old_name.lower() and keyword.split("_")[0] in old_name.lower():
                            filename = new_path
                            break
                
                # Build API image URL
                image_api = f"/api/image/{retailer}/{client}/{filename}" if filename else ""
                
                # Extract brand - handle different JSON structures
                brand = ad.get("brand") or ad.get("title") or "Unknown"
                
                # Extract message/headline
                message = ad.get("message") or ad.get("headline") or ad.get("description") or ""
                
                all_cards.append({
                    "retailer": retailer,
                    "client": client,
                    "keyword": data.get("keyword") or data.get("search_term"),
                    "ad_type": ad.get("type") or ad.get("ad_type"),
                    "brand": brand,
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
        "total_cards": len(all_cards)
    })

@app.route("/api/image/<retailer>/<client>/<path:filename>", methods=["GET"])
def api_image(retailer, client, filename):
    """
    Serve ad image by trying all allowed subdirectories for the retailer
    
    This abstracts the folder differences (TOA vs Sponsored_Product vs Main)
    Filename can include subdirectory path (e.g., "SBA/image.png")
    """
    retailer = retailer.lower()
    
    # Try all allowed subdirs for this retailer
    try:
        leaves = allowed_subdirs(retailer)
    except ValueError:
        return jsonify({"error": f"unknown retailer: {retailer}"}), 404
    
    # If filename includes a path, try that first
    if "/" in filename:
        p = os.path.join(OUTPUT_ROOT, retailer, client, filename)
        if os.path.exists(p):
            return send_from_directory(os.path.dirname(p), os.path.basename(p))
    
    # Priority order: specific ad types first, then Main, then runs
    priority_order = [
        leaf for leaf in leaves
        if leaf not in ["Main", "runs"]
    ] + ["Main"]
    
    # Try exact filename match in each directory
    for leaf in priority_order:
        p = os.path.join(OUTPUT_ROOT, retailer, client, leaf, filename)
        if os.path.exists(p):
            return send_from_directory(os.path.dirname(p), os.path.basename(p))
    
    # If exact match fails, try fuzzy matching by ad type and keyword
    # Extract ad type from directory name in filename or from filename itself
    filename_lower = filename.lower()
    for leaf in priority_order:
        dir_path = os.path.join(OUTPUT_ROOT, retailer, client, leaf)
        if not os.path.isdir(dir_path):
            continue
        
        # List all files in this directory
        try:
            files = os.listdir(dir_path)
            # Try to find a file that matches the ad type pattern
            ad_type_prefix = leaf.lower().replace("_", "")
            for f in files:
                f_lower = f.lower()
                # Match if file starts with ad type and has similar naming pattern
                if f_lower.startswith(ad_type_prefix) or ad_type_prefix in f_lower:
                    # Return the first match (could be improved with better matching)
                    return send_from_directory(dir_path, f)
        except Exception:
            continue
    
    return jsonify({"error": "image not found"}), 404

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
            return send_from_directory(
                os.path.join(ASSETS_ROOT, "logos"),
                filename
            )
    
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
            return send_from_directory(
                os.path.join(ASSETS_ROOT, "logos"),
                pattern
            )
    
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

@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "retailers_available": len(list_retailers())
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
    
    app.run(host='0.0.0.0', port=5006, debug=True)
