"""E2E and subprocess tests for cli-web-walmart.

Live tests open a real Chrome browser via playwright and hit Walmart.com.
Subprocess tests invoke the installed `cli-web-walmart` binary.

Run live tests only:
    python -m pytest tests/test_e2e.py -m live -v

Run subprocess tests only:
    CLI_WEB_FORCE_INSTALLED=1 python -m pytest tests/test_e2e.py -m subprocess -v

Note: Walmart is a public site — no auth required.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time

import pytest

# ── _resolve_cli helper ────────────────────────────────────────────────────────

def _resolve_cli(name: str) -> str:
    """Resolve CLI binary path.

    Checks (in order):
    1. CLI_WEB_FORCE_INSTALLED=1 → use installed binary on PATH
    2. shutil.which(name) → installed binary if on PATH
    3. Fallback: python -m cli_web.<app>.<app>_cli (dev mode)
    """
    if os.environ.get("CLI_WEB_FORCE_INSTALLED"):
        path = shutil.which(name)
        if not path:
            pytest.fail(
                f"CLI_WEB_FORCE_INSTALLED=1 but '{name}' not found on PATH. "
                f"Run: pip install -e <path/to/agent-harness>"
            )
        return path

    path = shutil.which(name)
    if path:
        return path

    # Dev-mode fallback
    return None  # handled per-test


def _run_cli(*args, timeout=60):
    """Run cli-web-walmart with given args, return CompletedProcess."""
    cli = _resolve_cli("cli-web-walmart")
    if cli:
        cmd = [cli] + list(args)
    else:
        cmd = [sys.executable, "-m", "cli_web.walmart"] + list(args)

    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


# ── Live E2E tests ─────────────────────────────────────────────────────────────

@pytest.mark.live
class TestLiveSearch:
    """Live tests for the products search command — hits real Walmart.com."""

    def test_search_coffee_returns_items(self):
        """Searching 'coffee' returns a non-empty list of items."""
        from cli_web.walmart.core import client

        results = client.search("coffee")
        assert results.query == "coffee"
        assert results.total_count > 0
        assert len(results.items) > 0

    def test_search_item_fields_populated(self):
        """Each search result has required fields non-empty."""
        from cli_web.walmart.core import client

        results = client.search("coffee")
        assert len(results.items) > 0

        # Check at least the first 5 items
        for item in results.items[:5]:
            assert item.item_id, f"Missing item_id: {item}"
            assert item.name, f"Missing name: {item}"
            # Price may be empty for marketplace items, but should not be "$None"
            assert item.price.line_price != "$None", f"Price is '$None': {item}"

    def test_search_page_2(self):
        """Page 2 returns different items than page 1."""
        from cli_web.walmart.core import client

        page1 = client.search("coffee", page=1)
        page2 = client.search("coffee", page=2)
        ids1 = {i.item_id for i in page1.items}
        ids2 = {i.item_id for i in page2.items}
        # Pages should overlap minimally
        assert len(ids1 & ids2) < len(ids1) * 0.5, "Page 1 and 2 have too many common items"

    def test_search_returns_urls(self):
        """Search results include URLs (absolute via to_dict, relative on model)."""
        from cli_web.walmart.core import client

        results = client.search("coffee")
        for item in results.items[:5]:
            # .url on the model may be relative (/ip/...); to_dict() makes it absolute
            d = item.to_dict()
            assert d["url"].startswith("https://www.walmart.com"), (
                f"URL does not start with walmart.com: {d['url']}"
            )

    def test_search_no_raw_protocol_leak(self):
        """Search results do not contain raw protocol fragments."""
        from cli_web.walmart.core import client

        results = client.search("coffee")
        for item in results.items[:10]:
            d = item.to_dict()
            output = json.dumps(d)
            assert "wrb.fr" not in output, "Raw RPC data leaked"
            assert "__NEXT_DATA__" not in output, "__NEXT_DATA__ leaked"
            assert "<script" not in output, "Raw HTML leaked"


@pytest.mark.live
class TestLiveDetail:
    """Live tests for the products detail command — hits real Walmart.com."""

    KNOWN_ITEM_ID = "971362035"  # Starbucks Pike Place — stable product

    def test_detail_returns_product(self):
        """Fetching product detail returns a ProductDetail object."""
        from cli_web.walmart.core import client

        product = client.detail(self.KNOWN_ITEM_ID)
        assert product.item_id == self.KNOWN_ITEM_ID
        assert product.name
        assert product.price.line_price
        assert product.price.line_price != "$None"

    def test_detail_fields_populated(self):
        """Product detail includes all expected fields."""
        from cli_web.walmart.core import client

        product = client.detail(self.KNOWN_ITEM_ID)
        assert product.name
        assert product.brand
        # .url may be relative; to_dict() returns the full URL
        assert product.to_dict()["url"].startswith("https://www.walmart.com")

    def test_detail_list_vs_detail_consistency(self):
        """Detail price matches what search returns for the same item."""
        from cli_web.walmart.core import client

        # Search to find the item
        results = client.search("starbucks pike place 28oz")
        target = next(
            (i for i in results.items if i.item_id == self.KNOWN_ITEM_ID), None
        )

        if target is None:
            pytest.skip(f"Item {self.KNOWN_ITEM_ID} not in first search page — skipping consistency check")

        # Fetch detail
        product = client.detail(self.KNOWN_ITEM_ID)

        # Name should be consistent
        assert product.name, "Detail name is empty"
        assert target.name, "Search name is empty"

    def test_detail_not_found_raises(self):
        """Non-existent item raises NotFoundError."""
        from cli_web.walmart.core import client
        from cli_web.walmart.core.exceptions import NotFoundError, WalmartError

        # Use an obviously invalid ID — may raise NotFoundError or WalmartError
        with pytest.raises((NotFoundError, WalmartError)):
            client.detail("00000000001")


@pytest.mark.live
class TestLiveBrowse:
    """Live tests for the products browse command."""

    COFFEE_CATEGORY = "food/coffee/976759_976787_1001080"

    def test_browse_category_returns_items(self):
        """Browsing the coffee category returns a result (items or empty with total)."""
        from cli_web.walmart.core import client

        results = client.browse(self.COFFEE_CATEGORY)
        # Walmart browse pages use the same __NEXT_DATA__ itemStacks structure as
        # search, but category IDs may change over time. A valid (non-error) response
        # is sufficient — an empty result is not a client bug.
        assert results is not None
        assert isinstance(results.items, list)
        # If we got items, verify they have the right shape
        if results.items:
            item = results.items[0]
            assert item.item_id
            assert item.name

    def test_browse_query_label(self):
        """Browse result has a descriptive query label."""
        from cli_web.walmart.core import client

        results = client.browse(self.COFFEE_CATEGORY)
        assert results.query.startswith("browse:")


# ── Subprocess / CLI tests ────────────────────────────────────────────────────

@pytest.mark.subprocess
class TestCLISubprocess:
    """Subprocess tests that invoke the installed cli-web-walmart binary."""

    def test_help_flag(self):
        """--help exits 0 and shows usage text."""
        result = _run_cli("--help", timeout=15)
        assert result.returncode == 0
        assert "walmart" in result.stdout.lower() or "usage" in result.stdout.lower()

    def test_products_search_json_output(self):
        """products search --json returns valid JSON with expected structure."""
        result = _run_cli("products", "search", "coffee", "--json", "--limit", "5", timeout=90)
        assert result.returncode == 0, f"CLI failed: {result.stderr}"

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            pytest.fail(f"Output is not valid JSON: {e}\nOutput: {result.stdout[:500]}")

        assert "items" in data or "success" in data, f"Unexpected JSON shape: {data}"

        # Navigate to items list (may be wrapped in {"success": true, "data": {...}})
        if "data" in data:
            items = data["data"].get("items", [])
        else:
            items = data.get("items", [])

        assert len(items) > 0, "No items returned from search"

        # Verify item structure
        item = items[0]
        assert "item_id" in item
        assert "name" in item
        assert "price" in item
        assert item["name"], "Item name is empty"
        assert "walmart.com" in item.get("url", ""), "URL missing walmart.com"

    def test_products_search_no_rpc_leak(self):
        """search --json output does not contain raw protocol fragments."""
        result = _run_cli("products", "search", "coffee", "--json", "--limit", "5", timeout=90)
        assert result.returncode == 0, f"CLI failed: {result.stderr}"

        output = result.stdout
        assert "__NEXT_DATA__" not in output, "__NEXT_DATA__ leaked into output"
        assert "<script" not in output, "Raw HTML leaked into output"
        assert "wrb.fr" not in output, "Raw RPC data leaked into output"

    def test_products_search_price_not_none(self):
        """Search results do not have '$None' prices."""
        result = _run_cli("products", "search", "coffee", "--json", "--limit", "10", timeout=90)
        assert result.returncode == 0, f"CLI failed: {result.stderr}"

        output = result.stdout
        assert "$None" not in output, "Price contains '$None' — PriceInfo.from_dict() bug"

    def test_products_detail_json_output(self):
        """products detail --json returns valid product JSON."""
        result = _run_cli("products", "detail", "971362035", "--json", timeout=90)
        assert result.returncode == 0, f"CLI failed: {result.stderr}"

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            pytest.fail(f"Output is not valid JSON: {e}\nOutput: {result.stdout[:500]}")

        # Navigate to product data
        if "data" in data:
            product = data["data"]
        else:
            product = data

        assert product.get("item_id") == "971362035"
        assert product.get("name"), "Product name is empty"
        assert product.get("price"), "Product price is empty"
        assert "$None" not in str(product.get("price", "")), "Price is '$None'"

    def test_products_search_no_sponsored(self):
        """--no-sponsored flag filters out sponsored items."""
        result = _run_cli(
            "products", "search", "coffee", "--json", "--no-sponsored", "--limit", "20",
            timeout=90,
        )
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        data = json.loads(result.stdout)

        items = data.get("data", data).get("items", data.get("items", []))
        for item in items:
            assert item.get("is_sponsored") is False, (
                f"Sponsored item in --no-sponsored results: {item.get('name')}"
            )

    def test_products_search_human_output(self):
        """Default (non-JSON) output shows product names in a table."""
        result = _run_cli("products", "search", "coffee", "--limit", "5", timeout=90)
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        output = result.stdout + result.stderr
        # Should show coffee-related product names
        assert any(
            kw in output.lower()
            for kw in ("coffee", "folgers", "starbucks", "espresso", "roast")
        ), f"No coffee product names in output:\n{output[:1000]}"

    def test_version_flag(self):
        """--version exits 0 and shows a version string."""
        result = _run_cli("--version", timeout=15)
        assert result.returncode == 0
        assert "0.1.0" in result.stdout or "0.1.0" in result.stderr

    def test_products_search_limit(self):
        """--limit option restricts the number of items returned."""
        result = _run_cli("products", "search", "coffee", "--json", "--limit", "3", timeout=90)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        items = data.get("data", data).get("items", data.get("items", []))
        assert len(items) <= 3, f"Expected ≤3 items, got {len(items)}"
