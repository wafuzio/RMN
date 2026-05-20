# cli-web-walmart

Search and browse Walmart products from the command line.

## Installation

```bash
pip install -e .
```

Requires Google Chrome to be installed (used to bypass Walmart's bot protection).

## Usage

### One-shot commands

```bash
# Search for products
cli-web-walmart products search coffee
cli-web-walmart products search "dark roast" --limit 10
cli-web-walmart products search coffee --page 2
cli-web-walmart products search coffee --no-sponsored

# Get full product details
cli-web-walmart products detail 10534406
cli-web-walmart products detail 971362035

# Browse a category
cli-web-walmart products browse food/coffee/976759_976787_1001080

# JSON output (all commands support --json)
cli-web-walmart products search coffee --json
cli-web-walmart products detail 10534406 --json
```

### Interactive REPL

Run without arguments to enter the interactive REPL:

```bash
cli-web-walmart
```

Inside the REPL:

```
walmart> products search coffee
walmart> products search "dark roast" --limit 5 --json
walmart> products detail 10534406
walmart> products browse food/coffee/976759_976787_1001080
walmart> help
walmart> exit
```

## JSON Output Format

### Search

```json
{
  "query": "coffee",
  "total_count": 1000,
  "page": 1,
  "item_count": 40,
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
```

### Product Detail

```json
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
  "short_description": "- 40.3 oz can\n- Classic roast",
  "long_description": "Folgers Classic Roast Coffee...",
  "seller": "Walmart",
  "url": "https://www.walmart.com/ip/Folgers-Coffee/10534406",
  "images": ["https://i5.walmartimages.com/..."],
  "specifications": [
    {"name": "Brand", "value": "Folgers"},
    {"name": "Weight", "value": "40.3 oz"}
  ]
}
```

## Options

### `products search <query>`

| Option | Default | Description |
|--------|---------|-------------|
| `--page N` | 1 | Results page number |
| `--limit N` | 20 | Max items to display |
| `--no-sponsored` | — | Exclude sponsored listings |
| `--json` | — | JSON output |

### `products detail <item-id>`

| Option | Default | Description |
|--------|---------|-------------|
| `--json` | — | JSON output |

### `products browse <category>`

| Option | Default | Description |
|--------|---------|-------------|
| `--page N` | 1 | Results page number |
| `--json` | — | JSON output |

## How It Works

Walmart's website is protected by PerimeterX bot detection, which blocks direct
HTTP requests and plain browser automation. This CLI uses real Google Chrome with
a persistent browser profile to maintain a trusted session.

On first run, Chrome opens visibly to establish the profile. Subsequent runs reuse
the same profile and are faster. The browser profile is stored at:

```
~/.config/cli-web-walmart/browser-profile/
```

Product data is extracted from the `__NEXT_DATA__` JSON blob embedded in each
Walmart page (Next.js SSR), providing complete and structured product information
without any scraping fragility.

## Testing

```bash
# Unit tests (fast, no network)
python -m pytest cli_web/walmart/tests/test_core.py -v

# Live E2E tests (requires network + Chrome)
python -m pytest cli_web/walmart/tests/test_e2e.py -m live -v

# Subprocess tests (requires installed CLI)
CLI_WEB_FORCE_INSTALLED=1 python -m pytest cli_web/walmart/tests/test_e2e.py -m subprocess -v

# Full suite
CLI_WEB_FORCE_INSTALLED=1 python -m pytest cli_web/walmart/tests/ -v
```
