#!/usr/bin/env python3
"""
Quick diagnostic to test Instacart from GUI context
"""
import os
import sys

print("=" * 60)
print("Instacart Diagnostic Test")
print("=" * 60)

# Check environment
print(f"INSTACART_PROFILE_DIR: {os.environ.get('INSTACART_PROFILE_DIR')}")
print(f"INSTACART_STORE: {os.environ.get('INSTACART_STORE')}")
print()

# Try to import and run
try:
    from retailers.instacart.adapter import InstacartAdapter
    from core.run_context import RunContext
    
    profile_dir = os.environ.get('INSTACART_PROFILE_DIR')
    if not profile_dir:
        print("❌ INSTACART_PROFILE_DIR not set!")
        sys.exit(1)
    
    adapter = InstacartAdapter()
    print(f"✅ Adapter loaded: {adapter.display_name}")
    
    ctx = RunContext(
        retailer='instacart',
        client='diagnostic_test',
        base_dir=os.getcwd(),
        output_dir='output/instacart/diagnostic_test',
        runs_dir='output/instacart/diagnostic_test/runs',
        logs_dir='logs/instacart',
        profile_dir=profile_dir,
        script_dir=os.getcwd()
    )
    
    print(f"✅ Context created")
    print(f"   Profile dir: {ctx.profile_dir}")
    print(f"   Output dir: {ctx.output_dir}")
    print()
    
    keyword = "test"
    print(f"Running search_and_capture for '{keyword}'...")
    print("-" * 60)
    
    result = adapter.search_and_capture(keyword, ctx)
    
    print("-" * 60)
    print(f"Result: {result}")
    
    if result:
        print("✅ SUCCESS!")
    else:
        print("❌ FAILED!")
        sys.exit(1)
        
except Exception as e:
    print(f"❌ Exception: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
