# Instacart Adapter for Retail Ad Monitor

This adapter enables the Retail Ad Monitor to scrape and extract ad images from Instacart search results pages.

## Setup

1. Create an Instacart profile:

```bash
# Run the setup script
./scripts/setup_instacart_profile.sh

# Or manually:
mkdir -p ~/Documents/Amazon_Scrape/profiles/instacart
python3 auth/retailer_auth.py --retailer instacart --profile-dir ~/Documents/Amazon_Scrape/profiles/instacart
```

2. Add the environment variables to your shell profile (`~/.zshrc` or `~/.bash_profile`):

```bash
export INSTACART_PROFILE_DIR=~/Documents/Amazon_Scrape/profiles/instacart
export INSTACART_STORE=publix  # Optional, defaults to 'publix'
```

3. Reload your shell:

```bash
source ~/.zshrc
```

## Usage

1. Launch the Retail Ad Monitor GUI:

```bash
python3 keyword_input.py
```

2. Select "Instacart" from the retailer dropdown.
3. Enter keywords to search for.
4. Click "Run Scraper" to start the scraping process.

## Ad Placement Mapping

The Instacart adapter maps Instacart ad placements to the existing output folders:

- **TOA**: Shoppable Display Ads and Shoppable Video Ads (large format ads with product carousels)
- **Skyscraper**: Display Ads (horizontal brand strips at top of search results)
- **Carousel**: Product carousels within shoppable ads

## Ad Types Detected

The adapter uses **semantic selectors** (not hashed CSS classes) to detect:

1. **Shoppable Display Ad**
   - Static image ads with product carousels
   - Detected by: `data-testid="shoppable-list-sliding-carousel"` + Advertisement image
   - May include: h2 header, "Sponsored" label (can be split across spans), hero image
   - Examples: GoodPop, Icy Hot, C4, Trolli

2. **Shoppable Video Ad**
   - Video ads with product carousels
   - Detected by: carousel + `<video>` element or "Play Video" button
   - Includes: h2 header, "Sponsored" label, video player, product carousel
   - Examples: Dreyers, Dairy Farmers of America
   - Video files: Downloads MP4 (direct) or saves HLS URL (.m3u8)

3. **Ad Container Selection**
   - Finds the **outermost ancestor** containing all ad elements
   - Ensures complete capture: header + hero/video + carousel
   - Handles multiple ad formats (with/without headers)
   - Adds 20px padding to include visual borders

4. **Sponsored Label Detection**
   - Handles split text: `<span>Spons</span><span> ored</span>`
   - Uses regex: `r"Spons\s*ored"` with `inner_text()` fallback

## Store Configuration

Instacart requires a store context for search. The default store is "publix", but you can configure it:

```bash
export INSTACART_STORE=kroger  # or any other supported store slug
```

Common store slugs:
- `publix`
- `kroger`
- `costco`
- `safeway`
- `albertsons`

## URL Pattern

Instacart search URL pattern:
```
https://www.instacart.com/store/{store}/s?k={keyword}
```

Example:
```
https://www.instacart.com/store/publix/s?k=eggs
```

## Output

- HTML and JSON files are saved in the `output/instacart/<client>/runs/` directory
- Ad images are saved in the `output/instacart/<client>/TOA/`, `output/instacart/<client>/Skyscraper/`, and `output/instacart/<client>/Carousel/` directories
- Logs are saved in the `logs/instacart/` directory

## Troubleshooting

If you encounter issues with the Instacart adapter:

1. Check that you have a valid Instacart profile:
   - Run `ls -la ~/Documents/Amazon_Scrape/profiles/instacart` to verify the profile exists
   - If needed, recreate the profile with `./scripts/setup_instacart_profile.sh`

2. Check that the environment variables are set:
   - Run `echo $INSTACART_PROFILE_DIR` to verify the environment variable is set
   - Run `echo $INSTACART_STORE` to check the store configuration
   - If not, set them with `export INSTACART_PROFILE_DIR=...` and reload your shell

3. Check the logs:
   - Look in the `logs/instacart/` directory for detailed logs of the scraping process

4. Verify authentication:
   - Run `python3 scripts/test_instacart_ads_with_auth.py` to test ad visibility
   - Should report 8+ ads found if authentication is working

## Technical Details

### Authentication & Loading
- **Authentication**: Requires persistent Chrome profile with logged-in session
- **Wait Strategy**: Uses `domcontentloaded` instead of `networkidle` due to dynamic content
- **Lazy Loading**: Pre-scrolls page before extraction to load all lazy-loaded ads
- **Virtual Scrolling**: Bidirectional scroll for full-page screenshots to keep grid items in DOM

### Ad Detection & Extraction
- **Semantic Selectors**: Uses stable HTML attributes (`data-testid`, `alt`, `role`) instead of hashed classes
- **Container Selection**: Finds outermost ancestor containing h2 + "Spons" + carousel (or Advertisement img + carousel)
- **Split Text Handling**: Detects "Sponsored" even when split across multiple `<span>` elements
- **Hero Image Extraction**: Fallback logic for images without `alt="Advertisement"`
- **Video Handling**: Detects video elements, downloads MP4 or saves HLS URLs, includes video metadata

### Screenshot Strategy
- **Container-based**: Screenshots the complete ad container (not individual elements)
- **Padding**: Adds 20px padding on all sides to capture visual borders
- **Timing**: Waits for ad creative to load before capture (viewability gates)
- **Full-page**: Uses CDP for static full-page capture without viewport resizing

### Known Issues & Solutions
- **Issue**: Ads cropped too tight, missing headers
  - **Solution**: Find outermost ancestor container, not closest
- **Issue**: Lazy-loaded ads missing from extraction
  - **Solution**: Pre-scroll page to load all content before extraction
- **Issue**: Virtual scroll grid items missing
  - **Solution**: Bidirectional scroll to keep items in DOM for screenshot
- **Issue**: Hero images not captured in JSON
  - **Solution**: Fallback to find large images (>100px) from display CDN
