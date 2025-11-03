#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.brands import canonicalize

WALMART_ROOT = ROOT / "output" / "walmart"
AD_FOLDERS = ("SBA", "SBV", "Tile_Takeover")

# Filename schema:
# <retailer>__<advertiser>__<ad_type>__<client>__<search_term>__DYYYY-MM-DD_THH-MM.SS_<index>.<ext>
FILENAME_RE = re.compile(
    r"""^(?P<retailer>[a-z0-9]+)__             # retailer
         (?P<advertiser>[a-z0-9_]+)__          # advertiser
         (?P<adtype>[a-z0-9_]+)__              # ad type token (lower)
         (?P<client>[a-z0-9_]+)__              # client token
         (?P<term>[a-z0-9_]+)__                # keyword token
         D(?P<date>\d{4}-\d{2}-\d{2})_T(?P<time>\d{2}-\d{2}\.\d{2})_(?P<idx>\d+)\.(?P<ext>png|jpg|jpeg|webp)$
    """,
    re.VERBOSE
)

TYPE_MAP = {
    "sba": "SBA",
    "sbv": "SBV",
    "tile_takeover": "Tile_Takeover",
}

def to_iso_z_from_run_id(run_id: str) -> str:
    dt = datetime.strptime(run_id, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")

def run_id_from_tokens(date: str, time: str) -> str:
    # date: YYYY-MM-DD, time: HH-MM.SS -> YYYYMMDDHHMMSS
    hh, mm_ss = time.split("-", 1)
    mm, ss = mm_ss.split(".", 1)
    y, m, d = date.split("-")
    return f"{y}{m}{d}{hh}{mm}{ss}"

def adtype_to_canonical(token: str) -> str:
    return TYPE_MAP.get(token, token.upper())

def slug_to_words(s: str) -> str:
    return s.replace("_", " ").strip()

def ensure_run_json(client_root: Path, run_id: str, client: str, keyword_token: str) -> Path:
    run_dir = client_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    run_json = run_dir / f"run_results_{run_id}.json"
    if not run_json.exists():
        payload = {
            "retailer": "walmart",
            "client": client,
            "keyword": slug_to_words(keyword_token),
            "timestamp": to_iso_z_from_run_id(run_id),
            "run_id": run_id,
            "ads": [],
        }
        run_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return run_json

def load_run_json(p: Path) -> Dict[str, Any]:
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}

def ad_already_present(data: Dict[str, Any], rel_image_path: str) -> bool:
    return any(ad.get("image_path") == rel_image_path for ad in data.get("ads", []))

def build_ad_object(run_id: str, ad_index: int, ad_type: str, rel_image_path: str, brand_token: str, keyword_token: str) -> Dict[str, Any]:
    # De-slug and canonicalize brand
    de_slug = None if brand_token == "unknown" else slug_to_words(brand_token)
    brand = canonicalize(de_slug) if de_slug else None
    return {
        "id": f"walmart-{run_id}-{ad_index}",
        "type": ad_type,                  # SBA|SBV|Tile_Takeover
        "brand": brand,
        "brand_logo": None,
        "title": None,
        "description": None,
        "cta": None,
        "href": None,
        "image_url": None,
        "image_path": rel_image_path,     # e.g., "SBV/walmart__...png"
        "products": [],
        "metadata": {
            "slot": None,
            "keyword_token": keyword_token,
        },
    }

def process_image(img: Path, write: bool, backup: bool) -> Tuple[str, str]:
    # Expect output/walmart/<client>/<Folder>/<filename>
    try:
        client = img.parent.parent.name
        folder = img.parent.name
        client_root = img.parents[1]  # .../output/walmart/<client>
    except Exception:
        return ("skip", f"Unexpected path structure: {img}")

    if folder not in AD_FOLDERS:
        return ("skip", f"Not an ad folder: {img}")

    m = FILENAME_RE.match(img.name)
    if not m:
        return ("skip", f"Filename pattern mismatch: {img.name}")

    retailer = m.group("retailer")
    advertiser = m.group("advertiser")
    adtype_token = m.group("adtype")
    client_token = m.group("client")
    keyword_token = m.group("term")
    date = m.group("date")
    time = m.group("time")

    if retailer != "walmart":
        return ("skip", f"Not walmart retailer token: {retailer} for {img.name}")

    run_id = run_id_from_tokens(date, time)
    run_json = ensure_run_json(client_root, run_id, client, keyword_token)
    data = load_run_json(run_json)
    if not data:
        return ("error", f"Cannot load/initialize run JSON: {run_json}")

    # Force canonical top-level fields to be safe
    data["retailer"] = "walmart"
    data["client"] = client
    data["keyword"] = data.get("keyword") or slug_to_words(keyword_token)
    data["timestamp"] = data.get("timestamp") or to_iso_z_from_run_id(run_id)
    data["run_id"] = run_id
    if "ads" not in data or not isinstance(data["ads"], list):
        data["ads"] = []

    # Build ad object if not already present
    rel_image_path = f"{folder}/{img.name}"
    if ad_already_present(data, rel_image_path):
        return ("ok", f"Exists: {rel_image_path} in {run_json}")

    ad_type = adtype_to_canonical(adtype_token)
    ad_index = len(data["ads"]) + 1
    ad = build_ad_object(run_id, ad_index, ad_type, rel_image_path, advertiser, keyword_token)
    data["ads"].append(ad)

    if not write:
        return ("dry", f"Would ADD {rel_image_path} -> {run_json}")

    if backup:
        bak = run_json.with_suffix(run_json.suffix + ".bak_rebuild")
        if not bak.exists():
            bak.write_text(run_json.read_text())

    run_json.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return ("write", f"ADD {rel_image_path} -> {run_json}")

def main():
    ap = argparse.ArgumentParser(description="Batch rebuild Walmart canonical run JSONs from image files.")
    ap.add_argument("--client", type=str, default="", help="Limit to a single client (folder name under output/walmart)")
    ap.add_argument("--write", action="store_true", help="Write changes (default: dry-run)")
    ap.add_argument("--backup", action="store_true", help="Backup run JSON before writing")
    args = ap.parse_args()

    if not WALMART_ROOT.exists():
        print("No output/walmart found.")
        return

    clients = [d for d in WALMART_ROOT.iterdir() if d.is_dir()]
    if args.client:
        clients = [d for d in clients if d.name == args.client]

    total, added, skipped, errors = 0, 0, 0, 0
    for client_dir in clients:
        for folder in AD_FOLDERS:
            dirp = client_dir / folder
            if not dirp.exists():
                continue
            for img in sorted(dirp.iterdir()):
                if not img.is_file():
                    continue
                total += 1
                status, msg = process_image(img, write=args.write, backup=args.backup)
                print(f"{status.upper()}: {msg}")
                if status == "write":
                    added += 1
                elif status == "dry":
                    pass
                elif status == "ok":
                    skipped += 1
                elif status in ("skip", "error"):
                    errors += 1

    print(f"Done. Files scanned={total}, added={added}, skipped={skipped}, errors={errors}, mode={'WRITE' if args.write else 'DRY-RUN'}.")
if __name__ == "__main__":
    main()
