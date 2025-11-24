# retailers/target/adapter.py
from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, Any

from core.retailers import RetailerAdapter, register


class TargetAdapter(RetailerAdapter):
    """Target.com adapter integrating with canonical target_search_and_capture.

    This adapter is thin glue:
    - Resolves the Target Playwright profile directory.
    - Sets TARGET_PROFILE_DIR env var for the root search script.
    - Delegates search and capture to target_search_and_capture.search_and_capture.
    """

    slug = "target"
    display_name = "Target"
    profile_env = "TARGET_PROFILE_DIR"

    def _resolve_profile_dir(self, ctx) -> str | None:
        """Pick a profile directory for Target.

        Priority:
        1) ctx.profile_dir if set and exists
        2) $TARGET_PROFILE_DIR env var if set and exists
        3) fallback to profiles/target_playwright_profile under project root if exists
        """
        # 1) ctx.profile_dir
        profile_dir = getattr(ctx, "profile_dir", None)
        if profile_dir and os.path.isdir(profile_dir):
            return profile_dir

        # 2) env var
        env_dir = os.environ.get(self.profile_env)
        if env_dir and os.path.isdir(env_dir):
            return env_dir

        # 3) project-local fallback
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        fallback = os.path.join(project_root, "profiles", "target")
        if os.path.isdir(fallback):
            return fallback

        return None

    def search_and_capture(self, keyword: str, ctx) -> bool:
        """Execute Target search and capture via root target_search_and_capture script."""
        import sys

        # Ensure project root is on sys.path so target_search_and_capture can be imported
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        try:
            from target_search_and_capture import search_and_capture as core_sc
        except Exception as e:
            print(f"❌ Failed to import target_search_and_capture: {e}")
            return False

        # Resolve and export profile dir for the core script
        profile_dir = self._resolve_profile_dir(ctx)
        if profile_dir:
            os.environ[self.profile_env] = profile_dir

        return core_sc(keyword, ctx.output_dir, headless=False)

    def collect_pairs_for_run(self, ctx, run_start_ts: float):
        """Collect JSON/HTML pairs from the most recent Target run.

        Mirrors Instacart/Walmart naming: run_results_*.json + search_results_*.html
        under ctx.output_dir/runs.
        """
        import glob

        runs = os.path.join(ctx.output_dir, "runs")
        jsons = sorted(
            [
                p
                for p in glob.glob(os.path.join(runs, "run_results_*.json"))
                if os.path.getmtime(p) >= run_start_ts - 2
            ],
            key=os.path.getmtime,
        )
        pairs = []
        for j in jsons:
            h = j.replace("run_results_", "search_results_").replace(".json", ".html")
            if os.path.exists(h):
                pairs.append((j, h))
        return pairs

    def extract_images(self, json_path: str, html_path: str, ctx) -> dict:
        """Download Target ad images based on image_url in run JSON.

        - Saves images under ListingPageBannerAd/ and Sponsored_Logo/ folders
          within ctx.output_dir (which is output/target/<client>).
        - Uses canonical filenames via filename_utils.generate_ad_filename.
        - Updates ads[].image_path in the JSON to a relative path.

        Returns a summary dict with keys toa/sky/car for GUI compatibility:
        - toa: ListingPageBannerAd count
        - sky: Sponsored_Logo count
        - car: 0 (no carousel type for Target)
        """
        import json
        from datetime import datetime
        from pathlib import Path
        from types import SimpleNamespace

        from filename_utils import generate_ad_filename
        from utils.path_taxonomy import ensure_subdir
        from extractors.screenshot_ad_image import direct_download_image

        os.makedirs(ctx.logs_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = os.path.join(ctx.logs_dir, f"target_image_extract_{ts}.log")

        log_lines: list[str] = []

        def log(msg: str) -> None:
            print(msg)
            log_lines.append(msg)

        # Load run JSON
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                run = json.load(f)
        except Exception as e:
            log(f"❌ Failed to read Target run JSON: {e}")
            with open(log_path, "w", encoding="utf-8") as lf:
                lf.write("\n".join(log_lines))
            return {"toa": 0, "sky": 0, "car": 0, "log": log_path}

        ads = run.get("ads") or []
        if not ads:
            log("[target] No ads[] in run JSON; nothing to extract")
            with open(log_path, "w", encoding="utf-8") as lf:
                lf.write("\n".join(log_lines))
            return {"toa": 0, "sky": 0, "car": 0, "log": log_path}

        keyword = run.get("keyword", "unknown")
        run_ts = run.get("run_id") or run.get("timestamp") or ts
        referer = run.get("url_after") or "https://www.target.com/"

        client = getattr(ctx, "client", None) or run.get("client", "unknown_client")
        output_root = Path(ctx.output_dir)

        banner_count = 0
        logo_count = 0

        for idx, ad in enumerate(ads, start=1):
            img_url = ad.get("image_url")
            if not img_url:
                continue

            ad_type = ad.get("type") or "ListingPageBannerAd"
            # Map ad_type to canonical folder for Target
            if ad_type == "ListingPageBannerAd":
                folder = "ListingPageBannerAd"
            elif ad_type == "Sponsored_Logo":
                folder = "Sponsored_Logo"
            else:
                # Unknown type: keep it but place under Main
                folder = "Main"

            # Ensure subdirectory exists per Target taxonomy
            try:
                target_dir = ensure_subdir("target", output_root, folder)
            except Exception as e:
                log(f"[target] Failed to ensure folder {folder!r}: {e}")
                continue

            # Use brand as advertiser if present; otherwise explicit 'unknown'
            # so the second filename slot is always an advertiser token and
            # never the ad type itself.
            raw_brand = (ad.get("brand") or "").strip()
            advertiser = raw_brand or "unknown"

            filename = generate_ad_filename(
                retailer="target",
                ad_type=ad_type,
                client=client,
                search_term=keyword,
                timestamp=run_ts,
                index=idx,
                extension="png",
                advertiser=advertiser,
            )

            dest_path = target_dir / filename
            if dest_path.exists():
                # Already downloaded in a previous run of extract_images
                rel_path = dest_path.relative_to(output_root)
                ad["image_path"] = str(rel_path)
                if ad_type == "ListingPageBannerAd":
                    banner_count += 1
                elif ad_type == "Sponsored_Logo":
                    logo_count += 1
                continue

            log(f"[target] Downloading image for ad #{idx}: {img_url[:120]}...")
            try:
                ok = direct_download_image(str(img_url), str(dest_path), referer=referer)
            except Exception as e:
                log(f"[target] direct_download_image error for ad #{idx}: {e}")
                ok = False

            if not ok:
                log(f"[target] Failed to download image for ad #{idx}")
                continue

            rel_path = dest_path.relative_to(output_root)
            ad["image_path"] = str(rel_path)
            if ad_type == "ListingPageBannerAd":
                banner_count += 1
            elif ad_type == "Sponsored_Logo":
                logo_count += 1

        # Save updated JSON with image_path fields
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(run, f, indent=2, ensure_ascii=False)
            log(f"[target] Updated run JSON with image_path for {banner_count + logo_count} ads")
        except Exception as e:
            log(f"❌ Failed to write updated Target JSON: {e}")

        with open(log_path, "w", encoding="utf-8") as lf:
            lf.write("\n".join(log_lines))

        # Map Target types onto generic keys for GUI compatibility
        return {
            "toa": banner_count,
            "sky": logo_count,
            "car": 0,
            "log": log_path,
        }


# Register on import
register(TargetAdapter())
