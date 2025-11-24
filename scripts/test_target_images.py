#!/usr/bin/env python3
"""Test Target image extraction pipeline.

This helper script:
- Locates the latest Target run JSON/HTML pair under a given output dir
  (e.g. output/target/adapter_test).
- Builds a RunContext for Target.
- Invokes TargetAdapter.extract_images to download ad images based on
  image_url fields and update the run JSON with image_path.
- Prints a summary of ListingPageBannerAd/Sponsored_Logo image counts
  plus the log path.
"""

from __future__ import annotations

import argparse
import glob
import os
from pathlib import Path
from typing import Tuple, Optional

import sys

# Ensure project root is on sys.path so core/ and retailers/ can be imported
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.run_context import RunContext
from retailers.target.adapter import TargetAdapter


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
    html_candidate = latest_json.replace("run_results_", "search_results_").replace(".json", ".html")
    if not os.path.exists(html_candidate):
        return None
    return latest_json, html_candidate


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Target image extraction for latest run")
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Target output dir, e.g. output/target/adapter_test",
    )
    parser.add_argument(
        "--client",
        help="Client name; defaults to last component of output-dir",
    )

    args = parser.parse_args()
    output_dir = os.path.abspath(args.output_dir)

    pair = find_latest_run_pair(output_dir)
    if not pair:
        print(f"❌ No run_results_*.json + search_results_*.html pair found under {output_dir}/runs")
        return 1

    json_path, html_path = pair
    print(f"📄 JSON: {json_path}")
    print(f"🌐 HTML: {html_path}")

    # Derive client from arg or output_dir (output/target/<client>)
    client = args.client
    if not client:
        parts = os.path.normpath(output_dir).split(os.sep)
        client = parts[-1] if parts else "adapter_test"

    # Build RunContext for Target
    base_dir = str(Path(__file__).resolve().parent.parent)
    logs_dir = os.path.join(base_dir, "logs", "target")
    ctx = RunContext(
        retailer="target",
        client=client,
        base_dir=base_dir,
        output_dir=output_dir,
        runs_dir=os.path.join(output_dir, "runs"),
        logs_dir=logs_dir,
        profile_dir=None,
        script_dir=os.path.dirname(__file__),
    )

    adapter = TargetAdapter()
    summary = adapter.extract_images(json_path, html_path, ctx)

    print("\n=== Target Image Extract Summary ===")
    print(f"ListingPageBannerAd (toa): {summary.get('toa', 0)}")
    print(f"Sponsored_Logo (sky):     {summary.get('sky', 0)}")
    print(f"Carousels (car):           {summary.get('car', 0)}")
    print(f"Log:                        {summary.get('log', '<none>')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
