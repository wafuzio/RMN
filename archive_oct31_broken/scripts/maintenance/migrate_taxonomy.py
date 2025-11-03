#!/usr/bin/env python3
"""
Taxonomy Migration Script

Safely migrates existing ad data to comply with artifact taxonomy:
- Moves Walmart images from runs/ to ad-type folders
- Adds image_path fields to Instacart JSON
- Fixes Kroger path references

Usage:
    python3 scripts/maintenance/migrate_taxonomy.py --retailer walmart --client land_o_frost --dry-run
    python3 scripts/maintenance/migrate_taxonomy.py --retailer walmart --client land_o_frost --execute
    python3 scripts/maintenance/migrate_taxonomy.py --retailer all --execute
"""

import os
import sys
import json
import shutil
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple

# Add project root to path
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.path_taxonomy import allowed_subdirs

# Colors for output
class Colors:
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    RED = '\033[0;31m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color

def log_info(msg: str):
    print(f"{Colors.BLUE}ℹ{Colors.NC} {msg}")

def log_success(msg: str):
    print(f"{Colors.GREEN}✓{Colors.NC} {msg}")

def log_warning(msg: str):
    print(f"{Colors.YELLOW}⚠{Colors.NC} {msg}")

def log_error(msg: str):
    print(f"{Colors.RED}✗{Colors.NC} {msg}")

# ============================================================================
# Walmart Migration
# ============================================================================

def migrate_walmart_client(client_dir: Path, dry_run: bool = True) -> Dict:
    """
    Migrate Walmart client data:
    - Move images from runs/<timestamp>/ to ad-type folders
    - Update JSON with new paths
    """
    stats = {
        'files_moved': 0,
        'json_updated': 0,
        'errors': 0,
        'skipped': 0
    }
    
    runs_dir = client_dir / "runs"
    if not runs_dir.exists():
        log_warning(f"No runs directory found in {client_dir}")
        return stats
    
    # Find all run subdirectories
    run_dirs = [d for d in runs_dir.iterdir() if d.is_dir()]
    log_info(f"Found {len(run_dirs)} run directories")
    
    for run_dir in run_dirs:
        log_info(f"Processing {run_dir.name}...")
        
        # Find JSON file
        json_files = list(run_dir.glob("run_results_*.json"))
        if not json_files:
            log_warning(f"No run_results JSON found in {run_dir.name}")
            stats['skipped'] += 1
            continue
        
        json_file = json_files[0]
        
        # Load JSON
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
        except Exception as e:
            log_error(f"Failed to load {json_file.name}: {e}")
            stats['errors'] += 1
            continue
        
        # Find images in this run directory
        image_files = []
        for ext in ['*.png', '*.jpg', '*.jpeg', '*.mp4']:
            image_files.extend(run_dir.glob(ext))
        
        # Skip metadata files
        image_files = [f for f in image_files if not any(x in f.name for x in ['meta.json', 'steps.jsonl', 'trace.zip'])]
        
        if not image_files:
            log_info(f"No images to migrate in {run_dir.name}")
            continue
        
        log_info(f"Found {len(image_files)} images to migrate")
        
        # Determine ad type from filename and move
        moved_files = []
        for img_file in image_files:
            # Parse filename to determine ad type
            filename = img_file.name.lower()
            
            if '_sba_' in filename:
                target_folder = 'SBA'
            elif '_sbv_' in filename:
                target_folder = 'SBV'
            elif '_tile_takeover_' in filename or '_tiletakeover_' in filename:
                target_folder = 'Tile_Takeover'
            elif '_top_banner_' in filename or '_topbanner_' in filename:
                target_folder = 'Top_Banner'
            elif 'search_results' in filename or 'fullpage' in filename:
                target_folder = 'Main'
            else:
                log_warning(f"Unknown ad type for {img_file.name}, skipping")
                stats['skipped'] += 1
                continue
            
            # Create target directory
            target_dir = client_dir / target_folder
            if not dry_run:
                target_dir.mkdir(exist_ok=True)
            
            target_path = target_dir / img_file.name
            
            # Move file
            if dry_run:
                log_info(f"  [DRY RUN] Would move: {img_file.name} → {target_folder}/")
            else:
                try:
                    shutil.move(str(img_file), str(target_path))
                    log_success(f"  Moved: {img_file.name} → {target_folder}/")
                    moved_files.append((img_file.name, f"{target_folder}/{img_file.name}"))
                    stats['files_moved'] += 1
                except Exception as e:
                    log_error(f"  Failed to move {img_file.name}: {e}")
                    stats['errors'] += 1
        
        # Update JSON with new paths
        if moved_files and not dry_run:
            # Add image_paths field to JSON
            if 'image_paths' not in data:
                data['image_paths'] = {}
            
            for old_name, new_path in moved_files:
                data['image_paths'][old_name] = new_path
            
            # Save updated JSON
            try:
                with open(json_file, 'w') as f:
                    json.dump(data, f, indent=2)
                log_success(f"  Updated {json_file.name} with new paths")
                stats['json_updated'] += 1
            except Exception as e:
                log_error(f"  Failed to update {json_file.name}: {e}")
                stats['errors'] += 1
    
    return stats

