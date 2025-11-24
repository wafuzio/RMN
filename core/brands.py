"""
Brand canonicalization helper - shared by capture and JSON generation.
Returns canonical brand names from text using a lexicon.
"""
from __future__ import annotations
import json
import re
from difflib import get_close_matches
from pathlib import Path

# Resolve /config/brands.json next to repository root
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BRANDS_PATH = PROJECT_ROOT / "config" / "brands.json"

_CACHE: list[dict] | None = None
_SYNONYM_TO_CANON: dict[str, str] = {}

def _load():
    global _CACHE, _SYNONYM_TO_CANON
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
    for b in data:
        for s in [b["name"], *b.get("synonyms", [])]:
            _SYNONYM_TO_CANON[s.lower()] = b["name"]

def canonicalize(text: str | None) -> str | None:
    """Return canonical brand name from free text (header/message), else None."""
    _load()
    if not text:
        return None
    low = text.strip().lower()
    if low in _SYNONYM_TO_CANON:
        return _SYNONYM_TO_CANON[low]
    
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
                return _SYNONYM_TO_CANON[brand_key]
    
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
            return _SYNONYM_TO_CANON[m[0]]
    return None
