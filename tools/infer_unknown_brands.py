#!/usr/bin/env python3
"""
Batch LLM brand inference for null-brand ads.

Reads the manifest to find runs that have ads but no brands extracted, then
uses the AlchemyAI relay (gpt-5.4-2026-03-05) to infer the brand from all
available context signals:

  - retailer, client name, search keyword          ← richest context
  - ad title / headline
  - href domain
  - logo_url / image_url CDN UUID fingerprints
  - other brands seen in the same search run (competitors / co-advertisers)

Results are stored in cache/brand_inference_cache.json, keyed by MD5 of the
creative fingerprint string.  The server reads this cache at serve time so
card rendering is never blocked by live relay calls.

Usage
-----
    # Infer all unknown brands (all retailers)
    python3 tools/infer_unknown_brands.py

    # Target one retailer, cap at 200 LLM calls
    python3 tools/infer_unknown_brands.py --retailer walmart --limit 200

    # Preview prompts without calling the relay
    python3 tools/infer_unknown_brands.py --dry-run --limit 5

    # Force re-inference even for cached entries
    python3 tools/infer_unknown_brands.py --force --retailer walmart

Environment
-----------
    ALCHEMY_API_KEY   JWT token for the AlchemyAI/Gale relay (required)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT   = PROJECT_ROOT / "output"
CACHE    = PROJECT_ROOT / "cache"
MANIFEST = CACHE / "run_manifest.json"
LLM_CACHE_PATH = CACHE / "brand_inference_cache.json"

_MODEL = "gpt-5.4-2026-03-05"

# Ad types where LLM inference is worthwhile (structural unknowns like
# Amazon Product_Listing are excluded — they'd need a different approach).
_INFERRABLE_TYPES = {
    "Gallery_Card", "Gallery_Cards",
    "Tile_Takeover", "Marquee_Banner", "Hero_Banner",
    "SBV", "SBA", "Sponsored_Brand", "Sponsored_Brand_Video",
    "Main",
}

# Minimum signal requirement: at least one of these must be non-empty.
_SIGNAL_FIELDS = ("title", "message", "headline", "logo_url", "image_url", "href")


# ---------------------------------------------------------------------------
# Fingerprinting (mirrors logic in builder_server_v2.py)
# ---------------------------------------------------------------------------

def _first_uuid(url: str | None) -> str | None:
    if not url:
        return None
    m = re.search(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        url, re.IGNORECASE,
    )
    return m.group(0).lower() if m else None


def _ad_fingerprint_key(ad: dict) -> str | None:
    """Derive a stable, human-readable fingerprint string from observable ad signals."""
    logo_uuid = _first_uuid(ad.get("logo_url"))
    img_uuid  = _first_uuid(ad.get("image_url"))
    href_path = (ad.get("href") or "").split("?")[0].strip("/").lower()
    parts = []
    if logo_uuid:
        parts.append(f"logo:{logo_uuid}")
    if img_uuid:
        parts.append(f"img:{img_uuid}")
    if href_path and len(href_path) > 12:
        parts.append(f"href:{href_path}")
    return "|".join(parts) if parts else None


def _fp_hash(fp_key: str) -> str:
    return hashlib.md5(fp_key.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Cache I/O
# ---------------------------------------------------------------------------

def load_llm_cache() -> dict[str, str]:
    """Load existing inference cache.  Returns {} if file is missing/corrupt."""
    if not LLM_CACHE_PATH.exists():
        return {}
    try:
        return json.loads(LLM_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_llm_cache(cache: dict[str, str]) -> None:
    CACHE.mkdir(exist_ok=True)
    tmp = LLM_CACHE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(LLM_CACHE_PATH)


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------

def load_manifest() -> dict:
    if not MANIFEST.exists():
        raise FileNotFoundError(
            f"Manifest not found at {MANIFEST}.  "
            "Run: python3 tools/build_run_manifest.py"
        )
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _href_domain(href: str | None) -> str:
    if not href:
        return ""
    try:
        return urlparse(href).netloc or ""
    except Exception:
        return ""


def build_prompt(
    ad: dict,
    *,
    retailer: str,
    client: str,
    keyword: str,
    run_brands: list[str],
) -> str:
    """Construct the LLM prompt for a single null-brand ad."""
    ad_type  = ad.get("type") or ad.get("ad_type") or "display"
    title    = (ad.get("title") or ad.get("message") or ad.get("headline") or "").strip()
    href     = ad.get("href") or ""
    domain   = _href_domain(href)
    logo_url = ad.get("logo_url") or ""

    context_lines = [
        f"Retailer: {retailer.title()}",
        # NOTE: client is the company monitoring this keyword space — it is NOT
        # necessarily the advertiser.  Competitors and other brands appear here.
        f"Monitoring client (may or may not be the advertiser): {client}",
        f"Search keyword: \"{keyword}\"",
        f"Ad type: {ad_type}",
    ]
    if title:
        context_lines.append(f"Ad title / headline: \"{title}\"")
    if domain:
        context_lines.append(f"Ad href domain: {domain}")
    if logo_url:
        context_lines.append(f"Logo CDN URL: {logo_url[:80]}...")
    if run_brands:
        context_lines.append(
            f"Other brands seen in this search run: {', '.join(run_brands[:12])}"
        )

    context = "\n".join(context_lines)

    return (
        "You are a retail advertising analyst identifying advertiser brands "
        "from display ads.\n\n"
        f"{context}\n\n"
        "What brand placed this ad?  Respond with JSON only, no other text:\n"
        "{\"brand\": \"Brand Name\", \"confidence\": 0.0}\n\n"
        "Rules:\n"
        "- brand: the advertiser's brand name, or null if unknown\n"
        "- confidence: 0.0–1.0; only return a non-null brand if ≥ 0.7 confident\n"
        "- The monitoring client is NOT necessarily the advertiser — it may be a competitor watching the space\n"
        "- If this is a Walmart house ad, return {\"brand\": \"Walmart\", \"confidence\": 1.0}\n"
        "- If truly unknown, return {\"brand\": null, \"confidence\": 0.0}\n"
        "- Return the brand's consumer-facing name (e.g. \"Gatorade\", not \"PepsiCo\")"
    )


# ---------------------------------------------------------------------------
# LLM call + response parsing
# ---------------------------------------------------------------------------

def _parse_relay_response(raw: str) -> tuple[str | None, float]:
    """Parse JSON response from relay.  Returns (brand_or_None, confidence)."""
    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"```[a-z]*\n?", "", text).strip().rstrip("`").strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Last-resort: try to extract brand with regex
        m = re.search(r'"brand"\s*:\s*"([^"]+)"', raw)
        brand = m.group(1).strip() if m else None
        m2 = re.search(r'"confidence"\s*:\s*([0-9.]+)', raw)
        confidence = float(m2.group(1)) if m2 else 0.0
        return brand, confidence

    brand      = data.get("brand")
    confidence = float(data.get("confidence", 0.0))
    if not brand or str(brand).lower() in ("null", "unknown", "none"):
        return None, confidence
    return str(brand).strip(), confidence


def infer_brand_via_llm(
    client_obj,  # RelayClient instance
    prompt: str,
    *,
    dry_run: bool = False,
) -> tuple[str | None, float]:
    """Call relay and return (canonical_brand_or_None, confidence)."""
    if dry_run:
        print("  [DRY-RUN] Prompt:\n", prompt[:500], "...\n")
        return None, 0.0

    raw = client_obj.complete(
        prompt,
        model=_MODEL,
        temperature=0.0,
        max_tokens=80,
    )
    brand, confidence = _parse_relay_response(raw)
    return brand, confidence


# ---------------------------------------------------------------------------
# Main processing loop
# ---------------------------------------------------------------------------

def process_run_file(
    json_path: Path,
    manifest_row: dict,
    *,
    llm_cache: dict[str, str],
    fp_index: dict[str, str],
    relay_client,
    dry_run: bool,
    force: bool,
    stats: dict,
) -> int:
    """Process one run JSON file.  Returns number of new LLM calls made."""
    try:
        doc = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  ⚠️  Could not read {json_path.name}: {e}")
        return 0

    ads: list[dict] = doc.get("ads", [])
    if not ads:
        for blk in doc.get("results", []):
            ads.extend(blk.get("ads", []))

    retailer = manifest_row["retailer"]
    client   = manifest_row["client"]
    keyword  = manifest_row["keyword"]

    # Collect non-null brands in this run for surrounding-signal context
    run_brands: list[str] = []
    for a in ads:
        b = a.get("brand") or a.get("advertiser")
        if b and b != "Unknown":
            run_brands.append(b)
    run_brands = sorted(set(run_brands))

    calls_made = 0
    for ad in ads:
        brand_raw = ad.get("brand") or ad.get("advertiser")
        if brand_raw and brand_raw != "Unknown":
            continue  # already has a brand

        ad_type = ad.get("type") or ad.get("ad_type") or "Main"
        if ad_type not in _INFERRABLE_TYPES:
            stats["skipped_type"] += 1
            continue

        # Skip if no recoverable signals
        if not any(ad.get(f) for f in _SIGNAL_FIELDS):
            stats["skipped_no_signals"] += 1
            continue

        fp_key = _ad_fingerprint_key(ad)

        # Tier 1: manifest fingerprint index (free, already built)
        if fp_key and not force:
            for sub_key in fp_key.split("|"):
                if sub_key in fp_index:
                    stats["resolved_fingerprint"] += 1
                    break
            else:
                pass  # no break → not in fp_index, fall through
            # Check if any sub-key is in fp_index
            if any(sub_key in fp_index for sub_key in fp_key.split("|")):
                continue  # already resolved by fingerprint propagation

        # Tier 2: LLM cache hit
        if fp_key and not force:
            h = _fp_hash(fp_key)
            if h in llm_cache:
                stats["cache_hit"] += 1
                continue

        # Need to call LLM
        prompt = build_prompt(
            ad,
            retailer=retailer,
            client=client,
            keyword=keyword,
            run_brands=run_brands,
        )

        brand_inferred, confidence = infer_brand_via_llm(
            relay_client, prompt, dry_run=dry_run
        )

        if fp_key:
            h = _fp_hash(fp_key)
            # Store brand if confident, empty string if confirmed unknown
            llm_cache[h] = brand_inferred if brand_inferred and confidence >= 0.7 else ""

        calls_made += 1
        stats["llm_calls"] += 1
        if brand_inferred and confidence >= 0.7:
            stats["inferred"] += 1
            if not dry_run:
                print(f"    ✅ {brand_inferred} (conf={confidence:.2f}) — {ad_type}: {(ad.get('title') or '')[:60]}")
        else:
            stats["low_confidence"] += 1
            if not dry_run:
                print(f"    ❓ Unknown (conf={confidence:.2f}) — {ad_type}: {(ad.get('title') or '')[:60]}")

        # Brief pause to be kind to the relay
        if not dry_run:
            time.sleep(0.3)

    return calls_made


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch LLM brand inference for null-brand ads",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--retailer",  help="Limit to one retailer (e.g. walmart)")
    parser.add_argument("--client",    help="Limit to one client slug")
    parser.add_argument("--limit",     type=int, default=0,
                        help="Max LLM calls to make (0 = unlimited)")
    parser.add_argument("--dry-run",   action="store_true",
                        help="Print prompts without calling the relay")
    parser.add_argument("--force",     action="store_true",
                        help="Re-infer even if result is already cached")
    args = parser.parse_args()

    if not args.dry_run:
        import os
        if not os.environ.get("ALCHEMY_API_KEY"):
            print("❌ ALCHEMY_API_KEY is not set.  Export it before running.")
            sys.exit(1)

    print("📋 Loading manifest …")
    manifest = load_manifest()
    rows: list[dict] = manifest.get("runs", [])
    fp_index: dict[str, str] = manifest.get("creative_fingerprints", {})
    print(f"   {len(rows)} runs loaded, {len(fp_index)} creative fingerprints available")

    llm_cache = load_llm_cache()
    print(f"   {len(llm_cache)} entries already in LLM inference cache")

    # Find all runs with ads — we check individual ad brand fields inside process_run_file,
    # so runs that have SOME brands identified are still worth scanning for null-brand ads
    # within the same run (e.g. a Differin SBA + an unknown SBV in the same acne-kit run).
    candidate_rows = [
        r for r in rows
        if r.get("ad_count", 0) > 0
        and (not args.retailer or r["retailer"] == args.retailer)
        and (not args.client   or r["client"]   == args.client)
    ]
    print(f"   {len(candidate_rows)} candidate runs to scan for null-brand ads")

    if not candidate_rows:
        print("✅ Nothing to scan — no matching runs with ads.")
        return

    # Initialise relay client (skipped in dry-run)
    relay_client = None
    if not args.dry_run:
        try:
            sys.path.insert(0, str(PROJECT_ROOT))
            from llm_client import RelayClient
            relay_client = RelayClient()
            print(f"🔌 Relay client ready ({_MODEL})")
        except Exception as e:
            print(f"❌ Could not initialise relay client: {e}")
            sys.exit(1)

    stats: dict[str, int] = {
        "llm_calls": 0,
        "inferred": 0,
        "low_confidence": 0,
        "cache_hit": 0,
        "resolved_fingerprint": 0,
        "skipped_type": 0,
        "skipped_no_signals": 0,
    }

    save_every = 50  # persist cache every N LLM calls
    total_calls = 0

    for i, row in enumerate(candidate_rows):
        if args.limit and total_calls >= args.limit:
            print(f"\n⏹  Reached --limit {args.limit}, stopping.")
            break

        json_path = OUTPUT / row["json_path"]
        if not json_path.exists():
            continue

        retailer_label = f"{row['retailer']}/{row['client']}"
        print(f"\n[{i+1}/{len(candidate_rows)}] {retailer_label} — {row['keyword']!r} ({row['run_id']})")

        new_calls = process_run_file(
            json_path, row,
            llm_cache=llm_cache,
            fp_index=fp_index,
            relay_client=relay_client,
            dry_run=args.dry_run,
            force=args.force,
            stats=stats,
        )
        total_calls += new_calls

        # Periodically persist to disk so progress survives interruptions
        if not args.dry_run and new_calls > 0 and (stats["llm_calls"] % save_every) == 0:
            save_llm_cache(llm_cache)
            print(f"  💾 Cache saved ({len(llm_cache)} entries)")

    # Final save
    if not args.dry_run:
        save_llm_cache(llm_cache)

    print("\n" + "=" * 60)
    print("📊 Summary")
    print(f"  LLM calls made:       {stats['llm_calls']}")
    print(f"  Brands inferred:      {stats['inferred']}")
    print(f"  Low confidence:       {stats['low_confidence']}")
    print(f"  Cache hits (skipped): {stats['cache_hit']}")
    print(f"  Fingerprint resolved: {stats['resolved_fingerprint']}")
    print(f"  Skipped (ad type):    {stats['skipped_type']}")
    print(f"  Skipped (no signals): {stats['skipped_no_signals']}")
    if not args.dry_run:
        print(f"\n✅ Cache saved to {LLM_CACHE_PATH} ({len(llm_cache)} entries)")
    print("=" * 60)


if __name__ == "__main__":
    main()
