#!/usr/bin/env python3
"""
Instacart Readiness Doctor

Comprehensive health check for Instacart Builder.io integration:
- Server status (Flask, Vite, ngrok)
- Authentication profile setup
- Data integrity (canonical schema, image paths)
- API endpoint verification
- Canonical schema compliance

Usage:
    python3 tools/instacart_readiness_doctor.py [--client CLIENT] [--auto-fix]
"""

import os
import sys
import json
import requests
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

# Colors for output
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
RED = '\033[0;31m'
BLUE = '\033[0;34m'
NC = '\033[0m'  # No Color

def print_header(text):
    print(f"\n{BLUE}{'=' * 80}{NC}")
    print(f"{BLUE}{text.center(80)}{NC}")
    print(f"{BLUE}{'=' * 80}{NC}\n")

def print_check(name, passed, details=""):
    status = f"{GREEN}✅ PASS{NC}" if passed else f"{RED}❌ FAIL{NC}"
    print(f"{status} {name}")
    if details:
        print(f"     {details}")

def print_warning(text):
    print(f"{YELLOW}⚠️  {text}{NC}")

def print_info(text):
    print(f"     {text}")

class InstacartReadinessDoctor:
    def __init__(self, client=None, auto_fix=False):
        self.client = client
        self.auto_fix = auto_fix
        self.output_root = project_root / "output" / "instacart"
        self.issues = []
        self.warnings = []
        
    def check_servers(self):
        """Check if Flask and Vite servers are running"""
        print_header("SERVER STATUS")
        
        # Check Flask (port 5006)
        try:
            response = requests.get("http://localhost:5006/api/retailers", timeout=2)
            flask_running = response.status_code == 200
            print_check("Flask server (port 5006)", flask_running)
            if not flask_running:
                self.issues.append("Flask server not responding")
        except Exception as e:
            print_check("Flask server (port 5006)", False, str(e))
            self.issues.append("Flask server not running")
        
        # Check Vite (port 8080)
        try:
            response = requests.get("http://localhost:8080", timeout=2)
            vite_running = response.status_code == 200
            print_check("Vite dev server (port 8080)", vite_running)
            if not vite_running:
                self.warnings.append("Vite dev server not running (optional for API testing)")
        except Exception:
            print_check("Vite dev server (port 8080)", False, "Not running (optional)")
        
        # Check ngrok (optional)
        try:
            response = requests.get("http://localhost:4040/api/tunnels", timeout=2)
            if response.status_code == 200:
                tunnels = response.json().get('tunnels', [])
                if tunnels:
                    public_url = tunnels[0].get('public_url', 'N/A')
                    print_check("ngrok tunnel", True, f"Public URL: {public_url}")
                else:
                    print_check("ngrok tunnel", False, "No active tunnels")
            else:
                print_check("ngrok tunnel", False, "Not running (optional)")
        except Exception:
            print_check("ngrok tunnel", False, "Not running (optional)")
    
    def check_authentication(self):
        """Check Instacart authentication profile"""
        print_header("AUTHENTICATION")
        
        profile_dir = os.environ.get('INSTACART_PROFILE_DIR')
        
        if not profile_dir:
            print_check("INSTACART_PROFILE_DIR env var", False, "Not set")
            self.issues.append("INSTACART_PROFILE_DIR environment variable not set")
            print_info("Set with: export INSTACART_PROFILE_DIR=~/ChromeProfiles/instacart")
            return
        
        print_check("INSTACART_PROFILE_DIR env var", True, profile_dir)
        
        profile_path = Path(profile_dir).expanduser()
        if profile_path.exists():
            print_check("Profile directory exists", True, str(profile_path))
            
            # Check for session data
            default_dir = profile_path / "Default"
            if default_dir.exists():
                cookies = default_dir / "Cookies"
                if cookies.exists():
                    print_check("Session cookies found", True)
                else:
                    print_warning("No cookies found - may need to login")
                    self.warnings.append("No session cookies - authentication may be required")
            else:
                print_warning("No Default profile - may need initial setup")
        else:
            print_check("Profile directory exists", False, str(profile_path))
            self.issues.append(f"Profile directory does not exist: {profile_path}")
            print_info("Run: ./scripts/setup_instacart_profile.sh")
    
    def check_data_integrity(self):
        """Check Instacart data integrity and canonical schema compliance"""
        print_header("DATA INTEGRITY")
        
        if not self.output_root.exists():
            print_check("Instacart output directory", False, str(self.output_root))
            self.issues.append("Instacart output directory does not exist")
            return
        
        print_check("Instacart output directory", True, str(self.output_root))
        
        # Get clients to check
        clients = []
        if self.client:
            client_dir = self.output_root / self.client
            if client_dir.exists():
                clients = [client_dir]
            else:
                print_check(f"Client '{self.client}'", False, "Not found")
                return
        else:
            clients = [d for d in self.output_root.iterdir() if d.is_dir()]
        
        if not clients:
            print_warning("No client directories found")
            return
        
        print_info(f"Checking {len(clients)} client(s)...")
        
        total_runs = 0
        canonical_runs = 0
        legacy_runs = 0
        total_ads = 0
        ads_with_images = 0
        
        for client_dir in clients:
            runs_dir = client_dir / "runs"
            if not runs_dir.exists():
                continue
            
            json_files = list(runs_dir.glob("run_results_*.json")) + \
                        list(runs_dir.glob("*/run_results_*.json"))
            
            for json_file in json_files:
                total_runs += 1
                try:
                    data = json.loads(json_file.read_text())
                    
                    # Check if canonical
                    if isinstance(data.get("ads"), list):
                        canonical_runs += 1
                        ads = data["ads"]
                        
                        # Check canonical fields
                        has_run_id = bool(data.get("run_id"))
                        has_iso_timestamp = "T" in str(data.get("timestamp", "")) and "Z" in str(data.get("timestamp", ""))
                        
                        if not has_run_id:
                            self.warnings.append(f"Missing run_id: {json_file.name}")
                        if not has_iso_timestamp:
                            self.warnings.append(f"Non-ISO timestamp: {json_file.name}")
                        
                        # Check ads
                        for ad in ads:
                            total_ads += 1
                            if ad.get("image_path"):
                                ads_with_images += 1
                    else:
                        legacy_runs += 1
                        # Legacy structure
                        results = data.get("results", [])
                        for r in results:
                            if isinstance(r, dict):
                                ads = r.get("ads", [])
                                total_ads += len(ads)
                                ads_with_images += sum(1 for ad in ads if ad.get("screenshot") or ad.get("image_path"))
                
                except Exception as e:
                    self.warnings.append(f"Could not read {json_file.name}: {e}")
        
        # Print results
        print_info(f"Total runs: {total_runs}")
        print_info(f"Canonical runs: {canonical_runs}")
        print_info(f"Legacy runs: {legacy_runs}")
        print_info(f"Total ads: {total_ads}")
        print_info(f"Ads with image paths: {ads_with_images}")
        
        if total_ads > 0:
            coverage = (ads_with_images / total_ads) * 100
            print_check(
                "Image path coverage",
                coverage >= 95,
                f"{coverage:.1f}% ({ads_with_images}/{total_ads})"
            )
            if coverage < 95:
                self.warnings.append(f"Image path coverage below 95%: {coverage:.1f}%")
        
        if legacy_runs > 0:
            print_warning(f"{legacy_runs} legacy runs found - run migration tool")
            print_info("Run: python3 tools/migrate_instacart_legacy_to_canonical.py")
    
    def check_api_endpoints(self):
        """Check API endpoints with Instacart data"""
        print_header("API ENDPOINTS")
        
        # Get a sample client
        test_client = self.client
        if not test_client:
            clients = [d.name for d in self.output_root.iterdir() if d.is_dir()]
            if clients:
                test_client = clients[0]
        
        if not test_client:
            print_warning("No clients available for API testing")
            return
        
        print_info(f"Testing with client: {test_client}")
        
        # Test /api/runs
        try:
            response = requests.get(
                f"http://localhost:5006/api/runs?retailer=instacart&client={test_client}",
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                run_count = len(data.get('runs', []))
                print_check("/api/runs", True, f"{run_count} runs returned")
                
                # Check timestamp format
                if data.get('runs'):
                    sample_ts = data['runs'][0].get('timestamp', '')
                    has_iso = 'T' in sample_ts and 'Z' in sample_ts
                    has_epoch = 'timestamp_ms' in data['runs'][0]
                    print_check("  ISO Z timestamps", has_iso, sample_ts if has_iso else "Legacy format")
                    print_check("  Epoch milliseconds", has_epoch)
            else:
                print_check("/api/runs", False, f"Status {response.status_code}")
                self.issues.append(f"/api/runs returned {response.status_code}")
        except Exception as e:
            print_check("/api/runs", False, str(e))
            self.issues.append(f"/api/runs error: {e}")
        
        # Test /api/ads/cards
        try:
            response = requests.get(
                f"http://localhost:5006/api/ads/cards?retailer=instacart&client={test_client}&page_size=5",
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                card_count = len(data.get('cards', []))
                print_check("/api/ads/cards", True, f"{card_count} cards returned")
                
                # Check card structure
                if data.get('cards'):
                    sample_card = data['cards'][0]
                    has_timestamp = bool(sample_card.get('timestamp'))
                    has_timestamp_ms = bool(sample_card.get('timestamp_ms'))
                    has_image_url = bool(sample_card.get('image_url'))
                    has_advertisers = bool(sample_card.get('advertisers'))
                    
                    print_check("  timestamp field", has_timestamp)
                    print_check("  timestamp_ms field", has_timestamp_ms)
                    print_check("  image_url field", has_image_url)
                    print_check("  advertisers array", has_advertisers)
            else:
                print_check("/api/ads/cards", False, f"Status {response.status_code}")
                self.issues.append(f"/api/ads/cards returned {response.status_code}")
        except Exception as e:
            print_check("/api/ads/cards", False, str(e))
            self.issues.append(f"/api/ads/cards error: {e}")
        
        # Test image serving
        if test_client:
            try:
                # Try to get a sample image
                response = requests.get(
                    f"http://localhost:5006/api/ads/cards?retailer=instacart&client={test_client}&page_size=1",
                    timeout=5
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get('cards') and data['cards'][0].get('image_url'):
                        image_url = data['cards'][0]['image_url']
                        if image_url.startswith('/api/image'):
                            img_response = requests.get(f"http://localhost:5006{image_url}", timeout=5)
                            print_check(
                                "Image serving",
                                img_response.status_code == 200,
                                f"Status {img_response.status_code}"
                            )
                            if img_response.status_code != 200:
                                self.issues.append("Image serving failed")
            except Exception as e:
                print_check("Image serving", False, str(e))
    
    def print_summary(self):
        """Print final summary"""
        print_header("SUMMARY")
        
        if not self.issues and not self.warnings:
            print(f"{GREEN}✅ ALL CHECKS PASSED{NC}")
            print(f"\n{GREEN}Instacart is ready for Builder.io integration!{NC}\n")
        else:
            if self.issues:
                print(f"{RED}❌ {len(self.issues)} CRITICAL ISSUE(S):{NC}")
                for issue in self.issues:
                    print(f"   • {issue}")
                print()
            
            if self.warnings:
                print(f"{YELLOW}⚠️  {len(self.warnings)} WARNING(S):{NC}")
                for warning in self.warnings:
                    print(f"   • {warning}")
                print()
            
            print(f"\n{YELLOW}Action required before Builder.io integration{NC}\n")
    
    def run(self):
        """Run all checks"""
        print_header("INSTACART READINESS DOCTOR")
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if self.client:
            print(f"Client: {self.client}")
        
        self.check_servers()
        self.check_authentication()
        self.check_data_integrity()
        self.check_api_endpoints()
        self.print_summary()

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Instacart Builder.io Readiness Check")
    parser.add_argument("--client", help="Specific client to check")
    parser.add_argument("--auto-fix", action="store_true", help="Attempt to auto-fix issues")
    args = parser.parse_args()
    
    doctor = InstacartReadinessDoctor(client=args.client, auto_fix=args.auto_fix)
    doctor.run()

if __name__ == "__main__":
    main()
