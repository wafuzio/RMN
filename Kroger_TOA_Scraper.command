#!/bin/bash
# Kroger TOA Scraper Launcher
# This script launches the Kroger TOA Scraper GUI

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Change to the script directory
cd "$SCRIPT_DIR"

# Launch the Python GUI application
python3 keyword_input.py

# Keep terminal open if there's an error
if [ $? -ne 0 ]; then
    echo "Press any key to close..."
    read -n 1
fi
