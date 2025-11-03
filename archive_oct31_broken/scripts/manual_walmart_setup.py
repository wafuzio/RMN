#!/usr/bin/env python3
"""
Manual Walmart profile setup - keeps browser open for CAPTCHA solving.
"""
import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

# Profile directory
PROFILE_DIR = os.environ.get('WALMART_PROFILE_DIR') or os.path.expanduser("~/Documents/Amazon_Scrape/profiles/walmart")

def main():
    print("=" * 60)
    print("Walmart Profile Setup - Manual CAPTCHA Solving")
    print("=" * 60)
    print(f"Profile directory: {PROFILE_DIR}")
    print()
    print("INSTRUCTIONS:")
    print("1. Browser will open to walmart.com")
    print("2. If you see 'Robot or human?' CAPTCHA:")
    print("   - Press and hold the button until it turns green")
    print("   - Wait for it to verify")
    print("3. Browse walmart.com naturally:")
    print("   - Search for a product (e.g., 'milk')")
    print("   - Click on a product")
    print("   - Scroll around")
    print("4. When done, press Ctrl+C in this terminal to close")
    print()
    print("=" * 60)
    input("Press Enter to open browser...")
    
    os.makedirs(PROFILE_DIR, exist_ok=True)
    
    with sync_playwright() as p:
        print("\n🌐 Opening browser...")
        context = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=False,
            viewport={'width': 1366, 'height': 768},
            locale='en-US',
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
            ],
            ignore_default_args=["--enable-automation"],
        )
        
        page = context.pages[0] if context.pages else context.new_page()
        
        # Navigate to Walmart
        print("📍 Navigating to walmart.com...")
        page.goto("https://www.walmart.com/", wait_until='domcontentloaded')
        
        print()
        print("✅ Browser is open!")
        print()
        print("👉 Solve the CAPTCHA if it appears")
        print("👉 Browse around naturally")
        print("👉 Press Ctrl+C when done to save and close")
        print()
        
        try:
            # Keep browser open until user interrupts
            page.wait_for_timeout(600000)  # 10 minutes max
        except KeyboardInterrupt:
            print("\n\n💾 Saving session and closing browser...")
        
        context.close()
        
    print()
    print("=" * 60)
    print("✅ Session saved!")
    print()
    print("Next steps:")
    print(f"1. Add to ~/.zshrc:")
    print(f"   export WALMART_PROFILE_DIR=\"{PROFILE_DIR}\"")
    print()
    print("2. Reload shell:")
    print("   source ~/.zshrc")
    print()
    print("3. Test the scraper:")
    print("   python3 keyword_input.py")
    print("=" * 60)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Setup cancelled")
        sys.exit(0)
