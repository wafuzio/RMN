# Taxonomy Migration Summary

**Date:** 2025-10-10  
**Branch:** `builder_integration`  
**Status:** ✅ Complete

---

## What Was Done

### 1. Created Migration Script ✅

**File:** `scripts/maintenance/migrate_taxonomy.py`

**Features:**
- Safe, non-destructive migration with `--dry-run` mode
- Retailer-specific migration logic
- Color-coded output with detailed logging
- Idempotent (can run multiple times safely)
- Backs up data by updating JSON with mappings

**Usage:**
```bash
# Dry run (see what would happen)
python3 scripts/maintenance/migrate_taxonomy.py --retailer walmart --client land_o_frost --dry-run

# Execute migration
python3 scripts/maintenance/migrate_taxonomy.py --retailer walmart --client land_o_frost --execute

# Migrate all retailers
python3 scripts/maintenance/migrate_taxonomy.py --retailer all --execute
```

---

### 2. Walmart Migration ✅

**Problem:** All images saved in `runs/<timestamp>/` instead of ad-type folders

**Solution:**
- Moved images to correct folders (SBA/, SBV/, Tile_Takeover/, Top_Banner/)
- Updated JSON with `image_paths` mapping
- Kept only JSON/HTML/logs in runs/

**Results:**
```
Walmart land_o_frost:
- 8 files moved
- 2 JSON files updated
- Images now in: SBA/, SBV/, Tile_Takeover/
```

**Before:**
```
runs/20251010150112/
├── walmart_packaged_deli_meat_sba_1.png      ❌
├── walmart_packaged_deli_meat_sbv_1.png      ❌
├── walmart_packaged_deli_meat_sbv_1.mp4      ❌
├── walmart_packaged_deli_meat_tile_takeover_1.png  ❌
├── run_results_*.json                        ✅
└── run_report.json                           ✅
```

**After:**
```
SBA/walmart_packaged_deli_meat_sba_1.png                    ✅
SBV/walmart_packaged_deli_meat_sbv_1.png                    ✅
SBV/walmart_packaged_deli_meat_sbv_1.mp4                    ✅
Tile_Takeover/walmart_packaged_deli_meat_tile_takeover_1.png ✅
runs/20251010150112/
├── run_results_*.json                                       ✅
└── run_report.json                                          ✅
```

---

### 3. Instacart Migration ✅

**Problem:** JSON doesn't reference saved images

**Solution:**
- Scanned saved images in ad-type folders
- Matched images to JSON entries by timestamp/keyword
- Added `image_path` fields to JSON

**Results:**
```
Instacart land_o_frost:
- 5 images linked
- 2 JSON files updated
- Images now referenced in JSON
```

**Before:**
```json
{
  "type": "Shoppable Display Ad",
  "title": "Applegate Breakfast Favorites",
  "selector": "div.e-1qzz7bi"
  // ❌ No image_path
}
```

**After:**
```json
{
  "type": "Shoppable Display Ad",
  "title": "Applegate Breakfast Favorites",
  "selector": "div.e-1qzz7bi",
  "image_path": "Shoppable_Display_Ads/ShoppableDisplayAd_packaged_deli_meat_20251010_150339_1.png"  ✅
}
```

---

### 4. Flask API Updates ✅

**File:** `web/builder_server_v2.py`

**Changes:**
1. **Handle nested directory structures**
   - Scans both flat and nested runs/ directories
   - Supports Walmart's `runs/<timestamp>/` structure
   
2. **Support path parameters in image URLs**
   - Changed route from `/<filename>` to `/<path:filename>`
   - Handles paths like `SBA/image.png`
   
3. **Use image_paths mapping**
   - Reads `image_paths` field from migrated JSON
   - Matches ad types to images for Walmart
   
4. **Updated all endpoints**
   - `/api/runs` - Finds JSON in subdirectories
   - `/api/terms` - Scans nested structures
   - `/api/ads/cards` - Processes nested JSON files
   - `/api/image` - Serves images from correct paths

---

## Testing Results

