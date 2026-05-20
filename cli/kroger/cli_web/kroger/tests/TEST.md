# TEST.md — cli-web-kroger

## Part 1: Test Plan

### Scope

`cli-web-kroger` is a read-only public API client with no auth. Tests fall into three tiers:

| Marker | What it covers | Requires network? |
|--------|----------------|-------------------|
| `unit` | Exception hierarchy, client construction, `raise_for_status()` | No |
| `subprocess` | CLI binary entry points (`--help` for all command groups) | No |
| `live` | Real API calls via Chrome/Playwright | Yes (opens Chrome) |

### Unit tests (`test_core.py`)

- Exception hierarchy: `KrogerError` base, subclasses (`AuthError`, `RateLimitError`, `NetworkError`, `ServerError`, `NotFoundError`, `RPCError`)
- `KrogerClient()` default `location_id = "70100070"`
- `KrogerClient(location_id=X)` sets custom location
- All expected methods present: `search_products`, `get_product`, `get_reviews`, `get_coupons`, `get_recommendations`, `close`
- `raise_for_status()`: 200/204 → no-op; 401/403 → `AuthError`; 404 → `NotFoundError`; 429 → `RateLimitError`; 5xx → `ServerError`; unknown → base `KrogerError`
- `to_dict()` error codes: `NotFoundError` → `NOT_FOUND`, `RateLimitError` with/without `retry_after`

### Subprocess tests (`test_e2e.py`)

- `cli-web-kroger --help` exits 0
- `cli-web-kroger search products --help` exits 0, contains "query"
- `cli-web-kroger products --help` exits 0
- `cli-web-kroger reviews --help` exits 0
- `cli-web-kroger coupons --help` exits 0

### Live tests (`test_e2e.py`, `-m live`)

- Search "butter" returns ≥1 result with `upc` and description field
- `get_product("0086174500008")` returns Vital Farms unsalted butter
- `get_reviews("0086174500008")` returns review aggregate with `numberOfReviews > 0`

Live tests require Playwright and real Chrome. They open a visible Chrome window off-screen.

---

## Part 2: Test Results

**Run date:** 2026-05-18  
**Python version:** 3.11.9  
**CLI version:** 0.1.0  

### Unit + subprocess (28 tests)

```
$ pytest cli_web/kroger/tests/ -m "unit or subprocess" -v
28 passed
```

All 23 unit tests and 5 subprocess tests pass.

### Live tests (manual verification)

```
$ cli-web-kroger --json search products "natural butter" --limit 5
{"success": true, "data": [...26 results...], "total": 26}

$ cli-web-kroger --json products get 0086174500008
{"success": true, "data": {"id": "0086174500008", "item": {"brand": {"name": "Vital Farms"}, ...}}}

$ cli-web-kroger --json reviews list 0086174500008 --limit 3
{"success": true, "data": {"summary": {"averageRating": 4.78, "numberOfReviews": 2717, ...}}}
```

All live commands verified working against real Kroger API.

### Known behavior

- Each command opens a real Chrome window (positioned off-screen at -10000,-10000)
- The persistent profile at `~/.config/cli-web-kroger/browser-profile/` accumulates Akamai cookies over time; first-run on a fresh profile may be slightly slower
- `coupons list` may return empty array for products with no active digital coupons
