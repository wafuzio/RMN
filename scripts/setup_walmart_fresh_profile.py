#!/usr/bin/env python3
"""
Walmart Fresh Profile Setup — Manual Mode

Deletes the existing profile and creates a clean one at the same fixed path
so that launcher.env / .zshrc don't need to change.

Opens a browser with the exact fingerprint settings used by the scraper.
YOU do all the browsing, scrolling, and signing in. When done, press Enter
in this terminal to save the profile.

Usage:
    .venv/bin/python3 scripts/setup_walmart_fresh_profile.py
"""

import os
import sys
import shutil
from playwright.sync_api import sync_playwright

PROFILE_DIR = os.path.expanduser("~/Documents/Amazon_Scrape/profiles/walmart")


def check_login_status(page):
    """Check if user is logged in."""
    try:
        indicator = page.locator('[data-testid="logged-in-account-button-name"]').first
        return indicator.count() > 0 and indicator.is_visible(timeout=2000)
    except:
        return False


def setup_fresh_profile(profile_dir):
    """Delete old profile, open browser with scraper-identical settings. Human does all browsing."""
    print("=" * 60)
    print("Walmart Fresh Profile Setup")
    print("=" * 60)
    print(f"Profile directory: {profile_dir}")
    print()

    if os.path.exists(profile_dir):
        print(f"Existing profile found — will delete it before opening the browser.")
    else:
        print("No existing profile — will create fresh.")

    print()
    print("Browser will open at walmart.com. YOU:")
    print("  - Browse naturally, scroll, click around")
    print("  - Sign in to your Walmart account")
    print("  - When done, come back here and press Enter")
    print()
    print("=" * 60)
    input("Press Enter to delete old profile and open browser...")

    # Delete old profile so we start completely clean
    if os.path.exists(profile_dir):
        shutil.rmtree(profile_dir)
        print(f"Deleted: {profile_dir}")
    os.makedirs(profile_dir, exist_ok=True)

    with sync_playwright() as p:
        print("\nOpening browser...")

        # IDENTICAL settings to the main scraper's _launch() function.
        # Fingerprint consistency is critical — PX will flag a profile warmed
        # up with different GPU/viewport/sandbox settings.
        context = p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=False,
            channel='chrome',              # Real Chrome = correct JA3 TLS fingerprint
            viewport={'width': 1366, 'height': 768},
            locale='en-US',
            timezone_id='America/New_York',
            chromium_sandbox=True,         # CRITICAL: removes --no-sandbox banner
            args=[
                '--use-angle=metal',           # Force ANGLE→Metal (macOS GPU)
                '--enable-gpu-rasterization',   # Prefer GPU raster
                '--ignore-gpu-blocklist',       # Don't let Chrome disable GPU
                '--disable-focus-on-load',
                '--noerrdialogs',
            ],
            ignore_default_args=['--enable-automation'],  # Prevents navigator.webdriver=true
        )

        # Match the main scraper's webdriver override
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://www.walmart.com/", wait_until='domcontentloaded')

        print("\nBrowser is open. Browse and sign in, then come back here.")
        input("Press Enter when done to save and close the browser...")

        logged_in = check_login_status(page)
        print("\nSaving profile and closing browser...")
        context.close()

    # Verify profile was written
    checks = {
        'Cookies':                  os.path.join(profile_dir, 'Default', 'Cookies'),
        'Preferences':              os.path.join(profile_dir, 'Default', 'Preferences'),
        'Network Persistent State': os.path.join(profile_dir, 'Default', 'Network Persistent State'),
    }
    print("\nVerifying profile on disk...")
    all_ok = True
    for label, path in checks.items():
        exists = os.path.exists(path)
        size = os.path.getsize(path) if exists else 0
        status = f"{size:,} bytes" if exists and size > 0 else "MISSING"
        print(f"  {label:30s} {status}")
        if not exists or size == 0:
            all_ok = False

    print("\n" + "=" * 60)
    print("Profile Setup Complete!")
    print("=" * 60)
    print(f"  Profile:   {profile_dir}")
    print(f"  Logged in: {'Yes' if logged_in else 'Not detected'}")
    print(f"  Cookies:   {'OK' if all_ok else 'WARNING — profile may be empty'}")
    print()
    print("Next step: Restart the GUI:")
    print("  .venv/bin/python3 keyword_input.py")
    print("=" * 60)


def main():
    try:
        setup_fresh_profile(PROFILE_DIR)
    except KeyboardInterrupt:
        print("\n\nSetup cancelled.")
        sys.exit(0)
    except Exception as e:
        print(f"\nError during setup: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
