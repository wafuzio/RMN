# Kroger TOA Monitoring Project

A tool for tracking and analyzing Targeted Onsite Ads (TOAs) and other ad types on Kroger.com search results, with support for integration with Builder.io.

## Overview

This project provides a system for monitoring and analyzing sponsored brand presence in Kroger.com search results. It includes tools for:

- Automated search and capture of Kroger.com search results
- Extraction of TOA (Targeted Onsite Ad) data from search results
- Precise cropping of TOA banner images for use in Builder.io
- Client-specific organization of results
- API endpoints for accessing images and data

## Complete Workflow

1. **Keyword Entry** → User enters search keywords and client name via `keyword_input.py`
2. **Search & Capture** → `kroger_search_and_capture.py` performs the search and captures screenshots/HTML
3. **TOA Extraction** → `kroger_ad_core.py` with `toa_extractor.py` extracts TOA data from HTML
4. **Image Processing** → `capture_toa_images.py` creates precisely cropped TOA-only images
5. **Data Storage** → Results stored in client-specific directories with organized structure
6. **API Access** → `builder_server.py` provides API endpoints for Builder.io integration

## Directory Structure

```
output/
  ├── <client_name>/       # Client-specific directory (e.g., Land_O_Frost)
  │   ├── main/           # Full page screenshots
  │   ├── TOA/            # TOA-only images and results
  │   └── *.html          # Saved HTML files
```

## Key Components

- **keyword_input.py**: GUI for entering keywords and managing searches
- **kroger_search_and_capture.py**: Performs searches and captures HTML/screenshots
- **kroger_ad_core.py**: Core functionality for ad extraction
- **ad_extractors/**: Modular system for different ad type extractors
  - **base_extractor.py**: Base class with common extraction methods
  - **toa_extractor.py**: Specific extractor for TOA banners
- **process_saved_html.py**: Processes saved HTML files to extract ad data
- **capture_toa_images.py**: Creates precisely cropped TOA-only images
- **builder_server.py**: Flask server with API endpoints for Builder.io integration

## API Endpoints

- `/api/images/<client>/<filename>` - Serves full page screenshots
- `/api/toa/<client>/<filename>` - Serves TOA-only images

## Features

- **Session Persistence**: Handles Akamai Bot Protection with cookie persistence
- **Modular Ad Extractors**: Easily add new ad type extractors
- **Adaptive TOA Detection**: Uses edge detection to precisely crop TOA banners
- **Client Organization**: Stores results in client-specific directories
- **Builder.io Integration**: API endpoints for accessing images

## Requirements

- Python 3.8+
- Playwright
- BeautifulSoup4
- Pillow (PIL)
- Flask
- NumPy

## Installation

1. Clone this repository
2. Install dependencies: `pip install -r requirements.txt`
3. Install Playwright browsers: `playwright install`

## Usage

### Running the Main Tool

```bash
python keyword_input.py
```

### Processing Saved HTML

```bash
python process_saved_html.py --input-dir output/<client_name> --output-dir output/<client_name>
```

### Creating TOA-Only Images

```bash
python capture_toa_images.py <client_name>
```

### Starting the API Server

```bash
python builder_server.py
```

## Adding New Ad Extractors

1. Copy `ad_extractors/template_extractor.py` to a new file
2. Modify the class name, ad type, and extraction logic
3. Register the extractor in the module
4. Import the new extractor in `kroger_ad_core.py`
