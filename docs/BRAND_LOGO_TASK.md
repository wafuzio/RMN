# Brand Logo Database Maintenance Task

## Objective
Systematically find and add missing brand logos to the brand logo database at `docs/BRAND_LOGO_DATABASE.md`.

## Context
The brand logo database is used by scrapers to automatically download brand logos when processing ads. Missing logos result in ads being saved without brand attribution or visual identification.

## Current Database Location
`/Users/dan.maguire/Documents/Amazon_Scrape/docs/BRAND_LOGO_DATABASE.md`

## Task Instructions

### 1. Identify Missing Brands
Scan the following sources to find brands that appear in ads but are missing from the logo database:

**Sources to check:**
- `output/*/runs/*.json` - Check `advertisers` fields in ad data
- `config/brands.json` - Brand lexicon (33 brands currently)
- Recent scraper output logs

**Brands recently encountered that may need logos:**
- Magic Spoon
- Pull-Ups
- Jell-O
- Nature's Path
- NuTrail
- Olipop
- Ithaca
- Häagen-Dazs
- Tide
- Ghirardly
- Dreyers

### 2. Find Official Brand Logos
For each missing brand:

1. **Search for official brand website**
   - Look for "About", "Press Kit", or "Media" pages
   - These often have downloadable logos

2. **Check brand's Wikipedia page**
   - Often has official logos in the infobox

3. **Use brand's social media**
   - Twitter/X profile images
   - LinkedIn company pages
   - Facebook pages

4. **Preferred logo characteristics:**
   - SVG format (scalable, best quality)
   - PNG with transparent background (second choice)
   - High resolution (at least 500px wide)
   - Official brand colors
   - No taglines or extra text (just the logo)

### 3. Add to Database
For each brand logo found, add an entry to `BRAND_LOGO_DATABASE.md` in this format:

```markdown
## Brand Name

**URL:** https://direct-link-to-logo-file.svg
**Format:** SVG / PNG
**Source:** Official website / Wikipedia / etc.
**Added:** YYYY-MM-DD
**Notes:** Any relevant notes about the logo
```

### 4. Verification
After adding logos:
1. Test that the URL is accessible and returns the image
2. Verify the image is the correct brand logo
3. Check that the format is suitable for web use
4. Ensure the logo is high enough quality

## Success Criteria
- All brands in `config/brands.json` have logo entries
- All brands appearing in recent scraper runs have logo entries
- Each logo URL is verified to be accessible
- Logos are official and high quality

## Automation Hints
You can use these commands to help identify missing brands:

```bash
# Find all unique advertisers in recent runs
find output -name "*.json" -type f -exec jq -r '.results[]?.ads[]?.advertisers[]?' {} \; 2>/dev/null | sort -u

# Check which brands from lexicon are missing from logo database
comm -23 <(jq -r '.[].name' config/brands.json | sort) <(grep "^## " docs/BRAND_LOGO_DATABASE.md | sed 's/^## //' | sort)
```

## Notes
- Respect copyright - only use official logos from legitimate sources
- Prefer direct links to logo files over page URLs
- Document the source for each logo for future reference
- If a logo URL becomes unavailable, update with a new source
