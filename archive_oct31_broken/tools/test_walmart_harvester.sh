#!/bin/bash
# Test Walmart Logo Harvester

echo "🧪 Testing Walmart Logo Harvester"
echo "=================================="
echo ""

# Check environment
if [ -z "$WALMART_PROFILE_DIR" ]; then
    echo "❌ WALMART_PROFILE_DIR not set"
    echo "   Run: export WALMART_PROFILE_DIR=\"/path/to/chrome/profile\""
    exit 1
fi

if [ ! -d "$WALMART_PROFILE_DIR" ]; then
    echo "❌ WALMART_PROFILE_DIR does not exist: $WALMART_PROFILE_DIR"
    exit 1
fi

echo "✅ WALMART_PROFILE_DIR: $WALMART_PROFILE_DIR"
echo ""

# Test with a known brand
BRAND="BOOST"
echo "🔍 Testing with brand: $BRAND"
echo ""

# Run harvester
python3 tools/walmart_logo_harvester.py "$BRAND" \
    --profile-dir "$WALMART_PROFILE_DIR" \
    --headless

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Harvester succeeded!"
    echo ""
    echo "📁 Check output:"
    echo "   - output/brand_logos/boost.*"
    echo "   - output/brand_logos/brand_logo_database.json"
    echo ""
    
    # Show the logo file if it exists
    if ls output/brand_logos/boost.* 1> /dev/null 2>&1; then
        echo "✅ Logo file found:"
        ls -lh output/brand_logos/boost.*
    fi
else
    echo "❌ Harvester failed with exit code: $EXIT_CODE"
fi

exit $EXIT_CODE
