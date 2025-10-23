#!/usr/bin/env python3
"""
OCR-based Brand Detection for Co-branded Ads

Detects multiple brand names from ad screenshots using OCR to identify
co-branded advertisements (e.g., Herdez + Jennie-O).
"""

import re
from typing import List, Optional
from PIL import Image, ImageEnhance


def detect_brands_from_image(image_path: str) -> List[str]:
    """
    Detect brand names from an ad image using OCR.
    
    Looks for:
    - Copyright notices (©2025 Brand Name)
    - Known brand patterns
    
    Args:
        image_path: Path to the image file
        
    Returns:
        List of detected brand names (empty if none found)
    """
    try:
        import pytesseract
    except ImportError:
        print("⚠️ pytesseract not installed, skipping OCR brand detection")
        return []
    
    try:
        # Open and enhance image for better OCR
        img = Image.open(image_path)
        enhancer = ImageEnhance.Contrast(img)
        img_enhanced = enhancer.enhance(2.0)
        
        # Run OCR
        text = pytesseract.image_to_string(img_enhanced)
        
        # Extract brands from copyright notices
        brands = extract_brands_from_text(text)
        
        return brands
        
    except Exception as e:
        print(f"⚠️ OCR brand detection failed: {e}")
        return []


def extract_brands_from_text(text: str) -> List[str]:
    """
    Extract brand names from OCR text.
    
    Looks for patterns like:
    - ©2025 Brand Name, LLC
    - ©2025 Brand Name
    - Copyright Brand Name
    - Brand Name® (registered trademark)
    - Brand Name™ (trademark)
    
    Args:
        text: OCR extracted text
        
    Returns:
        List of unique brand names
    """
    brands = set()
    
    # Pattern 1: Copyright with year and company name
    # ©2025 MegaMex Foods, LLC | ©2025 Jennie-O Turkey Store
    # More greedy pattern to capture full brand names including hyphens
    copyright_pattern = r'©\s*\d{4}\s+([A-Z][A-Za-z0-9&\s\'-]+?)(?:,|\s+LLC|\s+Inc|\s+Corp|\s+Co\.|\s*\||$)'
    matches = re.findall(copyright_pattern, text)
    for match in matches:
        brand = match.strip()
        # Clean up common suffixes and extra words
        brand = re.sub(r'\s+(LLC|Inc|Corp|Co|Foods|Turkey|Store|Stores).*$', '', brand, flags=re.IGNORECASE)
        brand = brand.strip()
        if brand and len(brand) > 2 and not brand.lower() in ['the', 'and', 'or']:
            brands.add(brand)
    
    # Pattern 2: Trademark symbols (® or ™)
    # Pull-Ups® | Magic Spoon™ | Brand Name®
    # Look for capitalized words followed by ® or ™
    trademark_pattern = r'([A-Z][A-Za-z0-9&\s\'-]+?)[®™]'
    matches = re.findall(trademark_pattern, text)
    for match in matches:
        brand = match.strip()
        # Clean up extra words after the brand
        # Keep hyphenated brands like "Pull-Ups" intact
        if brand and len(brand) > 2 and not brand.lower() in ['the', 'and', 'or', 'select', 'buy', 'save']:
            brands.add(brand)
    
    # Pattern 2: Map parent companies to consumer brands
    brand_mapping = {
        'MegaMex': 'Herdez',
        'Hormel': 'Jennie-O',
        'Jennie-': 'Jennie-O',  # OCR sometimes breaks this
        'Kraft Heinz': 'Kraft Heinz',
        'Unilever': 'Unilever',
        'Procter & Gamble': 'P&G',
    }
    
    # Apply brand mapping and clean up
    final_brands = set()
    for brand in brands:
        # Check if this brand should be mapped to a consumer brand
        mapped = False
        for parent, consumer_brand in brand_mapping.items():
            if parent.lower() in brand.lower():
                final_brands.add(consumer_brand)
                mapped = True
                break
        if not mapped:
            final_brands.add(brand)
    
    # Also check full text for brand mentions
    for parent, consumer_brand in brand_mapping.items():
        if parent.lower() in text.lower():
            final_brands.add(consumer_brand)
    
    return sorted(list(final_brands))


def update_ad_with_ocr_brands(ad_dict: dict, image_path: str) -> dict:
    """
    Update an ad dictionary with OCR-detected brands.
    
    If multiple brands are detected, updates the 'advertisers' field.
    
    Args:
        ad_dict: Ad dictionary with 'advertisers' field
        image_path: Path to the ad screenshot
        
    Returns:
        Updated ad dictionary
    """
    detected_brands = detect_brands_from_image(image_path)
    
    if not detected_brands:
        return ad_dict
    
    # Get existing advertisers
    existing = ad_dict.get('advertisers', [])
    
    # Merge detected brands with existing (avoid duplicates)
    all_brands = list(existing) if existing else []
    for brand in detected_brands:
        # Case-insensitive check for duplicates
        if not any(b.lower() == brand.lower() for b in all_brands):
            all_brands.append(brand)
    
    # Update if we found additional brands
    if len(all_brands) > len(existing if existing else []):
        ad_dict['advertisers'] = all_brands
        print(f"✓ OCR detected co-branded ad: {' + '.join(all_brands)}")
    
    return ad_dict


if __name__ == "__main__":
    # Test with the cheese_dip TOA image
    import sys
    test_image = "/Users/dan.maguire/Documents/Amazon_Scrape/output/kroger/cheese_dip/TOA/kroger__unknown__toa__unknown__cheese_dip__D2025-10-12_T19-20.33_1.png"
    
    print("Testing OCR brand detection...")
    brands = detect_brands_from_image(test_image)
    print(f"Detected brands: {brands}")
