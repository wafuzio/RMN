#!/usr/bin/env python3
"""Test the Target adapter end-to-end.

This script mirrors the pattern in ADDING_NEW_RETAILER.md for other retailers.
It:
- Builds a RunContext for retailer='target'
- Uses TARGET_PROFILE_DIR (or profiles/target) for the Playwright profile
- Invokes the TargetAdapter via the registry
- Prints where HTML/JSON were written and basic stats
"""

import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(project_root))

from core.run_context import RunContext
from core.retailers import get as get_retailer_adapter

# Ensure adapter is registered
import retailers.target.adapter  # noqa: F401


def main() -> int:
    profile_dir = os.environ.get("TARGET_PROFILE_DIR")
    if not profile_dir:
        # Fallback to project-local profiles/target
        fallback = project_root / "profiles" / "target"
        if fallback.is_dir():
            profile_dir = str(fallback)
        else:
            print("❌ TARGET_PROFILE_DIR not set and profiles/target does not exist.")
            print("   Run scripts/setup_target_profile.sh first.")
            return 1

    if not os.path.isdir(profile_dir):
        print(f"❌ Target profile dir is invalid: {profile_dir}")
        return 1

    print("=" * 60)
    print("Target Adapter Test")
    print("=" * 60)
    print(f"Profile: {profile_dir}")
    print()

    test_client = "adapter_test"
    retailer_slug = "target"

    base_dir = str(project_root)
    output_dir = str(project_root / "output" / retailer_slug / test_client)
    runs_dir = str(project_root / "output" / retailer_slug / test_client / "runs")
    logs_dir = str(project_root / "logs" / retailer_slug)

    ctx = RunContext(
        retailer=retailer_slug,
        client=test_client,
        base_dir=base_dir,
        output_dir=output_dir,
        runs_dir=runs_dir,
        logs_dir=logs_dir,
        profile_dir=profile_dir,
        script_dir=base_dir,
    )

    os.makedirs(ctx.output_dir, exist_ok=True)

    adapter = get_retailer_adapter(retailer_slug)

    print(f"Testing adapter: {adapter.display_name} ({adapter.slug})")
    print(f"Output directory: {ctx.output_dir}")
    print()

    keyword = "milk"
    print(f"Running search_and_capture for keyword: '{keyword}'")
    print("-" * 60)

    success = adapter.search_and_capture(keyword, ctx)

    print("-" * 60)
    if not success:
        print("❌ search_and_capture failed")
        return 1

    print("✅ search_and_capture completed successfully")

    # Inspect outputs
    runs_path = Path(ctx.output_dir) / "runs"
    if runs_path.exists():
        html_files = sorted(runs_path.glob("search_results_*.html"))
        json_files = sorted(runs_path.glob("run_results_*.json"))

        print(f"\nOutput files:")
        print(f"  HTML files: {len(html_files)}")
        print(f"  JSON files: {len(json_files)}")

        if json_files:
            latest_json = json_files[-1]
            import json

            with latest_json.open("r", encoding="utf-8") as f:
                data = json.load(f)
            ads = data.get("ads", [])
            print(f"\nCanonical run JSON: {latest_json}")
            print(f"  retailer:   {data.get('retailer')}\n  client:     {data.get('client')}\n  keyword:    {data.get('keyword')}\n  timestamp:  {data.get('timestamp')}\n  run_id:     {data.get('run_id')}\n  ads count:  {len(ads)}")

    return 0


if __name__ == "__main__":  # pragma: no cover (manual script)
    raise SystemExit(main())
