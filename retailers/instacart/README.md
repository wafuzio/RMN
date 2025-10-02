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

- **TOA**: Shoppable Display Ads (video and static ads with product carousels)
- **Skyscraper**: Top Banner Ads (horizontal brand strips at top of search results)
- **Carousel**: Product carousels within shoppable ads

## Ad Types Detected

Based on HTML analysis, the adapter detects:

1. **Shoppable Display Ads** (`div.e-1qzz7bi`)
   - Static image ads with product carousels
   - Video ads with product carousels
   - Brand logo + headline + "Sponsored" label

2. **Top Banner Ads** (`div.e-1hv1sre`)
   - Horizontal brand strips
   - Compact header with product carousel
   - Appears at top of search results

3. **Sponsored Labels** (`div.e-cwus85`)
   - "Sponsored" text indicators
   - Appears on all ad types

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

- **Authentication**: Requires persistent Chrome profile with logged-in session
- **Wait Strategy**: Uses `domcontentloaded` instead of `networkidle` due to dynamic content
- **Ad Detection**: Uses CSS selectors from actual Instacart HTML patterns
- **Success Criteria**: At least one TOA or Skyscraper image (following Kroger pattern)
