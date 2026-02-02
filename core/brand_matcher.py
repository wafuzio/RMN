#!/usr/bin/env python3
"""
Enhanced Brand Matcher - Intelligent brand matching with confidence scoring

Reduces manual review by using multiple matching strategies:
- Exact match (canonical + synonyms)
- Fuzzy matching with Levenshtein distance
- Common abbreviation patterns
- Brand name normalization
"""

import re
from difflib import SequenceMatcher
from typing import Optional, Tuple, List
import json
from pathlib import Path


class BrandMatcher:
    def __init__(self, lexicon_path: str = "config/brands.json"):
        self.lexicon_path = Path(lexicon_path)
        self.brands = []
        self.name_to_brand = {}  # All names (canonical + synonyms) → brand entry
        self.load_lexicon()
    
    def load_lexicon(self):
        """Load brand lexicon and build lookup maps"""
        if not self.lexicon_path.exists():
            return
        
        with open(self.lexicon_path, 'r', encoding='utf-8') as f:
            self.brands = json.load(f)
        
        # Build fast lookup map
        for brand in self.brands:
            canonical = brand.get("name", "")
            if not canonical:
                continue
            
            # Map canonical name
            self.name_to_brand[canonical.lower()] = brand
            
            # Map all synonyms
            for syn in brand.get("synonyms", []):
                self.name_to_brand[syn.lower()] = brand
    
    def normalize(self, text: str) -> str:
        """Normalize brand name for matching"""
        if not text:
            return ""
        
        text = text.lower().strip()
        
        # Remove common suffixes/prefixes
        text = re.sub(r'\b(inc|llc|ltd|corp|co|the)\b\.?', '', text)
        
        # Normalize punctuation
        text = text.replace("'", "").replace("'", "").replace("`", "")
        text = text.replace(".", "")
        text = text.replace(" & ", " and ").replace("&", " and ")
        
        # Remove extra whitespace
        text = " ".join(text.split())
        
        return text
    
    def similarity_score(self, s1: str, s2: str) -> float:
        """Calculate similarity between two strings (0.0 to 1.0)"""
        if not s1 or not s2:
            return 0.0
        
        # Exact match
        if s1 == s2:
            return 1.0
        
        # Normalized exact match
        n1 = self.normalize(s1)
        n2 = self.normalize(s2)
        if n1 == n2:
            return 0.98
        
        # One contains the other (likely variant)
        if n1 in n2 or n2 in n1:
            return 0.90
        
        # Sequence matcher (Levenshtein-like)
        return SequenceMatcher(None, n1, n2).ratio()
    
    def check_abbreviation(self, abbrev: str, full_name: str) -> bool:
        """Check if abbrev could be an abbreviation of full_name"""
        abbrev = abbrev.lower().replace(" ", "")
        
        # Get initials from full name
        words = full_name.lower().split()
        initials = "".join(w[0] for w in words if w)
        
        if abbrev == initials:
            return True
        
        # Check if abbrev is first letters of each word
        if len(abbrev) == len(words):
            if all(abbrev[i] == words[i][0] for i in range(len(abbrev))):
                return True
        
        return False
    
    def match(self, brand_text: str, threshold: float = 0.70) -> Tuple[Optional[dict], float, str]:
        """
        Match brand text to canonical brand.
        
        CONSERVATIVE APPROACH:
        - Only exact matches (canonical or synonym) are high confidence
        - Fuzzy matches are for SUGGESTIONS ONLY, not auto-assignment
        - Always prefer manual review over incorrect auto-assignment
        
        Returns:
            (brand_entry, confidence_score, match_type)
            - brand_entry: The matched brand dict or None
            - confidence_score: 0.0 to 1.0
            - match_type: "exact", "synonym", "fuzzy", "abbreviation", or "none"
        """
        if not brand_text:
            return None, 0.0, "none"
        
        brand_lower = brand_text.lower().strip()
        
        # 1. Exact match (canonical or synonym) - ONLY HIGH CONFIDENCE CASE
        if brand_lower in self.name_to_brand:
            return self.name_to_brand[brand_lower], 1.0, "exact"
        
        # 2. Normalized exact match - Still very high confidence
        normalized = self.normalize(brand_text)
        for name, brand in self.name_to_brand.items():
            if self.normalize(name) == normalized:
                return brand, 0.98, "synonym"
        
        # 3. Fuzzy matching - SUGGESTIONS ONLY, cap at 0.75 max confidence
        # This ensures fuzzy matches NEVER trigger auto-assignment
        best_match = None
        best_score = 0.0
        best_type = "none"
        
        for name, brand in self.name_to_brand.items():
            score = self.similarity_score(brand_text, name)
            
            # Cap fuzzy match confidence at 0.75 to prevent auto-assignment
            if score > 0.85:
                score = 0.75  # Force manual review for fuzzy matches
            
            if score > best_score:
                best_score = score
                best_match = brand
                best_type = "fuzzy"
        
        # 4. Check abbreviation patterns - Medium confidence, requires review
        for brand in self.brands:
            canonical = brand.get("name", "")
            if self.check_abbreviation(brand_text, canonical):
                # Abbreviation match is medium confidence - needs review
                if best_score < 0.70:
                    best_match = brand
                    best_score = 0.70  # Medium confidence, not auto-assign
                    best_type = "abbreviation"
        
        # Only return if above threshold
        if best_score >= threshold:
            return best_match, best_score, best_type
        
        return None, best_score, "none"
    
    def get_suggestions(self, brand_text: str, limit: int = 5) -> List[Tuple[dict, float, str]]:
        """
        Get top N brand suggestions for manual review.
        
        Returns list of (brand_entry, confidence_score, match_type) tuples.
        """
        suggestions = []
        
        for brand in self.brands:
            canonical = brand.get("name", "")
            score = self.similarity_score(brand_text, canonical)
            
            # Also check synonyms
            for syn in brand.get("synonyms", []):
                syn_score = self.similarity_score(brand_text, syn)
                score = max(score, syn_score)
            
            if score > 0.3:  # Minimum threshold for suggestions
                match_type = "fuzzy" if score < 0.98 else "synonym"
                suggestions.append((brand, score, match_type))
        
        # Sort by score descending
        suggestions.sort(key=lambda x: x[1], reverse=True)
        
        return suggestions[:limit]


# Example usage
if __name__ == "__main__":
    matcher = BrandMatcher()
    
    test_cases = [
        "Annie Chun's",      # Exact
        "ACHUN",             # Abbreviation
        "Annie Chuns",       # Close variant
        "Barilla Pasta",     # Synonym
        "Coca Cola",         # Should match Coca-Cola
        "Unknown Brand XYZ"  # No match
    ]
    
    print("=== Brand Matching Test ===\n")
    for test in test_cases:
        brand, confidence, match_type = matcher.match(test)
        
        if brand:
            print(f"Input: '{test}'")
            print(f"  → Matched: {brand['name']}")
            print(f"  → Confidence: {confidence:.2%}")
            print(f"  → Type: {match_type}")
        else:
            print(f"Input: '{test}'")
            print(f"  → No match (best score: {confidence:.2%})")
        print()
