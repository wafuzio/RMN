#!/usr/bin/env python3
"""
Kroger curl_cffi scraper using real API endpoints discovered from HAR analysis.

Two-step process:
1. Search API - Get product GTINs (UPCs)
2. Product Details API - Get full product data

Usage:
    python3 experiments/kroger_curl_cffi_v2.py --search "black forest ham" --store-id "03500577"
"""

import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

try:
    from curl_cffi import requests
except ImportError:
    print("ERROR: curl_cffi not installed")
    print("Install with: pip install curl-cffi")
    sys.exit(1)


# API Endpoints
SEARCH_API = "https://www.kroger.com/atlas/v1/search/v1/products-search"
PRODUCT_API = "https://www.kroger.com/atlas/v1/product/v2/products"

# Output directory
OUTPUT_DIR = Path(__file__).parent / "curl_cffi_output"
OUTPUT_DIR.mkdir(exist_ok=True)


def get_headers(referer: str = None) -> Dict[str, str]:
    """
    Build headers for Kroger API requests.
    
    Args:
        referer: Optional referer URL
        
    Returns:
        Headers dict
    """
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9",
        "accept-encoding": "gzip, deflate, br",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Google Chrome";v="145", "Chromium";v="145", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
    }
    
    if referer:
        headers["referer"] = referer
    
    return headers


def search_products(
    query: str,
    store_id: str,
    page_size: int = 24,
    page_offset: int = 0,
    cookies: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Call Kroger search API to get product GTINs.
    
    Args:
        query: Search term
        store_id: Store location ID (e.g., "03500577")
        page_size: Number of results per page
        page_offset: Pagination offset
        cookies: Optional cookies dict
        
    Returns:
        Search API response JSON
    """
    params = {
        "option.groupBy": "PRODUCT_VARIANT",
        "option.quickFacets": "true",
        "filter.locationId": store_id,
        "filter.query": query,
        "filter.fulfillmentMethods": ["IN_STORE", "PICKUP", "DELIVERY"],
        "page.offset": str(page_offset),
        "page.size": str(page_size),
        "option.personalization": "PURCHASE_HISTORY"
    }
    
    referer = f"https://www.kroger.com/search?query={query.replace(' ', '%20')}&searchType=default_search"
    headers = get_headers(referer)
    
    print(f"→ Calling Search API...")
    print(f"  Query: {query}")
    print(f"  Store: {store_id}")
    print(f"  Page: {page_offset}-{page_offset + page_size}")
    
    try:
        # Try with edge impersonation and HTTP/2 disabled
        response = requests.get(
            SEARCH_API,
            params=params,
            headers=headers,
            cookies=cookies,
            impersonate="edge101",
            timeout=30,
            allow_redirects=True,
            verify=True,
            http_version=1  # Force HTTP/1.1 to avoid HTTP/2 stream errors
        )
        
        print(f"← Status: {response.status_code}")
        print(f"  Size: {len(response.content)} bytes")
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 403:
            print(f"  ✗ BLOCKED BY AKAMAI (403 Forbidden)")
            print(f"  Response: {response.text[:300]}")
            return None
        else:
            print(f"  Error: {response.text[:200]}")
            return None
            
    except Exception as e:
        print(f"✗ Search API error: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_product_details(
    gtins: List[str],
    cookies: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Call Kroger product details API to get full product data.
    
    Args:
        gtins: List of GTIN-13 codes (UPCs)
        cookies: Optional cookies dict
        
    Returns:
        Product details API response JSON
    """
    params = {
        "filter.verified": "true",
        "projections": "items.full,offers.compact,nutrition.label,inventory.projected,variantGroupings.compact"
    }
    
    # Add each GTIN as a separate filter parameter
    for gtin in gtins:
        params.setdefault("filter.gtin13s", []).append(gtin)
    
    headers = get_headers()
    
    print(f"\n→ Calling Product Details API...")
    print(f"  GTINs: {len(gtins)}")
    
    try:
        response = requests.get(
            PRODUCT_API,
            params=params,
            headers=headers,
            cookies=cookies,
            impersonate="chrome120",
            timeout=30
        )
        
        print(f"← Status: {response.status_code}")
        print(f"  Size: {len(response.content)} bytes")
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"  Error: {response.text[:200]}")
            return None
            
    except Exception as e:
        print(f"✗ Product Details API error: {e}")
        return None


