#!/usr/bin/env python3
"""
Audit Instacart image files vs canonical JSON mappings.
Identifies:
1. Images referenced in canonical JSON (mapped)
2. Images NOT referenced in any JSON (orphaned)
3. JSON ads without valid image files (broken references)
"""

import json
from pathlib import Path
from collections import defaultdict

ROOT = Path("output/instacart")

def main():
    # Collect all image files (excluding Main and legacy_backup)
    all_images = set()
    for img in ROOT.rglob("*.png"):
        if "Main" in img.parts or "legacy_backup" in img.parts:
            continue
        # Store relative to client root
        try:
            # Find client dir (e.g., output/instacart/blue_bunny)
            client_idx = list(img.parts).index("instacart") + 1
            client = img.parts[client_idx]
            rel_path = str(Path(*img.parts[client_idx + 1:]))
            all_images.add((client, rel_path))
        except (ValueError, IndexError):
            pass
    
    # Collect all image_path references from canonical JSON
    referenced_images = set()
    broken_refs = []
    json_count = 0
    ad_count = 0
    
    for json_file in ROOT.rglob("run_results_*.json"):
        if "legacy_backup" in str(json_file):
            continue
        
        try:
            data = json.loads(json_file.read_text())
            if not isinstance(data.get("ads"), list):
                continue
            
            json_count += 1
            client = data.get("client", "unknown")
            
            for ad in data["ads"]:
                ad_count += 1
                img_path = ad.get("image_path")
                if img_path:
                    referenced_images.add((client, img_path))
                    
                    # Check if file actually exists
                    full_path = ROOT / client / img_path
                    if not full_path.exists():
                        broken_refs.append({
                            "client": client,
                            "json": json_file.name,
                            "image_path": img_path
                        })
        except Exception as e:
            print(f"Error processing {json_file}: {e}")
    
    # Calculate differences
    orphaned = all_images - referenced_images
    mapped = all_images & referenced_images
    
    # Group by client
    orphaned_by_client = defaultdict(list)
    for client, path in orphaned:
        orphaned_by_client[client].append(path)
    
    mapped_by_client = defaultdict(int)
    for client, path in mapped:
        mapped_by_client[client] += 1
    
    # Report
    print("=" * 80)
    print("INSTACART IMAGE MAPPING AUDIT")
    print("=" * 80)
    print()
    print(f"📊 Summary:")
    print(f"  Total image files (excl. Main): {len(all_images)}")
    print(f"  Canonical JSON files: {json_count}")
    print(f"  Total ads in JSON: {ad_count}")
    print()
    print(f"✅ Mapped images (in JSON): {len(mapped)} ({len(mapped)/len(all_images)*100:.1f}%)")
    print(f"❌ Orphaned images (NOT in JSON): {len(orphaned)} ({len(orphaned)/len(all_images)*100:.1f}%)")
    print(f"⚠️  Broken references (JSON → missing file): {len(broken_refs)}")
    print()
    
    if orphaned:
        print("=" * 80)
        print("ORPHANED IMAGES BY CLIENT")
        print("=" * 80)
        for client in sorted(orphaned_by_client.keys()):
            paths = orphaned_by_client[client]
            print(f"\n{client}: {len(paths)} orphaned images")
            for path in sorted(paths)[:5]:  # Show first 5
                print(f"  - {path}")
            if len(paths) > 5:
                print(f"  ... and {len(paths) - 5} more")
    
    if broken_refs:
        print()
        print("=" * 80)
        print("BROKEN REFERENCES (JSON points to missing files)")
        print("=" * 80)
        for ref in broken_refs[:10]:  # Show first 10
            print(f"  {ref['client']}/{ref['json']}: {ref['image_path']}")
        if len(broken_refs) > 10:
            print(f"  ... and {len(broken_refs) - 10} more")
    
    print()
    print("=" * 80)
    print("MAPPED IMAGES BY CLIENT")
    print("=" * 80)
    for client in sorted(mapped_by_client.keys()):
        count = mapped_by_client[client]
        total = count + len(orphaned_by_client.get(client, []))
        pct = count / total * 100 if total > 0 else 0
        print(f"  {client}: {count}/{total} mapped ({pct:.1f}%)")
    
    print()
    print("=" * 80)
    print("NEXT STEPS")
    print("=" * 80)
    if orphaned:
        print("1. Orphaned images need to be either:")
        print("   a) Deleted (if truly obsolete)")
        print("   b) Mapped to canonical JSON (if they're valid ads)")
    if broken_refs:
        print("2. Broken references need to be fixed:")
        print("   a) Update image_path in JSON to correct filename")
        print("   b) Or remove the ad from JSON if image is truly missing")
    if not orphaned and not broken_refs:
        print("✅ All images are properly mapped to canonical JSON!")

if __name__ == "__main__":
    main()
