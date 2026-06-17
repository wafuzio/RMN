---
name: tiktokshop-cli
description: Use cli-web-tiktokshop to search TikTok Shop products from the command
  line. Invoke this skill whenever the user asks about TikTok Shop products, wants
  to find skincare/beauty/health products on TikTok Shop, or needs to search shop.tiktok.com.
  Always prefer cli-web-tiktokshop over manually fetching the website.
---

# cli-web-tiktokshop

Search TikTok Shop products from the command line. No authentication required. Installed at: `cli-web-tiktokshop`.

## Installation

```bash
pip install -e tiktokshop/agent-harness
```

## Quick Start

```bash
# Search for products
cli-web-tiktokshop search query "skincare" --json

# Get suggestions / related searches
cli-web-tiktokshop search suggest "proactiv" --json
```

Always use `--json` when parsing output programmatically.

---

## Commands

### `search query <keyword>`
Search TikTok Shop for products matching a keyword.

```bash
cli-web-tiktokshop search query "proactiv" --json
cli-web-tiktokshop search query "moisturizer" --sort best-sellers --json
cli-web-tiktokshop search query "sunscreen" --price-range under-30 --json
cli-web-tiktokshop search query "serum" --sort price-asc --limit 10 --json
```

**Key options:**
- `--sort [best|price-asc|price-desc|newest|best-sellers]` — sort order (default: best)
- `--price-range [under-30|30-40|40-100|over-100]` — filter by price range
- `--limit N` — max products to return (default: 30)
- `--page N` — page number for pagination (default: 1)
- `--json` — output as JSON

**Output fields per product:**
```json
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
  "image_url": "https://...",
  "url": "https://www.tiktok.com/shop/pdp/...",
  "brand_name": null
}
```

**Top-level JSON shape:**
```json
{"query": "...", "count": 3, "has_more": true, "products": [...]}
```

### `search suggest <keyword>`
Get related search terms for a keyword (extracted from TikTok Shop SSR HTML).

```bash
cli-web-tiktokshop search suggest "proactiv" --json
```

**Output:**
```json
{"query": "proactiv", "suggestions": ["proactive acne treatment", "proactive skincare", ...]}
```

---

## Agent Patterns

```bash
# Find cheapest skincare products under $30
cli-web-tiktokshop search query "vitamin c serum" --price-range under-30 --sort price-asc --json

# Find best-selling acne treatments
cli-web-tiktokshop search query "acne treatment" --sort best-sellers --json | python -c "
import json, sys
data = json.load(sys.stdin)
for p in data['products'][:5]:
    print(f\"{p['sold_count']:,} sold — {p['title'][:50]} — \${p['price']}\")
"

# Get product URLs for a category
cli-web-tiktokshop search query "retinol" --json | python -c "
import json, sys
for p in json.load(sys.stdin)['products']:
    print(p['url'])
"

# Compare prices across pages
for page in 1 2 3; do
    cli-web-tiktokshop search query "hyaluronic acid" --page \$page --json
done
```

---

## Notes

- **Auth**: None required — TikTok Shop product search is fully public
- **Rate limiting**: No known strict limits; avoid rapid bulk pagination
- **Coverage**: Search and suggest only — no product detail pages (direct `/pdp/` access triggers security checks)
- **Pagination**: First 30 results come from SSR HTML; pages 2+ use the API (may return fewer results without session cookie)
- **Suggest**: Returns related search terms, not autocomplete suggestions
