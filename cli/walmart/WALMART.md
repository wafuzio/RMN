# WALMART.md — CLI-Web Walmart API Map

## Overview

- **Site**: https://www.walmart.com
- **Protocol**: Next.js SSR — all product data embedded in `<script id="__NEXT_DATA__">` JSON on each HTML page
- **Auth**: None — all read operations are public (no login required)
- **Anti-bot**: Akamai + PerimeterX — requires real Chrome browser with persistent profile
- **Runtime HTTP**: Python playwright with `channel="chrome"` + persistent user_data_dir (`~/.config/cli-web-walmart/browser-profile/`)
- **Docs**: No public API; SSR data is the interface

---

## Endpoints

### 1. Product Search
- **URL**: `GET https://www.walmart.com/search?q={query}&page={page}`
- **Data path**: `props.pageProps.initialData.searchResult`
- **Key fields**:
  - `searchResult.aggregatedCount` — total product count
  - `searchResult.itemStacks[0].items[]` — list of product items
  - `searchResult.paginationV2` — pagination info

### 2. Category Browse
- **URL**: `GET https://www.walmart.com/browse/{category}/{taxIds}`
- **Data path**: same as search (`searchResult.itemStacks[0].items[]`)
- **Example**: `/browse/food/coffee/976759_976787_1001080`

### 3. Product Detail
- **URL**: `GET https://www.walmart.com/ip/{slug}/{item_id}`
- **Data path**: `props.pageProps.initialData.data.product`
- **Key fields**: `name`, `usItemId`, `priceInfo`, `shortDescription`, `longDescription`, `brand`, `averageRating`, `numberOfReviews`, `images[]`, `specifications[]`

---

## Item Data Shape (search result)

```json
{
  "usItemId": "3197101168",
  "name": "Black Rifle Coffee Company Blackbeard's Delight K Cups Pods",
  "brand": "Black Rifle Coffee Company",
  "canonicalUrl": "/ip/{slug}/{usItemId}",
  "priceInfo": {
    "linePrice": "$17.88",
    "unitPrice": "$2.10/oz",
    "wasPrice": "",
    "savings": ""
  },
  "averageRating": 4.6,
  "numberOfReviews": 1988,
  "availabilityStatusV2": {"display": "In Stock", "value": "IN_STOCK"},
  "sellerName": "Walmart",
  "imageInfo": {"thumbnailUrl": "https://i5.walmartimages.com/..."},
  "isSponsoredFlag": false
}
```

---

## CLI Command Map

| Command | HTTP | URL | Description |
|---------|------|-----|-------------|
| `products search <query>` | GET | `/search?q={query}&page={page}` | Search products |
| `products detail <item-id>` | GET | `/ip/-/{item_id}` | Get product detail |
| `products browse <category>` | GET | `/browse/{category}` | Browse category |

---

## Anti-bot Notes

- Direct `httpx` requests are blocked (PerimeterX redirect to `/blocked?...`)
- `curl_cffi` with `impersonate="chrome120"` alone is also blocked
- **Solution**: Use `playwright` with `channel="chrome"` and a persistent user_data_dir
  - User data dir: `~/.config/cli-web-walmart/browser-profile/`
  - First run: browser launches visibly, PerimeterX validates the real Chrome
  - Subsequent runs: headless mode works with the established profile
- **Client architecture**: Playwright persistent context opened once per CLI invocation; all pages share the same context

---

## Price Fields Reference

| Field | Format | Notes |
|-------|--------|-------|
| `priceInfo.linePrice` | `"$17.88"` | Main display price |
| `priceInfo.unitPrice` | `"$2.10/oz"` | Unit price (when available) |
| `priceInfo.wasPrice` | `"$19.99"` | Original price (when on sale) |
| `priceInfo.savings` | `"$2.11"` | Savings amount |

---

## No-auth Site Notes

- No `auth.py`, no `session.py`, no auth command groups
- No `~/.config/cli-web-walmart/auth.json` (browser profile is not auth data)
- Browser profile manages PerimeterX cookies transparently
- CLI works out of the box with no setup required beyond installation
