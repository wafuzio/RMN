#!/bin/bash

# Retail Ad Monitor - Quick Server Restart Script
# Safely kills and restarts Flask API, ngrok, and Vite dev server
# Skips catalog/index/logo rebuild steps for faster restarts

set -e  # Exit on error

echo "=============================================="
echo "Retail Ad Monitor - Quick Restart"
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

# --- Kill by process name first (catches detached/orphaned processes) ---
echo "  - Killing stale processes by name..."
if pgrep -f "builder_server_v2.py" > /dev/null 2>&1; then
    pkill -9 -f "builder_server_v2.py" 2>/dev/null || true
    echo -e "    ${GREEN}✓ Killed builder_server_v2.py${NC}"
fi
if pgrep -f "ngrok" > /dev/null 2>&1; then
    pkill -9 ngrok 2>/dev/null || true
    echo -e "    ${GREEN}✓ Killed ngrok${NC}"
fi

# --- Kill anything on our ports (catches processes we didn't start) ---
for PORT in 5006 3000 3001 4040; do
    if lsof -ti:$PORT > /dev/null 2>&1; then
        echo "  - Killing processes on port $PORT..."
        lsof -ti:$PORT | xargs kill -9 2>/dev/null || true
        echo -e "    ${GREEN}✓ Port $PORT cleared${NC}"
    fi
done

# --- Wait for ports to be fully released (retry up to 5s) ---
echo "  - Waiting for ports to be released..."
for i in 1 2 3 4 5; do
    ALL_FREE=true
    for PORT in 5006 3000; do
        if lsof -ti:$PORT > /dev/null 2>&1; then
            ALL_FREE=false
            break
        fi
    done
    if $ALL_FREE; then break; fi
    sleep 1
done

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

# Use .venv Python for all tool scripts
PYTHON="$SCRAPER_DIR/.venv/bin/python3"
if [ ! -x "$PYTHON" ]; then
    echo -e "${YELLOW}⚠️  .venv not found, falling back to system python3${NC}"
    PYTHON=python3
fi

# ============================================
# Step 3: Start servers
# ============================================

echo ""
echo -e "${YELLOW}[3/3] Starting servers...${NC}"

# Start Flask API
echo "  - Starting Flask API..."
cd "$SCRAPER_DIR"
nohup "$PYTHON" web/builder_server_v2.py > logs/flask.log 2>&1 &
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
nohup ngrok http 5006 > logs/ngrok.log 2>&1 &
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

# ============================================
# Summary
# ============================================

echo ""
echo "=============================================="
echo -e "${GREEN}Quick restart complete!${NC}"
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
