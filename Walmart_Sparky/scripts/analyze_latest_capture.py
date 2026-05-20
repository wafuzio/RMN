#!/usr/bin/env python3
"""
Analyzes the latest capture against WHAT_WE_KNOW.md claims.
Outputs a structured update report: which claims are confirmed, extended, or contradicted.
Called automatically after each new capture is processed by parse_har_curl.py.

Usage:
    python3 analyze_latest_capture.py
    python3 analyze_latest_capture.py data/captures/TIMESTAMP_parsed.json
"""

import json
import sys
from pathlib import Path
from datetime import datetime


# ── Helpers ──────────────────────────────────────────────────────────────────

def load_capture(filepath=None):
    captures_dir = Path(__file__).parent.parent / "data" / "captures"

    if filepath:
        path = Path(filepath)
    else:
        parsed_files = list(captures_dir.glob("*_parsed.json"))
        if not parsed_files:
            return None, None
        path = max(parsed_files, key=lambda p: p.stat().st_mtime)

    with open(path) as f:
        data = json.load(f)

    return path, data


def count_captures():
    captures_dir = Path(__file__).parent.parent / "data" / "captures"
    return len(list(captures_dir.glob("*_parsed.json"))) if captures_dir.exists() else 0


def extract_metrics(data):
    """Pull flat metrics from the nested parsed JSON structure."""
    pm = data.get("product_metrics", {})
    rc = data.get("response_classification", {})
    em = data.get("editorial_metrics", {})
    ai = data.get("ad_infrastructure", {})
    sr = data.get("search_query_reformulation", {})
    qm = data.get("query_metadata", {})

    total = pm.get("total_products", 0)
    p1 = pm.get("seller_breakdown", {}).get("1P", 0)
    p3 = pm.get("seller_breakdown", {}).get("3P", 0)

    return {
        "query":            qm.get("query_text", ""),
        "reformulated":     sr.get("reformulated", ""),
        "mode":             rc.get("response_mode", ""),
        "intent":           rc.get("intent_name", ""),
        "total_products":   total,
        "brand_count":      pm.get("garanimals_count", 0),
        "brand_share":      pm.get("garanimals_share", 0.0),
        "brand_positions":  pm.get("garanimals_positions", []),
        "brands_present":   pm.get("brands", []),
        "seller_1p":        p1,
        "seller_3p":        p3,
        "pct_1p":           (p1 / total * 100) if total else 0,
        "editorial_mention":em.get("garanimals_mentioned", False),
        "source_domains":   em.get("source_domains", []),
        "max_ads":          ai.get("max_ads", 0),
        "ads_active":       ai.get("ads_active", False),
        "conversation_title": data.get("query_metadata", {}).get("conversation_title", ""),
    }


# ── Claim checkers ───────────────────────────────────────────────────────────
# Each returns one of: "CONFIRMS", "CONTRADICTS", "EXTENDS", "N/A"
# along with a note string.

VALUE_WORDS  = {"cheap", "affordable", "budget", "inexpensive", "value", "low cost", "low-cost"}
SEASON_WORDS = {"back to school", "fall", "spring", "summer", "winter", "holiday",
                "halloween", "christmas", "easter", "back-to-school"}
GIFT_WORDS   = {"gift", "niece", "nephew", "birthday", "present", "for my"}
BEST_SELL    = {"best selling", "best-selling", "bestselling"}


def _has(query, words):
    q = query.lower()
    return any(w in q for w in words)


def check_R1(m):
    if not _has(m["query"], VALUE_WORDS):
        return "N/A", None
    if m["pct_1p"] >= 60:
        return "CONFIRMS", f"Value query → {m['pct_1p']:.0f}% 1P"
    return "CONTRADICTS", f"Value query but only {m['pct_1p']:.0f}% 1P — investigate"


def check_R2(m):
    if not _has(m["query"], SEASON_WORDS):
        return "N/A", None
    if m["pct_1p"] == 0:
        return "CONFIRMS", f"Seasonal query → 0% 1P (pure 3P)"
    return "CONTRADICTS", f"Seasonal query but {m['pct_1p']:.0f}% 1P — routing may have changed"


def check_R3(m):
    if not _has(m["query"], GIFT_WORDS):
        return "N/A", None
    if m["pct_1p"] == 0:
        return "CONFIRMS", f"Gift/relational context → 0% 1P"
    return "CONTRADICTS", f"Gift context but {m['pct_1p']:.0f}% 1P — unexpected"


def check_R4(m):
    if not _has(m["query"], BEST_SELL):
        return "N/A", None
    if m["pct_1p"] == 0:
        return "CONFIRMS", f"'Best selling' → 100% 3P"
    if m["pct_1p"] >= 60:
        return "CONTRADICTS", f"'Best selling' but {m['pct_1p']:.0f}% 1P — R-4 may be category-specific"
    return "EXTENDS", f"'Best selling' → {m['pct_1p']:.0f}% 1P (mixed result, not pure 3P)"


