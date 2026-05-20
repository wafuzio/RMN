#!/bin/bash
# Walmart Fresh Profile Setup - Manual Chrome Launch
# 
# Launches REAL Chrome (not Playwright) with a fresh profile for 
# completely organic browsing and login. No automation detection 
# possible because there IS no automation.
#
# Usage:
#   ./scripts/setup_walmart_fresh_profile_manual.sh [profile_name]

set -e

# Get profile name
PROFILE_NAME="${1:-walmart_fresh_$(date +%Y%m%d_%H%M%S)}"
PROFILE_DIR="$HOME/ChromeProfiles/$PROFILE_NAME"

echo "=" 
