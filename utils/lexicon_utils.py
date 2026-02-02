"""
Lexicon Utilities

Shared functions for validating and cleaning the brand lexicon (config/brands.json)
to prevent duplicates and synonym conflicts.
"""

import json
import os
from typing import List, Dict, Set

BLACKLIST_PATH = "config/brand_blacklist.json"


def load_blacklist() -> Set[str]:
    """Load blacklisted brand names (lowercase)."""
    try:
        if os.path.exists(BLACKLIST_PATH):
            with open(BLACKLIST_PATH, 'r') as f:
                data = json.load(f)
            return set(data.get('brands', []))
    except Exception:
        pass
    return set()


def is_blacklisted(brand_name: str) -> bool:
    """Check if a brand name is blacklisted."""
    if not brand_name:
        return False
    blacklist = load_blacklist()
    return brand_name.strip().lower() in blacklist


def deduplicate_and_clean_brands(brands: List[Dict]) -> List[Dict]:
    """
    Deduplicate brands and ensure no synonyms exist as main brand names.
    Also filters out blacklisted brands.
    
    Args:
        brands: List of brand dictionaries with 'name' and 'synonyms' keys
        
    Returns:
        Cleaned and deduplicated list of brands
    """
    # Load blacklist once
    blacklist = load_blacklist()
    
    # Step 0: Filter out blacklisted brands
    filtered_brands = []
    for brand in brands:
        if brand['name'].strip().lower() in blacklist:
            print(f"[LEXICON] Rejected blacklisted brand '{brand['name']}'")
            continue
        filtered_brands.append(brand)
    
    # Step 1: Deduplicate brands by name (case-insensitive)
    seen_names = {}
    deduplicated = []
    
    for brand in filtered_brands:
        name_lower = brand['name'].lower()
        if name_lower in seen_names:
            # Merge synonyms into the first occurrence
            existing = seen_names[name_lower]
            for syn in brand['synonyms']:
                if syn not in existing['synonyms']:
                    existing['synonyms'].append(syn)
            print(f"[LEXICON] Merged duplicate brand '{brand['name']}' into '{existing['name']}'")
        else:
            seen_names[name_lower] = brand
            deduplicated.append(brand)
    
    # Step 2: Remove any synonym that exists as a main brand name
    all_brand_names = {b['name'] for b in deduplicated}
    all_brand_names_lower = {name.lower() for name in all_brand_names}
    
    for brand in deduplicated:
        original_synonyms = brand['synonyms'].copy()
        # Filter out synonyms that are main brands OR blacklisted
        brand['synonyms'] = [
            syn for syn in brand['synonyms']
            if syn.lower() not in all_brand_names_lower and syn.strip().lower() not in blacklist
        ]
        
        # Log if we removed any
        removed = set(original_synonyms) - set(brand['synonyms'])
        for syn in removed:
            if syn.strip().lower() in blacklist:
                print(f"[LEXICON] Removed blacklisted synonym '{syn}' from '{brand['name']}'")
            else:
                print(f"[LEXICON] Removed synonym '{syn}' from '{brand['name']}' (exists as main brand)")
    
    return deduplicated


def save_lexicon(brands: List[Dict], lexicon_path: str):
    """
    Save brands to lexicon file with validation and sorting.
    
    Args:
        brands: List of brand dictionaries
        lexicon_path: Path to brands.json file
    """
    # Clean and deduplicate
    cleaned_brands = deduplicate_and_clean_brands(brands)
    
    # Sort alphabetically by name (case-insensitive)
    brands_sorted = sorted(cleaned_brands, key=lambda x: x['name'].lower())
    
    # Save
    with open(lexicon_path, 'w', encoding='utf-8') as f:
        json.dump(brands_sorted, f, indent=2, ensure_ascii=False)
    
    return brands_sorted
