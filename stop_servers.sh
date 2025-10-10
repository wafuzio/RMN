#!/bin/bash

# Retail Ad Monitor - Stop All Servers Script

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=============================================="
echo "Retail Ad Monitor - Stopping All Servers"
echo "=============================================="
echo ""

# Kill Flask API (port 5006)
echo -n "Stopping Flask API (port 5006)...  "
if lsof -ti:5006 > /dev/null 2>&1; then
    lsof -ti:5006 | xargs kill -9 2>/dev/null || true
    echo -e "${GREEN}✓ Stopped${NC}"
else
    echo -e "ℹ Not running"
fi

# Kill any builder_server_v2.py processes
if pgrep -f "builder_server_v2.py" > /dev/null 2>&1; then
    pkill -9 -f "builder_server_v2.py" 2>/dev/null || true
    echo -e "  ${GREEN}✓ Cleaned up Flask processes${NC}"
fi

# Kill ngrok
echo -n "Stopping ngrok...                   "
if pgrep -f "ngrok" > /dev/null 2>&1; then
    pkill -9 ngrok 2>/dev/null || true
    echo -e "${GREEN}✓ Stopped${NC}"
else
    echo -e "ℹ Not running"
fi

# Kill Vite (port 3000 and 3001)
echo -n "Stopping Vite (port 3000)...        "
if lsof -ti:3000 > /dev/null 2>&1; then
    lsof -ti:3000 | xargs kill -9 2>/dev/null || true
    echo -e "${GREEN}✓ Stopped${NC}"
else
    echo -e "ℹ Not running"
fi

if lsof -ti:3001 > /dev/null 2>&1; then
    lsof -ti:3001 | xargs kill -9 2>/dev/null || true
    echo -e "  ${GREEN}✓ Cleaned up port 3001${NC}"
fi

echo ""
echo -e "${GREEN}All servers stopped successfully!${NC}"
echo "=============================================="
