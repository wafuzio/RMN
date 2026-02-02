#!/usr/bin/env python3
"""Test the TikTok Shop adapter end-to-end."""

import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from retailers.tiktokshop.adapter import TikTokShopAdapter
from core.run_context import RunContext


def test_tiktokshop_adapter():
    profile_dir = os.environ.get('TIKTOKSHOP_PROFILE_DIR')
    if not profile_dir or not os.path.isdir(profile_dir):
        print(f"❌ TIKTOKSHOP_PROFILE_DIR not set or invalid: {profile_dir}")
        print("\nTo set up the profile, run:")
        print("  ./scripts/setup_tiktokshop_profile.sh")
        return False
    
    print("=" * 60)
    print("TikTok Shop Adapter Test")
    print("=" * 60)
    print(f"Profile: {profile_dir}")
    print()
    
    test_client = "adapter_test"
    base_dir = str(project_root)
    output_dir = str(project_root / "output" / "tiktokshop" / test_client)
    runs_dir = str(project_root / "output" / "tiktokshop" / test_client / "runs")
    logs_dir = str(project_root / "logs" / "tiktokshop")
    
    ctx = RunContext(
        retailer="tiktokshop",
        client=test_client,
        base_dir=base_dir,
        output_dir=output_dir,
        runs_dir=runs_dir,
        logs_dir=logs_dir,
        profile_dir=profile_dir,
        script_dir=base_dir
    )
    
    os.makedirs(ctx.output_dir, exist_ok=True)
    
    adapter = TikTokShopAdapter()
    
    print(f"Testing adapter: {adapter.display_name} ({adapter.slug})")
    print(f"Output directory: {ctx.output_dir}")
    print()
    
    # Use "main" to capture the homepage
    keyword = "main"
    print(f"Running search_and_capture for: '{keyword}' (homepage)")
    print("-" * 60)
    
    success = adapter.search_and_capture(keyword, ctx)
    
    print("-" * 60)
    if success:
        print("✅ search_and_capture completed successfully")
        
        runs_dir = Path(ctx.output_dir) / "runs"
        if runs_dir.exists():
            html_files = list(runs_dir.glob("search_results_*.html"))
            json_files = list(runs_dir.glob("run_results_*.json"))
            
            print(f"\nOutput files:")
            print(f"  HTML files: {len(html_files)}")
            print(f"  JSON files: {len(json_files)}")
            
            if json_files:
                import json
                with open(json_files[-1]) as f:
                    data = json.load(f)
                
                products = [a for a in data.get("ads", []) if a.get("type") == "Products"]
                brands = [a for a in data.get("ads", []) if a.get("type") == "Featured_Brands"]
                
                print(f"\n  Products found: {len(products)}")
                print(f"  Brand sections: {len(brands)}")
                print(f"  Main screenshot: {data.get('main_screenshot', 'N/A')}")
        
        # Check for screenshots
        main_dir = Path(ctx.output_dir) / "Main"
        products_dir = Path(ctx.output_dir) / "Products"
        
        if main_dir.exists():
            main_shots = list(main_dir.glob("*.png"))
            print(f"\n  Main screenshots: {len(main_shots)}")
        
        if products_dir.exists():
            product_shots = list(products_dir.glob("*.png"))
            print(f"  Product screenshots: {len(product_shots)}")
        
        return True
    else:
        print("❌ search_and_capture failed")
        return False


if __name__ == "__main__":
    success = test_tiktokshop_adapter()
    sys.exit(0 if success else 1)
