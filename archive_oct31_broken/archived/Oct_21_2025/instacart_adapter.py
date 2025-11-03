# retailers/instacart/adapter.py
from __future__ import annotations
import os, glob, time, subprocess
from datetime import datetime
from core.retailers import RetailerAdapter, register


class InstacartAdapter(RetailerAdapter):
    slug = "instacart"
    display_name = "Instacart"
    profile_env = "INSTACART_PROFILE_DIR"

    def search_and_capture(self, keyword: str, ctx) -> bool:
        """Execute Instacart search and capture HTML/JSON."""
        # Create debug log in output directory
        debug_log = os.path.join(ctx.output_dir, "adapter_debug.log")
        os.makedirs(ctx.output_dir, exist_ok=True)
        
        def log(msg):
            print(msg)
            try:
                from datetime import datetime
                with open(debug_log, 'a', encoding='utf-8') as f:
                    f.write(f"{datetime.now().isoformat()} {msg}\n")
            except:
                pass
        
        log(f"=== ADAPTER START: {keyword} ===")
        log(f"Output dir: {ctx.output_dir}")
        log(f"Profile dir: {ctx.profile_dir}")
        
        try:
            import sys
            # Add project root to path
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            sys.path.insert(0, project_root)
            log(f"Project root: {project_root}")
            
            # Import the search_and_capture function from root directory
            log("Attempting import...")
            from instacart_search_and_capture import search_and_capture
            log("✅ Import successful")
            
            # Get store from environment (default: publix)
            store = os.environ.get('INSTACART_STORE', 'publix')
            log(f"Store: {store}")
            
            # NEW: Ensure scraper sees the same profile/store even when launched from the app
            if ctx.profile_dir and os.path.isdir(ctx.profile_dir):
                os.environ["INSTACART_PROFILE_DIR"] = ctx.profile_dir
                log(f"Injected INSTACART_PROFILE_DIR into env: {ctx.profile_dir}")
            else:
                log("⚠️ ctx.profile_dir missing or invalid; scraper may run without cookies")
            
            os.environ.setdefault("INSTACART_STORE", store)
            
            log("Calling search_and_capture...")
            result = search_and_capture(keyword, ctx.output_dir, store=store)
            log(f"Result: {result}")
            return result
            
        except Exception as e:
            log(f"❌ EXCEPTION in adapter: {type(e).__name__}: {e}")
            import traceback
            log(traceback.format_exc())
            return False

    def collect_pairs_for_run(self, ctx, run_start_ts: float):
        """Collect JSON/HTML pairs from the most recent run."""
        runs = os.path.join(ctx.output_dir, "runs")
        jsons = sorted([p for p in glob.glob(os.path.join(runs, "run_results_*.json"))
                        if os.path.getmtime(p) >= run_start_ts - 2],
                       key=os.path.getmtime)
        pairs = []
        for j in jsons:
            h = j.replace("run_results_", "search_results_").replace(".json", ".html")
            if os.path.exists(h):
                pairs.append((j, h))
        return pairs
    def extract_images(self, json_path: str, html_path: str, ctx) -> dict:
        """
        Count screenshots that were already captured during search_and_capture.
        
        NOTE: As of the latest update, instacart_search_and_capture.py now takes
        screenshots during the same page load as HTML/JSON extraction. This ensures
        perfect synchronization between screenshots and extracted data.
        
        This method now just counts the screenshots that were already created,
        rather than re-navigating and creating new ones.
        """
        import glob
        from datetime import datetime
        import os, time
        
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(ctx.logs_dir, exist_ok=True)
        log_path = os.path.join(ctx.logs_dir, f"image_extract_{ts}.log")
        pair_start = time.time()

        # Count images with a forgiving window (5 min back)
        slack_seconds = 300
        horizon = pair_start - slack_seconds

        def recent_pngs(leaf: str) -> list:
            d = os.path.join(ctx.output_dir, leaf)
            return [
                p for p in glob.glob(os.path.join(d, "*.png"))
                if os.path.getmtime(p) >= horizon
            ]

        # Instacart folders
        toa_files = []
        toa_files += recent_pngs("Shoppable_Display_Ads")
        toa_files += recent_pngs("Shoppable_Video_Ads")
        toa_files += recent_pngs("Shoppable_Recipe_Ads")
        toa_files += recent_pngs("Main")

        sky_files = []
        sky_files += recent_pngs("Display_Ads")

        # Log what we counted
        with open(log_path, "w", encoding="utf-8") as lf:
            lf.write(f"=== Instacart Screenshot Count {datetime.now().isoformat()} ===\n")
            lf.write(f"NOTE: Screenshots captured during search_and_capture (same page load)\n\n")
            lf.write(f"Counted files (since {datetime.fromtimestamp(horizon).isoformat()}):\n")
            lf.write(f"  Shoppable Ads: {len(toa_files)}\n")
            for p in sorted(toa_files)[:10]:
                lf.write(f"    - {os.path.basename(p)}\n")
            lf.write(f"  Display Ads: {len(sky_files)}\n")
            for p in sorted(sky_files)[:10]:
                lf.write(f"    - {os.path.basename(p)}\n")
            lf.write(f"=== END {datetime.now().isoformat()} ===\n")

        return {
            "toa": len(toa_files),
            "sky": len(sky_files),
            "car": 0,
            "log": log_path,
        }


# Register on import
register(InstacartAdapter())
