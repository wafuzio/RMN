#!/bin/bash

# Quick morning startup - checks what's running and starts what's needed
# Use this after waking your laptop if services aren't running

set -e

echo "=============================================="
echo "Retail Monitor - Morning Startup Check"
echo "=============================================="
echo ""

SCRAPER_DIR="/Users/dan.maguire/Documents/Amazon_Scrape"
VITE_DIR="$SCRAPER_DIR/neon-sanctuary"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Check each service
echo "Checking service status..."
echo ""

# Flask
if lsof -ti:5006 > /dev/null 2>&1; then
    echo -e "  ${GREEN}✓ Flask API running${NC}"
    FLASK_RUNNING=true
else
    echo -e "  ${RED}✗ Flask API stopped${NC}"
    FLASK_RUNNING=false
fi

# ngrok
if lsof -ti:4040 > /dev/null 2>&1; then
    echo -e "  ${GREEN}✓ ngrok running${NC}"
    NGROK_RUNNING=true
else
    echo -e "  ${RED}✗ ngrok stopped${NC}"
    NGROK_RUNNING=false
fi

# Vite
if lsof -ti:3000 > /dev/null 2>&1; then
    echo -e "  ${GREEN}✓ Vite running${NC}"
    VITE_RUNNING=true
else
    echo -e "  ${RED}✗ Vite stopped${NC}"
    VITE_RUNNING=false
fi

# Supabase
if docker ps | grep -q supabase_db_Amazon_Scrape; then
    echo -e "  ${GREEN}✓ Supabase running${NC}"
    SUPABASE_RUNNING=true
else
    echo -e "  ${RED}✗ Supabase stopped${NC}"
    SUPABASE_RUNNING=false
fi

echo ""

# If everything is running, we're done
if [ "$FLASK_RUNNING" = true ] && [ "$NGROK_RUNNING" = true ] && [ "$VITE_RUNNING" = true ]; then
    echo -e "${GREEN}All services are running!${NC}"
    echo ""
    echo "🌐 Dashboard: http://localhost:3000"
    exit 0
fi

# Otherwise, start what's needed
echo -e "${YELLOW}Starting stopped services...${NC}"
echo ""

if [ "$SUPABASE_RUNNING" = false ]; then
    echo "Starting Supabase..."
    cd "$SCRAPER_DIR"
    supabase start
    sleep 3
fi

if [ "$FLASK_RUNNING" = false ]; then
    echo "Starting Flask API..."
    cd "$SCRAPER_DIR"
    nohup "$SCRAPER_DIR/.venv/bin/python3" web/builder_server_v2.py > logs/flask.log 2>&1 &
    sleep 2
fi

if [ "$NGROK_RUNNING" = false ]; then
    echo "Starting ngrok..."
    nohup ngrok http 5006 > logs/ngrok.log 2>&1 &
    sleep 3
fi

if [ "$VITE_RUNNING" = false ]; then
    echo "Starting Vite..."
    cd "$VITE_DIR"
    nohup npm run dev > ../logs/vite.log 2>&1 &
    sleep 3
fi

echo ""
echo -e "${GREEN}All services started!${NC}"
echo ""
echo "🌐 Dashboard: http://localhost:3000"
echo ""
