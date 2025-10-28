#!/usr/bin/env python3
"""
Test script to verify brand extraction properly filters promotional terms
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from archived.kroger_ad_core import _brand_from_token, _extract_kroger_advertiser

def test_promotional_terms():
    """Test that promotional terms are rejected"""
    print("Testing promotional term rejection...")
    
    promotional_terms = [
        "Digital Deal",
        "digital deal",
        "DIGITAL DEAL",
        "Shop Now",
        "Buy Now",
        "Save Now",
        "Advertisement",
        "Sponsored",
        "Halloween Treats",
        "Christmas Sale",
        "Limited Time",
        "Exclusive Deal"
    ]
    
    for term in promotional_terms:
        result = _brand_from_token(term)
        status = "✅ PASS" if result is None else f"❌ FAIL (got: {result})"
        print(f"  {term:25s} -> {status}")
    
    print()

def test_valid_brands():
    """Test that valid brands are still recognized"""
    print("Testing valid brand recognition...")
    
    # These should match if they're in the lexicon
    test_brands = [
        "Tide",
        "Crest",
        "Pampers",
        "Gillette",
        "Bounty"
    ]
    
    for brand in test_brands:
        result = _brand_from_token(brand)
        status = "✅ PASS" if result is not None else "⚠️  NOT IN LEXICON"
        print(f"  {brand:25s} -> {status} (got: {result})")
    
    print()

def test_ad_dict_extraction():
    """Test full advertiser extraction from ad dict"""
    print("Testing full advertiser extraction...")
    
    # Test case 1: Ad with "Digital Deal" in message
    ad1 = {
        "message": "Digital Deal - Save on groceries",
        "href": "https://www.kroger.com/search?query=milk"
    }
    result1 = _extract_kroger_advertiser(ad1)
    status1 = "✅ PASS" if result1 is None or result1 != "Digital Deal" else f"❌ FAIL (got: {result1})"
    print(f"  Ad with 'Digital Deal' message: {status1}")
    
    # Test case 2: Ad with brand in URL
    ad2 = {
        "message": "Save on Tide products",
        "href": "https://www.kroger.com/brand/tide"
    }
    result2 = _extract_kroger_advertiser(ad2)
    status2 = "✅ PASS" if result2 == "Tide" else f"⚠️  Got: {result2}"
    print(f"  Ad with Tide in message:        {status2}")
    
    # Test case 3: Ad with promotional alt_text
    ad3 = {
        "alt_text": "Digital Deal Advertisement",
        "message": "Shop Now",
        "href": "https://www.kroger.com/search"
    }
    result3 = _extract_kroger_advertiser(ad3)
    status3 = "✅ PASS" if result3 is None or result3 not in ["Digital Deal", "Shop Now"] else f"❌ FAIL (got: {result3})"
    print(f"  Ad with promotional alt_text:   {status3}")
    
    print()

if __name__ == "__main__":
    print("=" * 60)
    print("Brand Extraction Test Suite")
    print("=" * 60)
    print()
    
    test_promotional_terms()
    test_valid_brands()
    test_ad_dict_extraction()
    
    print("=" * 60)
    print("Test suite complete!")
    print("=" * 60)
