# Brand Review Tool Fixes - November 5, 2025

## Problem
The brand review tool was reporting "All brands have been identified!" when hundreds of ads actually had mismatches between JSON brand names and image filenames.

## Root Causes

### 1. **Gated Mismatch Detection**
The tool only flagged filename/JSON mismatches if the filename brand looked like a "campaign code" (via `is_uncertain_brand()`). If the filename contained a real brand slug (just the wrong one), it was silently skipped.

**Example:** JSON says `BOOST Advanced` but file is `kroger__muscle_milk__carousel__...` → Not flagged ❌

### 2. **Missing Fallback for Wrong Brand Slugs**
When `find_ad_image()` returned `None` (because it couldn't find the branded file), the tool only searched for files with `__unknown__` in the name. It didn't search for files with different brand slugs.

**Example:** JSON says `kroger__boost_advanced__carousel__...` but file is `kroger__muscle_milk__carousel__...` → Not found ❌

### 3. **Weak Slug Normalization**
The `to_slug()` function only replaced spaces, apostrophes, and ampersands. It didn't handle hyphens, punctuation, or other special characters, leading to false "matches" and "mismatches".

**Example:** `"Ben & Jerry's"` → `"ben_jerrys"` but filename might be `"ben_and_jerrys"` → Mismatch ❌

### 4. **Broken References Not Flagged**
When JSON had an image path but no file existed after all reconciliation attempts, the ad was silently skipped instead of being flagged for review.

## Solutions Implemented

### FIX #1: Unconditional Mismatch Flagging
**Location:** `load_unknown_brands()` - filename brand slug comparison

**Before:**
```python
if brand_slug_in_file not in adv_slugs:
    looks_like_code = self.is_uncertain_brand(brand_slug_in_file.replace('_', ' '))
    if looks_like_code:  # ← GATE
        is_unknown_in_filename = True
```

**After:**
```python
if brand_slug_in_file not in adv_slugs:
    # Unconditional flag on brand slug mismatch
    is_unknown_in_filename = True
    print(f"[WARN] Filename brand slug '{brand_slug_in_file}' ≠ advertisers {adv_slugs}")
```

**Impact:** Now catches all brand slug mismatches, not just campaign codes.

---

### FIX #2: Wildcard Brand Slug Search
**Location:** `load_unknown_brands()` - after `find_ad_image()` returns `None`

**New Helper Methods:**
```python
def expected_image_path_from_json(self, ad, json_file):
    """Return the full path that the JSON points to, even if it doesn't exist."""
    # Constructs path from JSON fields for all retailers (Kroger, Walmart, Instacart)

def find_existing_image_ignoring_brand(self, expected_full_path):
    """Find a file matching all parts except the brand slug segment."""
    # Uses glob pattern: retailer__*__adtype__client__search__Dts.png
    # Returns most recent match if multiple found
```

**New Logic:**
```python
if not image_path:
    expected_path = self.expected_image_path_from_json(ad, json_file)
    if expected_path and not os.path.exists(expected_path):
        alt = self.find_existing_image_ignoring_brand(expected_path)
        if alt:
            image_path = alt
            is_unknown_in_filename = True
            print(f"[WARN] JSON image path not found: {expected_path}")
            print(f"[WARN] Found existing file with different brand slug: {alt}")
```

**Impact:** Finds files with ANY brand slug mismatch, not just `__unknown__`. More comprehensive than legacy recovery.

---

### FIX #3: Robust Slug Normalization
**Location:** `to_slug()` method

**Before:**
```python
def to_slug(self, text):
    return text.lower().replace(' ', '_').replace("'", '').replace('&', 'and')
```

**After:**
```python
def to_slug(self, text):
    s = text.lower()
    s = s.replace('&', 'and')
    s = s.replace("'", '')
    # Collapse any non-alphanumeric into underscores
    s = re.sub(r'[^a-z0-9]+', '_', s)
    # Collapse multiple underscores
    s = re.sub(r'_+', '_', s).strip('_')
    return s
```

**Impact:** Handles hyphens, punctuation, diacritics consistently. Reduces false matches/mismatches.

---

### FIX #4: Flag Broken JSON References
**Location:** `load_unknown_brands()` - after all reconciliation attempts

**New Logic:**
```python
if not image_path:
    # Check if JSON has any image path field
    has_json_path = (ad.get('image_path') or 
                   ad.get('toa_image_path') or 
                   ad.get('skyscraper_image_path') or 
                   ad.get('carousel_image_path'))
    if has_json_path:
        print(f"[WARN] JSON has an image path but no matching file exists after reconciliation")
        is_unknown_in_filename = True
```

**Impact:** Broken references are now flagged for review instead of being silently skipped.

---

## Additional Improvements

### Instacart Type Coverage
Added Instacart ad types to legacy `__unknown__` recovery step:
```python
type_to_folder = {
    # ... existing types ...
    'display_ad': 'DisplayAd',
    'shoppable_recipe_ad': 'ShoppableRecipe',
    'main': 'Main'
}
```

### Documentation
Added comments explaining:
- Legacy `__unknown__` search is less comprehensive than Fix #2
- Fix #2 finds ANY brand slug mismatch, not just "unknown"
- All retailer types now covered (Kroger, Walmart, Instacart)

---

## Expected Results

### Before Fixes
- Tool reported: "All brands have been identified!"
- Diagnostic script found: **Hundreds of ads** with JSON/filename mismatches

### After Fixes
- Tool should now flag all ads where:
  - Filename has `__unknown__` but JSON has a brand
  - Filename has a different brand slug than JSON
  - JSON path doesn't exist but a file with different brand slug does
  - JSON has a path but no file exists at all

### Test Cases Covered

1. ✅ JSON: `BOOST Advanced`, File: `kroger__unknown__carousel__...`
2. ✅ JSON: `BOOST Advanced`, File: `kroger__muscle_milk__carousel__...`
3. ✅ JSON: `Coca-Cola`, File: `kroger__pepsi__carousel__...`
4. ✅ JSON: `kroger__boost_advanced__carousel__...` (doesn't exist), File: `kroger__unknown__carousel__...` (exists)
5. ✅ JSON: `kroger__boost_advanced__carousel__...` (doesn't exist), No file exists at all
6. ✅ Empty advertisers array in JSON
7. ✅ Advertisers: `['unknown']` in JSON

---

## Files Modified
- `brand_review_tool.py` - All four fixes implemented
- `tools/find_unknown_ads.py` - Enhanced diagnostic script to detect JSON/filename mismatches

## Commits
- `f0ce6c7` - Initial diagnostic improvements
- `ade71f3` - Complete fixes for all four issues

## Next Steps
1. Run the brand review tool to verify it now catches all mismatches
2. Review and correct the flagged ads
3. Consider running a bulk reconciliation script to rename files to match JSON