# ============================================================================
# Instacart Migration
# ============================================================================

def migrate_instacart_client(client_dir: Path, dry_run: bool = True) -> Dict:
    """
    Migrate Instacart client data:
    - Add image_path fields to JSON by matching saved images
    """
    stats = {
        'json_updated': 0,
        'images_linked': 0,
        'errors': 0,
        'skipped': 0
    }
    
    runs_dir = client_dir / "runs"
    if not runs_dir.exists():
        log_warning(f"No runs directory found in {client_dir}")
        return stats
    
    # Find all JSON files
    json_files = list(runs_dir.glob("run_results_*.json"))
    log_info(f"Found {len(json_files)} JSON files")
    
    for json_file in json_files:
        log_info(f"Processing {json_file.name}...")
        
        # Load JSON
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
        except Exception as e:
            log_error(f"Failed to load {json_file.name}: {e}")
            stats['errors'] += 1
            continue
        
        # Extract timestamp from filename or JSON
        timestamp = data.get('timestamp', '')
        if not timestamp:
            # Try to extract from filename: run_results_20251010_150339.json
            parts = json_file.stem.split('_')
            if len(parts) >= 3:
                timestamp = f"{parts[-2]}_{parts[-1]}"
        
        if not timestamp:
            log_warning(f"No timestamp found for {json_file.name}, skipping")
            stats['skipped'] += 1
            continue
        
        # Get keyword
        keyword = data.get('keyword', data.get('search_term', ''))
        if not keyword:
            log_warning(f"No keyword found for {json_file.name}, skipping")
            stats['skipped'] += 1
            continue
        
        # Process ads
        ads = data.get('ads', [])
        if not ads:
            log_info(f"No ads in {json_file.name}")
            continue
        
        updated = False
        for idx, ad in enumerate(ads):
            ad_type = ad.get('type', '')
            if not ad_type:
                continue
            
            # Determine folder based on ad type
            if 'Shoppable Display' in ad_type:
                folder = 'Shoppable_Display_Ads'
                prefix = 'ShoppableDisplayAd'
            elif 'Shoppable Video' in ad_type:
                folder = 'Shoppable_Video_Ads'
                prefix = 'ShoppableVideoAd'
            elif 'Display' in ad_type:
                folder = 'Display_Ads'
                prefix = 'DisplayAd'
            else:
                continue
            
            # Look for matching image
            ad_folder = client_dir / folder
            if not ad_folder.exists():
                continue
            
            # Try to find image by pattern
            pattern = f"{prefix}_{keyword.replace(' ', '_')}_{timestamp}_*.png"
            matching_images = list(ad_folder.glob(pattern))
            
            if not matching_images:
                # Try without keyword
                pattern = f"{prefix}_*_{timestamp}_*.png"
                matching_images = list(ad_folder.glob(pattern))
            
            if matching_images:
                # Use the first match (or match by index if multiple)
                if len(matching_images) > idx:
                    img_file = matching_images[idx]
                else:
                    img_file = matching_images[0]
                
                relative_path = f"{folder}/{img_file.name}"
                
                if 'image_path' not in ad or not ad['image_path']:
                    if dry_run:
                        log_info(f"  [DRY RUN] Would add image_path: {relative_path}")
                    else:
                        ad['image_path'] = relative_path
                        updated = True
                        stats['images_linked'] += 1
                        log_success(f"  Linked: {ad_type} → {img_file.name}")
        
        # Save updated JSON
        if updated and not dry_run:
            try:
                with open(json_file, 'w') as f:
                    json.dump(data, f, indent=2)
                log_success(f"  Updated {json_file.name}")
                stats['json_updated'] += 1
            except Exception as e:
                log_error(f"  Failed to update {json_file.name}: {e}")
                stats['errors'] += 1
    
    return stats

