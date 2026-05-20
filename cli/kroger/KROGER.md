# KROGER.md — Kroger Web CLI API Map

## Overview

Kroger exposes a JSON REST API at `https://www.kroger.com/atlas/v1/`. Product
search and details are fully public (no login required). The site uses Akamai
Bot Manager — `curl_cffi` with Chrome impersonation is required for all requests.

**Base URL:** `https://www.kroger.com`
**API prefix:** `/atlas/v1/`
**Protocol:** REST JSON
**Auth:** None for read operations (cookie-based session for cart/coupons if logged in)
**Bot protection:** Akamai (`_abck`, `bm_sz`, `bm_sv` cookies) → `curl_cffi` required
**Extra header:** `x-kroger-channel: WEB`

---

## CLI Command Structure

```
cli-web-kroger [--json]
├── search products <query> [OPTIONS]   # Search product catalog
├── products get <upc>                  # Get product details by UPC/GTIN
├── reviews list <upc> [OPTIONS]        # List product reviews
└── coupons list <upc>                  # List digital coupons for a product
```

---

## Endpoints

### Search

#### `GET /atlas/v1/search/v1/products-search`

Search Kroger's product catalog.

**Query params:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `filter.query` | string | Yes | Search query |
| `filter.locationId` | string | No | Store ID (default: `70100070`) |
| `filter.fulfillmentMethods` | string | No | `PICKUP`, `DELIVERY`, `IN_STORE` |
| `option.groupBy` | string | No | `PRODUCT_VARIANT` (groups variants) |
| `option.quickFacets` | bool | No | `true` |
| `page.offset` | int | No | Pagination offset (default: 0) |
| `page.size` | int | No | Results per page (default: 30, max: 50) |

**Response:** `data.productsSearch` — array of product groups
```json
{
  "groupedBy": "1578351444029354",
  "brandName": "simple truth organic",
  "description": "simple truth organic® vitamin d whole milk half gallon",
  "upc": "0001111085287",
  "relevanceScore": 0.90480363,
  "searchEngineRank": 1
}
```

---

### Products

#### `GET /atlas/v1/product/v2/products`

Get full product details by GTIN13/UPC.

**Query params:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `filter.gtin13s` | string | Yes | 13-digit GTIN/UPC (comma-separated for multiple) |
| `filter.locationId` | string | No | Store ID for pricing/inventory |
| `filter.verified` | bool | No | `true` |
| `projections` | string | No | `items.full,offers.compact,nutrition.label,inventory.projected,variantGroupings.compact` |

**Response:** `data.products` — array of product objects
```json
{
  "id": "0086174500008",
  "item": {
    "brand": {"name": "Vital Farms", "code": "18311"},
    "description": "Vital Farms® Grass-Fed Unsalted Butter Sticks, 2 sticks / 8 oz",
    "categories": [{"code": "15", "name": "Dairy"}, {"code": "73", "name": "Natural & Organic"}],
    "customerFacingSize": "8 oz",
    "gtin14": "00086174500008"
  },
  "price": {
    "storePrices": {
      "regular": {"defaultDescription": "$5.49", "nfor": 1, "nforPrice": "USD 5.49"},
      "promo": {...}
    }
  },
  "inventory": {
    "locations": [{"locationId": "03400383", "available": 15, "stockLevel": "HIGH"}]
  }
}
```

---

### Reviews

#### `GET /atlas/v1/reviews/v1/item/{upc}/reviews`

Get customer reviews for a product.

**Path params:** `upc` — 13-digit GTIN
**Query params:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `page.size` | int | No | Reviews per page (default: 16) |
| `page.offset` | int | No | Pagination offset |
| `projections` | string | No | `reviews.full` |

**Response:** `data.reviews`
```json
{
  "product": {
    "averageRating": 4.78,
    "numberOfReviews": 2717,
    "fiveStarRatings": 2232
  },
  "reviews": [...]
}
```

---

### Coupons

#### `GET /atlas/v1/savings-coupons/v1/coupons`

Get available digital coupons for a product.

**Query params:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `filter.upc` | string | Yes | Product UPC |
| `filter.type` | string | No | `standard` |
| `projections` | string | No | `coupons.full` |

**Response:** `data.coupons` — array of coupon objects

---

## Data Model

### ProductSummary (from search)
- `upc` — 13-digit GTIN (canonical product ID)
- `brandName` — brand name (lowercase)
- `description` — product description
- `searchEngineRank` — result position

### Product (from product detail)
- `id` — GTIN13
- `item.description` — full product name
- `item.brand.name` — brand name
- `item.customerFacingSize` — package size
- `item.categories` — array of {code, name}
- `price.storePrices.regular.defaultDescription` — formatted price string
- `inventory.locations[0].stockLevel` — `HIGH`, `LOW`, `OUT_OF_STOCK`

### Review
- `rating` — 1-5 star rating
- `title` — review headline
- `comments` — review body
- `authorNickname` — reviewer name
- `submissionDate` — ISO date string

---

## Auth Strategy

**No auth required for search/products/reviews.**
Product search, detail, and reviews are fully public. The API returns data without
any session cookies.

For future cart/coupon-clip features (not implemented), cookie-based auth via
Playwright browser login would be needed.

---

## Notes

- Akamai cookies (`_abck`, `bm_sz`, etc.) are generated by the browser and sent
  automatically. `curl_cffi` with Chrome TLS fingerprint impersonation bypasses
  Akamai without needing real browser cookies.
- Location ID `70100070` is a generic Kroger store that returns nationwide pricing.
  Users can override with `--location-id` to get local pricing and inventory.
- UPCs in Kroger URLs (e.g., `/p/product-name/0086174500008`) are 13-digit GTINs.
