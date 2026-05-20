"""Unit tests for cli-web-tiktokshop core modules (no network)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from cli_web.tiktokshop.core.client import (
    Product,
    SearchResult,
    TiktokshopClient,
    _parse_product,
)
from cli_web.tiktokshop.core.exceptions import (
    NetworkError,
    NotFoundError,
    ParseError,
    ServerError,
    TiktokshopError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_raw_product(**overrides) -> dict:
    """Return a minimal raw product dict as returned by the TikTok API."""
    base = {
        "product_id": "1731326251759669703",
        "title": "Proactiv Solution Renewing Cleanser",
        "product_price_info": {
            "sale_price_format": "16.00",
            "currency_name": "USD",
            "price_prefix": "",
        },
        "rate_info": {"score": 4.8, "review_count": 42},
        "sold_info": {"sold_count": 1234},
        "seller_info": {"shop_name": "BestSkincare", "seller_id": "7495616181061519815"},
        "brand_info": {"brand_name": "Proactiv"},
        "image": {"url_list": ["https://cdn.example.com/img.jpg"]},
        "seo_url": "/us/pdp/proactiv-solution/1731326251759669703",
    }
    base.update(overrides)
    return base


def _make_ssr_html(products: list[dict], load_more: dict | None = None) -> str:
    """Wrap product list in the SSR JSON blob TikTok embeds in HTML."""
    if load_more is None:
        load_more = {"offset": 30, "page_token": "tok123", "api_source": 2}

    ssr = {
        "loaderData": {
            "(region)/(route_page_name)/page": {
                "page_config": {
                    "components_map": [
                        {
                            "component_name": "feed_list_search_word",
                            "component_data": {
                                "products": products,
                                "load_more_params": load_more,
                            },
                        }
                    ]
                }
            }
        }
    }
    blob = json.dumps(ssr)
    return f'<html><script type="application/json" id="__MODERN_ROUTER_DATA__">{blob}</script></html>'


# ---------------------------------------------------------------------------
# _parse_product
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestParseProduct:
    def test_basic_fields(self):
        raw = _make_raw_product()
        p = _parse_product(raw)
        assert p.product_id == "1731326251759669703"
        assert p.title == "Proactiv Solution Renewing Cleanser"
        assert p.price == "16.00"
        assert p.currency == "USD"
        assert p.rating == 4.8
        assert p.review_count == "42"
        assert p.sold_count == 1234
        assert p.shop_name == "BestSkincare"
        assert p.brand_name == "Proactiv"
        assert p.image_url == "https://cdn.example.com/img.jpg"

    def test_seo_url_string(self):
        raw = _make_raw_product(seo_url="/us/pdp/test/123")
        p = _parse_product(raw)
        assert p.seo_url == "/us/pdp/test/123"

    def test_seo_url_dict(self):
        raw = _make_raw_product(seo_url={"canonical_url": "/us/pdp/test/123", "slug": "test", "type": 2})
        p = _parse_product(raw)
        assert p.seo_url == "/us/pdp/test/123"

    def test_seo_url_missing_generates_fallback(self):
        raw = _make_raw_product(seo_url="")
        raw["product_id"] = "abc123"
        raw["title"] = "Test Product"
        p = _parse_product(raw)
        assert "abc123" in p.seo_url
        assert "test-product" in p.seo_url

    def test_missing_rating(self):
        raw = _make_raw_product()
        raw["rate_info"] = {}
        p = _parse_product(raw)
        assert p.rating is None
        assert p.review_count == ""

    def test_missing_brand(self):
        raw = _make_raw_product()
        raw["brand_info"] = {}
        p = _parse_product(raw)
        assert p.brand_name is None

    def test_missing_image(self):
        raw = _make_raw_product()
        raw["image"] = {"url_list": []}
        p = _parse_product(raw)
        assert p.image_url == ""

    def test_price_prefix(self):
        raw = _make_raw_product()
        raw["product_price_info"]["price_prefix"] = "From"
        p = _parse_product(raw)
        assert p.price_prefix == "From"


# ---------------------------------------------------------------------------
# Product.to_dict
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestProductToDict:
    def test_url_construction_with_leading_slash(self):
        raw = _make_raw_product(seo_url="/us/pdp/test/123")
        p = _parse_product(raw)
        d = p.to_dict()
        assert d["url"] == "https://shop.tiktok.com/us/pdp/test/123"

    def test_url_construction_already_absolute(self):
        raw = _make_raw_product(seo_url="https://shop.tiktok.com/us/pdp/test/123")
        p = _parse_product(raw)
        d = p.to_dict()
        assert d["url"] == "https://shop.tiktok.com/us/pdp/test/123"

    def test_all_keys_present(self):
        p = _parse_product(_make_raw_product())
        d = p.to_dict()
        expected_keys = {
            "product_id", "title", "price", "currency", "price_prefix",
            "rating", "review_count", "sold_count", "shop_name", "seller_id",
            "image_url", "url", "brand_name",
        }
        assert set(d.keys()) == expected_keys


# ---------------------------------------------------------------------------
# SearchResult.to_dict
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSearchResultToDict:
    def test_basic_structure(self):
        p = _parse_product(_make_raw_product())
        result = SearchResult(query="proactiv", products=[p], has_more=True, page=1)
        d = result.to_dict()
        assert d["query"] == "proactiv"
        assert d["page"] == 1
        assert d["count"] == 1
        assert d["has_more"] is True
        assert d["next_page"] == 2
        assert len(d["products"]) == 1

    def test_no_next_page_when_no_more(self):
        p = _parse_product(_make_raw_product())
        result = SearchResult(query="proactiv", products=[p], has_more=False, page=1)
        d = result.to_dict()
        assert "next_page" not in d


# ---------------------------------------------------------------------------
# TiktokshopClient._parse_ssr_data
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestParseSSRData:
    def setup_method(self):
        self.client = TiktokshopClient()

    def teardown_method(self):
        self.client.close()

    def test_extracts_products(self):
        html = _make_ssr_html([_make_raw_product()])
        products, load_more = self.client._parse_ssr_data(html, "proactiv")
        assert len(products) == 1
        assert products[0].title == "Proactiv Solution Renewing Cleanser"

    def test_injects_search_word_into_load_more(self):
        html = _make_ssr_html([_make_raw_product()])
        _, load_more = self.client._parse_ssr_data(html, "proactiv")
        assert load_more.get("search_word") == "proactiv"

    def test_missing_script_tag_raises_parse_error(self):
        with pytest.raises(ParseError):
            self.client._parse_ssr_data("<html><body>No SSR</body></html>", "test")

    def test_malformed_json_raises_parse_error(self):
        html = '<script id="__MODERN_ROUTER_DATA__">{broken json}</script>'
        with pytest.raises(ParseError):
            self.client._parse_ssr_data(html, "test")

    def test_missing_component_returns_empty(self):
        ssr = {
            "loaderData": {
                "(region)/(route_page_name)/page": {
                    "page_config": {"components_map": []}
                }
            }
        }
        html = f'<script id="__MODERN_ROUTER_DATA__">{json.dumps(ssr)}</script>'
        products, load_more = self.client._parse_ssr_data(html, "test")
        assert products == []

    def test_unexpected_structure_raises_parse_error(self):
        html = '<script id="__MODERN_ROUTER_DATA__">{"loaderData": {}}</script>'
        with pytest.raises(ParseError):
            self.client._parse_ssr_data(html, "test")


# ---------------------------------------------------------------------------
# TiktokshopClient._extract_related_searches
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestExtractRelatedSearches:
    def setup_method(self):
        self.client = TiktokshopClient()

    def teardown_method(self):
        self.client.close()

    def test_extracts_related_links(self):
        ssr = {
            "loaderData": {
                "(region)/(route_page_name)/page": {
                    "page_config": {
                        "components_map": [
                            {
                                "component_name": "related_link_search_words",
                                "component_data": {
                                    "related_links": [
                                        {"name": "proactive acne treatment"},
                                        {"name": "proactive skincare"},
                                    ]
                                },
                            }
                        ]
                    }
                }
            }
        }
        html = f'<script id="__MODERN_ROUTER_DATA__">{json.dumps(ssr)}</script>'
        results = self.client._extract_related_searches(html)
        assert "proactive acne treatment" in results
        assert "proactive skincare" in results

    def test_missing_component_returns_empty(self):
        html = _make_ssr_html([])
        results = self.client._extract_related_searches(html)
        assert results == []

    def test_bad_html_returns_empty(self):
        results = self.client._extract_related_searches("<html>no data</html>")
        assert results == []


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestExceptions:
    def test_all_exceptions_subclass_base(self):
        for cls in (NetworkError, NotFoundError, ParseError, ServerError):
            assert issubclass(cls, TiktokshopError)

    def test_server_error_has_status_code(self):
        exc = ServerError("fail", status_code=503)
        assert exc.status_code == 503

    def test_network_error_message(self):
        exc = NetworkError("Connection refused")
        assert "Connection refused" in str(exc)

    def test_parse_error_message(self):
        exc = ParseError("Bad JSON")
        assert "Bad JSON" in str(exc)


# ---------------------------------------------------------------------------
# TiktokshopClient HTTP error mapping
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestClientHTTPErrors:
    def setup_method(self):
        self.client = TiktokshopClient()

    def teardown_method(self):
        self.client.close()

    def test_network_error_on_connect_failure(self):
        import httpx
        with patch.object(self.client._http, "get", side_effect=httpx.ConnectError("refused")):
            with pytest.raises(NetworkError):
                self.client._get_page_html("test")

    def test_network_error_on_timeout(self):
        import httpx
        with patch.object(self.client._http, "get", side_effect=httpx.TimeoutException("timed out")):
            with pytest.raises(NetworkError):
                self.client._get_page_html("test")

    def test_server_error_on_5xx(self):
        import httpx
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.text = "Service Unavailable"
        mock_resp.cookies = {}
        with patch.object(self.client._http, "get", return_value=mock_resp):
            with pytest.raises(ServerError) as exc_info:
                self.client._get_page_html("test")
        assert exc_info.value.status_code == 503

    def test_not_found_on_404(self):
        import httpx
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not Found"
        mock_resp.cookies = {}
        with patch.object(self.client._http, "get", return_value=mock_resp):
            with pytest.raises(NotFoundError):
                self.client._get_page_html("test")


# ---------------------------------------------------------------------------
# TiktokshopClient.search — mocked HTTP
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestClientSearchMocked:
    def setup_method(self):
        self.client = TiktokshopClient()

    def teardown_method(self):
        self.client.close()

    def test_empty_query_raises(self):
        with pytest.raises(TiktokshopError, match="cannot be empty"):
            self.client.search("")

    def test_whitespace_query_raises(self):
        with pytest.raises(TiktokshopError, match="cannot be empty"):
            self.client.search("   ")

    def test_search_returns_ssr_products(self):
        html = _make_ssr_html([_make_raw_product()])
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = html
        mock_resp.cookies = {}

        with patch.object(self.client._http, "get", return_value=mock_resp):
            result = self.client.search("proactiv", limit=30)

        assert result.query == "proactiv"
        assert len(result.products) == 1
        assert result.products[0].title == "Proactiv Solution Renewing Cleanser"

    def test_api_graceful_fallback_when_no_data(self):
        """When product_list API returns {code: 100000} with no 'data', pagination stops."""
        html = _make_ssr_html([_make_raw_product()])
        mock_get = MagicMock()
        mock_get.status_code = 200
        mock_get.text = html
        mock_get.cookies = {}

        mock_post = MagicMock()
        mock_post.status_code = 200
        mock_post.json.return_value = {"code": 100000}  # no "data" key

        with patch.object(self.client._http, "get", return_value=mock_get):
            with patch.object(self.client._http, "post", return_value=mock_post):
                result = self.client.search("proactiv", limit=60)

        # Should have only the 1 SSR product, not crash
        assert len(result.products) == 1

    def test_page_2_slices_correctly(self):
        """Page 2 returns products 30-60."""
        raw_products = [_make_raw_product(product_id=str(i), title=f"Product {i}") for i in range(60)]
        html = _make_ssr_html(raw_products[:30])

        mock_get = MagicMock()
        mock_get.status_code = 200
        mock_get.text = html
        mock_get.cookies = {}

        api_response_products = raw_products[30:]
        mock_post = MagicMock()
        mock_post.status_code = 200
        mock_post.json.return_value = {
            "data": {
                "products": api_response_products,
                "load_more_params": {"offset": 60, "page_token": "tok2"},
                "has_more": True,
            }
        }

        with patch.object(self.client._http, "get", return_value=mock_get):
            with patch.object(self.client._http, "post", return_value=mock_post):
                result = self.client.search("test", page=2)

        assert len(result.products) == 30
        assert result.products[0].title == "Product 30"
