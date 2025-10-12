#!/bin/bash
# Setup authenticated Amazon profile for the scraper

PROFILE_DIR=~/Documents/Amazon_Scrape/profiles/amazon

echo "=========================================="
echo "Amazon Profile Setup"
echo "=========================================="
echo ""
echo "This will:"
echo "1. Create a persistent browser profile at: $PROFILE_DIR"
echo "2. Open Amazon.com for you to log in"
echo "3. Save your authenticated session"
echo ""
echo "Press Enter to continue..."
read

# Create profile directory
mkdir -p "$PROFILE_DIR"

# Run the auth script
python3 auth/retailer_auth.py --retailer amazon --profile-dir "$PROFILE_DIR"

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "✅ Profile setup complete!"
    echo "=========================================="
    echo ""
    echo "Next steps:"
    echo ""
    echo "1. Add to your shell profile (~/.zshrc or ~/.bash_profile):"
    echo "   export AMAZON_PROFILE_DIR=\"$PROFILE_DIR\""
    echo ""
    echo "2. Reload your shell:"
    echo "   source ~/.zshrc"
    echo ""
    echo "3. Or set it for this session:"
    echo "   export AMAZON_PROFILE_DIR=\"$PROFILE_DIR\""
    echo ""
else
    echo ""
    echo "❌ Profile setup failed"
    exit 1
fi
