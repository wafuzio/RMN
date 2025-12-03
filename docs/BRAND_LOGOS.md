# Brand Logo System

Complete guide for collecting, storing, reviewing, and updating brand logos.

## Overview

The brand logo system automatically collects logos from retailer ads and provides a centralized database for the frontend. Logos go through a verification workflow before being served to users.

**Key Components:**
- **Automatic collection** during ad scraping
- **Centralized storage** in `output/brand_logos/`
- **Verification workflow** (unverified → verified)
- **JSON database** mapping brands to logo files
- **API endpoint** for serving logos to frontend

## Directory Structure

```
output/brand_logos/
├── brand_logo_database.json   # Main database mapping brands → logo files
├── verified/                  # ✅ Reviewed and approved logos
│   ├── lays.png
│   ├── campbells.png
│   └── ...
└── unverified/                # ⏳ Newly collected, pending review
    ├── unknown_brand_123.png
    └── ...
```

## Workflow

### 1. Collection (Automatic)

Logos are automatically collected when running scrapers:

```bash
# Logos collected during any scrape
python walmart_search_and_capture.py --keyword "chips" --client "lays"
python instacart_search_and_capture.py --keyword "ice cream" --client "blue_bunny"
```

**Logo Sources by Retailer:**
| Retailer  | Logo Sources | Status |
|-----------|--------------|--------|
| Instacart | Display Ads, Recipe Ads | ✅ Integrated |
| Walmart   | SBA logos, Marquee Banners, Gallery Cards | ✅ Integrated |
| Amazon    | Sponsored Brand logos, SB Cards | ✅ Integrated |
| Kroger    | N/A (product carousels only, no brand logos) | ⏳ Future |

**What happens during scraping:**
1. Scraper extracts brand name from ad
2. **Lexicon check**: Canonicalizes brand name via `config/brands.json`
   - If brand is a synonym, maps to canonical name (e.g., "Kelloggs" → "Kellogg's")
   - Uses canonical name for all subsequent lookups
3. **Logo check**: Checks if canonical brand already has a verified logo
   - If logo exists → skips download, reuses existing logo
   - If no logo → proceeds to download
4. Finds logo image (from alt text, dedicated logo element, etc.)
5. Downloads logo to `unverified/` folder
6. Updates `brand_logo_database.json` under canonical brand name

**Lexicon Integration (`config/brands.json`):**
```json
{
  "name": "Kellogg's",
  "synonyms": ["Kellogg", "Kelloggs", "Kellogg Company", "Kellogg Co"]
}
```

When the scraper sees "Kelloggs" in an ad:
1. Lexicon lookup finds canonical name "Kellogg's"
2. Database check: Does "kelloggs" (normalized) have a logo?
3. If yes → use existing logo, no download needed
4. If no → download and save under "kelloggs" key with display name "Kellogg's"

### 2. Review (Manual)

Use the Logo Verifier GUI to review unverified logos:

```bash
python tools/logo_verifier_gui.py
```

**Review Actions:**
- **Approve** → Moves to `verified/` folder
- **Reject** → Deletes the logo
- **Rename** → Fix brand name before approving

**Quality Criteria:**
- ✅ Clear, recognizable brand logo
- ✅ Good resolution (at least 200px)
- ✅ Correct brand attribution
- ❌ Blurry or cropped images
- ❌ Product images (not logos)
- ❌ Wrong brand name

### 3. Storage

**Database Schema (`brand_logo_database.json`):**

```json
{
  "brands": {
    "lays": {
      "brand_name": "Lay's",
      "logo_file": "verified/lays.png",
      "source": "instacart_scrape",
      "updated_at": "2025-12-01T14:30:00"
    }
  }
}
```

**Brand Name Normalization:**
Brand names are normalized to create database keys:
- Lowercase
- Replace `&` with `and`
- Remove apostrophes, periods
- Replace spaces with underscores

| Original | Normalized Key |
|----------|---------------|
| Lay's | `lays` |
| Ben & Jerry's | `ben_and_jerrys` |
| Dr. Pepper | `dr_pepper` |

### 4. Serving (API)

Logos are served via the Node.js API:

```
GET /api/logo/brand/:brandName?w=240
```

**Example:**
```
http://localhost:3000/api/logo/brand/Lay's?w=240
```

