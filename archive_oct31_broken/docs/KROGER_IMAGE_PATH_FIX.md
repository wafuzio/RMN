# Kroger Image Path Fix

## Problem

Kroger was using the canonical JSON schema but TOA and Skyscraper ads were missing `image_path` fields, causing only 8% API coverage despite images being saved to disk.

### Root Cause

- ✅ Kroger saves images to disk (`TOA/`, `Skyscraper/`, `Carousel/`)
- ✅ Kroger uses canonical JSON structure
- ✅ Kroger populates `advertisers` array
- ❌ **TOA and Skyscraper ads never got `image_path` set in JSON**
- ✅ Carousel ads already had `image_path` working

## Solution

### 1. Updated `archived/kroger_ad_core.py`

Added `image_path` generation for TOA and Skyscraper ads (lines 898-934, 1091-1127):

**TOA Ads:**
```python
# Generate image_path for TOA (similar to carousel logic)
try:
    if timestamp and search_term and client:
        from filename_utils import generate_ad_filename
        from datetime import datetime
        
        # Parse timestamp to datetime
        ts_dt = None
        if isinstance(timestamp, str):
            try:
                ts_dt = datetime.strptime(timestamp, "%Y-%m-%d_%H-%M-%S")
            except ValueError:
                ts_dt = timestamp
        
        # Use canonical advertiser from lexicon, fallback to "unknown"
        canonical_advertiser = (ad.get('advertisers') or ['unknown'])[0]
        
        # Generate filename using same logic as screenshot script
        filename = generate_ad_filename(
            retailer="kroger",
            ad_type="toa",
            advertiser=canonical_advertiser,
            client=client,
            search_term=search_term,
            timestamp=ts_dt,
            index=idx
        )
        
        # Set relative path in ad data
        ad['toa_image_path'] = os.path.join('TOA', filename)
        # Canonical: mirror to image_path
        ad['image_path'] = ad['toa_image_path']
        log(f"Generated toa_image_path: {ad['toa_image_path']}")
except Exception as e:
    log(f"Error generating TOA filename: {e}")
```

**Skyscraper Ads:** Same pattern with `skyscraper_image_path`

### 2. Created Reconciliation Tool

`tools/reconcile_kroger_images_to_json.py` - Backfills existing JSON files with image paths.

**Features:**
- Scans all Kroger client directories for saved images
- Parses filenames to extract metadata (advertiser, ad_type, timestamp, etc.)
- Matches images to JSON files by timestamp and search term
- Updates ads with correct `image_path` fields
- Supports dry-run mode for safe testing

**Usage:**
```bash
# Dry run (preview changes)
python3 tools/reconcile_kroger_images_to_json.py --dry-run

# Reconcile all clients
python3 tools/reconcile_kroger_images_to_json.py

# Reconcile specific client
python3 tools/reconcile_kroger_images_to_json.py --client barilla
```

## Expected Results

### Before Fix:
| Ad Type | Saves Images? | Has `image_path`? | Coverage |
|---------|---------------|-------------------|----------|
| CuratedCarousel | ✅ Yes | ✅ Yes | ~100% |
| TOA | ✅ Yes | ❌ **NO** | ~0% |
| Skyscraper | ✅ Yes | ❌ **NO** | ~0% |
| **Overall** | ✅ Yes | ⚠️ Partial | **8%** |

### After Fix:
| Ad Type | Saves Images? | Has `image_path`? | Coverage |
|---------|---------------|-------------------|----------|
| CuratedCarousel | ✅ Yes | ✅ Yes | ~100% |
| TOA | ✅ Yes | ✅ **YES** | ~100% |
| Skyscraper | ✅ Yes | ✅ **YES** | ~100% |
| **Overall** | ✅ Yes | ✅ **YES** | **~100%** |

## Testing

### 1. Test New Scrapes

Run a new Kroger scrape and verify `image_path` is populated:

```bash
# Run scraper (if you have one configured)
python3 kroger_search_and_capture.py --client test_client --keyword "ice cream"

# Check JSON structure
cat output/kroger/test_client/runs/*/run_results_*.json | jq '.ads[0] | {type, advertisers, image_path}'
```

Expected output:
```json
{
  "type": "TOA",
  "advertisers": ["Breyers"],
  "image_path": "TOA/kroger__breyers__toa__test_client__ice_cream__D2025-10-29_T23-15.00_1.png"
}
```

### 2. Test Reconciliation Tool

```bash
# Dry run first
python3 tools/reconcile_kroger_images_to_json.py --client barilla --dry-run

# Apply changes
python3 tools/reconcile_kroger_images_to_json.py --client barilla
```

### 3. Verify API Coverage

```bash
# Check coverage before reconciliation
curl -s "http://localhost:5006/api/audit/images?retailer=kroger&client=barilla" | jq '{coverage_pct, resolvable, missing}'

# Run reconciliation
python3 tools/reconcile_kroger_images_to_json.py --client barilla

# Check coverage after reconciliation
curl -s "http://localhost:5006/api/audit/images?retailer=kroger&client=barilla" | jq '{coverage_pct, resolvable, missing}'
```

Expected improvement: 8% → ~100%

### 4. Verify Frontend

```bash
# Get sample cards
curl -s "http://localhost:5006/api/ads/cards?retailer=kroger&client=barilla&page_size=10" | jq '.cards[] | {brand, ad_type, image_url, has_image}'
```

All cards should have `has_image: true` instead of placeholders.

## Files Modified

1. **`archived/kroger_ad_core.py`**
   - Added `image_path` generation for TOA ads (lines 898-934)
   - Added `image_path` generation for Skyscraper ads (lines 1091-1127)

2. **`tools/reconcile_kroger_images_to_json.py`** (NEW)
   - Reconciliation tool to backfill existing JSON files

## Migration Path

1. ✅ Update `kroger_ad_core.py` (done)
2. ✅ Create reconciliation tool (done)
3. ⏳ Run reconciliation on existing data
4. ⏳ Verify API coverage improves to ~100%
5. ⏳ Test frontend shows all images

## Notes

- The fix follows the same pattern as Walmart and Instacart
- Carousel ads already worked, so no changes needed there
- The `_normalize_image_path_fields()` function already handles the fallback logic
- Future scrapes will automatically include `image_path` for all ad types
- Existing data can be backfilled using the reconciliation tool
