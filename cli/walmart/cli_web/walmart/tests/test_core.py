"""Unit tests for cli-web-walmart core modules.

All tests are fast and network-free — playwright/_fetch_next_data is mocked
at the boundary so no browser is opened.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Fixtures: realistic __NEXT_DATA__ shapes ───────────────────────────────────

SEARCH_NEXT_DATA = {
    "props": {
        "pageProps": {
            "initialData": {
                "searchResult": {
                    "aggregatedCount": 1000,
                    "itemStacks": [
                        {
                            "items": [
                                {
                                    "usItemId": "10534406",
                                    "name": "Folgers Classic Roast Ground Coffee, 40.3 Oz",
                                    "brand": "Folgers",
                                    "priceInfo": {
                                        "linePrice": "$8.98",
                                        "unitPrice": "$0.22/oz",
                                        "wasPrice": "",
                                        "savings": "",
                                    },
                                    "averageRating": 4.8,
                                    "numberOfReviews": 12305,
                                    "canonicalUrl": "/ip/Folgers-Coffee/10534406",
                                    "availabilityStatusV2": {"display": "In Stock"},
                                    "sellerName": "Walmart",
                                    "isSponsoredFlag": False,
                                    "imageInfo": {
                                        "thumbnailUrl": "https://i5.walmartimages.com/folgers.jpg"
                                    },
                                },
                                {
                                    "usItemId": "971362035",
                                    "name": "Starbucks Pike Place Ground Coffee, 28 oz",
                                    "brand": "Starbucks",
                                    "priceInfo": {
                                        "linePrice": "$14.97",
                                        "unitPrice": "$0.53/oz",
                                        "wasPrice": "$16.99",
                                        "savings": "$2.02",
                                    },
                                    "averageRating": 4.7,
                                    "numberOfReviews": 3421,
                                    "canonicalUrl": "/ip/Starbucks-Pike-Place/971362035",
                                    "availabilityStatusV2": {"display": "In Stock"},
                                    "sellerName": "Walmart",
                                    "isSponsoredFlag": True,
                                    "imageInfo": {
                                        "thumbnailUrl": "https://i5.walmartimages.com/starbucks.jpg"
                                    },
                                },
                                # Item with no name — should be skipped
                                {"usItemId": "99999", "brand": "Ghost"},
                            ]
                        }
                    ],
                }
            }
        }
    }
}

DETAIL_NEXT_DATA = {
    "props": {
        "pageProps": {
            "initialData": {
                "data": {
                    "product": {
                        "usItemId": "10534406",
                        "name": "Folgers Classic Roast Ground Coffee, 40.3 Oz",
                        "brand": {"name": "Folgers"},
                        "priceInfo": {
                            "currentPrice": {"priceString": "$8.98"},
                            "unitPrice": {"priceString": "$0.22/oz"},
                            "wasPrice": None,
                            "savings": None,
                        },
                        "averageRating": 4.8,
                        "numberOfReviews": 12305,
                        "shortDescription": "<ul><li>40.3 oz can</li><li>Classic roast</li></ul>",
                        "longDescription": "<p>Folgers Classic Roast Coffee.</p>",
                        "sellerName": "Walmart",
                        "canonicalUrl": "/ip/Folgers-Coffee/10534406",
                        "images": [
                            {"url": "https://i5.walmartimages.com/folgers_lg.jpg"},
                            {"url": "https://i5.walmartimages.com/folgers_side.jpg"},
                        ],
                        "specifications": [
                            {"name": "Brand", "value": "Folgers"},
                            {"name": "Weight", "value": "40.3 oz"},
                        ],
                    }
                }
            }
        }
    }
}


# ── PriceInfo tests ────────────────────────────────────────────────────────────

class TestPriceInfo:
    """Tests for PriceInfo.from_dict() handling both search and detail page shapes."""

    def test_from_dict_search_page_format(self):
        """Search pages use priceInfo.linePrice as a plain string."""
        from cli_web.walmart.core.models import PriceInfo

        d = {
            "linePrice": "$8.98",
            "unitPrice": "$0.22/oz",
            "wasPrice": "",
            "savings": "",
        }
        p = PriceInfo.from_dict(d)
        assert p.line_price == "$8.98"
        assert p.unit_price == "$0.22/oz"
        assert p.was_price == ""
        assert p.savings == ""

    def test_from_dict_detail_page_format(self):
        """Detail pages use priceInfo.currentPrice.priceString (nested object)."""
        from cli_web.walmart.core.models import PriceInfo

        d = {
            "currentPrice": {"priceString": "$8.98"},
            "unitPrice": {"priceString": "$0.22/oz"},
            "wasPrice": None,
            "savings": None,
        }
        p = PriceInfo.from_dict(d)
        assert p.line_price == "$8.98"
        assert p.unit_price == "$0.22/oz"
        assert p.was_price == ""
        assert p.savings == ""

    def test_from_dict_sale_item(self):
        """Items on sale have wasPrice and savings populated."""
        from cli_web.walmart.core.models import PriceInfo

        d = {
            "linePrice": "$14.97",
            "unitPrice": "$0.53/oz",
            "wasPrice": "$16.99",
            "savings": "$2.02",
        }
        p = PriceInfo.from_dict(d)
        assert p.line_price == "$14.97"
        assert p.was_price == "$16.99"
        assert p.savings == "$2.02"

    def test_from_dict_empty(self):
        """Empty dict returns empty PriceInfo (no crash)."""
        from cli_web.walmart.core.models import PriceInfo

        p = PriceInfo.from_dict({})
        assert p.line_price == ""
        assert p.unit_price == ""

    def test_from_dict_none(self):
        """None returns empty PriceInfo."""
        from cli_web.walmart.core.models import PriceInfo

        p = PriceInfo.from_dict(None)
        assert p.line_price == ""

    def test_to_dict_roundtrip(self):
        """to_dict() returns expected keys."""
        from cli_web.walmart.core.models import PriceInfo

        p = PriceInfo(line_price="$8.98", unit_price="$0.22/oz", was_price="", savings="")
        d = p.to_dict()
        assert d["line_price"] == "$8.98"
        assert d["unit_price"] == "$0.22/oz"
        assert "was_price" in d
        assert "savings" in d


# ── SearchItem tests ───────────────────────────────────────────────────────────

class TestSearchItem:
    """Tests for SearchItem.from_dict() field extraction."""

    def test_basic_fields(self):
        """Core fields map correctly from raw item dict."""
        from cli_web.walmart.core.models import SearchItem

        raw = SEARCH_NEXT_DATA["props"]["pageProps"]["initialData"]["searchResult"][
            "itemStacks"
        ][0]["items"][0]
        item = SearchItem.from_dict(raw)
        assert item.item_id == "10534406"
        assert item.name == "Folgers Classic Roast Ground Coffee, 40.3 Oz"
        assert item.brand == "Folgers"
        assert item.rating == 4.8
        assert item.num_reviews == 12305
        assert item.availability == "In Stock"
        assert item.seller == "Walmart"
        assert item.is_sponsored is False
        assert item.thumbnail_url == "https://i5.walmartimages.com/folgers.jpg"

    def test_price_extracted(self):
        """Price is parsed from priceInfo."""
        from cli_web.walmart.core.models import SearchItem

        raw = SEARCH_NEXT_DATA["props"]["pageProps"]["initialData"]["searchResult"][
            "itemStacks"
        ][0]["items"][0]
        item = SearchItem.from_dict(raw)
        assert item.price.line_price == "$8.98"
        assert item.price.unit_price == "$0.22/oz"

    def test_sponsored_flag(self):
        """isSponsoredFlag is mapped correctly."""
        from cli_web.walmart.core.models import SearchItem

        raw = SEARCH_NEXT_DATA["props"]["pageProps"]["initialData"]["searchResult"][
            "itemStacks"
        ][0]["items"][1]
        item = SearchItem.from_dict(raw)
        assert item.is_sponsored is True

    def test_to_dict_url_prefixed(self):
        """to_dict() prepends https://www.walmart.com to relative URLs."""
        from cli_web.walmart.core.models import SearchItem

        raw = SEARCH_NEXT_DATA["props"]["pageProps"]["initialData"]["searchResult"][
            "itemStacks"
        ][0]["items"][0]
        item = SearchItem.from_dict(raw)
        d = item.to_dict()
        assert d["url"].startswith("https://www.walmart.com")
        assert "item_id" in d
        assert "name" in d
        assert "price" in d
        assert "rating" in d
        assert "is_sponsored" in d

    def test_to_dict_already_full_url(self):
        """to_dict() does not double-prefix already-full URLs."""
        from cli_web.walmart.core.models import SearchItem

        raw = dict(SEARCH_NEXT_DATA["props"]["pageProps"]["initialData"]["searchResult"][
            "itemStacks"
        ][0]["items"][0])
        raw["canonicalUrl"] = "https://www.walmart.com/ip/Folgers/10534406"
        item = SearchItem.from_dict(raw)
        assert item.to_dict()["url"] == "https://www.walmart.com/ip/Folgers/10534406"