def check_R5(m):
    has_value   = _has(m["query"], VALUE_WORDS)
    has_season  = _has(m["query"], SEASON_WORDS)
    if not (has_value and has_season):
        return "N/A", None
    if m["pct_1p"] == 0:
        return "CONFIRMS", "Seasonal overrides value → 0% 1P despite value modifier"
    return "CONTRADICTS", f"Value + seasonal but {m['pct_1p']:.0f}% 1P — hierarchy may vary by season word"


def check_R6(m):
    if m["total_products"] == 0:
        return "N/A", None
    if m["pct_1p"] >= 80 or m["pct_1p"] == 0:
        return "CONFIRMS", f"Binary result: {m['pct_1p']:.0f}% 1P"
    return "EXTENDS", f"Mixed result: {m['pct_1p']:.0f}% 1P — another borderline query found"


def check_R8(m):
    # Can only confirm determinism if we have prior captures of same query — flag for manual check
    return "N/A", "Manual: run same query again to confirm determinism"


def check_R9(m):
    if m["total_products"] == 0:
        return "N/A", None
    # If 3P dominant and brand present → CONTRADICTS; if brand absent → CONFIRMS
    if m["pct_1p"] <= 20 and m["brand_count"] > 0:
        return "CONTRADICTS", f"3P-dominant result but target brand appeared at positions {m['brand_positions']}"
    if m["pct_1p"] <= 20 and m["brand_count"] == 0:
        return "CONFIRMS", "3P-dominant result, target brand absent — routing before ranking holds"
    return "N/A", None


def check_K1(m):
    if m["pct_1p"] < 60 or m["total_products"] == 0:
        return "N/A", None
    if 1 in m["brand_positions"]:
        return "CONFIRMS", "Target brand at position #1 on 1P-dominant query"
    if m["brand_count"] > 0:
        return "EXTENDS", f"Target brand on 1P path but NOT at #1 — positions {m['brand_positions']}"
    return "EXTENDS", "1P-dominant query but target brand absent — ranking gap on 1P path"


def check_K3(m):
    if m["pct_1p"] > 20:
        return "N/A", None
    if m["brand_count"] == 0:
        return "CONFIRMS", "3P-dominant result → target brand share = 0%"
    return "CONTRADICTS", f"3P result but target brand appeared at positions {m['brand_positions']}"


def check_E1(m):
    if m["mode"] != "editorial":
        return "N/A", None
    return "CONFIRMS", "Editorial-only response (no products)"


def check_E4(m):
    if not m["source_domains"]:
        return "N/A", None
    known = {"reddit.com", "thespruce.com", "babycenter.com"}
    new_domains = set(m["source_domains"]) - known
    if new_domains:
        return "EXTENDS", f"NEW source domains found: {', '.join(new_domains)} — add to E-4"
    return "CONFIRMS", f"Sources match known set: {', '.join(m['source_domains'])}"


def check_A1(m):
    if m["ads_active"]:
        return "CONTRADICTS", "⚠️  ADS ARE NOW ACTIVE — showAds is true. Document immediately."
    if m["max_ads"] > 0:
        return "CONFIRMS", f"Ad infrastructure present but inactive (max_ads={m['max_ads']}, showAds=false)"
    return "N/A", None


def check_C3(m):
    title = m.get("conversation_title", "")
    if not title:
        return "N/A", None
    return "CONFIRMS", f"Conversation title present: '{title}'"


CLAIM_CHECKERS = [
    ("R-1", "Value modifiers → 1P path",                     check_R1),
    ("R-2", "Seasonal modifiers → 3P path",                  check_R2),
    ("R-3", "Gift/novelty context → 3P path",                check_R3),
    ("R-4", "'Best selling' → 3P path",                      check_R4),
    ("R-5", "Seasonal overrides value modifier",              check_R5),
    ("R-6", "Results are binary (1P-dominant or 3P-exclusive)", check_R6),
    ("R-9", "Routing operates before ranking",                check_R9),
    ("K-1", "Target brand holds position #1 on value queries", check_K1),
    ("K-3", "Target brand share = 0% on 3P-dominant results", check_K3),
    ("E-1", "Perception queries trigger editorial-only mode", check_E1),
    ("E-4", "Primary editorial sources are reddit/thespruce/babycenter", check_E4),
    ("A-1", "Ad infrastructure present but inactive",         check_A1),
    ("C-3", "Conversation title tracks routing evolution",    check_C3),
]


# ── Open question detector ────────────────────────────────────────────────────

