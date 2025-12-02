"""
Brand canonicalization helper - shared by capture and JSON generation.
Returns canonical brand names from text using a lexicon.
"""
from __future__ import annotations
import json
import re
import unicodedata
from difflib import get_close_matches
from pathlib import Path

# Resolve /config/brands.json next to repository root
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BRANDS_PATH = PROJECT_ROOT / "config" / "brands.json"

_CACHE: list[dict] | None = None
_SYNONYM_TO_CANON: dict[str, str] = {}
_NORMALIZED_TO_CANON: dict[str, str] = {}
_AMBIGUOUS_BRANDS: set[str] = set()  # Brands that need manual approval when matched

def _normalize_brand(brand: str | None) -> str:
    """
    Normalize a brand name for matching.
    Removes apostrophes, hyphens, accents, and converts to lowercase.
    """
    if not brand:
        return ""

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
    brand = brand.replace("'", ' ')  # Replace apostrophe with space
    brand = brand.replace('-', ' ')  # Replace hyphen with space

    # Remove all remaining punctuation except spaces
    brand = re.sub(r"[^\w\s]", "", brand)

    # Collapse multiple spaces
    brand = re.sub(r'\s+', ' ', brand)

    # Strip
    return brand.strip()

def _load():
    global _CACHE, _SYNONYM_TO_CANON, _NORMALIZED_TO_CANON, _AMBIGUOUS_BRANDS
    if _CACHE is not None:
        return
    try:
        with open(BRANDS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        # Minimal seed; extend via config/brands.json
        data = [
            {"name": "Bomb Pop", "synonyms": ["BombPop", "Bomb-Pop"]},
            {"name": "Go-GURT", "synonyms": ["GoGurt", "Gogurt"]},
            {"name": "Nature's Bounty", "synonyms": ["Natures Bounty", "NBTY"]},
            {"name": "Yoplait", "synonyms": []},
            {"name": "Kroger", "synonyms": []},
        ]
    _CACHE = data
    _SYNONYM_TO_CANON.clear()
    _NORMALIZED_TO_CANON.clear()
    _AMBIGUOUS_BRANDS.clear()
    for b in data:
        canonical_name = b["name"]
        # Track ambiguous brands (need manual approval)
        if b.get("ambiguous"):
            _AMBIGUOUS_BRANDS.add(canonical_name)
        # Build both exact-match and normalized dictionaries
        for s in [canonical_name, *b.get("synonyms", [])]:
            # Exact match (case-insensitive)
            _SYNONYM_TO_CANON[s.lower()] = canonical_name
            # Normalized match (removes apostrophes, hyphens, accents)
            normalized = _normalize_brand(s)
            if normalized:
                _NORMALIZED_TO_CANON[normalized] = canonical_name

def canonicalize(text: str | None, mark_ambiguous: bool = True) -> str | None:
    """Return canonical brand name from free text (header/message), else None.
    
    Args:
        text: The text to search for brand names
        mark_ambiguous: If True, ambiguous brands are returned with "(?)" suffix
                       to indicate they need manual approval
    
    Returns:
        Canonical brand name, or brand name with "(?) suffix if ambiguous
    """
    _load()
    if not text:
        return None
    low = text.strip().lower()
    if low in _SYNONYM_TO_CANON:
        brand = _SYNONYM_TO_CANON[low]
        if mark_ambiguous and brand in _AMBIGUOUS_BRANDS:
            return f"{brand}(?)"
        return brand

    # Try normalized matching (handles apostrophes, hyphens, accents)
    normalized = _normalize_brand(text)
    if normalized and normalized in _NORMALIZED_TO_CANON:
        brand = _NORMALIZED_TO_CANON[normalized]
        if mark_ambiguous and brand in _AMBIGUOUS_BRANDS:
            return f"{brand}(?)"
        return brand
    
    # Common words to skip (not real brands in this context)
    SKIP_WORDS = {
        'now', 'shop', 'save', 'buy', 'get', 'free', 'new', 'all', 'more', 
        'today', 'here', 'click', 'learn', 'find', 'see', 'view', 'explore',
    }
    
    # Check for multi-word brand names (case-insensitive substring match)
    # Sort by length descending to match longer brands first (e.g., "Muscle Milk" before "Milk")
    sorted_brands = sorted(_SYNONYM_TO_CANON.keys(), key=len, reverse=True)
    for brand_key in sorted_brands:
        # Skip ONLY if the brand is exactly a common word (not if it contains it)
        # e.g., skip "now" but not "Nutrition Now!" or "Now Foods"
        if brand_key.lower() in SKIP_WORDS and len(brand_key.split()) == 1:
            continue
            
        # Check multi-word brands or brands with special characters
        if ' ' in brand_key or '-' in brand_key or '&' in brand_key or 'ö' in brand_key or 'ü' in brand_key or '!' in brand_key:
            # Check if brand appears in text (case-insensitive, word boundary aware)
            pattern = r'\b' + re.escape(brand_key) + r'\b'
            if re.search(pattern, low, re.IGNORECASE):
                brand = _SYNONYM_TO_CANON[brand_key]
                if mark_ambiguous and brand in _AMBIGUOUS_BRANDS:
                    return f"{brand}(?)"
                return brand
    
    # Tokenize display text and fuzzy match tokens against synonyms
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9&''\-]+", text)
    choices = list(_SYNONYM_TO_CANON.keys())
    for t in tokens:
        tok = t.lower()
        # Skip common words
        if tok in SKIP_WORDS:
            continue
        # Avoid using very short tokens (3-4 chars) for fuzzy brand matching,
        # since they are often generic words (e.g., "blue") and collide with
        # unrelated brand names (e.g., "Bluey"). Exact matches are already
        # handled earlier via _SYNONYM_TO_CANON.
        if len(tok) <= 4:
            continue
        m = get_close_matches(tok, choices, n=1, cutoff=0.86)
        if m:
            brand = _SYNONYM_TO_CANON[m[0]]
            if mark_ambiguous and brand in _AMBIGUOUS_BRANDS:
                return f"{brand}(?)"
            return brand
    return None


def add_brand(brand_name: str) -> bool:
    """
    Add a new brand to the lexicon if it doesn't already exist.
    Uses the shared save_lexicon utility for consistency with other tools.
    
    Args:
        brand_name: The brand name to add (will be title-cased)
        
    Returns:
        True if brand was added, False if it already exists or is invalid
    """
    if not brand_name or brand_name.lower() in ('unknown', ''):
        return False
    
    _load()
    
    # Check if brand already exists (exact or normalized match)
    if canonicalize(brand_name):
        return False  # Already in lexicon
    
    # Clean up brand name - title case, strip whitespace
    clean_name = brand_name.strip().title()
    
    # Don't add very short names (likely noise)
    if len(clean_name) < 2:
        return False
    
    # Add to lexicon file using shared utility
    try:
        from utils.lexicon_utils import save_lexicon
        
        with open(BRANDS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Check again in file (in case cache is stale)
        existing_names = {b["name"].lower() for b in data}
        if clean_name.lower() in existing_names:
            return False
        
        # Add new brand
        data.append({
            "name": clean_name,
            "synonyms": []
        })
        
        # Save using shared utility (handles deduplication and sorting)
        save_lexicon(data, str(BRANDS_PATH))
        
        # Invalidate cache so next canonicalize() call reloads
        global _CACHE
        _CACHE = None
        
        return True
    except Exception as e:
        print(f"Warning: Could not add brand to lexicon: {e}")
        return False
