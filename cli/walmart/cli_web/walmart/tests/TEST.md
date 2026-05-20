# TEST.md — cli-web-walmart Test Plan & Results


## Part 1: Test Plan


### Test Inventory

| File | Tests | Layer |
|------|-------|-------|
| test_core.py | 42 | Unit (mocked) |
| test_e2e.py | 20 | E2E (live) + Subprocess |

**Total: 62 tests**


### test_core.py

**TestPriceInfo** (6 tests) — Unit (mocked)

- `test_from_dict_search_page_format` — from dict search page format
- `test_from_dict_detail_page_format` — from dict detail page format
- `test_from_dict_sale_item` — from dict sale item
- `test_from_dict_empty` — from dict empty
- `test_from_dict_none` — from dict none
- `test_to_dict_roundtrip` — to dict roundtrip

**TestSearchItem** (5 tests) — Unit (mocked)

- `test_basic_fields` — basic fields
- `test_price_extracted` — price extracted
- `test_sponsored_flag` — sponsored flag
- `test_to_dict_url_prefixed` — to dict url prefixed
- `test_to_dict_already_full_url` — to dict already full url

**TestProductDetail** (7 tests) — Unit (mocked)

- `test_basic_fields` — basic fields
- `test_brand_from_dict_object` — brand from dict object
- `test_price_from_current_price` — price from current price
- `test_short_description_strips_html` — short description strips html
- `test_images_extracted` — images extracted
- `test_specifications_extracted` — specifications extracted
- `test_to_dict_keys` — to dict keys

**TestSearchResults** (1 tests) — Unit (mocked)

- `test_to_dict` — to dict

**TestExceptions** (12 tests) — Unit (mocked)

- `test_auth_error_recoverable_default` — auth error recoverable default
- `test_auth_error_non_recoverable` — auth error non recoverable
- `test_rate_limit_error_retry_after` — rate limit error retry after
- `test_rate_limit_to_dict_includes_retry_after` — rate limit to dict includes retry after
- `test_server_error_status_code` — server error status code
- `test_not_found_error` — not found error
- `test_error_code_mapping` — error code mapping
- `test_raise_for_status_401` — raise for status 401
- `test_raise_for_status_404` — raise for status 404
- `test_raise_for_status_429_with_retry_after` — raise for status 429 with retry after
- `test_raise_for_status_500` — raise for status 500
- `test_raise_for_status_2xx_ok` — raise for status 2xx ok

**TestClientParsing** (6 tests) — Unit (mocked)

- `test_search_returns_search_results` — search returns search results
- `test_search_page_param` — search page param
- `test_search_filters_nameless_items` — search filters nameless items
- `test_detail_returns_product_detail` — detail returns product detail
- `test_detail_raises_not_found` — detail raises not found
- `test_browse_returns_search_results` — browse returns search results

**TestHandleErrors** (5 tests) — Unit (mocked)

- `test_exits_1_on_walmart_error` — exits 1 on walmart error
- `test_exits_2_on_unexpected_error` — exits 2 on unexpected error
- `test_json_mode_outputs_structured_error` — json mode outputs structured error
- `test_keyboard_interrupt_exits_130` — keyboard interrupt exits 130
- `test_no_error_passes_through` — no error passes through

### test_e2e.py

**TestLiveSearch** (5 tests) — E2E (live)

- `test_search_coffee_returns_items` — search coffee returns items
- `test_search_item_fields_populated` — search item fields populated
- `test_search_page_2` — search page 2
- `test_search_returns_urls` — search returns urls
- `test_search_no_raw_protocol_leak` — search no raw protocol leak

**TestLiveDetail** (4 tests) — E2E (live)

- `test_detail_returns_product` — detail returns product
- `test_detail_fields_populated` — detail fields populated
- `test_detail_list_vs_detail_consistency` — detail list vs detail consistency
- `test_detail_not_found_raises` — detail not found raises

**TestLiveBrowse** (2 tests) — E2E (live)

- `test_browse_category_returns_items` — browse category returns items
- `test_browse_query_label` — browse query label

**TestCLISubprocess** (9 tests) — Subprocess

- `test_help_flag` — help flag
- `test_products_search_json_output` — products search json output
- `test_products_search_no_rpc_leak` — products search no rpc leak
- `test_products_search_price_not_none` — products search price not none
- `test_products_detail_json_output` — products detail json output
- `test_products_search_no_sponsored` — products search no sponsored
- `test_products_search_human_output` — products search human output
- `test_version_flag` — version flag
- `test_products_search_limit` — products search limit

---


## Part 2: Test Results


**Date:** 2026-05-18 05:19 UTC


### Summary

| Metric | Value |
|--------|-------|
| Total tests | 0 |
| Passed | 0 |
| Failed | 0 |
| Errors | 0 |
| Skipped | 0 |
| Pass rate | N/A |
| Execution time | 74.19s |
| Date | 2026-05-18 05:19 UTC |

### Raw Output

```
============================= test session starts ==============================
platform darwin -- Python 3.11.9, pytest-9.0.3, pluggy-1.6.0
rootdir: /Users/dan.maguire/My project/walmart/agent-harness
plugins: anyio-4.12.0
collected 62 items

cli_web/walmart/tests/test_core.py ..................................... [ 59%]
.....                                                                    [ 67%]
cli_web/walmart/tests/test_e2e.py .......s............                   [100%]

=================== 61 passed, 1 skipped in 74.19s (0:01:14) ===================
```
