#!/bin/bash
# Start the Builder.io API server with proper environment

# Set environment variables
export SCRAPER_HOME="${SCRAPER_HOME:-$(cd "$(dirname "$0")/.." && pwd)}"
export ALLOWED_ORIGINS="${ALLOWED_ORIGINS:-https://builder.io,https://cdn.builder.io}"
export API_KEY="${API_KEY:-}"

echo "=========================================="
echo "Retail Ad Monitor API Server"
echo "=========================================="
echo "SCRAPER_HOME: $SCRAPER_HOME"
echo "ALLOWED_ORIGINS: $ALLOWED_ORIGINS"
echo "API_KEY: ${API_KEY:+SET}"
echo ""
echo "Starting server on http://localhost:5006"
echo "=========================================="
echo ""

cd "$SCRAPER_HOME"
python3 web/builder_server_v2.py
