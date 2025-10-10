#!/bin/bash

# Retail Ad Monitor - Server Status Check Script

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=============================================="
echo "Retail Ad Monitor - Server Status"
echo "=============================================="
echo ""

# Check Flask API (port 5006)
echo -n "Flask API (port 5006):     "
if lsof -ti:5006 > /dev/null 2>&1; then
    PID=$(lsof -ti:5006 | head -1)
    echo -e "${GREEN}✓ Running (PID: $PID)${NC}"
else
    echo -e "${RED}✗ Not running${NC}"
fi

# Check ngrok
echo -n "ngrok:                     "
if pgrep -f "ngrok" > /dev/null 2>&1; then
    PID=$(pgrep -f "ngrok" | head -1)
    NGROK_URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null | grep -o 'https://[^"]*ngrok[^"]*' | head -1)
    if [ -n "$NGROK_URL" ]; then
        echo -e "${GREEN}✓ Running (PID: $PID)${NC}"
        echo "                           URL: $NGROK_URL"
    else
        echo -e "${YELLOW}⚠ Running but URL not available yet${NC}"
    fi
else
    echo -e "${RED}✗ Not running${NC}"
fi

# Check Vite (port 3000)
echo -n "Vite (port 3000):          "
if lsof -ti:3000 > /dev/null 2>&1; then
    PID=$(lsof -ti:3000 | head -1)
    echo -e "${GREEN}✓ Running (PID: $PID)${NC}"
else
    # Check if it's on 3001 instead
    if lsof -ti:3001 > /dev/null 2>&1; then
        PID=$(lsof -ti:3001 | head -1)
        echo -e "${YELLOW}⚠ Running on port 3001 (PID: $PID)${NC}"
    else
        echo -e "${RED}✗ Not running${NC}"
    fi
fi

echo ""
echo "=============================================="
