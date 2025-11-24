#!/usr/bin/env python3
"""Rebuild missing Kroger ad images from archived HTML + JSON.

This script:
- Walks output/kroger/<client>/runs
- For each run_results_*.json, finds the matching search_results_*.html
- If the JSON has ads with image_url but missing image_path, it calls
  extractors/screenshot_ad_images.py to capture images and update JSON.

It does NOT re-run any live Kroger searches; it only uses existing
run_results_*.json + search_results_*.html artifacts.
"""

import json
import os
import sys
import subprocess
from pathlib import Path
from typing import Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def json_has_missing_images(data: Dict[str, Any]) -> bool:
    """Return True if any ad has image_url but no image_path."""

    def ad_missing(ad: Dict[str, Any]) -> bool:
        if not isinstance(ad, dict):
            return False
        if not ad.get("image_url"):
            return False
        if ad.get("image_path"):
            return False
        return True

    # Aggregated shape
    for result in data.get("results", []) or []:
        for ad in result.get("ads", []) or []:
            if ad_missing(ad):
                return True

    # Per-run shape
    top_ads = data.get("ads")
    if isinstance(top_ads, list):
        for ad in top_ads:
            if ad_missing(ad):
                return True

    return False


def main() -> None:
    output_root = PROJECT_ROOT / "output" / "kroger"
    if not output_root.is_dir():
        print(f"No Kroger output directory at {output_root}")
        return

    # Choose extractor script the same way KrogerAdapter does:
    # prefer screenshot_ad_images.py if present, else fall back to
    # screenshot_toa_image.py (which is a shim into screenshot_ad_image.py).
    ad_script = PROJECT_ROOT / "extractors" / "screenshot_ad_images.py"
    toa_script = PROJECT_ROOT / "extractors" / "screenshot_toa_image.py"
    if ad_script.is_file():
        screenshot_script = ad_script
    elif toa_script.is_file():
        screenshot_script = toa_script
    else:
        print("No suitable screenshot extractor found (expected screenshot_ad_images.py or screenshot_toa_image.py)")
        return

    total_runs = 0
    total_invoked = 0

    for client_dir in sorted(p for p in output_root.iterdir() if p.is_dir()):
        client_slug = client_dir.name
        runs_dir = client_dir / "runs"
        if not runs_dir.is_dir():
            continue

        print(f"\n=== Replaying screenshots for client: {client_slug} ===")
        client_runs = 0
        client_invoked = 0

        for json_path in sorted(runs_dir.glob("run_results_*.json")):
            total_runs += 1
            client_runs += 1

            # Determine matching HTML file
            html_name = json_path.name.replace("run_results_", "search_results_").replace(".json", ".html")
            html_path = runs_dir / html_name
            if not html_path.is_file():
                # No archived HTML for this run
                continue

            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"  {json_path.name}: failed to read JSON: {e}")
                continue

            if not json_has_missing_images(data):
                continue

            # Invoke screenshot_ad_images.py on this pair
            cmd = [
                sys.executable,
                str(screenshot_script),
                "--json",
                str(json_path),
                "--html",
                str(html_path),
                "--output",
                str(client_dir),
                "--client",
                client_slug,
                "--no-lock",
                "--time-window",
                "1440",
                "--browser-lock-timeout",
                "600",
            ]

            print(f"  {json_path.name}: missing images detected, running screenshot_ad_images.py")
            try:
                subprocess.run(
                    cmd,
                    cwd=str(PROJECT_ROOT),
                    check=False,
                )
            except Exception as e:
                print(f"    ❌ subprocess failed: {e}")
                continue

            total_invoked += 1
            client_invoked += 1

        print(f"  Runs checked for {client_slug}: {client_runs}, screenshot tool invoked: {client_invoked}")

    print(f"\nOverall runs checked: {total_runs}, screenshot tool invoked: {total_invoked}")


if __name__ == "__main__":
    main()
