# retailers/amazon/adapter.py
from __future__ import annotations
import os, json, time, re, urllib.parse, glob
from datetime import datetime
from typing import List, Tuple, Dict
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError
from core.retailers import RetailerAdapter, register

class AmazonAdapter(RetailerAdapter):
    slug = "amazon"
    display_name = "Amazon"
    profile_env = "AMAZON_PROFILE_DIR"   # set this in your shell or GUI

    def _search_url(self, keyword: str, page: int = 1) -> str:
        q = urllib.parse.quote(keyword.strip())
        return f"https://www.amazon.com/s?k={q}&page={page}"

    def _launch_ctx(self, ctx):
        # ctx is RunContext from your framework
        from playwright.sync_api import sync_playwright
        p = sync_playwright().start()
        # Ensure Amazon uses its own profile, not walmart
        amazon_profile = os.path.expanduser("~/ChromeProfiles/amazon")
        profile_path = ctx.profile_dir or os.path.join(ctx.base_dir, "profiles", "amazon")
        if "walmart" in profile_path.lower():
            profile_path = amazon_profile
        browser_ctx = p.chromium.launch_persistent_context(
            user_data_dir=profile_path,
            channel="chrome",
            headless=True,
            viewport={"width": 1400, "height": 900},
            locale="en-US"
        )
        return p, browser_ctx

    def search_and_capture(self, keyword: str, ctx) -> bool:
        """Delegate to the main amazon_search_and_capture.search_and_capture.

        This ensures GUI runs use the same scraper logic as direct CLI runs.
        """
        # Ensure the profile env is wired for the main script
        if getattr(ctx, "profile_dir", None):
            os.environ.setdefault(self.profile_env, ctx.profile_dir)

        # Import here to avoid hard dependency at adapter import time
        from amazon_search_and_capture import search_and_capture as amz_search_and_capture

        # amazon_search_and_capture handles Playwright, logging, HTML/JSON, and images
        return amz_search_and_capture(keyword, ctx.output_dir)

    def collect_pairs_for_run(self, ctx, run_start_ts: float) -> List[Tuple[str, str]]:
        """Return all (json, html) pairs created since run_start_ts, just like Kroger."""
        runs = os.path.join(ctx.output_dir, "runs")
        jsons = sorted(
            [p for p in glob.glob(os.path.join(runs, "run_results_amazon_*.json"))
             if os.path.getmtime(p) >= (run_start_ts - 2)],
            key=os.path.getmtime
        )
        pairs = []
        for j in jsons:
            with open(j, "r", encoding="utf-8") as f:
                meta = json.load(f)
            h = os.path.join(runs, meta.get("html", "").strip())
            if os.path.exists(h):
                pairs.append((j, h))
        return pairs

    def extract_images(self, json_path: str, html_path: str, ctx) -> Dict:
        """
        Navigate live to the search URL again (using the same profile) and capture:
        - Sponsored Brand Video → Sponsored_Brand_Video
        - Sponsored Products → Sponsored_Product
        - Featured from Amazon brands → Featured_Brand
        - Sponsored Carousel → Sponsored_Carousel

        Returns {"toa": n, "sky": n, "car": n, "log": path}
        """
        with open(json_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        keyword = meta.get("keyword", "")
        url = meta.get("search_url") or self._search_url(keyword)

        p, bctx = self._launch_ctx(ctx)
        page = bctx.new_page()
        log_dir = ctx.logs_dir
        os.makedirs(log_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = os.path.join(log_dir, f"image_extract_{ts}.log")

        def safe_screenshot(locator, out_path) -> bool:
            try:
                locator.scroll_into_view_if_needed(timeout=2000)
                page.wait_for_timeout(200)
                locator.screenshot(path=out_path, timeout=3000)
                return True
            except Exception:
                return False

        counts = {"toa": 0, "sky": 0, "car": 0, "log": log_path}
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(1500)

            # Ensure main slot is present
            page.locator("div.s-main-slot").first.wait_for(timeout=6500)

            # 1) Sponsored Brand Video - Video ads at top of search
            sbv_dir = os.path.join(ctx.output_dir, "Sponsored_Brand_Video")
            os.makedirs(sbv_dir, exist_ok=True)
            sbv_candidates = [
                "div.AdHolder[data-cel-widget*='sb-video-product-collection']",
                "[cel_widget_id*='sb-video-product-collection']",
            ]
            for sel in sbv_candidates:
                loc = page.locator(sel).first
                if loc.count() > 0:
                    out = os.path.join(sbv_dir, f"amazon_sbv_{ctx.client}_{ts}.png")
                    if safe_screenshot(loc, out):
                        counts["toa"] += 1  # Keep toa count for backward compatibility
                        break

            # 2) Sponsored Products - Individual sponsored product listings
            sp_dir = os.path.join(ctx.output_dir, "Sponsored_Product")
            os.makedirs(sp_dir, exist_ok=True)
            sp_candidates = [
                "div.s-result-item:has(.puis-sponsored-label-text)",
                "[data-component-type='sp-sponsored-result']",
            ]
            sp_count = 0
            for sel in sp_candidates:
                locs = page.locator(sel).all()
                for i, loc in enumerate(locs[:5]):  # Capture first 5 sponsored products
                    out = os.path.join(sp_dir, f"amazon_sp_{ctx.client}_{ts}_{i}.png")
                    if safe_screenshot(loc, out):
                        sp_count += 1
                if sp_count > 0:
                    counts["sky"] = sp_count  # Keep sky count for backward compatibility
                    break

            # 3) Sponsored Carousel - Featured product carousels
            sc_dir = os.path.join(ctx.output_dir, "Sponsored_Carousel")
            os.makedirs(sc_dir, exist_ok=True)
            sc_candidates = [
                "div[cel_widget_id*='FEATURED_ASINS_LIST']",
                "div[data-cel-widget*='FEATURED_ASINS_LIST']",
            ]
            for sel in sc_candidates:
                loc = page.locator(sel).first
                if loc.count() > 0:
                    out = os.path.join(sc_dir, f"amazon_carousel_{ctx.client}_{ts}.png")
                    if safe_screenshot(loc, out):
                        counts["car"] += 1  # Keep car count for backward compatibility
                        break
            
            # 4) Featured Brand - "Featured from Amazon brands" products
            fb_dir = os.path.join(ctx.output_dir, "Featured_Brand")
            os.makedirs(fb_dir, exist_ok=True)
            fb_candidates = [
                ".puis-label-popover:has-text('Featured from Amazon brands')",
            ]
            fb_count = 0
            for sel in fb_candidates:
                # Find parent product containers
                locs = page.locator(f"div.s-result-item:has({sel})").all()
                for i, loc in enumerate(locs[:3]):  # Capture first 3 featured brands
                    out = os.path.join(fb_dir, f"amazon_featured_{ctx.client}_{ts}_{i}.png")
                    if safe_screenshot(loc, out):
                        fb_count += 1
                break

        except Exception as e:
            with open(log_path, "a", encoding="utf-8") as lf:
                lf.write(f"Error: {e}\n")
        finally:
            bctx.close()
            p.stop()

        return counts

register(AmazonAdapter())