**Features:**
- Automatic resizing via `w` parameter
- WebP conversion for smaller files
- ETag caching with mtime-based invalidation
- Falls back to 404 if logo not found

### 5. Updating Logos

When you need to replace a logo:

**Option A: Single Logo Refresh**
```bash
# After replacing the file in verified/
python tools/refresh_brand_logo.py "Brand Name"
```

**Option B: Full Sync (runs on server restart)**
```bash
python tools/sync_verified_logos.py
```

**Option C: Server Restart**
```bash
./restart_servers.sh
# Automatically runs sync_verified_logos.py
```

## Tools Reference

| Tool | Purpose |
|------|---------|
| `tools/logo_verifier_gui.py` | GUI for reviewing unverified logos |
| `tools/refresh_brand_logo.py` | Update single logo in database + bust cache |
| `tools/sync_verified_logos.py` | Sync all verified logos to database |
| `tools/harvest_amazon_brand_logos.py` | Extract logos from Amazon scrape data |
| `tools/logo_scout.py` | Fetch logos from Wikidata/Clearbit for brands in API |
| `tools/logo_scout_lexicon.py` | Fetch logos for all brands in lexicon missing logos |

### LogoScout - Automated Logo Fetching

For brands without logos, LogoScout can automatically fetch them from external sources:

```bash
# Fetch logos for all lexicon brands missing logos
python tools/logo_scout_lexicon.py

# Fetch logos for brands from a specific retailer/client
python tools/logo_scout.py --api http://localhost:5006 --retailer instacart --client blue_bunny
```

**Sources (in order):**
1. **Wikidata** - Official logo (P154) or website domain
2. **Clearbit** - `https://logo.clearbit.com/<domain>`

This is useful after adding new brands to the lexicon - run `logo_scout_lexicon.py` to backfill missing logos.

## Finding Missing Logos

### Check Which Brands Need Logos

```bash
# Find all unique advertisers in recent runs
find output -name "run_results*.json" -type f -exec jq -r '.ads[]?.brand // .ads[]?.advertisers[]?' {} \; 2>/dev/null | sort -u | head -50

# Check brands from lexicon
jq -r '.[].name' config/brands.json | sort
```

### Adding Logos Manually

1. **Find official logo** from:
   - Brand's official website (Press Kit / Media page)
   - Wikipedia infobox
   - Social media profile images

2. **Save to verified folder:**
   ```bash
   # Use normalized filename
   cp ~/Downloads/logo.png output/brand_logos/verified/brand_name.png
   ```

3. **Refresh the database:**
   ```bash
   python tools/refresh_brand_logo.py "Brand Name"
   ```

**Logo Requirements:**
- PNG with transparent background (preferred)
- SVG (best for scalability)
- At least 200px wide
- Official brand colors
- No taglines or extra text

## Duplicate Prevention

The system prevents duplicate logos using:

1. **Content-based deduplication** - MD5 hash of image bytes
2. **Numbered naming** - `brand.png`, `brand_2.png` for variants
3. **Retailer tracking** - Knows which retailers have each brand

**Example:**
- First Boiron logo → `boiron.png`
- Different Boiron logo (different content) → `boiron_2.png`
- Same logo from different URL → reuses `boiron.png`

## Cache Invalidation

When logos are updated:

1. **Server-side**: File mtime is included in ETag, so touching the file invalidates cache
2. **Browser-side**: Cache-Control is set to 1 day (not immutable)
3. **Immediate refresh**: Hard refresh (Cmd+Shift+R) or incognito window

## Troubleshooting

### Logo Not Updating

```bash
# 1. Verify file exists
ls -la output/brand_logos/verified/ | grep -i "brand"

# 2. Refresh the logo
python tools/refresh_brand_logo.py "Brand Name"

# 3. Hard refresh browser (Cmd+Shift+R)
```

### Logo Shows 404

```bash
# Check if brand is in database
python3 -c "import json; db=json.load(open('output/brand_logos/brand_logo_database.json')); print(db.get('brands',{}).get('brand_slug', 'NOT FOUND'))"

# Sync verified logos
python tools/sync_verified_logos.py
```

### Wrong Logo Displayed

1. Delete incorrect logo from `verified/`
2. Add correct logo with same filename
3. Run `python tools/refresh_brand_logo.py "Brand Name"`
4. Hard refresh browser
