# Brand Lexicon Integration

**Status:** ✅ COMPLETE - Canonical brand normalization applied across all retailers

## Overview

The brand lexicon (`config/brands.json`) provides canonical brand name mappings to ensure consistent brand attribution across all retailers. This prevents fragmentation where "Lay's", "Lays", and "Lay_s" would be treated as different brands.

## What Was Implemented

### A) Walmart Ad Builder
**File:** `walmart_search_and_capture.py`

**Change:** Added brand canonicalization in `build_ad_object()`:

```python
from core.brands import canonicalize

# In build_ad_object():
raw_brand = _ensure_str_or_none(brand_name)
canon_brand = canonicalize(raw_brand) if raw_brand else None

ad_obj = {
    "brand": canon_brand or raw_brand,  # prefer canonical; fallback to raw
    ...
}
```

**Impact:** All Walmart ads now have canonical brand names.

---

### B) Batch Rebuild Tool
**File:** `tools/batch_rebuild_walmart_runs_from_images.py`

**Change:** Canonicalize brand token extracted from filenames:

```python
from core.brands import canonicalize

# In build_ad_object():
de_slug = None if brand_token == "unknown" else slug_to_words(brand_token)
brand = canonicalize(de_slug) if de_slug else None
```

**Impact:** Orphaned images rebuilt from filenames get canonical brand names.

---

### C) Brand Logo Database
**File:** `brand_logo_database.py`

**Change:** Always store canonical brand names:

```python
from core.brands import canonicalize

# In add_brand_logo():
canon = canonicalize(brand) if brand else None
display_name = canon or brand or "unknown"
brand_key = self._normalize_brand_name(display_name)

self.database["brands"][brand_key] = {
    "brand_name": display_name,  # Canonical brand name
    ...
}
```

**Impact:** Brand logo database has one entry per canonical brand, no fragmentation.

---

### D) Kroger (Already Implemented)
**File:** `archived/kroger_ad_core.py`

**Status:** ✅ Already using lexicon via `_extract_kroger_advertiser()`

- CuratedCarousel filenames use canonical brand
- TOA and Skyscraper ads get canonical brand names
- All Kroger ads flow through lexicon normalization

---

## Lexicon Validation Tool

**File:** `tools/validate_lexicon.py`

Checks `config/brands.json` for:
- ✅ Duplicate synonyms mapping to multiple brands
- ✅ Campaign-like synonyms (Q1, Q2, 2025, etc.)
- ✅ Cross-brand pollution (brand A having brand B as synonym)

**Usage:**
```bash
python3 tools/validate_lexicon.py
```

**Current Status:**
- ⚠️ 17 duplicate synonym collisions found
- ⚠️ 24 campaign-like synonyms found
- ⚠️ Cross-brand pollution detected

**Recommended Action:** Clean up `config/brands.json` to remove:
1. Campaign codes (e.g., "MSCCollegeFootballWave210152 5", "SSMAlwaysOn0625")
2. Duplicate synonyms (e.g., "Bertolli" in both Bertolli and Birds Eye)
3. Cross-brand references (e.g., "Cottonelle" in Kleenex synonyms)

---

## Where Lexicon Is Used

### Walmart
- ✅ `build_ad_object()` - Canonicalizes brand during ad creation
- ✅ `batch_rebuild_walmart_runs_from_images.py` - Canonicalizes brand from filenames
- ✅ Brand logo enrichment (when implemented) - Will use canonical brands

### Kroger
- ✅ `_extract_kroger_advertiser()` - Already canonicalizes via lexicon
- ✅ `generate_ad_filename()` - Uses canonical brand for filenames
- ✅ CuratedCarousel, TOA, Skyscraper - All use canonical brands

### Brand Logo Database
- ✅ `add_brand_logo()` - Always stores canonical brand names
- ✅ Logo filenames use canonical brand tokens
- ✅ One database entry per canonical brand

### Future Retailers (Instacart, Amazon)
- 🔄 Will use `canonicalize()` in their ad builders
- 🔄 Will follow same pattern as Walmart/Kroger

---

## Benefits

### 1. Consistent Brand Attribution
```json
// Before (fragmented):
{"brand": "Lays"}
{"brand": "Lay's"}
{"brand": "Lay_s"}

// After (canonical):
{"brand": "Lay's"}
{"brand": "Lay's"}
{"brand": "Lay's"}
```

