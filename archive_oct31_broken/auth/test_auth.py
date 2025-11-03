# Test script for the retailer authentication helper
import os
import sys
import json
from pathlib import Path

# Add the parent directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth.gui_helper import get_profile_dir, set_profile_dir, load_profile_config

def test_profile_config():
    """Test the profile configuration functions."""
    # Load the current configuration
    config = load_profile_config()
    print("Current configuration:")
    print(json.dumps(config, indent=2))
    
    # Test getting a profile directory
    kroger_profile = get_profile_dir("kroger")
    print(f"Kroger profile directory: {kroger_profile}")
    
    # Test setting a profile directory
    test_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "profiles",
        "test"
    )
    set_profile_dir("test", test_dir)
    print(f"Set test profile directory to: {test_dir}")
    
    # Verify the change
    config = load_profile_config()
    print("Updated configuration:")
    print(json.dumps(config, indent=2))
    
    # Clean up
    if "test" in config:
        del config["test"]
        from auth.gui_helper import save_profile_config
        save_profile_config(config)
        print("Cleaned up test profile")

if __name__ == "__main__":
    test_profile_config()
