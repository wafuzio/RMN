"""
Unified Flask server for Builder.io integration and scraping control
"""

from flask import Flask, jsonify, request, render_template, send_from_directory
import os
import json
import glob
from datetime import datetime
from collections import Counter
import re

# Optional: keep NLTK detection if you still use it
try:
    import nltk
    from nltk.tokenize import word_tokenize
    from nltk.corpus import stopwords
    NLTK_AVAILABLE = True
except Exception:
    NLTK_AVAILABLE = False

app = Flask(__name__)

# ---- CORS headers so Builder can talk to it ----
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# ---- Example API route ----
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})

# TODO: bring over your scrape, client, schedule, conflict endpoints from the remote version here

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5006, debug=True)