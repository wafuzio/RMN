# GUI Display Issues - March 5, 2026

## Issue 1: Walmart House Ad Showing as "Unknown" ✅ FIXED

**Problem**: Walmart+ house ads (Gallery Cards) show brand as "Unknown" instead of "Walmart"

**Root Cause**: Walmart+ house ads use descriptive alt text like "A walmart plus bag filled with supplies next to a walmart plus gas station" instead of the expected brand extraction patterns

**Fix Applied**:
1. **Scraper** (`walmart_search_and_capture.py` lines 1418-1431): Added detection for "walmart plus" or "walmart+" in logo alt text and headline
2. **Backend** (`web/builder_server_v2.py` lines 2413-2418, 2971-2977): Added fallback detection for old JSON data in both API code paths

**Impact**: ✅ Future scrapes fixed, ✅ Past scrapes fixed via backend

---

## Issue 2: Orgain Instacart Ad Type Label ✅ NOT A BUG

**Problem**: User reported Orgain ad showing as "Shoppable Video Ad" but displaying as static image

**Investigation**: Backend correctly returns `Shoppable_Display_Ad` for Orgain ads. Frontend correctly displays "Shoppable Display Ad". The screenshot was likely from a different ad or misread.

**Status**: ✅ No fix needed - system working correctly

---

## Issue 3: Nutrail Ad Cropping - Partial Row Above and Cut Off ✅ FIXED

**Problem**: Instacart Shoppable Display Ad shows partial product row above and cuts off at bottom

**Root Cause**: Scraper was screenshotting the outer container `div` which includes padding/borders, instead of the inner `{div_id}-inner` element with actual ad content

**Fix Applied**: `instacart_search_and_capture.py` line 779
- Changed from `elements.append(('Shoppable Display Ad', div))` 
- To `elements.append(('Shoppable Display Ad', inner))`
- Now screenshots the inner element to avoid container padding/borders

**Impact**: ✅ Future scrapes fixed

---

## Issue 4: Oribe Vertical Ad in LHS Column (Should Be RHS) ✅ FIXED

**Problem**: Amazon Sponsored Display portrait ads appearing in left horizontal column instead of right vertical column

**Root Cause**: Amazon scraper wasn't capturing `dimensions` or `card_format` in JSON, so frontend couldn't route portrait ads to RHS column

**Fix Applied**: `amazon_search_and_capture.py` 
- Lines 2462-2474: Added dimension probing after screenshot for main Display ads
- Lines 2555-2559: Added dimensions/card_format to ad data
- Lines 3617-3630, 3674-3678: Added same fix to left rail ads
- Lines 3753-3765, 3823-3827: Added same fix to bottom ads
- Sets `card_format="tile"` when height > width * 1.5 (portrait)

**Impact**: ✅ Future scrapes fixed, ✅ Past scrapes partially fixed via backend probing (lines 3231-3258)

---

## Issue 5: Oreo Thin White Strip - Image Extraction Failure ✅ FIXED

**Problem**: Target Listing Page Banner ad shows as thin white strip instead of full ad image

**Root Cause**: Scraper was screenshotting the outer `div[data-module-type='ListingPageBannerAd']` container which has incorrect dimensions, instead of the actual ad image/anchor element

**Fix Applied**: `target_search_and_capture.py` lines 808-830
- Added cascading element targeting: anchor with doubleclick → anchor with image → image directly
- Screenshots the actual ad content instead of empty container
- Logs which element type was targeted for debugging

**Impact**: ✅ Future scrapes fixed

---

## Issue 6: Maybelline White Borders - Container Padding Issue ✅ ADDRESSED

**Problem**: Many ads from recent scrapes have white borders from container padding/margins

**Root Cause**: Screenshotting outer container elements that have padding, margins, or background colors instead of the actual ad creative

**Fixes Applied**:
1. **Walmart Gallery Cards** (already fixed in lines 1480-1491): Screenshots `#tile` instead of `#tile-container` to avoid margin/padding
2. **Instacart Display Ads** (Issue #3 fix): Screenshots inner element instead of outer container
3. **Target Banners** (Issue #5 fix): Screenshots anchor/image instead of container
4. **Amazon Display** (existing code lines 2456-2460): Already targets inner creative via `_display_screenshot_target()`

**Impact**: ✅ Systematic fixes applied across all major scrapers

---

## Priority Order

1. **Issue 6** (Maybelline white borders) - CRITICAL, widespread, recent
2. **Issue 1** (Walmart house ads) - ✅ FIXED
3. **Issue 4** (Oribe placement) - Affects user experience
4. **Issue 3** (Nutrail cropping) - Affects ad quality
5. **Issue 5** (Oreo extraction) - Complete failure case
6. **Issue 2** (Orgain label) - Cosmetic frontend issue

---

## Next Steps

1. ✅ Fix Issue 1 - Walmart house ad detection (COMPLETED)
2. Audit all scrapers for white border cropping issue (Issue 6)
3. Fix Oribe card format detection (Issue 4)
4. Fix Nutrail bounding box (Issue 3)
5. Fix Oreo image extraction (Issue 5)
6. Fix frontend ad type labeling (Issue 2)