### Walmart ✅
```bash
curl "http://localhost:5006/api/runs?retailer=walmart&client=land_o_frost"
# Returns: 2 runs with 3 ads each

curl "http://localhost:5006/api/ads/cards?retailer=walmart&client=land_o_frost"
# Returns: 6 ad cards with correct image URLs

curl "http://localhost:5006/api/image/walmart/land_o_frost/SBA/walmart_packaged_deli_meat_sba_1.png"
# Returns: 200 OK (210KB image)
```

### Instacart ✅
```bash
curl "http://localhost:5006/api/runs?retailer=instacart&client=land_o_frost"
# Returns: 2 runs with ads

curl "http://localhost:5006/api/ads/cards?retailer=instacart&client=land_o_frost"
# Returns: 14 ad cards with brand names (from title field)

curl "http://localhost:5006/api/image/instacart/land_o_frost/ShoppableDisplayAd_packaged_deli_meat_20251010_150339_2.png"
# Returns: 200 OK (343KB image)
```

### Dashboard ✅
- Open http://localhost:3000
- Select Walmart → land_o_frost
- See 6 ad cards with images
- Select Instacart → land_o_frost
- See 14 ad cards with brand names

---

## What's Left to Do

### Phase 1: Migrate Existing Data (Optional)
Run migration on other clients:
```bash
# Migrate all Walmart clients
python3 scripts/maintenance/migrate_taxonomy.py --retailer walmart --execute

# Migrate all Instacart clients
python3 scripts/maintenance/migrate_taxonomy.py --retailer instacart --execute

# Migrate all Kroger clients
python3 scripts/maintenance/migrate_taxonomy.py --retailer kroger --execute
```

### Phase 2: Fix Scrapers (Future)
Update scrapers to follow taxonomy from the start:

**Walmart (`walmart_search_and_capture.py`):**
- [ ] Use `core.paths.output_dir_for()` to get base directory
- [ ] Save images directly to ad-type folders (SBA/, SBV/, etc.)
- [ ] Update JSON with correct image paths as images are saved
- [ ] Keep only JSON/HTML/logs in runs/

**Instacart (`instacart_search_and_capture.py`):**
- [ ] Add `image_path` field to JSON when saving images
- [ ] Optionally add `brand` field (currently uses `title`)

**Kroger (`kroger_search_and_capture.py`):**
- [ ] Fix path generation to match actual saved files
- [ ] Update JSON with correct paths (not UUID-based)

### Phase 3: Cleanup (Optional)
- [ ] Remove old migration script once scrapers are fixed
- [ ] Add tests for taxonomy compliance
- [ ] Update onboarding docs with taxonomy requirements

---

## Files Changed

### New Files
- `scripts/maintenance/migrate_taxonomy.py` - Migration script

### Modified Files
- `web/builder_server_v2.py` - API updates for nested structures
- `docs/ARTIFACT_TAXONOMY.md` - Added known issues section

### Git Commits
1. `6ce7a4c` - Initial Builder.io integration
2. `1cb2bb2` - Taxonomy migration script and API fixes

---

## Key Learnings

1. **Non-destructive migrations are key** - Dry-run mode prevented accidents
2. **Idempotent operations** - Can run migration multiple times safely
3. **Workarounds in API** - Fixed display issues without touching scrapers
4. **Nested directory support** - API now handles multiple file structures
5. **Path parameters in Flask** - `<path:filename>` allows subdirectory paths

---

## Compliance Checklist

When updating scrapers, ensure:

- [ ] Uses `core.paths.output_dir_for()` to get base directory
- [ ] Saves images to ad-type-specific folders (not runs/)
- [ ] Updates JSON with correct `image_path` references
- [ ] Uses `brand` field (not retailer-specific field names)
- [ ] Saves only JSON/HTML/logs to runs/ directory
- [ ] Follows naming convention: `<ad_type>_<keyword>_<timestamp>_<index>.<ext>`
- [ ] Tests with `utils.path_taxonomy.allowed_subdirs()` to verify folders

---

## References

- **Taxonomy Definition:** `docs/ARTIFACT_TAXONOMY.md`
- **Migration Script:** `scripts/maintenance/migrate_taxonomy.py`
- **API Server:** `web/builder_server_v2.py`
- **Builder Guide:** `docs/BUILDER_GUIDE.md`
- **Path Utilities:** `utils/path_taxonomy.py`

---

**Status:** ✅ Migration complete and tested  
**Next:** Run migration on remaining clients or update scrapers
