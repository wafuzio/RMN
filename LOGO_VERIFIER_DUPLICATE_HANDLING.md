# Logo Verifier - Duplicate Logo Handling

## Problem Fixed

Previously, when the logo verifier encountered files with version suffixes like `aquasonic_2.png`, `bodyarmor_2.png`, etc., it would create brand entries with names like "Aquasonic 2", "Bodyarmor 2" in the database. This was incorrect behavior.

## New Behavior

### 1. **Automatic Version Suffix Stripping**

When processing logo files, the verifier now:
- Detects version suffixes: `_2`, `_3`, `_v2`, `_v3`, etc.
- Strips these suffixes from the brand name
- Maintains the original brand name (e.g., "Aquasonic" instead of "Aquasonic 2")

**Example:**
- File: `aquasonic_2.png`
- Old behavior: Brand name = "Aquasonic 2" ❌
- New behavior: Brand name = "Aquasonic" ✅

### 2. **Integration with Brand Name Verifier**

When a duplicate logo is detected (file has version suffix):

1. Logo is kept with the correct brand name
2. Console message directs you to use the **Brand Name Verifier** tool
3. Brand Name Verifier has built-in logo comparison with side-by-side preview
4. You can merge brands and choose which logo to keep

### 3. **Visual Indicators in GUI**

The logo verifier GUI now shows:
- **🔄 icon** for duplicate logos
- **[DUPLICATE - needs comparison]** status in progress bar
- Original filename displayed: `(from: aquasonic_2.png)`

## Workflow

### Step 1: Logo Verifier

1. **Run logo verifier as normal**:
   ```bash
   .venv/bin/python3 tools/logo_verifier_gui.py
   ```

2. **When you see a duplicate logo** (🔄 icon):
   - Press **Y** to keep it (uses correct brand name automatically)
   - Console shows: "⚠️ DUPLICATE LOGO: [Brand Name]"
   - Continue reviewing remaining logos

### Step 2: Brand Name Verifier (Logo Comparison)

3. **Run Brand Name Verifier** to compare and merge:
   ```bash
   .venv/bin/python3 tools/brand_name_verifier.py
   ```

4. **Find the duplicate brand** in the list
   - Look for brands with similar names (e.g., "Malk" and "Malk Organics")
   - Click "Similar Brands" to see matches

5. **Merge the brands**:
   - Select the duplicate brand
   - Click "Merge" or press **M**
   - Choose which brand name to keep
   - **Logo comparison dialog appears automatically**
   - Side-by-side preview of both logos
   - Click "Use This Logo" under the better quality logo
   - Merge completes - keeps better logo, deletes the other

## Logo Comparison Features (Brand Name Verifier)

The Brand Name Verifier's logo merge dialog shows:
- **Side-by-side preview** of both logos
- **Source brand** (left) vs **Target brand** (right)
- **"Use This Logo"** buttons under each preview
- **"Skip Logo Merge"** - keep both logos separate
- **"Cancel Merge"** - abort the entire merge operation

Quality factors to consider:
- Resolution (higher is better)
- Transparency (RGBA preferred over white background)
- Aspect ratio (square or reasonable ratio)
- Brand accuracy (correct logo version)

## Code Changes

### Files Modified

**`tools/logo_verifier_gui.py`**:
- Added version suffix detection and stripping (lines 234-244)
- Added duplicate flag to brand data (line 254)
- Updated UI to show duplicate status (lines 428-452)
- Added console notification directing to Brand Name Verifier (lines 596-610)

### Pattern Matching

Version suffixes detected:
- `_2`, `_3`, `_4`, etc. (any trailing underscore + digit)
- `_v2`, `_v3`, `_v4`, etc. (underscore + v + digit)

Regex patterns used:
```python
stem_clean = re.sub(r'_\d+$', '', stem)      # Remove _2, _3, etc.
stem_clean = re.sub(r'_v\d+$', '', stem_clean)  # Remove _v2, _v3, etc.
```

## Benefits

1. **No more "[Brand] 2" entries** in the database
2. **Automatic duplicate detection** - no manual checking needed
3. **Uses existing Brand Name Verifier tool** - no separate queue to manage
4. **Side-by-side logo comparison** already built into merge workflow
5. **Clear visual indicators** in both tools
6. **Preserves both logos** until you choose which to keep

## Example Session

### Logo Verifier
```
→ Running logo verifier...

📊 Found 47 logos to verify
   From database: 34 unverified entries
   New files: 13 (will be added to database)
   Skipped: 156 already verified, 0 missing files

Logo 1 of 47 [NEW] [DUPLICATE - needs comparison]
🔄 Aquasonic (from: aquasonic_2.png)

Press Y to keep...
➕ Added new brand to database: aquasonic
⚠️  DUPLICATE LOGO: Aquasonic
   Use Brand Name Verifier tool to compare and merge logos
   Command: .venv/bin/python3 tools/brand_name_verifier.py
📁 Moved unverified/aquasonic_2.png -> verified/aquasonic_2.png

[Continue with remaining logos...]
```

### Brand Name Verifier
```
→ Running brand name verifier...

Brand 3 of 91
Aquasonic

Similar Brands (click to merge):
1. ✓ Aquasonic (85%)

Press M to merge...

[Logo Merge Dialog appears]
Choose which logo to keep for the merged brand:

From: Aquasonic          To: Aquasonic
[Logo preview]           [Logo preview]
[Use This Logo]          [Use This Logo]

[Click on better logo]
✓ Merged logos - kept better quality version
```

## Troubleshooting

### Issue: Duplicate still created with " 2" name

**Cause**: Old database entries may still exist with " 2" names from before this fix.

**Fix**: 
1. Edit `output/brand_logos/brand_logo_database.json`
2. Find entries with " 2" in brand_name
3. Remove the " 2" suffix
4. Update the key to match (remove `_2` from key)
5. Save and re-run verifier

### Issue: Can't find duplicate brand in Brand Name Verifier

**Cause**: Brand might not be in lexicon yet, or names don't match exactly.

**Fix**: 
1. Check `config/brands.json` for the brand
2. Use the search feature in Brand Name Verifier
3. Look for similar brand names (fuzzy matching)
4. If needed, add brand to lexicon first

### Issue: Both logos look the same

**Cause**: Might be identical logos with different filenames.

**Fix**: 
1. Choose either one (doesn't matter)
2. Or click "Skip Logo Merge" to keep both temporarily
3. Delete the duplicate file manually later
