#!/usr/bin/env python3
"""
Walmart Frontend Readiness Doctor

Checks JSONs, image_path coverage, and whether the API can resolve image URLs
for a sample of Walmart ads.

Usage:
    python3 tools/doctor_walmart_frontend.py
    API_BASE=https://<your-ngrok>.ngrok-free.dev python3 tools/doctor_walmart_frontend.py
"""
import json
import glob
import os
import random
from pathlib import Path
import requests

SCRAPER_HOME = os.environ.get("SCRAPER_HOME") or str(Path(__file__).resolve().parents[1])
API = os.environ.get("API_BASE") or "http://localhost:5006"


def walmart_clients():
    """Get list of Walmart clients"""
    root = Path(SCRAPER_HOME) / "output" / "walmart"
    if not root.exists():
        return []
    return [p.name for p in root.iterdir() if p.is_dir()]


def run_jsons(client):
    """Get all run JSON files for a client (flat + nested)"""
    cr = Path(SCRAPER_HOME) / "output" / "walmart" / client / "runs"
    if not cr.exists():
        return []
    # nested + flat
    nested = sorted(glob.glob(str(cr / "*" / "run_results_*.json")))
    flat = sorted(glob.glob(str(cr / "run_results_*.json")))
    return nested + flat


def main():
    print("=" * 80)
    print("WALMART FRONTEND READINESS DOCTOR")
    print("=" * 80)
    print(f"\nAPI Base: {API}")
    print(f"Scraper Home: {SCRAPER_HOME}\n")
    
    clients = walmart_clients()
    
    if not clients:
        print("❌ No Walmart clients found!")
        print(f"   Expected directory: {Path(SCRAPER_HOME) / 'output' / 'walmart'}")
        return
    
    print(f"Found {len(clients)} Walmart client(s)\n")
    
    total_clients = 0
    total_ads = 0
    total_with_path = 0
    total_resolvable = 0
    total_probed = 0
    
    for client in clients:
        total_clients += 1
        jsons = run_jsons(client)
        
        if not jsons:
            print(f"⚠️  [{client}] No run JSONs found")
            continue
        
        ads_total = 0
        has_path = 0
        resolvable = 0
        samples = []
        
        for j in jsons:
            try:
                data = json.loads(Path(j).read_text())
                ads = data.get("ads") or []
                
                for ad in ads:
                    ads_total += 1
                    
                    # Check for image_path (canonical or legacy)
                    rel = ad.get("image_path") or ad.get("screenshot")
                    if not rel:
                        # Check legacy fallbacks
                        for k, v in ad.items():
                            if isinstance(k, str) and k.endswith("_image_path") and isinstance(v, str) and v:
                                rel = v
                                break
                    
                    if rel:
                        has_path += 1
                    
                    # Collect samples for API probing
                    if len(samples) < 10:
                        samples.append((client, rel, ad))
            except Exception as e:
                print(f"❌ Error reading {j}: {e}")
        
        # Calculate coverage
        coverage = (has_path / max(1, ads_total)) * 100
        
        # Print client summary
        status = "✅" if coverage >= 95 else "⚠️" if coverage >= 80 else "❌"
        print(f"{status} [{client}] ads={ads_total} with_image_path={has_path} ({coverage:.0f}%)")
        
        total_ads += ads_total
        total_with_path += has_path
        
        # API probe small sample
        if samples:
            probe_count = 0
            for (client, rel, ad) in samples:
                if not rel:
                    continue
                
                url = f"{API}/api/image/walmart/{client}/{rel}"
                try:
                    r = requests.get(url, timeout=5, headers={"ngrok-skip-browser-warning": "true"})
                    if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
                        resolvable += 1
                except Exception:
                    pass
                probe_count += 1
                total_probed += 1
            
            if probe_count:
                probe_pct = (resolvable / probe_count) * 100
                probe_status = "✅" if probe_pct >= 90 else "⚠️" if probe_pct >= 70 else "❌"
                print(f"    {probe_status} API resolvable (sample): {resolvable}/{probe_count} ({probe_pct:.0f}%)")
                total_resolvable += resolvable
    
    # Overall summary
    print("\n" + "=" * 80)
    print("OVERALL SUMMARY")
    print("=" * 80)
    
    if total_ads == 0:
        print("❌ No Walmart ads found across all clients")
        return
    
    overall_coverage = (total_with_path / total_ads) * 100
    print(f"\nTotal clients: {total_clients}")
    print(f"Total ads: {total_ads}")
    print(f"Ads with image_path: {total_with_path} ({overall_coverage:.1f}%)")
    
    if total_probed > 0:
        overall_resolvable = (total_resolvable / total_probed) * 100
        print(f"API resolvable (sampled): {total_resolvable}/{total_probed} ({overall_resolvable:.1f}%)")
    
    print("\n" + "=" * 80)
    print("RECOMMENDATIONS")
    print("=" * 80)
    
    if overall_coverage < 95:
        print("\n❌ Image path coverage below 95%")
        print("\n   Fix missing image_path fields:")
        print("   1. Rebuild runs from orphan images:")
        print("      python3 tools/batch_rebuild_walmart_runs_from_images.py --write --backup")
        print("\n   2. Reconcile remaining ads:")
        print("      python3 tools/reconcile_walmart_images_to_json.py --write --backup --min-score 6")
        print("\n   3. Re-run this doctor:")
        print("      python3 tools/doctor_walmart_frontend.py")
    elif total_probed > 0 and overall_resolvable < 90:
        print("\n⚠️  Image paths exist but API can't resolve them")
        print("\n   Check:")
        print("   1. Flask API is running: curl http://localhost:5006/health")
        print("   2. Image files exist on disk")
        print("   3. Restart servers: ./restart_servers.sh")
    else:
        print("\n✅ ALL CHECKS PASSED!")
        print("\n   Your Walmart ads are ready for Builder.io!")
        print("\n   Next steps:")
        print("   1. Open Builder.io")
        print("   2. Create a new page")
        print("   3. Add Custom Code block")
        print(f"   4. Fetch ads from: {API}/api/ads/cards?retailer=walmart&client=<client>&page_size=24")
        print("   5. Display images using the image_url field")


if __name__ == "__main__":
    main()
