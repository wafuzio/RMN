#!/usr/bin/env python3
"""
Centralized product image store.

Stores one representative image per unique product ID across all retailers.
Images are stored in a flat directory per retailer:

    assets/<retailer>/product_images/<product_id>.<ext>

For example:
    assets/amazon/product_images/B0DPR511FX.jpg
    assets/walmart/product_images/1BKSA0L3Z4YD.jpg
    assets/kroger/product_images/0080033810103.jpg
    assets/target/product_images/82215651.jpg
    assets/instacart/product_images/12345678.jpg

The store is append-only: once an image exists for a product ID, it is never
overwritten. This ensures stable references and avoids redundant downloads.

Usage from scrapers or backfill scripts:
    from tools.product_image_store import store_product_image, get_image_path, has_image

    # Check if we already have an image
    if not has_image("walmart", "1BKSA0L3Z4YD"):
        # Download and store
        store_product_image("walmart", "1BKSA0L3Z4YD", image_bytes, ext="jpg")

    # Get path for JSON reference
    path = get_image_path("walmart", "1BKSA0L3Z4YD")  # -> "assets/walmart/product_images/1BKSA0L3Z4YD.jpg"

Usage from CLI (backfill from existing HTML image URLs):
    python3 tools/product_image_store.py backfill --retailer walmart --dry-run
    python3 tools/product_image_store.py backfill --retailer all
    python3 tools/product_image_store.py stats
"""

import argparse
import glob
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

# Project root (parent of tools/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"


# ── Core API ──────────────────────────────────────────────────────────────────

def _image_dir(retailer: str) -> Path:
    """Return the product image directory for a retailer."""
    return ASSETS_DIR / retailer / "product_images"


def _find_existing(retailer: str, product_id: str) -> Path | None:
    """Find an existing image file for a product ID (any extension)."""
    search_dirs = [_image_dir(retailer)]
    # Also check legacy Amazon path
    if retailer == 'amazon':
        search_dirs.append(ASSETS_DIR / 'amazon' / 'ASIN_Images')
    for d in search_dirs:
        if not d.is_dir():
            continue
        for ext in ('jpg', 'jpeg', 'png', 'webp', 'gif'):
            p = d / f"{product_id}.{ext}"
            if p.exists() and p.stat().st_size > 100:
                return p
    return None


def has_image(retailer: str, product_id: str) -> bool:
    """Check if we already have an image for this product."""
    if not product_id:
        return False
    return _find_existing(retailer, product_id) is not None


def get_image_path(retailer: str, product_id: str, relative: bool = True) -> str | None:
    """
    Get the path to a stored product image.
    Returns relative path from project root by default, or absolute if relative=False.
    Returns None if no image exists.
    """
    if not product_id:
        return None
    existing = _find_existing(retailer, product_id)
    if existing is None:
        return None
    if relative:
        return str(existing.relative_to(PROJECT_ROOT))
    return str(existing)


def store_product_image(retailer: str, product_id: str, image_data: bytes, ext: str = "jpg") -> str:
    """
    Store a product image. Returns the relative path from project root.
    No-op if an image already exists for this product ID.
    """
    if not product_id:
        raise ValueError("product_id is required")
    if not image_data or len(image_data) < 100:
        raise ValueError("image_data is too small or empty")

    existing = _find_existing(retailer, product_id)
    if existing is not None:
        return str(existing.relative_to(PROJECT_ROOT))

    d = _image_dir(retailer)
    d.mkdir(parents=True, exist_ok=True)

    ext = ext.lstrip('.').lower()
    if ext not in ('jpg', 'jpeg', 'png', 'webp', 'gif'):
        ext = 'jpg'

    path = d / f"{product_id}.{ext}"
    path.write_bytes(image_data)
    return str(path.relative_to(PROJECT_ROOT))


