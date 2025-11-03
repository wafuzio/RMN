#!/usr/bin/env python3
import os, sys, time, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from walmart_search_and_capture import search_and_capture, PROFILE_ENV

def main():
    base = Path(__file__).parent.parent / "output" / "walmart" / "adapter_test"
    base.mkdir(parents=True, exist_ok=True)
    prof = os.environ.get(PROFILE_ENV)
    print(f"Profile: {prof}")
    res = search_and_capture(
        root_logger=None,
        activity_cb=lambda k, m: print(f"[{k}] {m}"),
        base_dir=str(base),
        keyword="blue bunny",
        profile_dir=prof,
        headless=True,
    )
    print("shots:", len(res.shots), "assets:", len(res.assets))
    print("meta:", json.dumps(res.meta, indent=2))

if __name__ == "__main__":
    sys.exit(main() or 0)
