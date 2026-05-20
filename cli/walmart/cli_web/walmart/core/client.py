"""Walmart HTTP client using Playwright with Chrome persistent profile.

Walmart is protected by PerimeterX, which blocks direct HTTP requests and
plain Playwright Chromium. This client uses real Google Chrome with a persistent
user data directory to maintain a trusted browser profile.

The playwright context is opened once per CLI invocation and shared across
all commands via the singleton pattern.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import quote_plus

from .exceptions import (
    AuthError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    ServerError,
    WalmartError,
    raise_for_status,
)
from .models import ProductDetail, SearchItem, SearchResults

# Browser profile persisted here — PerimeterX trusts real Chrome profiles
PROFILE_DIR = Path.home() / ".config" / "cli-web-walmart" / "browser-profile"
BASE_URL = "https://www.walmart.com"

# Singleton playwright context — opened once, reused across all commands
_context = None
_playwright = None

# HTTP status → exception mapping (used by raise_for_status in exceptions.py):
# 401/403 → AuthError, 404 → NotFoundError, 429 → RateLimitError, 5xx → ServerError


def _profile_established() -> bool:
    """Return True if the Chrome profile has been set up (not first run)."""
    return (PROFILE_DIR / "Default" / "Cookies").exists()


def _get_context():
    """Return the shared playwright browser context, creating it if needed.

    Uses headless=True when the profile is already established (subsequent runs),
    headless=False only for the very first run so PerimeterX can validate real Chrome.
    """
    global _context, _playwright

    if _context is not None:
        try:
            _context.pages  # health check
            return _context
        except Exception:
            _context = None
            _playwright = None

    from playwright.sync_api import sync_playwright

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    # Always use headless=False — PerimeterX detects and blocks headless Chrome
    # even with an established profile. The visible browser is required on every run.
    _playwright = sync_playwright().start()
    _context = _playwright.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        channel="chrome",            # Real Google Chrome — bypasses PerimeterX
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
        viewport={"width": 1280, "height": 800},
        locale="en-US",
    )
    return _context


class _ClientContextManager:
    """Context manager wrapper for use-as-with-block support.

    Usage::

        with _ClientContextManager():
            results = search("coffee")
    """

    def __enter__(self):
        return self

    def __exit__(self, *args):
        close_context()


def close_context() -> None:
    """Close the browser context. Call at CLI exit."""
    global _context, _playwright
    if _context is not None:
        try:
            _context.close()
        except Exception:
            pass
        _context = None
    if _playwright is not None:
        try:
            _playwright.stop()
        except Exception:
            pass
        _playwright = None


def _fetch_next_data(url: str) -> dict:
    """Fetch a Walmart page and extract __NEXT_DATA__ JSON.

    Returns the parsed __NEXT_DATA__ dict.
    Raises WalmartError subclasses on failure.
    """
    ctx = _get_context()
    page = ctx.new_page()
    try:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
        except Exception as e:
            if "timeout" not in str(e).lower():
                raise NetworkError(f"Navigation failed: {e}") from e
            time.sleep(1)  # page may still be usable after domcontentloaded timeout

        current_url = page.url
        if "blocked" in current_url or "captcha" in current_url.lower():
            raise WalmartError(
                "Walmart blocked this request. The browser profile may need to be "
                "re-established. Try running the command again."
            )

        raw = page.evaluate(
            "() => { const el = document.getElementById('__NEXT_DATA__'); "
            "return el ? el.textContent : null; }"
        )
        if not raw:
            raise WalmartError(
                f"No __NEXT_DATA__ at {url}. The page structure may have changed."
            )

        return json.loads(raw)

    finally:
        page.close()


def _parse_items(next_data: dict) -> tuple[list[dict], int]:
    """Extract raw item dicts and total count from __NEXT_DATA__."""
    try:
        props = next_data.get("props", {}).get("pageProps", {})
        sr = props.get("initialData", {}).get("searchResult", {})
        total = sr.get("aggregatedCount", 0)
        stacks = sr.get("itemStacks", [])
        items = []
        for stack in stacks:
            for item in stack.get("items", []):
                if isinstance(item, dict) and item.get("name"):
                    items.append(item)
        return items, total
    except Exception as e:
        raise WalmartError(f"Failed to parse search results: {e}") from e


# ── Public API ─────────────────────────────────────────────────────────────────


def search(query: str, page: int = 1) -> SearchResults:
    """Search Walmart for products matching *query*.

    Args:
        query: Search terms (e.g. "dark roast coffee").
        page:  Results page number (1-based, ~40-60 items each).

    Returns:
        SearchResults with items list, total_count, and page info.
    """
    url = f"{BASE_URL}/search?q={quote_plus(query)}&page={page}"
    nd = _fetch_next_data(url)
    raw_items, total = _parse_items(nd)
    items = [SearchItem.from_dict(i) for i in raw_items]
    return SearchResults(query=query, total_count=total, page=page, items=items)


def detail(item_id: str) -> ProductDetail:
    """Fetch full product detail for *item_id*.

    Args:
        item_id: Walmart item ID (usItemId), e.g. "10534406".

    Returns:
        ProductDetail with full product information.

    Raises:
        NotFoundError: If the item does not exist.
    """
    url = f"{BASE_URL}/ip/-/{item_id}"
    nd = _fetch_next_data(url)

    if "404" in nd.get("page", ""):
        raise NotFoundError(f"Product not found: {item_id}")

    try:
        props = nd.get("props", {}).get("pageProps", {})
        product_data = props.get("initialData", {}).get("data", {}).get("product", {})
        if not product_data:
            raise NotFoundError(f"Product not found: {item_id}")
        return ProductDetail.from_dict(product_data)
    except NotFoundError:
        raise
    except Exception as e:
        raise WalmartError(f"Failed to parse product detail: {e}") from e


def browse(category_path: str, page: int = 1) -> SearchResults:
    """Browse a Walmart category page.

    Args:
        category_path: Path after /browse/ (e.g. "food/coffee/976759_976787_1001080").
        page: Results page number (1-based).

    Returns:
        SearchResults with category items.
    """
    path = category_path.lstrip("/")
    url = f"{BASE_URL}/browse/{path}?page={page}"
    nd = _fetch_next_data(url)
    raw_items, total = _parse_items(nd)
    items = [SearchItem.from_dict(i) for i in raw_items]
    label = path.split("/")[-1].replace("_", ",")
    return SearchResults(query=f"browse:{label}", total_count=total, page=page, items=items)
