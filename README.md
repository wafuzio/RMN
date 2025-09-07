# Kroger TOA Monitoring Project

A tool for tracking and analyzing Targeted Onsite Ads (TOAs) and other ad types on Kroger.com search results.

## Overview

This project provides a system for monitoring and analyzing sponsored brand presence in Kroger.com search results. It includes tools for:

- Automated search and capture of Kroger.com search results
- Extraction of TOA (Targeted Onsite Ad) data from search results
- Scheduling of regular search runs
- Analysis of ad content and trends

## Key Components

- **Kroger_login.py**: Handles authentication with cookie persistence
- **kroger_search_and_capture.py**: Performs searches and captures HTML/screenshots
- **kroger_ad_core.py**: Core functionality for ad extraction
- **process_saved_html.py**: Processes saved HTML files to extract ad data
- **keyword_input.py**: GUI for entering keywords and managing searches
- **ad_extractors/**: Modular system for different ad type extractors

## Features

- **Session Persistence**: Handles Akamai Bot Protection with cookie persistence
- **Modular Ad Extractors**: Easily add new ad type extractors
- **Scheduling**: Set up regular search runs on a schedule
- **Error Recovery**: Retry mechanism for failed searches
- **Data Analysis**: Extract common words and phrases from ad content

## Requirements

- Python 3.8+
- Playwright
- BeautifulSoup4
- NLTK
- Tkinter (for GUI)

## Installation

1. Clone this repository
2. Install dependencies: `pip install -r requirements.txt`
3. Install Playwright browsers: `playwright install`

## Usage

Run the GUI tool:
```
python keyword_input.py
```

Or process saved HTML files:
```
python process_saved_html.py
```

## Adding New Ad Extractors

1. Copy `ad_extractors/template_extractor.py` to a new file
2. Modify the class name, ad type, and extraction logic
3. Register the extractor in the module
4. Import the new extractor in `kroger_ad_core.py`
