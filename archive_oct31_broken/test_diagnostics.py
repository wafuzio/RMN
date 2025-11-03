#!/usr/bin/env python3
"""
Test script to verify diagnostics implementation in kroger_ad_core.py
"""

from kroger_ad_core import get_rendered_html

# Test URL
url = "https://www.kroger.com/search?query=trolli&searchType=default_search"

# Run with diagnostics
print("Running test with diagnostics...")
html = get_rendered_html(url, wait_ms=3000)

print("Test completed. Check the diagnostics folder for output files.")
