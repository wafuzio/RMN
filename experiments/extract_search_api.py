#!/usr/bin/env python3
"""
Extract the main search API endpoint from Kroger HAR file.
"""
import json
from pathlib import Path
from urllib.parse import urlparse, parse_qs

har_file = Path('/Users/dan.maguire/Documents/Amazon_Scrape/www.kroger.com.har')

with open(har_file) as f:
    har = json.load(f)

print("=== SEARCHING FOR KROGER SEARCH API ===\n")

# Look for the main search endpoint
search_api = None
for entry in har['log']['entries']:
    url = entry['request']['url']
    
    # The main search API endpoint
    if '/atlas/v1/search/v1/products' in url and entry.get('pageref') == 'page_3':
        search_api = entry
        break

if search_api:
    print("✓ FOUND MAIN SEARCH API ENDPOINT\n")
    
    url = search_api['request']['url']
    parsed = urlparse(url)
    
    print(f"URL: {url}\n")
    print(f"Base: {parsed.scheme}://{parsed.netloc}{parsed.path}")
    print(f"Method: {search_api['request']['method']}")
    print(f"Status: {search_api['response']['status']}\n")
    
    # Extract query parameters
    print("Query Parameters:")
    if 'queryString' in search_api['request']:
        for param in search_api['request']['queryString']:
            print(f"  {param['name']}: {param['value']}")
    
    # Extract important headers
    print("\nRequired Headers:")
    important_headers = {}
    for header in search_api['request']['headers']:
        name = header['name'].lower()
        if name in ['authorization', 'accept', 'user-agent', 'referer', 'x-requested-with']:
            important_headers[header['name']] = header['value']
            if len(header['value']) > 100:
                print(f"  {header['name']}: {header['value'][:100]}...")
            else:
                print(f"  {header['name']}: {header['value']}")
    
    # Check for cookies
    print("\nCookies:")
    cookie_header = None
    for header in search_api['request']['headers']:
        if header['name'].lower() == 'cookie':
            cookie_header = header['value']
            # Parse cookies
            cookies = {}
            for part in cookie_header.split('; '):
                if '=' in part:
                    name, value = part.split('=', 1)
                    cookies[name] = value
            print(f"  Found {len(cookies)} cookies")
            # Show important ones
            for name in ['_pxhd', 'pxcts', 'Cred', 'authToken']:
                if name in cookies:
                    val = cookies[name]
                    if len(val) > 50:
                        val = val[:50] + '...'
                    print(f"    {name}: {val}")
            break
    
    # Parse response
    print("\nResponse:")
    print(f"  Status: {search_api['response']['status']}")
    print(f"  Size: {search_api['response']['content'].get('size', 0)} bytes")
    
    if 'text' in search_api['response']['content']:
        try:
            response_json = json.loads(search_api['response']['content']['text'])
            print(f"  Top-level keys: {list(response_json.keys())}")
            
            # Look for products
            if 'data' in response_json:
                data = response_json['data']
                print(f"\n  'data' structure: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                
                if isinstance(data, dict) and 'products' in data:
                    products = data['products']
                    print(f"  Found {len(products)} products")
                    if products:
                        print(f"  Sample product keys: {list(products[0].keys())[:10]}")
                        
                        # Save sample
                        with open('/Users/dan.maguire/Documents/Amazon_Scrape/experiments/kroger_search_api_response.json', 'w') as out:
                            json.dump(response_json, out, indent=2)
                        print(f"\n✓ Full response saved to kroger_search_api_response.json")
                        
                        # Show sample product
                        print(f"\nSample product:")
                        sample = products[0]
                        for key in ['productId', 'upc', 'description', 'brand', 'price']:
                            if key in sample:
                                print(f"  {key}: {sample[key]}")
            
            # Save curl command template
            print("\n" + "="*60)
            print("CURL_CFFI TEMPLATE:")
            print("="*60)
            print(f"""
import requests from curl_cffi

url = "{parsed.scheme}://{parsed.netloc}{parsed.path}"
params = {{""")
            if 'queryString' in search_api['request']:
                for param in search_api['request']['queryString']:
                    print(f'    "{param["name"]}": "{param["value"]}",')
            print(f"""}}

headers = {{""")
            for name, value in important_headers.items():
                if len(value) > 100:
                    value = value[:100] + '...'
                print(f'    "{name}": "{value}",')
            print(f"""}}

response = requests.get(url, params=params, headers=headers, impersonate="chrome120")
data = response.json()
products = data['data']['products']
""")
            
        except Exception as e:
            print(f"  Error parsing response: {e}")
else:
    print("⚠ Could not find /atlas/v1/search/v1/products endpoint")
    print("\nSearching for any search-related endpoints...")
    
    for entry in har['log']['entries']:
        url = entry['request']['url']
        if 'search' in url.lower() and entry.get('pageref') == 'page_3':
            print(f"  - {entry['request']['method']} {url}")
