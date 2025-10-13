# Co-Branded Ad Support

## Overview
The system now fully supports co-branded advertisements where multiple brands collaborate on a single ad (e.g., Herdez + Jennie-O "Taco Tuesday" campaign).

## Key Features

### 1. **JSON Structure**
Advertisers are stored as arrays for consistent handling:

```json
{
  "type": "TOA",
  "advertisers": ["Herdez", "Jennie-O"],  // Array format
  "message": "Turk-ify Your Taco"
}
```

**Single-brand ads:**
```json
{
  "advertisers": ["Kraft"]
}
```

**Co-branded ads:**
```json
{
  "advertisers": ["Herdez", "Jennie-O"]
}
```

### 2. **Filename Format**
Multiple brands are joined with `+` separator:

**Single brand:**
```
kroger__herdez__toa__cheese_dip__cheese_dip__D2025-10-12_T19-20.33_1.png
```

**Co-branded:**
```
kroger__herdez+jennie_o__toa__cheese_dip__cheese_dip__D2025-10-12_T19-20.33_1.png
```

**With ampersand (P&G):**
```
kroger__p&g+kraft_heinz__toa__test__test__D2025-10-12_T19-20.33_1.png
```

### 3. **Parsing Filenames**
To extract brands from filenames:

```python
parts = filename.split('__')
retailer = parts[0]           # "kroger"
advertiser_segment = parts[1]  # "herdez+jennie_o"
advertisers = advertiser_segment.split('+')  # ["herdez", "jennie_o"]
ad_type = parts[2]            # "toa"
```

### 4. **OCR Brand Detection**
After each screenshot is saved, OCR automatically detects brands:

**Detection Methods:**
- Copyright notices: `©2025 Brand Name, LLC`
- Parent company mapping: `MegaMex Foods` → `Herdez`
- Multiple brands trigger co-branded classification

**Workflow:**
1. Screenshot saved with initial filename
2. OCR runs on saved image
3. Brands detected from copyright text
4. If multiple brands found:
   - File renamed with all brands
   - JSON updated with full advertiser array

## Dashboard Integration

### Counting Strategy
Each co-branded ad counts as **1 ad** but attributes to **all brands**:

**Example Query Results:**
- Query "Herdez ads": Returns 1 ad (the co-branded one)
- Query "Jennie-O ads": Returns 1 ad (the same co-branded one)
- Total unique ads: 1
- Total brand impressions: 2 (Herdez: 1, Jennie-O: 1)

### Database Schema Recommendation
```sql
-- Ads table
CREATE TABLE ads (
    id INT PRIMARY KEY,
    retailer VARCHAR(50),
    ad_type VARCHAR(50),
    client VARCHAR(100),
    search_term VARCHAR(200),
    timestamp DATETIME,
    filename VARCHAR(500)
);

-- Ad-Brand junction table (many-to-many)
CREATE TABLE ad_brands (
    ad_id INT,
    brand_name VARCHAR(100),
    FOREIGN KEY (ad_id) REFERENCES ads(id)
);
```

**Querying:**
```sql
-- Get all ads for a specific brand
SELECT a.* FROM ads a
JOIN ad_brands ab ON a.id = ab.ad_id
WHERE ab.brand_name = 'Herdez';

-- Get brand impression counts
SELECT brand_name, COUNT(*) as impressions
FROM ad_brands
GROUP BY brand_name;
```

## Files Modified

### Core Changes
1. **`filename_utils.py`**
   - Updated `generate_ad_filename()` to accept list of advertisers
   - Added `preserve_ampersand` parameter to `sanitize_component()`
   - Joins multiple advertisers with `+`

2. **`archived/kroger_ad_core.py`**
   - Changed `advertiser` → `advertisers` (array)
   - Stores single brands as `["Brand"]` for consistency

3. **`extractors/screenshot_ad_image.py`**
   - Handles `advertisers` array from JSON
   - Passes advertiser list to filename generator
   - Runs OCR after screenshot
   - Renames file if co-brands detected

4. **`extractors/ocr_brand_detector.py`** (NEW)
   - Detects brands from copyright notices
   - Maps parent companies to consumer brands
   - Returns array of detected brands

## Testing

Run the test suite:
```bash
python3 extractors/ocr_brand_detector.py
```

Expected output:
```
Detected brands: ['Herdez', 'Jennie-O']
```

## Edge Cases Handled

1. **Brand names with ampersands**: `P&G` preserved in filenames
2. **Single-brand ads**: Stored as `["Brand"]` for consistency
3. **OCR failures**: Gracefully skipped, uses HTML-extracted brand
4. **Parent company names**: Mapped to consumer brands (MegaMex → Herdez)
5. **Incomplete OCR**: "Jennie-" mapped to "Jennie-O"

## Future Enhancements

- [ ] Add brand confidence scores from OCR
- [ ] Support for 3+ brand collaborations
- [ ] Brand logo detection (computer vision)
- [ ] Historical co-branding trend analysis
