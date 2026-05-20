#!/usr/bin/env python3
"""
Quick test script to capture traffic with mitmproxy.

Usage:
1. Terminal 1: .venv/bin/mitmproxy -p 8080
2. Terminal 2: .venv/bin/python3 test_mitm_capture.py
"""

from playwright.sync_api import sync_playwright
import time

def test_capture():
    print("🔍 Starting browser with mitmproxy...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome",
            headless=False,
            proxy={
                "server": "http://127.0.0.1:8080"
            }
        )
        
        context = browser.new_context(
            ignore_https_errors=True  # Ignore cert errors for first run
        )
        
        page = context.new_page()
        
        print("📡 Navigating to walmart.com...")
        print("   (Check mitmproxy terminal for traffic)")
        
        page.goto("https://www.walmart.com", wait_until="networkidle")
        
        print("✅ Page loaded. Check mitmproxy for captured requests.")
        print("   Press Enter to close browser...")
        input()
        
        browser.close()
        print("✅ Done! Check mitmproxy for all captured traffic.")

if __name__ == "__main__":
    test_capture()
