#!/usr/bin/env python3
"""
Deduplicate Brand Logos

Scans the brand_logos directory and removes duplicate images based on content hash.
Updates the database to point to the deduplicated files.
"""

import os
import sys
import json
import hashlib
from pathlib import Path
from collections import defaultdict

def get_content_hash(filepath):
    """Get MD5 hash of file content"""
    with open(filepath, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()[:8]

def deduplicate_logos(base_dir):
    """Deduplicate logo files based on content hash"""
    # Check both possible locations
    logos_dir = Path(base_dir) / "output" / "brand_logos"
    if not logos_dir.exists():
        logos_dir = Path(base_dir) / "brand_logos"
    
    db_file = logos_dir / "brand_logo_database.json"
    
    if not logos_dir.exists():
        print(f"❌ Directory not found: {logos_dir}")
        print(f"   Tried: {Path(base_dir) / 'output' / 'brand_logos'}")
        print(f"   Tried: {Path(base_dir) / 'brand_logos'}")
        return
    
    # Load database
    if db_file.exists():
        with open(db_file, 'r', encoding='utf-8') as f:
            database = json.load(f)
    else:
        print(f"❌ Database not found: {db_file}")
        return
    
    # Scan all logo files (recursively) and group by content hash
    print("🔍 Scanning logo files...")
    hash_to_files = defaultdict(list)
    
    for filepath in logos_dir.rglob("*.*"):
        if filepath.name == "brand_logo_database.json" or not filepath.is_file():
            continue
        if filepath.suffix.lower().lstrip('.') not in ["png", "jpg", "jpeg", "gif", "webp"]:
            continue
        content_hash = get_content_hash(filepath)
        hash_to_files[content_hash].append(filepath)
    
    # Group files by brand and rename to clean numbered format
    print("\n🔄 Renaming to clean format...")
    brand_files = defaultdict(list)
    
    # Group by brand name (everything before hash or number)
    for filepath in logos_dir.rglob("*.*"):
        if filepath.name == "brand_logo_database.json" or not filepath.is_file():
            continue
        
        # Extract brand name (everything before _ or .)
        name_parts = filepath.stem.split('_')
        if len(name_parts) >= 2 and len(name_parts[-1]) == 8:
            # Has hash suffix - brand name is everything except last part
            brand_name = '_'.join(name_parts[:-1])
        else:
            # No hash - use full stem
            brand_name = filepath.stem
        
        brand_files[brand_name].append(filepath)
    
    # Process each brand
    files_renamed = 0
    files_removed = 0
    
    for brand_name, files in brand_files.items():
        if len(files) == 0:
            continue
        
        # Get content hashes to find duplicates
        file_hashes = {}
        for f in files:
            content_hash = get_content_hash(f)
            if content_hash not in file_hashes:
                file_hashes[content_hash] = []
            file_hashes[content_hash].append(f)
        
        # Get extension from first file
        ext = files[0].suffix
        
        # Rename unique files to clean format
        unique_files = []
        for content_hash, hash_files in file_hashes.items():
            # Keep first file, remove duplicates
            keeper = hash_files[0]
            unique_files.append(keeper)
            
            # Remove duplicates
            for dup in hash_files[1:]:
                print(f"   🗑️  Removing duplicate: {dup.name}")
                
                # Update database references
                for brand_key, brand_data in database["brands"].items():
                    if brand_data.get("logo_file", "").endswith(dup.name):
                        # Will be updated to new name below
                        pass
                
                dup.unlink()
                files_removed += 1
        
        # Rename to clean numbered format (preserve relative subdirectory)
        for idx, filepath in enumerate(unique_files, 1):
            if idx == 1:
                new_name = f"{brand_name}{ext}"
            else:
                new_name = f"{brand_name}_{idx}{ext}"

            new_path = filepath.parent / new_name
            # Compute relative path from logos_dir for DB storage
            rel_dir = filepath.parent.relative_to(logos_dir).as_posix()
            rel_path = f"{rel_dir}/{new_name}" if rel_dir != "." and rel_dir != "" else new_name
            
            if filepath.name != new_name:
                print(f"   📝 Renaming: {filepath.name} → {new_name}")
                
                # Update database references (normalize away any leading
                # brand_logos/ prefix and store path relative to logo root).
                for brand_key, brand_data in database["brands"].items():
                    lf = (brand_data.get("logo_file", "") or "").strip()
                    if lf.startswith("brand_logos/"):
                        lf_cmp = lf.split("/", 1)[1]
                    else:
                        lf_cmp = lf
                    if lf_cmp.endswith(filepath.name):
                        brand_data["logo_file"] = rel_path
                
                filepath.rename(new_path)
                files_renamed += 1
    
    print(f"\n📊 Summary:")
    print(f"   Files renamed: {files_renamed}")
    print(f"   Duplicates removed: {files_removed}")
    
    # Save updated database
    with open(db_file, 'w', encoding='utf-8') as f:
        json.dump(database, f, indent=2, ensure_ascii=False)
    print(f"   ✅ Database updated: {db_file}")

if __name__ == "__main__":
    # Get project root (parent of scripts directory)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    print(f"🔧 Deduplicating brand logos in: {project_root}")
    deduplicate_logos(project_root)
