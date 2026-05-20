# TEST.md — cli-web-tiktokshop Test Plan & Results


## Part 1: Test Plan


### Test Inventory

| File | Tests | Layer |
|------|-------|-------|
| test_core.py | 34 | Unit (mocked) |
| test_e2e.py | 24 | E2E (live) + Subprocess |

**Total: 58 tests**


### test_core.py

**TestParseProduct** (8 tests) — Unit (mocked)

- `test_basic_fields` — basic fields
- `test_seo_url_string` — seo url string
- `test_seo_url_dict` — seo url dict
- `test_seo_url_missing_generates_fallback` — seo url missing generates fallback
- `test_missing_rating` — missing rating
- `test_missing_brand` — missing brand
- `test_missing_image` — missing image
- `test_price_prefix` — price prefix

**TestProductToDict** (3 tests) — Unit (mocked)

- `test_url_construction_with_leading_slash` — url construction with leading slash
- `test_url_construction_already_absolute` — url construction already absolute
- `test_all_keys_present` — all keys present

**TestSearchResultToDict** (1 tests) — Unit (mocked)

- `test_basic_structure` — basic structure

**TestParseSSRData** (6 tests) — Unit (mocked)

- `test_extracts_products` — extracts products
- `test_injects_search_word_into_load_more` — injects search word into load more
- `test_missing_script_tag_raises_parse_error` — missing script tag raises parse error
- `test_malformed_json_raises_parse_error` — malformed json raises parse error
- `test_missing_component_returns_empty` — missing component returns empty
- `test_unexpected_structure_raises_parse_error` — unexpected structure raises parse error

**TestExtractRelatedSearches** (3 tests) — Unit (mocked)

- `test_extracts_related_links` — extracts related links
- `test_missing_component_returns_empty` — missing component returns empty
- `test_bad_html_returns_empty` — bad html returns empty

**TestExceptions** (4 tests) — Unit (mocked)

- `test_all_exceptions_subclass_base` — all exceptions subclass base
- `test_server_error_has_status_code` — server error has status code
- `test_network_error_message` — network error message
- `test_parse_error_message` — parse error message

**TestClientHTTPErrors** (4 tests) — Unit (mocked)

- `test_network_error_on_connect_failure` — network error on connect failure
- `test_network_error_on_timeout` — network error on timeout
- `test_server_error_on_5xx` — server error on 5xx
- `test_not_found_on_404` — not found on 404

**TestClientSearchMocked** (5 tests) — Unit (mocked)

- `test_empty_query_raises` — empty query raises
- `test_whitespace_query_raises` — whitespace query raises
- `test_search_returns_ssr_products` — search returns ssr products
- `test_api_graceful_fallback_when_no_data` — api graceful fallback when no data
- `test_page_2_slices_correctly` — page 2 slices correctly

### test_e2e.py

**TestLiveSearch** (10 tests) — E2E (live)

- `test_search_returns_products` — search returns products
- `test_product_has_required_fields` — product has required fields
- `test_search_result_to_dict_fields` — search result to dict fields
- `test_product_url_is_valid` — product url is valid
- `test_sort_price_asc` — sort price asc
- `test_sort_best_sellers` — sort best sellers
- `test_has_more_flag` — has more flag
- `test_empty_query_raises` — empty query raises
- `test_no_raw_json_leaked_in_titles` — no raw json leaked in titles
- `test_product_image_url_format` — product image url format

**TestLiveSuggest** (2 tests) — E2E (live)

- `test_suggest_returns_list` — suggest returns list
- `test_suggest_strings` — suggest strings

**TestCLISubprocess** (12 tests) — Subprocess

- `test_help` — help
- `test_search_query_help` — search query help
- `test_search_query_json_output` — search query json output
- `test_search_query_json_has_url_not_seo_url` — search query json has url not seo url
- `test_search_query_json_url_is_absolute` — search query json url is absolute
- `test_search_query_no_raw_protocol_leak` — search query no raw protocol leak
- `test_search_query_sort_price_asc` — search query sort price asc
- `test_search_suggest_json_output` — search suggest json output
- `test_search_suggest_plain_output` — search suggest plain output
- `test_version_flag` — version flag
- `test_invalid_sort_fails` — invalid sort fails
- `test_json_structure_complete` — json structure complete

---


## Part 2: Test Results


**Date:** 2026-05-19 23:32 UTC


### Summary

| Metric | Value |
|--------|-------|
| Total tests | 0 |
| Passed | 0 |
| Failed | 0 |
| Errors | 0 |
| Skipped | 0 |
| Pass rate | N/A |
| Execution time | 32.06s |
| Date | 2026-05-19 23:32 UTC |

### Raw Output

```
============================= test session starts ==============================
platform darwin -- Python 3.11.9, pytest-9.0.3, pluggy-1.6.0
rootdir: /Users/dan.maguire/My project/tiktokshop/agent-harness
plugins: anyio-4.13.0
collected 59 items

cli_web/tiktokshop/tests/test_core.py .................................. [ 57%]
.                                                                        [ 59%]
cli_web/tiktokshop/tests/test_e2e.py ........................            [100%]

=============================== warnings summary ===============================
cli_web/tiktokshop/tests/test_e2e.py::TestLiveSearch::test_search_result_to_dict_fields
cli_web/tiktokshop/tests/test_e2e.py::TestLiveSearch::test_product_url_is_valid
cli_web/tiktokshop/tests/test_e2e.py::TestLiveSearch::test_sort_price_asc
cli_web/tiktokshop/tests/test_e2e.py::TestLiveSearch::test_has_more_flag
cli_web/tiktokshop/tests/test_e2e.py::TestLiveSearch::test_product_image_url_format
  /Users/dan.maguire/.pyenv/versions/3.11.9/lib/python3.11/site-packages/httpx/_client.py:1144: DeprecationWarning: Setting per-request cookies=<...> is being deprecated, because the expected behaviour on cookie persistence is ambiguous. Set cookies directly on the client instance instead.
    return self.request(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================= 59 passed, 5 warnings in 32.06s ========================
```
