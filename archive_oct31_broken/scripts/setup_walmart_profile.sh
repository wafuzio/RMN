#!/bin/bash
set -euo pipefail

PROFILE_DIR=${WALMART_PROFILE_DIR:-"$HOME/Documents/Amazon_Scrape/profiles/walmart"}
mkdir -p "$PROFILE_DIR"

echo "=========================================="
echo "Walmart Profile Setup"
echo "=========================================="
echo "Profile dir: $PROFILE_DIR"
echo ""
echo "IMPORTANT: Walmart uses PerimeterX bot protection"
echo "You MUST manually solve the CAPTCHA once to establish trust"
echo ""
echo "Steps:"
echo "1. Browser will open to walmart.com"
echo "2. If you see 'Robot or human?' - solve the CAPTCHA"
echo "3. Browse a few pages naturally (search, click products)"
echo "4. Close the browser when done"
echo "5. The session will be saved for future runs"
echo ""
read -p "Press Enter to continue..."

python3 auth/retailer_auth.py --retailer walmart --profile-dir "$PROFILE_DIR" || true

echo
echo "=========================================="
echo "Next Steps:"
echo "=========================================="
echo "1. Add to your shell profile (~/.zshrc or ~/.bash_profile):"
echo "   export WALMART_PROFILE_DIR=\"$PROFILE_DIR\""
echo ""
echo "2. Reload your shell:"
echo "   source ~/.zshrc"
echo ""
echo "3. Test the scraper:"
echo "   python3 keyword_input.py"
echo "=========================================="
