#!/usr/bin/env python3
"""
Walmart Readiness Doctor

Comprehensive health check for Walmart ad rendering in Builder.io.
Tests data integrity, API endpoints, and image resolution.

Usage:
    python3 tools/walmart_readiness_doctor.py
    python3 tools/walmart_readiness_doctor.py --client <client-name>
    python3 tools/walmart_readiness_doctor.py --fix  # Auto-fix issues
"""
import os
import sys
import json
import glob
import argparse
import requests
from pathlib import Path
from collections import defaultdict

PROJECT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT / "output" / "walmart"


class Color:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_header(text):
    print(f"\n{Color.BOLD}{Color.BLUE}{'=' * 80}{Color.END}")
    print(f"{Color.BOLD}{Color.BLUE}{text.center(80)}{Color.END}")
    print(f"{Color.BOLD}{Color.BLUE}{'=' * 80}{Color.END}\n")


def print_section(text):
    print(f"\n{Color.BOLD}{text}{Color.END}")
    print("-" * 80)


def print_ok(text):
    print(f"{Color.GREEN}✅ {text}{Color.END}")


def print_warn(text):
    print(f"{Color.YELLOW}⚠️  {text}{Color.END}")


def print_error(text):
    print(f"{Color.RED}❌ {text}{Color.END}")


def check_servers():
    """Check if Flask, Vite, and ngrok are running"""
    print_section("Step 0: Server Status")
    
    issues = []
    
    # Check Flask
    try:
        resp = requests.get("http://localhost:5006/health", timeout=2)
        if resp.status_code == 200:
            print_ok("Flask API running on port 5006")
        else:
            print_error(f"Flask API returned {resp.status_code}")
            issues.append("flask_error")
    except Exception as e:
        print_error(f"Flask API not responding: {e}")
        issues.append("flask_down")
    
    # Check Vite
    try:
        resp = requests.get("http://localhost:3000", timeout=2)
        print_ok("Vite dev server running on port 3000")
    except Exception:
        try:
            resp = requests.get("http://localhost:3001", timeout=2)
            print_ok("Vite dev server running on port 3001")
        except Exception as e:
            print_error(f"Vite dev server not responding: {e}")
            issues.append("vite_down")
    
    # Check ngrok
    try:
        resp = requests.get("http://localhost:4040/api/tunnels", timeout=2)
        tunnels = resp.json()
        public_url = None
        for tunnel in tunnels.get("tunnels", []):
            if tunnel.get("proto") == "https":
                public_url = tunnel.get("public_url")
                break
        
        if public_url:
            print_ok(f"ngrok tunnel active: {public_url}")
            return issues, public_url
        else:
            print_error("ngrok running but no HTTPS tunnel found")
            issues.append("ngrok_no_tunnel")
    except Exception as e:
        print_error(f"ngrok not responding: {e}")
        issues.append("ngrok_down")
    
    return issues, None


def check_data_integrity(client=None):
    """Check Walmart JSON data integrity"""
    print_section("Step 1: Data Integrity")
    
    if not OUTPUT_DIR.exists():
        print_error(f"Walmart output directory not found: {OUTPUT_DIR}")
        return {"critical": True}
    
    clients = [client] if client else [d.name for d in OUTPUT_DIR.iterdir() if d.is_dir()]
    
    stats = {
        "total_ads": 0,
        "ads_with_image_path": 0,
        "ads_missing_image_path": 0,
        "ads_with_missing_files": 0,
        "clients_checked": 0,
        "issues": []
    }
    
    for client_name in clients:
        client_dir = OUTPUT_DIR / client_name
        runs_dir = client_dir / "runs"
        
        if not runs_dir.exists():
            continue
        
        stats["clients_checked"] += 1
        
        # Find all run JSONs (both flat and nested)
        json_files = []
        json_files.extend(runs_dir.glob("run_results_*.json"))
        for run_dir in runs_dir.iterdir():
            if run_dir.is_dir():
                json_files.extend(run_dir.glob("run_results_*.json"))
        
        for json_file in json_files:
            try:
                data = json.loads(json_file.read_text())
                ads = data.get("ads", [])
                
                for ad in ads:
                    stats["total_ads"] += 1
                    
                    image_path = ad.get("image_path")
                    if image_path:
                        stats["ads_with_image_path"] += 1
                        
                        # Check if file exists
                        full_path = client_dir / image_path
                        if not full_path.exists():
                            stats["ads_with_missing_files"] += 1
                            stats["issues"].append({
                                "client": client_name,
                                "json": json_file.name,
                                "ad_id": ad.get("id"),
                                "image_path": image_path,
                                "issue": "file_missing"
                            })
                    else:
                        stats["ads_missing_image_path"] += 1
                        stats["issues"].append({
                            "client": client_name,
                            "json": json_file.name,
                            "ad_id": ad.get("id"),
                            "ad_type": ad.get("type"),
                            "issue": "no_image_path"
                        })
            except Exception as e:
                print_error(f"Error reading {json_file}: {e}")
    
    # Print summary
    print(f"\nClients checked: {stats['clients_checked']}")
    print(f"Total ads: {stats['total_ads']}")
    
    if stats['total_ads'] == 0:
        print_error("No Walmart ads found!")
        return stats
    
    coverage = (stats['ads_with_image_path'] / stats['total_ads']) * 100
    
    print(f"\nImage path coverage: {stats['ads_with_image_path']}/{stats['total_ads']} ({coverage:.1f}%)")
    
    if coverage >= 95:
        print_ok("Excellent coverage!")
    elif coverage >= 80:
        print_warn("Good coverage, but some ads missing image_path")
    else:
        print_error("Poor coverage - many ads missing image_path")
    
    if stats['ads_with_missing_files'] > 0:
        print_error(f"{stats['ads_with_missing_files']} ads have image_path but file doesn't exist")
    
    return stats


