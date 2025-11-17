# Amazon Adapter for Retail Ad Monitor

This adapter enables the Retail Ad Monitor to scrape and extract ad images from Amazon search results pages.

## Setup

1. Create an Amazon profile:

```bash
# Run the setup script
../../scripts/setup_amazon_profile.sh

# Or manually:
mkdir -p ~/Documents/Amazon_Scrape/profiles/amazon
python3 auth/retailer_auth.py --retailer amazon --profile-dir ~/Documents/Amazon_Scrape/profiles/amazon
export AMZ_PROFILE_DIR=~/Documents/Amazon_Scrape/profiles/amazon
```

2. Add the environment variable to your shell profile:

```bash
echo 'export AMZ_PROFILE_DIR=~/Documents/Amazon_Scrape/profiles/amazon' >> ~/.zshrc
# Or for bash:
# echo 'export AMZ_PROFILE_DIR=~/Documents/Amazon_Scrape/profiles/amazon' >> ~/.bash_profile
```

## Usage

1. Launch the Retail Ad Monitor GUI:

```bash
python3 keyword_input.py
```

2. Select "Amazon" from the retailer dropdown.
3. Enter keywords to search for.
4. Click "Run Scraper" to start the scraping process.

## Ad Placement Mapping

The Amazon adapter maps Amazon ad placements to the existing output folders:

- **TOA**: Sponsored Brands (headline banner) and/or Video banner near top (SB/SBV)
- **Skyscraper**: Right-rail Sponsored Display (if present; not on all SERPs)
- **Carousel**: Sponsored Products top-of-search strip (horizontal carousels) or first sponsored row

## Output

- HTML and JSON files are saved in the `output/amazon/<client>/runs/` directory
- Ad images are saved in the `output/amazon/<client>/TOA/`, `output/amazon/<client>/Skyscraper/`, and `output/amazon/<client>/Carousel/` directories
- Logs are saved in the `logs/amazon/` directory

## Troubleshooting

If you encounter issues with the Amazon adapter:

1. Check that you have a valid Amazon profile:
   - Run `ls -la ~/Documents/Amazon_Scrape/profiles/amazon` to verify the profile exists
   - If needed, recreate the profile with `python3 auth/retailer_auth.py --retailer amazon --profile-dir ~/Documents/Amazon_Scrape/profiles/amazon`

2. Check that the environment variable is set:
   - Run `echo $AMZ_PROFILE_DIR` to verify the environment variable is set
   - If not, set it with `export AMZ_PROFILE_DIR=~/Documents/Amazon_Scrape/profiles/amazon`

3. Check the logs:
   - Look in the `logs/amazon/` directory for detailed logs of the scraping process
