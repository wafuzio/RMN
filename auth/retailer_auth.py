# auth/retailer_auth.py
import os, time, argparse
from playwright.sync_api import sync_playwright

RETAILER_URLS = {
    "amazon": "https://www.amazon.com/",
    "kroger": "https://www.kroger.com/",
    "walmart": "https://www.walmart.com/",
    "instacart": "https://www.instacart.com/store/publix",  # Default to Publix for initial setup
    "target": "https://www.target.com/",
}

def ensure_profile(retailer: str, profile_dir: str, channel="chrome"):
    os.makedirs(profile_dir, exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=False,
            channel=channel,
            viewport={"width": 1400, "height": 900},
            locale="en-US"
        )
        page = ctx.new_page()
        page.goto(RETAILER_URLS[retailer], wait_until="domcontentloaded")
        print(f"Login to {retailer} in the opened browser, complete 2FA if prompted.")
        print("Leave the page logged in, then close the window to save the profile.")
        while True:
            try:
                content = page.content().lower()
                # Heuristic: "Hello" account link appears for logged-in US accounts
                if retailer == "amazon" and ("hello" in content or "nav-link-accountlist" in content):
                    break
                if retailer == "kroger" and ("my account" in content or "sign out" in content):
                    break
                if retailer == "instacart" and ("log out" in content or "sign out" in content):
                    break
                if retailer == "walmart" and ("account" in content or "sign out" in content):
                    break
                if retailer == "target" and ("account" in content or "sign out" in content or "my target" in content):
                    break
            except Exception:
                pass
            time.sleep(3)
        ctx.close()
        print(f"✅ Saved profile at: {profile_dir}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--retailer", required=True, choices=["kroger","amazon","walmart","instacart","target"])
    ap.add_argument("--profile-dir", required=True, help="Path to persistent Chrome profile dir")
    args = ap.parse_args()
    ensure_profile(args.retailer, args.profile_dir)
