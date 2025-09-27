#!/usr/bin/env python3
"""
Compatibility shim: forwards legacy calls to the modern extractor.
Tries both screenshot_ad_images.py and screenshot_ad_image.py.
"""
import os
import sys

# Ensure this directory is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ad_main = None

try:
    # Preferred name (plural)
    from screenshot_ad_images import main as ad_main
except Exception:
    try:
        # Fallback if your file is named singular
        from screenshot_ad_image import main as ad_main
    except Exception as e:
        print(f"❌ Could not import screenshot_ad_images or screenshot_ad_image: {e}")
        sys.exit(1)

if __name__ == "__main__":
    sys.exit(ad_main())