# ============================================================================
# Kroger Migration
# ============================================================================

def migrate_kroger_client(client_dir: Path, dry_run: bool = True) -> Dict:
    """
    Migrate Kroger client data:
    - Fix incorrect image paths in JSON
    """
    stats = {
        'json_updated': 0,
        'paths_fixed': 0,
        'errors': 0,
        'skipped': 0
    }
    
    runs_dir = client_dir / "runs"
    if not runs_dir.exists():
        log_warning(f"No runs directory found in {client_dir}")
        return stats
    
    # Find all JSON files
    json_files = list(runs_dir.glob("run_results_*.json"))
    log_info(f"Found {len(json_files)} JSON files")
    
    for json_file in json_files:
        log_info(f"Processing {json_file.name}...")
        
        # Load JSON
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
        except Exception as e:
            log_error(f"Failed to load {json_file.name}: {e}")
            stats['errors'] += 1
            continue
        
        # Process results structure
        results = data.get('results', [])
        if not results:
            log_info(f"No results in {json_file.name}")
            continue
        
        updated = False
        for result in results:
            ads = result.get('ads', [])
            
            for ad in ads:
                ad_type = ad.get('type', '')
                if not ad_type:
                    continue
                
                # Check for path fields
                path_fields = ['skyscraper_image_path', 'carousel_image_path', 'toa_image_path']
                
                for field in path_fields:
                    if field in ad and ad[field]:
                        old_path = ad[field]
                        
                        # Extract just the filename
                        filename = os.path.basename(old_path)
                        
                        # Determine correct folder
                        if 'skyscraper' in field:
                            folder = 'Skyscraper'
                        elif 'carousel' in field:
                            folder = 'Carousel'
                        elif 'toa' in field:
                            folder = 'TOA'
                        else:
                            continue
                        
                        # Check if file actually exists
                        actual_folder = client_dir / folder
                        if actual_folder.exists():
                            # Find matching file
                            matching = list(actual_folder.glob(f"*{ad_type.lower()}*.png"))
                            if matching:
                                correct_path = f"{folder}/{matching[0].name}"
                                
                                if ad[field] != correct_path:
                                    if dry_run:
                                        log_info(f"  [DRY RUN] Would fix: {field}")
                                        log_info(f"    Old: {ad[field]}")
                                        log_info(f"    New: {correct_path}")
                                    else:
                                        ad[field] = correct_path
                                        updated = True
                                        stats['paths_fixed'] += 1
                                        log_success(f"  Fixed: {field} → {correct_path}")
        
        # Save updated JSON
        if updated and not dry_run:
            try:
                with open(json_file, 'w') as f:
                    json.dump(data, f, indent=2)
                log_success(f"  Updated {json_file.name}")
                stats['json_updated'] += 1
            except Exception as e:
                log_error(f"  Failed to update {json_file.name}: {e}")
                stats['errors'] += 1
    
    return stats

