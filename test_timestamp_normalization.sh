#!/bin/bash
# Test Timestamp Normalization
# Verifies that all timestamps are normalized to ISO 8601 Z format

set -e

echo "=============================================="
echo "Timestamp Normalization Test"
echo "=============================================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Test 1: Check cards endpoint returns ISO Z timestamps
echo "Test 1: Checking /api/ads/cards timestamps..."
RESPONSE=$(curl -s "http://localhost:5006/api/ads/cards?retailer=walmart&client=halo_top&page_size=5")

# Check if all timestamps match ISO Z format
ISO_Z_COUNT=$(echo "$RESPONSE" | jq '[.cards[].timestamp] | map(select(test("^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$"))) | length')
TOTAL_COUNT=$(echo "$RESPONSE" | jq '.cards | length')

if [ "$ISO_Z_COUNT" -eq "$TOTAL_COUNT" ]; then
    echo -e "${GREEN}✅ All $TOTAL_COUNT card timestamps are ISO Z format${NC}"
else
    echo -e "${RED}❌ Only $ISO_Z_COUNT/$TOTAL_COUNT timestamps are ISO Z format${NC}"
    echo "Sample timestamps:"
    echo "$RESPONSE" | jq '.cards[].timestamp' | head -5
fi

# Test 2: Check timestamp_ms field exists
echo ""
echo "Test 2: Checking timestamp_ms field..."
HAS_EPOCH=$(echo "$RESPONSE" | jq '[.cards[].timestamp_ms] | map(select(. != null and . > 0)) | length')

if [ "$HAS_EPOCH" -eq "$TOTAL_COUNT" ]; then
    echo -e "${GREEN}✅ All $TOTAL_COUNT cards have timestamp_ms (epoch)${NC}"
else
    echo -e "${YELLOW}⚠️  Only $HAS_EPOCH/$TOTAL_COUNT cards have timestamp_ms${NC}"
fi

# Test 3: Check runs endpoint returns ISO Z timestamps
echo ""
echo "Test 3: Checking /api/runs timestamps..."
RUNS_RESPONSE=$(curl -s "http://localhost:5006/api/runs?retailer=walmart&client=halo_top")

RUNS_ISO_COUNT=$(echo "$RUNS_RESPONSE" | jq '[.runs[].timestamp] | map(select(test("^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$"))) | length')
RUNS_TOTAL=$(echo "$RUNS_RESPONSE" | jq '.runs | length')

if [ "$RUNS_ISO_COUNT" -eq "$RUNS_TOTAL" ]; then
    echo -e "${GREEN}✅ All $RUNS_TOTAL run timestamps are ISO Z format${NC}"
else
    echo -e "${RED}❌ Only $RUNS_ISO_COUNT/$RUNS_TOTAL run timestamps are ISO Z format${NC}"
fi

# Test 4: Verify timestamps are parseable
echo ""
echo "Test 4: Verifying timestamps are parseable..."
SAMPLE_TS=$(echo "$RESPONSE" | jq -r '.cards[0].timestamp')
echo "Sample timestamp: $SAMPLE_TS"

# Try to parse with date command (macOS compatible)
if date -j -f "%Y-%m-%dT%H:%M:%SZ" "$SAMPLE_TS" "+%Y-%m-%d %H:%M:%S UTC" 2>/dev/null; then
    echo -e "${GREEN}✅ Timestamp is parseable${NC}"
else
    echo -e "${RED}❌ Timestamp parsing failed${NC}"
fi

# Test 5: Check date filtering works with UTC
echo ""
echo "Test 5: Testing UTC date filtering..."
TODAY=$(date -u +"%Y-%m-%d")
YESTERDAY=$(date -u -v-1d +"%Y-%m-%d")

FILTERED=$(curl -s "http://localhost:5006/api/ads/cards?retailer=walmart&client=halo_top&start=$YESTERDAY&end=$TODAY&page_size=100")
FILTERED_COUNT=$(echo "$FILTERED" | jq '.cards | length')

echo "Cards from $YESTERDAY to $TODAY: $FILTERED_COUNT"
if [ "$FILTERED_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✅ Date filtering working${NC}"
else
    echo -e "${YELLOW}⚠️  No cards in date range (may be expected if no recent data)${NC}"
fi

# Summary
echo ""
echo "=============================================="
echo "Test Summary"
echo "=============================================="
echo "Cards tested: $TOTAL_COUNT"
echo "ISO Z format: $ISO_Z_COUNT/$TOTAL_COUNT"
echo "With epoch_ms: $HAS_EPOCH/$TOTAL_COUNT"
echo "Runs tested: $RUNS_TOTAL"
echo "Runs ISO Z: $RUNS_ISO_COUNT/$RUNS_TOTAL"
echo ""

if [ "$ISO_Z_COUNT" -eq "$TOTAL_COUNT" ] && [ "$RUNS_ISO_COUNT" -eq "$RUNS_TOTAL" ]; then
    echo -e "${GREEN}✅ Timestamp normalization working perfectly!${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Update Builder.io frontend to use ISO Z timestamps"
    echo "2. Test MTD/YTD filtering with UTC ranges"
    echo "3. Verify grid and modal show same formatted time"
else
    echo -e "${RED}❌ Some timestamps not normalized${NC}"
    echo "Check Flask logs for errors"
fi
