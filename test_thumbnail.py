#!/usr/bin/env python3
"""Quick test of thumbnail generation."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from web.builder_server_v2 import generate_thumbnail, THUMBNAIL_CACHE

# Test with a real image
test_image = Path("output/kroger/cheese_dip/TOA/kroger__president__toa__cheese_dip__cheese_dip__D2025-12-03_T12-33.00_1.png")

if not test_image.exists():
    print(f"❌ Test image not found: {test_image}")
    sys.exit(1)

print(f"📸 Testing thumbnail generation...")
print(f"   Source: {test_image.name}")
print(f"   Size: {test_image.stat().st_size / 1024 / 1024:.2f}MB")

# Generate thumbnail
thumbnail = generate_thumbnail(test_image, max_width=800, quality=85)

print(f"\n✅ Thumbnail generated!")
print(f"   Path: {thumbnail}")
print(f"   Size: {thumbnail.stat().st_size / 1024:.1f}KB")
print(f"   Reduction: {(1 - thumbnail.stat().st_size / test_image.stat().st_size) * 100:.1f}%")

# Test cache hit
print(f"\n🔄 Testing cache hit...")
thumbnail2 = generate_thumbnail(test_image, max_width=800, quality=85)
print(f"   Cached: {thumbnail2 == thumbnail}")

# Show cache contents
cache_files = list(THUMBNAIL_CACHE.glob("*.jpg"))
print(f"\n📁 Cache directory: {THUMBNAIL_CACHE}")
print(f"   Files: {len(cache_files)}")
if cache_files:
    total_size = sum(f.stat().st_size for f in cache_files)
    print(f"   Total size: {total_size / 1024 / 1024:.2f}MB")
