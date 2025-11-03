#!/bin/bash

# Retail Ad Monitor - Server Restart Script
# Safely kills and restarts Flask API, ngrok, and Vite dev server

set -e  # Exit on error

echo "=============================================="
echo "Retail Ad Monitor - Restarting All Servers"
echo "=============================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Project directories
SCRAPER_DIR="/Users/dan.maguire/Documents/Amazon_Scrape"
VITE_DIR="$SCRAPER_DIR/neon-sanctuary"

# ============================================
# Step 1: Kill existing servers
# ============================================

echo -e "${YELLOW}[1/3] Stopping existing servers...${NC}"

# Kill Flask API (port 5006)
echo "  - Stopping Flask API (port 5006)..."
if lsof -ti:5006 > /dev/null 2>&1; then
    lsof -ti:5006 | xargs kill -9 2>/dev/null || true
    echo -e "    ${GREEN}✓ Flask stopped${NC}"
else
    echo "    ℹ Flask not running"
fi

# Kill any builder_server_v2.py processes (in case they're hung)
if pgrep -f "builder_server_v2.py" > /dev/null 2>&1; then
    pkill -9 -f "builder_server_v2.py" 2>/dev/null || true
    echo -e "    ${GREEN}✓ Cleaned up Flask processes${NC}"
fi

# Kill ngrok (port 4040 is ngrok's web interface)
echo "  - Stopping ngrok..."
if pgrep -f "ngrok" > /dev/null 2>&1; then
    pkill -9 ngrok 2>/dev/null || true
    echo -e "    ${GREEN}✓ ngrok stopped${NC}"
else
    echo "    ℹ ngrok not running"
fi

# Kill Vite (port 3000)
echo "  - Stopping Vite dev server (port 3000)..."
if lsof -ti:3000 > /dev/null 2>&1; then
    lsof -ti:3000 | xargs kill -9 2>/dev/null || true
    echo -e "    ${GREEN}✓ Vite stopped${NC}"
else
    echo "    ℹ Vite not running"
fi

# Also kill port 3001 in case Vite moved there
if lsof -ti:3001 > /dev/null 2>&1; then
    lsof -ti:3001 | xargs kill -9 2>/dev/null || true
    echo -e "    ${GREEN}✓ Cleaned up port 3001${NC}"
fi

# Wait for ports to be fully released
echo "  - Waiting for ports to be released..."
sleep 2

# ============================================
# Step 2: Verify ports are free
# ============================================

echo ""
echo -e "${YELLOW}[2/3] Verifying ports are available...${NC}"

# Check if ports are free
PORTS_OK=true

if lsof -ti:5006 > /dev/null 2>&1; then
    echo -e "  ${RED}✗ Port 5006 still in use!${NC}"
    PORTS_OK=false
else
    echo -e "  ${GREEN}✓ Port 5006 available${NC}"
fi

if lsof -ti:3000 > /dev/null 2>&1; then
    echo -e "  ${RED}✗ Port 3000 still in use!${NC}"
    PORTS_OK=false
else
    echo -e "  ${GREEN}✓ Port 3000 available${NC}"
fi

if [ "$PORTS_OK" = false ]; then
    echo -e "${RED}Error: Ports still in use. Please manually kill processes and try again.${NC}"
    exit 1
fi

# ============================================
# Step 3: Start servers
# ============================================

echo ""
echo -e "${YELLOW}[3/3] Starting servers...${NC}"

# Start Flask API
echo "  - Starting Flask API..."
cd "$SCRAPER_DIR"
nohup python3 web/builder_server_v2.py > logs/flask.log 2>&1 &
FLASK_PID=$!
sleep 2

# Verify Flask started
if ps -p $FLASK_PID > /dev/null; then
    echo -e "    ${GREEN}✓ Flask started (PID: $FLASK_PID)${NC}"
else
    echo -e "    ${RED}✗ Flask failed to start. Check logs/flask.log${NC}"
    exit 1
fi

# Start ngrok
echo "  - Starting ngrok tunnel..."
nohup ngrok http 127.0.0.1:5006 > logs/ngrok.log 2>&1 &
NGROK_PID=$!
sleep 3

# Verify ngrok started
if ps -p $NGROK_PID > /dev/null; then
    echo -e "    ${GREEN}✓ ngrok started (PID: $NGROK_PID)${NC}"
    # Get ngrok URL
    NGROK_URL=$(curl -s http://localhost:4040/api/tunnels | grep -o 'https://[^"]*ngrok[^"]*' | head -1)
    if [ -n "$NGROK_URL" ]; then
        echo -e "    ${GREEN}  URL: $NGROK_URL${NC}"
    fi
else
    echo -e "    ${RED}✗ ngrok failed to start. Check logs/ngrok.log${NC}"
    exit 1
fi

# Start Vite
echo "  - Starting Vite dev server..."
cd "$VITE_DIR"
nohup npm run dev > ../logs/vite.log 2>&1 &
VITE_PID=$!
sleep 3

# Verify Vite started
if ps -p $VITE_PID > /dev/null; then
    echo -e "    ${GREEN}✓ Vite started (PID: $VITE_PID)${NC}"
else
    echo -e "    ${RED}✗ Vite failed to start. Check logs/vite.log${NC}"
    exit 1
fi

# Start Builder.io dev tools (if .env has BUILDER_PRIVATE_KEY)
echo "  - Starting Builder.io dev tools..."
cd "$VITE_DIR"
if [ -f .env ] && grep -q "BUILDER_PRIVATE_KEY" .env; then
    # Load the private key from .env
    export $(grep "BUILDER_PRIVATE_KEY" .env | xargs)
    nohup npx @builder.io/dev-tools launch --serverUrl http://localhost:3000 --no-open --local > ../logs/builder-devtools.log 2>&1 &
    BUILDER_PID=$!
    sleep 3
    
    # Verify Builder dev tools started
    if ps -p $BUILDER_PID > /dev/null; then
        # Get the port from the log
        BUILDER_PORT=$(grep -o "http://localhost:[0-9]*" ../logs/builder-devtools.log 2>/dev/null | grep -o "[0-9]*$" | head -1)
        if [ -n "$BUILDER_PORT" ]; then
            echo -e "    ${GREEN}✓ Builder.io dev tools started (PID: $BUILDER_PID, Port: $BUILDER_PORT)${NC}"
        else
            echo -e "    ${GREEN}✓ Builder.io dev tools started (PID: $BUILDER_PID)${NC}"
        fi
    else
        echo -e "    ${YELLOW}⚠ Builder.io dev tools failed to start (optional)${NC}"
    fi
else
    echo -e "    ${YELLOW}ℹ Skipping Builder.io dev tools (no BUILDER_PRIVATE_KEY in .env)${NC}"
fi
cd "$SCRAPER_DIR"

# ============================================
# Summary
# ============================================

echo ""
echo "=============================================="
echo -e "${GREEN}All servers started successfully!${NC}"
echo "=============================================="
echo ""
echo "📊 Server Status:"
echo "  • Flask API:     http://localhost:5006 (PID: $FLASK_PID)"
echo "  • ngrok:         $NGROK_URL (PID: $NGROK_PID)"
echo "  • Vite:          http://localhost:3000 (PID: $VITE_PID)"
echo ""
echo "📝 Logs:"
echo "  • Flask:  $SCRAPER_DIR/logs/flask.log"
echo "  • ngrok:  $SCRAPER_DIR/logs/ngrok.log"
echo "  • Vite:   $SCRAPER_DIR/logs/vite.log"
echo ""
echo "🌐 Open your dashboard:"
echo "  http://localhost:3000"
echo ""
echo "=============================================="
