# Test script for the Amazon adapter
import os
import sys
from core.retailers import list_adapters, get as get_retailer_adapter

# Import the adapter to ensure it's registered
import retailers.amazon.adapter

def test_amazon_adapter():
    """Test that the Amazon adapter is registered correctly."""
    print("Testing Amazon adapter registration...")
    
    # List all registered adapters
    adapters = list_adapters()
    adapter_names = [a.display_name for a in adapters]
    print(f"Registered adapters: {adapter_names}")
    
    # Check if Amazon adapter is registered
    if "Amazon" in adapter_names:
        print("✅ Amazon adapter is registered correctly.")
    else:
        print("❌ Amazon adapter is not registered.")
        return False
    
    # Get the Amazon adapter
    try:
        amazon_adapter = get_retailer_adapter("amazon")
        print(f"✅ Retrieved Amazon adapter: {amazon_adapter.display_name}")
        print(f"Profile environment variable: {amazon_adapter.profile_env}")
        return True
    except Exception as e:
        print(f"❌ Error retrieving Amazon adapter: {e}")
        return False

if __name__ == "__main__":
    test_amazon_adapter()
