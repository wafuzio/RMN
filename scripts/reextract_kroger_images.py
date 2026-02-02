#!/usr/bin/env python3
"""
Re-extract images from Kroger HTML files that are missing images.
Run this after fixing Playwright/Chromium issues.
"""

import os
import sys
import glob
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

def find_missing_html_files(base_dir: str, days: int = 3):
    """Find HTML files from the last N days that don't have corresponding images."""
    cutoff = datetime.now() - timedelta(days=days)
    missing = []
    
    for client_dir in glob.glob(os.path.join(base_dir, '*')):
        if not os.path.isdir(client_dir):
            continue
        client = os.path.basename(client_dir)
        runs_dir = os.path.join(client_dir, 'runs')
        if not os.path.isdir(runs_dir):
            continue
        
        for html in glob.glob(os.path.join(runs_dir, 'search_results_*.html')):
            m = re.search(r'(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})', os.path.basename(html))
            if not m:
                continue
            ts = m.group(1)
            
            try:
                file_dt = datetime.strptime(ts, '%Y-%m-%d_%H-%M-%S')
            except:
                continue
            
            if file_dt < cutoff:
                continue
            
            # Check if images exist
            toa_pattern = os.path.join(client_dir, 'TOA', f'*{ts}*.png')
            sky_pattern = os.path.join(client_dir, 'Skyscraper', f'*{ts}*.png')
            
            if not glob.glob(toa_pattern) and not glob.glob(sky_pattern):
                missing.append((client, html))
    
    return missing


def process_html_file(html_path: str, client_dir: str, headless: bool = True):
    """Process a single HTML file to extract images."""
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "process_saved_html.py"),
        "--files", html_path,
        "--output-dir", client_dir,
        "--force-images",
    ]
    if headless:
        cmd.append("--headless")
    
    print(f"  Processing: {os.path.basename(html_path)}")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(PROJECT_ROOT),
    )
    
    if result.returncode == 0:
        # Check if images were created
        if "saved to:" in result.stdout.lower() or "screenshot saved" in result.stdout.lower():
            return True
    return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Re-extract images from Kroger HTML files")
    parser.add_argument("--days", type=int, default=3, help="Process files from last N days (default: 3)")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of files to process (0 = all)")
    parser.add_argument("--dry-run", action="store_true", help="Just show what would be processed")
    args = parser.parse_args()
    
    base_dir = str(PROJECT_ROOT / "output" / "kroger")
    
    print(f"🔍 Finding HTML files from last {args.days} days without images...")
    missing = find_missing_html_files(base_dir, days=args.days)
    
    print(f"📋 Found {len(missing)} files to process")
    
    if args.dry_run:
        for client, html in missing[:20]:
            print(f"  [{client}] {os.path.basename(html)}")
        if len(missing) > 20:
            print(f"  ... and {len(missing) - 20} more")
        return
    
    if args.limit > 0:
        missing = missing[:args.limit]
        print(f"📋 Processing first {len(missing)} files")
    
    success = 0
    failed = 0
    
    for i, (client, html) in enumerate(missing, 1):
        client_dir = os.path.dirname(os.path.dirname(html))  # Go up from runs/
        print(f"\n[{i}/{len(missing)}] {client}")
        
        try:
            if process_html_file(html, client_dir):
                success += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  ❌ Error: {e}")
            failed += 1
    
    print(f"\n✅ Complete: {success} succeeded, {failed} failed")


if __name__ == "__main__":
    main()
