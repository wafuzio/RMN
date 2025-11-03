#!/usr/bin/env python3
"""
Quick test of the Instacart adapter end-to-end.
Tests search_and_capture without running full image extraction.
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import adapter
from retailers.instacart.adapter import InstacartAdapter
from core.run_context import RunContext

def test_instacart_adapter():
    """Test the Instacart adapter search_and_capture."""
    
    # Check environment
    profile_dir = os.environ.get('INSTACART_PROFILE_DIR')
    if not profile_dir or not os.path.isdir(profile_dir):
        print(f"❌ INSTACART_PROFILE_DIR not set or invalid: {profile_dir}")
        print("Run: ./scripts/setup_instacart_profile.sh")
        return False
    
    store = os.environ.get('INSTACART_STORE', 'publix')
    
    print("=" * 60)
    print("Instacart Adapter Test")
    print("=" * 60)
    print(f"Profile: {profile_dir}")
    print(f"Store: {store}")
    print()
    
    # Create test context
    test_client = "adapter_test"
    base_dir = str(project_root)
    output_dir = str(project_root / "output" / "instacart" / test_client)
    runs_dir = str(project_root / "output" / "instacart" / test_client / "runs")
    logs_dir = str(project_root / "logs" / "instacart")
    
    ctx = RunContext(
        retailer="instacart",
        client=test_client,
        base_dir=base_dir,
        output_dir=output_dir,
        runs_dir=runs_dir,
        logs_dir=logs_dir,
        profile_dir=profile_dir,
        script_dir=base_dir
    )
    
    # Create output directory
    os.makedirs(ctx.output_dir, exist_ok=True)
    
    # Test adapter
    adapter = InstacartAdapter()
    
    print(f"Testing adapter: {adapter.display_name} ({adapter.slug})")
    print(f"Output directory: {ctx.output_dir}")
    print()
    
    # Test search and capture
    keyword = "eggs"
    print(f"Running search_and_capture for keyword: '{keyword}'")
    print("-" * 60)
    
    success = adapter.search_and_capture(keyword, ctx)
    
    print("-" * 60)
    if success:
        print("✅ search_and_capture completed successfully")
        
        # Check for output files
        runs_dir = Path(ctx.output_dir) / "runs"
        if runs_dir.exists():
            html_files = list(runs_dir.glob("search_results_*.html"))
            json_files = list(runs_dir.glob("run_results_*.json"))
            
            print(f"\nOutput files:")
            print(f"  HTML files: {len(html_files)}")
            print(f"  JSON files: {len(json_files)}")
            
            if html_files:
                print(f"\n  Latest HTML: {html_files[-1].name}")
            if json_files:
                print(f"  Latest JSON: {json_files[-1].name}")
                
                # Show JSON content
                import json
                with open(json_files[-1]) as f:
                    data = json.load(f)
                print(f"\n  Ads found: {len(data.get('ads', []))}")
                for ad in data.get('ads', [])[:3]:  # Show first 3
                    print(f"    - {ad.get('type')}: {ad.get('title', 'N/A')}")
        
        return True
    else:
        print("❌ search_and_capture failed")
        return False


if __name__ == "__main__":
    success = test_instacart_adapter()
    sys.exit(0 if success else 1)
