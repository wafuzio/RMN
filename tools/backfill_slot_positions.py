#!/usr/bin/env python3
"""
Backfill slot position fields on all existing run JSON files.

For every ad in every run JSON, assigns:
  - slot              (int) : 0-based global page position (array index)
  - slot_within_type  (int) : 0-based position within ads of the same type
  - total_slots       (int) : total number of ads on the page
  - total_slots_of_type (int) : total number of ads of this type on the page

Ads are already stored in page order (top-to-bottom DOM extraction), so
array index == global page position.

Handles both canonical (flat ads[]) and legacy (results[].ads[]) formats.

Usage:
    python3 tools/backfill_slot_positions.py [--dry-run] [--retailer kroger]
"""

import argparse
import glob
import json
import os
import sys
from collections import Counter


def collect_ads(data):
    """
    Return a flat list of (ad_dict, container_list, container_index) tuples
    in page order. Works for both canonical and legacy JSON formats.

    container_list is the Python list the ad lives in (so we can mutate it),
    container_index is the ad's index within that list.
    """
    ads = []

    # Canonical format: top-level ads[]
    top_ads = data.get("ads")
    if isinstance(top_ads, list):
        for i, ad in enumerate(top_ads):
            if isinstance(ad, dict):
                ads.append((ad, top_ads, i))

    # Legacy format: results[].ads[]
    results = data.get("results")
    if isinstance(results, list):
        for result in results:
            nested_ads = result.get("ads")
            if isinstance(nested_ads, list):
                for i, ad in enumerate(nested_ads):
                    if isinstance(ad, dict):
                        ads.append((ad, nested_ads, i))

    return ads


def assign_slots(ads_tuples):
    """
    Given a list of (ad_dict, container, idx) in page order, assign
    slot, slot_within_type, total_slots, total_slots_of_type to each ad.

    Returns the number of ads that were modified.
    """
    if not ads_tuples:
        return 0

    total_slots = len(ads_tuples)

    # Count totals per type
    type_counts = Counter()
    for ad, _, _ in ads_tuples:
        ad_type = ad.get("type") or ad.get("ad_type") or "Unknown"
        type_counts[ad_type] += 1

    # Track running index per type
    type_running = Counter()
    modified = 0

    for global_idx, (ad, container, container_idx) in enumerate(ads_tuples):
        ad_type = ad.get("type") or ad.get("ad_type") or "Unknown"
        within_type_idx = type_running[ad_type]
        type_running[ad_type] += 1

        # Check if anything actually changes
        old = (
            ad.get("slot"),
            ad.get("slot_within_type"),
            ad.get("total_slots"),
            ad.get("total_slots_of_type"),
        )
        new = (global_idx, within_type_idx, total_slots, type_counts[ad_type])

        if old != new:
            ad["slot"] = global_idx
            ad["slot_within_type"] = within_type_idx
            ad["total_slots"] = total_slots
            ad["total_slots_of_type"] = type_counts[ad_type]
            modified += 1

    return modified


def process_file(filepath, dry_run=False):
    """
    Process a single JSON file. Returns (num_ads, num_modified, error_str|None).
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return 0, 0, str(e)

    if not isinstance(data, dict):
        return 0, 0, None

    ads_tuples = collect_ads(data)
    if not ads_tuples:
        return 0, 0, None

    modified = assign_slots(ads_tuples)

    if modified > 0 and not dry_run:
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write("\n")
        except Exception as e:
            return len(ads_tuples), 0, f"write error: {e}"

    return len(ads_tuples), modified, None


def main():
    parser = argparse.ArgumentParser(description="Backfill slot position fields on run JSONs")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing files")
    parser.add_argument("--retailer", type=str, default=None, help="Only process one retailer (e.g. kroger)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print every file processed")
    args = parser.parse_args()

    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
    if not os.path.isdir(base):
        print(f"ERROR: output directory not found: {base}")
        sys.exit(1)

    retailers = [args.retailer] if args.retailer else sorted(
        d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))
    )

    total_files = 0
    total_ads = 0
    total_modified = 0
    total_errors = 0
    files_changed = 0

    for retailer in retailers:
        retailer_dir = os.path.join(base, retailer)
        if not os.path.isdir(retailer_dir):
            print(f"  SKIP {retailer}: not a directory")
            continue

        # Find all JSON files under runs/ directories
        pattern = os.path.join(retailer_dir, "**", "runs", "**", "*.json")
        json_files = sorted(glob.glob(pattern, recursive=True))

        # Also check for runs/*.json (non-nested)
        pattern2 = os.path.join(retailer_dir, "**", "runs", "*.json")
        json_files2 = sorted(glob.glob(pattern2, recursive=True))

        all_files = sorted(set(json_files + json_files2))

        r_ads = 0
        r_modified = 0
        r_errors = 0
        r_files_changed = 0

        for filepath in all_files:
            num_ads, num_modified, error = process_file(filepath, dry_run=args.dry_run)
            total_files += 1
            r_ads += num_ads
            total_ads += num_ads

            if error:
                r_errors += 1
                total_errors += 1
                if args.verbose:
                    print(f"  ERROR {filepath}: {error}")
            elif num_modified > 0:
                r_modified += num_modified
                total_modified += num_modified
                r_files_changed += 1
                files_changed += 1
                if args.verbose:
                    print(f"  {filepath}: {num_ads} ads, {num_modified} modified")

        print(f"  {retailer}: {len(all_files)} files, {r_ads} ads, {r_modified} modified in {r_files_changed} files, {r_errors} errors")

    mode = "DRY RUN" if args.dry_run else "DONE"
    print(f"\n{mode}: {total_files} files scanned, {total_ads} ads, {total_modified} modified in {files_changed} files, {total_errors} errors")


if __name__ == "__main__":
    main()
