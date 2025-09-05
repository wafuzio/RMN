try:
    # No specific playwright imports needed in this file
    # The actual playwright functionality is imported through Kroger_login and Kroger_TOA
    pass
except ImportError as e:
    print(f"❌ Missing dependency: {e.name}. Run: pip install -r requirements.txt")
    exit(1)

import subprocess

try:
    subprocess.run(
        ["playwright", "install"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
except subprocess.SubprocessError as e:
    print(
        f"❌ Playwright browser binaries may be missing. Run: python -m playwright install. Error: {e}"
    )
    exit(1)

import time
from datetime import datetime
import json
import os

from Kroger_TOA import extract_toa_ads_from_url
from Kroger_login import get_authenticated_context

search_terms = [
    # Deli & Meat
    "packaged deli meat",
    "deli meat",
    "black forest ham",
    "sliced turkey",
    # Dairy
    "yogurt",
    "cheese",
    # Produce
    "organic apples",
    "fresh vegetables",
    # Pantry
    "pasta sauce",
    "cereal",
    "coffee",
    # Health & Wellness
    "vitamins",
    "protein powder",
    # Household
    "laundry detergent",
    "paper towels",
]


def run_test():
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    all_results = {}

    print("🔐 Logging into Kroger and launching browser session...")
    user_data_dir = os.path.expanduser("~/ChromeProfiles/kroger_clean_profile")
    # Get authenticated context first
    browser, _ = get_authenticated_context(user_data_dir=user_data_dir)
    # Wait for a moment to ensure session is properly established
    print("⏳ Waiting for session to stabilize...")
    time.sleep(5)  # Add a 5-second wait after login
    # Close the browser to ensure cookies are properly saved
    browser.close()
    print("✅ Browser closed, session data should be saved")
    # Wait a moment before starting the scraping process
    time.sleep(2)
    for term in search_terms:
        print(f"\n🔎 Searching for: {term}")
        search_url = f"https://www.kroger.com/search?query={term.replace(' ', '%20')}"
        try:
            # Pass the same user_data_dir to extract_toa_ads_from_url
            results = extract_toa_ads_from_url(search_url, user_data_dir=user_data_dir)
            all_results[term] = results
            print(f"✅ Found {len(results['ads'])} TOAs")
        except ValueError as e:
            print(f"❌ Error with term '{term}': {e}")
            all_results[term] = []
        except KeyError as e:
            print(f"❌ Missing key in results for '{term}': {e}")
            all_results[term] = []
        except (ConnectionError, TimeoutError) as e:
            print(f"❌ Connection error with term '{term}': {e}")
            all_results[term] = []
        except RuntimeError as e:
            print(f"❌ Runtime error with term '{term}': {e}")
            all_results[term] = []

        time.sleep(3)  # slightly longer polite gap between searches

    print("\n💾 Saving results...")
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"toas_test_{timestamp}.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)

    print(f"✅ Done. Saved to: {output_file}")


if __name__ == "__main__":
    run_test()
