"""
Kroger TOA Extraction Test

This script tests the TOA extraction functionality separately from the session persistence test
to avoid asyncio conflicts.
"""

import os
import json
import urllib.parse
from datetime import datetime
from Kroger_TOA import extract_toa_ads_from_url

# Constants
USER_DATA_DIR = os.path.expanduser("~/ChromeProfiles/kroger_clean_profile")
TEST_SEARCH_TERM = "black forest ham"
OUTPUT_DIR = "output"

def test_toa_extraction():
    """Test the TOA extraction functionality"""
    print("\n" + "="*50)
    print("KROGER TOA EXTRACTION TEST")
    print("="*50)
    
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Create search URL
    search_url = "https://www.kroger.com/search?query={}".format(urllib.parse.quote_plus(TEST_SEARCH_TERM))
    
    print("\n🔍 Testing TOA extraction for search term: {}".format(TEST_SEARCH_TERM))
    print("   URL: {}".format(search_url))
    
    try:
        print("\n📊 Running extract_toa_ads_from_url...")
        results = extract_toa_ads_from_url(search_url, user_data_dir=USER_DATA_DIR)
        
        # Save results
        results_path = os.path.join(OUTPUT_DIR, "toa_results_{}.json".format(timestamp))
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
            
        print("✅ Found {} TOAs using extract_toa_ads_from_url".format(len(results['ads'])))
        print("💾 Results saved to {}".format(results_path))
        
        # Print some details about the ads found
        if results['ads']:
            print("\n📋 TOA Details:")
            for i, ad in enumerate(results['ads'], 1):
                print("  Ad #{}: {}".format(i, ad.get('message', 'No message')))
                print("    - Description: {}".format(ad.get('description', 'None')))
                print("    - CTA: {}".format(ad.get('cta', 'None')))
                print("    - Brand: {}".format(ad.get('brand', 'Unknown')))
                print()
        
        return True
        
    except FileNotFoundError as e:
        print("❌ File not found error: {}".format(e))
        return False
    except json.JSONDecodeError as e:
        print("❌ JSON decode error: {}".format(e))
        return False
    except ValueError as e:
        print("❌ Value error: {}".format(e))
        return False
    except AttributeError as e:
        print("❌ Attribute error: {}".format(e))
        return False
    except Exception as e:
        print("❌ Unexpected error: {}".format(e))
        return False

if __name__ == "__main__":
    success = test_toa_extraction()
    
    if success:
        print("\n✅ TOA EXTRACTION TEST PASSED")
    else:
        print("\n❌ TOA EXTRACTION TEST FAILED")
