#!/usr/bin/env python3
"""
Validate Walmart canonical JSON schema.
Checks for: run_id, ads[], ISO timestamps, correct ad types, proper image paths.
"""
import json
import re
import glob
from pathlib import Path

def is_iso_with_tz(s):
    """Check if timestamp is ISO 8601 with timezone (Z or +/-HH:MM)"""
    return bool(re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+\-]\d{2}:\d{2})$', s))

def validate_walmart_json():
    # Pick the newest Walmart run JSON
    run_dirs = sorted(glob.glob('output/walmart/*/runs/*'))
    if not run_dirs:
        raise SystemExit("❌ No Walmart run dirs found. Did the scrape finish?")
    
    latest = run_dirs[-1]
    print(f"📁 Latest run dir: {latest}")
    
    candidates = sorted(Path(latest).glob('run_results_*.json'))
    if not candidates:
        raise SystemExit(f"❌ No run_results_*.json in {latest}")
    
    run_json = candidates[-1]
    print(f"📄 Validating: {run_json}")
    
    data = json.loads(run_json.read_text())
    
    # Top-level schema checks
    required_top = ['retailer', 'client', 'keyword', 'timestamp', 'run_id', 'ads']
    missing = [k for k in required_top if k not in data]
    if missing:
        raise SystemExit(f"❌ Missing top-level fields {missing} in {run_json}")
    
    print(f"✅ All required top-level fields present")
    
    if data['retailer'] != 'walmart':
        raise SystemExit(f"❌ retailer != 'walmart' ({data['retailer']}) in {run_json}")
    
    print(f"✅ retailer = 'walmart'")
    
    if not is_iso_with_tz(data['timestamp']):
        raise SystemExit(f"❌ Non-ISO timestamp (needs timezone) in {run_json}: {data['timestamp']}")
    
    print(f"✅ timestamp is ISO 8601 with timezone: {data['timestamp']}")
    
    if not data['run_id'].isdigit() or len(data['run_id']) != 14:
        raise SystemExit(f"❌ run_id not 14-digit timestamp in {run_json}: {data['run_id']}")
    
    print(f"✅ run_id is 14-digit timestamp: {data['run_id']}")
    
    ads = data['ads']
    print(f"📊 Found {len(ads)} ads in JSON")
    
    if len(ads) == 0:
        print("⚠️  WARNING: No ads captured. This is OK for initial test (ads_list not yet populated)")
        print("   Future enhancement will populate ads during capture")
        return
    
    allowed_types = {'SBA', 'SBV', 'Tile_Takeover'}
    bad_types = set()
    bad_paths = []
    
    for i, ad in enumerate(ads):
        t = ad.get('type')
        if t not in allowed_types:
            bad_types.add(t)
        
        img = ad.get('image_path') or ad.get('screenshot')
        if not img:
            raise SystemExit(f"❌ Ad {i} missing image_path/screenshot")
        
        if img.startswith('runs/'):
            bad_paths.append(img)
        
        # Ensure image_path starts with an allowed folder
        if not any(img.startswith(prefix + '/') for prefix in allowed_types.union({'Main'})):
            bad_paths.append(img)
    
    if bad_types:
        raise SystemExit(f"❌ Unexpected ad.type(s) {bad_types}")
    
    if bad_paths:
        raise SystemExit(f"❌ Misplaced images (should not be in runs/ and must start in SBA/SBV/Tile_Takeover/Main): {bad_paths[:5]}")
    
    print(f"✅ All ad types are valid: {allowed_types}")
    print(f"✅ All image paths are correctly placed")
    print("\n🎉 Walmart JSON schema and paths look good!")

if __name__ == "__main__":
    validate_walmart_json()
