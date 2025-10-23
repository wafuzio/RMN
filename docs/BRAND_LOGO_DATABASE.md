# Brand Logo Database

Automatically downloads and manages brand logos from retailer ads for reuse in the frontend.

## Overview

The brand logo database system:
- **Automatically downloads** brand logos when scraping ads
- **Stores logos** in a centralized `brand_logos/` directory
- **Creates a JSON database** mapping brands to logo files
- **Prevents duplicates** using URL hashing
- **Tracks metadata** (retailers, first/last seen, ad types)
- **Works across retailers** (Instacart, Walmart, Kroger, Amazon)

## Directory Structure

```
Amazon_Scrape/
├── brand_logos/                    # Centralized logo storage
│   ├── brand_logo_database.json   # Main database file
│   ├── frontend_logos.json        # Frontend-friendly export
│   ├── lays.png                   # Logo files (clean, numbered names)
│   ├── sour_patch_kids.png
│   ├── nestle_2.png               # Multiple logos numbered sequentially
│   └── ...
└── brand_logo_database.py         # Database manager class
```

## Database Schema

### Main Database (`brand_logo_database.json`)

```json
{
  "brands": {
    "lays": {
      "brand_name": "Lay's",
      "logo_url": "https://display.instacart.com/.../72917cb9-cc41-404c-9a7e-dcdedf0a7ee5-1.png",
      "logo_file": "brand_logos/lays.png",
      "retailers": ["instacart", "kroger"],
      "first_seen": "2025-10-15T12:53:00",
      "last_seen": "2025-10-15T14:30:00",
      "metadata": {
        "ad_type": "Display Ad",
        "keyword": "chips",
        "timestamp": "2025-10-15_12-53-00"
      }
    }
  },
  "metadata": {
    "last_updated": "2025-10-15T14:30:00",
    "total_brands": 42
  }
}
```

### Frontend Export (`frontend_logos.json`)

Simplified mapping for frontend use:

```json
{
  "Lay's": "brand_logos/lays.png",
  "Sour Patch Kids": "brand_logos/sour_patch_kids.png",
  "McCormick": "brand_logos/mccormick.png",
  "Nestlé": "brand_logos/nestle_2.png"
}
```

## Usage

### Automatic Collection (During Scraping)

Logos are automatically collected when running any retailer scraper:

**Instacart:**
```bash
python instacart_search_and_capture.py --keyword "ice cream" --client "blue_bunny"
```

**Walmart:**
```bash
python walmart_search_and_capture.py --keyword "chips" --client "lays"
```

The scraper will:
1. Extract brand names from ads (Display Ads, SBA, etc.)
2. Find brand logo images with alt text
3. Download and save logos to `brand_logos/`
4. Update the database JSON

**Logo Sources by Retailer:**
- **Instacart**: Display Ad logos, Recipe ad logos
- **Walmart**: SBA (Sponsored Brand Ad) logos, Marquee Banner logos
- **Kroger**: TOA (Targeted Onsite Ad) logos (future)
- **Amazon**: Sponsored Brand logos (future)

### Manual Management

```python
from brand_logo_database import BrandLogoDatabase

# Initialize database
db = BrandLogoDatabase()

# Add a brand logo
db.add_brand_logo(
    brand="Lay's",
    logo_url="https://display.instacart.com/.../logo.png",
    retailer="instacart",
    metadata={"ad_type": "Display Ad"}
)

# Get logo path for a brand
logo_path = db.get_logo_path("Lay's")
# Returns: "brand_logos/lays.png"

# List all brands
brands = db.list_all_brands()
# Returns: ["Lay's", "Sour Patch Kids", "McCormick", ...]

# Export for frontend
frontend_map = db.export_for_frontend("brand_logos/frontend_logos.json")
```

## Frontend Integration

### Option 1: Direct File Access

```typescript
import brandLogos from '@/brand_logos/frontend_logos.json';

function BrandLogo({ brandName }: { brandName: string }) {
  const logoPath = brandLogos[brandName];
  
  if (!logoPath) return <span>{brandName}</span>;
  
  return <img src={`/${logoPath}`} alt={brandName} />;
}
```

### Option 2: API Endpoint

Create an API endpoint to serve logos:

```python
# server/routes/brand_logos.py
from brand_logo_database import BrandLogoDatabase

@app.get("/api/brand-logo/<brand_name>")
def get_brand_logo(brand_name):
    db = BrandLogoDatabase()
    logo_info = db.get_brand_logo(brand_name)
    
    if logo_info:
        return jsonify(logo_info)
    return jsonify({"error": "Brand not found"}), 404
```

## Features

### Duplicate Prevention

- **Content-based deduplication**: Uses MD5 hash of image content (not URL)
- Identical images from different URLs share one file
- Clean numbered naming: `brand_name.png` or `brand_name_2.png` (no hash suffixes)
- If same logo content is encountered, reuses existing file instead of re-downloading
- Tracks which retailers have this brand

**Example:**
- First Boiron logo → `boiron.png`
- Different Boiron logo (different content) → `boiron_2.png`
- Same Boiron logo from different URL → reuses `boiron.png`

### Brand Name Normalization

Brand names are normalized for database keys:
- Lowercase
- Replace `&` with `and`
- Remove apostrophes, periods
- Replace spaces with underscores

Examples:
- `"Lay's"` → `lays`
- `"Ben & Jerry's"` → `ben_and_jerrys`
- `"Dr. Pepper"` → `dr_pepper`

### Metadata Tracking

Each brand logo includes:
- **Original brand name** (with proper casing)
- **Logo URL** (original source)
- **Local file path** (relative path)
- **Retailers** (list of retailers where seen)
- **First/last seen** (timestamps)
- **Custom metadata** (ad type, keyword, etc.)

## Benefits

1. **Reusable Assets** - Download once, use everywhere
2. **Consistent Branding** - Use official brand logos across frontend
3. **Performance** - Serve logos locally instead of external CDNs
4. **Offline Capability** - Logos available even if original source is down
5. **Analytics** - Track which brands appear most frequently
6. **Multi-Retailer** - See which brands appear across different retailers

## Maintenance


### Update Logos

If a brand updates their logo, the system will:
1. Detect the new URL
2. Download the new logo with a different hash
3. Keep the old logo (for historical data)
4. Update the database to point to the new logo

## Future Enhancements

- [ ] Image optimization (resize, compress)
- [ ] Brand aliases (handle variations like "Coca Cola" vs "Coke")
- [ ] Logo quality scoring
- [ ] Bulk export to CDN
