#!/usr/bin/env python3
"""
Brand Lexicon Validation Tool

Checks config/brands.json for:
- Duplicate synonyms mapping to multiple brands
- Campaign-like synonyms that shouldn't be in the lexicon
- Cross-brand synonym pollution
"""
import json
from pathlib import Path
from collections import defaultdict

LEX = Path(__file__).parent.parent / "config" / "brands.json"
if not LEX.exists():
    print(f"❌ {LEX} not found")
    raise SystemExit(1)

data = json.loads(LEX.read_text())
syn_to_brand = {}
dups = defaultdict(set)
problems = []

print("🔍 Validating brand lexicon...")
print(f"   File: {LEX}")
print(f"   Brands: {len(data)}")
print()

# Check for duplicate synonyms
for b in data:
    brand = b["name"]
    for syn in [b["name"]] + b.get("synonyms", []):
        key = syn.strip().lower()
        if key in syn_to_brand and syn_to_brand[key] != brand:
            dups[key].add(brand)
            dups[key].add(syn_to_brand[key])
        syn_to_brand[key] = brand

# Flag campaign-like synonyms
campaignish = []
campaign_patterns = [
    "alwayson", "wave", "fy", "q1", "q2", "q3", "q4", 
    "2024", "2025", "2026", "campaign", "promo", "test"
]
for b in data:
    brand = b["name"]
    for syn in b.get("synonyms", []):
        s = syn.strip().lower()
        if any(pattern in s for pattern in campaign_patterns):
            campaignish.append((brand, syn))

# Print findings
if dups:
    print("❌ Synonyms mapping to multiple brands:")
    for syn, brands in sorted(dups.items()):
        print(f"   '{syn}' → {sorted(brands)}")
    print()
else:
    print("✅ No duplicate synonym collisions")
    print()

if campaignish:
    print("⚠️  Suspicious campaign-like synonyms:")
    for brand, syn in sorted(campaignish):
        print(f"   {brand}: '{syn}'")
    print()
else:
    print("✅ No campaign-like synonyms detected")
    print()

# Check for potential cross-brand pollution
# (e.g., "Kleenex" having "Cottonelle" as synonym)
cross_brand = []
all_brand_names = {b["name"].lower() for b in data}
for b in data:
    brand = b["name"]
    for syn in b.get("synonyms", []):
        syn_lower = syn.strip().lower()
        if syn_lower in all_brand_names and syn_lower != brand.lower():
            cross_brand.append((brand, syn, syn_lower))

if cross_brand:
    print("⚠️  Potential cross-brand pollution:")
    for brand, syn, other_brand in sorted(cross_brand):
        print(f"   {brand} has synonym '{syn}' which is also a brand name")
    print()
else:
    print("✅ No cross-brand pollution detected")
    print()

# Summary
total_synonyms = sum(len(b.get("synonyms", [])) for b in data)
print("📊 Summary:")
print(f"   Total brands: {len(data)}")
print(f"   Total synonyms: {total_synonyms}")
print(f"   Duplicate collisions: {len(dups)}")
print(f"   Campaign-like synonyms: {len(campaignish)}")
print(f"   Cross-brand pollution: {len(cross_brand)}")
print()

if dups or campaignish or cross_brand:
    print("⚠️  Issues found - please review and fix config/brands.json")
    raise SystemExit(1)
else:
    print("✅ Lexicon validation passed!")
    raise SystemExit(0)
