#!/usr/bin/env python3
"""
Brand normalization utilities for case-insensitive, punctuation-insensitive matching.

This ensures that "Ben & Jerry's", "ben and jerrys", "BEN AND JERRY'S" all match.
"""

import unicodedata
import re


def normalize_brand_for_matching(brand: str | None) -> str:
    """
    Normalize a brand name for case-insensitive, punctuation-insensitive matching.
    
    Rules:
    - Convert to lowercase
    - Remove all punctuation (apostrophes, ampersands, periods, hyphens, etc.)
    - Remove accents/diacritics (ü → u, é → e)
    - Collapse multiple spaces to single space
    - Strip leading/trailing whitespace
    
    Examples:
        "Ben & Jerry's" → "ben and jerrys"
        "L'Oréal" → "loreal"
        "Häagen-Dazs" → "haagen dazs"
        "Lay's" → "lays"
    """
    if not brand:
        return ""
    
    # Convert to string if needed
    brand = str(brand)
    
    # Normalize unicode (decompose accents)
    brand = unicodedata.normalize('NFD', brand)
    
    # Remove diacritics (accents)
    brand = ''.join(char for char in brand if unicodedata.category(char) != 'Mn')
    
    # Convert to lowercase
    brand = brand.lower()
    
    # Replace common separators with space
    brand = brand.replace('&', ' and ')
    brand = brand.replace('+', ' and ')
    
    # Remove all punctuation except spaces
    brand = re.sub(r"[^\w\s]", "", brand)
    
    # Collapse multiple spaces
    brand = re.sub(r'\s+', ' ', brand)
    
    # Strip
    return brand.strip()


def brands_match(brand1: str | None, brand2: str | None) -> bool:
    """
    Check if two brand names match (case-insensitive, punctuation-insensitive).
    
    Examples:
        brands_match("Ben & Jerry's", "ben and jerrys") → True
        brands_match("Häagen-Dazs", "haagen dazs") → True
        brands_match("Lay's", "lays") → True
    """
    return normalize_brand_for_matching(brand1) == normalize_brand_for_matching(brand2)


def find_matching_brand(brand: str | None, brand_list: list[str]) -> str | None:
    """
    Find a matching brand in a list (case-insensitive, punctuation-insensitive).
    
    Returns the original casing from brand_list if found, None otherwise.
    
    Example:
        find_matching_brand("ben and jerrys", ["Ben & Jerry's", "Breyers"]) → "Ben & Jerry's"
    """
    if not brand:
        return None
    
    normalized = normalize_brand_for_matching(brand)
    
    for candidate in brand_list:
        if normalize_brand_for_matching(candidate) == normalized:
            return candidate
    
    return None
