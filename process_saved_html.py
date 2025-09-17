"""
Process Saved HTML Files for Ad Extraction

This script processes HTML files that have already been saved by test_session_persistence.py
to extract ad data without needing to use Playwright.
"""

import os
import json
import glob
import argparse
import requests
import re
from datetime import datetime
from bs4 import BeautifulSoup
from kroger_ad_core import extract_ads_from_html, extract_common_words_and_phrases
from urllib.parse import urljoin

# Import for TOA image capture
try:
    from PIL import Image
    from io import BytesIO
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Constants
DEFAULT_DIR = "output"

def extract_toa_images(json_file, html_file=None, client_name=None):
    """
    Extract TOA images using screenshot_toa_image.py
    
    Args:
        json_file (str): Path to the JSON file with TOA data
        html_file (str, optional): Path to specific HTML file to process
        client_name (str): Client name for organizing output
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        import subprocess
        
        # Build command to run screenshot_toa_image.py
        cmd = ["python3", "screenshot_toa_image.py", "--json", json_file]
        
        # Add HTML file if provided
        if html_file:
            cmd.extend(["--html", html_file])  # Using --html flag (short form is -f)
        
        # Add client name if provided
        if client_name:
            cmd.extend(["--client", client_name])
            
        print(f"\n📷 Extracting TOA images using screenshot_toa_image.py...")
        
        # Use subprocess.run to wait for completion
        try:
            # Set a timeout to prevent hanging indefinitely
            result = subprocess.run(cmd, 
                                  stdout=subprocess.PIPE, 
                                  stderr=subprocess.PIPE,
                                  text=True,
                                  timeout=60)  # 60 second timeout
            
            if result.returncode == 0:
                print(f"✅ TOA image extraction completed successfully")
                return True
            else:
                print(f"⚠️ TOA image extraction completed with issues: {result.stderr}")
                return True  # Still return True to continue processing
        except subprocess.TimeoutExpired:
            print(f"⚠️ TOA image extraction timed out after 60 seconds, continuing anyway")
            return True  # Continue processing even if timeout occurs
    except Exception as e:
        print(f"❌ Error starting TOA image extraction: {e}")
        return False

def remove_html_from_ads(ads):
    """Remove HTML content from ads to reduce JSON size"""
    for ad in ads:
        if 'html' in ad:
            del ad['html']
    return ads

def extract_ads_from_html_file(html_file):
    """Extract ad data from a saved HTML file"""
    print(f"\n📝 Processing HTML file: {os.path.basename(html_file)}")
    
    try:
        # Read the HTML file
        with open(html_file, 'r', encoding='utf-8') as f:
            html = f.read()
        
        # Try to extract keyword from filename
        keyword = None
        filename = os.path.basename(html_file)
        if filename.startswith("search_results_"):
            # Extract search term from filename
            # Format is typically search_results_SEARCH_TERM_TIMESTAMP.html
            # Extract everything between search_results_ and the timestamp
            timestamp_pattern = r'_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}'
            match = re.search(timestamp_pattern, filename)
            
            if match:
                # Get everything between 'search_results_' and the timestamp
                keyword_part = filename[len('search_results_'):match.start()]
                keyword = keyword_part.replace('_', ' ').strip()
            else:
                # Fallback to old method
                parts = filename.replace("search_results_", "").split("_")
                if len(parts) > 1:
                    # Last part is usually the timestamp
                    keyword = "_".join(parts[:-1])
                    keyword = keyword.replace("_", " ")
                    
                # Try to extract search term from page title or search input
                soup = BeautifulSoup(html, 'html.parser')
                
                # Method 1: Look for search query in title
                title = soup.title.text if soup.title else ""
                if "Search:" in title:
                    search_term = title.split("Search:")[1].strip()
                    keyword = search_term
                
                # Method 2: Look for search input value
                if not keyword:
                    search_input = soup.select_one('input[type="search"]')
                    if search_input and search_input.get('value'):
                        keyword = search_input.get('value')
                
                # Method 3: Look for search term in URL
                if not keyword:
                    meta_refresh = soup.select_one('meta[http-equiv="refresh"]')
                    if meta_refresh and 'query=' in meta_refresh.get('content', ''):
                        content = meta_refresh.get('content')
                        query_part = content.split('query=')[1].split('&')[0]
                        keyword = query_part.replace('%20', ' ')
                
                # Fallback: Use the filename parts without timestamp
                if not keyword:
                    keyword = "_".join(parts[:-1]).replace(".html", "").replace("_", " ")
        
        # Get client name from directory path
        client = None
        dir_path = os.path.dirname(html_file)
        if "output" in dir_path:
            client_dir = os.path.basename(dir_path)
            if client_dir != "output":  # Make sure it's not the main output dir
                client = client_dir
        
        # Find corresponding screenshot in main subfolder
        screenshot_path = None
        if client:
            main_dir = os.path.join(dir_path, "main")
            if os.path.exists(main_dir):
                # Get the base filename without extension
                base_filename = os.path.splitext(filename)[0]
                # Look for matching screenshot
                screenshot_candidates = glob.glob(os.path.join(main_dir, f"{base_filename}.png"))
                if screenshot_candidates:
                    screenshot_path = screenshot_candidates[0]
        
        # Extract all ads from the HTML
        ads = extract_ads_from_html(html, client=client, search_term=keyword)
        
        # Remove HTML content from ads to reduce JSON size
        ads = remove_html_from_ads(ads)
        
        # Create TOA subfolder for images
        if client:
            toa_dir = os.path.join(os.path.dirname(html_file), "TOA")
            os.makedirs(toa_dir, exist_ok=True)
        
        # Get titles for analysis
        titles = [ad.get('message', '') for ad in ads if ad.get('message')]
        analysis = extract_common_words_and_phrases(titles)
        
        return {
            'ads': ads,
            'analysis': analysis,
            'count': len(ads),
            'keyword': keyword,
            'search_term': keyword,  # Adding search_term field explicitly
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'source_file': html_file
        }
        
    except FileNotFoundError as e:
        print(f"❌ File not found error: {e}")
        return None
    except (ValueError, AttributeError, TypeError) as e:
        print(f"❌ Error processing HTML file: {e}")
        return None

def get_daily_results_file(output_dir):
    """Get the path to the daily results file"""
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Create TOA subfolder if it doesn't exist
    toa_dir = os.path.join(output_dir, "TOA")
    os.makedirs(toa_dir, exist_ok=True)
    
    return os.path.join(toa_dir, f"toa_results_{today}.json")

def load_existing_results(results_path):
    """Load existing results from the daily file if it exists"""
    if os.path.exists(results_path):
        try:
            with open(results_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load existing results: {e}")
            return {"results": []}
    return {"results": []}

def process_latest_html_file(input_dir=None, output_dir=None):
    """Process the most recently saved HTML file"""
    # Use default directories if not provided
    input_dir = input_dir or DEFAULT_DIR
    output_dir = output_dir or DEFAULT_DIR
    
    # Find the latest HTML file
    html_files = glob.glob(os.path.join(input_dir, "search_results_*.html"))
    if not html_files:
        print(f"❌ No HTML files found in the input directory: {input_dir}")
        return False
    
    # Sort by modification time (newest first)
    latest_html = max(html_files, key=os.path.getmtime)
    print(f"📋 Found latest HTML file: {os.path.basename(latest_html)}")
    
    # Process the HTML file
    results = extract_ads_from_html_file(latest_html)
    if not results:
        return False
    
    # Get the daily results file path
    os.makedirs(output_dir, exist_ok=True)
    results_path = get_daily_results_file(output_dir)
    
    # Load existing results or create new structure
    daily_results = load_existing_results(results_path)
    
    # Append new results
    daily_results["results"].append(results)
    daily_results["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Save the updated results
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(daily_results, f, indent=2)
    
    print(f"✅ Found {results['count']} TOAs")
    print(f"💾 Results saved to {results_path}")
    
    # TOA images are now extracted once from the combined JSON results
    # This prevents duplicate image generation from multiple HTML files
    
    # NOTE: Carousel images are now captured directly in kroger_search_and_capture.py
    # No need to extract carousel images here anymore
    pass
    
    # Print some details about the ads found
    if results['ads']:
        print("\n📋 TOA Details:")
        for i, ad in enumerate(results['ads'], 1):
            print(f"  Ad #{i}: {ad.get('message', 'No message')}")
            print(f"    - Description: {ad.get('description', 'None')}")
            print(f"    - CTA: {ad.get('cta', 'None')}")
            print(f"    - Brand: {ad.get('brand', 'Unknown')}")
            print()
    
    return True

def process_all_html_files(input_dir=None, output_dir=None):
    """Process all HTML files in the input directory"""
    # Use default directories if not provided
    input_dir = input_dir or DEFAULT_DIR
    output_dir = output_dir or DEFAULT_DIR
    
    html_files = glob.glob(os.path.join(input_dir, "search_results_*.html"))
    if not html_files:
        print(f"❌ No HTML files found in the input directory: {input_dir}")
        return False
    
    print(f"📃 Found {len(html_files)} HTML files to process")
    
    # Get the daily results file path
    os.makedirs(output_dir, exist_ok=True)
    results_path = get_daily_results_file(output_dir)
    
    # Load existing results or create new structure
    daily_results = load_existing_results(results_path)
    
    # Group HTML files by search term
    search_term_files = {}
    
    # Process each HTML file and organize by search term
    for html_file in html_files:
        # Extract data from the file
        result = extract_ads_from_html_file(html_file)
        if not result:
            continue
            
        # Get the search term
        search_term = result.get('keyword')
        if not search_term:
            # Use filename as fallback
            filename = os.path.basename(html_file)
            search_term = filename.replace("search_results_", "").split("_")[0]
        
        # Add to the appropriate group
        if search_term not in search_term_files:
            search_term_files[search_term] = []
        
        search_term_files[search_term].append(result)
    
    # Process each search term group
    processed_count = 0
    for search_term, results_list in search_term_files.items():
        if not results_list:
            continue
            
        # Sort results by timestamp (newest first)
        results_list.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        # Include all results for this search term, not just the latest
        for result in results_list:
            # Make sure the keyword is set correctly
            result['keyword'] = search_term
            result['search_term'] = search_term  # Ensure search_term is set
            
            # Add to daily results
            daily_results["results"].append(result)
            processed_count += 1
    
    # Update timestamp
    daily_results["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Save the updated results
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(daily_results, f, indent=2)
    
    print(f"✅ Processed {processed_count} search terms from {len(html_files)} HTML files")
    print(f"💾 Combined results saved to {results_path}")
    
    # Process TOA images ONCE from the combined results
    print("\n📷 Extracting TOA images from combined results...")
    extract_toa_images(results_path, client_name=os.path.basename(output_dir))
    
    return True

if __name__ == "__main__":
    print("\n" + "="*50)
    print("KROGER TOA HTML PROCESSOR")
    print("="*50)
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Process saved HTML files to extract TOA data")
    parser.add_argument("--input-dir", "-i", type=str, help="Directory containing HTML files to process")
    parser.add_argument("--output-dir", "-o", type=str, help="Directory to save extracted TOA data")
    parser.add_argument("--all", "-a", action="store_true", help="Process all HTML files instead of just the latest")
    parser.add_argument("--all-files", action="store_true", help="Process all HTML files instead of just the latest")
    args = parser.parse_args()
    
    # Process HTML files
    if args.all or args.all_files:
        success = process_all_html_files(args.input_dir, args.output_dir)
    else:
        success = process_latest_html_file(args.input_dir, args.output_dir)
    
    if success:
        print("\n✅ TOA EXTRACTION COMPLETED SUCCESSFULLY")
    else:
        print("\n❌ TOA EXTRACTION FAILED")
