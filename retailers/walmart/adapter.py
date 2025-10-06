# retailers/walmart/adapter.py
from __future__ import annotations
import os
from core.retailers import RetailerAdapter, register


class WalmartAdapter(RetailerAdapter):
    slug = "walmart"
    display_name = "Walmart"
    profile_env = "WALMART_PROFILE_DIR"

    def search_and_capture(self, keyword: str, ctx) -> bool:
        """Execute Walmart search and capture with activity callback."""
        import sys
        # Add project root to path
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        sys.path.insert(0, project_root)
        
        # Import the Playwright runner
        from walmart_search_and_capture import search_and_capture as wm_search
        
        # Create activity callback that uses GUI's step method
        def activity_cb(kind: str, msg: str):
            # This will be called by the Walmart runner to report progress
            print(f"{kind.upper()}: {msg}")
        
        # Call the Playwright runner with proper parameters
        try:
            result = wm_search(
                root_logger=None,
                activity_cb=activity_cb,
                base_dir=ctx.output_dir,
                keyword=keyword,
                profile_dir=ctx.profile_dir,
                headless=False,  # Show browser for debugging
            )
            # Return True if HTML was saved
            return result.html_saved > 0
        except Exception as e:
            print(f"❌ Walmart adapter error: {e}")
            import traceback
            traceback.print_exc()
            return False


# Register on import
register(WalmartAdapter())
