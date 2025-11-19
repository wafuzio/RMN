#!/usr/bin/env python3
"""
Repository consistency checker - audits schedules, outputs, folders, and brand logos.
Prints warnings only, does not modify anything.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ALLOWED = {
    "kroger": {"TOA", "Skyscraper", "Carousel", "Display_Ads", "Main", "runs"},
    "walmart": {"SBA", "SBV", "Tile_Takeover", "Main", "runs"},
    "instacart": {"Shoppable_Display_Ads", "Shoppable_Video_Ads", "Shoppable_Recipe_Ads", "Display_Ads", "Main", "runs"},
    "amazon": {"Sponsored_Brand", "Sponsored_Product", "Sponsored_Display", "Main", "runs"},
}

# ISO 8601 with timezone regex (rough check)
ISO_TZ = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+\-]\d{2}:\d{2})$")

def is_image(p: Path) -> bool:
    return p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}

def check_schedules():
    print("\n=== Checking Schedules ===")
    sched_dir = ROOT / "schedules"
    if not sched_dir.exists():
        print("WARN: schedules/ not found.")
        return
    
    for p in sched_dir.glob("*.json"):
        if p.name == "master_schedule.json":
            continue
        try:
            s = json.loads(p.read_text())
        except Exception as e:
            print(f"ERROR: Invalid JSON {p}: {e}")
            continue
        
        # Validate keywords (must be non-empty)
        if not s.get("keywords") or len(s["keywords"]) == 0:
            print(f"ERROR: {p.name} has empty keywords[] (minimum 1 required)")
        
        # Validate timestamps
        for tkey in ("created_at", "updated_at"):
            ts = s.get(tkey)
            if ts and not ISO_TZ.match(ts):
                print(f"ERROR: {p.name} {tkey} not ISO 8601 with TZ: {ts}")
        
        # Filename policy check (informational)
        parts = p.stem.split("__")
        if len(parts) < 3:
            print(f"WARN: Schedule filename not matching <retailer>__<client>__<keyword_slug>.json: {p.name}")

def check_outputs():
    print("\n=== Checking Output Directories ===")
    out = ROOT / "output"
    if not out.exists():
        print("INFO: output/ not found.")
        return
    
    for retailer_dir in out.iterdir():
        if not retailer_dir.is_dir():
            continue
        retailer = retailer_dir.name
        allowed = ALLOWED.get(retailer, set())
        if not allowed:
            continue
        
        for client_dir in retailer_dir.iterdir():
            if not client_dir.is_dir():
                continue
            
            for child in client_dir.iterdir():
                if child.is_dir():
                    # Check for disallowed folders
                    if child.name not in allowed:
                        # Special case: Walmart legacy folders
                        if retailer == "walmart" and child.name in {"Top_Banner", "Marquee_Banner"}:
                            print(f"WARN: Legacy Walmart folder (future ad type): {retailer}/{client_dir.name}/{child.name}")
                        else:
                            print(f"ERROR: Disallowed folder for {retailer}/{client_dir.name}: {child.name}")
                elif is_image(child) and client_dir.name == "runs":
                    print(f"ERROR: Image file in runs/: {child}")
            
            # Check images not in runs/
            runs_dir = client_dir / "runs"
            if runs_dir.exists():
                for f in runs_dir.glob("**/*"):
                    if is_image(f):
                        print(f"ERROR: Image found in runs/: {f}")
            
            # Check JSONs in runs for schema shape and timestamps
            # Only validate canonical run_results_*.json files, skip metadata and reports
            for run_json in (client_dir / "runs").glob("**/run_results_*.json"):
                try:
                    data = json.loads(run_json.read_text())
                except Exception as e:
                    print(f"ERROR: Invalid JSON {run_json}: {e}")
                    continue
                
                # Check required top-level fields
                for key in ("retailer", "keyword", "timestamp", "run_id", "ads"):
                    if key not in data:
                        print(f"ERROR: Missing {key} in {run_json}")
                
                # Check timestamp format
                ts = data.get("timestamp")
                if ts and not ISO_TZ.match(ts):
                    print(f"ERROR: Non-ISO timestamp in {run_json}: {ts}")
                
                # Per-ad checks
                for ad in data.get("ads", []):
                    if not (ad.get("image_path") or ad.get("screenshot")):
                        print(f"WARN: Ad missing image path fields in {run_json}")
                    
                    # Kroger CuratedCarousel -> Carousel mapping
                    if retailer == "kroger" and ad.get("type") == "CuratedCarousel":
                        pass  # expected; folder mapping is external
                    
                    # Warn on Walmart legacy ad types
                    if retailer == "walmart" and ad.get("type") in {"Top_Banner", "Marquee_Banner"}:
                        print(f"WARN: Walmart ad.type {ad.get('type')} found in {run_json} (future ad type, not yet implemented).")

def check_brand_logos():
    print("\n=== Checking Brand Logos ===")
    logos_dir = ROOT / "output" / "brand_logos"
    db_file = logos_dir / "brand_logo_database.json"
    front = logos_dir / "frontend_logos.json"
    
    if not logos_dir.exists():
        print("WARN: output/brand_logos/ not found.")
        return
    
    if not db_file.exists():
        print("WARN: brand_logos/brand_logo_database.json not found.")
    else:
        try:
            db = json.loads(db_file.read_text())
            # Spot check timestamps
            md = db.get("metadata", {})
            lu = md.get("last_updated")
            if lu and not ISO_TZ.match(lu):
                print(f"ERROR: brand_logo_database last_updated not ISO 8601 with TZ: {lu}")
            
            # Check brand entries
            for brand_key, brand_data in db.get("brands", {}).items():
                for ts_field in ("first_seen", "last_seen"):
                    ts = brand_data.get(ts_field)
                    if ts and not ISO_TZ.match(ts):
                        print(f"WARN: brand_logo_database brands.{brand_key}.{ts_field} not ISO 8601 with TZ: {ts}")
        except Exception as e:
            print(f"ERROR: Invalid brand_logo_database.json: {e}")
    
    if not front.exists():
        print("WARN: brand_logos/frontend_logos.json not found.")
    else:
        try:
            mapping = json.loads(front.read_text())
            for brand, path in mapping.items():
                if not path.startswith("brand_logos/"):
                    print(f"ERROR: frontend_logos path not rooted at brand_logos/: {brand} -> {path}")
                if not (ROOT / "output" / path).exists():
                    print(f"WARN: frontend logo path missing on disk: {path}")
        except Exception as e:
            print(f"ERROR: Invalid frontend_logos.json: {e}")

if __name__ == "__main__":
    print("Repository Consistency Check")
    print("=" * 50)
    check_schedules()
    check_outputs()
    check_brand_logos()
    print("\n" + "=" * 50)
    print("Done.")
