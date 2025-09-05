"""
Process Saved HTML Files for TOA Extraction

This script processes HTML files that have already been saved by test_session_persistence.py
to extract TOA data without needing to use Playwright.
"""

import os
import json
import glob
import argparse
from datetime import datetime
from bs4 import BeautifulSoup
from Kroger_TOA import extract_toa_ad, extract_common_words_and_phrases

# Constants
DEFAULT_DIR = "output"

def extract_toa_from_html_file(html_file):
    """Extract TOA data from a saved HTML file"""
    print(f"\n📄 Processing HTML file: {os.path.basename(html_file)}")
    
    try:
        # Read the HTML file
        with open(html_file, 'r', encoding='utf-8') as f:
            html = f.read()
        
        # Extract keyword from filename
        filename = os.path.basename(html_file)
        keyword = None
        if "search_results_" in filename and ".html" in filename:
            # Format is typically search_results_keyword_timestamp.html
            parts = filename.replace("search_results_", "").split("_")
            if len(parts) > 1:
                # Join all parts except the last one (timestamp) and the file extension
                keyword = "_".join(parts[:-1]).replace(".html", "")
        
        # Parse the HTML
        soup = BeautifulSoup(html, 'html.parser')
        toa_divs = soup.select('div[data-testid="StandardTOA"]')
        
        print(f"[TOA Ads Found] {len(toa_divs)}")
        
        results = []
        for div in toa_divs:
            ad = extract_toa_ad(str(div))
            if ad:
                results.append(ad)
        
        titles = [ad['message'] for ad in results if ad.get('message')]
        analysis = extract_common_words_and_phrases(titles)
        
        return {
            'ads': results,
            'analysis': analysis,
            'count': len(results),
            'keyword': keyword,
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
    return os.path.join(output_dir, f"toa_results_{today}.json")

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
    results = extract_toa_from_html_file(latest_html)
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
    
    print(f"📋 Found {len(html_files)} HTML files to process")
    
    # Get the daily results file path
    os.makedirs(output_dir, exist_ok=True)
    results_path = get_daily_results_file(output_dir)
    
    # Load existing results or create new structure
    daily_results = load_existing_results(results_path)
    
    # Process each HTML file and append to results
    processed_count = 0
    for html_file in html_files:
        results = extract_toa_from_html_file(html_file)
        if results:
            daily_results["results"].append(results)
            processed_count += 1
    
    # Update timestamp
    daily_results["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Save the updated results
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(daily_results, f, indent=2)
    
    print(f"✅ Processed {processed_count} HTML files")
    print(f"💾 Combined results saved to {results_path}")
    
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
    args = parser.parse_args()
    
    # Process HTML files
    if args.all:
        success = process_all_html_files(args.input_dir, args.output_dir)
    else:
        success = process_latest_html_file(args.input_dir, args.output_dir)
    
    if success:
        print("\n✅ TOA EXTRACTION COMPLETED SUCCESSFULLY")
    else:
        print("\n❌ TOA EXTRACTION FAILED")
