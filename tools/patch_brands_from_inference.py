#!/usr/bin/env python3
"""
Batch-patch brand fields in run JSON files using the same inference tiers
as _infer_brand_from_ad() in builder_server_v2.py (Tiers 1-3 only — no LLM).

Tiers applied:
  1  - Creative fingerprint lookup (manifest creative_fingerprints index)
  1.5- Product title scan (SBV carousel products)
  2  - Title / subheadline / description structural patterns
  3  - povid URL segment (Tile_Takeover / Marquee_Banner)

Run:
  python3 tools/patch_brands_from_inference.py [--retailer walmart] [--dry-run]

After running, rebuild the manifest:
  python3 tools/build_run_manifest.py --incremental
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.brands import canonicalize as _exact_canon

OUTPUT_ROOT = PROJECT_ROOT / "output"
MANIFEST_PATH = PROJECT_ROOT / "cache" / "run_manifest.json"

# ── tagline guard (same as builder_server_v2) ──────────────────────────────
_TAGLINE_PREFIXES = re.compile(
    r'^(?:shop|get|buy|try|save|find|discover|introducing|experience|celebrate|'
    r'power|boost|give|make|fuel|love|hit|live|big|real|same|special|works|'
    r'refresh|glow|feel|taste|meet|see|go |be |it\'s|a |the )',
    re.IGNORECASE,
)

_UUID_RE = re.compile(
    r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
    re.IGNORECASE,
)


def _first_uuid(url: str | None) -> str | None:
    m = _UUID_RE.search(url or "")
    return m.group(0).lower() if m else None


def _infer(ad: dict, fp_index: dict) -> str | None:
    """Return inferred brand or None (mirrors server-side logic)."""

    # Tier 1: fingerprint
    if fp_index:
        logo_uuid = _first_uuid(ad.get("logo_url"))
        img_uuid  = _first_uuid(ad.get("image_url"))
        href_path = (ad.get("href") or "").split("?")[0].strip("/").lower()
        for key in [
            f"logo:{logo_uuid}" if logo_uuid else None,
            f"img:{img_uuid}"   if img_uuid  else None,
            f"href:{href_path}" if href_path and len(href_path) > 12 else None,
        ]:
            if key and key in fp_index:
                val = fp_index[key]
                if val and val.lower() != "unknown":
                    return val

    # Tier 1.5: product titles
    for product in (ad.get("products") or []):
        prod_title = (product.get("title") or "").strip()
        if not prod_title:
            continue
        c = _exact_canon(prod_title)
        if c and not c.endswith("(?)"):
            return c
        # Try first 2-3 words as brand prefix
        words = prod_title.split()
        for n in (2, 3, 1):
            if len(words) >= n:
                c2 = _exact_canon(" ".join(words[:n]))
                if c2 and not c2.endswith("(?)"):
                    return c2

    # Tier 2a: title (full-text, guarded)
    title_field = (ad.get("title") or ad.get("message") or ad.get("headline") or "").strip()
    if title_field:
        prefix_m = re.match(
            r'^(?:by|shop|from|introducing|brought to you by)\s+(.+)',
            title_field,
            re.IGNORECASE,
        )
        if prefix_m:
            c = _exact_canon(prefix_m.group(1).strip())
            if c and not c.endswith("(?)"):
                return c
        if not _TAGLINE_PREFIXES.match(title_field) and len(title_field.split()) <= 4:
            c = _exact_canon(title_field)
            if c and not c.endswith("(?)"):
                return c

    # Tier 2b: subheadline / description (structural patterns only)
    for text in [
        (ad.get("subheadline") or ad.get("sub_headline") or "").strip(),
        (ad.get("description") or "").strip(),
    ]:
        if not text:
            continue
        prefix_m = re.match(
            r'^(?:by|from|introducing|brought to you by)\s+(.+)',
            text,
            re.IGNORECASE,
        )
        if prefix_m:
            c = _exact_canon(prefix_m.group(1).strip())
            if c and not c.endswith("(?)"):
                return c
        em = re.search(
            r"\bfrom\s+([A-Za-z][A-Za-z0-9 &']{1,30}?)(?:\s*[.,!]|'s\b|\s*$)",
            text,
        )
        if em:
            c = _exact_canon(em.group(1).strip())
            if c and not c.endswith("(?)"):
                return c
        for pm in re.finditer(r"\b([A-Za-z][A-Za-z0-9]{2,})'s\b", text):
            c = _exact_canon(pm.group(1))
            if c and not c.endswith("(?)"):
                return c

    # Tier 3: povid URL
    href = ad.get("href") or ""
    if href:
        povid_m = re.search(r'[?&]povid=([^&]+)', href)
        if povid_m:
            segs = povid_m.group(1).split("_")
            first_word = next(
                (s for s in segs if len(s) > 2 and s.lower() not in
                 {"walmart", "sponsored", "ad", "brand", "tile", "takeover", "marquee", "banner"}),
                None,
            )
            if first_word:
                c = _exact_canon(first_word)
                if c and not c.endswith("(?)"):
                    return c

    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Patch null/Unknown brand fields via inference")
    parser.add_argument("--retailer", default="walmart", help="Retailer slug (default: walmart)")
    parser.add_argument("--dry-run", action="store_true", help="Show counts without writing files")
    args = parser.parse_args()

    # Load fingerprint index from manifest
    fp_index: dict[str, str] = {}
    if MANIFEST_PATH.exists():
        try:
            mf = json.loads(MANIFEST_PATH.read_text())
            fp_index = mf.get("creative_fingerprints", {})
            print(f"✅ Loaded {len(fp_index):,} fingerprints from manifest")
        except Exception as e:
            print(f"⚠️  Could not load manifest: {e}")

    retailer_dir = OUTPUT_ROOT / args.retailer
    if not retailer_dir.exists():
        print(f"No output directory for retailer: {args.retailer}")
        sys.exit(1)

    patched_files = 0
    patched_ads = 0
    brand_counts: dict[str, int] = {}
    still_unknown = 0

    json_files = sorted(retailer_dir.rglob("*.json"))
    print(f"Scanning {len(json_files):,} JSON files in {retailer_dir} …")

    for jpath in json_files:
        try:
            doc = json.loads(jpath.read_text())
        except Exception:
            continue

        ads = doc.get("ads", [])
        changed = False

        for ad in ads:
            existing = ad.get("brand") or ""
            if existing and existing.lower() not in ("unknown", ""):
                continue  # already has a brand — skip

            inferred = _infer(ad, fp_index)
            if inferred:
                ad["brand"] = inferred
                changed = True
                patched_ads += 1
                brand_counts[inferred] = brand_counts.get(inferred, 0) + 1
            else:
                still_unknown += 1

        if changed and not args.dry_run:
            jpath.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
            patched_files += 1

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Results:")
    print(f"  Files patched:     {patched_files:,}")
    print(f"  Ads newly branded: {patched_ads:,}")
    print(f"  Still unknown:     {still_unknown:,}")
    print(f"\nTop inferred brands:")
    for brand, count in sorted(brand_counts.items(), key=lambda x: -x[1])[:20]:
        print(f"  {brand:30} {count:6}")

    if not args.dry_run and patched_files:
        print("\nRebuilding manifest …")
        import subprocess
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "tools" / "build_run_manifest.py")],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        )
        if result.returncode == 0:
            print("✅ Manifest rebuilt")
        else:
            print("⚠️  Manifest rebuild failed:", result.stderr[-500:])


if __name__ == "__main__":
    main()
