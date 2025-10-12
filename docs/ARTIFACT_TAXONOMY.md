# Artifact Taxonomy and Directory Hygiene

This document defines the folder structure for each retailer and explains how to prevent "directory gore" (cross-retailer folder contamination).

## Problem Statement

**Before taxonomy enforcement:**
```
output/instacart/cheese_dip/
├── TOA/              ❌ Kroger folder in Instacart directory
├── Skyscraper/       ❌ Kroger folder in Instacart directory
├── Carousel/         ❌ Kroger folder in Instacart directory
├── Display_Ads/      ✅ Valid for Instacart
└── runs/             ✅ Valid for all retailers
```

**Root cause:** `core/paths.py` hardcoded Kroger folders for ALL retailers.

## Solution: Retailer-Specific Taxonomy

### Taxonomy Definition (`utils/path_taxonomy.py`)

```python
RETAILER_SUBDIRS = {
    "kroger": ["TOA", "Skyscraper", "Carousel", "Display_Ads", "Main", "runs"],
    "instacart": ["Shoppable_Display_Ads", "Shoppable_Video_Ads", "Display_Ads", "Main", "runs"],
    "amazon": ["TOA", "Skyscraper", "Carousel", "Main", "runs"],
    "walmart": ["Top_Banner", "SBA", "Tile_Takeover", "SBV", "Main", "runs"],
}

def allowed_subdirs(retailer: str) -> list[str]:
    """Returns list of allowed subdirectories for a retailer."""
    return RETAILER_SUBDIRS.get(retailer.lower(), ["Main", "runs"])
```

### Enforced in `core/paths.py`

```python
from utils.path_taxonomy import allowed_subdirs

def output_dir_for(base: str, retailer: str, client: str) -> str:
    """
    Create output directory with retailer-specific folder taxonomy.
    Only creates folders that are allowed for the specific retailer.
    """
    d = os.path.join(base, "output", retailer, client)
    ensure_dir(d)
    
    # Create only the folders allowed for this retailer
    for leaf in allowed_subdirs(retailer):
        ensure_dir(os.path.join(d, leaf))
    
    return d
```

## Retailer Taxonomy Reference

### Kroger
```
output/kroger/<client>/
├── TOA/              # Top of Ad (banner ads)
├── Skyscraper/       # Vertical sidebar ads
├── Carousel/         # Product carousels
├── Display_Ads/      # Generic display ads
├── Main/             # Main search results
└── runs/             # Run artifacts (JSON, HTML)
```

### Instacart
```
output/instacart/<client>/
├── Shoppable_Display_Ads/    # Display ads with product links
├── Shoppable_Video_Ads/      # Video ads with product links
├── Display_Ads/              # Generic display ads
├── Main/                     # Main search results
└── runs/                     # Run artifacts (JSON, HTML)
```

**⚠️ CURRENT ISSUE:** Instacart JSON structure doesn't match other retailers:
- Uses `title` field instead of `brand`
- Missing `image_path` fields - images are saved but not referenced in JSON
- API workaround: Flask API now maps `title` → `brand` for compatibility
- **TODO:** Update Instacart scraper to add image path references to JSON

### Amazon
```
output/amazon/<client>/
├── TOA/              # Top of Ad (banner ads)
├── Skyscraper/       # Vertical sidebar ads
├── Carousel/         # Product carousels
├── Main/             # Main search results
└── runs/             # Run artifacts (JSON, HTML)
```

### Walmart
```
output/walmart/<client>/
├── Top_Banner/       # Top banner ads (a.ad, a.adctr)
├── SBA/              # Sponsored Brand Ads ([data-testid="sba-container"])
├── Tile_Takeover/    # Tile takeover ads ([data-testid="tile-take-over"])
├── SBV/              # Sponsored Brand Video ([data-testid="search-video-in-grid"])
├── Main/             # Main search results
└── runs/             # Run artifacts (JSON, HTML)
```

**✅ RESOLVED:** Walmart scraper now correctly saves images to ad-type folders (Top_Banner/, SBA/, SBV/, Tile_Takeover/) with standardized naming. Only JSON/HTML/logs remain in runs/.

### Default (New Retailers)
```
output/<retailer>/<client>/
├── Main/             # Main search results
└── runs/             # Run artifacts (JSON, HTML)
```

## Adding a New Retailer

### 1. Define Taxonomy

Edit `utils/path_taxonomy.py`:
```python
RETAILER_SUBDIRS = {
    # ... existing retailers ...
    "target": ["Display_Ads", "Sponsored_Products", "Main", "runs"],
}
```

### 2. Use in Code

```python
from core.paths import output_dir_for

# This will create only Target-allowed folders
output_dir = output_dir_for(base=".", retailer="target", client="test_client")
```

### 3. Verify

```bash
tree output/target/test_client/
# Should show only: Display_Ads/, Sponsored_Products/, Main/, runs/
```

## Cleanup Script

### Remove Disallowed Folders

`scripts/maintenance/cleanup_taxonomy.py` removes folders that shouldn't exist:

