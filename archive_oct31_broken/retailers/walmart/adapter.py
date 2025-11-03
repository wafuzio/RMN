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

    def collect_pairs_for_run(self, ctx, run_start_ts: float):
        """Collect JSON/HTML pairs from the most recent run."""
        import glob
        # Use ctx.runs_dir if available, otherwise fall back to output_dir/runs
        runs = getattr(ctx, "runs_dir", None) or os.path.join(ctx.output_dir, "runs")
        print(f"[walmart adapter] collect_pairs_for_run: searching in {runs}")
        jsons = sorted([p for p in glob.glob(os.path.join(runs, "run_results_*.json"))
                        if os.path.getmtime(p) >= run_start_ts - 2],
                       key=os.path.getmtime)
        print(f"[walmart adapter] found {len(jsons)} run_results JSON files")
        pairs = []
        for j in jsons:
            h = j.replace("run_results_", "search_results_").replace(".json", ".html")
            if os.path.exists(h):
                pairs.append((j, h))
                print(f"[walmart adapter] paired: {os.path.basename(j)} + {os.path.basename(h)}")
            else:
                print(f"[walmart adapter] missing HTML for: {os.path.basename(j)}")
        print(f"[walmart adapter] returning {len(pairs)} pairs")
        return pairs

    def extract_images(self, json_path: str, html_path: str, ctx) -> Dict[str, Any]:
        """
        Extract images from Walmart HTML (screenshots already captured during scrape).
        Returns: {"toa": int, "sky": int, "car": int, "log": str|None}
        """
        # Walmart captures screenshots during search_and_capture, so no additional extraction needed
        # Just return counts based on what's in the runs directory
        import glob
        runs_dir = os.path.dirname(json_path)
        
        # Count existing screenshots by type
        toa_count = len(glob.glob(os.path.join(runs_dir, "*_top_banner_*.png")))
        sba_count = len(glob.glob(os.path.join(runs_dir, "*_sba_*.png")))
        tile_count = len(glob.glob(os.path.join(runs_dir, "*_tile_takeover_*.png")))
        sbv_count = len(glob.glob(os.path.join(runs_dir, "*_sbv_*.png")))
        
        total = toa_count + sba_count + tile_count + sbv_count
        
        return {
            "toa": toa_count,
            "sky": sba_count + tile_count,  # Map to "sky" for GUI compatibility
            "car": sbv_count,  # Map to "car" for GUI compatibility
            "log": None
        }


# Register on import
register(WalmartAdapter())
