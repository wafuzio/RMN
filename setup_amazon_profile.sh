#!/bin/bash
# Setup script for Amazon profile

# Create profiles directory if it doesn't exist
mkdir -p ~/Documents/Amazon_Scrape/profiles/amazon

# Run the auth helper
python3 auth/retailer_auth.py --retailer amazon --profile-dir ~/Documents/Amazon_Scrape/profiles/amazon

# Set environment variable
export AMZ_PROFILE_DIR=~/Documents/Amazon_Scrape/profiles/amazon
echo "✅ Environment variable AMZ_PROFILE_DIR set to: $AMZ_PROFILE_DIR"
echo "To make this permanent, add the following line to your ~/.zshrc or ~/.bash_profile:"
echo "export AMZ_PROFILE_DIR=~/Documents/Amazon_Scrape/profiles/amazon"
