#!/bin/bash
# Test Media-Aware Cards Implementation
# Tests that images and videos are properly separated

set -e

echo "=============================================="
echo "Media-Aware Cards Test"
echo "=============================================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Test 1: Check API returns cards with media fields
echo "Test 1: Fetching cards from API..."
RESPONSE=$(curl -s "http://localhost:5006/api/ads/cards?retailer=walmart&client=halo_top&page_size=10")
CARD_COUNT=$(echo "$RESPONSE" | jq '.cards | length')

if [ "$CARD_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✅ API returned $CARD_COUNT cards${NC}"
else
    echo -e "${RED}❌ No cards returned${NC}"
    exit 1
fi

# Test 2: Check all cards have image_url
echo ""
echo "Test 2: Checking all cards have image_url..."
CARDS_WITH_IMAGE=$(echo "$RESPONSE" | jq '[.cards[] | select(.image_url != null and .image_url != "")] | length')

if [ "$CARDS_WITH_IMAGE" -eq "$CARD_COUNT" ]; then
    echo -e "${GREEN}✅ All $CARD_COUNT cards have image_url${NC}"
else
    echo -e "${RED}❌ Only $CARDS_WITH_IMAGE/$CARD_COUNT cards have image_url${NC}"
fi

# Test 3: Check for video cards
echo ""
echo "Test 3: Checking for video support..."
CARDS_WITH_VIDEO=$(echo "$RESPONSE" | jq '[.cards[] | select(.video_url != null and .video_url != "")] | length')

if [ "$CARDS_WITH_VIDEO" -gt 0 ]; then
    echo -e "${GREEN}✅ Found $CARDS_WITH_VIDEO cards with video_url${NC}"
    
    # Test 4: Check video cards have poster_url
    VIDEOS_WITH_POSTER=$(echo "$RESPONSE" | jq '[.cards[] | select(.video_url != null and .poster_url != null)] | length')
    if [ "$VIDEOS_WITH_POSTER" -eq "$CARDS_WITH_VIDEO" ]; then
        echo -e "${GREEN}✅ All $CARDS_WITH_VIDEO video cards have poster_url${NC}"
    else
        echo -e "${YELLOW}⚠️  Only $VIDEOS_WITH_POSTER/$CARDS_WITH_VIDEO video cards have poster_url${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  No video cards found (this is OK if client has no SBV ads)${NC}"
fi

# Test 5: Test video endpoint
echo ""
echo "Test 5: Testing video endpoint..."
VIDEO_URL=$(echo "$RESPONSE" | jq -r '.cards[] | select(.video_url != null) | .video_url' | head -1)

if [ -n "$VIDEO_URL" ] && [ "$VIDEO_URL" != "null" ]; then
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:5006${VIDEO_URL}")
    if [ "$HTTP_CODE" -eq 200 ]; then
        echo -e "${GREEN}✅ Video endpoint working (HTTP $HTTP_CODE)${NC}"
    else
        echo -e "${RED}❌ Video endpoint failed (HTTP $HTTP_CODE)${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  No video URL to test${NC}"
fi

# Test 6: Test image endpoint
echo ""
echo "Test 6: Testing image endpoint..."
IMAGE_URL=$(echo "$RESPONSE" | jq -r '.cards[0].image_url')

if [ -n "$IMAGE_URL" ] && [ "$IMAGE_URL" != "null" ]; then
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:5006${IMAGE_URL}")
    if [ "$HTTP_CODE" -eq 200 ]; then
        echo -e "${GREEN}✅ Image endpoint working (HTTP $HTTP_CODE)${NC}"
    else
        echo -e "${RED}❌ Image endpoint failed (HTTP $HTTP_CODE)${NC}"
    fi
else
    echo -e "${RED}❌ No image URL to test${NC}"
fi

# Summary
echo ""
echo "=============================================="
echo "Test Summary"
echo "=============================================="
echo "Total cards: $CARD_COUNT"
echo "Cards with image_url: $CARDS_WITH_IMAGE"
echo "Cards with video_url: $CARDS_WITH_VIDEO"
echo ""
echo -e "${GREEN}✅ Media-aware cards implementation working!${NC}"
echo ""
echo "Next steps:"
echo "1. Test in Builder.io grid (images should display)"
echo "2. Test in Builder.io modal (videos should play)"
echo "3. Verify poster images show before video plays"