def download_and_store(retailer: str, product_id: str, image_url: str, timeout: int = 10) -> str | None:
    """
    Download an image from a URL and store it. Returns relative path or None on failure.
    Skips if image already exists.
    """
    if not product_id or not image_url:
        return None

    if has_image(retailer, product_id):
        return get_image_path(retailer, product_id)

    try:
        import requests
        resp = requests.get(image_url, timeout=timeout, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        resp.raise_for_status()
        if len(resp.content) < 100:
            return None

        # Determine extension from content type or URL
        ct = resp.headers.get('content-type', '')
        if 'png' in ct:
            ext = 'png'
        elif 'webp' in ct:
            ext = 'webp'
        elif 'gif' in ct:
            ext = 'gif'
        else:
            # Try URL extension
            url_path = urlparse(image_url).path
            url_ext = os.path.splitext(url_path)[1].lstrip('.').lower()
            ext = url_ext if url_ext in ('jpg', 'jpeg', 'png', 'webp', 'gif') else 'jpg'

        return store_product_image(retailer, product_id, resp.content, ext=ext)
    except Exception:
        return None


# ── Backfill from existing JSON product_listings ──────────────────────────────

def _collect_image_urls_from_json(retailer: str) -> list[dict]:
    """
    Scan all run_results JSON files for a retailer and collect
    (product_id, image_url) pairs from product_listings entries.
    """
    output_dir = PROJECT_ROOT / "output" / retailer
    if not output_dir.is_dir():
        return []

    pairs = []
    seen = set()

    for json_path in sorted(glob.glob(str(output_dir / "**" / "run_results*.json"), recursive=True)):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue

        # Check product_listings key (legacy)
        listings = data.get('product_listings', [])
        # Also check ads array for Product_Listing type
        for ad in data.get('ads', []):
            if ad.get('type') == 'Product_Listing':
                listings.append(ad)

        for item in listings:
            pid = item.get('product_id') or item.get('asin') or ''
            url = item.get('image_url') or ''
            if pid and url and pid not in seen:
                seen.add(pid)
                pairs.append({'product_id': pid, 'image_url': url})

        # Also scan slots[] — primary source for all retailers after backfill
        for slot in data.get('slots', []):
            pid = slot.get('product_id') or ''
            url = slot.get('image_url') or ''
            if pid and url and pid not in seen:
                seen.add(pid)
                pairs.append({'product_id': pid, 'image_url': url})

    return pairs


def backfill_images(retailer: str, dry_run: bool = False, verbose: bool = False, max_downloads: int = 0):
    """
    Download product images for a retailer from URLs found in JSON files.
    """
    if retailer == 'all':
        for r in ('amazon', 'walmart', 'kroger', 'target', 'instacart'):
            backfill_images(r, dry_run=dry_run, verbose=verbose, max_downloads=max_downloads)
        return

    pairs = _collect_image_urls_from_json(retailer)
    already = 0
    to_download = []

    for p in pairs:
        if has_image(retailer, p['product_id']):
            already += 1
        else:
            to_download.append(p)

    print(f"\n{retailer.upper()} image backfill:")
    print(f"  Unique products with URLs: {len(pairs)}")
    print(f"  Already stored:            {already}")
    print(f"  Need download:             {len(to_download)}")

    if dry_run:
        print("  (dry run — no downloads)")
        if verbose and to_download[:5]:
            for p in to_download[:5]:
                print(f"    {p['product_id']}  {p['image_url'][:80]}")
        return

    if max_downloads > 0:
        to_download = to_download[:max_downloads]

    downloaded = 0
    failed = 0
    for p in to_download:
        result = download_and_store(retailer, p['product_id'], p['image_url'])
        if result:
            downloaded += 1
            if verbose:
                print(f"  ✓ {p['product_id']}")
        else:
            failed += 1
            if verbose:
                print(f"  ✗ {p['product_id']}  {p['image_url'][:60]}")
        # Rate limit
        if downloaded % 50 == 0 and downloaded > 0:
            time.sleep(1)

    print(f"  Downloaded: {downloaded}")
    print(f"  Failed:     {failed}")


# ── Stats ─────────────────────────────────────────────────────────────────────

def print_stats():
    """Print image store statistics per retailer."""
    print("\nProduct Image Store Stats:")
    print(f"{'Retailer':>12}  {'Images':>8}  {'Size (MB)':>10}  {'Path'}")
    print("-" * 70)

    total_images = 0
    total_bytes = 0

    for retailer in ('amazon', 'walmart', 'kroger', 'target', 'instacart'):
        d = _image_dir(retailer)
        if not d.is_dir():
            print(f"{retailer:>12}  {'0':>8}  {'0.0':>10}  (not created)")
            continue

        count = 0
        size = 0
        for f in d.iterdir():
            if f.is_file() and f.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp', '.gif'):
                count += 1
                size += f.stat().st_size

        total_images += count
        total_bytes += size
        print(f"{retailer:>12}  {count:>8}  {size / 1024 / 1024:>10.1f}  {d.relative_to(PROJECT_ROOT)}")

    print("-" * 70)
    print(f"{'TOTAL':>12}  {total_images:>8}  {total_bytes / 1024 / 1024:>10.1f}")

    # Also check legacy Amazon ASIN_Images
    legacy = ASSETS_DIR / "amazon" / "ASIN_Images"
    if legacy.is_dir():
        count = sum(1 for f in legacy.iterdir() if f.is_file())
        print(f"\n  Note: {count} images in legacy assets/amazon/ASIN_Images/")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Centralized product image store")
    sub = parser.add_subparsers(dest='command')

    # backfill
    bp = sub.add_parser('backfill', help='Download product images from JSON URLs')
    bp.add_argument('--retailer', required=True, help='Retailer name or "all"')
    bp.add_argument('--dry-run', action='store_true')
    bp.add_argument('--verbose', '-v', action='store_true')
    bp.add_argument('--max', type=int, default=0, help='Max downloads (0=unlimited)')

    # stats
    sub.add_parser('stats', help='Print image store statistics')

    # check
    cp = sub.add_parser('check', help='Check if an image exists')
    cp.add_argument('retailer')
    cp.add_argument('product_id')

    args = parser.parse_args()

    if args.command == 'backfill':
        backfill_images(args.retailer, dry_run=args.dry_run, verbose=args.verbose, max_downloads=args.max)
    elif args.command == 'stats':
        print_stats()
    elif args.command == 'check':
        path = get_image_path(args.retailer, args.product_id)
        if path:
            print(f"Found: {path}")
        else:
            print(f"No image for {args.retailer}/{args.product_id}")
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
