#!/usr/bin/env python3
"""
Batch Thumbnail Generator

Pre-generates thumbnails for all existing ad images to populate the cache.
This eliminates the first-request delay for thumbnail generation.

Usage:
    python3 tools/batch_generate_thumbnails.py [--dry-run] [--retailer RETAILER] [--client CLIENT]

Examples:
    # Generate all thumbnails
    python3 tools/batch_generate_thumbnails.py
    
    # Preview what would be generated (no actual generation)
    python3 tools/batch_generate_thumbnails.py --dry-run
    
    # Generate only for specific retailer
    python3 tools/batch_generate_thumbnails.py --retailer walmart
    
    # Generate only for specific client
    python3 tools/batch_generate_thumbnails.py --retailer kroger --client halo_top
"""

import sys
import argparse
from pathlib import Path
from time import time, perf_counter
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from web.builder_server_v2 import generate_thumbnail, THUMBNAIL_CACHE, _thumbnail_stats

# Supported image extensions
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp'}

def find_all_images(output_root: Path, retailer: str = None, client: str = None):
    """Find all ad images in the output directory."""
    images = []
    
    # Build search path
    if retailer and client:
        search_path = output_root / retailer / client
    elif retailer:
        search_path = output_root / retailer
    else:
        search_path = output_root
    
    if not search_path.exists():
        print(f"❌ Path does not exist: {search_path}")
        return []
    
    print(f"🔍 Scanning: {search_path}")
    
    # Find all image files
    for ext in IMAGE_EXTENSIONS:
        pattern = f"**/*{ext}"
        found = list(search_path.glob(pattern))
        images.extend(found)
        print(f"   Found {len(found)} {ext} files")
    
    return images

def process_image(image_path: Path, dry_run: bool = False):
    """Process a single image (generate thumbnail)."""
    try:
        if dry_run:
            # Just check if thumbnail exists
            cache_filename = f"{image_path.stem}_800.jpg"
            cache_path = THUMBNAIL_CACHE / cache_filename
            exists = cache_path.exists()
            return {
                'path': image_path,
                'status': 'exists' if exists else 'would_generate',
                'size': image_path.stat().st_size,
                'error': None
            }
        else:
            # Generate thumbnail
            start = perf_counter()
            thumbnail_path = generate_thumbnail(image_path, max_width=800, quality=85)
            elapsed = perf_counter() - start
            
            return {
                'path': image_path,
                'status': 'generated' if thumbnail_path != image_path else 'cached',
                'size': image_path.stat().st_size,
                'thumbnail_size': thumbnail_path.stat().st_size if thumbnail_path.exists() else 0,
                'elapsed': elapsed,
                'error': None
            }
    except Exception as e:
        return {
            'path': image_path,
            'status': 'error',
            'size': 0,
            'error': str(e)
        }

def format_size(bytes_size):
    """Format bytes to human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f}{unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f}TB"

def format_time(seconds):
    """Format seconds to human-readable time."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}m"
    else:
        return f"{seconds / 3600:.1f}h"

