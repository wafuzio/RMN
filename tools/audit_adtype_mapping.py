#!/usr/bin/env python3
import json, re, sys
from pathlib import Path
from typing import Dict, Any, Tuple, List

ROOT = Path(__file__).resolve().parents[1]

# Canonical retailer folder contracts (must match utils/path_taxonomy.py)
ALLOWED_FOLDERS = {
    "kroger": {"TOA", "Skyscraper", "Carousel", "Display_Ads", "Main", "runs"},
    "walmart": {"SBA", "SBV", "Tile_Takeover", "Main", "runs"},
    "instacart": {"Shoppable_Display_Ads", "Shoppable_Video_Ads", "Shoppable_Recipe_Ads", "Display_Ads", "Main", "runs"},
    "amazon": {"Sponsored_Brand", "Sponsored_Product", "Sponsored_Display", "Sponsored_Brand_Cards", "Sponsored_Brand_Video", "Sponsored_Carousel", "Main", "runs"},
}

# JSON ad.type → folder mapping only when they differ
ADTYPE_TO_FOLDER = {
    ("kroger", "CuratedCarousel"): "Carousel",
    # Else JSON ad.type = folder name 1:1
}

def folder_for_adtype(retailer: str, ad_type: str) -> str:
    return ADTYPE_TO_FOLDER.get((retailer, ad_type), ad_type)

# ISO 8601 with timezone (Z or offset)
ISO_TZ = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+\-]\d{2}:\d{2})$")

# Standard filename format:
# <retailer>__<advertiser>__<ad_type>__<client>__<search_term>__DYYYY-MM-DD_THH-MM.SS_<index>.<ext>
FILENAME_RE = re.compile(
    r"""^(?P<retailer>[a-z0-9]+)__            # retailer (lowercase)
         (?P<advertiser>[a-z0-9_]+)__         # advertiser
         (?P<adtype>[a-z0-9_]+)__             # ad_type (lowercase underscore)
         (?P<client>[a-z0-9_]+)__             # client
         (?P<term>[a-z0-9_]+)__               # search term
         D(?P<date>\d{4}-\d{2}-\d{2})_T(?P<time>\d{2}-\d{2}\.\d{2})_   # date/time
         (?P<idx>\d+)\.(?P<ext>png|jpg|jpeg|webp)$                      # index.ext
    """,
    re.VERBOSE
)

def normalize_adtype_token(json_ad_type: str, retailer: str) -> str:
    """
    Convert JSON ad.type to the filename token format (lowercase underscores).
    Example:
      'Tile_Takeover' -> 'tile_takeover'
      'CuratedCarousel' -> 'curatedcarousel' (filename examples typically don't keep casing)
      'Sponsored_Brand' -> 'sponsored_brand'
    """
    token = json_ad_type.replace(" ", "_")
    # Preserve underscores (Tile_Takeover, Shoppable_Display_Ads) and lower
    token = token.replace("-", "_").strip().lower()
    return token