# ============================================================================
# Main Migration Logic
# ============================================================================

def migrate_retailer(output_dir: Path, retailer: str, client: str = None, dry_run: bool = True):
    """Migrate a specific retailer or all retailers"""
    
    print("\n" + "="*60)
    print(f"Taxonomy Migration - {retailer.upper()}")
    print(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    print("="*60 + "\n")
    
    retailer_dir = output_dir / retailer
    if not retailer_dir.exists():
        log_error(f"Retailer directory not found: {retailer_dir}")
        return
    
    # Get clients to process
    if client:
        clients = [client]
    else:
        clients = [d.name for d in retailer_dir.iterdir() if d.is_dir()]
    
    log_info(f"Processing {len(clients)} client(s)")
    
    total_stats = {
        'files_moved': 0,
        'json_updated': 0,
        'images_linked': 0,
        'paths_fixed': 0,
        'errors': 0,
        'skipped': 0
    }
    
    for client_name in clients:
        client_dir = retailer_dir / client_name
        
        print(f"\n{Colors.BLUE}{'─'*60}{Colors.NC}")
        print(f"{Colors.BLUE}Client: {client_name}{Colors.NC}")
        print(f"{Colors.BLUE}{'─'*60}{Colors.NC}\n")
        
        # Call appropriate migration function
        if retailer == 'walmart':
            stats = migrate_walmart_client(client_dir, dry_run)
        elif retailer == 'instacart':
            stats = migrate_instacart_client(client_dir, dry_run)
        elif retailer == 'kroger':
            stats = migrate_kroger_client(client_dir, dry_run)
        else:
            log_warning(f"No migration defined for {retailer}")
            continue
        
        # Aggregate stats
        for key in total_stats:
            total_stats[key] += stats.get(key, 0)
        
        # Print client summary
        print(f"\n{Colors.YELLOW}Client Summary:{Colors.NC}")
        for key, value in stats.items():
            if value > 0:
                print(f"  {key}: {value}")
    
    # Print total summary
    print(f"\n{Colors.GREEN}{'='*60}{Colors.NC}")
    print(f"{Colors.GREEN}Total Summary{Colors.NC}")
    print(f"{Colors.GREEN}{'='*60}{Colors.NC}")
    for key, value in total_stats.items():
        if value > 0:
            print(f"  {key}: {value}")
    print()

def main():
    parser = argparse.ArgumentParser(description='Migrate ad data to comply with taxonomy')
    parser.add_argument('--retailer', required=True, 
                       choices=['walmart', 'instacart', 'kroger', 'all'],
                       help='Retailer to migrate')
    parser.add_argument('--client', help='Specific client to migrate (optional)')
    parser.add_argument('--dry-run', action='store_true', default=True,
                       help='Show what would be done without making changes')
    parser.add_argument('--execute', action='store_true',
                       help='Actually perform the migration')
    
    args = parser.parse_args()
    
    # Determine dry run mode
    dry_run = not args.execute
    
    # Get output directory
    output_dir = PROJECT_ROOT / "output"
    if not output_dir.exists():
        log_error(f"Output directory not found: {output_dir}")
        sys.exit(1)
    
    # Migrate
    if args.retailer == 'all':
        for retailer in ['walmart', 'instacart', 'kroger']:
            migrate_retailer(output_dir, retailer, args.client, dry_run)
    else:
        migrate_retailer(output_dir, args.retailer, args.client, dry_run)
    
    if dry_run:
        print(f"\n{Colors.YELLOW}This was a DRY RUN. No changes were made.{Colors.NC}")
        print(f"{Colors.YELLOW}Run with --execute to perform the migration.{Colors.NC}\n")

if __name__ == '__main__':
    main()
