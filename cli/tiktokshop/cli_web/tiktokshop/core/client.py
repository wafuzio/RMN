"""HTTP client for cli-web-tiktokshop.

Strategy:
  1. GET the search page HTML to get cookies + SSR products + pagination token
  2. Parse __MODERN_ROUTER_DATA__ script tag to extract initial products
  3. POST /api/shop/brandy_desktop/s/product_list for additional pages
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from .exceptions import (
    NetworkError,
    NotFoundError,
    ParseError,
    TiktokshopError,
    raise_for_status,
)

BASE_URL = "https://shop.tiktok.com"

_COMPONENT_INFO = json.dumps({
    "component_type": "feed_list",
    "component_name": "feed_list_search_word",
    "fe_config": {
        "is_main_feed": True,
        "is_fmp_significant": True,
        "show_structure_data": False,
        "show_empty_page": True,
        "empty_text": {"title": "No results found", "sub_title": "Try another search"},
        "title": "Results for {keyword}",
        "data_source": {
            "type": "search_word",
            "storage_global_product_info": True,
            "params": {"count": 30, "clamp": True},
        },
    },
})

_SORT_MAP = {
    "best": None,
    "best-sellers": "ecom_sold_count",
    "price-asc": "ecom_price|ASC",
    "price-desc": "ecom_price|DESC",
    "newest": "ecom_publish_time",
}

_PRICE_RANGE_MAP = {
    "under-30": "ecom_max_price|30",
    "30-40": "ecom_price_stat|30,40",
    "40-100": "ecom_price_stat|40,100",
    "over-100": "ecom_low_price|100",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_API_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,*/*;q=0.8",
    "Content-Type": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://shop.tiktok.com/us/s",
}


@dataclass
class Product:
    product_id: str
    title: str
    price: str
    currency: str
    price_prefix: str
    rating: float | None
    review_count: str
    sold_count: int
    shop_name: str
    seller_id: str
    image_url: str
    seo_url: str
    brand_name: str | None = None

    def to_dict(self) -> dict:
        return {
            "product_id": self.product_id,
            "title": self.title,
            "price": self.price,
            "currency": self.currency,
            "price_prefix": self.price_prefix,
            "rating": self.rating,
            "review_count": self.review_count,
            "sold_count": self.sold_count,
            "shop_name": self.shop_name,
            "seller_id": self.seller_id,
            "image_url": self.image_url,
            "url": (f"https://shop.tiktok.com{self.seo_url}" if self.seo_url.startswith("/") else self.seo_url) if self.seo_url else "",
            "brand_name": self.brand_name,
        }


@dataclass
class SearchResult:
    query: str
    products: list[Product]
    has_more: bool
    page: int = 1
    _load_more_params: dict = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict:
        d = {
            "query": self.query,
            "page": self.page,
            "count": len(self.products),
            "has_more": self.has_more,
            "products": [p.to_dict() for p in self.products],
        }
        if self.has_more:
            d["next_page"] = self.page + 1
        return d


def _parse_product(raw: dict) -> Product:
    """Parse a raw product dict from the API response."""
    price_info = raw.get("product_price_info", {})
    rate_info = raw.get("rate_info", {})
    sold_info = raw.get("sold_info", {})
    seller_info = raw.get("seller_info", {})
    brand_info = raw.get("brand_info", {})

    image_url = ""
    img = raw.get("image", {})
    url_list = img.get("url_list", [])
    if url_list:
        image_url = url_list[0]

    seo_url_raw = raw.get("seo_url", "")
    if isinstance(seo_url_raw, dict):
        seo_url = seo_url_raw.get("canonical_url", "")
    elif isinstance(seo_url_raw, str):
        seo_url = seo_url_raw
    else:
        seo_url = ""
    if not seo_url:
        pid = raw.get("product_id", "")
        title_slug = re.sub(r"[^a-z0-9]+", "-", raw.get("title", "").lower()).strip("-")
        seo_url = f"https://shop.tiktok.com/us/pdp/{title_slug}/{pid}" if pid else ""

    return Product(
        product_id=raw.get("product_id", ""),
        title=raw.get("title", ""),
        price=price_info.get("sale_price_format", ""),
        currency=price_info.get("currency_name", "USD"),
        price_prefix=price_info.get("price_prefix", ""),
        rating=rate_info.get("score") or None,
        review_count=str(rate_info.get("review_count", "")),
        sold_count=sold_info.get("sold_count", 0),
        shop_name=seller_info.get("shop_name", ""),
        seller_id=seller_info.get("seller_id", ""),
        image_url=image_url,
        seo_url=seo_url,
        brand_name=brand_info.get("brand_name") if brand_info else None,
    )


class TiktokshopClient:
    """Client for TikTok Shop search API."""

    def __init__(self):
        self._http = httpx.Client(
            timeout=httpx.Timeout(connect=15.0, read=30.0, write=30.0, pool=30.0),
            follow_redirects=True,
        )
        self._cookies: dict = {}

    def _get_page_html(self, query: str) -> str:
        """GET the search page HTML, saving cookies for subsequent API calls."""
        url = f"{BASE_URL}/us/s"
        try:
            resp = self._http.get(
                url,
                params={"q": query},
                headers=_HEADERS,
                cookies=self._cookies or None,
            )
        except httpx.ConnectError as exc:
            raise NetworkError(f"Connection failed: {exc}")
        except httpx.TimeoutException as exc:
            raise NetworkError(f"Request timed out: {exc}")
        raise_for_status(resp)
        # Persist cookies for API calls
        self._cookies = dict(resp.cookies)
        return resp.text

    def _parse_ssr_data(self, html: str, query: str) -> tuple[list[Product], dict]:
        """Extract products and load_more_params from SSR HTML."""
        m = re.search(
            r'<script[^>]*id="__MODERN_ROUTER_DATA__"[^>]*>(.*?)</script>',
            html,
            re.DOTALL,
        )
        if not m:
            raise ParseError("Could not find __MODERN_ROUTER_DATA__ in page HTML")

        try:
            data = json.loads(m.group(1).strip())
        except json.JSONDecodeError as exc:
            raise ParseError(f"Failed to parse page state JSON: {exc}")

        try:
            page_data = data["loaderData"]["(region)/(route_page_name)/page"]
            components = page_data["page_config"]["components_map"]
        except (KeyError, TypeError) as exc:
            raise ParseError(f"Unexpected page state structure: {exc}")

        # Find the main search results component
        search_comp = None
        for c in components:
            if c.get("component_name") == "feed_list_search_word":
                search_comp = c
                break

        if not search_comp:
            return [], {"offset": 0, "page_token": "", "api_source": 2}

        cd = search_comp.get("component_data", {})
        raw_products = cd.get("products", [])
        load_more = cd.get("load_more_params", {})

        # Inject search_word if missing (needed for API pagination calls)
        if "search_word" not in load_more:
            load_more["search_word"] = query

        products = [_parse_product(p) for p in raw_products]
        return products, load_more

    def _api_product_list(
        self,
        load_more_params: dict,
        filters: list[dict] | None = None,
    ) -> tuple[list[Product], dict, bool]:
        """Call the product_list API for a page of results."""
        params_with_filters = {**load_more_params}
        if filters:
            params_with_filters["filters"] = filters
        elif "filters" not in params_with_filters:
            params_with_filters["filters"] = []
        if "exclude_product_ids" not in params_with_filters:
            params_with_filters["exclude_product_ids"] = []
        if "seller_id" not in params_with_filters:
            params_with_filters["seller_id"] = ""

        req_body = {
            "component_info": _COMPONENT_INFO,
            "load_more_params": json.dumps(params_with_filters),
        }

        try:
            resp = self._http.post(
                f"{BASE_URL}/api/shop/brandy_desktop/s/product_list",
                json=req_body,
                headers=_API_HEADERS,
                cookies=self._cookies or None,
            )
        except httpx.ConnectError as exc:
            raise NetworkError(f"Connection failed: {exc}")
        except httpx.TimeoutException as exc:
            raise NetworkError(f"Request timed out: {exc}")
        raise_for_status(resp)

        try:
            resp_body = resp.json()
            if "data" not in resp_body:
                # API returned {code: 100000} without data — token expired or not set.
                # Stop paginating rather than raising.
                return [], {}, False
            data = resp_body["data"]
        except (ValueError,) as exc:
            raise ParseError(f"Unexpected API response: {exc}")

        products = [_parse_product(p) for p in data.get("products", [])]
        next_params = data.get("load_more_params", {})
        has_more = bool(data.get("has_more", False))
        return products, next_params, has_more

    def search(
        self,
        query: str,
        *,
        sort: str = "best",
        limit: int = 30,
        page: int = 1,
        price_range: str | None = None,
    ) -> SearchResult:
        """Search for products.

        Args:
            query: Search keyword.
            sort: Sort order — best, price-asc, price-desc, newest, best-sellers.
            limit: Max products to return (default 30, max ~300).
            page: Page number starting at 1.
            price_range: Optional price filter — under-30, 30-40, 40-100, over-100.
        """
        if not query or not query.strip():
            raise TiktokshopError("Search query cannot be empty")

        sort_filter_id = _SORT_MAP.get(sort)
        price_filter_id = _PRICE_RANGE_MAP.get(price_range) if price_range else None

        filters = []
        if sort_filter_id:
            filters.append({"filter_option_id": sort_filter_id})
        if price_filter_id:
            filters.append({"filter_option_id": price_filter_id})

        # Always load page 1 from HTML (SSR)
        html = self._get_page_html(query)
        ssr_products, load_more = self._parse_ssr_data(html, query)

        all_products = list(ssr_products)
        has_more = bool(load_more)
        current_params = {**load_more, "search_word": query}

        # Add filters to initial params
        if filters and "filters" not in current_params:
            current_params["filters"] = filters

        # Calculate which pages we need (each page is ~30 products)
        target_page_end = page * 30  # last product index we want
        target_start = (page - 1) * 30  # first product index we want

        # Paginate until we have enough products
        page_count = 0
        max_api_pages = 10
        while len(all_products) < target_page_end and has_more and page_count < max_api_pages:
            new_products, next_params, has_more = self._api_product_list(
                current_params, filters=filters if filters else None
            )
            if not new_products:
                break
            all_products.extend(new_products)
            current_params = {**next_params, "search_word": query}
            page_count += 1

        # Slice to the requested page
        page_products = all_products[target_start:target_page_end]
        page_products = page_products[:limit]

        return SearchResult(
            query=query,
            products=page_products,
            has_more=has_more or len(all_products) > target_page_end,
            page=page,
            _load_more_params=current_params,
        )

    def suggest(self, query: str) -> list[str]:
        """Get related search terms for a query (extracted from page HTML)."""
        html = self._get_page_html(query)
        return self._extract_related_searches(html)

    def _extract_related_searches(self, html: str) -> list[str]:
        """Extract related search keywords from the SSR HTML."""
        try:
            m = re.search(
                r'<script[^>]*id="__MODERN_ROUTER_DATA__"[^>]*>(.*?)</script>',
                html,
                re.DOTALL,
            )
            if not m:
                return []
            data = json.loads(m.group(1).strip())
            page_config = data["loaderData"]["(region)/(route_page_name)/page"]["page_config"]
            components = page_config.get("components_map", [])
            for comp in components:
                if comp.get("component_name") == "related_link_search_words":
                    links = comp.get("component_data", {}).get("related_links", [])
                    return [lnk["name"] for lnk in links if "name" in lnk]
        except (KeyError, TypeError, json.JSONDecodeError):
            pass
        return []

    def close(self):
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