# ── ProductDetail tests ────────────────────────────────────────────────────────

class TestProductDetail:
    """Tests for ProductDetail.from_dict() field extraction."""

    def _get_product_raw(self):
        return DETAIL_NEXT_DATA["props"]["pageProps"]["initialData"]["data"]["product"]

    def test_basic_fields(self):
        """Core fields map correctly from product detail dict."""
        from cli_web.walmart.core.models import ProductDetail

        raw = self._get_product_raw()
        p = ProductDetail.from_dict(raw)
        assert p.item_id == "10534406"
        assert p.name == "Folgers Classic Roast Ground Coffee, 40.3 Oz"
        assert p.brand == "Folgers"
        assert p.rating == 4.8
        assert p.num_reviews == 12305
        assert p.seller == "Walmart"

    def test_brand_from_dict_object(self):
        """Brand field can be a dict with 'name' key."""
        from cli_web.walmart.core.models import ProductDetail

        raw = self._get_product_raw()
        assert isinstance(raw["brand"], dict)
        p = ProductDetail.from_dict(raw)
        assert p.brand == "Folgers"

    def test_price_from_current_price(self):
        """Detail page price comes from currentPrice.priceString."""
        from cli_web.walmart.core.models import ProductDetail

        raw = self._get_product_raw()
        p = ProductDetail.from_dict(raw)
        assert p.price.line_price == "$8.98"
        assert p.price.unit_price == "$0.22/oz"

    def test_short_description_strips_html(self):
        """HTML tags are stripped from shortDescription."""
        from cli_web.walmart.core.models import ProductDetail

        raw = self._get_product_raw()
        p = ProductDetail.from_dict(raw)
        assert "<ul>" not in p.short_description
        assert "<li>" not in p.short_description
        assert "40.3 oz can" in p.short_description

    def test_images_extracted(self):
        """Image URLs are extracted from images list."""
        from cli_web.walmart.core.models import ProductDetail

        raw = self._get_product_raw()
        p = ProductDetail.from_dict(raw)
        assert len(p.images) == 2
        assert "folgers_lg.jpg" in p.images[0]

    def test_specifications_extracted(self):
        """Specifications list is parsed."""
        from cli_web.walmart.core.models import ProductDetail

        raw = self._get_product_raw()
        p = ProductDetail.from_dict(raw)
        assert len(p.specifications) == 2
        assert p.specifications[0]["name"] == "Brand"
        assert p.specifications[0]["value"] == "Folgers"

    def test_to_dict_keys(self):
        """to_dict() returns all expected keys."""
        from cli_web.walmart.core.models import ProductDetail

        raw = self._get_product_raw()
        p = ProductDetail.from_dict(raw)
        d = p.to_dict()
        expected_keys = {
            "item_id", "name", "brand", "price", "unit_price", "was_price",
            "savings", "rating", "num_reviews", "short_description",
            "long_description", "seller", "url", "images", "specifications",
        }
        assert expected_keys.issubset(d.keys())


