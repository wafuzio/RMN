# core/retailers.py
from __future__ import annotations
from typing import Dict, List

class RetailerAdapter:
    slug: str = "kroger"
    display_name: str = "Kroger"
    profile_env: str = "KROGER_PROFILE_DIR"  # env var to read default profile

    # Search step: write JSON/HTML to ctx.output_dir
    def search_and_capture(self, keyword: str, ctx) -> bool:
        raise NotImplementedError

    # Return list[(json_path, html_path)] for files created since run_start_ts
    def collect_pairs_for_run(self, ctx, run_start_ts: float):
        raise NotImplementedError

    # Extract images; return counts and log path
    # return {"toa": int, "sky": int, "car": int, "log": str}
    def extract_images(self, json_path: str, html_path: str, ctx) -> dict:
        raise NotImplementedError

# Simple registry
_REG: Dict[str, RetailerAdapter] = {}

def register(adapter: RetailerAdapter):
    _REG[adapter.slug] = adapter

def get(slug: str) -> RetailerAdapter:
    return _REG[slug]

def list_adapters() -> List[RetailerAdapter]:
    return list(_REG.values())
