"""
Simple Flask server for Builder.io integration

This server provides API endpoints for Builder.io to access ad data
"""

from flask import Flask, jsonify, request, render_template
import os
import json
import glob
from datetime import datetime

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
    
    # Find all toa_results files
    result_files = glob.glob(os.path.join(output_dir, "toa_results_*.json"))
    
    # Sort by date (newest first)
    result_files.sort(reverse=True)
    
    # Limit to most recent 10 files for grid display
    result_files = result_files[:10]
    
    grid_data = {
        "title": f"{client} TOA Monitoring",
        "schedule": []
    }
    
    for file_path in result_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # Extract date from filename
                filename = os.path.basename(file_path)
                date_str = filename.replace("toa_results_", "").replace(".json", "")
                
                # Format date for display (e.g., SEP 12)
                try:
                    date_obj = datetime.strptime(date_str.split('_')[0], "%Y-%m-%d")
                    display_date = date_obj.strftime("%b %d").upper()
                except:
                    display_date = date_str.split('_')[0]
                
                # Get keyword from data if available
                keyword = "unknown"
                if data.get("results") and len(data["results"]) > 0:
                    keyword = data["results"][0].get("keyword", "unknown")
                
                # Format ads for grid display
                grid_ads = []
                if data.get("results"):
                    for result in data["results"]:
                        if result.get("ads"):
                            for ad in result["ads"]:
                                # Create NFL-style ad entry
                                grid_ad = {
                                    "brand": ad.get("brand", "Unknown"),
                                    "image_url": ad.get("image_url", ""),
                                    "message": ad.get("message", ""),
                                    "featured": ad.get("featured", False)
                                }
                                grid_ads.append(grid_ad)
                
                # Add to schedule
                grid_data["schedule"].append({
                    "date": display_date,
                    "week": keyword,  # Using keyword as "week" in NFL style
                    "ads": grid_ads
                })
        except Exception as e:
            print(f"Error loading {file_path}: {e}")
    
    return jsonify(grid_data)

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
    # Add missing import
    from flask import send_from_directory
    
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
