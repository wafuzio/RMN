#!/bin/bash
# Test script to verify Walmart ads[] population

echo "========================================="
echo "🧪 WALMART ADS[] POPULATION TEST"
echo "========================================="
echo ""

# Find latest run
latest_run=$(ls -1d output/walmart/*/runs/* 2>/dev/null | sort | tail -n1)

if [ -z "$latest_run" ]; then
    echo "❌ No Walmart runs found"
    exit 1
fi

echo "📁 Latest run: $latest_run"
echo ""

# Check if run_results JSON exists
json_file=$(ls "$latest_run"/run_results_*.json 2>/dev/null | head -n1)

if [ -z "$json_file" ]; then
    echo "❌ No run_results_*.json found in $latest_run"
    exit 1
fi

echo "📄 JSON file: $json_file"
echo ""

# Check ads count
ads_count=$(jq '.ads | length' "$json_file" 2>/dev/null)

if [ -z "$ads_count" ]; then
    echo "❌ Failed to read ads count"
    exit 1
fi

echo "📊 Ads count: $ads_count"
echo ""

if [ "$ads_count" -eq 0 ]; then
    echo "⚠️  WARNING: No ads captured (ads_count = 0)"
    echo "   This might be expected if no ads were present on the page"
    echo ""
fi

# Show first ad (if any)
if [ "$ads_count" -gt 0 ]; then
    echo "🔍 First ad object:"
    echo "---"
    jq '.ads[0]' "$json_file" 2>/dev/null | head -n 30
    echo "---"
    echo ""
    
    # Validate ad structure
    echo "✅ Validating ad structure..."
    
    # Check required fields
    for field in id type brand brand_logo title description cta href image_url image_path products metadata; do
        has_field=$(jq ".ads[0] | has(\"$field\")" "$json_file" 2>/dev/null)
        if [ "$has_field" = "true" ]; then
            echo "  ✓ $field"
        else
            echo "  ✗ $field (MISSING)"
        fi
    done
    echo ""
    
    # Check ad types
    echo "📋 Ad types found:"
    jq '.ads | group_by(.type) | map({type: .[0].type, count: length})' "$json_file" 2>/dev/null
    echo ""
    
    # Check image paths
    echo "🖼️  Image path validation:"
    bad_paths=$(jq '.ads[] | select(.image_path | startswith("runs/")) | .image_path' "$json_file" 2>/dev/null)
    if [ -n "$bad_paths" ]; then
        echo "  ❌ Found images in runs/ folder (should be in SBA/SBV/Tile_Takeover):"
        echo "$bad_paths"
    else
        echo "  ✅ All image paths start with correct folders (SBA/SBV/Tile_Takeover)"
    fi
    echo ""
fi

echo "========================================="
echo "✅ TEST COMPLETE"
echo "========================================="
