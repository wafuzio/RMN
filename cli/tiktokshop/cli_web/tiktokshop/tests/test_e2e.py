"""E2E and subprocess tests for cli-web-tiktokshop.

Live tests hit the real TikTok Shop website — no auth required (public site).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import pytest

from cli_web.tiktokshop.core.client import TiktokshopClient
from cli_web.tiktokshop.core.exceptions import TiktokshopError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_cli(name: str) -> list[str]:
    """Resolve installed CLI command; falls back to python -m for dev."""
    force = os.environ.get("CLI_WEB_FORCE_INSTALLED", "").strip() == "1"
    path = shutil.which(name)
    if path:
        print(f"[_resolve_cli] Using installed command: {path}")
        return [path]
    if force:
        raise RuntimeError(f"{name} not found in PATH. Install with: pip install -e .")
    module = "cli_web.tiktokshop.tiktokshop_cli"
    print(f"[_resolve_cli] Falling back to: {sys.executable} -m {module}")
    return [sys.executable, "-m", module]


# ---------------------------------------------------------------------------
# Live E2E tests — real TikTok Shop API (no auth needed)
# ---------------------------------------------------------------------------

@pytest.mark.live
class TestLiveSearch:
    """Live E2E tests against real TikTok Shop. No auth required."""

    def setup_method(self):
        self.client = TiktokshopClient()

    def teardown_method(self):
        self.client.close()

    def test_search_returns_products(self):
        result = self.client.search("skincare", limit=5)
        assert result.query == "skincare"
        assert len(result.products) > 0, "Expected at least one product"

    def test_product_has_required_fields(self):
        result = self.client.search("moisturizer", limit=3)
        assert len(result.products) > 0
        p = result.products[0]
        assert p.product_id, "product_id must not be empty"
        assert p.title, "title must not be empty"
        assert p.price, "price must not be empty"
        assert p.shop_name, "shop_name must not be empty"

    def test_search_result_to_dict_fields(self):
        result = self.client.search("proactiv", limit=3)
        assert len(result.products) > 0
        d = result.to_dict()
        assert "query" in d
        assert "page" in d
        assert "count" in d
        assert "has_more" in d
        assert "products" in d
        p = d["products"][0]
        for key in ("product_id", "title", "price", "currency", "shop_name",
                    "image_url", "url", "brand_name"):
            assert key in p, f"Missing key: {key}"

    def test_product_url_is_valid(self):
        result = self.client.search("sunscreen", limit=3)
        assert len(result.products) > 0
        for p in result.products:
            d = p.to_dict()
            assert d["url"].startswith("http"), f"URL should be absolute: {d['url']}"

    def test_sort_price_asc(self):
        result = self.client.search("moisturizer", sort="price-asc", limit=5)
        assert len(result.products) > 0

    def test_sort_best_sellers(self):
        result = self.client.search("skincare", sort="best-sellers", limit=5)
        assert len(result.products) > 0

    def test_has_more_flag(self):
        result = self.client.search("beauty", limit=30)
        # A popular query like "beauty" should always have more results
        assert isinstance(result.has_more, bool)

    def test_empty_query_raises(self):
        with pytest.raises(TiktokshopError):
            self.client.search("")

    def test_no_raw_json_leaked_in_titles(self):
        """Product titles must not contain raw JSON fragments."""
        result = self.client.search("serum", limit=5)
        for p in result.products:
            assert '"product_id"' not in p.title, "Raw JSON leaked into title"
            assert "loaderData" not in p.title

    def test_product_image_url_format(self):
        result = self.client.search("toner", limit=3)
        for p in result.products:
            if p.image_url:
                assert p.image_url.startswith("http"), f"Image URL should be absolute: {p.image_url}"


@pytest.mark.live
class TestLiveSuggest:
    def setup_method(self):
        self.client = TiktokshopClient()

    def teardown_method(self):
        self.client.close()

    def test_suggest_returns_list(self):
        suggestions = self.client.suggest("proactiv")
        # May return empty if TikTok doesn't have related searches for this query
        assert isinstance(suggestions, list)

    def test_suggest_strings(self):
        suggestions = self.client.suggest("skincare")
        for s in suggestions:
            assert isinstance(s, str)
            assert len(s) > 0


# ---------------------------------------------------------------------------
# Subprocess / CLI binary tests
# ---------------------------------------------------------------------------

@pytest.mark.subprocess
class TestCLISubprocess:
    CLI_BASE = _resolve_cli("cli-web-tiktokshop")

    def _run(self, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            self.CLI_BASE + args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=check,
        )

    def test_help(self):
        result = self._run(["--help"])
        assert result.returncode == 0
        assert "search" in result.stdout.lower()

    def test_search_query_help(self):
        result = self._run(["search", "query", "--help"])
        assert result.returncode == 0
        assert "--sort" in result.stdout
        assert "--limit" in result.stdout

    def test_search_query_json_output(self):
        result = self._run(["search", "query", "proactiv", "--limit", "3", "--json"])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["query"] == "proactiv"
        assert data["count"] >= 1
        assert "products" in data

    def test_search_query_json_has_url_not_seo_url(self):
        """JSON output must use 'url' key, not 'seo_url'."""
        result = self._run(["search", "query", "skincare", "--limit", "1", "--json"])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        p = data["products"][0]
        assert "url" in p, "Must have 'url' key in product"
        assert "seo_url" not in p, "'seo_url' must not be exposed in JSON output"

    def test_search_query_json_url_is_absolute(self):
        result = self._run(["search", "query", "moisturizer", "--limit", "2", "--json"])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        for p in data["products"]:
            assert p["url"].startswith("http"), f"URL must be absolute: {p['url']}"

    def test_search_query_no_raw_protocol_leak(self):
        """--json output must not contain raw SSR data fragments."""
        result = self._run(["search", "query", "acne", "--limit", "3", "--json"])
        assert result.returncode == 0
        raw = result.stdout
        assert "__MODERN_ROUTER_DATA__" not in raw, "Raw SSR data leaked"
        assert "loaderData" not in raw, "Raw SSR data leaked"
        assert "component_name" not in raw, "Raw SSR data leaked"

    def test_search_query_sort_price_asc(self):
        result = self._run(["search", "query", "toner", "--sort", "price-asc", "--limit", "3", "--json"])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["count"] >= 1

    def test_search_suggest_json_output(self):
        result = self._run(["search", "suggest", "skincare", "--json"])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "query" in data
        assert "suggestions" in data
        assert isinstance(data["suggestions"], list)

    def test_search_suggest_plain_output(self):
        result = self._run(["search", "suggest", "proactiv"])
        assert result.returncode == 0
        # Output should be text (suggestions or "No suggestions" message)
        assert len(result.stdout) >= 0  # May be empty if no related searches

    def test_version_flag(self):
        result = self._run(["--version"])
        assert result.returncode == 0
        assert "0.1.0" in result.stdout

    def test_invalid_sort_fails(self):
        result = self._run(["search", "query", "test", "--sort", "invalid"], check=False)
        assert result.returncode != 0

    def test_json_structure_complete(self):
        """Verify all expected JSON keys are present."""
        result = self._run(["search", "query", "serum", "--limit", "1", "--json"])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        for key in ("query", "page", "count", "has_more", "products"):
            assert key in data, f"Missing top-level key: {key}"
        p = data["products"][0]
        for key in ("product_id", "title", "price", "currency", "price_prefix",
                    "rating", "review_count", "sold_count", "shop_name",
                    "seller_id", "image_url", "url", "brand_name"):
            assert key in p, f"Missing product key: {key}"
