#!/usr/bin/env python3
"""
Backfill MP4 videos for Instacart video ads using stored HLS URLs.

This script:
1. Finds all Instacart video ads with video_url (HLS stream) but no local MP4
2. Downloads the HLS stream using ffmpeg
3. Updates the JSON with video_path

Usage:
    python tools/backfill_instacart_mp4s.py [--dry-run] [--client CLIENT] [--limit N]
"""

import json
import os
import subprocess
import shutil
import glob
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_ROOT = PROJECT_ROOT / "output" / "instacart"

# Find ffmpeg
FFMPEG = shutil.which('ffmpeg') or '/opt/homebrew/bin/ffmpeg'


def download_hls_to_mp4(hls_url: str, output_path: Path, timeout: int = 60) -> bool:
    """Download HLS stream to MP4 using ffmpeg."""
    try:
        result = subprocess.run(
            [FFMPEG, '-i', hls_url, '-c', 'copy', '-bsf:a', 'aac_adtstoasc', str(output_path)],
            capture_output=True,
            timeout=timeout
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"    ⚠️ ffmpeg error: {e}")
        return False


def process_json_file(json_path: Path, client_root: Path, dry_run: bool = False) -> dict:
    """Process a single JSON file and download missing MP4s."""
    stats = {"checked": 0, "downloaded": 0, "skipped": 0, "failed": 0}
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    ads = data.get('ads', [])
    modified = False
    
    for ad in ads:
        ad_type = (ad.get('type') or '').lower()
        if 'video' not in ad_type:
            continue
        
        stats["checked"] += 1
        
        # Get HLS URL
        hls_url = ad.get('video_url')
        if not hls_url or not hls_url.startswith('http'):
            stats["skipped"] += 1
            continue
        
        # Check if MP4 already exists
        image_path = ad.get('image_path')
        if not image_path:
            stats["skipped"] += 1
            continue
        
        # Derive MP4 path from image path
        mp4_rel_path = image_path.replace('.png', '.mp4')
        mp4_full_path = client_root / mp4_rel_path
        
        if mp4_full_path.exists():
            # Already have MP4, just ensure video_path is set
            if not ad.get('video_path'):
                ad['video_path'] = mp4_rel_path
                modified = True
            stats["skipped"] += 1
            continue
        
        # Need to download
        print(f"    📥 Downloading: {mp4_rel_path}")
        
        if dry_run:
            print(f"       [DRY RUN] Would download from {hls_url[:60]}...")
            stats["downloaded"] += 1
            continue
        
        # Ensure directory exists
        mp4_full_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Download
        if download_hls_to_mp4(hls_url, mp4_full_path):
            ad['video_path'] = mp4_rel_path
            modified = True
            stats["downloaded"] += 1
            print(f"       ✅ Downloaded ({mp4_full_path.stat().st_size} bytes)")
        else:
            stats["failed"] += 1
            print(f"       ❌ Failed")
    
    # Save if modified
    if modified and not dry_run:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    return stats


def main():
    parser = argparse.ArgumentParser(description="Backfill MP4s for Instacart video ads")
    parser.add_argument("--dry-run", action="store_true", help="Don't download, just report")
    parser.add_argument("--client", type=str, help="Process only specific client")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of downloads (0=unlimited)")
    args = parser.parse_args()
    
    if not os.path.exists(FFMPEG):
        print(f"❌ ffmpeg not found at {FFMPEG}")
        return
    
    print(f"🔧 Using ffmpeg: {FFMPEG}")
    
    # Find all client directories
    if args.client:
        clients = [OUTPUT_ROOT / args.client]
        if not clients[0].exists():
            print(f"❌ Client not found: {args.client}")
            return
    else:
        clients = [d for d in OUTPUT_ROOT.iterdir() if d.is_dir()]
    
    total_stats = {"checked": 0, "downloaded": 0, "skipped": 0, "failed": 0}
    download_count = 0
    
    for client_dir in sorted(clients):
        client_name = client_dir.name
        
        # Find all run JSON files
        json_files = list(client_dir.glob("**/run_results*.json"))
        if not json_files:
            continue
        
        print(f"\n📁 {client_name}: {len(json_files)} run files")
        
        for json_path in json_files:
            if args.limit and download_count >= args.limit:
                print(f"\n⏹️ Reached limit of {args.limit} downloads")
                break
            
            stats = process_json_file(json_path, client_dir, args.dry_run)
            
            for k, v in stats.items():
                total_stats[k] += v
            
            download_count += stats["downloaded"]
            
            if stats["downloaded"] > 0:
                print(f"  📄 {json_path.name}: +{stats['downloaded']} MP4s")
        
        if args.limit and download_count >= args.limit:
            break
    
    # Summary
    print(f"\n{'='*50}")
    print(f"📊 Summary:")
    print(f"   Video ads checked: {total_stats['checked']}")
    print(f"   Already had MP4: {total_stats['skipped']}")
    print(f"   Downloaded: {total_stats['downloaded']}")
    print(f"   Failed: {total_stats['failed']}")
    
    if args.dry_run:
        print(f"\n🔍 DRY RUN - no files were downloaded")


if __name__ == "__main__":
    main()