# ── SearchResults tests ────────────────────────────────────────────────────────

class TestSearchResults:
    """Tests for SearchResults container."""

    def test_to_dict(self):
        """to_dict() includes query, total_count, page, item_count, items."""
        from cli_web.walmart.core.models import SearchResults

        sr = SearchResults(query="coffee", total_count=1000, page=1, items=[])
        d = sr.to_dict()
        assert d["query"] == "coffee"
        assert d["total_count"] == 1000
        assert d["page"] == 1
        assert d["item_count"] == 0
        assert isinstance(d["items"], list)


# ── Exception hierarchy tests ─────────────────────────────────────────────────

class TestExceptions:
    """Tests for the typed exception hierarchy."""

    def test_auth_error_recoverable_default(self):
        """AuthError is recoverable by default."""
        from cli_web.walmart.core.exceptions import AuthError

        exc = AuthError("session expired")
        assert exc.recoverable is True
        assert str(exc) == "session expired"

    def test_auth_error_non_recoverable(self):
        """AuthError can be marked non-recoverable."""
        from cli_web.walmart.core.exceptions import AuthError

        exc = AuthError("invalid credentials", recoverable=False)
        assert exc.recoverable is False

    def test_rate_limit_error_retry_after(self):
        """RateLimitError stores retry_after."""
        from cli_web.walmart.core.exceptions import RateLimitError

        exc = RateLimitError("rate limited", retry_after=60.0)
        assert exc.retry_after == 60.0

    def test_rate_limit_to_dict_includes_retry_after(self):
        """RateLimitError.to_dict() includes retry_after field."""
        from cli_web.walmart.core.exceptions import RateLimitError

        exc = RateLimitError("rate limited", retry_after=30.0)
        d = exc.to_dict()
        assert d["error"] is True
        assert d["code"] == "RATE_LIMITED"
        assert d["retry_after"] == 30.0

    def test_server_error_status_code(self):
        """ServerError stores HTTP status code."""
        from cli_web.walmart.core.exceptions import ServerError

        exc = ServerError("internal error", status_code=503)
        assert exc.status_code == 503

    def test_not_found_error(self):
        """NotFoundError has correct error code."""
        from cli_web.walmart.core.exceptions import NotFoundError

        exc = NotFoundError("item not found")
        d = exc.to_dict()
        assert d["code"] == "NOT_FOUND"
        assert d["error"] is True

    def test_error_code_mapping(self):
        """_error_code_for() maps each exception type correctly."""
        from cli_web.walmart.core.exceptions import (
            AuthError, NetworkError, NotFoundError,
            RateLimitError, ServerError, _error_code_for,
        )

        assert _error_code_for(AuthError("x")) == "AUTH_EXPIRED"
        assert _error_code_for(RateLimitError("x")) == "RATE_LIMITED"
        assert _error_code_for(NotFoundError("x")) == "NOT_FOUND"
        assert _error_code_for(ServerError("x")) == "SERVER_ERROR"
        assert _error_code_for(NetworkError("x")) == "NETWORK_ERROR"

    def test_raise_for_status_401(self):
        """raise_for_status() raises AuthError on 401."""
        from cli_web.walmart.core.exceptions import AuthError, raise_for_status

        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        with pytest.raises(AuthError):
            raise_for_status(mock_resp)

    def test_raise_for_status_404(self):
        """raise_for_status() raises NotFoundError on 404."""
        from cli_web.walmart.core.exceptions import NotFoundError, raise_for_status

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not Found"
        with pytest.raises(NotFoundError):
            raise_for_status(mock_resp)

    def test_raise_for_status_429_with_retry_after(self):
        """raise_for_status() raises RateLimitError with retry_after on 429."""
        from cli_web.walmart.core.exceptions import RateLimitError, raise_for_status

        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = "Too Many Requests"
        mock_resp.headers = {"Retry-After": "60"}
        with pytest.raises(RateLimitError) as exc_info:
            raise_for_status(mock_resp)
        assert exc_info.value.retry_after == 60.0

    def test_raise_for_status_500(self):
        """raise_for_status() raises ServerError on 500."""
        from cli_web.walmart.core.exceptions import ServerError, raise_for_status

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        with pytest.raises(ServerError) as exc_info:
            raise_for_status(mock_resp)
        assert exc_info.value.status_code == 500

    def test_raise_for_status_2xx_ok(self):
        """raise_for_status() does not raise on 2xx."""
        from cli_web.walmart.core.exceptions import raise_for_status

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        raise_for_status(mock_resp)  # should not raise