def main():
    parser = argparse.ArgumentParser(description='Batch generate thumbnails for all ad images')
    parser.add_argument('--dry-run', action='store_true', help='Preview without generating')
    parser.add_argument('--retailer', type=str, help='Filter by retailer (e.g., walmart, kroger)')
    parser.add_argument('--client', type=str, help='Filter by client (requires --retailer)')
    parser.add_argument('--workers', type=int, default=4, help='Number of parallel workers (default: 4)')
    parser.add_argument('--max-images', type=int, help='Limit number of images to process (for testing)')
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.client and not args.retailer:
        print("❌ --client requires --retailer")
        sys.exit(1)
    
    # Find output directory
    output_root = project_root / "output"
    if not output_root.exists():
        print(f"❌ Output directory not found: {output_root}")
        sys.exit(1)
    
    print("=" * 80)
    print("🖼️  BATCH THUMBNAIL GENERATOR")
    print("=" * 80)
    print(f"Mode: {'DRY RUN (preview only)' if args.dry_run else 'GENERATE'}")
    print(f"Output root: {output_root}")
    print(f"Cache directory: {THUMBNAIL_CACHE}")
    print(f"Workers: {args.workers}")
    if args.retailer:
        print(f"Filter: retailer={args.retailer}" + (f", client={args.client}" if args.client else ""))
    print()
    
    # Find all images
    start_time = time()
    images = find_all_images(output_root, args.retailer, args.client)
    
    if not images:
        print("❌ No images found")
        sys.exit(0)
    
    # Apply max limit if specified
    if args.max_images:
        images = images[:args.max_images]
        print(f"⚠️  Limited to first {args.max_images} images")
    
    total_images = len(images)
    total_size = sum(img.stat().st_size for img in images)
    
    print(f"\n📊 Found {total_images:,} images ({format_size(total_size)})")
    print()
    
    if args.dry_run:
        print("🔍 Checking cache status...")
    else:
        print("⚙️  Generating thumbnails...")
        print("   (This may take 30-60 minutes for 36K images)")
    print()
    
    # Process images in parallel
    results = {
        'generated': 0,
        'cached': 0,
        'errors': 0,
        'would_generate': 0,
        'exists': 0,
        'total_original_size': 0,
        'total_thumbnail_size': 0
    }
    
    processed = 0
    last_update = time()
    
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        # Submit all tasks
        futures = {executor.submit(process_image, img, args.dry_run): img for img in images}
        
        # Process results as they complete
        for future in as_completed(futures):
            result = future.result()
            processed += 1
            
            # Update stats
            status = result['status']
            results[status] = results.get(status, 0) + 1
            results['total_original_size'] += result['size']
            if 'thumbnail_size' in result:
                results['total_thumbnail_size'] += result['thumbnail_size']
            
            # Print progress every 1 second
            now = time()
            if now - last_update >= 1.0 or processed == total_images:
                elapsed = now - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                eta = (total_images - processed) / rate if rate > 0 else 0
                
                pct = (processed / total_images) * 100
                bar_width = 40
                filled = int(bar_width * processed / total_images)
                bar = '█' * filled + '░' * (bar_width - filled)
                
                print(f"\r[{bar}] {pct:5.1f}% | {processed:,}/{total_images:,} | "
                      f"{rate:.1f} img/s | ETA: {format_time(eta)}", end='', flush=True)
                
                last_update = now
            
            # Print errors immediately
            if result['error']:
                print(f"\n❌ Error: {result['path'].name}: {result['error']}")
    
    print("\n")
    
    # Final statistics
    elapsed_total = time() - start_time
    
    print("=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)
    
    if args.dry_run:
        print(f"Already cached:    {results.get('exists', 0):,} images")
        print(f"Would generate:    {results.get('would_generate', 0):,} images")
    else:
        print(f"Generated:         {results.get('generated', 0):,} images")
        print(f"Already cached:    {results.get('cached', 0):,} images")
        print(f"Errors:            {results.get('errors', 0):,} images")
        print()
        print(f"Original size:     {format_size(results['total_original_size'])}")
        print(f"Thumbnail size:    {format_size(results['total_thumbnail_size'])}")
        if results['total_original_size'] > 0:
            reduction = (1 - results['total_thumbnail_size'] / results['total_original_size']) * 100
            print(f"Size reduction:    {reduction:.1f}%")
    
    print()
    print(f"Total time:        {format_time(elapsed_total)}")
    print(f"Processing rate:   {total_images / elapsed_total:.1f} images/second")
    print()
    
    # Cache statistics
    cache_files = list(THUMBNAIL_CACHE.glob("*.jpg"))
    cache_size = sum(f.stat().st_size for f in cache_files)
    print(f"Cache directory:   {THUMBNAIL_CACHE}")
    print(f"Cache files:       {len(cache_files):,}")
    print(f"Cache size:        {format_size(cache_size)}")
    print()
    
    if not args.dry_run:
        print("✅ Thumbnail generation complete!")
        print()
        print("Next steps:")
        print("  1. Restart Flask server to see updated stats")
        print("  2. Check stats: curl http://localhost:5006/api/thumbnail/stats")
        print("  3. Test in browser - all images should load instantly!")
    else:
        print("💡 Run without --dry-run to generate thumbnails")
    
    print("=" * 80)

if __name__ == '__main__':
    main()