def extract_gtins_from_search(search_response: Dict[str, Any]) -> List[str]:
    """
    Extract GTIN codes from search API response.
    
    Args:
        search_response: Search API JSON response
        
    Returns:
        List of GTIN-13 codes
    """
    gtins = []
    
    # Navigate the response structure to find GTINs
    # Structure may vary, so we'll check multiple possible paths
    
    if 'data' in search_response:
        data = search_response['data']
        
        # Check for products array
        if isinstance(data, dict) and 'products' in data:
            products = data['products']
            for product in products:
                if 'upc' in product:
                    gtins.append(product['upc'])
                elif 'gtin13' in product:
                    gtins.append(product['gtin13'])
                elif 'productId' in product:
                    # Sometimes the productId IS the GTIN
                    gtins.append(product['productId'])
        
        # Check for upcs array directly
        elif isinstance(data, dict) and 'upcs' in data:
            gtins.extend(data['upcs'])
    
    return gtins


def scrape_kroger(
    query: str,
    store_id: str,
    cookies: Optional[Dict[str, str]] = None,
    save_output: bool = True
) -> Dict[str, Any]:
    """
    Complete Kroger scraping workflow using curl_cffi.
    
    Args:
        query: Search term
        store_id: Store location ID
        cookies: Optional cookies from Playwright session
        save_output: Whether to save results to file
        
    Returns:
        Combined results dict
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Step 1: Search for products
    search_results = search_products(query, store_id, cookies=cookies)
    
    if not search_results:
        print("\n✗ Search failed")
        return None
    
    if save_output:
        search_file = OUTPUT_DIR / f"search_{timestamp}.json"
        with open(search_file, 'w') as f:
            json.dump(search_results, f, indent=2)
        print(f"\n✓ Search results saved: {search_file}")
    
    # Step 2: Extract GTINs
    gtins = extract_gtins_from_search(search_results)
    
    if not gtins:
        print("\n⚠ No GTINs found in search results")
        print("Search response structure:")
        print(json.dumps(search_results, indent=2)[:500])
        return {"search": search_results, "products": None}
    
    print(f"\n✓ Extracted {len(gtins)} GTINs")
    
    # Step 3: Get product details
    product_details = get_product_details(gtins, cookies=cookies)
    
    if not product_details:
        print("\n✗ Product details fetch failed")
        return {"search": search_results, "products": None}
    
    if save_output:
        products_file = OUTPUT_DIR / f"products_{timestamp}.json"
        with open(products_file, 'w') as f:
            json.dump(product_details, f, indent=2)
        print(f"✓ Product details saved: {products_file}")
    
    # Combine results
    results = {
        "search": search_results,
        "products": product_details,
        "metadata": {
            "query": query,
            "store_id": store_id,
            "timestamp": timestamp,
            "gtin_count": len(gtins)
        }
    }
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Kroger curl_cffi scraper")
    parser.add_argument("--search", required=True, help="Search term")
    parser.add_argument("--store-id", default="03500577", help="Store location ID")
    parser.add_argument("--cookies-file", help="Path to cookies JSON file")
    parser.add_argument("--no-save", action="store_true", help="Don't save output files")
    
    args = parser.parse_args()
    
    # Load cookies if provided
    cookies = None
    if args.cookies_file:
        cookies_path = Path(args.cookies_file)
        if cookies_path.exists():
            with open(cookies_path) as f:
                cookies_data = json.load(f)
            
            # Convert Playwright cookie format to dict
            if isinstance(cookies_data, list):
                cookies = {c['name']: c['value'] for c in cookies_data}
            else:
                cookies = cookies_data
            
            print(f"✓ Loaded {len(cookies)} cookies from {cookies_path}")
        else:
            print(f"⚠ Cookies file not found: {cookies_path}")
    
    print("\n" + "="*60)
    print("KROGER CURL_CFFI SCRAPER")
    print("="*60 + "\n")
    
    # Run scraper
    results = scrape_kroger(
        query=args.search,
        store_id=args.store_id,
        cookies=cookies,
        save_output=not args.no_save
    )
    
    if results:
        print("\n" + "="*60)
        print("✓ SCRAPING COMPLETE")
        print("="*60)
        
        if results.get('products'):
            # Try to count products
            products_data = results['products']
            if isinstance(products_data, dict) and 'data' in products_data:
                product_count = len(products_data['data'])
                print(f"\nExtracted {product_count} products")
        
        return 0
    else:
        print("\n" + "="*60)
        print("✗ SCRAPING FAILED")
        print("="*60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
