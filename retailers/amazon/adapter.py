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
    profile_env = "AMZ_PROFILE_DIR"   # set this in your shell or GUI

    def _search_url(self, keyword: str, page: int = 1) -> str:
        q = urllib.parse.quote(keyword.strip())
        return f"https://www.amazon.com/s?k={q}&page={page}"

    def _launch_ctx(self, ctx):
        # ctx is RunContext from your framework
        from playwright.sync_api import sync_playwright
        p = sync_playwright().start()
        browser_ctx = p.chromium.launch_persistent_context(
            user_data_dir=ctx.profile_dir or os.path.join(ctx.base_dir, "profiles", "amazon"),
            channel="chrome",
            headless=True,
            viewport={"width": 1400, "height": 900},
            locale="en-US"
        )
        return p, browser_ctx

    def search_and_capture(self, keyword: str, ctx) -> bool:
        """Navigate to Amazon search, save HTML + JSON run record."""
        p, bctx = self._launch_ctx(ctx)
        success = False
        page = bctx.new_page()
        url = self._search_url(keyword, page=1)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            # let the page settle a bit
            page.wait_for_timeout(1200)
            html = page.content()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            runs = os.path.join(ctx.output_dir, "runs")
            os.makedirs(runs, exist_ok=True)
            html_path = os.path.join(runs, f"search_results_amazon_{ctx.client}_{ts}.html")
            json_path = os.path.join(runs, f"run_results_amazon_{ctx.client}_{ts}.json")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
            run = {
                "retailer": "amazon",
                "client": ctx.client,
                "keyword": keyword,
                "search_url": url,
                "ts": ts,
                "html": os.path.basename(html_path),
            }
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(run, f, indent=2)
            success = True
        finally:
            bctx.close()
            p.stop()
        return success

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
        - Top-of-search Sponsored Brands / Video banner → TOA
        - Right-rail Sponsored Display (if present) → Skyscraper
        - Sponsored Products top strip / first row → Carousel

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

            # 1) TOA: Sponsored Brands banner (headline) or video at top
            # These selectors are starting points; we'll refine them with live pages.
            toa_candidates = [
                "div.s-main-slot div:has(span:has-text('Sponsored')):nth-match(1)",
                "div[data-component-type='sbv-result']",
                "div[data-component-type='s-searchgrid-carousel']",
            ]
            toa_dir = os.path.join(ctx.output_dir, "TOA"); os.makedirs(toa_dir, exist_ok=True)
            hit = False
            for sel in toa_candidates:
                loc = page.locator(sel).first
                if loc.count() > 0:
                    out = os.path.join(toa_dir, f"amazon_toa_{ctx.client}_{ts}.png")
                    if safe_screenshot(loc, out):
                        counts["toa"] += 1
                        hit = True
                        break
            # If nothing matched, grab the very top viewport as a fallback "top-of-search"
            if not hit:
                out = os.path.join(toa_dir, f"amazon_toa_{ctx.client}_{ts}.png")
                page.screenshot(path=out, clip={"x": 0, "y": 0, "width": 1400, "height": 500})
                counts["toa"] += 1

            # 2) Skyscraper (right rail sponsored display) – shown on some pages
            sky_dir = os.path.join(ctx.output_dir, "Skyscraper"); os.makedirs(sky_dir, exist_ok=True)
            sky_candidates = [
                "#rhf",                      # Rare Amazon right-hand feature area
                "div#ad-left-1",             # placeholder examples
                "div#ad-right-1",
            ]
            for sel in sky_candidates:
                loc = page.locator(sel).first
                if loc.count() > 0:
                    out = os.path.join(sky_dir, f"amazon_sky_{ctx.client}_{ts}.png")
                    if safe_screenshot(loc, out):
                        counts["sky"] += 1
                        break

            # 3) Carousel: top-of-search Sponsored Products strip / first row
            car_dir = os.path.join(ctx.output_dir, "Carousel"); os.makedirs(car_dir, exist_ok=True)
            car_candidates = [
                "div[data-component-type='sp-sponsored-result'] >> nth=0..5",
                "div.s-main-slot div:has(span:has-text('Sponsored'))",
            ]
            # Strategy: screenshot the first sponsored product row (up to a reasonable width)
            try:
                first_sp = page.locator("div[data-component-type='sp-sponsored-result']").first
                if first_sp.count() > 0:
                    row = first_sp.locator("xpath=ancestor::div[contains(@class,'s-main-slot')]")
                    out = os.path.join(car_dir, f"amazon_car_{ctx.client}_{ts}.png")
                    if safe_screenshot(row, out):
                        counts["car"] += 1
            except Exception:
                pass

        except Exception as e:
            with open(log_path, "a", encoding="utf-8") as lf:
                lf.write(f"Error: {e}\n")
        finally:
            bctx.close()
            p.stop()

        return counts

register(AmazonAdapter())
