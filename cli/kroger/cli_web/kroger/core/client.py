"""HTTP client for cli-web-kroger.

Kroger's product API is public (no login required for search/detail/reviews).
Akamai Bot Manager blocks headless Chromium — we use real Google Chrome with a
persistent user profile (same strategy as the Walmart CLI for PerimeterX).

Chrome is launched with headless=False (visible) but positioned off-screen so
the window is out of the way. The persistent profile accumulates valid Akamai
cookies over time, making subsequent runs faster.

API calls are intercepted via Playwright's response handler, so we get the raw
JSON that the browser fetches natively — no curl_cffi needed.

KROGER PERFORMANCE NOTE:
Kroger.com is notoriously slow to load its JS modules. All timeouts are set
generously. Lazy-loaded content (CuratedCarousel images, sponsored tiles) only
renders after the element enters the viewport — always wait after scrolling,
never assume content is ready immediately.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .exceptions import (
    KrogerError,
    NetworkError,
    NotFoundError,
)

BASE_URL = "https://www.kroger.com"
PROFILE_DIR = Path.home() / ".config" / "cli-web-kroger" / "browser-profile"
DEFAULT_LOCATION_ID = "70100070"

_context = None
_playwright = None


def _get_context():
    """Return shared Chrome browser context, creating it if needed."""
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
    _playwright = sync_playwright().start()
    _context = _playwright.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        channel="chrome",             # Real Google Chrome — bypasses Akamai
        headless=False,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--window-position=-10000,-10000",  # Off-screen — effectively hidden
        ],
        viewport={"width": 1280, "height": 800},
        locale="en-US",
    )
    return _context


def _close_context() -> None:
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


def _dismiss_kroger_modal(page) -> bool:
    """Dismiss the 'Improving your experience' modality-selector modal.

    Two-phase approach:
      1. Try clicking a dismiss/continue button (fast path, respects UX).
      2. Regardless of phase 1, scrub modal/overlay elements from the DOM so
         page.content() never includes the popup in captured HTML.

    Returns True if a button was successfully clicked.
    """
    # Phase 1 — try to click a dismiss button (3 s timeout each)
    dismiss_selectors = [
        "[data-testid='ModalitySelector--btnContinue']",
        "[data-testid='ModalitySelector--close']",
        "[data-testid='modal-close-button']",
        "button[aria-label='Close']",
        "button[aria-label='close']",
        "button:has-text('Continue')",
        "button:has-text('Got it')",
        "button:has-text('No, thanks')",
        "button:has-text('Accept')",
        "button:has-text('Close')",
    ]
    clicked = False
    for sel in dismiss_selectors:
        try:
            page.locator(sel).first.click(timeout=3000)
            clicked = True
            page.wait_for_timeout(500)
            break
        except Exception:
            continue

    # Phase 2 — scrub modal/dialog/overlay elements from DOM so they never
    # appear in page.content(). Runs unconditionally — belt-and-suspenders.
    try:
        page.evaluate("""() => {
            const targets = [
                '[role="dialog"]',
                '[aria-modal="true"]',
                '[data-testid*="Modal"]',
                '[data-testid*="modal"]',
                '[data-testid*="Modality"]',
                '.ReactModal__Overlay',
                '.ReactModal__Content',
                '.modal-overlay',
                '.ModalitySelector',
            ];
            targets.forEach(sel => {
                document.querySelectorAll(sel).forEach(el => {
                    el.remove();
                });
            });
        }""")
    except Exception:
        pass

    return clicked


def _scroll_and_lazy_load(page, scroll_pause_ms: int = 2000) -> None:
    """Scroll through the page in bursts to trigger lazy-loaded content.

    Kroger lazy-loads carousels and sponsored tiles as they enter the viewport.
    Waits generously after each scroll — Kroger's module loading is slow and
    content is not ready immediately after the element enters view.

    Scrolls back to top at the end so page.content() captures the full
    above-the-fold layout for screenshots.
    """
    viewport_h = page.evaluate("window.innerHeight") or 800
    # Step ≈ 1.5× viewport — overlapping windows ensure nothing is skipped
    step = int(viewport_h * 1.5)

    position = 0
    while True:
        total_h = page.evaluate("document.body.scrollHeight") or 0
        if position >= total_h:
            break
        page.evaluate(f"window.scrollBy(0, {step})")
        position += step
        # Generous pause — Kroger is slow; images need time to actually render
        page.wait_for_timeout(scroll_pause_ms)

    # Backscroll peek: scroll back up partway so above-the-fold content
    # is visible again (lazy-unload protection on some browsers)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(1500)

    # Wait for CuratedCarousel images to finish loading
    try:
        page.wait_for_selector(
            "div.CuratedCarousel img",
            state="visible",
            timeout=10000,
        )
        page.wait_for_timeout(1000)  # extra settle time after first image visible
    except Exception:
        pass  # no carousels on this page — that's fine


def _navigate_and_capture(
    nav_url: str,
    capture_fragment: str,
    timeout_ms: int = 30000,
) -> dict:
    """Navigate to *nav_url* and return the first API response matching *capture_fragment*.

    Uses page.expect_response() — the idiomatic Playwright pattern for response
    capture. Avoids calling response.body() inside an event handler (which
    deadlocks in Playwright's sync API).
    """
    ctx = _get_context()
    page = ctx.new_page()
    try:
        with page.expect_response(
            lambda r: capture_fragment in r.url,
            timeout=timeout_ms + 15000,
        ) as response_info:
            try:
                page.goto(nav_url, wait_until="domcontentloaded", timeout=timeout_ms)
            except Exception:
                pass  # partial load is fine — we just need the API response
        body = response_info.value.body()
        return json.loads(body)
    except Exception as exc:
        raise NetworkError(
            f"Timed out waiting for {capture_fragment!r} API response "
            f"while navigating {nav_url}"
        ) from exc
    finally:
        try:
            page.close()
        except Exception:
            pass


class KrogerClient:
    """Kroger atlas/v1 client via Chrome navigation + response interception."""

    def __init__(self, location_id: str = DEFAULT_LOCATION_ID):
        self.location_id = location_id

    def search_products(
        self,
        query: str,
        *,
        location_id: str | None = None,
        fulfillment: str | None = None,
        limit: int = 30,
        offset: int = 0,
    ) -> list[dict]:
        """Search Kroger products by keyword."""
        from urllib.parse import urlencode

        params: dict = {"query": query, "searchType": "default_search"}
        nav_url = BASE_URL + "/search?" + urlencode(params)
        data = _navigate_and_capture(nav_url, "products-search")
        return data.get("data", {}).get("productsSearch", [])

    def get_product(
        self,
        upc: str,
        *,
        location_id: str | None = None,
    ) -> dict:
        """Get full product details by UPC/GTIN13. Raises NotFoundError if missing."""
        nav_url = BASE_URL + f"/p/-/{upc}"
        data = _navigate_and_capture(nav_url, "product/v2/products")
        products = data.get("data", {}).get("products", [])
        if not products:
            raise NotFoundError(f"Product not found: {upc}")
        return products[0]

    def get_reviews(
        self,
        upc: str,
        *,
        limit: int = 16,
        offset: int = 0,
    ) -> dict:
        """Get product reviews. Returns data.reviews dict."""
        nav_url = BASE_URL + f"/p/-/{upc}"
        data = _navigate_and_capture(nav_url, f"reviews/v1/item/{upc}/reviews")
        return data.get("data", {}).get("reviews", {})

    def get_coupons(self, upc: str) -> list[dict]:
        """Get available digital coupons for a product UPC."""
        nav_url = BASE_URL + f"/p/-/{upc}"
        data = _navigate_and_capture(nav_url, "savings-coupons/v1/coupons")
        return data.get("data", {}).get("coupons", [])

    def get_recommendations(self, upc: str, *, limit: int = 10) -> list[dict]:
        """Get better-for-you product alternatives."""
        nav_url = BASE_URL + f"/p/-/{upc}"
        data = _navigate_and_capture(nav_url, "better-for-you")
        return data.get("data", {}).get("betterForYou", [])

    def capture_search_html(
        self,
        query: str,
        *,
        output_dir: str | Path | None = None,
        scroll_pause_ms: int = 2000,
        screenshot: bool = True,
    ) -> dict:
        """Navigate to a search page, lazy-load all content, dismiss any modal,
        and return the fully-rendered HTML + screenshot.

        Artifacts are saved under *output_dir* (default: ./runs/<run_id>/).

        Returns a dict with:
          - run_id: str
          - html_path: str  — path to saved .html file
          - screenshot_path: str | None  — path to full-page .png (if screenshot=True)
          - html: str  — the raw HTML string
        """
        from urllib.parse import urlencode

        run_id = str(int(time.time()))
        safe_query = query.replace(" ", "_")[:40]

        if output_dir is None:
            output_dir = Path.cwd() / "runs" / run_id
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        params: dict = {"query": query, "searchType": "default_search"}
        nav_url = BASE_URL + "/search?" + urlencode(params)

        ctx = _get_context()
        page = ctx.new_page()
        try:
            # Navigate and wait for Atlas search API response (confirms page loaded)
            with page.expect_response(
                lambda r: "products-search" in r.url,
                timeout=45000,
            ):
                try:
                    page.goto(nav_url, wait_until="domcontentloaded", timeout=30000)
                except Exception:
                    pass  # partial load is fine — we just need the search API to fire

            # Dismiss "Improving your experience" modal (click + DOM scrub)
            _dismiss_kroger_modal(page)

            # Scroll through page to trigger lazy-loaded carousels + sponsored tiles
            _scroll_and_lazy_load(page, scroll_pause_ms=scroll_pause_ms)

            # Full-page screenshot (before page.content() so layout is intact)
            screenshot_path = None
            if screenshot:
                screenshot_path = output_dir / f"screenshot_{safe_query}_{run_id}.png"
                try:
                    page.screenshot(
                        path=str(screenshot_path),
                        full_page=True,
                        timeout=15000,
                    )
                except Exception:
                    screenshot_path = None

            # Grab fully-rendered HTML (modal already scrubbed from DOM)
            html = page.content()
            html_path = output_dir / f"search_results_{safe_query}_{run_id}.html"
            html_path.write_text(html, encoding="utf-8")

            return {
                "run_id": run_id,
                "query": query,
                "html_path": str(html_path),
                "screenshot_path": str(screenshot_path) if screenshot_path else None,
                "html": html,
            }
        except Exception as exc:
            raise NetworkError(
                f"HTML capture failed for query {query!r}: {exc}"
            ) from exc
        finally:
            try:
                page.close()
            except Exception:
                pass

    def close(self):
        _close_context()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
