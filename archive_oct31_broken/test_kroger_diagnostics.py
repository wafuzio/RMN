#!/usr/bin/env python3
"""
Simple test script to verify the diagnostics implementation in kroger_ad_core.py
"""

from kroger_ad_core import get_rendered_html, log

# Test URL
URL = "https://www.kroger.com/search?query=milk"

def main():
    """Run a simple test of the diagnostics implementation"""
    log(">>> Starting diagnostics test")
    
    # Run get_rendered_html with the test URL
    try:
        html = get_rendered_html(URL, wait_ms=3000)
        log(f">>> HTML length: {len(html)}")
        log(">>> Test completed successfully")
        return True
    except Exception as e:
        log(f">>> Test failed: {e}")
        return False

if __name__ == "__main__":
    main()
