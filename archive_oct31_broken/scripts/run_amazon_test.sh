#!/bin/bash
# Simple script to test the Amazon adapter

# Check if AMZ_PROFILE_DIR is set
if [ -z "$AMZ_PROFILE_DIR" ]; then
    # Try to find a default profile
    DEFAULT_PROFILE="$HOME/Documents/Amazon_Scrape/profiles/amazon"
    if [ -d "$DEFAULT_PROFILE" ]; then
        export AMZ_PROFILE_DIR="$DEFAULT_PROFILE"
        echo "Using default profile: $AMZ_PROFILE_DIR"
    else
        echo "Error: AMZ_PROFILE_DIR environment variable not set and default profile not found."
        echo "Please run the following commands:"
        echo "  mkdir -p ~/Documents/Amazon_Scrape/profiles/amazon"
        echo "  python3 auth/retailer_auth.py --retailer amazon --profile-dir ~/Documents/Amazon_Scrape/profiles/amazon"
        echo "  export AMZ_PROFILE_DIR=~/Documents/Amazon_Scrape/profiles/amazon"
        exit 1
    fi
fi

# Get the keyword from command line or use default
KEYWORD="${1:-coffee maker}"
CLIENT="${2:-test_client}"

echo "Testing Amazon adapter with keyword: $KEYWORD"
echo "Client: $CLIENT"
echo "Profile: $AMZ_PROFILE_DIR"

# Run the test
python3 -c "
import os
import sys
import time
from core.retailers import get as get_retailer_adapter
from core.run_context import RunContext
from core.paths import output_dir_for, logs_dir_for
import retailers.amazon.adapter

# Get the Amazon adapter
amazon_adapter = get_retailer_adapter('amazon')
print(f'Using adapter: {amazon_adapter.display_name}')

# Set up the run context
base_dir = os.path.dirname(os.path.abspath('__file__'))
client = '$CLIENT'

# Create run context
ctx = RunContext(
    retailer='amazon',
    client=client,
    base_dir=base_dir,
    output_dir=output_dir_for(base_dir, 'amazon', client),
    runs_dir=os.path.join(output_dir_for(base_dir, 'amazon', client), 'runs'),
    logs_dir=logs_dir_for(base_dir, 'amazon'),
    profile_dir=os.environ.get('AMZ_PROFILE_DIR'),
    script_dir=base_dir
)

# Run the search and capture
print(f'Running search and capture for: $KEYWORD')
run_start_ts = time.time()
success = amazon_adapter.search_and_capture('$KEYWORD', ctx)

if not success:
    print('Search and capture failed.')
    sys.exit(1)

# Collect pairs
print('Collecting HTML/JSON pairs...')
pairs = amazon_adapter.collect_pairs_for_run(ctx, run_start_ts)

if not pairs:
    print('No HTML/JSON pairs found.')
    sys.exit(1)

print(f'Found {len(pairs)} HTML/JSON pairs.')

# Extract images
for i, (json_path, html_path) in enumerate(pairs):
    print(f'Extracting images from pair {i+1}/{len(pairs)}...')
    results = amazon_adapter.extract_images(json_path, html_path, ctx)
    
    print(f'Extraction results:')
    print(f'  TOA (Sponsored Brands): {results[\"toa\"]}')
    print(f'  Skyscraper (Sponsored Display): {results[\"sky\"]}')
    print(f'  Carousel (Sponsored Products): {results[\"car\"]}')
    print(f'  Log file: {results[\"log\"]}')

print('\\nTest completed successfully!')
print(f'Output directory: {ctx.output_dir}')
print(f'Log directory: {ctx.logs_dir}')
"

# Check exit status
if [ $? -eq 0 ]; then
    echo "Test completed successfully!"
    echo "Check the following directories for results:"
    echo "  HTML/JSON: ~/Documents/Amazon_Scrape/output/amazon/$CLIENT/runs/"
    echo "  TOA: ~/Documents/Amazon_Scrape/output/amazon/$CLIENT/TOA/"
    echo "  Skyscraper: ~/Documents/Amazon_Scrape/output/amazon/$CLIENT/Skyscraper/"
    echo "  Carousel: ~/Documents/Amazon_Scrape/output/amazon/$CLIENT/Carousel/"
    echo "  Logs: ~/Documents/Amazon_Scrape/logs/amazon/"
else
    echo "Test failed. Check the error messages above."
fi
