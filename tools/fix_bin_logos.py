#!/usr/bin/env python3
"""
Fix .bin logo files by detecting their actual image type and renaming them.

Also updates the brand_logo_database.json to reflect the new filenames.
"""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOGOS_DIR = PROJECT_ROOT / "output" / "brand_logos"
LOGOS_DB = LOGOS_DIR / "brand_logo_database.json"


def detect_image_type(filepath: Path) -> str:
    """Detect image type from magic bytes (file signature)"""
    content = filepath.read_bytes()
    if content[:8] == b'\x89PNG\r\n\x1a\n':
        return 'png'
    elif content[:3] == b'\xff\xd8\xff':
        return 'jpg'
    elif content[:6] in (b'GIF87a', b'GIF89a'):
        return 'gif'
    elif content[:4] == b'RIFF' and content[8:12] == b'WEBP':
        return 'webp'
    elif content[:4] == b'<svg' or b'<svg' in content[:100]:
        return 'svg'
    return None


def main():
    # Find all .bin files
    bin_files = list(LOGOS_DIR.rglob("*.bin"))
    
    if not bin_files:
        print("✓ No .bin files found")
        return
    
    print(f"Found {len(bin_files)} .bin files to fix\n")
    
    # Load database
    db = {}
    if LOGOS_DB.exists():
        db = json.loads(LOGOS_DB.read_text())
    
    renamed = 0
    failed = 0
    
    for bin_file in bin_files:
        actual_type = detect_image_type(bin_file)
        
        if actual_type is None:
            print(f"⚠️  Could not detect type: {bin_file.name}")
            failed += 1
            continue
        
        # New filename with correct extension
        new_name = bin_file.stem + "." + actual_type
        new_path = bin_file.parent / new_name
        
        # Check for conflicts
        if new_path.exists():
            print(f"⚠️  Target exists, skipping: {bin_file.name} -> {new_name}")
            failed += 1
            continue
        
        # Rename file
        bin_file.rename(new_path)
        print(f"✓ {bin_file.name} -> {new_name} ({actual_type})")
        renamed += 1
        
        # Update database if needed
        old_rel = str(bin_file.relative_to(LOGOS_DIR))
        new_rel = str(new_path.relative_to(LOGOS_DIR))
        
        for brand_key, brand_data in db.get("brands", {}).items():
            logo_file = brand_data.get("logo_file", "")
            if logo_file == old_rel or logo_file == f"brand_logos/{old_rel}":
                brand_data["logo_file"] = new_rel
                print(f"   Updated DB: {brand_key}")
    
    # Save database
    if renamed > 0 and db:
        from datetime import datetime, timezone
        db["metadata"] = db.get("metadata", {})
        db["metadata"]["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        LOGOS_DB.write_text(json.dumps(db, indent=2, ensure_ascii=False))
        print(f"\n💾 Database saved")
    
    print(f"\n📊 Summary: {renamed} renamed, {failed} failed")


if __name__ == "__main__":
    main()
