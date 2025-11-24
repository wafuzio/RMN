#!/usr/bin/env python3
"""Front-to-back debug harness for Target pipeline.

This script is designed to debug the *entire* Target flow for a single client
and keyword:

1. Optionally runs the Target adapter's search_and_capture (Playwright) to
   produce a new HTML + run JSON.
2. Locates the latest run_results_*.json + search_results_*.html pair.
3. Re-runs the same HTML extraction logic used in target_search_and_capture
   (_extract_ads_from_html) and prints:
   - Internal log messages from that extractor
   - Counts of ads by type (ListingPageBannerAd, Sponsored_Logo, etc.)
4. Compares those HTML-extracted ads to the JSON's ads[] length.
5. Invokes TargetAdapter.extract_images to download images and update
   ads[].image_path, then prints per-type image counts and log path.

Usage examples:

  # Full capture + debug for adapter_test with default keyword "milk"
  python scripts/debug_target_pipeline.py --client adapter_test

  # Analyze an existing run for client test10 without re-running capture
  python scripts/debug_target_pipeline.py --client test10 \
      --keyword "acne skin care" --skip-capture
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Optional, Tuple

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.run_context import RunContext
from core.retailers import get as get_retailer_adapter

# Ensure Target adapter is registered
import retailers.target.adapter  # noqa: F401
from retailers.target.adapter import TargetAdapter
from target_search_and_capture import _extract_ads_from_html


def find_latest_run_pair(output_dir: str) -> Optional[Tuple[str, str]]:
    """Find the most recent (run_results, search_results) pair under output_dir/runs."""
    runs_dir = os.path.join(output_dir, "runs")
    json_paths = sorted(
        glob.glob(os.path.join(runs_dir, "run_results_*.json")),
        key=os.path.getmtime,
    )
    if not json_paths:
        return None

    latest_json = json_paths[-1]
    html_candidate = latest_json.replace("run_results_", "search_results_").replace(
        ".json", ".html"
    )
    if not os.path.exists(html_candidate):
        return None
    return latest_json, html_candidate


def audit_html_extraction(html_path: str, run_id: str, keyword: str) -> list[dict]:
    """Run _extract_ads_from_html against a saved HTML file and print debug info."""
    html = Path(html_path).read_text(encoding="utf-8")
    log_lines: list[str] = []

    def log(msg: str) -> None:
        print(msg)
        log_lines.append(msg)

    print("\n=== HTML Extraction Audit ===")
    print(f"HTML file: {html_path}")
    ads = _extract_ads_from_html(html, run_id=run_id, keyword=keyword, log=log)

    counts = Counter(ad.get("type", "<unknown>") for ad in ads)
    print("\nHTML extractor produced:")
    print(f"  Total ads: {len(ads)}")
    for t, c in sorted(counts.items()):
        print(f"  {t}: {c}")

    if not ads:
        print("  (No ads extracted from HTML; see log lines above for clues.)")

    return ads


def main() -> int:
    parser = argparse.ArgumentParser(description="Debug Target SRP pipeline front-to-back")
    parser.add_argument("--client", required=True, help="Client name (folder under output/target)")
    parser.add_argument("--keyword", help="Keyword to search; default 'milk' if running capture")
    parser.add_argument(
        "--output-dir",
        help="Explicit output dir; defaults to output/target/<client>",
    )
    parser.add_argument(
        "--skip-capture",
        action="store_true",
        help="Skip running Playwright capture; just analyze latest existing run",
    )

    args = parser.parse_args()

    retailer_slug = "target"
    client = args.client
    keyword = args.keyword or "milk"

    base_dir = str(PROJECT_ROOT)
    output_dir = args.output_dir or str(PROJECT_ROOT / "output" / retailer_slug / client)
    runs_dir = os.path.join(output_dir, "runs")
    logs_dir = str(PROJECT_ROOT / "logs" / retailer_slug)

    # Resolve Target profile directory
    profile_dir = os.environ.get("TARGET_PROFILE_DIR")
    if not profile_dir:
        fallback = PROJECT_ROOT / "profiles" / "target"
        if fallback.is_dir():
            profile_dir = str(fallback)
        else:
            print("❌ TARGET_PROFILE_DIR not set and profiles/target does not exist.")
            print("   Run scripts/setup_target_profile.sh first.")
            return 1

    if not os.path.isdir(profile_dir):
        print(f"❌ Target profile dir is invalid: {profile_dir}")
        return 1

    ctx = RunContext(
        retailer=retailer_slug,
        client=client,
        base_dir=base_dir,
        output_dir=output_dir,
        runs_dir=runs_dir,
        logs_dir=logs_dir,
        profile_dir=profile_dir,
        script_dir=base_dir,
    )

    os.makedirs(ctx.output_dir, exist_ok=True)

    print("=" * 60)
    print("Target Pipeline Debug")
    print("=" * 60)
    print(f"Client:   {client}")
    print(f"Keyword:  {keyword}")
    print(f"Output:   {output_dir}")
    print(f"Profile:  {profile_dir}")

    # 1) Optional capture via adapter
    if not args.skip_capture:
        adapter = get_retailer_adapter(retailer_slug)
        print("\n--- Step 1: search_and_capture via adapter ---")
        print(f"Adapter:  {adapter.display_name} ({adapter.slug})")
        ok = adapter.search_and_capture(keyword, ctx)
        if not ok:
            print("❌ search_and_capture failed; aborting debug run")
            return 1
        print("✅ search_and_capture completed")

    # 2) Locate latest run pair
    print("\n--- Step 2: locate latest run JSON/HTML pair ---")
    pair = find_latest_run_pair(output_dir)
    if not pair:
        print(f"❌ No run_results_*.json + search_results_*.html under {runs_dir}")
        return 1

    json_path, html_path = pair
    print(f"JSON: {json_path}")
    print(f"HTML: {html_path}")

    # 3) Inspect run JSON
    print("\n--- Step 3: inspect run JSON ---")
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            run = json.load(f)
    except Exception as e:
        print(f"❌ Failed to read run JSON: {e}")
        return 1

    ads = run.get("ads") or []
    print(f"retailer: {run.get('retailer')}\nclient:   {run.get('client')}\nkeyword:  {run.get('keyword')}\nrun_id:   {run.get('run_id')}\nads[]:    {len(ads)}")

    # 4) Audit HTML extraction using the same function as the scraper
    html_ads = audit_html_extraction(
        html_path,
        run_id=run.get("run_id") or "debug",
        keyword=run.get("keyword") or keyword,
    )

    print("\n--- Step 4: compare JSON ads[] vs HTML extractor ---")
    print(f"ads[] in JSON:        {len(ads)}")
    print(f"ads from HTML audit:  {len(html_ads)}")

    # 5) Run image extraction via TargetAdapter
    print("\n--- Step 5: image extraction via TargetAdapter ---")
    t_adapter = TargetAdapter()
    summary = t_adapter.extract_images(json_path, html_path, ctx)

    print("\nImage extract summary (Target):")
    print(f"ListingPageBannerAd (toa): {summary.get('toa', 0)}")
    print(f"Sponsored_Logo (sky):     {summary.get('sky', 0)}")
    print(f"Carousels (car):          {summary.get('car', 0)}")
    print(f"Log:                       {summary.get('log', '<none>')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
