---
name: walmart-cli
description: >
  Use this skill whenever the user asks to search Walmart products, look up
  prices, check product details, or browse Walmart categories. Always prefer
  cli-web-walmart over manually fetching walmart.com. Use when the user asks
  about: finding the cheapest X on Walmart, comparing prices, looking up a
  specific product, browsing coffee/electronics/food categories on Walmart.
---

# walmart-cli

Search and browse Walmart products via `cli-web-walmart`.

## Quick Start

```bash
# Search for products (most common)
cli-web-walmart products search "coffee" --json

# Get full details on a specific item
cli-web-walmart products detail 10534406 --json

# Browse a category
cli-web-walmart products browse food/coffee/976759_976787_1001080 --json
```

## Commands

### `products search <query>`

Search for products by keyword.

```bash
cli-web-walmart products search "dark roast coffee" --json
cli-web-walmart products search "coffee" --limit 10 --json
cli-web-walmart products search "coffee" --page 2 --json
cli-web-walmart products search "coffee" --no-sponsored --json
```

**JSON output** (`{"success": true, "data": {...}}`):
```json
{
  "success": true,
  "data": {
    "query": "coffee",
    "total_count": 18000,
    "page": 1,
    "item_count": 20,
    "has_more": true,
    "items": [
      {
        "item_id": "10534406",
        "name": "Folgers Classic Roast Ground Coffee, 40.3 Oz",
        "brand": "Folgers",
        "price": "$8.98",
        "unit_price": "$0.22/oz",
        "was_price": "",
        "savings": "",
        "rating": 4.8,
        "num_reviews": 12305,
        "url": "https://www.walmart.com/ip/Folgers-Coffee/10534406",
        "availability": "In Stock",
        "seller": "Walmart",
        "is_sponsored": false,
        "thumbnail_url": "https://i5.walmartimages.com/..."
      }
    ]
  }
}
```

**Options:**
- `--page N` — page number (default: 1, ~40-60 items per page)
- `--limit N` — max items to show (default: 20)
- `--no-sponsored` — exclude sponsored listings
- `--json` — JSON output

### `products detail <item-id>`

Get full product details. `item-id` is from search results (`item_id` field).

```bash
cli-web-walmart products detail 10534406 --json
```

**JSON output fields**: `item_id`, `name`, `brand`, `price`, `unit_price`,
`was_price`, `savings`, `rating`, `num_reviews`, `short_description`,
`long_description`, `seller`, `url`, `images`, `specifications`

### `products browse <category>`

Browse a Walmart category by URL path.

```bash
cli-web-walmart products browse food/coffee/976759_976787_1001080 --json
cli-web-walmart products browse electronics --json
```

**Options:** `--page N`, `--limit N`, `--json`

## Agent Patterns

```bash
# Find cheapest coffee under $10 (use jq or Python to filter)
cli-web-walmart products search "coffee" --json | \
  python3 -c "import sys,json; d=json.load(sys.stdin); \
  items=[i for i in d['data']['items'] if i['price'] and float(i['price'].replace('\$','').replace(',','')) < 10]; \
  print(json.dumps(items, indent=2))"

# Get top-rated items
cli-web-walmart products search "coffee maker" --json | \
  python3 -c "import sys,json; d=json.load(sys.stdin); \
  items=sorted(d['data']['items'], key=lambda x: x['rating'] or 0, reverse=True)[:5]; \
  print(json.dumps(items, indent=2))"

# Check if item is on sale
cli-web-walmart products detail 10534406 --json | \
  python3 -c "import sys,json; d=json.load(sys.stdin)['data']; \
  print('ON SALE' if d['was_price'] else 'FULL PRICE', d['price'])"
```

## Notes

- **No auth required** — Walmart product search is fully public.
- **Browser required** — Uses real Google Chrome to bypass PerimeterX.
  Chrome opens visibly on each run. Profile stored at `~/.config/cli-web-walmart/browser-profile/`.
- **Rate limits** — Space searches 1-2s apart to avoid PerimeterX detection.
- **Page size** — Search returns ~40-60 items per page; use `--page N` to paginate.
- **Item IDs** — The `item_id` (usItemId) from search can be passed to `detail`.

## Installation

```bash
pip install -e walmart/agent-harness
```
