#!/usr/bin/env python3
"""
Delete ENTIRE runs that contain any ads marked with brand="delete" from the brand review tool.

This script:
1. Scans all JSON run files for ANY ads with brand="delete"
2. If found, deletes the ENTIRE run including:
   - All images from that run
   - The run JSON file
   - The run directory (if empty)
3. Creates a backup before making changes

Rationale: If you can't have a complete picture of what ads were in a run, 
the entire run is deleted to maintain data integrity.

Usage:
    python3 tools/delete_marked_ads.py --dry-run  # Preview what will be deleted
    python3 tools/delete_marked_ads.py            # Actually delete
    python3 tools/delete_marked_ads.py --backup-dir /path/to/backup  # Custom backup location
"""

import json
import os
import shutil
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple

def find_all_run_jsons(output_dir: Path) -> List[Path]:
    """Find all run_results_*.json files."""
    json_files = []
    for root, dirs, files in os.walk(output_dir):
        for file in files:
            if file.startswith("run_results_") and file.endswith(".json"):
                json_files.append(Path(root) / file)
    return json_files

def has_delete_marked_ads(json_path: Path) -> Tuple[bool, List[Dict]]:
    """
    Check if run has ANY ads marked with brand="delete".
    Returns (has_delete_ads, all_ads)
    """
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        ads = data.get('ads', [])
        if not ads:
            # Try legacy structure
            results = data.get('results', [])
            if results and isinstance(results, list) and len(results) > 0:
                ads = results[0].get('ads', [])
        
        has_delete = False
        
        for ad in ads:
            brand = ad.get('brand')
            # Handle None brand
            if brand is not None:
                brand = brand.lower().strip()
                if brand == 'delete':
                    has_delete = True
                    break
            
            # Also check advertisers array
            advertisers = ad.get('advertisers', [])
            if advertisers:
                has_delete_advertiser = any(
                    adv and adv.lower().strip() == 'delete' for adv in advertisers if adv
                )
                if has_delete_advertiser:
                    has_delete = True
                    break
        
        return has_delete, ads
    
    except Exception as e:
        print(f"⚠️  Error reading {json_path}: {e}")
        return False, []

def get_image_path(ad: Dict, client_root: Path) -> Path | None:
    """Get the full path to the ad's image file."""
    # Try different possible image path fields
    image_rel_path = (
        ad.get('image_path') or 
        ad.get('screenshot') or 
        ad.get('screenshot_path')
    )
    
    if not image_rel_path:
        return None
    
    # Handle absolute vs relative paths
    if image_rel_path.startswith('/'):
        image_rel_path = image_rel_path.lstrip('/')
    
    image_full_path = client_root / image_rel_path
    
    if image_full_path.exists():
        return image_full_path
    
    # Try without leading path components (just filename)
    filename = Path(image_rel_path).name
    for root, dirs, files in os.walk(client_root):
        if filename in files:
            return Path(root) / filename
    
    return None

def backup_file(file_path: Path, backup_dir: Path) -> Path:
    """Create a backup of a file."""
    # Convert to absolute path if relative
    abs_path = file_path.resolve()
    cwd = Path.cwd()
    
    # Get relative path from current directory
    try:
        rel_path = abs_path.relative_to(cwd)
    except ValueError:
        # If file is outside cwd, use just the filename
        rel_path = abs_path.name
    
    backup_path = backup_dir / rel_path
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(abs_path, backup_path)
    return backup_path

def delete_marked_ads(
    output_dir: Path,
    dry_run: bool = True,
    backup_dir: Path | None = None,
    delete_empty_runs: bool = False
):
    """Main deletion logic - deletes ENTIRE runs that contain any 'delete' marked ads."""
    
    if backup_dir is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = Path(f"backups/delete_marked_ads_{timestamp}")
    
    if not dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)
        print(f"📦 Backup directory: {backup_dir}")
    
    json_files = find_all_run_jsons(output_dir)
    print(f"🔍 Found {len(json_files)} run JSON files\n")
    print("⚠️  MODE: Deleting ENTIRE runs that contain any 'delete' marked ads\n")
    
    total_ads_deleted = 0
    total_images_deleted = 0
    total_runs_deleted = 0
    
    for json_path in json_files:
        has_delete, all_ads = has_delete_marked_ads(json_path)
        
        if not has_delete:
            continue
        
        # Get client root directory
        client_root = json_path.parent.parent
        run_dir = json_path.parent
        
        print(f"\n📄 {json_path.relative_to(output_dir)}")
        print(f"   🗑️  ENTIRE RUN will be deleted ({len(all_ads)} total ads)")
        
        # Delete ALL images from this run
        images_deleted = 0
        for ad in all_ads:
            image_path = get_image_path(ad, client_root)
            if image_path and image_path.exists():
                if dry_run:
                    print(f"      Would delete: {image_path.name}")
                else:
                    backup_file(image_path, backup_dir)
                    image_path.unlink()
                images_deleted += 1
        
        if dry_run:
            print(f"      Would delete: {len(all_ads)} ads, {images_deleted} images")
            print(f"      Would delete JSON: {json_path.name}")
            # Check if entire run directory would be empty
            if run_dir.exists():
                remaining_files = [f for f in run_dir.iterdir() if f != json_path]
                if not remaining_files:
                    print(f"      Would delete empty run directory: {run_dir.name}")
        else:
            # Backup and delete JSON
            backup_file(json_path, backup_dir)
            json_path.unlink()
            print(f"   ✅ Deleted {images_deleted} images")
            print(f"   ✅ Deleted JSON: {json_path.name}")
            
            # Delete run directory if it's now empty
            if run_dir.exists():
                remaining_files = list(run_dir.iterdir())
                if not remaining_files:
                    run_dir.rmdir()
                    print(f"   ✅ Deleted empty run directory: {run_dir.name}")
        
        total_ads_deleted += len(all_ads)
        total_images_deleted += images_deleted
        total_runs_deleted += 1
    
    # Summary
    print("\n" + "="*60)
    print("📊 SUMMARY")
    print("="*60)
    print(f"{'DRY RUN - ' if dry_run else ''}Complete runs deleted: {total_runs_deleted}")
    print(f"{'DRY RUN - ' if dry_run else ''}Total ads deleted: {total_ads_deleted}")
    print(f"{'DRY RUN - ' if dry_run else ''}Total images deleted: {total_images_deleted}")
    
    if dry_run:
        print("\n⚠️  This was a DRY RUN. No files were actually deleted.")
        print("   Run without --dry-run to perform the deletion.")
    else:
        print(f"\n✅ Backup saved to: {backup_dir}")
        print("   You can restore from backup if needed.")

def main():
    parser = argparse.ArgumentParser(
        description="Delete ads marked with brand='delete' from brand review tool"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview what will be deleted without actually deleting'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path('output'),
        help='Output directory to scan (default: output/)'
    )
    parser.add_argument(
        '--backup-dir',
        type=Path,
        help='Custom backup directory (default: backups/delete_marked_ads_TIMESTAMP/)'
    )
    parser.add_argument(
        '--delete-empty-runs',
        action='store_true',
        help='Delete run JSON files that become empty after deletion'
    )
    
    args = parser.parse_args()
    
    if not args.output_dir.exists():
        print(f"❌ Output directory not found: {args.output_dir}")
        return 1
    
    delete_marked_ads(
        output_dir=args.output_dir,
        dry_run=args.dry_run,
        backup_dir=args.backup_dir,
        delete_empty_runs=args.delete_empty_runs
    )
    
    return 0

if __name__ == '__main__':
    exit(main())
