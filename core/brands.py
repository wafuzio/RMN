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
PARENT_COMPANIES_PATH = PROJECT_ROOT / "config" / "parent_companies.json"
BLACKLIST_PATH = PROJECT_ROOT / "config" / "brand_blacklist.json"

_CACHE: list[dict] | None = None
_BLACKLIST: set[str] | None = None  # Lowercase brand names to skip
_SYNONYM_TO_CANON: dict[str, str] = {}
_NORMALIZED_TO_CANON: dict[str, str] = {}
_AMBIGUOUS_BRANDS: set[str] = set()  # Brands that need manual approval when matched
_PARENT_COMPANY_CACHE: dict[str, dict] | None = None  # brand_name_lower -> company info

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
    brand = brand.replace("'", '')   # Remove apostrophe (Nellie's -> Nellies)
    brand = brand.replace("'", '')   # Remove curly apostrophe too
    brand = brand.replace('.', '')   # Remove periods (Dr. Pepper -> Dr Pepper)
    brand = brand.replace('-', ' ')  # Replace hyphen with space
    brand = brand.replace('_', ' ')  # Replace underscore with space

    # Remove all remaining punctuation except spaces and alphanumerics
    brand = re.sub(r"[^\w\s]", "", brand)
    
    # Remove underscores that survived (since \w includes underscore)
    brand = brand.replace('_', ' ')

    # Collapse multiple spaces
    brand = re.sub(r'\s+', ' ', brand)

    # Strip
    return brand.strip()


def _load_blacklist() -> set[str]:
    """Load blacklisted brand names (case-insensitive)."""
    global _BLACKLIST
    if _BLACKLIST is not None:
        return _BLACKLIST
    try:
        with open(BLACKLIST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        _BLACKLIST = {b.lower().strip() for b in data.get("brands", [])}
    except Exception:
        _BLACKLIST = set()
    return _BLACKLIST


def is_blacklisted(brand_name: str | None) -> bool:
    """
    Check if a brand name is blacklisted (house ads, retailer brands, etc.).
    Case-insensitive matching.
    
    Use this to skip saving/displaying ads for blacklisted brands.
    """
    if not brand_name:
        return False
    blacklist = _load_blacklist()
    return brand_name.lower().strip() in blacklist


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
    
    # Reject URLs and other invalid brand patterns
    text_stripped = text.strip()
    if text_stripped.startswith(('http://', 'https://', 'www.')) or '.com' in text_stripped.lower():
        return None
    
    low = text_stripped.lower()
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


def get_brand_from_ad(ad: dict) -> str | None:
    """
    Extract brand from an ad object using consistent field priority.
    
    Checks canonical 'brand' field first, then falls back to 'advertisers' array.
    This ensures consistent behavior across all tools regardless of which
    field the scraper populated.
    
    Args:
        ad: Ad dictionary from JSON
        
    Returns:
        Brand name string, or None if no valid brand found
    """
    # Primary: canonical 'brand' field
    brand = ad.get('brand')
    if brand and isinstance(brand, str) and brand.lower() not in ('unknown', ''):
        return brand
    
    # Fallback: first advertiser from array
    advertisers = ad.get('advertisers', [])
    if advertisers and isinstance(advertisers, list) and len(advertisers) > 0:
        first_adv = advertisers[0]
        if first_adv and isinstance(first_adv, str) and first_adv.lower() not in ('unknown', ''):
            return first_adv
    
    return None


def _load_parent_companies() -> dict[str, dict]:
    """Load parent company database and build brand->company lookup cache."""
    global _PARENT_COMPANY_CACHE
    
    if _PARENT_COMPANY_CACHE is not None:
        return _PARENT_COMPANY_CACHE
    
    _PARENT_COMPANY_CACHE = {}
    
    if not PARENT_COMPANIES_PATH.exists():
        return _PARENT_COMPANY_CACHE
    
    try:
        with open(PARENT_COMPANIES_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        for company in data.get('companies', []):
            company_info = {
                'id': company.get('id'),
                'name': company.get('name')
            }
            for brand in company.get('brands', []):
                _PARENT_COMPANY_CACHE[brand.lower()] = company_info
    except Exception as e:
        print(f"Warning: Could not load parent companies: {e}")
    
    return _PARENT_COMPANY_CACHE


def get_parent_company(brand_name: str) -> dict | None:
    """
    Get the parent company for a brand.
    
    Args:
        brand_name: The brand name to look up
        
    Returns:
        Dict with 'id' and 'name' of parent company, or None if not found
    """
    if not brand_name:
        return None
    
    cache = _load_parent_companies()
    return cache.get(brand_name.lower())


def get_all_parent_companies() -> list[dict]:
    """Get list of all parent companies."""
    if not PARENT_COMPANIES_PATH.exists():
        return []
    
    try:
        with open(PARENT_COMPANIES_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('companies', [])
    except Exception:
        return []


def get_brands_by_parent(parent_id: str) -> list[str]:
    """Get all brands owned by a parent company."""
    companies = get_all_parent_companies()
    for company in companies:
        if company.get('id') == parent_id:
            return company.get('brands', [])
    return []


def add_brand_to_parent(brand_name: str, parent_id: str) -> bool:
    """Add a brand to a parent company's brand list."""
    global _PARENT_COMPANY_CACHE
    
    if not PARENT_COMPANIES_PATH.exists():
        return False
    
    try:
        with open(PARENT_COMPANIES_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        for company in data.get('companies', []):
            if company.get('id') == parent_id:
                if brand_name not in company.get('brands', []):
                    company.setdefault('brands', []).append(brand_name)
                    
                    with open(PARENT_COMPANIES_PATH, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    
                    # Invalidate cache
                    _PARENT_COMPANY_CACHE = None
                    return True
                return False  # Already exists
        
        return False  # Parent not found
    except Exception as e:
        print(f"Warning: Could not add brand to parent: {e}")
        return False
