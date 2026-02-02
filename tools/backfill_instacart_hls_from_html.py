#!/usr/bin/env python3
"""
Backfill missing video_url (HLS) from HTML files for Instacart video ads.
Then download MP4s for any that are missing.

Usage:
    python tools/backfill_instacart_hls_from_html.py [--dry-run] [--download]
"""

import json
import re
import os
import glob
import subprocess
import shutil
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_ROOT = PROJECT_ROOT / "output" / "instacart"
FFMPEG = shutil.which('ffmpeg') or '/opt/homebrew/bin/ffmpeg'


def find_html_for_json(json_path: Path) -> Path | None:
    """Find the HTML file corresponding to a JSON run file."""
    run_dir = json_path.parent
    
    # Look for any HTML file in the same directory
    html_files = list(run_dir.glob("*.html"))
    if html_files:
        return html_files[0]
    
    # Also check parent runs directory for flat structure
    if run_dir.name == "runs":
        # Flat structure: runs/run_results_XXX.json and runs/search_results_XXX.html
        json_name = json_path.name
        # Extract timestamp from json name
        match = re.search(r'(\d{14})', json_name)
        if match:
            ts = match.group(1)
            for html in run_dir.glob(f"*{ts}*.html"):
                return html
    
    return None


def extract_hls_urls_from_html(html_path: Path) -> list[str]:
    """Extract all HLS (.m3u8) URLs from HTML file."""
    try:
        with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
            html = f.read()
        
        # Find all m3u8 URLs
        urls = re.findall(r'https://[^"\'<>\s]+\.m3u8[^"\'<>\s]*', html)
        # Dedupe while preserving order
        seen = set()
        unique = []
        for url in urls:
            if url not in seen:
                seen.add(url)
                unique.append(url)
        return unique
    except Exception as e:
        print(f"    Error reading HTML: {e}")
        return []


def download_hls_to_mp4(hls_url: str, output_path: Path, timeout: int = 60) -> bool:
    """Download HLS stream to MP4 using ffmpeg."""
    try:
        result = subprocess.run(
            [FFMPEG, '-i', hls_url, '-c', 'copy', '-bsf:a', 'aac_adtstoasc', str(output_path)],
            capture_output=True,
            timeout=timeout
        )
        return result.returncode == 0
    except Exception as e:
        print(f"    ffmpeg error: {e}")
        return False


def process_json_file(json_path: Path, client_root: Path, dry_run: bool, download: bool) -> dict:
    """Process a single JSON file."""
    stats = {"checked": 0, "updated_url": 0, "downloaded": 0, "failed": 0}
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    ads = data.get('ads', [])
    video_ads = [ad for ad in ads if 'video' in (ad.get('type') or '').lower()]
    
    if not video_ads:
        return stats
    
    stats["checked"] = len(video_ads)
    
    # Check if any video ads are missing HLS URL
    missing_url = [ad for ad in video_ads if not (ad.get('video_url') or '').startswith('http')]
    
    if not missing_url:
        return stats
    
    # Find HTML file
    html_path = find_html_for_json(json_path)
    if not html_path:
        return stats
    
    # Extract HLS URLs from HTML
    hls_urls = extract_hls_urls_from_html(html_path)
    if not hls_urls:
        return stats
    
    print(f"  📄 {json_path.name}: {len(missing_url)} ads missing URL, {len(hls_urls)} URLs in HTML")
    
    modified = False
    url_idx = 0
    
    for ad in video_ads:
        # Skip if already has URL
        if (ad.get('video_url') or '').startswith('http'):
            continue
        
        # Assign next available HLS URL
        if url_idx < len(hls_urls):
            hls_url = hls_urls[url_idx]
            url_idx += 1
            
            if not dry_run:
                ad['video_url'] = hls_url
                modified = True
            
            stats["updated_url"] += 1
            print(f"    + Added HLS URL to ad")
            
            # Download MP4 if requested (with deduplication via video index)
            if download and not dry_run:
                from utils.video_index import VideoIndex
                video_index = VideoIndex()
                
                # Check if this HLS URL already has an MP4
                existing_mp4 = video_index.get(hls_url)
                if existing_mp4:
                    # Reuse existing video
                    ad['video_path'] = existing_mp4.split('/', 2)[-1] if '/' in existing_mp4 else existing_mp4
                    stats["downloaded"] += 1
                    print(f"    ♻️ Reused existing MP4")
                else:
                    image_path = ad.get('image_path')
                    if image_path:
                        mp4_rel = image_path.replace('.png', '.mp4')
                        mp4_path = client_root / mp4_rel
                        
                        if not mp4_path.exists():
                            mp4_path.parent.mkdir(parents=True, exist_ok=True)
                            print(f"    📥 Downloading MP4...")
                            if download_hls_to_mp4(hls_url, mp4_path):
                                ad['video_path'] = mp4_rel
                                # Register in video index
                                full_rel = f"instacart/{client_root.name}/{mp4_rel}"
                                video_index.set(hls_url, full_rel, mp4_path.stat().st_size)
                                stats["downloaded"] += 1
                                print(f"    ✅ Downloaded")
                            else:
                                stats["failed"] += 1
                                print(f"    ❌ Failed")
    
    # Save if modified
    if modified:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    return stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Don't modify files")
    parser.add_argument("--download", action="store_true", help="Also download MP4s")
    args = parser.parse_args()
    
    print(f"🔧 Backfilling HLS URLs from HTML files")
    if args.dry_run:
        print("   (DRY RUN)")
    if args.download:
        print(f"   Will download MP4s using: {FFMPEG}")
    
    total_stats = {"checked": 0, "updated_url": 0, "downloaded": 0, "failed": 0}
    
    # Find all client directories
    for client_dir in sorted(OUTPUT_ROOT.iterdir()):
        if not client_dir.is_dir():
            continue
        
        client_name = client_dir.name
        json_files = list(client_dir.glob("**/run_results*.json"))
        
        if not json_files:
            continue
        
        print(f"\n📁 {client_name}: {len(json_files)} run files")
        
        for json_path in json_files:
            stats = process_json_file(json_path, client_dir, args.dry_run, args.download)
            for k, v in stats.items():
                total_stats[k] += v
    
    # Save video index
    if args.download and not args.dry_run:
        from utils.video_index import VideoIndex
        video_index = VideoIndex()
        video_index.save()
        print(f"\n📼 Video Index: {video_index.stats()}")
    
    print(f"\n{'='*50}")
    print(f"📊 Summary:")
    print(f"   Video ads checked: {total_stats['checked']}")
    print(f"   HLS URLs added: {total_stats['updated_url']}")
    print(f"   MP4s downloaded: {total_stats['downloaded']}")
    print(f"   Failed: {total_stats['failed']}")


if __name__ == "__main__":
    main()
