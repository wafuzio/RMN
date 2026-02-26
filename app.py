import sys
import os

# Add project root to path so we can import web module
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from web.builder_server_v2 import app

if __name__ == "__main__":
    print(f"Starting Flask server on http://0.0.0.0:5006")
    print(f"API endpoints available at http://localhost:5006/api/*")
    app.run(host="0.0.0.0", port=5006, debug=True)