```python
def cleanup_retailer_directories(retailer: str, base_dir: str = "output"):
    """Remove disallowed folders from existing client directories."""
    retailer_dir = os.path.join(base_dir, retailer)
    if not os.path.isdir(retailer_dir):
        return
    
    allowed = set(allowed_subdirs(retailer))
    
    for client_dir in os.listdir(retailer_dir):
        client_path = os.path.join(retailer_dir, client_dir)
        if not os.path.isdir(client_path):
            continue
        
        for item in os.listdir(client_path):
            item_path = os.path.join(client_path, item)
            if os.path.isdir(item_path) and item not in allowed:
                print(f"Removing disallowed folder: {item_path}")
                shutil.rmtree(item_path)
```

### Usage

```bash
# Clean all retailers
python3 scripts/maintenance/cleanup_taxonomy.py

# Clean specific retailer
python3 -c "
from scripts.maintenance.cleanup_taxonomy import cleanup_retailer_directories
cleanup_retailer_directories('instacart')
"
```

## Validation

### Pre-Commit Check

Add to your workflow:
```bash
# Check for invalid folders
python3 -c "
from utils.path_taxonomy import allowed_subdirs
import os

for retailer in ['kroger', 'instacart', 'amazon', 'walmart']:
    retailer_dir = f'output/{retailer}'
    if not os.path.isdir(retailer_dir):
        continue
    
    allowed = set(allowed_subdirs(retailer))
    
    for client in os.listdir(retailer_dir):
        client_path = os.path.join(retailer_dir, client)
        if not os.path.isdir(client_path):
            continue
        
        for folder in os.listdir(client_path):
            folder_path = os.path.join(client_path, folder)
            if os.path.isdir(folder_path) and folder not in allowed:
                print(f'❌ Invalid folder: {folder_path}')
                exit(1)

print('✅ All folders valid')
"
```

### CI Check

Add to GitHub Actions:
```yaml
- name: Validate artifact taxonomy
  run: |
    python3 scripts/maintenance/cleanup_taxonomy.py --dry-run --strict
```

## Common Mistakes

### ❌ Hardcoding Folder Names
```python
# Wrong
os.makedirs(os.path.join(output_dir, "TOA"), exist_ok=True)
os.makedirs(os.path.join(output_dir, "Skyscraper"), exist_ok=True)
```

### ✅ Using Taxonomy System
```python
# Correct
from core.paths import output_dir_for
output_dir = output_dir_for(base, retailer, client)
# Folders already created based on retailer
```

### ❌ Creating Folders Manually
```python
# Wrong
for folder in ["TOA", "Skyscraper", "Carousel"]:
    os.makedirs(os.path.join(output_dir, folder), exist_ok=True)
```

### ✅ Letting paths.py Handle It
```python
# Correct
output_dir = output_dir_for(base, retailer, client)
# Done! Correct folders exist
```

## Migration Guide

### Cleaning Existing Directories

1. **Backup first:**
   ```bash
   tar -czf output_backup_$(date +%Y%m%d).tar.gz output/
   ```

2. **Run cleanup:**
   ```bash
   python3 scripts/maintenance/cleanup_taxonomy.py
   ```

3. **Verify:**
   ```bash
   tree output/ -L 3
   ```

4. **Check for issues:**
   ```bash
   git status output/
   # Should show deleted folders only
   ```

### Updating Existing Code

1. **Find hardcoded folder creation:**
   ```bash
   grep -r "makedirs.*TOA" .
   grep -r "makedirs.*Skyscraper" .
   ```

2. **Replace with:**
   ```python
   from core.paths import output_dir_for
   output_dir = output_dir_for(base, retailer, client)
   ```

3. **Remove manual folder creation**

## Testing

### Unit Test Example

```python
def test_taxonomy_enforcement():
    """Test that only allowed folders are created."""
    import tempfile
    import shutil
    from core.paths import output_dir_for
    from utils.path_taxonomy import allowed_subdirs
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create output directory for Instacart
        output_dir = output_dir_for(tmpdir, "instacart", "test_client")
        
        # Check created folders
        created = set(os.listdir(output_dir))
        allowed = set(allowed_subdirs("instacart"))
        
        assert created == allowed, f"Created {created}, expected {allowed}"
        
        # Verify Kroger folders NOT created
        assert "TOA" not in created
        assert "Skyscraper" not in created
        assert "Carousel" not in created
```

---

## Known Issues & Workarounds

### Issue 1: Walmart Images in runs/ Directory ✅ RESOLVED

**Status:** Fixed as of 2025-10-12

**Solution Implemented:**
- Updated `walmart_search_and_capture.py` to extract client name and root from run directory path
- Modified `_capture_elements()` to accept `client_name`, `client_root`, and `timestamp` parameters
- Images now saved directly to ad-type folders (SBA/, SBV/, Tile_Takeover/, Top_Banner/)
- Standardized filename format: `walmart__<ad_type>__<client>__<search_term>__D<YYYY-MM-DD>_T<HH-MM.SS>_<index>.<ext>`
- Only JSON/HTML/logs remain in runs/ directory

