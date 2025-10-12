#!/usr/bin/env python3
"""
Walmart preflight debugging script
Run this to test if the preflight checks are working correctly
"""

import os
import sys
import traceback

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

def test_preflight():
    """Test Walmart preflight checks"""
    try:
        print("🔍 Testing Walmart preflight checks...")

        # Test 1: Check environment variable
        profile_env = os.environ.get("WALMART_PROFILE_DIR")
        print(f"✅ WALMART_PROFILE_DIR: {profile_env or 'NOT SET'}")

        if not profile_env:
            print("❌ WALMART_PROFILE_DIR not set")
            return False

        # Test 2: Check profile directory exists and is writable
        if not os.path.exists(profile_env):
            print(f"❌ Profile directory does not exist: {profile_env}")
            return False

        # Test 3: Try to write to profile directory
        test_file = os.path.join(profile_env, ".test_write")
        try:
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
            print(f"✅ Profile directory writable: {profile_env}")
        except Exception as e:
            print(f"❌ Profile directory not writable: {e}")
            return False

        # Test 4: Check for Google/Chrome/Default
        if profile_env.rstrip("/").endswith("Google/Chrome/Default"):
            print("❌ Using real Chrome Default profile - SECURITY RISK")
            return False

        print("✅ All preflight checks passed!")
        return True

    except Exception as e:
        print(f"❌ Preflight test failed: {e}")
        traceback.print_exc()
        return False

def test_scraper_import():
    """Test if walmart_search_and_capture can be imported"""
    try:
        print("🔍 Testing walmart_search_and_capture import...")
        from walmart_search_and_capture import search_and_capture
        print("✅ Import successful")
        return True
    except Exception as e:
        print(f"❌ Import failed: {e}")
        traceback.print_exc()
        return False

def test_scraper_call():
    """Test calling search_and_capture with minimal parameters"""
    try:
        print("🔍 Testing search_and_capture call...")

        # Import in the same process to avoid environment issues
        import sys
        sys.path.insert(0, '/Users/dan.maguire/Documents/Amazon_Scrape')
        from walmart_search_and_capture import search_and_capture

        def dummy_activity_cb(kind, msg):
            print(f"[DUMMY] {kind.upper()}: {msg}")

        # Use a persistent debug directory instead of temp
        import os
        debug_dir = "/Users/dan.maguire/Documents/Amazon_Scrape/debug_output"
        os.makedirs(debug_dir, exist_ok=True)

        # Create a timestamped subdirectory for this run
        import time
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        run_dir = os.path.join(debug_dir, f"debug_run_{timestamp}")

        print(f"📁 Using persistent debug dir: {run_dir}")
        print(f"📄 Logs will be at: {run_dir}/walmart_test_steps.jsonl")

        try:
            result = search_and_capture(
                root_logger=None,
                activity_cb=dummy_activity_cb,
                base_dir=run_dir,
                keyword="test",
                profile_dir=os.environ.get("WALMART_PROFILE_DIR"),
                headless=False,
            )

            print(f"✅ Call successful: {result}")
            print(f"🎯 Check logs at: {run_dir}/walmart_test_steps.jsonl")
            return True

        except Exception as e:
            print(f"❌ Call failed: {e}")
            import traceback
            traceback.print_exc()
            print(f"🎯 Check logs at: {run_dir}/walmart_test_steps.jsonl")
            return False

    except Exception as e:
        print(f"❌ Test call failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("WALMART SCRAPER DEBUGGING")
    print("=" * 60)

    # Test 1: Environment and preflight
    if not test_preflight():
        print("\n❌ Preflight checks failed - fix these first!")
        sys.exit(1)

    # Test 2: Import
    if not test_scraper_import():
        print("\n❌ Import failed - check dependencies!")
        sys.exit(1)

    # Test 3: Function call (this will fail if PX appears, but that's expected)
    print("\n🔍 Testing function call (may fail on PX, but preflight should work)...")
    test_scraper_call()

    print("\n" + "=" * 60)
    print("DEBUGGING COMPLETE")
    print("=" * 60)
