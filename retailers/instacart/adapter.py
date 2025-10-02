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
        import sys
        # Add project root to path
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        sys.path.insert(0, project_root)
        
        # Import the search_and_capture function from root directory
        from instacart_search_and_capture import search_and_capture
        
        # Get store from environment (default: publix)
        store = os.environ.get('INSTACART_STORE', 'publix')
        
        return search_and_capture(keyword, ctx.output_dir, store=store)

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
        Extract ad images from Instacart HTML using screenshot script.
        
        This uses the same extractor infrastructure as Kroger/Amazon,
        but with Instacart-specific selectors.
        """
        # Use the main ad extractor script
        ad_script = os.path.join(ctx.script_dir, "extractors/screenshot_ad_images.py")
        toa_script = os.path.join(ctx.script_dir, "extractors/screenshot_toa_image.py")
        script = ad_script if os.path.exists(ad_script) else toa_script

        cmd = [
            os.sys.executable, script,
            "--json", json_path,
            "--html", html_path,
            "--output", ctx.output_dir,
            "--headless",
            "--no-lock",
            "--time-window", "45",
            "--browser-lock-timeout", "600",
        ]
        
        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        
        # Pass profile directory if available
        if ctx.profile_dir and os.path.isdir(ctx.profile_dir):
            cmd += ["--profile-dir", ctx.profile_dir]
            env[self.profile_env] = ctx.profile_dir
        
        # Pass store configuration
        store = os.environ.get('INSTACART_STORE', 'publix')
        env['INSTACART_STORE'] = store

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_dir = ctx.logs_dir
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, f"image_extract_{ts}.log")
        pair_start = time.time()

        with open(log_path, "w", encoding="utf-8") as lf:
            lf.write(f"=== START {datetime.now().isoformat()} ===\n")
            lf.write(f"CMD: {' '.join(cmd)}\nCWD: {ctx.script_dir}\n\n")
            proc = subprocess.Popen(
                cmd, env=env, cwd=ctx.script_dir,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
            )
            for line in iter(proc.stdout.readline, ""):
                lf.write(line)
            try:
                proc.wait(timeout=240)
            except subprocess.TimeoutExpired:
                proc.kill()
                lf.write("\n❌ Timeout: 240s\n")
            lf.write(f"Exit code: {proc.returncode}\n")
            lf.write(f"=== END {datetime.now().isoformat()} ===\n")

        def count(leaf: str) -> int:
            return len([p for p in glob.glob(os.path.join(ctx.output_dir, leaf, "*.png"))
                        if os.path.getmtime(p) >= pair_start - 1])

        return {"toa": count("TOA"), "sky": count("Skyscraper"), "car": count("Carousel"), "log": log_path}


# Register on import
register(InstacartAdapter())
