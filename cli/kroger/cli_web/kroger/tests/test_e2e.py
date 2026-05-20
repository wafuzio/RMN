"""End-to-end tests for cli-web-kroger.

Subprocess tests: invoke the installed CLI binary and verify exit codes / output.
Live tests: hit the real Kroger API via Playwright Chrome (opens a visible window).

Run subsets:
    pytest -m subprocess   # fast, no network
    pytest -m live         # requires real Chrome + network
"""
from __future__ import annotations

import os
import subprocess

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_cli() -> str:
    """Return the CLI binary name to use in subprocess tests."""
    # Always use the installed binary — no local path fallback needed.
    return "cli-web-kroger"


def run_cli(*args, **kwargs):
    """Run the CLI with the given arguments and return the CompletedProcess."""
    return subprocess.run(
        [_resolve_cli()] + list(args),
        capture_output=True,
        text=True,
        timeout=120,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Subprocess tests — help text / exit codes only, no network
# ---------------------------------------------------------------------------


@pytest.mark.subprocess
def test_help_exits_zero_and_mentions_kroger():
    result = run_cli("--help")
    assert result.returncode == 0
    assert "kroger" in result.stdout.lower()


@pytest.mark.subprocess
def test_search_products_help():
    result = run_cli("search", "products", "--help")
    assert result.returncode == 0
    assert "query" in result.stdout.lower()


@pytest.mark.subprocess
def test_products_help():
    result = run_cli("products", "--help")
    assert result.returncode == 0


@pytest.mark.subprocess
def test_reviews_help():
    result = run_cli("reviews", "--help")
    assert result.returncode == 0


@pytest.mark.subprocess
def test_coupons_help():
    result = run_cli("coupons", "--help")
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Live tests — real browser + real Kroger API
# ---------------------------------------------------------------------------

# Skip the entire module-level section if playwright isn't installed.
playwright = pytest.importorskip("playwright", reason="playwright not installed")


@pytest.mark.live
def test_search_butter_returns_results():
    """Search for 'butter' and verify the response shape."""
    from cli_web.kroger.core.client import KrogerClient

    with KrogerClient() as client:
        results = client.search_products("butter")

    assert isinstance(results, list), "search_products should return a list"
    assert len(results) >= 1, "Expected at least one result for 'butter'"

    first = results[0]
    assert "upc" in first or "upcs" in first, (
        f"Expected 'upc'/'upcs' key in result, got: {list(first.keys())}"
    )
    # description may appear under different keys depending on API version
    desc_keys = {"description", "itemDescription", "name"}
    assert desc_keys & set(first.keys()), (
        f"Expected a description-like key in result, got: {list(first.keys())}"
    )


@pytest.mark.live
def test_get_product_vital_farms_butter():
    """Fetch a specific product and verify brand / description."""
    from cli_web.kroger.core.client import KrogerClient

    UPC = "0086174500008"

    with KrogerClient() as client:
        product = client.get_product(UPC)

    assert isinstance(product, dict)
    # Brand name or description should mention "vital farms" (case-insensitive)
    text = " ".join(str(v) for v in product.values()).lower()
    assert "vital farms" in text or "butter" in text, (
        f"Expected 'vital farms' or 'butter' in product data; got keys: {list(product.keys())}"
    )


@pytest.mark.live
def test_reviews_vital_farms_butter_has_reviews():
    """Verify that reviews exist for a well-known product."""
    from cli_web.kroger.core.client import KrogerClient

    UPC = "0086174500008"

    with KrogerClient() as client:
        reviews = client.get_reviews(UPC)

    assert isinstance(reviews, dict), "get_reviews should return a dict"
    # API returns {"product": {"numberOfReviews": N, ...}, "reviews": [...]}
    product = reviews.get("product", {})
    review_list = reviews.get("reviews", [])
    if product.get("numberOfReviews", 0) > 0 or len(review_list) > 0:
        pass  # either aggregate count or inline reviews confirms data is present
    else:
        pytest.fail(f"No reviews found — keys: {list(reviews.keys())}, product: {product}")