**Current Structure:**
```
SBA/walmart__sba__client_name__search_term__D2025-10-12_T12-34.56_1.png
SBV/walmart__sbv__client_name__search_term__D2025-10-12_T12-35.01_1.png
SBV/walmart__sbv__client_name__search_term__D2025-10-12_T12-35.01_1.mp4
Tile_Takeover/walmart__tile_takeover__client_name__search_term__D2025-10-12_T12-34.58_1.png
Top_Banner/walmart__top_banner__client_name__search_term__D2025-10-12_T12-34.57_1.png
runs/20251012123456/
├── run_results_*.json
├── run_report.json
├── run_report.md
└── search_results_*.html
```

---

### Issue 2: Instacart Missing Image Paths in JSON

**Problem:** Instacart JSON doesn't reference saved images:
```json
{
  "type": "Shoppable Display Ad",
  "title": "Applegate Breakfast Favorites",
  "selector": "div.e-1qzz7bi",
  "id": "0199cfb9-116c-7219-ac43-e90ad4342dcb"
  // ❌ No image_path field
}
```

Images exist: `Shoppable_Display_Ads/ShoppableDisplayAd_packaged_deli_meat_20251010_150339_1.png`

**Expected:**
```json
{
  "type": "Shoppable Display Ad",
  "title": "Applegate Breakfast Favorites",
  "image_path": "Shoppable_Display_Ads/ShoppableDisplayAd_packaged_deli_meat_20251010_150339_1.png"
}
```

**Root Cause:** Instacart scraper saves images but doesn't update JSON with paths.

**Fix Required:** Update Instacart scraper to:
1. Add `image_path` field to JSON when images are saved
2. Optionally: Add `brand` field (currently uses `title`)

**Workaround:** Flask API maps `title` → `brand` for compatibility.

---

### Issue 3: Kroger Missing Image Paths for Some Ads

**Problem:** Kroger JSON has UUID-based paths that don't match actual saved files:
```json
{
  "type": "Skyscraper",
  "image_url": "https://www.kroger.com/.../beb69322-77c6-4d0c-b131-a7f6390328c6.jpg",
  "skyscraper_image_path": "output/runs/Skyscraper/skyscraper_beb69322-..._ice_cream_cones_2025-10-09_08-56-54.jpg"
}
```

Actual file: `Skyscraper/skyscraper_ice_cream_cones_2025-10-09_08-56-21_1.png`

**Root Cause:** Path in JSON is outdated or incorrect.

**Workaround:** Flask API uses fuzzy matching by ad type to find images.

---

## Compliance Checklist

When adding or updating a scraper, ensure:

- [ ] Uses `core.paths.output_dir_for()` to get base directory
- [ ] Saves images to ad-type-specific folders (not runs/)
- [ ] Updates JSON with correct `image_path` references
- [ ] Uses `brand` field (not retailer-specific field names)
- [ ] Saves only JSON/HTML/logs to runs/ directory
- [ ] Follows naming convention: `<retailer>__<advertiser>__<ad_type>__<client>__<search_term>__D<YYYY-MM-DD>_T<HH-MM.SS>_<index>.<ext>`
- [ ] Tests with `utils.path_taxonomy.allowed_subdirs()` to verify folders

---

**Last Updated:** 2025-10-12

## Standardized Filename Format

All retailers now use a consistent filename format:

```
<retailer>__<advertiser>__<ad_type>__<client>__<search_term>__D<YYYY-MM-DD>_T<HH-MM.SS>_<index>.<ext>
```

**Components:**
- `<retailer>`: kroger, walmart, instacart, amazon
- `<advertiser>`: advertiser/brand name (e.g., popsicle, unilever) - extracted from ad
- `<ad_type>`: sba, sbv, skyscraper, toa, carousel, tile_takeover, etc.
- `<client>`: client name (e.g., blue_bunny, taxonomy_test)
- `<search_term>`: sanitized search keyword (e.g., ice_cream_cones)
- `D<YYYY-MM-DD>`: date with dashes (e.g., D2025-10-12)
- `T<HH-MM.SS>`: time with dashes and dot (e.g., T12-34.56)
- `<index>`: 1, 2, 3, etc.
- `<ext>`: png, jpg, mp4

**Examples:**
```
kroger__unilever__skyscraper__blue_bunny__ice_cream_cones__D2025-10-09_T08-56.21_1.png
walmart__popsicle__sba__taxonomy_test__ice_pop__D2025-10-12_T12-34.56_1.png
instacart__nestle__shoppable_display_ad__bomb_pop__ice_pop__D2025-10-12_T14-22.33_1.png
```

**Implementation:**
- Utility: `filename_utils.py` - `generate_ad_filename()` function
- Double underscores (`__`) separate major fields
- Single underscores (`_`) within field values
- All components sanitized (lowercase, special chars replaced)

## References

- `filename_utils.py` - Standardized filename generation
- `utils/path_taxonomy.py` - Taxonomy definitions
- `core/paths.py` - Path creation with enforcement
- `scripts/maintenance/cleanup_taxonomy.py` - Cleanup tool
- `docs/RETAILER_ONBOARDING_CHECKLIST.md` - Section 1 (Output and taxonomy)
