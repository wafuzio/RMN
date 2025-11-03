# Retailer Authentication Helper

This module provides tools for managing retailer authentication profiles using Playwright.

## Components

- `retailer_auth.py`: Command-line tool for creating and managing retailer authentication profiles
- `gui_helper.py`: Helper functions for integrating authentication management with the GUI
- `profiles.json`: Configuration file storing paths to retailer profiles
- `gui_integration_example.py`: Example of how to integrate with the GUI

## Usage

### Command Line

```bash
# Create/update a profile for Amazon
python3 auth/retailer_auth.py --retailer amazon --profile-dir ~/Documents/Amazon_Scrape/profiles/amazon

# Create/update a profile for Kroger
python3 auth/retailer_auth.py --retailer kroger --profile-dir ~/Documents/Amazon_Scrape/profiles/kroger
```

### In Python Code

```python
# Get the profile directory for a retailer
from auth.gui_helper import get_profile_dir
profile_dir = get_profile_dir("amazon")

# Set the profile directory for a retailer
from auth.gui_helper import set_profile_dir
set_profile_dir("amazon", "/path/to/profile")

# Manage retailer login from the GUI
from auth.gui_helper import manage_retailer_login
manage_retailer_login(root_window, "amazon")
```

### Integration with GUI

See `gui_integration_example.py` for an example of how to add a "Manage Login" button to the GUI.

## Environment Variables

The following environment variables are set when managing profiles:

- `AMAZON_PROFILE_DIR`: Path to the Amazon profile directory
- `KROGER_PROFILE_DIR`: Path to the Kroger profile directory
- `WALMART_PROFILE_DIR`: Path to the Walmart profile directory

These can be used in retailer adapters to specify the profile directory for Playwright.
