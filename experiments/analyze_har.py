#!/usr/bin/env python3
"""
Analyze Kroger HAR file to find product API endpoints.
"""
import json
from pathlib import Path

har_file = Path('/Users/dan.maguire/Documents/Amazon_Scrape/www.kroger.com.har')

with open(har_file) as f:
    har = json.load(f)

print("=== ANALYZING KROGER HAR FILE ===\n")

# Find the search page
search_page = None
for page in har['log']['pages']:
    if 'black%20forest%20ham' in page['title'] or 'black forest ham' in page['title'].lower():
        search_page = page
        print(f"Found search page: {page['title']}")
        print(f"  Started: {page['startedDateTime']}")
        print(f"  Page ID: {page['id']}\n")
        break

if not search_page:
    print("WARNING: Could not find search results page")
    search_page_id = 'page_3'  # Fallback
else:
    search_page_id = search_page['id']

# Find all requests for that page
print(f"=== REQUESTS FOR PAGE {search_page_id} ===\n")

api_requests = []
for entry in har['log']['entries']:
    if entry.get('pageref') == search_page_id:
        url = entry['request']['url']
        method = entry['request']['method']
        status = entry['response']['status']
        content_type = ''
        
        for header in entry['response']['headers']:
            if header['name'].lower() == 'content-type':
                content_type = header['value']
                break
        
        # Look for API calls (JSON responses)
        if 'application/json' in content_type or '/api/' in url or 'products' in url.lower():
            api_requests.append({
                'method': method,
                'url': url,
                'status': status,
                'content_type': content_type,
                'size': entry['response']['content'].get('size', 0),
                'entry': entry
            })

print(f"Found {len(api_requests)} API requests:\n")

for i, req in enumerate(api_requests, 1):
    print(f"{i}. {req['method']} {req['status']} - {req['url']}")
    print(f"   Content-Type: {req['content_type']}")
    print(f"   Size: {req['size']} bytes\n")

# Find the most likely product API
print("\n=== ANALYZING PRODUCT API ===\n")

product_api = None
for req in api_requests:
    url = req['url']
    # Look for search/product endpoints
    if any(keyword in url.lower() for keyword in ['search', 'product', 'item']):
        if req['size'] > 10000:  # Likely contains product data
            product_api = req
            break

if product_api:
    print(f"✓ Found product API endpoint:")
    print(f"  URL: {product_api['url']}")
    print(f"  Method: {product_api['method']}")
    print(f"  Status: {product_api['status']}")
    print(f"  Size: {product_api['size']} bytes\n")
    
    # Extract request details
    entry = product_api['entry']
    
    print("Request Headers:")
    for header in entry['request']['headers']:
        if header['name'].lower() in ['authorization', 'cookie', 'user-agent', 'accept', 'referer']:
            value = header['value']
            if len(value) > 100:
                value = value[:100] + '...'
            print(f"  {header['name']}: {value}")
    
    print("\nQuery Parameters:")
    if 'queryString' in entry['request']:
        for param in entry['request']['queryString']:
            print(f"  {param['name']}: {param['value']}")
    
    # Check response
    if 'text' in entry['response']['content']:
        try:
            response_json = json.loads(entry['response']['content']['text'])
            print("\nResponse Structure:")
            print(f"  Top-level keys: {list(response_json.keys())}")
            
            # Look for products
            for key in ['products', 'data', 'results', 'items']:
                if key in response_json:
                    products = response_json[key]
                    if isinstance(products, list) and len(products) > 0:
                        print(f"\n  Found {len(products)} products in '{key}' array")
                        print(f"  Sample product keys: {list(products[0].keys())}")
                        
                        # Save sample
                        with open('/Users/dan.maguire/Documents/Amazon_Scrape/experiments/kroger_api_sample.json', 'w') as out:
                            json.dump(response_json, out, indent=2)
                        print(f"\n✓ Full API response saved to kroger_api_sample.json")
                        break
        except:
            print("\n  (Could not parse response as JSON)")
else:
    print("⚠ Could not identify product API endpoint")
    print("\nAll API requests:")
    for req in api_requests:
        print(f"  - {req['url']}")
