#!/usr/bin/env python3
"""
Create canonical JSON files for orphaned Walmart images.
Matches images by timestamp and creates run_results_*.json files.
"""
import argparse
import json
import re
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
from typing import Dict, List, Any

ROOT = Path(__file__).resolve().parents[1]
WALMART_ROOT = ROOT / "output" / "walmart"

# Filename pattern: walmart__brand__adtype__client__keyword__DYYYY-MM-DD_THH-MM.SS_index.png
FILENAME_PATTERN = re.compile(
    r"walmart__(?P<brand>[^_]+)__(?P<adtype>[^_]+)__(?P<client>[^_]+)__(?P<keyword>.+?)__D(?P<date>\d{4}-\d{2}-\d{2})_T(?P<time>\d{2}-\d{2}\.\d{2})_(?P<idx>\d+)\.png"
)

# Ad type normalization
ADTYPE_MAP = {
    "sba": "SBA",
    "sbv": "SBV",
    "tile_takeover": "Tile_Takeover",
}

def get_orphaned_images() -> Dict[tuple, List[Dict]]:
    """Find all images not referenced in canonical JSONs, grouped by run."""
    
    # Get all images
    all_images = {}
    for folder in ["SBA", "SBV", "Tile_Takeover"]:
        for img in WALMART_ROOT.glob(f"*/{folder}/*.png"):
            client = img.parts[len(WALMART_ROOT.parts)]
            rel_path = str(img.relative_to(WALMART_ROOT / client))
            all_images[(client, rel_path)] = img
    
    # Get referenced images
    referenced = set()
    for json_file in WALMART_ROOT.glob("*/runs/*/run_results_*.json"):
        try:
            data = json.loads(json_file.read_text())
            client = data.get("client")
            if isinstance(data.get("ads"), list):
                for ad in data["ads"]:
                    img_path = ad.get("image_path")
                    if img_path and client:
                        referenced.add((client, img_path))
        except:
            pass
    
    # Find orphans
    orphaned = {k: v for k, v in all_images.items() if k not in referenced}
    
    # Group by run (client + timestamp)
    runs = defaultdict(list)
    for (client, rel_path), img_file in orphaned.items():
        match = FILENAME_PATTERN.match(img_file.name)
        if match:
            brand = match.group("brand")
            adtype = match.group("adtype")
            keyword = match.group("keyword")
            date = match.group("date")
            time = match.group("time")
            idx = match.group("idx")
            
            # Normalize
            brand_clean = brand.replace("_", " ").title() if brand != "unknown" else None
            adtype_clean = ADTYPE_MAP.get(adtype, adtype)
            keyword_clean = keyword.replace("_", " ")
            
            # Create timestamp for grouping
            time_clean = time.replace(".", ":")
            timestamp_iso = f"{date}T{time_clean}Z"
            run_id = date.replace("-", "") + time.replace("-", "").replace(".", "")
            
            run_key = (client, run_id, keyword_clean)
            
            runs[run_key].append({
                "brand": brand_clean,
                "type": adtype_clean,
                "image_path": rel_path,
                "idx": int(idx),
                "timestamp": timestamp_iso,
            })
    
    return runs

def create_canonical_json(client: str, run_id: str, keyword: str, ads: List[Dict], write: bool) -> Path:
    """Create canonical JSON for a run."""
    
    # Use first ad's timestamp
    timestamp = ads[0]["timestamp"]
    
    # Build canonical payload
    payload = {
        "retailer": "walmart",
        "client": client,
        "keyword": keyword,
        "timestamp": timestamp,
        "run_id": run_id,
        "ads": []
    }
    
    # Build ad objects
    for i, ad_data in enumerate(sorted(ads, key=lambda x: (x["type"], x["idx"])), 1):
        ad_obj = {
            "id": f"walmart-{run_id}-{i}",
            "type": ad_data["type"],
            "brand": ad_data["brand"],
            "brand_logo": None,
            "title": None,
            "description": None,
            "cta": None,
            "href": None,
            "image_url": None,
            "image_path": ad_data["image_path"],
            "products": [],
            "metadata": {
                "slot": ad_data["idx"] - 1,
                "note": "recovered_from_orphaned_image"
            }
        }
        payload["ads"].append(ad_obj)
    
    # Create run directory
    client_dir = WALMART_ROOT / client
    run_dir = client_dir / "runs" / run_id
    
    if write:
        run_dir.mkdir(parents=True, exist_ok=True)
        json_file = run_dir / f"run_results_{run_id}.json"
        json_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        return json_file
    else:
        return run_dir / f"run_results_{run_id}.json"

def main():
    ap = argparse.ArgumentParser(description="Create canonical JSONs for orphaned Walmart images")
    ap.add_argument("--write", action="store_true", help="Write JSON files (default is --write)")
    ap.add_argument("--limit", type=int, default=0, help="Limit number of runs to process (0=all)")
    args = ap.parse_args()
    
    print("🔍 Finding orphaned images...")
    runs = get_orphaned_images()
    
    print(f"📊 Found {sum(len(ads) for ads in runs.values())} orphaned images")
    print(f"📦 Grouped into {len(runs)} runs\n")
    
    if not runs:
        print("✅ No orphaned images found!")
        return
    
    created = 0
    for (client, run_id, keyword), ads in sorted(runs.items()):
        json_path = create_canonical_json(client, run_id, keyword, ads, write=args.write)
        
        if args.write:
            print(f"✅ Created: {json_path.relative_to(WALMART_ROOT)} ({len(ads)} ads)")
        else:
            print(f"✅ Created: {json_path.relative_to(WALMART_ROOT)} ({len(ads)} ads)")
        
        created += 1
        if args.limit and created >= args.limit:
            break
    
    print(f"\n📊 Total: {created} runs, mode={'WRITE' if args.write else 'DRY-RUN'}")

if __name__ == "__main__":
    main()
