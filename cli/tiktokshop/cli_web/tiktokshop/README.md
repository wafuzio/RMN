# cli-web-tiktokshop

Search TikTok Shop products from the command line. No authentication required.

## Installation

```bash
pip install -e /path/to/tiktokshop/agent-harness
```

## Usage

### Search products

```bash
# Basic search
cli-web-tiktokshop search query proactiv

# Sort by price (low to high)
cli-web-tiktokshop search query skincare --sort price-asc

# Sort options: best, price-asc, price-desc, newest, best-sellers
cli-web-tiktokshop search query moisturizer --sort best-sellers

# Filter by price range
cli-web-tiktokshop search query skincare --price-range under-30
cli-web-tiktokshop search query sunscreen --price-range 30-40
# Price range options: under-30, 30-40, 40-100, over-100

# Limit results
cli-web-tiktokshop search query "acne treatment" --limit 10

# Page through results (30 per page)
cli-web-tiktokshop search query skincare --page 2

# JSON output for scripting
cli-web-tiktokshop search query proactiv --json
```

### Search suggestions

```bash
cli-web-tiktokshop search suggest proactiv
cli-web-tiktokshop search suggest skincare --json
```

### Interactive REPL

```bash
cli-web-tiktokshop
```

Then type commands like:
```
search query proactiv
search query skincare --sort price-asc --limit 5 --json
search suggest moisturizer
```

## JSON output format

```json
{
  "query": "proactiv",
  "count": 3,
  "has_more": true,
  "products": [
    {
      "product_id": "1731326251759669703",
      "title": "Proactiv Solution Renewing Cleanser",
      "price": "16.00",
      "currency": "USD",
      "price_prefix": "",
      "rating": 5.0,
      "review_count": "1",
      "sold_count": 14,
      "shop_name": "EAZYPOINT",
      "seller_id": "7495616181061519815",
      "image_url": "https://p16-oec-general-useast5.ttcdn-us.com/...",
      "url": "https://www.tiktok.com/shop/pdp/...",
      "brand_name": null
    }
  ]
}
```

## How it works

The CLI fetches TikTok Shop search pages and parses the server-side rendered (SSR)
product data embedded in the HTML. No authentication or API keys required.
