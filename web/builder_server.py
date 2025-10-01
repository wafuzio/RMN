"""
Simple Flask server for Builder.io integration

This server provides API endpoints for Builder.io to access ad data
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "libs"))

import sys
sys.path.insert(0, "libs")
from flask import Flask, jsonify, request, render_template, send_from_directory
import os
import json
import glob
from datetime import datetime
import re

app = Flask(__name__)

# Enable CORS for Builder.io
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

@app.route('/')
def index():
    """Render the main page"""
    return render_template('index.html')

@app.route('/nfl')
def nfl_dashboard():
    """Render the NFL-style dashboard"""
    return render_template('nfl_dashboard.html')

@app.route('/api/ads', methods=['GET'])
def get_ads():
    """Get all ads"""
    output_dir = "output"
    clients = []
    
    # Get all client directories
    for client_dir in os.listdir(output_dir):
        client_path = os.path.join(output_dir, client_dir)
        if os.path.isdir(client_path):
            clients.append(client_dir)
    
    return jsonify({
        "clients": clients
    })

@app.route('/api/ads/<client>', methods=['GET'])
def get_client_ads(client):
    """Get ads for a specific client"""
    output_dir = os.path.join("output", client)
    
    if not os.path.exists(output_dir):
        return jsonify({"error": "Client not found"}), 404
    
    # Find all toa_results files
    result_files = glob.glob(os.path.join(output_dir, "toa_results_*.json"))
    
    # Sort by date (newest first)
    result_files.sort(reverse=True)
    
    results = []
    for file_path in result_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # Extract date from filename
                filename = os.path.basename(file_path)
                date_str = filename.replace("toa_results_", "").replace(".json", "")
                
                results.append({
                    "date": date_str,
                    "data": data
                })
        except Exception as e:
            print(f"Error loading {file_path}: {e}")
    
    return jsonify({
        "client": client,
        "results": results
    })

@app.route('/api/nfl-grid/<client>', methods=['GET'])
def get_nfl_style_grid(client):
    """Get ads formatted in NFL-style grid layout"""
    output_dir = os.path.join("output", client)
    if not os.path.exists(output_dir):
        return jsonify({"error": "Client not found"}), 404

    term = (request.args.get('term') or '').strip()
    norm_term = term.lower()

    # Pagination
    try:
        page = int(request.args.get('page', 1))
    except Exception:
        page = 1
    try:
        page_size = int(request.args.get('page_size', 6))
    except Exception:
        page_size = 6

    # Find all result files (newest first)
    all_files = glob.glob(os.path.join(output_dir, "toa_results_*.json"))
    all_files.sort(reverse=True)
    start = max((page-1)*page_size, 0)
    end = start + page_size
    window = all_files[start:end]

    def resolve_image_url(ad):
        image_url = ad.get('image_url', '')
        if image_url and str(image_url).lower().startswith(('http://','https://','/api/')):
            return image_url
        fname = ''
        try:
            fname = os.path.basename(str(image_url)) if image_url else ''
        except Exception:
            fname = ''
        if (not fname) and ad.get('filename'):
            try:
                fname = os.path.basename(str(ad.get('filename')))
            except Exception:
                fname = ''
        if fname:
            toa_path = os.path.join('output', client, 'TOA', fname)
            main_path = os.path.join('output', client, 'main', fname)
            if os.path.exists(toa_path):
                return f"/api/toa/{client}/{fname}"
            if os.path.exists(main_path):
                return f"/api/images/{client}/{fname}"
        return ''

    grid_data = {
        "title": f"{client} TOA Monitoring",
        "schedule": []
    }

    for file_path in window:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Extract date from filename
            filename = os.path.basename(file_path)
            date_str = filename.replace("toa_results_", "").replace(".json", "")
            try:
                date_obj = datetime.strptime(date_str.split('_')[0], "%Y-%m-%d")
                display_date = date_obj.strftime("%b %d").upper()
            except Exception:
                display_date = date_str.split('_')[0]

            # Collect ads filtered by term (if provided)
            grid_ads = []
            display_week = None
            for result in (data.get('results') or []):
                kw = str(result.get('keyword', '')).strip()
                if norm_term and kw.lower() != norm_term:
                    continue
                display_week = display_week or kw or term or 'unknown'
                for ad in (result.get('ads') or []):
                    grid_ads.append({
                        'brand': ad.get('brand', 'Unknown'),
                        'image_url': resolve_image_url(ad),
                        'message': ad.get('message', ''),
                        'featured': ad.get('featured', False)
                    })

            # If no ads collected and a term was specified, skip this file
            if norm_term and not grid_ads:
                continue

            grid_data['schedule'].append({
                'date': display_date,
                'week': display_week or (term if term else 'unknown'),
                'ads': grid_ads
            })
        except Exception as e:
            print(f"Error loading {file_path}: {e}")

    # Fallback: scan TOA files for term if no JSON matches
    if norm_term and not grid_data['schedule']:
        slug = re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", norm_term.lower())).strip('_')
        toa_dir = os.path.join(output_dir, 'TOA')
        if os.path.isdir(toa_dir):
            files = [p for p in glob.glob(os.path.join(toa_dir, f'toa_{slug}_*')) if os.path.isfile(p)]
            # Group by date parsed from filename
            by_date = {}
            for p in files:
                m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(p))
                key = None
                if m:
                    try:
                        dt = datetime.strptime(m.group(1), "%Y-%m-%d")
                        key = dt.strftime('%b %d').upper()
                    except Exception:
                        key = m.group(1)
                else:
                    key = 'UNKNOWN'
                by_date.setdefault(key, []).append(os.path.basename(p))
            # Sort newest->oldest by month/day
            def keynum(s):
                parts = s.split()
                months = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
                if len(parts)>=2:
                    mi = months.get(parts[0].upper(),0); d = int(parts[1]) if parts[1].isdigit() else 0
                    return mi*100+d
                return -1
            for dlabel in sorted(by_date.keys(), key=keynum, reverse=True):
                names = by_date[dlabel]
                ads = [{ 'brand':'Unknown', 'image_url': f"/api/toa/{client}/{n}", 'message':'', 'featured': False } for n in names]
                grid_data['schedule'].append({ 'date': dlabel, 'week': term, 'ads': ads })

    grid_data['page'] = page
    grid_data['page_size'] = page_size
    grid_data['total_files'] = len(all_files)
    grid_data['has_more'] = end < len(all_files)
    return jsonify(grid_data)

@app.route('/api/terms/<client>', methods=['GET'])
def get_terms(client):
    """Return list of available search terms (keywords) for a client."""
    terms = set()
    # Try client_history.json for curated terms
    hist_path = os.path.join('output', 'client_history.json')
    try:
        if os.path.exists(hist_path):
            with open(hist_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                t = data.get(client) or data.get(client.replace(' ','_'))
                if isinstance(t, dict):
                    t = t.get('terms')
                if isinstance(t, list):
                    for s in t:
                        if isinstance(s, str) and s.strip():
                            terms.add(s.strip())
    except Exception as e:
        print('failed reading client_history.json', e)

    # Parse keywords from JSON results files
    output_dir = os.path.join('output', client)
    if os.path.isdir(output_dir):
        for file_path in glob.glob(os.path.join(output_dir, 'toa_results_*.json')):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for r in (data.get('results') or []):
                        kw = str(r.get('keyword','')).strip()
                        if kw:
                            terms.add(kw)
            except Exception as e:
                print('error reading', file_path, e)

    # Parse from TOA filenames: toa_<slug>_YYYY-MM-DD_*.png
    toa_dir = os.path.join('output', client, 'TOA')
    if os.path.isdir(toa_dir):
        for fn in os.listdir(toa_dir):
            m = re.match(r"^toa_([^_]+(?:_[^_]+)*)_\d{4}-\d{2}-\d{2}", fn)
            if m:
                slug = m.group(1)
                terms.add(slug.replace('_',' '))

    return jsonify({ 'client': client, 'terms': sorted(terms) })

@app.route('/api/images/<path:image_path>')
def get_image(image_path):
    """Serve full page images from main subfolder"""
    # First try client-specific directories
    parts = image_path.split('/')
    if len(parts) > 1:
        client = parts[0]
        filename = parts[-1]
        client_path = os.path.join('output', client, 'main')
        if os.path.exists(os.path.join(client_path, filename)):
            return send_from_directory(client_path, filename)
    
    # Fall back to default images directory
    return send_from_directory('images/main', image_path)

@app.route('/api/toa/<path:image_path>')
def get_toa(image_path):
    """Serve TOA-only images from TOA subfolder"""
    # First try client-specific directories
    parts = image_path.split('/')
    if len(parts) > 1:
        client = parts[0]
        filename = parts[-1]
        client_path = os.path.join('output', client, 'TOA')
        if os.path.exists(os.path.join(client_path, filename)):
            return send_from_directory(client_path, filename)
    
    # Fall back to default TOA directory
    return send_from_directory('images/TOA', image_path)

if __name__ == '__main__':
    
    # Create templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    
    # Create a simple index.html if it doesn't exist
    index_path = os.path.join('templates', 'index.html')
    if not os.path.exists(index_path):
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write("""
<!DOCTYPE html>
<html>
<head>
    <title>Kroger Ad Monitor</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
        h1 { color: #333; }
    </style>
</head>
<body>
    <h1>Kroger Ad Monitor API</h1>
    <p>This server provides API endpoints for Builder.io to access ad data.</p>
    <h2>Available Endpoints:</h2>
    <ul>
        <li><code>/api/ads</code> - List all clients</li>
        <li><code>/api/ads/&lt;client&gt;</code> - Get ads for a specific client</li>
        <li><code>/api/images/&lt;path&gt;</code> - Access ad images</li>
    </ul>
</body>
</html>
            """)
    
    # Run the Flask app
    app.run(host='0.0.0.0', port=5006, debug=True)
