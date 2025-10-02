#!/bin/bash
# Setup script for Instacart profile authentication

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PROFILE_DIR="${HOME}/Documents/Amazon_Scrape/profiles/instacart"

echo "=========================================="
echo "Instacart Profile Setup"
echo "=========================================="
echo ""
echo "This script will:"
echo "1. Create a persistent Chrome profile for Instacart"
echo "2. Open a browser for you to log in manually"
echo "3. Save the authenticated session for future scraping"
echo ""
echo "Profile will be saved to: $PROFILE_DIR"
echo ""
read -p "Press Enter to continue..."

# Create profile directory
mkdir -p "$PROFILE_DIR"

# Run the authentication helper
cd "$PROJECT_ROOT"
python3 auth/retailer_auth.py --retailer instacart --profile-dir "$PROFILE_DIR"

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Add to your shell profile (~/.zshrc or ~/.bash_profile):"
echo "   export INSTACART_PROFILE_DIR=\"$PROFILE_DIR\""
echo ""
echo "2. Optionally set default store (default is 'publix'):"
echo "   export INSTACART_STORE=\"publix\""
echo ""
echo "3. Reload your shell:"
echo "   source ~/.zshrc"
echo ""
echo "4. Test the scraper:"
echo "   python3 keyword_input.py"
echo "   (Select 'Instacart' from the retailer dropdown)"
echo ""