def check_api_endpoints(ngrok_url):
    """Check API endpoints are working"""
    print_section("Step 2: API Endpoints")
    
    if not ngrok_url:
        print_error("No ngrok URL - skipping API checks")
        return {"skipped": True}
    
    issues = []
    
    # Check /api/retailers
    try:
        resp = requests.get(
            f"{ngrok_url}/api/retailers",
            headers={"ngrok-skip-browser-warning": "true"},
            timeout=5
        )
        if resp.status_code == 200:
            data = resp.json()
            retailers = data.get("retailers", [])
            if "walmart" in retailers:
                print_ok("/api/retailers includes walmart")
            else:
                print_error("/api/retailers missing walmart")
                issues.append("walmart_not_in_retailers")
        else:
            print_error(f"/api/retailers returned {resp.status_code}")
            issues.append("retailers_error")
    except Exception as e:
        print_error(f"/api/retailers failed: {e}")
        issues.append("retailers_failed")
    
    # Check /api/clients for walmart
    try:
        resp = requests.get(
            f"{ngrok_url}/api/clients?retailer=walmart",
            headers={"ngrok-skip-browser-warning": "true"},
            timeout=5
        )
        if resp.status_code == 200:
            clients = resp.json()
            if clients:
                print_ok(f"/api/clients found {len(clients)} Walmart clients")
                
                # Test /api/ads/cards for first client
                test_client = clients[0]
                resp = requests.get(
                    f"{ngrok_url}/api/ads/cards?retailer=walmart&client={test_client}&page_size=5",
                    headers={"ngrok-skip-browser-warning": "true"},
                    timeout=10
                )
                if resp.status_code == 200:
                    data = resp.json()
                    cards = data.get("cards", [])
                    print_ok(f"/api/ads/cards returned {len(cards)} cards for {test_client}")
                    
                    # Check if cards have image_url
                    cards_with_images = sum(1 for c in cards if c.get("image_url"))
                    if cards_with_images == len(cards):
                        print_ok(f"All {len(cards)} cards have image_url")
                    else:
                        print_warn(f"Only {cards_with_images}/{len(cards)} cards have image_url")
                        issues.append("cards_missing_image_url")
                    
                    # Test image endpoint
                    if cards and cards[0].get("image_url"):
                        image_url = cards[0]["image_url"]
                        resp = requests.get(
                            f"{ngrok_url}{image_url}",
                            headers={"ngrok-skip-browser-warning": "true"},
                            timeout=5
                        )
                        if resp.status_code == 200:
                            print_ok(f"/api/image endpoint working (tested: {image_url})")
                        else:
                            print_error(f"/api/image returned {resp.status_code} for {image_url}")
                            issues.append("image_endpoint_error")
                else:
                    print_error(f"/api/ads/cards returned {resp.status_code}")
                    issues.append("cards_error")
            else:
                print_error("/api/clients returned empty list for walmart")
                issues.append("no_clients")
        else:
            print_error(f"/api/clients returned {resp.status_code}")
            issues.append("clients_error")
    except Exception as e:
        print_error(f"API check failed: {e}")
        issues.append("api_failed")
    
    return {"issues": issues}


