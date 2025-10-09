#!/bin/bash
# Setup a clean Walmart profile (no Bot Manager cookies)

set -e

PROFILE_NAME="${1:-walmart_clean}"
PROFILE_DIR="$HOME/ChromeProfiles/$PROFILE_NAME"

echo "🧹 Setting up clean Walmart profile: $PROFILE_NAME"
echo ""

# Create profile directory
mkdir -p "$PROFILE_DIR"
echo "✅ Created profile directory: $PROFILE_DIR"

# Check if Chrome is installed
if [ ! -d "/Applications/Google Chrome.app" ]; then
    echo "❌ Google Chrome not found"
    echo "Install with: brew install --cask google-chrome"
    exit 1
fi

echo "✅ Google Chrome found"
echo ""

# Kill any existing Chrome with this profile
pkill -f "Google Chrome.*$PROFILE_DIR" 2>/dev/null && echo "✅ Closed existing Chrome" || echo "ℹ️  No Chrome running with this profile"
sleep 2

echo ""
echo "📝 Manual aging instructions:"
echo ""
echo "1. Run this command to open Chrome with the clean profile:"
echo "   open -na \"Google Chrome\" --args --disable-extensions --user-data-dir=\"$PROFILE_DIR\""
echo ""
echo "2. In Chrome:"
echo "   - Go to https://www.walmart.com"
echo "   - Accept cookies if prompted"
echo "   - Type a normal query (e.g., 'milk')"
echo "   - Scroll a bit, click a result"
echo "   - Spend 2-3 minutes browsing normally"
echo ""
echo "3. Quit Chrome (Cmd+Q)"
echo ""
echo "4. Set environment variable for your scraper:"
echo "   export WALMART_PROFILE_DIR=\"$PROFILE_DIR\""
echo ""
echo "5. Run your scraper"
echo ""

# Offer to open Chrome now
read -p "Open Chrome now for manual aging? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🚀 Opening Chrome with clean profile..."
    open -na "Google Chrome" --args --disable-extensions --user-data-dir="$PROFILE_DIR"
    echo ""
    echo "✅ Chrome opened. Follow the manual aging steps above."
    echo "   When done, quit Chrome and run your scraper with:"
    echo "   export WALMART_PROFILE_DIR=\"$PROFILE_DIR\""
else
    echo ""
    echo "ℹ️  Skipped. Run the command above when ready."
fi

echo ""
echo "Profile location: $PROFILE_DIR"