def audit_retailer(retailer: str) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """
    Returns a mapping keyed by (retailer, ad_type) with aggregate results:
      {
        (retailer, ad_type): {
           "ads_seen": int,
           "json_type_ok": int,
           "folder_ok": int,
           "image_exists": int,
           "filename_ok": int,
           "issues": set([...])
        },
        ...
      }
    """
    res: Dict[Tuple[str, str], Dict[str, Any]] = {}
    root = ROOT / "output" / retailer
    if not root.exists():
        return res

    # Find Kroger/Walmart nested runs JSON; Instacart/Amazon may vary but we try */runs/*/run_results_*.json
    run_jsons = sorted(root.glob("*/runs/*/run_results_*.json"))
    # Allow flat runs as fallback (older layouts)
    if not run_jsons:
        run_jsons = sorted(root.glob("*/runs/run_results_*.json"))

    for run_json in run_jsons:
        try:
            data = json.loads(run_json.read_text())
        except Exception as e:
            # Skip unreadable
            continue

        # Top-level checks
        retailer_ok = str(data.get("retailer", "")).lower() == retailer
        ts_ok = bool(ISO_TZ.match(data.get("timestamp", "")))
        run_id_ok = isinstance(data.get("run_id"), str) and data["run_id"].isdigit() and len(data["run_id"]) == 14

        # Walk ads
        for ad in data.get("ads", []):
            ad_type = ad.get("type")
            if not isinstance(ad_type, str):
                continue

            key = (retailer, ad_type)
            bucket = res.setdefault(key, {
                "ads_seen": 0,
                "json_type_ok": 0,
                "folder_ok": 0,
                "image_exists": 0,
                "filename_ok": 0,
                "issues": set(),
            })
            bucket["ads_seen"] += 1

            # JSON ad.type canonical check (simple presence plus retailer match)
            if retailer_ok:
                bucket["json_type_ok"] += 1

            img_path = ad.get("image_path") or ad.get("screenshot")
            if not img_path:
                bucket["issues"].add("missing_image_path")
                continue

            # Folder check
            try:
                folder = img_path.split("/", 1)[0]
            except Exception:
                folder = ""
            expected_folder = folder_for_adtype(retailer, ad_type)
            allowed = ALLOWED_FOLDERS.get(retailer, set())

            if folder == expected_folder and folder in allowed:
                bucket["folder_ok"] += 1
            else:
                bucket["issues"].add(f"folder_mismatch:{folder}!={expected_folder}")

            # File existence
            # Build client root from run_json: output/<retailer>/<client>/runs/<run_id>/run_results_*.json
            # Go up three levels to client dir: run_id -> runs -> client
            client_root = run_json.parent.parent.parent.resolve()  # <run_id> -> runs -> <client>
            img_file = (client_root / img_path).resolve()
            if img_file.exists():
                bucket["image_exists"] += 1
            else:
                bucket["issues"].add("missing_file_on_disk")

            # Filename pattern + ad_type token
            fn = img_file.name
            m = FILENAME_RE.match(fn)
            if not m:
                bucket["issues"].add("filename_pattern_mismatch")
            else:
                # filename retailer must match normalized retailer
                if m.group("retailer") != retailer:
                    bucket["issues"].add(f"filename_retailer_mismatch:{m.group('retailer')}")
                # ad type token check
                expected_token = normalize_adtype_token(ad_type, retailer)
                if m.group("adtype") == expected_token:
                    bucket["filename_ok"] += 1
                else:
                    bucket["issues"].add(f"filename_adtype_mismatch:{m.group('adtype')}!= {expected_token}")

    return res

def main():
    final: Dict[str, Dict[Tuple[str, str], Dict[str, Any]]] = {}
    for r in ("kroger", "walmart", "instacart", "amazon"):
        final[r] = audit_retailer(r)

    # Print a terse matrix first
    print("Retailer Ad-Type Mapping Audit (JSON + Filename + Folder):")
    for r in ("kroger", "walmart", "instacart", "amazon"):
        items = final[r]
        if not items:
            print(f"- {r}: no runs found")
            continue
        for (ret, adt), agg in sorted(items.items()):
            print(f"  - {ret}/{adt}: ads={agg['ads_seen']} json_ok={agg['json_type_ok']} folder_ok={agg['folder_ok']} "
                  f"image_exists={agg['image_exists']} filename_ok={agg['filename_ok']} issues={sorted(agg['issues'])}")

    # Build a checklist summary per retailer/ad_type
    print("\nChecklist Summary:")
    for r in ("kroger", "walmart", "instacart", "amazon"):
        items = final[r]
        if not items:
            print(f"- {r}: no data")
            continue
        print(f"- {r}:")
        for (ret, adt), agg in sorted(items.items()):
            ok_json = agg["json_type_ok"] == agg["ads_seen"] and agg["ads_seen"] > 0
            ok_folder = agg["folder_ok"] == agg["ads_seen"] and agg["ads_seen"] > 0
            ok_file = agg["image_exists"] == agg["ads_seen"] and agg["ads_seen"] > 0
            ok_name = agg["filename_ok"] == agg["ads_seen"] and agg["ads_seen"] > 0
            status = []
            status.append("JSON-type OK" if ok_json else "JSON-type FAIL")
            status.append("Folder OK" if ok_folder else "Folder FAIL")
            status.append("Image exists" if ok_file else "Image MISSING")
            status.append("Filename OK" if ok_name else "Filename FAIL")
            note = f"issues: {', '.join(sorted(agg['issues']))}" if agg["issues"] else ""
            print(f"  - {adt}: {' | '.join(status)} {note}")

if __name__ == "__main__":
    main()
