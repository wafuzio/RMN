#!/usr/bin/env python3
# Test script for Amazon scraping
import os
import sys
import time
from core.retailers import get as get_retailer_adapter
from core.run_context import RunContext
from core.paths import output_dir_for, logs_dir_for

# Import the adapter to ensure it's registered
import retailers.amazon.adapter

def test_amazon_scrape(keyword="coffee maker"):
    """Test the Amazon adapter with a simple search."""
    print(f"Testing Amazon adapter with keyword: {keyword}")
    
    # Get the Amazon adapter
    amazon_adapter = get_retailer_adapter("amazon")
    print(f"Using adapter: {amazon_adapter.display_name}")
    
    # Set up the run context
    base_dir = os.path.dirname(os.path.abspath(__file__))
    client = "test_client"
    
    # Get profile directory
    profile_dir = os.environ.get("AMZ_PROFILE_DIR")
    if not profile_dir:
        default_profile = os.path.join(base_dir, "profiles", "amazon")
        if os.path.isdir(default_profile):
            profile_dir = default_profile
            print(f"Using default profile: {profile_dir}")
        else:
            print("No Amazon profile found. Please run scripts/setup_amazon_profile.sh first.")
            return False
    
    # Create run context
    ctx = RunContext(
        retailer="amazon",
        client=client,
        base_dir=base_dir,
        output_dir=output_dir_for(base_dir, "amazon", client),
        runs_dir=os.path.join(output_dir_for(base_dir, "amazon", client), "runs"),
        logs_dir=logs_dir_for(base_dir, "amazon"),
        profile_dir=profile_dir,
        script_dir=base_dir
    )
    
    # Run the search and capture
    print(f"Running search and capture for: {keyword}")
    run_start_ts = time.time()
    success = amazon_adapter.search_and_capture(keyword, ctx)
    
    if not success:
        print("Search and capture failed.")
        return False
    
    # Collect pairs
    print("Collecting HTML/JSON pairs...")
    pairs = amazon_adapter.collect_pairs_for_run(ctx, run_start_ts)
    
    if not pairs:
        print("No HTML/JSON pairs found.")
        return False
    
    print(f"Found {len(pairs)} HTML/JSON pairs.")
    
    # Extract images
    for i, (json_path, html_path) in enumerate(pairs):
        print(f"Extracting images from pair {i+1}/{len(pairs)}...")
        results = amazon_adapter.extract_images(json_path, html_path, ctx)
        
        print(f"Extraction results:")
        print(f"  TOA (Sponsored Brands): {results['toa']}")
        print(f"  Skyscraper (Sponsored Display): {results['sky']}")
        print(f"  Carousel (Sponsored Products): {results['car']}")
        print(f"  Log file: {results['log']}")
    
    print("\nTest completed successfully!")
    print(f"Output directory: {ctx.output_dir}")
    print(f"Log directory: {ctx.logs_dir}")
    
    return True

if __name__ == "__main__":
    # Allow keyword to be passed as command line argument
    keyword = sys.argv[1] if len(sys.argv) > 1 else "coffee maker"
    test_amazon_scrape(keyword)
