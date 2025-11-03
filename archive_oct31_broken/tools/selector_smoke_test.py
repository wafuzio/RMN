#!/usr/bin/env python3
"""
Selector Smoke Test

Validates that selectors in an Ad Type Hint Pack actually match HTML samples.
Run this BEFORE composing a retailer to catch selector issues early.

Usage:
    python3 tools/selector_smoke_test.py docs/hints/newretailer_ad_types.yaml
"""
import sys
import yaml
from pathlib import Path
from bs4 import BeautifulSoup


def load_yaml(p: Path):
    """Load YAML hint pack"""
    return yaml.safe_load(p.read_text())


def test_selectors(hints: dict, samples_dir: Path):
    """Test all selectors against HTML samples"""
    results = []
    
    for ad in hints.get("ad_types", []):
        name = ad["canonical"]
        sels = ad.get("selectors", [])
        
        # Find HTML samples for this ad type
        glob = list(samples_dir.glob(f"{name}*.html"))
        
        if not glob:
            results.append((name, "NO_SAMPLES", 0, []))
            continue
        
        per_file = []
        for fp in glob:
            html = fp.read_text(errors="ignore")
            soup = BeautifulSoup(html, "html.parser")
            
            hits = 0
            per_sel = []
            
            # Test each selector
            for sel in sels:
                try:
                    found = len(soup.select(sel))
                    hits += found
                    per_sel.append((sel, found, "OK" if found > 0 else "MISS"))
                except Exception as e:
                    per_sel.append((sel, 0, f"ERROR: {e}"))
            
            # Test sub-selectors (image, href, title, etc.)
            sub_tests = []
            if ad.get("image", {}).get("element"):
                img_sel = ad["image"]["element"]
                try:
                    img_hits = len(soup.select(img_sel))
                    sub_tests.append(("image", img_sel, img_hits))
                except Exception as e:
                    sub_tests.append(("image", img_sel, f"ERROR: {e}"))
            
            if ad.get("href"):
                try:
                    href_hits = len(soup.select(ad["href"]))
                    sub_tests.append(("href", ad["href"], href_hits))
                except Exception as e:
                    sub_tests.append(("href", ad["href"], f"ERROR: {e}"))
            
            if ad.get("title"):
                try:
                    title_hits = len(soup.select(ad["title"]))
                    sub_tests.append(("title", ad["title"], title_hits))
                except Exception as e:
                    sub_tests.append(("title", ad["title"], f"ERROR: {e}"))
            
            per_file.append((fp.name, hits, per_sel, sub_tests))
        
        total_hits = sum(h for _, h, _, _ in per_file)
        status = "OK" if total_hits > 0 else "FAIL"
        results.append((name, status, total_hits, per_file))
    
    return results


def print_results(results):
    """Pretty-print test results"""
    print("\n" + "=" * 80)
    print("SELECTOR SMOKE TEST RESULTS")
    print("=" * 80 + "\n")
    
    all_ok = True
    
    for name, status, total, files in results:
        icon = "✅" if status == "OK" else "❌" if status == "FAIL" else "⚠️"
        print(f"{icon} {name}: {status} (total_hits={total})")
        
        if status != "OK":
            all_ok = False
        
        for fname, hits, per_sel, sub_tests in files:
            print(f"   📄 {fname}: {hits} container hits")
            
            # Container selectors
            for sel, cnt, result in per_sel:
                if isinstance(cnt, int):
                    sel_icon = "✓" if cnt > 0 else "✗"
                    print(f"      {sel_icon} {sel} → {cnt}")
                else:
                    print(f"      ✗ {sel} → {result}")
            
            # Sub-selectors
            if sub_tests:
                print(f"      Sub-elements:")
                for field, sel, result in sub_tests:
                    if isinstance(result, int):
                        sub_icon = "✓" if result > 0 else "✗"
                        print(f"         {sub_icon} {field}: {sel} → {result}")
                    else:
                        print(f"         ✗ {field}: {sel} → {result}")
        
        print()
    
    print("=" * 80)
    if all_ok:
        print("✅ All selectors validated successfully!")
    else:
        print("❌ Some selectors failed validation - fix before composing")
    print("=" * 80 + "\n")
    
    return all_ok


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 tools/selector_smoke_test.py docs/hints/{retailer}_ad_types.yaml")
        print()
        print("Example:")
        print("  python3 tools/selector_smoke_test.py docs/hints/kroger_ad_types.yaml")
        sys.exit(1)
    
    hint_path = Path(sys.argv[1])
    
    if not hint_path.exists():
        print(f"❌ Hint pack not found: {hint_path}")
        sys.exit(1)
    
    print(f"🔍 Loading hint pack: {hint_path}")
    hints = load_yaml(hint_path)
    
    retailer = hints.get("retailer", "unknown")
    samples_dir = hint_path.parent / retailer / "samples"
    
    if not samples_dir.exists():
        print(f"❌ Samples directory not found: {samples_dir}")
        print(f"   Create it and add HTML samples: {samples_dir}")
        sys.exit(1)
    
    print(f"📁 Samples directory: {samples_dir}")
    print(f"🏪 Retailer: {hints.get('display_name', retailer)}")
    print(f"📊 Ad types: {len(hints.get('ad_types', []))}")
    print()
    
    results = test_selectors(hints, samples_dir)
    all_ok = print_results(results)
    
    sys.exit(0 if all_ok else 1)
