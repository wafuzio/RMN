import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
PROACTIV_RUNS_DIR = BASE_DIR / "output" / "amazon" / "Proactiv" / "runs"


def infer_slot(ad: dict) -> str:
    """Infer slot for legacy Sponsored_Display ads based on subtype.

    We only touch Sponsored_Display ads and map:
    - subtype contains "left_rail" -> "left_rail"
    - subtype contains "bottom" -> "bottom"
    - otherwise -> "top" (treated as top-of-page bucket)
    """
    t_raw = (ad.get("type") or ad.get("ad_type") or "").lower()
    if "sponsored_display" not in t_raw and "sponsored display" not in t_raw:
        return ad.get("slot") or ""

    # If already has a slot, keep it
    if ad.get("slot"):
        return ad["slot"]

    subtype_raw = (ad.get("subtype") or "").lower()
    if "left_rail" in subtype_raw:
        return "left_rail"
    if "bottom" in subtype_raw:
        return "bottom"
    # Fallback: for Proactiv legacy runs, treat remaining display ads as left rail
    return "left_rail"


def backfill_proactiv_slots() -> None:
    if not PROACTIV_RUNS_DIR.is_dir():
        print(f"No Proactiv runs dir found at {PROACTIV_RUNS_DIR}")
        return

    run_files = sorted(PROACTIV_RUNS_DIR.glob("run_results_amazon_Proactiv_*.json"))
    if not run_files:
        print(f"No Proactiv run_results JSON files found under {PROACTIV_RUNS_DIR}")
        return

    print(f"Found {len(run_files)} Proactiv run_results files to scan")

    updated_files = 0
    updated_ads_total = 0

    for fp in run_files:
        try:
            with fp.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"⚠️  Skipping {fp.name}: could not read JSON -> {e}")
            continue

        ads = data.get("ads")
        if not isinstance(ads, list):
            continue

        changed = False
        updated_ads = 0

        for ad in ads:
            if not isinstance(ad, dict):
                continue
            t_raw = (ad.get("type") or ad.get("ad_type") or "").lower()
            if "sponsored_display" not in t_raw and "sponsored display" not in t_raw:
                continue

            old_slot = ad.get("slot") or ""
            new_slot = infer_slot(ad)

            # Only write if we actually inferred something and it changed
            if new_slot and new_slot != old_slot:
                ad["slot"] = new_slot
                changed = True
                updated_ads += 1

        if changed:
            backup_path = fp.with_suffix(fp.suffix + ".bak")
            try:
                if not backup_path.exists():
                    fp.replace(backup_path)
                else:
                    # If backup already exists, don't overwrite; we'll still rewrite the main file
                    pass
            except Exception as e:
                print(f"⚠️  Could not create backup for {fp.name}: {e}")

            try:
                with fp.open("w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(f"✅ Updated {fp.name}: added/normalized slot for {updated_ads} Sponsored_Display ads")
                updated_files += 1
                updated_ads_total += updated_ads
            except Exception as e:
                print(f"❌ Failed to write updated JSON for {fp.name}: {e}")
        else:
            # No changes needed
            continue

    print(f"Done. Updated {updated_files} files, {updated_ads_total} Sponsored_Display ads.")


if __name__ == "__main__":
    backfill_proactiv_slots()