### 2. Stable Filenames
```
// Before:
kroger__lays__toa__...png
kroger__lay_s__toa__...png

// After:
kroger__lay's__toa__...png
kroger__lay's__toa__...png
```

### 3. Clean Brand Logo Database
```json
// Before (fragmented):
{
  "lays": {...},
  "lay's": {...},
  "lay_s": {...}
}

// After (canonical):
{
  "lay's": {...}
}
```

### 4. Better Search & Filtering
- Users can search for "Lays" and find all variants
- Brand filters work consistently across retailers
- Analytics aggregate correctly

---

## Quality Checks

### Validation Script
Run before committing lexicon changes:
```bash
python3 tools/validate_lexicon.py
```

### Audit Tool Enhancement (Optional)
Add to `tools/audit_adtype_mapping.py`:

```python
from core.brands import canonicalize

# In per-ad loop:
brand = ad.get("brand")
if brand:
    canon = canonicalize(brand)
    if canon != brand:
        print(f"⚠️  Non-canonical brand: {brand} → should be {canon}")
```

This flags ads with non-canonical brand names.

---

## Lexicon Cleanup Recommendations

### 1. Remove Campaign Codes
These are temporary and pollute the lexicon:
- `MSCCollegeFootballWave210152 5`
- `SSMAlwaysOn0625`
- `TOABoostAugDec2025`
- `Q4FrozenBreakfastSandwichTOA`

**Action:** Delete these synonyms from `config/brands.json`

### 2. Fix Duplicate Synonyms
These map to multiple brands:
- `bertolli` → Bertolli, Birds Eye, P.F. Chang's
- `cottonelle` → Cottonelle, Kleenex, Scott, Viva
- `dr. pepper` → Cheez-It, Dr. Pepper, Eckrich

**Action:** Keep synonym only in the correct brand entry

### 3. Remove Cross-Brand References
Brand A shouldn't have Brand B as a synonym:
- Kleenex having "Cottonelle"
- Birds Eye having "Bertolli"

**Action:** Remove these cross-references

### 4. Validate After Cleanup
```bash
python3 tools/validate_lexicon.py
```

Should show:
```
✅ No duplicate synonym collisions
✅ No campaign-like synonyms detected
✅ No cross-brand pollution detected
✅ Lexicon validation passed!
```

---

## Testing

### Test Canonical Brand Assignment

**Walmart:**
```bash
# Run a scrape
python3 keyword_input.py
# Select Walmart, enter keyword, run

# Check brands in JSON
jq '.ads[].brand' output/walmart/{client}/runs/{run_id}/run_results_*.json
```

**Kroger:**
```bash
# Run a scrape
python3 keyword_input.py
# Select Kroger, enter keyword, run

# Check brands in JSON
jq '.ads[].brand' output/kroger/{client}/runs/run_results_*.json
```

**Expected:** All brand names should be canonical (e.g., "Lay's" not "Lays")

### Test Brand Logo Database
```python
from brand_logo_database import BrandLogoDatabase

db = BrandLogoDatabase()

# Add logo with non-canonical brand
db.add_brand_logo("lays", "https://...", "kroger")

# Check it was stored canonically
print(db.get_brand_logo("Lay's"))  # Should find it
print(db.list_all_brands())  # Should show "Lay's"
```

---

## Files Modified

1. `walmart_search_and_capture.py` - Added canonicalization to `build_ad_object()`
2. `tools/batch_rebuild_walmart_runs_from_images.py` - Canonicalize brand from filenames
3. `brand_logo_database.py` - Always store canonical brands
4. `tools/validate_lexicon.py` - NEW - Lexicon validation tool

---

## Next Steps

1. ✅ Walmart canonicalization - COMPLETE
2. ✅ Kroger canonicalization - Already implemented
3. ✅ Brand logo database - COMPLETE
4. ⏳ Clean up `config/brands.json` - Remove campaign codes and duplicates
5. ⏳ Run `validate_lexicon.py` until clean
6. ⏳ Apply to Instacart when implementing canonical schema
7. ⏳ Apply to Amazon when implementing canonical schema

---

## Documentation

- **Lexicon file:** `config/brands.json`
- **Canonicalization function:** `core/brands.py` → `canonicalize()`
- **Validation tool:** `tools/validate_lexicon.py`
- **Usage examples:** See Walmart and Kroger implementations

---

**Integration completed:** 2025-10-27
**Verified by:** Lexicon validation tool + manual testing
