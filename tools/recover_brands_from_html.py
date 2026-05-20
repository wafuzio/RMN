#!/usr/bin/env python3
"""
Post-hoc brand recovery from saved HTML.

Parses saved HTML files to extract brand signals that the scraper missed at
capture time, then patches the run_results JSON in place.

Two ad types are recovered:

  Gallery_Cards — individual gallery_card_N_<run_id>.html files contain the
    brand logo as <img id="logo" alt="BrandName ...">. The card index in the
    ads array is matched to the HTML file by position.

  SBV (Sponsored Brand Video) — the main search_results HTML contains the SBV
    module with product <a link-identifier="Product Title"> attributes.
    Brand is extracted from the first product title via lexicon matching.

Usage
-----
    python3 tools/recover_brands_from_html.py                   # all walmart
    python3 tools/recover_brands_from_html.py --client Proactiv # one client
    python3 tools/recover_brands_from_html.py --dry-run         # preview only
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT   = PROJECT_ROOT / "output"
MANIFEST = PROJECT_ROOT / "cache" / "run_manifest.json"

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("❌ beautifulsoup4 not installed.  Run: pip install beautifulsoup4")
    sys.exit(1)

try:
    from core.brands import canonicalize as canon_brand, is_blacklisted
except ImportError:
    def canon_brand(s): return None
    def is_blacklisted(s): return False


# ---------------------------------------------------------------------------
# Brand extraction helpers
# ---------------------------------------------------------------------------

def _brand_from_text(text: str) -> str | None:
    """Try lexicon match on full text, then shrinking prefix (1–3 words)."""
    if not text:
        return None
    # Full text first (catches "CeraVe", "Swisspers", multi-word like "Magic Spoon")
    b = canon_brand(text.strip())
    if b and not b.endswith("(?)"):
        return b
    # Shrinking prefix
    words = text.strip().split()
    for n in (1, 2, 3):
        candidate = " ".join(words[:n])
        b = canon_brand(candidate)
        if b and not b.endswith("(?)"):
            return b
    return None


def _brand_from_logo_alt(alt: str) -> str | None:
    """Extract brand from logo alt text like 'PanOxyl blue logo with tagline'."""
    if not alt:
        return None
    # Strip common suffixes
    clean = re.sub(
        r'\s*(logo|blue logo|pink logo|white logo|image|icon|trademark|registered|®|™)'
        r'.*$', '', alt, flags=re.IGNORECASE
    ).strip()
    return _brand_from_text(clean) or _brand_from_text(alt)


# ---------------------------------------------------------------------------
# Gallery Card recovery
# ---------------------------------------------------------------------------

def recover_gallery_cards(run_dir: Path, ads: list[dict]) -> int:
    """Patch null-brand Gallery_Cards using saved individual card HTML files.
    
    Returns count of ads branded.
    """
    # Collect gallery card HTML files: gallery_card_N_<run_id>.html
    gc_files = sorted(run_dir.glob("gallery_card_*.html"))
    if not gc_files:
        return 0

    # Build index: card_number (1-based) → brand extracted from HTML
    card_brands: dict[int, str] = {}
    for f in gc_files:
        m = re.match(r"gallery_card_(\d+)_", f.name)
        if not m:
            continue
        card_num = int(m.group(1))
        try:
            soup = BeautifulSoup(
                f.read_text(encoding="utf-8", errors="ignore"), "html.parser"
            )
        except Exception:
            continue

        # Primary: <img id="logo" alt="...">
        logo = soup.find("img", id="logo")
        if logo and logo.get("alt"):
            brand = _brand_from_logo_alt(logo["alt"])
            if brand:
                card_brands[card_num] = brand
                continue

        # Fallback: any img whose alt contains a known brand name
        for img in soup.find_all("img", alt=True):
            alt = img.get("alt", "").strip()
            if len(alt) < 3:
                continue
            brand = _brand_from_text(alt)
            if brand:
                card_brands[card_num] = brand
                break

    if not card_brands:
        return 0

    # Match card number to Gallery_Cards ads (by sequential position)
    gc_ad_indices = [
        i for i, a in enumerate(ads)
        if (a.get("type") or "") == "Gallery_Cards"
    ]

    branded = 0
    for seq_pos, ad_idx in enumerate(gc_ad_indices, start=1):
        ad = ads[ad_idx]
        if ad.get("brand") and ad["brand"] != "Unknown":
            continue  # already identified
        brand = card_brands.get(seq_pos)
        if brand and not is_blacklisted(brand):
            ad["brand"] = brand
            branded += 1

    return branded


# ---------------------------------------------------------------------------
# SBV recovery
# ---------------------------------------------------------------------------

def recover_sbv(run_dir: Path, ads: list[dict]) -> int:
    """Patch null-brand SBV ads using link-identifier product names in main HTML.
    
    Returns count of ads branded.
    """
    html_files = sorted(run_dir.glob("search_results_*.html"))
    if not html_files:
        return 0

    try:
        soup = BeautifulSoup(
            html_files[0].read_text(encoding="utf-8", errors="ignore"), "html.parser"
        )
    except Exception:
        return 0

    sbv_el = soup.find(attrs={"data-testid": "search-video-in-grid"})
    if not sbv_el:
        return 0

    # Collect product titles from link-identifier attributes (non-numeric)
    product_titles: list[str] = []
    for a in sbv_el.find_all("a", attrs={"link-identifier": True}):
        name = (a.get("link-identifier") or "").strip()
        if name and not name.isdigit() and len(name) > 5:
            product_titles.append(name)

    if not product_titles:
        return 0

    # Also try img alt text on the video poster image within SBV
    video_poster = sbv_el.find("img", alt=lambda a: a and len(a) > 5)

    branded = 0
    for ad in ads:
        if (ad.get("type") or "") != "SBV":
            continue
        if ad.get("brand") and ad["brand"] != "Unknown":
            continue

        # Store raw product titles for Tier 1.5 inference at serve time
        if not ad.get("products"):
            ad["products"] = [{"title": t} for t in product_titles[:6]]

        # Try to extract brand from product titles
        for pt in product_titles:
            brand = _brand_from_text(pt)
            if brand and not is_blacklisted(brand):
                ad["brand"] = brand
                branded += 1
                break

        # Fallback: video poster image alt
        if not (ad.get("brand") and ad["brand"] != "Unknown") and video_poster:
            brand = _brand_from_logo_alt(video_poster.get("alt", ""))
            if brand and not is_blacklisted(brand):
                ad["brand"] = brand
                branded += 1

    return branded


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--client",  help="Limit to one client slug (e.g. Proactiv)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would be patched without writing files")
    args = parser.parse_args()

    print("📋 Loading manifest …")
    mf = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = mf.get("runs", [])

    # Pre-screen: only walmart runs with ads
    candidates = [
        r for r in rows
        if r["retailer"] == "walmart"
        and r.get("ad_count", 0) > 0
        and (not args.client or r["client"].lower() == args.client.lower())
    ]
    print(f"   {len(candidates)} walmart runs to check")

    stats = {"runs_patched": 0, "gc_branded": 0, "sbv_branded": 0, "skipped": 0}

    for i, row in enumerate(candidates):
        run_json_path = OUTPUT / row["json_path"]
        if not run_json_path.exists():
            stats["skipped"] += 1
            continue

        try:
            doc = json.loads(run_json_path.read_text(encoding="utf-8"))
        except Exception:
            stats["skipped"] += 1
            continue

        ads = doc.get("ads", [])

        # Quick check: any null-brand Gallery_Cards or SBV?
        needs_gc  = any(
            (a.get("type") or "") == "Gallery_Cards"
            and not (a.get("brand") and a["brand"] != "Unknown")
            for a in ads
        )
        needs_sbv = any(
            (a.get("type") or "") == "SBV"
            and not (a.get("brand") and a["brand"] != "Unknown")
            for a in ads
        )

        if not needs_gc and not needs_sbv:
            continue

        run_dir = run_json_path.parent
        gc_branded  = recover_gallery_cards(run_dir, ads) if needs_gc  else 0
        sbv_branded = recover_sbv(run_dir, ads)           if needs_sbv else 0

        if gc_branded or sbv_branded:
            stats["runs_patched"] += 1
            stats["gc_branded"]   += gc_branded
            stats["sbv_branded"]  += sbv_branded
            if args.dry_run:
                print(
                    f"  [DRY] {row['client']}/{row['keyword']!r} "
                    f"GC+{gc_branded} SBV+{sbv_branded}"
                )
            else:
                run_json_path.write_text(
                    json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8"
                )

        if (i + 1) % 500 == 0:
            print(f"  … {i+1}/{len(candidates)} scanned, "
                  f"{stats['runs_patched']} patched so far")

    print()
    print("=" * 55)
    print("📊 Recovery results")
    print(f"  Runs patched:          {stats['runs_patched']:>6,}")
    print(f"  Gallery Cards branded: {stats['gc_branded']:>6,}")
    print(f"  SBV ads branded:       {stats['sbv_branded']:>6,}")
    print(f"  Runs skipped:          {stats['skipped']:>6,}")
    print("=" * 55)

    if not args.dry_run and stats["runs_patched"]:
        print("\n🔄 Rebuilding manifest to reflect patched data …")
        import subprocess
        subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "tools" / "build_run_manifest.py")],
            check=False,
        )


if __name__ == "__main__":
    main()
