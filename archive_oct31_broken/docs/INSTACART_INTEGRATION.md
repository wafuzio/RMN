# Instacart Integration Summary

## Overview
Successfully integrated Instacart into the multi-retailer scraper application. The Instacart adapter follows the same architecture as Kroger and Amazon, enabling seamless keyword search and ad extraction.

## What Was Built

### 1. Authentication Setup
- **Script**: `scripts/setup_instacart_profile.sh`
- **Auth Module**: Updated `auth/retailer_auth.py` to support Instacart
- **Profile Location**: `~/Documents/Amazon_Scrape/profiles/instacart`
- **Environment Variables**:
  - `INSTACART_PROFILE_DIR`: Path to persistent Chrome profile
  - `INSTACART_STORE`: Store slug (default: `publix`)

### 2. Core Adapter Implementation
- **Directory**: `retailers/instacart/`
  - `adapter.py`: Main adapter class implementing `RetailerAdapter` interface
  - `__init__.py`: Package initialization
  - `README.md`: Comprehensive documentation

- **Search Script**: `instacart_search_and_capture.py`
  - Performs authenticated keyword searches
  - Saves HTML and JSON results
  - Extracts ad metadata (type, position, title, bounding box)

### 3. Integration Points
- **GUI Registration**: Updated `keyword_input.py` to import and register `InstacartAdapter`
- **Documentation**: Updated `docs/CONTEXT_SEED.md` with Instacart configuration
- **Testing**: Created `scripts/test_instacart_adapter.py` for end-to-end validation

## Technical Details

### URL Pattern
```
https://www.instacart.com/store/{store}/s?k={keyword}
```
Example:
```
https://www.instacart.com/store/publix/s?k=eggs
```

### **Ad Types Detected**
1. **Shoppable Display Ad** (`div.e-1qzz7bi`)
   - Static image ads with product carousels
   - Screenshots captured during same page load as data extraction
   - Folder: `Shoppable_Display_Ads/`

2. **Shoppable Video Ad** (`div.e-1qzz7bi` with video player)
   - Video ads with product carousels
   - Automatically detected by presence of video player element
   - Screenshots captured during same page load as data extraction
   - Folder: `Shoppable_Video_Ads/`

3. **Shoppable Recipe Ad** (`div.e-1yrpusx`)
   - Recipe cards with "Sponsored" label and brand logo
   - Includes recipe title, URL, and brand information
   - Screenshots captured during same page load as data extraction
   - Folder: `Shoppable_Recipe_Ads/`

4. **Display Ad** (`div.e-1hv1sre`)
   - Horizontal brand strips at top of search results
   - Screenshots captured during same page load as data extraction
   - Folder: `Display_Ads/`

### Wait Strategy
- Uses `domcontentloaded` instead of `networkidle` (Instacart has heavy dynamic content)
- 8-second explicit wait after page load for ad rendering
- Prevents timeout issues while ensuring ads are visible

## Verification Results

### Test 1: Ad Visibility with Authentication
**Script**: `scripts/test_instacart_ads_with_auth.py`

**Results**:
- ✅ 8 ads detected
- ✅ 3 Shoppable Display Ads
- ✅ 1 Top Banner Ad
- ✅ 4 Sponsored Labels
- ✅ Screenshots captured successfully

### Test 2: Adapter End-to-End
**Script**: `scripts/test_instacart_adapter.py`

**Results**:
- ✅ Adapter registered successfully
- ✅ Search and capture completed
- ✅ HTML saved: `runs/search_results_*.html`
- ✅ JSON saved: `runs/run_results_*.json`
- ✅ Ad metadata extracted (titles, types, positions)

## Usage Instructions

### One-Time Setup
```bash
# 1. Run setup script
./scripts/setup_instacart_profile.sh

# 2. Add to ~/.zshrc or ~/.bash_profile
export INSTACART_PROFILE_DIR=~/Documents/Amazon_Scrape/profiles/instacart
export INSTACART_STORE=publix  # Optional, defaults to publix

# 3. Reload shell
source ~/.zshrc
```

### Running the Scraper
```bash
# Via GUI
python3 keyword_input.py
# Select "Instacart" from retailer dropdown
# Enter keywords and click "Run Scraper"

# Via command line (testing)
python3 scripts/test_instacart_adapter.py
```

