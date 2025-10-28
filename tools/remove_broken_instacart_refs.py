#!/usr/bin/env python3
"""
Remove ads from canonical JSON that reference missing image files.
"""

import json
from pathlib import Path

ROOT = Path("output/instacart")

def main():
    removed_count = 0
    files_modified = 0
    
    for json_file in ROOT.rglob("run_results_*.json"):
        if "legacy_backup" in str(json_file):
            continue
        
        try:
            data = json.loads(json_file.read_text())
            if not isinstance(data.get("ads"), list):
                continue
            
            client = data.get("client", "unknown")
            original_count = len(data["ads"])
            
            # Filter out ads with missing image files
            valid_ads = []
            for ad in data["ads"]:
                img_path = ad.get("image_path")
                if img_path:
                    full_path = ROOT / client / img_path
                    if full_path.exists():
                        valid_ads.append(ad)
                    else:
                        print(f"Removing ad with missing image: {client}/{img_path}")
                        removed_count += 1
                else:
                    # Keep ads without image_path (shouldn't happen in canonical)
                    valid_ads.append(ad)
            
            # Update JSON if ads were removed
            if len(valid_ads) < original_count:
                data["ads"] = valid_ads
                json_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
                files_modified += 1
                print(f"  Updated {json_file.name}: {original_count} → {len(valid_ads)} ads")
        
        except Exception as e:
            print(f"Error processing {json_file}: {e}")
    
    print()
    print(f"✅ Removed {removed_count} broken ad references from {files_modified} JSON files")

if __name__ == "__main__":
    main()
