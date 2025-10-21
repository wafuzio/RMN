# Artifact Taxonomy and Directory Structure

**Purpose:** Defines standardized folder structure, file naming, and JSON schema for all retailers.

## Overview

Each retailer has a specific set of allowed subdirectories based on their ad types. This prevents cross-contamination (e.g., Kroger folders appearing in Walmart directories).

**Key Principle:** All retailers follow the same patterns, but with retailer-specific ad type folders.

## Brand Logos

Brand logos are stored in a centralized database for reuse across all retailers:

```
output/brand_logos/
├── brand_logo_database.json    # Metadata database
├── boiron.png                  # Clean, numbered filenames
├── stonyfield_organic.png
├── sour_patch_kids.jpg
└── nestle_2.png                # Multiple logos numbered sequentially
```

**Features:**
- **Content-based deduplication**: Identical images from different URLs share one file
- **Clean naming**: `brand_name.ext` or `brand_name_2.ext` (no hashes)
- **Database tracking**: JSON tracks URLs, retailers, first/last seen dates
- **Automatic enrichment**: Logo paths added to ad JSON via `brand_logo` field

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
├── Shoppable_Recipe_Ads/     # Recipe ads with product links
├── Display_Ads/              # Generic display ads
├── Main/                     # Main search results
└── runs/                     # Run artifacts (JSON, HTML)
```

### Amazon
```
output/amazon/<client>/
├── Sponsored_Brand/        # Sponsored Brand ads (top banner)
├── Sponsored_Product/      # Sponsored Product listings
├── Sponsored_Display/      # Display ads
├── Main/                   # Main search results
└── runs/                   # Run artifacts (JSON, HTML)
```
**TODO:** Verify actual Amazon ad type names and update accordingly

### Walmart
```
output/walmart/<client>/
├── Top_Banner/       # Top banner ads
├── SBA/              # Sponsored Brand Ads
├── Tile_Takeover/    # Tile takeover ads
├── SBV/              # Sponsored Brand Video
├── Main/             # Main search results
└── runs/             # Run artifacts (JSON, HTML)
```

---

## Standardized Filename Format

All image files follow this pattern:
```
<retailer>__<advertiser>__<ad_type>__<client>__<search_term>__D<YYYY-MM-DD>_T<HH-MM.SS>_<index>.<ext>
```

**Examples:**
```
kroger__unilever__skyscraper__blue_bunny__ice_cream_cones__D2025-10-09_T08-56.21_1.png
walmart__popsicle__sba__taxonomy_test__ice_pop__D2025-10-12_T12-34.56_1.png
instacart__nestle__shoppable_display_ad__bomb_pop__ice_pop__D2025-10-12_T14-22.33_1.png
```

**Rules:**
- Double underscores (`__`) separate major fields
- Single underscores (`_`) within field values
- All lowercase, special chars replaced with underscores
- Date format: `D<YYYY-MM-DD>` with dashes
- Time format: `T<HH-MM.SS>` with dashes and dot


## JSON Schema Standardization

**STATUS: PARTIALLY COMPLETE - ONGOING WORK**

### Problem
Each retailer outputs different JSON structures, requiring retailer-specific code in the API and frontend. Many retailers now follow the standard schema, but some legacy formats and retailer-specific fields remain.

### Target Standard Schema
```json
{
  "retailer": "kroger|walmart|instacart|amazon",
  "keyword": "search term",
  "timestamp": "2025-10-13T22:07:10",
  "run_id": "20251013220710",
  "ads": [
    {
      "id": "unique-ad-id",
      "type": "TOA|Skyscraper|CuratedCarousel|SBA|SBV|TileTakeover",
      "brand": "Brand Name",
      "brand_logo": "brand_logos/brand_name.png",
      "title": "Ad Title",
      "description": "Ad Description",
      "cta": "Call to Action",
      "href": "https://...",
      "image_url": "https://cdn.../original.jpg",
      "image_path": "Shoppable_Display_Ads/instacart__brand__shoppable_display_ad__client__keyword__D2025-10-20_T10-45.43_1.png",
      "screenshot": "Shoppable_Display_Ads/instacart__brand__shoppable_display_ad__client__keyword__D2025-10-20_T10-45.43_1.png",
      "products": [],
      "metadata": {}
    }
  ]
}
```

**Standard Fields:**
- `image_path`: Path to saved screenshot (in ad-type folder, not `runs/`)
- `screenshot`: Alias for `image_path` (some retailers use this)
- `brand_logo`: Relative path to brand logo file (automatically enriched from database)
- `timestamp`: ISO 8601 format with `T` separator (e.g., `2025-10-20T10:45:43`)

### Current Status by Retailer

**Kroger** (`kroger_search_and_capture.py`):
- ✅ Uses flat `ads[]` array
- ⚠️ Has multiple path fields (`carousel_image_path`, `skyscraper_image_path`) - needs consolidation
- ⚠️ Timestamp format needs ISO 8601 check

**Walmart** (`walmart_search_and_capture.py`):
- ✅ Outputs JSON with ad data
- ✅ Saves images to ad-type folders
- ⚠️ May have diagnostic fields that should be separated

**Instacart** (`instacart_search_and_capture.py`):
- ✅ Uses `screenshot` field for image path
- ✅ ISO 8601 timestamp format
- ✅ Saves images to ad-type folders
- ✅ Includes `brand_logo` enrichment
- ⚠️ Uses nested `results[].ads[]` structure - should be flat `ads[]`

**API** (`builder_server_v2.py`):
- ⚠️ Still has some retailer-specific code paths
- ⚠️ Checks multiple image path fields (`image_path`, `screenshot`, etc.)

### Implementation Checklist

When updating a scraper:
- [ ] Output flat `ads[]` array (not nested in `results[]`)
- [ ] Use single `image_path` field (not multiple path fields)
- [ ] Ensure `timestamp` is ISO 8601 format (`YYYY-MM-DDTHH:MM:SS`)
- [ ] Include `retailer`, `keyword`, `run_id` at top level
- [ ] Save images to ad-type folders (not `runs/`)
- [ ] Follow standardized filename format
- [ ] Test that images display in GUI

---

## Quick Reference

**Allowed Folders:**
- Kroger: `TOA`, `Skyscraper`, `Carousel`, `Display_Ads`, `Main`, `runs`
- Walmart: `Top_Banner`, `SBA`, `Tile_Takeover`, `SBV`, `Main`, `runs`
- Instacart: `Shoppable_Display_Ads`, `Shoppable_Video_Ads`, `Shoppable_Recipe_Ads`, `Display_Ads`, `Main`, `runs`
- Amazon: `Sponsored_Brand`, `Sponsored_Product`, `Sponsored_Display`, `Main`, `runs` (TODO: verify)
- Global: `brand_logos/` (centralized brand logo database)

**File Naming:** `retailer__advertiser__ad_type__client__search_term__DYYYY-MM-DD_THH-MM.SS_index.ext`

**JSON Schema:** See "JSON Schema Standardization" section above

**Key Files:**
- `utils/path_taxonomy.py` - Defines allowed folders per retailer
- `filename_utils.py` - Generates standardized filenames
- `brand_logo_database.py` - Manages centralized brand logo database
- `scripts/deduplicate_brand_logos.py` - Cleanup utility for existing logos
- `docs/RETAILER_ONBOARDING_CHECKLIST.md` - Full onboarding guide
