#!/usr/bin/env python3
"""
Lexicon Gap Report - Find brands in brand_index missing from config/brands.json

This tool compares the brand_index (built from actual scraped ads) against
the canonical brand lexicon and reports:
1. Brands in index but NOT in lexicon (need review/addition)
2. Brands in lexicon but NOT in index (possibly unused)

Usage:
    python3 tools/lexicon_gap_report.py [--add-missing] [--min-count N]
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BRAND_INDEX = PROJECT_ROOT / "output" / "brand_index.json"
BRAND_LEXICON = PROJECT_ROOT / "config" / "brands.json"
BLACKLIST_PATH = PROJECT_ROOT / "config" / "brand_blacklist.json"


def normalize_brand_key(brand: str) -> str:
    """Normalize brand name to a consistent key for matching.
    
    Collapses minor variations like:
    - "Dr. Pepper" vs "Dr Pepper" vs "dr pepper"
    - "Lay's" vs "Lays"
    - "Ben & Jerry's" vs "Ben and Jerrys"
    """
    if not brand:
        return ""
    
    s = brand.strip().lower()
    # Remove periods (Dr. -> Dr)
    s = s.replace(".", "")
    # Normalize apostrophes and quotes
    s = s.replace("'", "").replace("'", "").replace("`", "")
    # Normalize ampersands
    s = s.replace(" & ", " and ").replace("&", " and ")
    # Collapse multiple spaces
    s = " ".join(s.split())
    return s


def load_blacklist():
    """Load the brand blacklist"""
    if BLACKLIST_PATH.exists():
        try:
            return json.loads(BLACKLIST_PATH.read_text())
        except Exception:
            pass
    return {"brands": []}


def is_blacklisted(brand_name):
    """Check if a brand is blacklisted.
    
    Matches against:
    1. Exact case-insensitive match (for MSG: prefixed messages)
    2. Normalized match (for brand name variations)
    """
    blacklist = load_blacklist()
    brands_list = blacklist.get("brands", [])
    
    # Exact case-insensitive match (important for MSG: strings)
    brand_lower = brand_name.strip().lower()
    if brand_lower in [b.lower() for b in brands_list]:
        return True
    
    # Normalized match (for brand variations like Dr. Pepper vs Dr Pepper)
    normalized = normalize_brand_key(brand_name)
    return normalized in [normalize_brand_key(b) for b in brands_list]


def load_brand_index():
    """Load brand_index.json and return dict of brand -> count"""
    if not BRAND_INDEX.exists():
        print(f"❌ {BRAND_INDEX} not found. Run: python3 tools/build_brand_index.py")
        sys.exit(1)
    
    data = json.loads(BRAND_INDEX.read_text())
    index = data.get("index", {})
    
    # Count occurrences per brand (use normalized key)
    brand_counts = {}
    for brand, entries in index.items():
        total_ads = sum(len(e.get("ad_indices", [])) for e in entries)
        norm_key = normalize_brand_key(brand)
        # Merge if normalized key already exists
        if norm_key in brand_counts:
            brand_counts[norm_key]["count"] += total_ads
            brand_counts[norm_key]["runs"] += len(entries)
        else:
            brand_counts[norm_key] = {
                "display": brand,
                "count": total_ads,
                "runs": len(entries)
            }
    return brand_counts


def load_lexicon():
    """Load config/brands.json and return set of all known names (canonical + synonyms)"""
    if not BRAND_LEXICON.exists():
        print(f"❌ {BRAND_LEXICON} not found")
        sys.exit(1)
    
    data = json.loads(BRAND_LEXICON.read_text())
    
    known = {}  # normalized key -> canonical name
    canonical_names = set()
    
    for entry in data:
        name = entry.get("name", "").strip()
        if not name:
            continue
        
        canonical_names.add(name)
        # Use normalized key for matching
        known[normalize_brand_key(name)] = name
        
        for syn in entry.get("synonyms", []):
            syn = syn.strip()
            if syn:
                known[normalize_brand_key(syn)] = name
    
    return known, canonical_names


def smart_title_case(brand: str) -> str:
    """Convert brand name to proper title case with smart handling.
    
    - Title cases most words
    - Preserves all-caps acronyms (3 letters or less)
    - Handles apostrophes correctly (Lay's, Eggland's)
    - Preserves intentional casing patterns (iPhone, GoGurt)
    """
    if not brand:
        return brand
    
    # Already looks properly cased (has mix of upper/lower)
    if brand[0].isupper() and any(c.islower() for c in brand):
        return brand
    
    words = brand.split()
    result = []
    
    for word in words:
        # Preserve short all-caps (acronyms like GNC, P&G)
        if len(word) <= 3 and word.isupper():
            result.append(word)
        # Handle apostrophes (lay's -> Lay's)
        elif "'" in word:
            parts = word.split("'")
            result.append("'".join(p.capitalize() for p in parts))
        # Handle hyphenated words (good-humor -> Good-Humor)
        elif "-" in word:
            parts = word.split("-")
            result.append("-".join(p.capitalize() for p in parts))
        else:
            result.append(word.capitalize())
    
    return " ".join(result)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Find brands missing from lexicon")
    parser.add_argument("--min-count", type=int, default=1, 
                        help="Minimum ad count to report (default: 1)")
    parser.add_argument("--add-missing", action="store_true",
                        help="Add missing brands to lexicon (interactive)")
    parser.add_argument("--auto-add", action="store_true",
                        help="Auto-add all missing brands to lexicon for review in brand_name_verifier")
    parser.add_argument("--exclude-unknown", action="store_true",
                        help="Exclude 'unknown' brand from auto-add")
    args = parser.parse_args()
    
    print("🔍 Lexicon Gap Report")
    print("=" * 50)
    
    # Load data
    brand_counts = load_brand_index()
    known_brands, canonical_names = load_lexicon()
    
    print(f"📊 Brand Index: {len(brand_counts)} unique brands")
    print(f"📚 Lexicon: {len(canonical_names)} canonical brands, {len(known_brands)} total entries")
    print()
    
    # Find gaps
    missing_from_lexicon = []
    for brand_lower, info in brand_counts.items():
        if brand_lower not in known_brands:
            if info["count"] >= args.min_count:
                missing_from_lexicon.append({
                    "brand": info["display"],
                    "count": info["count"],
                    "runs": info["runs"]
                })
    
    # Sort by count descending
    missing_from_lexicon.sort(key=lambda x: -x["count"])
    
    # Find unused in lexicon
    index_brands_lower = set(brand_counts.keys())
    unused_in_lexicon = []
    for canon in canonical_names:
        if canon.lower() not in index_brands_lower:
            unused_in_lexicon.append(canon)
    
    # Report
    print(f"❌ Brands in INDEX but NOT in LEXICON: {len(missing_from_lexicon)}")
    if missing_from_lexicon:
        print("-" * 50)
        for item in missing_from_lexicon[:30]:
            print(f"  {item['brand']:40} ({item['count']:4} ads, {item['runs']:3} runs)")
        if len(missing_from_lexicon) > 30:
            print(f"  ... and {len(missing_from_lexicon) - 30} more")
    print()
    
    print(f"⚠️  Brands in LEXICON but NOT in INDEX: {len(unused_in_lexicon)}")
    if unused_in_lexicon:
        print("-" * 50)
        for brand in sorted(unused_in_lexicon)[:20]:
            print(f"  {brand}")
        if len(unused_in_lexicon) > 20:
            print(f"  ... and {len(unused_in_lexicon) - 20} more")
    print()
    
    # Auto-add all missing brands (for brand_name_verifier workflow)
    if args.auto_add and missing_from_lexicon:
        print("\n🔧 Auto-Add Mode (for brand_name_verifier)")
        print("=" * 50)
        
        lexicon_data = json.loads(BRAND_LEXICON.read_text())
        added = 0
        skipped = []
        
        blacklisted = []
        
        for item in missing_from_lexicon:
            brand_raw = item["brand"]
            
            # Skip 'unknown' if requested
            if args.exclude_unknown and brand_raw.lower() == "unknown":
                skipped.append(brand_raw)
                continue
            
            # Skip brands that look like garbage (too short, all numbers, etc.)
            if len(brand_raw) < 2 or brand_raw.isdigit():
                skipped.append(brand_raw)
                continue
            
            # Skip blacklisted brands
            if is_blacklisted(brand_raw):
                blacklisted.append(brand_raw)
                continue
            
            # Convert to proper title case
            brand_formatted = smart_title_case(brand_raw)
            
            # Also check if formatted version is blacklisted
            if is_blacklisted(brand_formatted):
                blacklisted.append(brand_raw)
                continue
            
            # Keep original as synonym if different
            synonyms = []
            if brand_raw.lower() != brand_formatted.lower() and brand_raw != brand_formatted:
                synonyms.append(brand_raw)
            
            lexicon_data.append({
                "name": brand_formatted,
                "synonyms": synonyms,
                "verified": False  # Will show up in brand_name_verifier
            })
            added += 1
        
        if added > 0:
            # Sort by name
            lexicon_data.sort(key=lambda x: x.get("name", "").lower())
            BRAND_LEXICON.write_text(json.dumps(lexicon_data, indent=2))
            print(f"✅ Added {added} brands to lexicon (verified=false)")
            print(f"⏭️  Skipped {len(skipped)} brands")
            if blacklisted:
                print(f"🚫 Blacklisted {len(blacklisted)} brands (not added)")
            print(f"\n💡 Now run brand_name_verifier to review:")
            print(f"   python3 tools/brand_name_verifier.py")
        else:
            if blacklisted:
                print(f"🚫 All {len(blacklisted)} missing brands are blacklisted")
    
    # Interactive add
    elif args.add_missing and missing_from_lexicon:
        print("\n🔧 Interactive Add Mode")
        print("=" * 50)
        
        lexicon_data = json.loads(BRAND_LEXICON.read_text())
        added = 0
        
        for item in missing_from_lexicon:
            brand = item["brand"]
            resp = input(f"Add '{brand}' to lexicon? [y/n/q]: ").strip().lower()
            
            if resp == "q":
                break
            elif resp == "y":
                lexicon_data.append({
                    "name": brand,
                    "synonyms": [],
                    "verified": False
                })
                added += 1
                print(f"  ✅ Added {brand}")
        
        if added > 0:
            # Sort by name
            lexicon_data.sort(key=lambda x: x.get("name", "").lower())
            BRAND_LEXICON.write_text(json.dumps(lexicon_data, indent=2))
            print(f"\n💾 Saved {added} new brands to {BRAND_LEXICON}")
    
    # Summary
    print("\n" + "=" * 50)
    print("📋 Summary:")
    print(f"   Missing from lexicon: {len(missing_from_lexicon)}")
    print(f"   Unused in lexicon: {len(unused_in_lexicon)}")
    
    if missing_from_lexicon and not args.auto_add and not args.add_missing:
        print(f"\n💡 To add missing brands for verifier review:")
        print(f"   python3 tools/lexicon_gap_report.py --auto-add --exclude-unknown --min-count 3")
        print(f"\n   Or interactively:")
        print(f"   python3 tools/lexicon_gap_report.py --add-missing")


if __name__ == "__main__":
    main()