def check_taxonomy_compliance():
    """Check taxonomy compliance"""
    print_section("Step 3: Taxonomy Compliance")
    
    # Run audit tool
    audit_script = PROJECT / "tools" / "audit_adtype_mapping.py"
    if not audit_script.exists():
        print_warn("audit_adtype_mapping.py not found - skipping")
        return {"skipped": True}
    
    import subprocess
    try:
        result = subprocess.run(
            [sys.executable, str(audit_script)],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        # Parse output for Walmart lines
        walmart_lines = [line for line in result.stdout.split('\n') if 'walmart/' in line.lower()]
        
        if walmart_lines:
            print("\nWalmart taxonomy audit:")
            for line in walmart_lines:
                if "OK" in line and "Image exists" in line:
                    print_ok(line.strip())
                elif "FAIL" in line or "MISSING" in line:
                    print_error(line.strip())
                else:
                    print(line.strip())
        else:
            print_warn("No Walmart entries in audit output")
        
        return {"output": walmart_lines}
    except Exception as e:
        print_error(f"Audit failed: {e}")
        return {"error": str(e)}


def print_recommendations(data_stats, api_results):
    """Print actionable recommendations"""
    print_header("RECOMMENDATIONS")
    
    if data_stats.get("critical"):
        print_error("CRITICAL: Walmart output directory not found")
        print("\n  Run a Walmart scrape first:")
        print("  python3 walmart_search_and_capture.py 'test' --output-dir output/walmart/test_client")
        return
    
    if data_stats.get("total_ads", 0) == 0:
        print_error("No Walmart ads found in any client")
        print("\n  Run a Walmart scrape first:")
        print("  python3 walmart_search_and_capture.py 'test' --output-dir output/walmart/test_client")
        return
    
    coverage = (data_stats.get("ads_with_image_path", 0) / data_stats.get("total_ads", 1)) * 100
    
    if coverage < 95:
        print_warn(f"Image path coverage is {coverage:.1f}% (target: 95%+)")
        print("\n  Fix missing image_path fields:")
        print("  1. Rebuild runs from orphan images:")
        print("     python3 tools/batch_rebuild_walmart_runs_from_images.py --write --backup")
        print("\n  2. Reconcile remaining ads:")
        print("     python3 tools/reconcile_walmart_images_to_json.py --write --backup --min-score 6")
        print("\n  3. Re-run this doctor:")
        print("     python3 tools/walmart_readiness_doctor.py")
    
    if data_stats.get("ads_with_missing_files", 0) > 0:
        print_error(f"{data_stats['ads_with_missing_files']} ads have image_path but file missing")
        print("\n  This indicates orphaned JSON entries. Options:")
        print("  1. Delete orphaned entries (recommended)")
        print("  2. Re-run scraper to regenerate images")
    
    if api_results.get("issues"):
        print_warn("API issues detected:")
        for issue in api_results["issues"]:
            print(f"  - {issue}")
        print("\n  Restart servers:")
        print("  ./restart_servers.sh")
    
    if coverage >= 95 and not data_stats.get("ads_with_missing_files") and not api_results.get("issues"):
        print_ok("ALL CHECKS PASSED!")
        print("\n  Your Walmart ads are ready for Builder.io!")
        print("\n  Next steps:")
        print("  1. Open Builder.io")
        print("  2. Create a new page")
        print("  3. Add Custom Code block")
        print("  4. Fetch ads from your ngrok URL")
        print("  5. Display images using the image_url field")


def main():
    parser = argparse.ArgumentParser(description="Walmart Builder.io Readiness Doctor")
    parser.add_argument("--client", help="Check specific client only")
    parser.add_argument("--fix", action="store_true", help="Auto-fix issues (runs rebuild/reconcile)")
    args = parser.parse_args()
    
    print_header("WALMART BUILDER.IO READINESS DOCTOR")
    
    # Step 0: Check servers
    server_issues, ngrok_url = check_servers()
    
    if "flask_down" in server_issues or "vite_down" in server_issues:
        print_error("\nServers not running! Start them first:")
        print("  ./restart_servers.sh")
        sys.exit(1)
    
    if not ngrok_url:
        print_warn("\nngrok URL not detected - API checks will be limited")
    
    # Step 1: Check data
    data_stats = check_data_integrity(args.client)
    
    # Step 2: Check API
    api_results = check_api_endpoints(ngrok_url) if ngrok_url else {"skipped": True}
    
    # Step 3: Check taxonomy
    taxonomy_results = check_taxonomy_compliance()
    
    # Print recommendations
    print_recommendations(data_stats, api_results)
    
    # Auto-fix if requested
    if args.fix:
        print_header("AUTO-FIX MODE")
        coverage = (data_stats.get("ads_with_image_path", 0) / data_stats.get("total_ads", 1)) * 100
        
        if coverage < 95:
            print("Running rebuild...")
            import subprocess
            subprocess.run([
                sys.executable,
                str(PROJECT / "tools" / "batch_rebuild_walmart_runs_from_images.py"),
                "--write", "--backup"
            ])
            
            print("\nRunning reconcile...")
            subprocess.run([
                sys.executable,
                str(PROJECT / "tools" / "reconcile_walmart_images_to_json.py"),
                "--write", "--backup", "--min-score", "6"
            ])
            
            print("\nRe-running doctor...")
            subprocess.run([sys.executable, __file__])


if __name__ == "__main__":
    main()
