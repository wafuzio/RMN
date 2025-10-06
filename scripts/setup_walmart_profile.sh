#!/bin/bash
set -euo pipefail

PROFILE_DIR=${WALMART_PROFILE_DIR:-"$HOME/Documents/Amazon_Scrape/profiles/walmart"}
mkdir -p "$PROFILE_DIR"

echo "Profile dir: $PROFILE_DIR"
python3 auth/retailer_auth.py --retailer walmart --profile-dir "$PROFILE_DIR" || true

echo
echo "Add to your shell profile (~/.zshrc or ~/.bash_profile):"
echo "export WALMART_PROFILE_DIR=\"$PROFILE_DIR\""
