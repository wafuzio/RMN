# Artifact Taxonomy and Directory Structure

**Purpose:** Defines standardized folder structure, file naming, and JSON schema for all retailers.

## Overview

Each retailer has a specific set of allowed subdirectories based on their ad types. This prevents cross-contamination (e.g., Kroger folders appearing in Walmart directories).

**Key Principle:** All retailers follow the same patterns, but with retailer-specific ad type folders.

## Brand Logos

Brand logos are stored in a centralized database at project root for reuse across all retailers:

```
brand_logos/                    # At project root (sibling to output/)
├── brand_logo_database.json    # Metadata database
├── boiron.png                  # Clean, numbered filenames
├── stonyfield_organic.png
├── sour_patch_kids.jpg
└── nestle_2.png                # Multiple logos numbered sequentially
```

**Features:**
- **Content-based deduplication**: MD5 hash of image bytes (not URL) - identical images share one file
- **Clean naming**: `brand_name.ext` or `brand_name_2.ext` (no hashes)
- **Database tracking**: JSON tracks URLs, retailers, first/last seen dates
- **Automatic enrichment**: Logo paths added to ad JSON via `brand_logo` field (relative to project root)

## Brand Canonicalization

All brand names are canonicalized via `core/brands.py` using a three-tier matching strategy:

**Matching Order:**
1. **Exact match** - Direct lookup in `config/brands.json` canonical names
2. **Phrase match** - Multi-word substring matching against synonyms (e.g., "Save on Blue Pet Foods" → "Blue Buffalo")
3. **Fuzzy token match** - Individual word matching with `difflib.get_close_matches` (cutoff=0.85)
   - **Critical:** Ignores short tokens (≤4 chars) to prevent generic word collisions
   - Example: "blue" is skipped to avoid "Blue Pet Foods" → "Bluey" mismatch

**Synonym Types in brands.json:**
- Plain brand names: `"BlueBunny"`, `"Blue-Bunny"`
- Full message phrases: `"MSG:Serve Up Sweet Pairings. Top holiday treats..."`
- Campaign codes: `"F25May262025May31TOAAlwaysOn"`

**Common Issues:**
- **Short token collisions**: Generic words like "blue", "new", "red" can match multiple brands
  - **Fix**: Add full-phrase synonyms; fuzzy matching now skips tokens ≤4 chars
- **Unknown brands**: Ad has advertiser but not in lexicon
  - **Fix**: Use Brand Review Tool to add to `brands.json`
- **Mislabeled brands**: Wrong brand assigned during rebuild
  - **Fix**: Use brand-specific repair scripts (see `tools/fix_bluey_rebuild_labels.py`)

**See:** `core/brands.py`, `config/brands.json`, `docs/COMMON_ISSUES.md` → Brand canonicalization

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
├── SBA/              # Sponsored Brand Ads
├── SBV/              # Sponsored Brand Video
├── Tile_Takeover/    # Tile takeover ads
├── Main/             # Main search results
└── runs/
    └── <timestamp>/  # Run artifacts (JSON, HTML) in nested timestamp dirs
        ├── run_results_*.json
        ├── search_results_*.html
        └── run_report.md
