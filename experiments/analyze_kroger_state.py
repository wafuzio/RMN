#!/usr/bin/env python3
"""
Quick script to extract and analyze the window.__INITIAL_STATE__ structure from Kroger HTML
"""
import json
import re

# Read the HTML file
with open('/Users/dan.maguire/Documents/Amazon_Scrape/kroger_html.md', 'r') as f:
    html = f.read()

# Extract the JSON from window.__INITIAL_STATE__
match = re.search(r'window\.__INITIAL_STATE__ = JSON\.parse\(\'(.+?)\'\)', html, re.DOTALL)
if match:
    json_str = match.group(1)
    # Unescape the JSON string
    json_str = json_str.encode().decode('unicode_escape')
    
    # Parse it
    state = json.loads(json_str)
    
    # Pretty print the top-level keys
    print("=== TOP-LEVEL KEYS ===")
    for key in state.keys():
        print(f"  - {key}")
    
    # Look for product data
    print("\n=== SEARCHING FOR PRODUCT DATA ===")
    
    # Check common locations
    if 'products' in state:
        print(f"Found 'products' key with {len(state['products'])} items")
        if state['products']:
            print(f"Sample product keys: {list(state['products'][0].keys())}")
    
    if 'search' in state:
        print(f"Found 'search' key")
        search_keys = list(state['search'].keys()) if isinstance(state['search'], dict) else []
        print(f"  Search keys: {search_keys}")
        
        # Check for products in search results
        if 'results' in state.get('search', {}):
            results = state['search']['results']
            print(f"  Found 'results' in search with type: {type(results)}")
            if isinstance(results, dict):
                print(f"    Results keys: {list(results.keys())}")
        
        if 'products' in state.get('search', {}):
            products = state['search']['products']
            print(f"  Found 'products' in search")
            if isinstance(products, dict):
                print(f"    Products keys: {list(products.keys())[:10]}")
                # Sample a product
                first_key = list(products.keys())[0]
                print(f"    Sample product ({first_key}):")
                print(f"      Keys: {list(products[first_key].keys())}")
    
    # Save the full state for inspection
    with open('/Users/dan.maguire/Documents/Amazon_Scrape/experiments/kroger_initial_state.json', 'w') as out:
        json.dump(state, out, indent=2)
    print(f"\n✓ Full state saved to kroger_initial_state.json ({len(json.dumps(state))} bytes)")
    
else:
    print("ERROR: Could not find window.__INITIAL_STATE__ in HTML")
