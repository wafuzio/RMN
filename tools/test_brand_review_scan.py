#!/usr/bin/env python3
"""Test the brand review tool scanning logic without GUI"""

import sys
import os

# Mock tkinter to avoid GUI
class MockTk:
    def title(self, t): pass
    def geometry(self, g): pass
    def quit(self): pass

sys.modules['tkinter'] = type(sys)('tkinter')
sys.modules['tkinter'].Tk = MockTk
sys.modules['tkinter'].ttk = type(sys)('ttk')
sys.modules['tkinter'].messagebox = type(sys)('messagebox')
sys.modules['tkinter'].font = type(sys)('font')
sys.modules['tkinter'].scrolledtext = type(sys)('scrolledtext')

# Now import the tool
from brand_review_tool import BrandReviewTool

# Create a mock root
root = MockTk()

# Create tool instance but skip GUI setup
tool = BrandReviewTool.__new__(BrandReviewTool)
tool.root = root
tool.unknown_ads = []
tool.current_index = 0
tool.lexicon_path = "config/brands.json"
tool.lexicon_brands = []
tool.logo_db = None

# Load lexicon
tool.load_lexicon()

# Load unknown brands (this is the key method)
print("Running load_unknown_brands()...")
print("="*80)
tool.load_unknown_brands()

print("\n" + "="*80)
print(f"Total unknown ads found: {len(tool.unknown_ads)}")

if tool.unknown_ads:
    print("\nFirst 5 unknown ads:")
    for i, ad_info in enumerate(tool.unknown_ads[:5], 1):
        print(f"\n{i}. {ad_info['json_file']}")
        print(f"   Type: {ad_info['ad'].get('type')}")
        print(f"   Brand: {ad_info['current_brand']}")
        print(f"   Image: {ad_info['image_path']}")
