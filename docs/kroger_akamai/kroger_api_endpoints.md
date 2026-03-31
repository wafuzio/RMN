# Kroger API Endpoints (Extracted from HAR)

## 1. Search API - Get Product IDs

**Endpoint:** `https://www.kroger.com/atlas/v1/search/v1/products-search`

**Method:** GET

**Query Parameters:**
```
option.groupBy=PRODUCT_VARIANT
option.quickFacets=true
filter.locationId=03500577
filter.query=black%20forest%20ham
filter.fulfillmentMethods=IN_STORE
filter.fulfillmentMethods=PICKUP
filter.fulfillmentMethods=DELIVERY
page.offset=0
page.size=24
option.personalization=PURCHASE_HISTORY
```

**Required Headers:**
```
accept: application/json, text/plain, */*
referer: https://www.kroger.com/search?query=black%20forest%20ham&searchType=default_search
user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0...
```

**Response:** ~7KB JSON with product GTINs (UPCs)

---

## 2. Product Details API - Get Full Product Data

**Endpoint:** `https://www.kroger.com/atlas/v1/product/v2/products`

**Method:** GET

**Query Parameters:**
```
filter.gtin13s=0022573700000
filter.gtin13s=0004450032953
filter.gtin13s=0005190001613
... (multiple GTINs from search results)
filter.verified=true
projections=items.full,offers.compact,nutrition.label,inventory.projected,variantGroupings.compact
```

**Required Headers:**
```
accept: application/json, text/plain, */*
referer: https://www.kroger.com/search?query=black%20forest%20ham&searchType=default_search
user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0...
```

**Response:** ~578KB JSON with full product details (images, prices, descriptions, nutrition, etc.)

---

## curl_cffi Implementation Strategy

1. **Call Search API** with search term → Get list of GTINs
2. **Call Product Details API** with GTINs → Get full product data
3. Use `impersonate="chrome120"` for TLS fingerprinting
4. Reuse cookies from Playwright session for authentication

## Key Notes

- **Location ID** is required (store-specific results)
- **GTINs** are 13-digit UPC codes
- **Projections** parameter controls which fields are returned
- Both APIs require proper headers (User-Agent, Referer, Accept)
- Cookies may be needed for authenticated features (prices, inventory)
