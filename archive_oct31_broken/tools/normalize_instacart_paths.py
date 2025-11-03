#!/usr/bin/env python3
import json, sys
from pathlib import Path

ROOT = Path("output/instacart")

REWRITES = {
    "Shoppable_Display_Ads/": "Shoppable_Display_Ad/",
    "Shoppable_Video_Ads/": "Shoppable_Video_Ad/",
    "Display_Ads/": "Display_Ad/",
}

def rewrite_path(p: str | None) -> str | None:
    if not p: return p
    for k, v in REWRITES.items():
        if p.startswith(k): return v + p[len(k):]
    return p

def process(jp: Path):
    try:
        data = json.loads(jp.read_text())
    except Exception:
        return 0
    ads = data.get("ads")
    if not isinstance(ads, list):
        return 0
    changed = 0
    for ad in ads:
        ip = ad.get("image_path")
        new = rewrite_path(ip)
        if new != ip:
            ad["image_path"] = new
            changed += 1
        vp = ad.get("video_path")
        newv = rewrite_path(vp)
        if newv != vp:
            ad["video_path"] = newv
            changed += 1
    if changed:
        jp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return changed

def main():
    count = 0
    for jp in ROOT.rglob("run_results_*.json"):
        count += process(jp)
    print(f"Updated {count} path entries")

if __name__ == "__main__":
    main()
