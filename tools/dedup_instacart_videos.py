#!/usr/bin/env python3
"""
Cross-run video deduplication for Instacart MP4s.

Many Instacart video ads are the same video served across different runs/clients.
This tool:
  1. Hashes all MP4 files to find true duplicates
  2. Keeps one canonical copy in a shared store: output/instacart/_shared_videos/{hash}.mp4
  3. Replaces all duplicates with symlinks to the shared copy
  4. Updates JSON image_path/video_path to use the symlink (no change needed — symlinks are transparent)

The symlinks are transparent to the Flask server's file-serving logic, so no
backend changes are needed.

Usage:
    python tools/dedup_instacart_videos.py --dry-run
    python tools/dedup_instacart_videos.py
    python tools/dedup_instacart_videos.py --undo   # Restore original files from shared store
"""

import argparse
import glob
import hashlib
import json
import os
import shutil
import sys
from collections import defaultdict
from pathlib import Path


SHARED_DIR_NAME = "_shared_videos"


def hash_file(filepath, chunk_size=65536):
    """Compute MD5 hash of a file."""
    h = hashlib.md5()
    with open(filepath, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def find_all_mp4s(output_root):
    """Find all MP4 files under the instacart output directory."""
    mp4s = []
    for f in glob.glob(os.path.join(output_root, '**', '*.mp4'), recursive=True):
        # Skip the shared directory itself
        if SHARED_DIR_NAME in f:
            continue
        if os.path.isfile(f) and not os.path.islink(f):
            mp4s.append(f)
    return mp4s


def find_all_mp4_links(output_root):
    """Find all MP4 symlinks (for undo)."""
    links = []
    for f in glob.glob(os.path.join(output_root, '**', '*.mp4'), recursive=True):
        if SHARED_DIR_NAME in f:
            continue
        if os.path.islink(f):
            links.append(f)
    return links


def dedup(output_root, dry_run=False):
    """Main dedup logic."""
    shared_dir = os.path.join(output_root, SHARED_DIR_NAME)
    
    # Step 1: Find all MP4s
    print("🔍 Scanning for MP4 files...")
    mp4s = find_all_mp4s(output_root)
    print(f"   Found {len(mp4s)} MP4 files (excluding symlinks)")
    
    if not mp4s:
        print("   Nothing to deduplicate.")
        return
    
    # Step 2: Group by size first (optimization — only hash same-size files)
    print("📏 Grouping by file size...")
    by_size = defaultdict(list)
    for f in mp4s:
        by_size[os.path.getsize(f)].append(f)
    
    unique_sizes = sum(1 for files in by_size.values() if len(files) == 1)
    dup_sizes = sum(1 for files in by_size.values() if len(files) > 1)
    print(f"   {unique_sizes} unique sizes, {dup_sizes} shared sizes")
    
    # Step 3: Hash files that share a size
    print("🔐 Hashing potential duplicates...")
    hash_groups = defaultdict(list)  # hash -> [filepath, ...]
    
    for size, files in by_size.items():
        if len(files) == 1:
            # Unique size — still need to track it
            hash_groups[hash_file(files[0])].append(files[0])
            continue
        for f in files:
            h = hash_file(f)
            hash_groups[h].append(f)
    
    unique_videos = len(hash_groups)
    dup_groups = {h: files for h, files in hash_groups.items() if len(files) > 1}
    total_dups = sum(len(files) - 1 for files in dup_groups.values())
    savings = sum(os.path.getsize(files[0]) * (len(files) - 1) for files in dup_groups.values())
    
    print(f"\n📊 Dedup Analysis:")
    print(f"   Unique videos: {unique_videos}")
    print(f"   Duplicate groups: {len(dup_groups)}")
    print(f"   Duplicate files to replace with symlinks: {total_dups}")
    print(f"   Space to recover: {savings / (1024**3):.2f} GB")
    
    if dry_run:
        print(f"\n🔍 DRY RUN — no changes made")
        # Show top 10 most duplicated
        print(f"\nTop 10 most duplicated videos:")
        for h, files in sorted(dup_groups.items(), key=lambda x: len(x[1]), reverse=True)[:10]:
            size = os.path.getsize(files[0])
            print(f"  {h[:12]}... {size:>10,} bytes x {len(files)} copies ({size * len(files) / (1024**2):.1f} MB total)")
        return
    
    # Step 4: Create shared directory
    os.makedirs(shared_dir, exist_ok=True)
    
    # Step 5: For each duplicate group, move one copy to shared and symlink the rest
    print(f"\n🔗 Creating shared store and symlinks...")
    links_created = 0
    bytes_freed = 0
    
    for file_hash, files in dup_groups.items():
        canonical = os.path.join(shared_dir, f"{file_hash}.mp4")
        
        # Move the first file to shared store (or skip if already there)
        if not os.path.exists(canonical):
            shutil.copy2(files[0], canonical)
        
        # Replace all copies with symlinks
        for f in files:
            file_size = os.path.getsize(f)
            os.remove(f)
            # Create relative symlink
            rel_target = os.path.relpath(canonical, os.path.dirname(f))
            os.symlink(rel_target, f)
            links_created += 1
            bytes_freed += file_size
    
    # Also handle unique files — move to shared and symlink for consistency
    # (This makes future dedup easier when new runs are added)
    for file_hash, files in hash_groups.items():
        if len(files) == 1:
            canonical = os.path.join(shared_dir, f"{file_hash}.mp4")
            if not os.path.exists(canonical):
                shutil.copy2(files[0], canonical)
            file_size = os.path.getsize(files[0])
            os.remove(files[0])
            rel_target = os.path.relpath(canonical, os.path.dirname(files[0]))
            os.symlink(rel_target, files[0])
            links_created += 1
    
    print(f"   ✅ Symlinks created: {links_created}")
    print(f"   ✅ Space freed: {bytes_freed / (1024**3):.2f} GB")
    print(f"   📁 Shared store: {shared_dir} ({len(os.listdir(shared_dir))} files)")


def undo(output_root):
    """Restore original files from shared store by replacing symlinks with copies."""
    shared_dir = os.path.join(output_root, SHARED_DIR_NAME)
    
    if not os.path.isdir(shared_dir):
        print("❌ No shared store found. Nothing to undo.")
        return
    
    print("🔍 Finding symlinks...")
    links = find_all_mp4_links(output_root)
    print(f"   Found {len(links)} symlinks")
    
    restored = 0
    for link in links:
        target = os.path.realpath(link)
        if os.path.exists(target):
            os.remove(link)
            shutil.copy2(target, link)
            restored += 1
    
    print(f"   ✅ Restored {restored} files")
    
    # Remove shared directory
    shutil.rmtree(shared_dir)
    print(f"   🗑️  Removed shared store")


def main():
    parser = argparse.ArgumentParser(description='Deduplicate Instacart video MP4s')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done')
    parser.add_argument('--undo', action='store_true', help='Restore original files from shared store')
    args = parser.parse_args()
    
    output_root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'output', 'instacart')
    
    if not os.path.isdir(output_root):
        print(f"❌ Output directory not found: {output_root}")
        sys.exit(1)
    
    if args.undo:
        undo(output_root)
    else:
        dedup(output_root, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