```

**Notes:** 
- Walmart uses nested timestamp directories (`runs/TIMESTAMP/*.json`) unlike other retailers.
- Marquee_Banner/Top_Banner is a planned future ad type (not yet implemented).

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

**STATUS: WALMART COMPLETE ✅ | KROGER/INSTACART IN PROGRESS | AMAZON TODO**

### Problem
Each retailer outputs different JSON structures, requiring retailer-specific code in the API and frontend. Walmart now follows the canonical schema. Kroger and Instacart use legacy nested formats.

### Canonical Schema (Walmart Implementation)
```json
{
  "retailer": "walmart",
  "client": "client_name",
  "keyword": "search term",
  "timestamp": "2025-10-27T02:56:54Z",
  "run_id": "20251026215556",
  "ads": [
    {
      "id": "walmart-20251026215556-1",
      "type": "SBA",
      "brand": "Breyers",
      "brand_logo": null,
      "title": null,
      "description": null,
      "cta": null,
      "href": "https://www.walmart.com/search?q=breyers&facet=brand:Breyers",
      "image_url": null,
      "image_path": "SBA/walmart__breyers__sba__client__ice_cream__D2025-10-26_T21-55.56_1.png",
      "products": [],
      "metadata": {
        "slot": 0
      }
    }
  ]
}
```

**Schema Reference:**
```typescript
{
  retailer: string;           // "kroger" | "walmart" | "instacart" | "amazon"
  client: string;             // Client/brand name
  keyword: string;            // Search term
  timestamp: string;          // ISO 8601 with timezone (Z or +HH:MM)
  run_id: string;             // 14-digit timestamp (YYYYMMDDHHMMSS)
  ads: Array<{
    id: string;               // Format: "<retailer>-<run_id>-<index>"
    type: string;             // Canonical ad type (SBA, SBV, Tile_Takeover, TOA, etc.)
    brand: string | null;     // Brand name (canonicalized via lexicon)
    brand_logo: string | null;// Path to brand logo (relative to project root)
    title: string | null;     // Ad title/headline
    description: string | null;
    cta: string | null;       // Call-to-action text
    href: string | null;      // Destination URL
    image_url: string | null; // Original CDN URL
    image_path: string;       // Path to screenshot (relative to client root)
    products: Array<any>;     // Product details (future)
    metadata: {
      slot?: number;          // Grid position/index
      [key: string]: any;     // Retailer-specific metadata
    };
  }>;
}
```

**Standard Fields:**
- `image_path` / `screenshot`: Path to saved screenshot (in ad-type folder, not `runs/`)
  - Different retailers use different field names for the same data
  - Instacart: `screenshot`
  - Kroger: `image_path`, `screenshot_path`, or type-specific (e.g., `skyscraper_image_path`)
  - Backend checks all common field names to find the correct path
- `brand_logo`: Relative path to brand logo file from project root (e.g., `brand_logos/lays.png`)
- `timestamp`: ISO 8601 format with timezone (e.g., `2025-10-20T10:45:43Z` or `2025-10-20T10:45:43+00:00`)
- `type`: Ad type string must match folder name exactly (e.g., `CuratedCarousel` maps to `Carousel/` folder for Kroger)

### Current Status by Retailer

**✅ Walmart** (`walmart_search_and_capture.py`) - **CANONICAL COMPLIANT**:
- ✅ Flat `ads[]` array at top level
- ✅ All required fields: `retailer`, `client`, `keyword`, `timestamp` (ISO Z), `run_id`, `ads[]`
- ✅ Per-ad fields: `id`, `type`, `brand`, `brand_logo`, `title`, `description`, `cta`, `href`, `image_url`, `image_path`, `products`, `metadata`
- ✅ Ad types: `SBA`, `SBV`, `Tile_Takeover` (canonical names)
- ✅ Images saved to correct folders (SBA/, SBV/, Tile_Takeover/)
- ✅ Filenames follow standard pattern with correct ad_type tokens
- ✅ Brand extraction with lexicon canonicalization
- ✅ Nested runs structure: `output/walmart/<client>/runs/<run_id>/run_results_<run_id>.json`
- **Status**: Production-ready, fully compliant with canonical schema

**⚠️ Kroger** (`kroger_search_and_capture.py`) - **LEGACY FORMAT** (repair tools available):
- ❌ Uses nested `results[].ads[]` structure (not flat `ads[]`)
- ❌ Missing top-level: `client`, `run_id`
- ❌ Timestamp not ISO 8601 with timezone
- ✅ Has `retailer`, `keyword` fields
- ✅ Saves images to ad-type folders (TOA/, Skyscraper/, Carousel/)
- ✅ Ad structure has: `type`, `message`, `description`, `cta`, `image_url`, `href`, `advertisers`
- ℹ️ JSON type `CuratedCarousel` maps to `Carousel/` folder (explicit mapping)
- ✅ **Repair tools available (Nov 2025):**
  - `tools/rebuild_kroger_images_from_archive.py` - Regenerate missing images offline from archived HTML
  - `tools/repair_kroger_image_paths.py` - Backfill missing `image_path` fields where PNGs exist
  - Brand-specific repair scripts for known mislabelings (Blue Buffalo/Bluey, Blue Bunny/Unknown)
  - **Common issue:** `image_path` missing despite PNGs existing (extractor URL/structure mismatch)
  - **Fix pattern:** Run repair tool → rebuild brand index → verify in dashboard
- **Needs**: Flatten to canonical schema, add missing fields, ISO timestamps

**⚠️ Instacart** (`instacart_search_and_capture.py`) - **LEGACY FORMAT**:
- ❌ Uses nested `results[].ads[]` structure (not flat `ads[]`)
- ❌ Missing top-level: `client`, `run_id`
- ❌ Timestamp not ISO 8601 with timezone
- ✅ Has `retailer`, `keyword` fields
- ✅ Ad structure has: `type`, `selector`, `id`, `index`, `bbox`, `advertisers`, `brand`, `screenshot`
- ✅ Uses `screenshot` field for image path
- ✅ Saves images to ad-type folders
- **Needs**: Flatten to canonical schema, add missing fields, ISO timestamps, rename `screenshot` to `image_path`

**❌ Amazon** - **NOT IMPLEMENTED**:
- No output directory exists
- **Needs**: Full implementation with canonical schema

**API** (`builder_server_v2.py`):
- ✅ Has `resolve_image_path()` helper to handle both `image_path` and `screenshot` fields
- ⚠️ Still has some retailer-specific code paths for legacy formats

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
- Walmart: `SBA`, `SBV`, `Tile_Takeover`, `Main`, `runs/<timestamp>`
- Instacart: `Shoppable_Display_Ads`, `Shoppable_Video_Ads`, `Shoppable_Recipe_Ads`, `Display_Ads`, `Main`, `runs`
- Amazon: `Sponsored_Brand`, `Sponsored_Product`, `Sponsored_Display`, `Main`, `runs` (TODO: verify)
- Global: `brand_logos/` at project root (centralized brand logo database)

**File Naming:** `retailer__advertiser__ad_type__client__search_term__DYYYY-MM-DD_THH-MM.SS_index.ext`

**JSON Schema:** See "JSON Schema Standardization" section above

**Key Files:**
- `utils/path_taxonomy.py` - Defines allowed folders per retailer
- `filename_utils.py` - Generates standardized filenames
- `brand_logo_database.py` - Manages centralized brand logo database
- `core/brands.py` - Brand canonicalization logic (exact → phrase → fuzzy matching)
- `config/brands.json` - Canonical brand names and synonyms
- `scripts/deduplicate_brand_logos.py` - Cleanup utility for existing logos
- `tools/build_brand_index.py` - Rebuild brand index from all run JSONs
- `docs/RETAILER_ONBOARDING_CHECKLIST.md` - Full onboarding guide

**Repair Tools:**
- `tools/rebuild_kroger_images_from_archive.py` - Offline image regeneration
- `tools/repair_kroger_image_paths.py` - Backfill missing image_path fields
- `tools/fix_bluey_rebuild_labels.py` - Fix Blue Buffalo/Bluey mislabeling
- `tools/repair_blue_bunny_sweet_pairings.py` - Fix Blue Bunny Unknown ads
