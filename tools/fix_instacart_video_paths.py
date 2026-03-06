#!/usr/bin/env python3
"""
Fix Instacart video ads that have video_overlay but missing video_path.

The videos exist in output/instacart/_shared_videos/ with MD5 hash filenames.
This script maps them back to the ads by checking if the video file exists.

Usage:
    python3 tools/fix_instacart_video_paths.py --preview
    python3 tools/fix_instacart_video_paths.py --apply
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def get_video_hash(video_url: str) -> str:
    """Get MD5 hash of video URL for lookup in _shared_videos."""
    return hashlib.md5(video_url.encode('utf-8')).hexdigest()


def find_video_in_shared(video_url: str, shared_videos_dir: Path) -> Path:
    """Check if video exists in _shared_videos directory."""
    if not video_url:
        return None
    
    video_hash = get_video_hash(video_url)
    video_file = shared_videos_dir / f"{video_hash}.mp4"
    
    if video_file.exists():
        return video_file
    
    return None


def fix_video_paths(run_data: dict, output_root: Path) -> Tuple[int, List[str]]:
    """Fix video ads with missing video_path."""
    fixed_count = 0
    changes = []
    
    retailer = run_data.get("retailer", "")
    if retailer != "instacart":
        return 0, []
    
    shared_videos_dir = output_root / "instacart" / "_shared_videos"
    if not shared_videos_dir.exists():
        return 0, [f"  ⚠️ Shared videos directory not found: {shared_videos_dir}"]
    
    ads = run_data.get("ads", [])
    
    for idx, ad in enumerate(ads):
        ad_type = ad.get("type", "")
        
        # Only process video ads
        if "video" not in ad_type.lower():
            continue
        
        # Check if already has video_path
        if ad.get("video_path"):
            continue
        
        # Check if has video_overlay (indicates video was detected)
        if not ad.get("video_overlay"):
            continue
        
        # Try to find video in metadata or reconstruct URL
        # First check if there's a video_url field
        video_url = ad.get("video_url")
        
        if video_url:
            video_file = find_video_in_shared(video_url, shared_videos_dir)
            if video_file:
                # Set relative path from output/instacart/
                rel_path = f"_shared_videos/{video_file.name}"
                ad["video_path"] = rel_path
                fixed_count += 1
                brand = ad.get("brand", "Unknown")
                changes.append(f"  Ad {idx+1}: {brand} - Mapped to {video_file.name}")
            else:
                brand = ad.get("brand", "Unknown")
                changes.append(f"  Ad {idx+1}: {brand} - Video URL found but file missing: {video_url[:80]}...")
        else:
            brand = ad.get("brand", "Unknown")
            changes.append(f"  Ad {idx+1}: {brand} - No video_url in metadata (can't map)")
    
    return fixed_count, changes


def process_run_file(json_path: Path, output_root: Path, apply: bool = False) -> Dict:
    """Process a single run JSON file."""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            run_data = json.load(f)
    except Exception as e:
        return {"error": str(e), "file": str(json_path)}
    
    retailer = run_data.get("retailer", "")
    run_id = run_data.get("run_id", "")
    
    if retailer != "instacart":
        return {"skipped": True}
    
    results = {
        "file": str(json_path.relative_to(output_root)),
        "retailer": retailer,
        "run_id": run_id,
        "changes": [],
        "total_fixes": 0
    }
    
    count, changes = fix_video_paths(run_data, output_root)
    results["video_paths_fixed"] = count
    results["changes"].extend(changes)
    results["total_fixes"] = count
    
    # Write back if applying changes and fixes were made
    if apply and results["total_fixes"] > 0:
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(run_data, f, indent=2, ensure_ascii=False)
            results["applied"] = True
        except Exception as e:
            results["write_error"] = str(e)
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Fix Instacart video paths for ads with video_overlay but missing video_path")
    parser.add_argument("--client", help="Specific client to process")
    parser.add_argument("--preview", action="store_true", help="Preview changes without applying")
    parser.add_argument("--apply", action="store_true", help="Apply changes to JSON files")
    parser.add_argument("--limit", type=int, help="Limit number of files to process")
    
    args = parser.parse_args()
    
    if not args.preview and not args.apply:
        print("ERROR: Must specify either --preview or --apply")
        sys.exit(1)
    
    # Get output root
    script_dir = Path(__file__).parent.parent
    output_root = script_dir / "output"
    
    if not output_root.exists():
        print(f"ERROR: Output directory not found: {output_root}")
        sys.exit(1)
    
    print(f"{'PREVIEW' if args.preview else 'APPLYING'} Instacart video path fixes")
    print(f"Output root: {output_root}")
    print()
    
    retailer_dir = output_root / "instacart"
    if not retailer_dir.exists():
        print("ERROR: Instacart directory not found")
        sys.exit(1)
    
    shared_videos_dir = retailer_dir / "_shared_videos"
    if not shared_videos_dir.exists():
        print(f"ERROR: Shared videos directory not found: {shared_videos_dir}")
        sys.exit(1)
    
    video_count = len(list(shared_videos_dir.glob("*.mp4")))
    print(f"Found {video_count} videos in _shared_videos/")
    print()
    
    # Find all run JSON files
    json_files = []
    for client_dir in retailer_dir.iterdir():
        if not client_dir.is_dir() or client_dir.name == "_shared_videos":
            continue
        if args.client and client_dir.name != args.client:
            continue
        
        runs_dir = client_dir / "runs"
        if runs_dir.exists():
            for run_dir in runs_dir.iterdir():
                if run_dir.is_dir():
                    for json_file in run_dir.glob("run_results_*.json"):
                        json_files.append(json_file)
    
    if args.limit:
        json_files = json_files[:args.limit]
    
    print(f"Processing {len(json_files)} run files")
    print(f"{'='*60}\n")
    
    total_files = 0
    total_fixes = 0
    total_errors = 0
    
    for json_path in json_files:
        total_files += 1
        result = process_run_file(json_path, output_root, apply=args.apply)
        
        if result.get("error"):
            total_errors += 1
            print(f"❌ ERROR: {result['file']}")
            print(f"   {result['error']}\n")
            continue
        
        if result.get("skipped"):
            continue
        
        if result.get("total_fixes", 0) > 0 or result.get("changes"):
            total_fixes += result.get("total_fixes", 0)
            print(f"📝 {result['file']}")
            for change in result["changes"]:
                print(change)
            if args.apply and result.get("applied"):
                print("  ✅ Changes applied")
            print()
    
    print(f"{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"Files processed: {total_files}")
    print(f"Video paths fixed: {total_fixes}")
    print(f"Errors: {total_errors}")
    print(f"Mode: {'PREVIEW (no changes written)' if args.preview else 'APPLIED (changes written)'}")


if __name__ == "__main__":
    main()
