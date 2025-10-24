#!/usr/bin/env python3
"""
Re-extract images for scrapes that don't have image paths stored in JSON.
This fixes the issue where old scrapes can't reliably match images to ads.
"""

import json
import os
import glob
import subprocess
import sys
from pathlib import Path

def get_base_dir():
    """Get the base directory of the project"""
    return Path(__file__).parent.parent

def find_scrapes_missing_paths():
    """Find all JSON files with ads that don't have image paths"""
    base_dir = get_base_dir()
    missing = []
    
    # Check all retailers
    for retailer in ['kroger', 'walmart', 'instacart']:
        pattern = str(base_dir / f'output/{retailer}/*/runs/*.json')
        json_files = glob.glob(pattern)
        
        for json_file in json_files:
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                
                has_missing = False
                for result in data.get('results', []):
                    for ad in result.get('ads', []):
                        ad_type = ad.get('type')
                        
                        # Check if path field is missing
                        if ad_type == 'TOA' and 'toa_image_path' not in ad:
                            has_missing = True
                        elif ad_type == 'Skyscraper' and 'skyscraper_image_path' not in ad:
                            has_missing = True
                        elif ad_type == 'CuratedCarousel' and 'carousel_image_path' not in ad:
                            has_missing = True
                
                if has_missing:
                    missing.append(json_file)
            except Exception as e:
                print(f"Error checking {json_file}: {e}")
    
    return missing

def reextract_images(json_file):
    """Re-run screenshot extraction for a specific JSON file"""
    base_dir = get_base_dir()
    
    # Get the HTML file - try both run_results and search_results naming
    html_file = json_file.replace('.json', '.html')
    
    # If run_results_*.json, also try search_results_*.html
    if not os.path.exists(html_file) and 'run_results_' in json_file:
        html_file = json_file.replace('run_results_', 'search_results_').replace('.json', '.html')
    
    if not os.path.exists(html_file):
        print(f"  ⚠️  HTML file not found: {os.path.basename(html_file)}")
        return False
    
    # Extract client name from path
    # Path format: output/{retailer}/{client}/runs/run_results_{keyword}_{timestamp}.json
    parts = json_file.split(os.sep)
    try:
        retailer_idx = parts.index('output') + 1
        retailer = parts[retailer_idx]
        client = parts[retailer_idx + 1]
    except (ValueError, IndexError):
        print(f"  ⚠️  Could not extract client from path: {json_file}")
        return False
    
    # Determine output directory
    output_dir = str(base_dir / f'output/{retailer}')
    
    # Get profile directory for the retailer
    profile_dir = os.environ.get('KROGER_PROFILE_DIR') if retailer == 'kroger' else None
    
    # Build command
    cmd = [
        sys.executable,
        str(base_dir / 'extractors/screenshot_ad_image.py'),
        '--json', json_file,
        '--html', html_file,
        '--client', client,
        '--output', output_dir,
        '--headless',
        '--max-per-type', '999',  # Extract all images
    ]
    
    if profile_dir:
        cmd.extend(['--profile-dir', profile_dir])
    
    print(f"  🔄 Running: {' '.join(cmd[-8:])}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            print(f"  ✅ Success")
            return True
        else:
            print(f"  ❌ Failed (exit code {result.returncode})")
            if result.stderr:
                print(f"     Error: {result.stderr[:200]}")
            return False
    except subprocess.TimeoutExpired:
        print(f"  ⏱️  Timeout (5 minutes)")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Re-extract images for scrapes missing paths')
    parser.add_argument('--limit', type=int, help='Limit number of scrapes to process (for testing)')
    args = parser.parse_args()
    
    print("🔍 Scanning for scrapes with missing image paths...\n")
    
    missing = find_scrapes_missing_paths()
    
    if not missing:
        print("✅ All scrapes have image paths stored!")
        return 0
    
    print(f"📋 Found {len(missing)} scrape(s) with missing image paths\n")
    
    # Apply limit if specified
    if args.limit and args.limit < len(missing):
        print(f"⚠️  Limiting to first {args.limit} scrapes for testing\n")
        missing = missing[:args.limit]
    
    # Ask for confirmation
    response = input(f"Re-extract images for {len(missing)} scrapes? (y/n): ").strip().lower()
    if response != 'y':
        print("Cancelled")
        return 1
    
    print("\n🚀 Starting re-extraction...\n")
    
    success_count = 0
    fail_count = 0
    
    for i, json_file in enumerate(missing, 1):
        # Show relative path
        rel_path = json_file.replace(str(get_base_dir()), '').lstrip('/')
        print(f"[{i}/{len(missing)}] {rel_path}")
        
        if reextract_images(json_file):
            success_count += 1
        else:
            fail_count += 1
        
        print()
    
    print(f"\n📊 Summary:")
    print(f"  ✅ Success: {success_count}")
    print(f"  ❌ Failed: {fail_count}")
    print(f"  📁 Total: {len(missing)}")
    
    return 0 if fail_count == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
