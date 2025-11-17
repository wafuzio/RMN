# retailers/walmart/adapter.py
from __future__ import annotations
import os
from typing import Dict, Any
from core.retailers import RetailerAdapter, register


class WalmartAdapter(RetailerAdapter):
    slug = "walmart"
    display_name = "Walmart"
    profile_env = "WALMART_PROFILE_DIR"

    def search_and_capture(self, keyword: str, ctx) -> Dict[str, Any]:
        """
        Execute Walmart search and capture with activity callback.
        
        Returns a dict:
            {'ok': bool, 'bail': bool, 'reason': str|None, 'result': CaptureResult|None}
        
        ok=True => success
        bail=True => do not retry (hard_block/px_locked/fatal)
        """
        import sys
        import traceback
        # Add project root to path
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        sys.path.insert(0, project_root)

        # Import the Playwright runner
        from walmart_search_and_capture import search_and_capture as core_sc
        try:
            from walmart_search_and_capture import DebugConfig
        except Exception:
            DebugConfig = None

        # Get context attributes safely
        activity_cb = getattr(ctx, "emit", None)  # GUI callback
        base_root = getattr(ctx, "runs_dir", None) or getattr(ctx, "output_dir", None) or getattr(ctx, "base_dir", None)
        profile_dir = getattr(ctx, "profile_dir", None)
        debug = getattr(ctx, "debug", None)

        # Call core scraper with direct parameters (safer than env mutation)
        result = core_sc(
            root_logger=None,
            activity_cb=activity_cb,
            base_dir=base_root,
            keyword=keyword,
            profile_dir=profile_dir,  # pass directly - overrides env
            headless=False,
            debug=debug if DebugConfig else None,
        )

        # Handle legacy bool return
        if isinstance(result, bool):
            return {'ok': bool(result), 'bail': False, 'reason': None, 'result': None}

        # Extract success and bail signals
        html_saved = int(getattr(result, "html_saved", 0) or 0)
        shots = getattr(result, "shots", []) or []
        ok = html_saved > 0 or len(shots) > 0
        
        meta = getattr(result, "meta", {}) or {}
        bail_reason = meta.get("bail")
        bail = bool(bail_reason)

        return {'ok': ok, 'bail': bail, 'reason': bail_reason, 'result': result}


# Register on import
register(WalmartAdapter())
