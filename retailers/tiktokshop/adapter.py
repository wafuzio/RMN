# retailers/tiktokshop/adapter.py
"""
TikTok Shop adapter for the Retail Ad Monitor.

Captures product listings, featured brands, and main page screenshots.
Includes automatic CAPTCHA solving for TikTok's slide puzzle.
"""
from __future__ import annotations
import os
import glob
import time
from datetime import datetime
from core.retailers import RetailerAdapter, register


class TikTokShopAdapter(RetailerAdapter):
    slug = "tiktokshop"
    display_name = "TikTok Shop"
    profile_env = "TIKTOKSHOP_PROFILE_DIR"

    def search_and_capture(self, keyword: str, ctx) -> bool:
        """Execute TikTok Shop search and capture products/screenshots."""
        import sys
        
        # Add project root to path
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        sys.path.insert(0, project_root)
        
        # CRITICAL: Inject profile dir into environment so scraper uses same session
        if ctx.profile_dir and os.path.isdir(ctx.profile_dir):
            os.environ["TIKTOKSHOP_PROFILE_DIR"] = ctx.profile_dir
            print(f"[TikTokShop] Injected TIKTOKSHOP_PROFILE_DIR: {ctx.profile_dir}")
        else:
            print("⚠️ ctx.profile_dir missing or invalid; scraper may run without cookies")
        
        # Import the search_and_capture function from root directory
        from tiktokshop_search_and_capture import search_and_capture
        
        return search_and_capture(keyword, ctx.output_dir)

    def collect_pairs_for_run(self, ctx, run_start_ts: float):
        """Collect JSON/HTML pairs from the most recent run."""
        runs = os.path.join(ctx.output_dir, "runs")
        jsons = sorted(
            [p for p in glob.glob(os.path.join(runs, "run_results_*.json"))
             if os.path.getmtime(p) >= run_start_ts - 2],
            key=os.path.getmtime
        )
        pairs = []
        for j in jsons:
            h = j.replace("run_results_", "search_results_").replace(".json", ".html")
            if os.path.exists(h):
                pairs.append((j, h))
        return pairs

    def extract_images(self, json_path: str, html_path: str, ctx) -> dict:
        """
        Extract images - for TikTok Shop, screenshots are captured during search.
        This method counts what was captured.
        """
        import json
        from pathlib import Path
        
        # Load the JSON to see what was captured
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
        except Exception as e:
            print(f"[TikTokShop] Error loading JSON: {e}")
            return {"products": 0, "brands": 0, "main": 0}
        
        # Count captured items
        products = [a for a in data.get("ads", []) if a.get("type") == "Products"]
        brands = [a for a in data.get("ads", []) if a.get("type") == "Featured_Brands"]
        
        # Check for main screenshot
        main_screenshot = data.get("main_screenshot", "")
        main_path = os.path.join(ctx.output_dir, main_screenshot) if main_screenshot else ""
        has_main = 1 if main_path and os.path.exists(main_path) else 0
        
        # Count actual image files
        products_dir = os.path.join(ctx.output_dir, "Products")
        brands_dir = os.path.join(ctx.output_dir, "Featured_Brands")
        
        product_images = len(glob.glob(os.path.join(products_dir, "*.png"))) if os.path.isdir(products_dir) else 0
        brand_images = len(glob.glob(os.path.join(brands_dir, "*.png"))) if os.path.isdir(brands_dir) else 0
        
        return {
            "products": product_images,
            "brands": brand_images,
            "main": has_main,
            "log": json_path.replace(".json", ".log")
        }


# Register on import
register(TikTokShopAdapter())
