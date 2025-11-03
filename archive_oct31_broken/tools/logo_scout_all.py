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
    
    # Now run logo_scout.py with a high limit to catch all brands
    # We can use any retailer/client since the database is shared
    print("🎯 Running LogoScout to fetch missing logos...")
    print(f"   (This will check {len(all_brands)} unique brands)")
    print()
    
    import subprocess
    result = subprocess.run([
        "python3", "tools/logo_scout.py",
        "--api", API_BASE,
        "--retailer", "instacart",
        "--client", get_clients("instacart")[0] if get_clients("instacart") else "blue_bunny",
        "--limit", str(len(all_brands) + 100)  # Add buffer
    ])
    
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
