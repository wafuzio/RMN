#!/bin/bash

# Kroger TOA Scraper - Scheduler Daemon Startup Script
# This script starts the scheduler daemon that monitors and executes
# scheduled scraping tasks for all configured clients.

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Activate virtual environment
source "$SCRIPT_DIR/.venv/bin/activate"

# Create logs directory if it doesn't exist
mkdir -p "$SCRIPT_DIR/logs"

echo "Starting Kroger TOA Scraper Scheduler Daemon..."
echo "Logs will be written to: $SCRIPT_DIR/logs/scheduler_daemon.log"
echo "Press Ctrl+C to stop the scheduler"
echo ""

# Run the scheduler daemon
cd "$SCRIPT_DIR"
python scheduler_daemon.py
