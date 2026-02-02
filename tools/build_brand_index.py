#!/usr/bin/env python3
"""
Build a brand index for fast brand-based ad lookups.

Creates an index file that maps:
  brand_name -> [(retailer, client, json_path, ad_indices), ...]

This allows instant lookups instead of scanning all JSON files.

Features:
- Supports both nested (runs/<run_id>/) and flat (runs/) structures
- Indexes both ad.brand and ad.advertisers[] (co-branded ads)
- Uses core/brands.py canonicalization for true brand mapping
"""

import os
import json
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import brand canonicalization and blacklist from core
try:
    from core.brands import canonicalize, is_blacklisted
    USE_BRAND_CANONICALIZATION = True
except ImportError:
    print("⚠️  core/brands.py not found, using basic lowercase canonicalization")
    USE_BRAND_CANONICALIZATION = False
    def is_blacklisted(brand):
        return False

OUTPUT_ROOT = Path(__file__).parent.parent / "output"
INDEX_FILE = OUTPUT_ROOT / "brand_index.json"


def normalize_brand_key(brand: str) -> str:
    """Normalize brand name to a consistent key for grouping.
    
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


def canonicalize_brand(brand: str) -> str:
    """Normalize brand name for consistent indexing"""
    if not brand:
        return ""
    
    # Use core/brands.py if available (checks lexicon)
    if USE_BRAND_CANONICALIZATION:
        canonical = canonicalize(brand)
        if canonical:
            return normalize_brand_key(canonical)
    
    # Fallback: normalize to collapse minor variations
    return normalize_brand_key(brand)


def build_brand_index():
    """Scan all JSON files and build brand index"""
    print("🔍 Building brand index...")
    start_time = datetime.now()
    
    # brand_name -> [(retailer, client, json_path, [ad_indices]), ...]
    brand_index = defaultdict(list)
    
    files_scanned = 0
    ads_indexed = 0
    
    # Scan all retailers
    for retailer_dir in OUTPUT_ROOT.iterdir():
        if not retailer_dir.is_dir() or retailer_dir.name.startswith('.'):
            continue
            
        retailer = retailer_dir.name
        print(f"  📁 Scanning {retailer}...")
        
        # Scan all clients
        for client_dir in retailer_dir.iterdir():
            if not client_dir.is_dir() or client_dir.name.startswith('.'):
                continue
                
            client = client_dir.name
            
            # Scan runs directory
            runs_dir = client_dir / "runs"
            if not runs_dir.exists():
                continue
            
            # Collect all JSON files (both nested and flat structures)
            json_files = []
            
            # 1. Nested structure: runs/<run_id>/run_results_*.json
            for run_dir in runs_dir.iterdir():
                if run_dir.is_dir():
                    json_files.extend(run_dir.glob("run_results_*.json"))
            
            # 2. Flat structure: runs/run_results_*.json (Kroger/Instacart legacy)
            json_files.extend(runs_dir.glob("run_results_*.json"))
            
            # Process all found JSON files
            for json_file in json_files:
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    files_scanned += 1
                    
                    # Extract ads array
                    ads = data.get('ads', [])
                    if not ads:
                        continue
                    
                    # Group ads by brand (including co-brands)
                    brand_ads = defaultdict(list)
                    indexed_ads = set()  # Track which ads we've indexed (avoid double counting)
                    
                    for idx, ad in enumerate(ads):
                        brands_for_ad = set()  # Track brands for this specific ad
                        
                        # Index primary brand
                        brand = ad.get('brand') or ''
                        if brand and brand.lower() != 'unknown':
                            canonical_brand = canonicalize_brand(brand)
                            # Skip blacklisted brands (house ads, retailer brands)
                            if canonical_brand and not is_blacklisted(canonical_brand):
                                brand_ads[canonical_brand].append(idx)
                                brands_for_ad.add(canonical_brand)
                        
                        # Index co-brands from advertisers array
                        advertisers = ad.get('advertisers', [])
                        for advertiser in advertisers:
                            if advertiser and advertiser.strip():
                                canonical_advertiser = canonicalize_brand(advertiser)
                                # Skip blacklisted brands (house ads, retailer brands)
                                if canonical_advertiser and not is_blacklisted(canonical_advertiser):
                                    brand_ads[canonical_advertiser].append(idx)
                                    brands_for_ad.add(canonical_advertiser)
                        
                        # Count this ad only once, regardless of how many brands it has
                        if brands_for_ad:
                            indexed_ads.add(idx)
                    
                    ads_indexed += len(indexed_ads)
                    
                    # Add to index
                    # Store relative path from OUTPUT_ROOT
                    rel_path = str(json_file.relative_to(OUTPUT_ROOT))
                    
                    for canonical_brand, indices in brand_ads.items():
                        # Get the first ad's image path for sample display
                        first_ad_idx = indices[0] if indices else 0
                        first_ad = ads[first_ad_idx] if first_ad_idx < len(ads) else {}
                        
                        # Extract image path from the ad (try various fields)
                        sample_image_rel = (
                            first_ad.get('image_path') or
                            first_ad.get('toa_image_path') or
                            first_ad.get('skyscraper_image_path') or
                            first_ad.get('carousel_image_path') or
                            None
                        )
                        
                        # Make sample_image path relative to output root (include retailer/client)
                        sample_image = None
                        if sample_image_rel:
                            sample_image = f"{retailer}/{client}/{sample_image_rel}"
                        
                        brand_index[canonical_brand].append({
                            'retailer': retailer,
                            'client': client,
                            'json_path': rel_path,
                            'ad_indices': indices,
                            'run_id': data.get('run_id'),
                            'timestamp': data.get('timestamp'),
                            'sample_image': sample_image,  # Full path from output root
                            'sample_ad_type': first_ad.get('type')  # Ad type for context
                        })
                
                except Exception as e:
                    print(f"    ⚠️  Error reading {json_file}: {e}")
                    continue
    
    # Convert defaultdict to regular dict for JSON serialization
    brand_index_dict = dict(brand_index)
    
    # Add metadata
    index_data = {
        'version': '1.0',
        'built_at': datetime.now().isoformat(),
        'stats': {
            'total_brands': len(brand_index_dict),
            'files_scanned': files_scanned,
            'ads_indexed': ads_indexed
        },
        'index': brand_index_dict
    }
    
    # Write index file
    print(f"\n💾 Writing index to {INDEX_FILE}...")
    with open(INDEX_FILE, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, indent=2)
    
    elapsed = (datetime.now() - start_time).total_seconds()
    
    print(f"\n✅ Brand index built successfully!")
    print(f"   📊 {len(brand_index_dict):,} brands indexed")
    print(f"   📄 {files_scanned:,} files scanned")
    print(f"   🎯 {ads_indexed:,} ads indexed")
    print(f"   ⏱️  {elapsed:.2f}s")
    print(f"   📁 {INDEX_FILE}")


def load_index():
    """Load existing brand index"""
    if INDEX_FILE.exists():
        try:
            with open(INDEX_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return None


def save_index(index_data):
    """Save brand index"""
    index_data['built_at'] = datetime.now().isoformat()
    with open(INDEX_FILE, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, indent=2)


def update_brand_in_index(old_brand: str, new_brand: str = None, delete: bool = False):
    """
    Incrementally update the brand index when a brand is renamed, merged, or deleted.
    
    Args:
        old_brand: The brand name being changed
        new_brand: The new brand name (for rename/merge), or None if deleting
        delete: If True, just remove old_brand entries (mark ads as unknown)
    
    This is much faster than a full rebuild (~0.1s vs ~16s).
    """
    index_data = load_index()
    if not index_data:
        print("[INDEX] No index found, skipping incremental update")
        return False
    
    index = index_data.get('index', {})
    old_key = old_brand.strip()
    
    if old_key not in index:
        print(f"[INDEX] Brand '{old_brand}' not in index, nothing to update")
        return True
    
    entries = index[old_key]
    
    if delete:
        # Just remove the old brand entries
        del index[old_key]
        print(f"[INDEX] Removed '{old_brand}' ({len(entries)} entries)")
    else:
        # Move entries to new brand
        new_key = new_brand.strip().lower() if new_brand else None
        if not new_key:
            print("[INDEX] No new brand specified for rename")
            return False
        
        # Merge into existing or create new
        if new_key in index:
            # Merge - add entries to existing brand, avoiding duplicates
            existing_paths = {e['json_path'] for e in index[new_key]}
            for entry in entries:
                if entry['json_path'] not in existing_paths:
                    index[new_key].append(entry)
            print(f"[INDEX] Merged '{old_brand}' into '{new_brand}' ({len(entries)} entries)")
        else:
            # Rename - just move the entries
            index[new_key] = entries
            print(f"[INDEX] Renamed '{old_brand}' to '{new_brand}' ({len(entries)} entries)")
        
        # Remove old key
        del index[old_key]
    
    # Update stats
    index_data['stats']['total_brands'] = len(index)
    
    # Save
    save_index(index_data)
    return True


if __name__ == '__main__':
    build_brand_index()