def check_open_questions(m):
    hits = []
    q = m["query"].lower()

    if "romper" in q and "best selling" not in q:
        hits.append("OQ-1: Generic romper query tested — does target brand appear?")
    if "back to school" in q and _has(q, VALUE_WORDS):
        hits.append("OQ-2: Affordable + back-to-school combo tested")
    if "cute" in q and not _has(q, GIFT_WORDS):
        hits.append("OQ-3: 'Cute' without gift context — check if 3P triggered")
    if "walmart brand" in q:
        hits.append("OQ-4: Explicit Walmart brand request tested")
    if "mix and match" in q:
        hits.append("Borderline routing query — document 1P% carefully")

    return hits


# ── Report ────────────────────────────────────────────────────────────────────

def print_report(capture_path, m, total_captures):
    divider = "=" * 72
    thin    = "-" * 72

    print(f"\n{divider}")
    print("  SPARKY CAPTURE ANALYSIS — WHAT WE KNOW UPDATE REPORT")
    print(divider)

    print(f"\n📄 Capture #{total_captures}: {capture_path.name}")
    print(f"   Query:        \"{m['query']}\"")
    print(f"   Reformulated: \"{m['reformulated']}\"")
    print(f"   Mode:         {m['mode']}")
    print(f"   1P / 3P:      {m['seller_1p']} / {m['seller_3p']}  ({m['pct_1p']:.0f}% 1P)")
    print(f"   Brand share:  {m['brand_count']}/5 ({m['brand_share']:.0f}%) at positions {m['brand_positions']}")
    if m["source_domains"]:
        print(f"   Sources:      {', '.join(m['source_domains'])}")
    if m["conversation_title"]:
        print(f"   Conv. title:  {m['conversation_title']}")
    print(f"   Ads active:   {'⚠️  YES — DOCUMENT NOW' if m['ads_active'] else 'No'}  (max_ads={m['max_ads']})")

    print(f"\n{thin}")
    print("  CLAIM CHECK vs WHAT_WE_KNOW.md")
    print(thin)

    icons = {"CONFIRMS": "✅", "CONTRADICTS": "❌", "EXTENDS": "➕", "N/A": "·"}
    actionable = []

    for claim_id, desc, checker in CLAIM_CHECKERS:
        result, note = checker(m)
        icon = icons.get(result, "?")
        if result == "N/A":
            print(f"   {icon}  {claim_id:<5} {desc}")
        else:
            print(f"   {icon}  {claim_id:<5} {desc}")
            print(f"         → {note}")
            if result in ("CONTRADICTS", "EXTENDS"):
                actionable.append((claim_id, result, note))

    oq_hits = check_open_questions(m)
    if oq_hits:
        print(f"\n{thin}")
        print("  OPEN QUESTIONS TOUCHED BY THIS CAPTURE")
        print(thin)
        for hit in oq_hits:
            print(f"   ❓  {hit}")

    print(f"\n{thin}")
    print("  ACTION ITEMS FOR WHAT_WE_KNOW.md")
    print(thin)

    today = datetime.now().strftime("%b %d, %Y")

    if not actionable and not oq_hits:
        print("   ✅  No updates needed — all applicable claims confirmed.")
    else:
        for claim_id, result, note in actionable:
            if result == "CONTRADICTS":
                print(f"\n   ❌  {claim_id} — CONTRADICTION FOUND")
                print(f"      Add to Challenges field:")
                print(f"      \"Capture #{total_captures} ({today}): {note}\"")
                print(f"      Consider downgrading confidence if this is 2nd contradiction.")
            elif result == "EXTENDS":
                print(f"\n   ➕  {claim_id} — NEW NUANCE")
                print(f"      Add to Notes or split into a sub-claim:")
                print(f"      \"{note}\"")

        if oq_hits:
            print(f"\n   ❓  Open question(s) touched — review and create new claim(s) if pattern holds:")
            for hit in oq_hits:
                print(f"      {hit}")

    # Ads alert — always print loudly
    if m["ads_active"]:
        print(f"\n{'!' * 72}")
        print("  🚨  ADS ARE LIVE — showAds is TRUE")
        print("  Update A-1 to CONTRADICTED immediately.")
        print("  Document ad format, placement, and first advertisers in A-2.")
        print('!' * 72)

    print(f"\n{divider}")
    print(f"  WHAT_WE_KNOW.md is at: docs/WHAT_WE_KNOW.md")
    print(f"  Update it now, then add to Change Log at the bottom.")
    print(divider + "\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    filepath = sys.argv[1] if len(sys.argv) > 1 else None
    capture_path, data = load_capture(filepath)

    if not data:
        print("⚠️  No captures found.")
        return

    m = extract_metrics(data)
    total = count_captures()
    print_report(capture_path, m, total)


if __name__ == "__main__":
    main()

