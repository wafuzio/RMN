# Oct 15, 2025 Working Instacart Scraper

These files represent the working state of the Instacart scraper as of Oct 15, 2025.

## Files

- **instacart_search_and_capture.py** (Oct 14 commit d4a6bef)
  - Main search script
  - Saves HTML and JSON only (no screenshots)
  - 455 lines

- **screenshot_instacart_ads.py** (current from extractors/)
  - Separate screenshot extractor
  - Loads saved HTML/JSON and takes screenshots
  - Uses `div.e-1qzz7bi` and `div.e-1hv1sre` selectors
  - 547 lines

- **instacart_adapter.py** (Oct 14 commit)
  - Retailer adapter for the scraper framework

## How It Worked

1. Run `instacart_search_and_capture.py` → saves HTML/JSON to runs/
2. Run `screenshot_instacart_ads.py` → reads HTML/JSON, takes screenshots

The two-step process ensured screenshots were taken from the same page state as the JSON data.

## Known Issues

- Uses hashed class names (`e-1qzz7bi`, `e-1hv1sre`) which may change over time
- Requires manual two-step execution

## Migration Notes

Later versions merged screenshot logic into the main capture script to ensure synchronization
and eliminate the two-step process. This required structural selectors instead of hashed classes.
