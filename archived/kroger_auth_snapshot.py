"""
Kroger Authentication Snapshot Utility

This script provides utilities to save and restore a complete authentication snapshot
including cookies, local storage, and session storage from a working Kroger login session.
"""

import os
import json
import time
from datetime import datetime
from playwright.sync_api import sync_playwright

# Constants
AUTH_SNAPSHOT_FILE = "kroger_auth.json"
USER_DATA_DIR = os.path.expanduser("~/ChromeProfiles/kroger_clean_profile")

def create_auth_snapshot(snapshot_file=AUTH_SNAPSHOT_FILE):
    """
    Creates a complete authentication snapshot from a working browser session.
    Captures cookies, localStorage, and sessionStorage.
    """
    with sync_playwright() as p:
        # Launch browser with persistent context
        context = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False,
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-infobars",
                "--disable-web-security",
            ]
        )
        
        page = context.pages[0] if context.pages else context.new_page()
        
        # Navigate to Kroger homepage
        page.goto("https://www.kroger.com/", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        
        # Check if we're logged in
        is_logged_in = "Sign In" not in page.content()
        
        if not is_logged_in:
            print("⚠️ Not logged in! Please log in manually before creating a snapshot.")
            print("Waiting 90 seconds for manual login...")
            
            # Try to click sign in
            try:
                page.click("text=Sign In")
                page.wait_for_timeout(1000)
                page.click('[data-testid="WelcomeMenuButtonSignIn"]')
            except TimeoutError as e:
                print("Timeout error clicking sign in: {}".format(e))
            except ValueError as e:
                print("Invalid selector for sign in: {}".format(e))
            
            page.wait_for_timeout(90000)  # 90 seconds for manual login
            
            # Check again if we're logged in
            is_logged_in = "Sign In" not in page.content()
            if not is_logged_in:
                print("❌ Still not logged in. Aborting snapshot creation.")
                context.close()
                return False
        
        # Collect authentication data
        auth_data = {
            "timestamp": datetime.now().isoformat(),
            "cookies": context.cookies(),
        }
        
        # Get localStorage and sessionStorage
        storage_states = {}
        try:
            # Get localStorage
            local_storage = page.evaluate("""() => {
                const items = {};
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    items[key] = localStorage.getItem(key);
                }
                return items;
            }""")
            storage_states["localStorage"] = local_storage
            
            # Get sessionStorage
            session_storage = page.evaluate("""() => {
                const items = {};
                for (let i = 0; i < sessionStorage.length; i++) {
                    const key = sessionStorage.key(i);
                    items[key] = sessionStorage.getItem(key);
                }
                return items;
            }""")
            storage_states["sessionStorage"] = session_storage
            
        except TimeoutError as e:
            print("⚠️ Timeout error capturing storage: {}".format(e))
        except ValueError as e:
            print("⚠️ Value error capturing storage: {}".format(e))
        
        auth_data["storageState"] = storage_states
        
        # Save the snapshot
        with open(snapshot_file, "w", encoding="utf-8") as f:
            json.dump(auth_data, f, indent=2)
        
        print("✅ Authentication snapshot saved to {}".format(snapshot_file))
        print("   - {} cookies captured".format(len(auth_data['cookies'])))
        print("   - {} localStorage items".format(len(storage_states.get('localStorage', {}))))
        print("   - {} sessionStorage items".format(len(storage_states.get('sessionStorage', {}))))
        
        context.close()
        return True

def restore_auth_snapshot(snapshot_file=AUTH_SNAPSHOT_FILE):
    """
    Restores authentication from a previously saved snapshot.
    """
    if not os.path.exists(snapshot_file):
        print("❌ Snapshot file {} not found".format(snapshot_file))
        return False
    
    try:
        with open(snapshot_file, "r", encoding="utf-8") as f:
            auth_data = json.load(f)
        
        cookies = auth_data.get("cookies", [])
        storage_state = auth_data.get("storageState", {})
        
        if not cookies:
            print("❌ No cookies found in snapshot")
            return False
        
        with sync_playwright() as p:
            # Launch browser with persistent context
            context = p.chromium.launch_persistent_context(
                user_data_dir=USER_DATA_DIR,
                headless=False,
                executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-infobars",
                    "--disable-web-security",
                ]
            )
            
            page = context.pages[0] if context.pages else context.new_page()
            
            # Add cookies
            context.add_cookies(cookies)
            print("✅ Restored {} cookies".format(len(cookies)))
            
            # Navigate to Kroger homepage
            page.goto("https://www.kroger.com/", wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            
            # Restore localStorage and sessionStorage if available
            if storage_state:
                local_storage = storage_state.get("localStorage", {})
                session_storage = storage_state.get("sessionStorage", {})
                
                # Set localStorage
                if local_storage:
                    for key, value in local_storage.items():
                        page.evaluate("""(key, value) => {
                            try {
                                localStorage.setItem(key, value);
                            } catch (e) {
                                console.error('Error setting localStorage', e);
                            }
                        }""", key, value)
                    print("✅ Restored {} localStorage items".format(len(local_storage)))
                
                # Set sessionStorage
                if session_storage:
                    for key, value in session_storage.items():
                        page.evaluate("""(key, value) => {
                            try {
                                sessionStorage.setItem(key, value);
                            } catch (e) {
                                console.error('Error setting sessionStorage', e);
                            }
                        }""", key, value)
                    print("✅ Restored {} sessionStorage items".format(len(session_storage)))
            
            # Refresh the page to apply all changes
            page.reload()
            page.wait_for_timeout(3000)
            
            # Check if we're logged in
            is_logged_in = "Sign In" not in page.content()
            
            if is_logged_in:
                print("✅ Successfully restored authentication! You are logged in.")
            else:
                print("❌ Authentication restoration failed. You are not logged in.")
            
            # Keep the browser open for a while to verify
            print("Browser will close in 10 seconds...")
            time.sleep(10)
            context.close()
            
            return is_logged_in
            
    except FileNotFoundError as e:
        print("❌ Snapshot file not found: {}".format(e))
        return False
    except json.JSONDecodeError as e:
        print("❌ Invalid snapshot file format: {}".format(e))
        return False
    except IOError as e:
        print("❌ Error reading snapshot file: {}".format(e))
        return False
    except ValueError as e:
        print("❌ Invalid snapshot data: {}".format(e))
        return False

def verify_login_status():
    """
    Verify if the current browser profile is logged into Kroger.
    """
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False,
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
            ]
        )
        
        page = context.pages[0] if context.pages else context.new_page()
        
        # Navigate to Kroger homepage
        page.goto("https://www.kroger.com/", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        
        # Check if we're logged in
        is_logged_in = "Sign In" not in page.content()
        
        if is_logged_in:
            print("✅ You are currently logged into Kroger")
        else:
            print("❌ You are NOT logged into Kroger")
        
        context.close()
        return is_logged_in

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Kroger Authentication Snapshot Utility")
    parser.add_argument("action", choices=["create", "restore", "verify"], 
                        help="Action to perform: create a new snapshot, restore from existing, or verify login status")
    
    args = parser.parse_args()
    
    if args.action == "create":
        create_auth_snapshot()
    elif args.action == "restore":
        restore_auth_snapshot()
    elif args.action == "verify":
        verify_login_status()
