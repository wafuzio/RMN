#!/bin/bash
# Simple script to run the Kroger TOA Scraper with python3

# Change to the script directory
cd "$(dirname "$0")"

# Run the keyword input tool with python3
python3 keyword_input.py

# Exit with the same status as the Python script
exit $?