# ── Client parsing logic tests (mock _fetch_next_data) ────────────────────────

class TestClientParsing:
    """Tests for client.py parsing logic — _fetch_next_data is mocked."""

    def test_search_returns_search_results(self):
        """client.search() parses __NEXT_DATA__ into SearchResults."""
        with patch(
            "cli_web.walmart.core.client._fetch_next_data",
            return_value=SEARCH_NEXT_DATA,
        ):
            from cli_web.walmart.core import client

            results = client.search("coffee")
            assert results.query == "coffee"
            assert results.total_count == 1000
            assert results.page == 1
            # 2 items (third has no name, gets skipped)
            assert len(results.items) == 2
            assert results.items[0].item_id == "10534406"
            assert results.items[0].name == "Folgers Classic Roast Ground Coffee, 40.3 Oz"

    def test_search_page_param(self):
        """client.search() passes page parameter to URL."""
        captured_url = []

        def mock_fetch(url):
            captured_url.append(url)
            return SEARCH_NEXT_DATA

        with patch("cli_web.walmart.core.client._fetch_next_data", side_effect=mock_fetch):
            from cli_web.walmart.core import client

            client.search("coffee", page=3)
            assert "page=3" in captured_url[0]

    def test_search_filters_nameless_items(self):
        """Items without a name field are excluded from results."""
        with patch(
            "cli_web.walmart.core.client._fetch_next_data",
            return_value=SEARCH_NEXT_DATA,
        ):
            from cli_web.walmart.core import client

            results = client.search("coffee")
            names = [i.name for i in results.items]
            assert "" not in names
            assert all(n for n in names)

    def test_detail_returns_product_detail(self):
        """client.detail() parses __NEXT_DATA__ into ProductDetail."""
        with patch(
            "cli_web.walmart.core.client._fetch_next_data",
            return_value=DETAIL_NEXT_DATA,
        ):
            from cli_web.walmart.core import client

            product = client.detail("10534406")
            assert product.item_id == "10534406"
            assert product.name == "Folgers Classic Roast Ground Coffee, 40.3 Oz"
            assert product.brand == "Folgers"
            assert product.price.line_price == "$8.98"

    def test_detail_raises_not_found(self):
        """client.detail() raises NotFoundError when __NEXT_DATA__ shows 404."""
        nd_404 = {"page": "404", "props": {"pageProps": {"initialData": {"data": {"product": {}}}}}}
        with patch(
            "cli_web.walmart.core.client._fetch_next_data",
            return_value=nd_404,
        ):
            from cli_web.walmart.core import client
            from cli_web.walmart.core.exceptions import NotFoundError

            with pytest.raises(NotFoundError):
                client.detail("99999999")

    def test_browse_returns_search_results(self):
        """client.browse() calls correct URL and returns SearchResults."""
        captured_url = []

        def mock_fetch(url):
            captured_url.append(url)
            return SEARCH_NEXT_DATA

        with patch("cli_web.walmart.core.client._fetch_next_data", side_effect=mock_fetch):
            from cli_web.walmart.core import client

            results = client.browse("food/coffee/976759_976787_1001080")
            assert "/browse/food/coffee/" in captured_url[0]
            assert results.total_count == 1000


