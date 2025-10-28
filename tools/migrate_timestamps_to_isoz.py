#!/usr/bin/env python3
"""
Migrate legacy timestamps in JSON files to ISO 8601 Z format.

This script walks through all run_results_*.json files and normalizes
timestamps to the canonical format: 2025-10-27T02:56:54Z

Usage:
    python3 tools/migrate_timestamps_to_isoz.py [--retailer RETAILER] [--dry-run]

Options:
    --retailer RETAILER  Only process this retailer (default: all)
    --dry-run           Show what would be changed without modifying files
"""

import json
import re
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone

def to_iso_z(ts, run_id=None):
    """Normalize timestamp to ISO 8601 Z format"""
    ts = (ts or "").strip()
    try:
        # Already ISO with Z
        if re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$', ts):
            return ts
        # Space-separated UTC
        m1 = re.match(r'^(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2}):(\d{2})$', ts)
        if m1:
            dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            return dt.isoformat(timespec="seconds").replace("+00:00", "Z")
        # Underscore-separated UTC
        m2 = re.match(r'^(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})$', ts)
        if m2:
            dt = datetime.strptime(ts, "%Y-%m-%d_%H-%M-%S").replace(tzinfo=timezone.utc)
            return dt.isoformat(timespec="seconds").replace("+00:00", "Z")
    except Exception:
        pass
    # Fallback from run_id
    if run_id:
        try:
            dt = datetime.strptime(run_id, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            return dt.isoformat(timespec="seconds").replace("+00:00", "Z")
        except Exception:
            pass
    # Leave as-is if can't parse
    return ts


def migrate_file(json_path: Path, dry_run: bool = False) -> tuple[bool, str]:
    """
    Migrate a single JSON file.
    Returns (changed, message)
    """
    try:
        data = json.loads(json_path.read_text())
        changed = False
        
        # Extract run_id from filename
        run_id = None
        m = re.search(r'run_results_(\d{14})', json_path.name)
        if m:
            run_id = m.group(1)
        
        # Normalize top-level timestamp
        if "timestamp" in data:
            old_ts = data["timestamp"]
            new_ts = to_iso_z(old_ts, run_id)
            if old_ts != new_ts:
                data["timestamp"] = new_ts
                changed = True
        
        # Normalize ad timestamps (canonical schema)
        if isinstance(data.get("ads"), list):
            for ad in data["ads"]:
                if "timestamp" in ad:
                    old_ts = ad["timestamp"]
                    new_ts = to_iso_z(old_ts, run_id)
                    if old_ts != new_ts:
                        ad["timestamp"] = new_ts
                        changed = True
        
        # Normalize ad timestamps (legacy results[] schema)
        if isinstance(data.get("results"), list):
            for result in data["results"]:
                if isinstance(result.get("ads"), list):
                    for ad in result["ads"]:
                        if "timestamp" in ad:
                            old_ts = ad["timestamp"]
                            new_ts = to_iso_z(old_ts, run_id)
                            if old_ts != new_ts:
                                ad["timestamp"] = new_ts
                                changed = True
        
        if changed and not dry_run:
            json_path.write_text(json.dumps(data, indent=2))
            return True, "✅ Migrated"
        elif changed and dry_run:
            return True, "🔍 Would migrate"
        else:
            return False, "⏭️  Already normalized"
    
    except Exception as e:
        return False, f"❌ Error: {e}"


def main():
    parser = argparse.ArgumentParser(description="Migrate timestamps to ISO 8601 Z format")
    parser.add_argument("--retailer", help="Only process this retailer")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without modifying files")
    args = parser.parse_args()
    
    # Find output directory
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    output_root = project_root / "output"
    
    if not output_root.exists():
        print(f"❌ Output directory not found: {output_root}")
        sys.exit(1)
    
    # Determine which retailers to process
    if args.retailer:
        retailers = [args.retailer]
    else:
        retailers = [d.name for d in output_root.iterdir() if d.is_dir()]
    
    print("=" * 60)
    print("Timestamp Migration to ISO 8601 Z")
    print("=" * 60)
    if args.dry_run:
        print("🔍 DRY RUN MODE - No files will be modified")
    print(f"Retailers: {', '.join(retailers)}")
    print("")
    
    total_files = 0
    migrated_files = 0
    
    for retailer in retailers:
        retailer_dir = output_root / retailer
        if not retailer_dir.exists():
            continue
        
        print(f"\n📁 Processing {retailer}...")
        
        # Find all run_results_*.json files
        json_files = list(retailer_dir.rglob("run_results_*.json"))
        
        for json_path in json_files:
            total_files += 1
            changed, message = migrate_file(json_path, args.dry_run)
            
            if changed:
                migrated_files += 1
                rel_path = json_path.relative_to(output_root)
                print(f"  {message}: {rel_path}")
    
    # Summary
    print("")
    print("=" * 60)
    print("Migration Summary")
    print("=" * 60)
    print(f"Total files processed: {total_files}")
    print(f"Files {'that would be ' if args.dry_run else ''}migrated: {migrated_files}")
    print(f"Files already normalized: {total_files - migrated_files}")
    
    if args.dry_run and migrated_files > 0:
        print("")
        print("Run without --dry-run to apply changes:")
        print(f"  python3 tools/migrate_timestamps_to_isoz.py{' --retailer ' + args.retailer if args.retailer else ''}")
    elif migrated_files > 0:
        print("")
        print("✅ Migration complete! All timestamps normalized to ISO 8601 Z format.")
    else:
        print("")
        print("✅ All timestamps already normalized!")


if __name__ == "__main__":
    main()
