#!/usr/bin/env python3
"""
LogoScout All - Scan all unique brands across all retailers/clients

Since the brand logo database is shared across all retailers,
this script discovers all unique brands first, then fetches missing logos once.
"""

import requests
import sys
from collections import Counter

API_BASE = "http://localhost:5006"
RETAILERS = ["instacart", "kroger", "walmart"]


def get_clients(retailer):
    """Get all clients for a retailer"""
    try:
        resp = requests.get(f"{API_BASE}/api/clients?retailer={retailer}", timeout=10)
        resp.raise_for_status()
        return resp.json().get("clients", [])
    except Exception as e:
        print(f"  ⚠️  Error fetching clients for {retailer}: {e}")
        return []


def get_brands_for_client(retailer, client, limit=500):
    """Get all brands for a specific client"""
    try:
        resp = requests.get(
            f"{API_BASE}/api/ads/cards",
            params={"retailer": retailer, "client": client, "page_size": limit},
            timeout=20
        )
        resp.raise_for_status()
        cards = resp.json().get("cards", [])
        
        brands = set()
        for card in cards:
            brand = (card.get("brand") or "").strip()
            if brand and brand.lower() not in {
                "display ad", "shoppable display ad", "shoppable video ad",
                "video ad", "sponsored product", "sponsored products", "unknown", "n/a"
            } and "shoppable" not in brand.lower():
                brands.add(brand)
        
        return brands
    except Exception as e:
        print(f"    ⚠️  Error fetching brands: {e}")
        return set()


def main():
    print("🔍 LogoScout All - Discovering unique brands across all retailers")
    print("=" * 70)
    print()
    
    all_brands = set()
    brand_counts = Counter()
    total_clients = 0
    
    print("📊 Gathering brands from all retailers/clients...")
    for retailer in RETAILERS:
        print(f"  Scanning {retailer}...")
        clients = get_clients(retailer)
        
        if not clients:
            print(f"    ⚠️  No clients found")
            continue
        
        for client in clients:
            total_clients += 1
            print(f"    → {retailer}/{client}", end=" ", flush=True)
            
            brands = get_brands_for_client(retailer, client)
            print(f"({len(brands)} brands)")
            
            all_brands.update(brands)
            for brand in brands:
                brand_counts[brand] += 1
    
    print()
    print("📈 Statistics:")
    print(f"  Total clients scanned: {total_clients}")
    print(f"  Unique brands found: {len(all_brands)}")
    print()
    
    if not all_brands:
        print("❌ No brands found!")
        return 1
    
    # Show top brands
    print("🏆 Top 10 most common brands:")
    for brand, count in brand_counts.most_common(10):
        print(f"  {brand}: {count} clients")
    print()
    
    # Fetch logos for ALL discovered brands directly
    print("🎯 Fetching logos for all discovered brands...")
    print(f"   (Checking {len(all_brands)} unique brands)")
    print()
    
    # Import logo_scout functions directly
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from tools.logo_scout import (
        load_database, save_database, normalize_brand_key,
        fetch_logo_for_brand, ensure_dirs
    )
    
    # Load logo database
    ensure_dirs()
    db = load_database()
    
    # Fetch logos for each brand
    fetched_count = 0
    skipped_count = 0
    not_found_count = 0
    
    for brand in sorted(all_brands):
        brand_key = normalize_brand_key(brand)
        
        # Check if already in database (with logo)
        if brand_key in db.get("brands", {}):
            brand_entry = db["brands"][brand_key]
            # Skip if it has a logo file OR is marked as not_found
            if brand_entry.get("logo_file") or brand_entry.get("not_found"):
                status = "not found (skipping)" if brand_entry.get("not_found") else "already in database"
                print(f"✓ {brand}: {status}")
                skipped_count += 1
                continue
        
        print(f"→ {brand} ...", end=" ", flush=True)
        path, note = fetch_logo_for_brand(db, brand, retailer="multi-retailer")
        
        if path:
            print(f"✅ {path.name} [{note['source']}]")
            fetched_count += 1
        else:
            print(f"❌ not found")
            not_found_count += 1
            # Mark as not_found in database to skip on next run
            if brand_key not in db["brands"]:
                db["brands"][brand_key] = {}
            db["brands"][brand_key]["not_found"] = True
            db["brands"][brand_key]["brand_name"] = brand
            from datetime import datetime, timezone
            db["brands"][brand_key]["last_checked"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Save database
    save_database(db)
    
    print()
    print("=" * 70)
    print(f"✅ Logo fetch complete!")
    print(f"   Fetched: {fetched_count} new logos")
    print(f"   Skipped: {skipped_count} existing/not-found brands")
    print(f"   Not found: {not_found_count} brands (marked to skip next time)")
    print(f"   Total brands in database: {len(db['brands'])}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
