# Kroger curl_cffi Experimental Scraper

## Overview

This is a **parallel path** experiment to test if `curl_cffi` with TLS impersonation can bypass Akamai's bot detection that currently blocks our Playwright-based scraper.

## Why This Approach?

### Current Problem
- Playwright gets blocked by Akamai even with perfect fingerprints
- `navigator.webdriver` is fixed but still blocked
- Akamai may be detecting Chrome DevTools Protocol (CDP)

### curl_cffi Advantages
1. **Perfect TLS fingerprinting** - Uses real browser TLS stacks
2. **No CDP detection** - Not using Chrome DevTools Protocol
3. **No JavaScript fingerprinting** - No browser APIs to check
4. **Lighter weight** - No browser overhead
5. **Faster** - Direct HTTP requests

## How It Works

### Two-Step Process

**Step 1: Get Cookies (One-time)**
```bash
python3 experiments/kroger_curl_cffi_test.py --get-cookies
```
- Launches Playwright once to authenticate
- Extracts all cookies including Akamai cookies
- Saves to `kroger_cookies.json`

**Step 2: Use curl_cffi**
```bash
python3 experiments/kroger_curl_cffi_test.py --search "black forest ham"
```
- Uses saved cookies with curl_cffi
- Impersonates Chrome's TLS fingerprint
- No browser, no CDP, no JavaScript

## Installation

```bash
# Install curl_cffi
pip install curl-cffi

# Already have Playwright installed
```

## Current Status

### ✅ Implemented
- Cookie extraction from Playwright
- Homepage access test with curl_cffi
- TLS impersonation (chrome124, edge, firefox)
- Akamai block detection
- Response saving for inspection

### 🔄 In Progress
- Finding Kroger's product search API endpoint
- Reverse-engineering API parameters

### ⏳ TODO
- Test if curl_cffi bypasses Akamai
- Map API response to our data format
- Compare results vs Playwright
- Decide on integration strategy

## Testing

### Test 1: Homepage Access
```bash
python3 experiments/kroger_curl_cffi_test.py --get-cookies
python3 experiments/kroger_curl_cffi_test.py
```

Expected: Homepage loads without "Access Denied"

### Test 2: Different Browser Impersonation
```bash
python3 experiments/kroger_curl_cffi_test.py --impersonate edge
python3 experiments/kroger_curl_cffi_test.py --impersonate firefox
```

### Test 3: Search API (once found)
```bash
python3 experiments/kroger_curl_cffi_test.py --search "black forest ham"
```

## Finding the API Endpoint

### Manual Method
1. Open Kroger in browser with DevTools (Network tab)
2. Search for a product
3. Look for XHR/Fetch requests
4. Find endpoint that returns product JSON
5. Note the URL, headers, and parameters

### Common Patterns to Try
- `/products/api/search`
- `/api/v1/products/search`
- `/search/api`
- GraphQL endpoint

## Integration Decision Points

### If curl_cffi Works ✅
- **Pros**: Bypasses Akamai, faster, lighter
- **Cons**: Need to maintain API mapping
- **Decision**: Integrate as primary method

### If curl_cffi Fails ❌
- **Reason**: Akamai blocks at network level regardless of TLS
- **Decision**: Document findings, keep Playwright approach

### If API Changes Frequently ⚠️
- **Hybrid**: Use curl_cffi when possible, fallback to Playwright
- **Decision**: Implement both paths with automatic fallback

## Output

All test outputs saved to `experiments/curl_cffi_output/`:
- `homepage_response.html` - Homepage HTML
- `search_response.json` - Search API response (once found)
- `kroger_cookies.json` - Extracted cookies

## References

- curl_cffi: https://github.com/yifeikong/curl_cffi
- TLS fingerprinting: https://tlsfingerprint.io/
- Akamai Bot Manager: https://www.akamai.com/products/bot-manager

## Notes

- This is experimental and not integrated into main scraper
- Cookies need periodic refresh (24-48 hours)
- API endpoints may change without notice
- Success depends on finding the right API endpoint
