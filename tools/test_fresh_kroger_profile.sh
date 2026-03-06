#!/bin/bash
# Test Kroger with a completely fresh profile to isolate if cookies are the issue

FRESH_PROFILE="$HOME/ChromeProfiles/kroger_test_fresh_$(date +%Y%m%d_%H%M%S)"

echo "Creating fresh profile at: $FRESH_PROFILE"
mkdir -p "$FRESH_PROFILE"

echo ""
echo "Testing with FRESH profile (no cookies, no history)..."
echo "This will help determine if kroger_clean_profile cookies are burned."
echo ""

# Modify the test script to use fresh profile temporarily
cd /Users/dan.maguire/Documents/Amazon_Scrape

# Run with fresh profile
USER_DATA_DIR="$FRESH_PROFILE" .venv/bin/python3 tools/kroger_step_by_step_test.py --step homepage

echo ""
echo "Fresh profile test complete."
echo "Profile location: $FRESH_PROFILE"
echo ""
echo "If this test SUCCEEDS:"
echo "  → kroger_clean_profile cookies are burned"
echo "  → Solution: Use fresh profile for production"
echo ""
echo "If this test FAILS:"
echo "  → IP is flagged (not profile)"
echo "  → Solution: Wait 24 hours or use different IP"
