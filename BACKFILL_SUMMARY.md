# GUI Display Issues - Backfill Summary
**Date**: March 5, 2026

## ✅ Completed Fixes

### 1. White Border Cropping - Target Sponsored Logos
**Status**: ✅ **COMPLETE - 70 images fixed**

**Problem**: Target Sponsored Logo images had ~1025px of white borders/padding, preventing proper display.

**Solution**: Created `tools/crop_white_borders.py` utility that:
- Detects non-white content boundaries
- Crops to actual content area
- Reduces images from 1319x272 to 300x266

**Results**:
- **70 images cropped** across 8 clients (curology, milkpep, blue_bunny, goodles, bomb_pop, Proactiv, barilla, Community_Coffee, quip)
- Removed ~1025px of white borders per image
- Images now display correctly without white padding

**Usage**:
```bash
# Preview cropping for all retailers
.venv/bin/python3 tools/crop_white_borders.py --all --preview

# Apply cropping to specific retailer/ad type
.venv/bin/python3 tools/crop_white_borders.py --retailer target --ad-type Sponsored_Logo --apply
```

---

### 2. Amazon Carousel Blacklist
**Status**: ✅ **COMPLETE - Future scrapes fixed**

**Problem**: Amazon house ad carousels like "Trending now" and "Picks from Amazon Influencers" were being included in results.

**Solution**: Added missing phrases to `CAROUSEL_HEADINGS` blacklist in `amazon_search_and_capture.py`:
- "Picks from Amazon Influencers"
- "From Amazon influencer storefronts"

**Impact**: Future Amazon scrapes will filter out these house ad carousels.

---

### 3. Backfill Scripts Created
**Status**: ✅ **COMPLETE - Tools ready**

Created comprehensive backfill utilities:

#### `tools/backfill_gui_fixes.py`
Fixes multiple issues in historical JSON data:
- Walmart house ads (Gallery Cards with walmart+ messaging)
- Amazon Sponsored Display (adds dimensions and card_format)
- Amazon house ad carousels (removes blacklisted phrases)
- Instacart video ads (audits missing video_path)

**Usage**:
```bash
# Preview fixes for specific retailer
.venv/bin/python3 tools/backfill_gui_fixes.py --retailer walmart --preview

# Apply fixes to all retailers
.venv/bin/python3 tools/backfill_gui_fixes.py --retailer all --apply
```

**Results**:
- Walmart: 7,362 files scanned, 0 house ads found to fix
- Amazon: 0 files found (data stored differently)

#### `tools/crop_white_borders.py`
Crops white borders from ad images.

**Features**:
- Detects content boundaries automatically
- Configurable white threshold (default 250/255)
- Filter by retailer, client, or ad type
- Preview mode before applying

---

## ⚠️ Partial Fixes / Limitations

### 4. Instacart Video Paths
**Status**: ⚠️ **BLOCKED - Missing metadata**

**Problem**: Orgain and other Instacart video ads have `video_overlay` coordinates but missing `video_path` field.

**Investigation**: 
- ✅ Videos exist in centralized storage: `output/instacart/_shared_videos/` (174 MP4 files)
- ❌ JSON data lacks `video_url` field needed to map videos to ads
- Videos are stored with MD5 hash filenames, but without the original URL we can't compute the hash

**Created Tool**: `tools/fix_instacart_video_paths.py` - ready to use once `video_url` is added to scraper output

**Next Steps**:
1. Update Instacart scraper to save `video_url` in ad JSON
2. Re-run backfill script to map existing videos
3. For old data without `video_url`, videos cannot be mapped retroactively

---

### 5. Walmart House Ads
**Status**: ⚠️ **No historical data found**

**Investigation**: Backfill script scanned 7,362 Walmart run files but found 0 Gallery Cards with walmart+ messaging and Unknown brand.

**Possible reasons**:
- Data may be in different location or format
- Backend fix in `builder_server_v2.py` may already be handling it at API time
- Issue may be in aggregated views rather than individual run files

**Backend Fix**: Already in place at lines 2413-2418 and 2971-2977 of `builder_server_v2.py`

---

### 6. Amazon Sponsored Display Dimensions
**Status**: ⚠️ **No data found**

**Investigation**: Backfill script found 0 Amazon run files in standard location.

**Possible reasons**:
- Amazon data stored in different directory structure
- Data may be in database rather than JSON files
- Need to verify actual Amazon data location

**Scraper Fix**: Already applied to `amazon_search_and_capture.py` for future scrapes

---

## 📊 Summary Statistics

| Fix | Status | Files Processed | Items Fixed |
|-----|--------|----------------|-------------|
| Target White Borders | ✅ Complete | 120 images | 70 cropped |
| Walmart House Ads | ⚠️ No data | 7,362 files | 0 found |
| Amazon Dimensions | ⚠️ No data | 0 files | N/A |
| Amazon Carousels | ✅ Complete | Scraper updated | Future only |
| Instacart Videos | ⚠️ Blocked | 174 videos exist | Need video_url |

---

## 🚀 Future Scrape Fixes (Already Applied)

All scraper improvements from today are in place:

1. ✅ **Walmart house ads** - Detection in scraper + backend fallback
2. ✅ **Instacart cropping** - Screenshot inner element (no padding)
3. ✅ **Amazon Sponsored Display** - Dimensions + card_format for portrait routing
4. ✅ **Target banners** - Screenshot anchor/image (not container)
5. ✅ **Amazon carousels** - Blacklist updated with missing phrases
6. ✅ **White borders** - All scrapers target inner elements

---

## 📝 Recommendations

### Immediate Actions:
1. ✅ **DONE**: Crop Target Sponsored Logo white borders (70 images fixed)
2. ⏭️ **SKIP**: Walmart/Amazon backfill (no data found in expected locations)
3. 🔄 **TODO**: Update Instacart scraper to save `video_url` field

### For Instacart Videos:
The scraper needs to be updated to save the `video_url` field in the ad JSON:

```python
# In instacart_search_and_capture.py, around line 1200
ad_data = {
    "type": ad_type,
    "brand": brand,
    "image_path": rel_img,
    "video_overlay": video_overlay,
    "video_path": video_rel_path,  # Already saved
    "video_url": video_src,         # ADD THIS LINE
    # ... rest of fields
}
```

Once added, run:
```bash
.venv/bin/python3 tools/fix_instacart_video_paths.py --apply
```

### For Old Data Verification:
If Walmart house ads or Amazon Sponsored Display issues persist in the GUI:
1. Check if data is in database rather than JSON files
2. Verify backend API is correctly applying fallback fixes
3. Check browser console for any API errors
4. Confirm frontend is using latest deployed version

---

## 🛠️ Available Tools

All backfill tools are located in `tools/` directory:

1. **`backfill_gui_fixes.py`** - Multi-purpose JSON fixer
2. **`crop_white_borders.py`** - Image border cropper  
3. **`fix_instacart_video_paths.py`** - Video path mapper (needs video_url)

Each tool has `--preview` and `--apply` modes for safe testing before making changes.