### Supported Stores
Common store slugs (configurable via `INSTACART_STORE`):
- `publix` (default)
- `kroger`
- `costco`
- `safeway`
- `albertsons`
- `wegmans`
- `heb`

## Output Structure
```
output/instacart/<client>/
├── runs/
│   ├── search_results_<keyword>_YYYY-MM-DD_HH-MM-SS.html
│   └── run_results_<keyword>_YYYY-MM-DD_HH-MM-SS.json
├── Shoppable_Display_Ads/    # Static display ads with products
├── Shoppable_Video_Ads/      # Video ads with products
├── Shoppable_Recipe_Ads/     # Recipe cards with brand sponsors
├── Display_Ads/              # Horizontal brand strips
└── Main/                     # Full-page screenshots

output/brand_logos/
├── brand_logo_database.json  # Centralized brand logo metadata
├── boiron.png
├── stonyfield_organic.png
└── nestle.jpg

logs/instacart/
├── keyword_input.log
└── image_extract_YYYYMMDD_HHMMSS.log
```

## Git Commits
1. **Authentication Setup** (commit: `3459304`)
   - Added Instacart support to `auth/retailer_auth.py`
   - Created `setup_instacart_profile.sh`
   - Added verification scripts and documentation

2. **Full Adapter Implementation** (commit: `c95db31`)
   - Created complete adapter structure
   - Implemented search and capture functionality
   - Registered with GUI
   - Updated documentation

## Recent Improvements (October 2025)

### 1. **Synchronized Screenshot Capture**
- **Problem**: Screenshots were taken in separate page loads, causing mismatches with HTML/JSON data
- **Solution**: Integrated screenshot capture directly into `instacart_search_and_capture.py`
- **Result**: All artifacts (HTML, JSON, screenshots) now from the same page load

### 2. **CDP Static Full-Page Screenshots**
- **Problem**: `page.screenshot(full_page=True)` caused viewport resizing, triggering DOM reflow
- **Solution**: Use Chrome DevTools Protocol's `Page.captureScreenshot` with `captureBeyondViewport=true`
- **Result**: Single-pass full-page capture without viewport manipulation

### 3. **Anti-Detection & Ad Loading**
- **Stable User Agent**: Mainstream Chrome UA to avoid automation fingerprinting
- **Consent Handling**: Broader selectors to dismiss consent banners on results page
- **Ad Creative Dwell Time**: Wait 1200ms for images/video to load (viewability gates)
- **Synthetic Dwell**: Emulate human behavior on direct navigation fallback

### 4. **Brand Logo Database**
- **Centralized Storage**: `output/brand_logos/` with metadata database
- **Content-Based Deduplication**: Identical images from different URLs share one file
- **Clean Naming**: `brand.png`, `brand_2.png` (no cryptic hashes)
- **JSON Enrichment**: `brand_logo` field automatically added to each ad

### 5. **Recipe Ad Support**
- **New Ad Type**: Shoppable Recipe Ads with sponsored brand logos
- **Extraction**: Recipe title, URL, brand, and logo
- **Screenshots**: Captured during same page load as other ads

## Known Limitations
1. **Store Selection**: Currently requires manual configuration via environment variable
2. **Ad Selectors**: Based on current HTML patterns (may change with Instacart UI updates)
3. **Lazy Loading**: Some below-fold ads may require additional scroll warmup

## Next Steps (Optional)
- [ ] Add GUI store selector for Instacart
- [ ] Add support for additional ad placements (e.g., in-grid sponsored products)
- [ ] Add multi-store testing capability
- [ ] Implement perceptual hashing for even better logo deduplication

## Success Criteria ✅
- [x] Instacart appears in GUI retailer dropdown
- [x] Authentication persists across sessions
- [x] Search returns valid HTML and JSON
- [x] Multiple ad types detected (Display, Video, Recipe)
- [x] Ad metadata extracted correctly
- [x] Screenshots synchronized with data extraction
- [x] Full-page screenshots without viewport resize
- [x] Brand logos extracted and deduplicated
- [x] JSON enriched with brand logo paths
- [x] Anti-detection measures implemented
- [x] No impact on existing Kroger/Amazon functionality
- [x] Documentation complete and up-to-date
- [x] End-to-end testing successful

---

**Status**: ✅ **COMPLETE** - Instacart adapter is fully functional with production-grade screenshot capture, brand logo management, and anti-detection measures.

**Last Updated**: 2025-10-16
