#!/bin/bash
# Setup script for Target persistent Playwright/Chrome profile

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE_DIR="$PROJECT_ROOT/profiles/target"

mkdir -p "$PROFILE_DIR"

echo "Using Target profile directory: $PROFILE_DIR"

"${PROJECT_ROOT}/.venv/bin/python" "$PROJECT_ROOT/auth/retailer_auth.py" \
  --retailer target \
  --profile-dir "$PROFILE_DIR"

echo ""
echo "Add this to your shell profile (e.g. ~/.zshrc):"
echo "  export TARGET_PROFILE_DIR=$PROFILE_DIR"
echo ""
echo "And ensure config/launcher.env has:" 
echo "  TARGET_PROFILE_DIR=$PROFILE_DIR" 
