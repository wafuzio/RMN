# cli-web-kroger

Agent-native CLI for the Kroger grocery product catalog. Search products, get
detailed information, read reviews, and find digital coupons — all from the
command line or programmatically via `--json`.

## Installation

```bash
pip install -e /path/to/kroger/agent-harness
```

Or from the project root:
```bash
pip install -e kroger/agent-harness
```

## Usage

### Interactive REPL
```bash
cli-web-kroger
```

### One-shot commands

**Search products:**
```bash
cli-web-kroger search products "natural butter"
cli-web-kroger search products "organic milk" --limit 10 --fulfillment PICKUP
cli-web-kroger search products "eggs" --json
```

**Product details (by UPC/GTIN13):**
```bash
cli-web-kroger products get 0086174500008
cli-web-kroger products get 0086174500008 --location-id 03400383 --json
cli-web-kroger products alternatives 0086174500008
```

**Reviews:**
```bash
cli-web-kroger reviews list 0086174500008
cli-web-kroger reviews list 0086174500008 --limit 5 --json
```

**Coupons:**
```bash
cli-web-kroger coupons list 0086174500008
cli-web-kroger coupons list 0086174500008 --json
```

## JSON Output

All commands support `--json` for structured output:

```bash
# Search
cli-web-kroger search products "butter" --json
# {"success": true, "data": [...], "total": 30}

# Product detail
cli-web-kroger products get 0086174500008 --json
# {"success": true, "data": {...}}

# Error response
# {"error": true, "code": "NOT_FOUND", "message": "Product not found: ..."}
```

## Notes

- No authentication required — Kroger's product catalog is publicly accessible.
- UPCs are 13-digit GTIN codes (shown in Kroger URLs after the product slug).
- Location ID defaults to a generic Kroger store (`70100070`). Use `--location-id`
  to get local pricing and live inventory for a specific store.
- Akamai bot protection is bypassed via `curl_cffi` Chrome TLS fingerprint impersonation.
