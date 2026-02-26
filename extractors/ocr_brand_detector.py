#!/usr/bin/env python3
"""
OCR-based Brand Detection for Co-branded Ads

Detects multiple brand names from ad screenshots using OCR to identify
co-branded advertisements (e.g., Herdez + Jennie-O).
"""

import re
import sys
from pathlib import Path
from typing import List, Optional
from PIL import Image, ImageEnhance

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _run_ocr(image_path: str) -> str:
    """Run OCR on an image and return the extracted text."""
    try:
        import pytesseract
    except ImportError:
        return ""
    
    try:
        img = Image.open(image_path)
        enhancer = ImageEnhance.Contrast(img)
        img_enhanced = enhancer.enhance(2.0)
        return pytesseract.image_to_string(img_enhanced)
    except Exception as e:
        print(f"⚠️ OCR failed: {e}")
        return ""


def lexicon_match_from_text(text: str) -> Optional[str]:
    """
    Scan OCR text against the brand lexicon to find known brands.
    Returns the canonical name of the best (longest) match, or None.
    """
    try:
        from core.brands import canonicalize
    except ImportError:
        return None
    
    if not text or len(text.strip()) < 3:
        return None
    
    # Normalize whitespace
    clean = re.sub(r'\s+', ' ', text).strip()
    
    # Try progressively shorter n-grams (4 words down to 1)
    words = clean.split()
    best = None
    best_len = 0
    
    for start in range(len(words)):
        for n in range(min(4, len(words) - start), 0, -1):
            candidate = " ".join(words[start:start + n])
            # Strip punctuation from edges
            candidate = re.sub(r'^[^\w]+|[^\w]+$', '', candidate).strip()
            if len(candidate) < 3:
                continue
            canon = canonicalize(candidate)
            if canon and canon.lower() != 'unknown':
                # Prefer longer matches
                if len(canon) > best_len:
                    best = canon
                    best_len = len(canon)
                # Once we find a match starting at this position, skip ahead
                break
    
    return best


def detect_brand_from_image_for_display(image_path: str) -> Optional[str]:
    """
    OCR fallback for Sponsored Display ads.
    Runs OCR on the screenshot and tries lexicon matching on the full text.
    Returns a single canonical brand name or None.
    """
    text = _run_ocr(image_path)
    if not text:
        return None
    
    # Try lexicon matching first (most reliable)
    brand = lexicon_match_from_text(text)
    if brand:
        return brand
    
    # Fall back to copyright/trademark pattern extraction
    pattern_brands = extract_brands_from_text(text)
    if pattern_brands:
        # Try to canonicalize the first pattern match
        try:
            from core.brands import canonicalize
            for b in pattern_brands:
                canon = canonicalize(b)
                if canon and canon.lower() != 'unknown':
                    return canon
        except ImportError:
            pass
        return pattern_brands[0]
    
    return None


def detect_brands_from_image(image_path: str) -> List[str]:
    """
    Detect brand names from an ad image using OCR.
    
    Looks for:
    - Copyright notices (©2025 Brand Name)
    - Known brand patterns
    - Lexicon matches against OCR text
    
    Args:
        image_path: Path to the image file
        
    Returns:
        List of detected brand names (empty if none found)
    """
    text = _run_ocr(image_path)
    if not text:
        return []
    
    brands = extract_brands_from_text(text)
    
    # Also try lexicon matching
    lexicon_brand = lexicon_match_from_text(text)
    if lexicon_brand and not any(b.lower() == lexicon_brand.lower() for b in brands):
        brands.append(lexicon_brand)
    
    return brands


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
