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
    # Tokenize display text and fuzzy match tokens against synonyms
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9&''\-]+", text)
    choices = list(_SYNONYM_TO_CANON.keys())
    for t in tokens:
        m = get_close_matches(t.lower(), choices, n=1, cutoff=0.86)
        if m:
            return _SYNONYM_TO_CANON[m[0]]
    return None