# ── handle_errors context manager tests ────────────────────────────────────────

class TestHandleErrors:
    """Tests for utils/helpers.py handle_errors() context manager."""

    def test_exits_1_on_walmart_error(self):
        """WalmartError exits with code 1 (user error)."""
        from cli_web.walmart.utils.helpers import handle_errors
        from cli_web.walmart.core.exceptions import WalmartError

        with pytest.raises(SystemExit) as exc_info:
            with handle_errors(json_mode=False):
                raise WalmartError("something failed")
        assert exc_info.value.code == 1

    def test_exits_2_on_unexpected_error(self):
        """Unexpected exceptions exit with code 2 (system error)."""
        from cli_web.walmart.utils.helpers import handle_errors

        with pytest.raises(SystemExit) as exc_info:
            with handle_errors(json_mode=False):
                raise RuntimeError("unexpected bug")
        assert exc_info.value.code == 2

    def test_json_mode_outputs_structured_error(self, capsys):
        """In --json mode, errors produce a JSON payload on stdout."""
        from cli_web.walmart.utils.helpers import handle_errors
        from cli_web.walmart.core.exceptions import WalmartError

        with pytest.raises(SystemExit):
            with handle_errors(json_mode=True):
                raise WalmartError("boom")

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["error"] is True
        assert "message" in data

    def test_keyboard_interrupt_exits_130(self):
        """KeyboardInterrupt exits with code 130 (Unix signal convention)."""
        from cli_web.walmart.utils.helpers import handle_errors

        with pytest.raises(SystemExit) as exc_info:
            with handle_errors(json_mode=False):
                raise KeyboardInterrupt()
        assert exc_info.value.code == 130

    def test_no_error_passes_through(self):
        """Successful code block runs without exception."""
        from cli_web.walmart.utils.helpers import handle_errors

        result = []
        with handle_errors(json_mode=False):
            result.append("ok")
        assert result == ["ok"]
