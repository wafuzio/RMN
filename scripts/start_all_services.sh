#!/bin/bash

# Auto-start script for LaunchAgent
# This runs on login and ensures all services are running

SCRAPER_DIR="/Users/dan.maguire/Documents/Amazon_Scrape"
VITE_DIR="$SCRAPER_DIR/neon-sanctuary"
LOG_DIR="$SCRAPER_DIR/logs"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Wait for network (important after sleep/wake)
sleep 5

# Check if Flask is already running
if ! lsof -ti:5006 > /dev/null 2>&1; then
    echo "$(date): Starting Flask..." >> "$LOG_DIR/autostart.log"
    cd "$SCRAPER_DIR"
    nohup "$SCRAPER_DIR/.venv/bin/python3" web/builder_server_v2.py > "$LOG_DIR/flask.log" 2>&1 &
    sleep 2
fi

# Check if ngrok is already running
if ! lsof -ti:4040 > /dev/null 2>&1; then
    echo "$(date): Starting ngrok..." >> "$LOG_DIR/autostart.log"
    nohup ngrok http 5006 > "$LOG_DIR/ngrok.log" 2>&1 &
    sleep 3
fi

# Check if Vite is already running
if ! lsof -ti:3000 > /dev/null 2>&1; then
    echo "$(date): Starting Vite..." >> "$LOG_DIR/autostart.log"
    cd "$VITE_DIR"
    nohup npm run dev > "$LOG_DIR/vite.log" 2>&1 &
fi

echo "$(date): All services started" >> "$LOG_DIR/autostart.log"
