#!/bin/bash
# Scan ALL brands across ALL retailers/clients for missing logos
# Since the brand logo database is shared, we gather all unique brands first

API_BASE="http://localhost:5006"
TEMP_BRANDS_FILE="/tmp/all_brands_$$.txt"

echo "🔍 LogoScout - Discovering all unique brands across all retailers"
echo "=================================================================="
echo ""

# Get all retailers and clients
RETAILERS=("instacart" "kroger" "walmart")

echo "📊 Gathering brands from all retailers/clients..."
> "$TEMP_BRANDS_FILE"  # Clear temp file

total_clients=0
for retailer in "${RETAILERS[@]}"; do
    echo "  Scanning $retailer..."
    
    # Get clients for this retailer
    clients=$(curl -s "$API_BASE/api/clients?retailer=$retailer" | jq -r '.clients[]' 2>/dev/null)
    
    if [ -z "$clients" ]; then
        echo "    ⚠️  No clients found"
        continue
    fi
    
    for client in $clients; do
        ((total_clients++))
        echo "    → $retailer/$client"
        
        # Fetch brands from this client and append to temp file
        python3 tools/logo_scout.py \
            --api "$API_BASE" \
            --retailer "$retailer" \
            --client "$client" \
            --limit 500 2>&1 | \
            grep "Found.*candidate brand" | \
            sed -E "s/.*\[(.*)\]/\1/" | \
            tr ',' '\n' | \
            sed "s/[' ]//g" >> "$TEMP_BRANDS_FILE"
    done
done

echo ""
echo "📈 Statistics:"
echo "  Total clients scanned: $total_clients"

# Get unique brands
sort -u "$TEMP_BRANDS_FILE" > "${TEMP_BRANDS_FILE}.unique"
unique_count=$(wc -l < "${TEMP_BRANDS_FILE}.unique")
echo "  Unique brands found: $unique_count"
echo ""

# Now run LogoScout on just one client to process all the unique brands
# (since it will check the shared database, it doesn't matter which client)
echo "🎯 Fetching missing logos for all unique brands..."
echo ""

# Use the first available client
first_retailer="instacart"
first_client=$(curl -s "$API_BASE/api/clients?retailer=$first_retailer" | jq -r '.clients[0]' 2>/dev/null)

if [ -n "$first_client" ]; then
    python3 tools/logo_scout.py \
        --api "$API_BASE" \
        --retailer "$first_retailer" \
        --client "$first_client" \
        --limit "$unique_count"
fi

# Cleanup
rm -f "$TEMP_BRANDS_FILE" "${TEMP_BRANDS_FILE}.unique"

echo ""
echo "✅ LogoScout scan complete!"
echo ""
echo "📊 Logo Database Summary:"
ls -lh web/static/brand-logos/ 2>/dev/null | tail -n +2 | wc -l | xargs echo "  Files in web/static/brand-logos/:"
du -sh web/static/brand-logos/ 2>/dev/null | cut -f1 | xargs echo "  Total size:"
echo ""
ls -lh output/brand_logos/*.{jpg,png,svg} 2>/dev/null | wc -l | xargs echo "  Files in output/brand_logos/:"
du -sh output/brand_logos/ 2>/dev/null | cut -f1 | xargs echo "  Total size:"
