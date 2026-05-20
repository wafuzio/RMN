#!/usr/bin/env python3
"""
Parse Sparky WebSocket captures (v26.17.1+) from HTTP Catcher paste format.

Usage:
    python3 parse_websocket_capture.py [input_file]
    
Default input: ../new_capture_input.txt
Output: prints structured analysis + saves to ../data/ws_parsed_TIMESTAMP.json
"""

import json
import sys
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote


BASE_DIR = Path(__file__).parent.parent


def clean_fixed_width_text(raw: str) -> str:
    """
    HTTP Catcher wraps long lines at a fixed column width with trailing spaces.
    Strip trailing whitespace per line, then rejoin without newlines.
    """
    lines = raw.split('\n')
    cleaned = ''.join(line.rstrip() for line in lines)
    return cleaned


def split_frames(cleaned_text: str) -> list:
    """
    Split the cleaned text into individual frame JSON strings.
    Frames are separated by whitespace/blank regions in the original.
    Strategy: find all top-level { } JSON objects.
    """
    frames = []
    depth = 0
    start = None

    for i, ch in enumerate(cleaned_text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start is not None:
                candidate = cleaned_text[start:i+1]
                frames.append(candidate)
                start = None

    return frames


def parse_frame(frame_str: str) -> dict:
    """Parse a single frame string into a dict. Returns partial data on error."""
    try:
        return json.loads(frame_str)
    except json.JSONDecodeError as e:
        return {"_parse_error": str(e), "_raw_preview": frame_str[:200]}


def extract_query(frames: list) -> dict:
    """Find and decode the outbound query frame."""
    for f in frames:
        if isinstance(f, dict) and f.get("traceId"):
            messages = f.get("messages", [])
            for msg in messages:
                data = msg.get("data", {})
                if data.get("type") == "input-message":
                    content = data.get("content", "")
                    encoding = data.get("encoding", "")
                    if "url_encoded" in encoding:
                        content = unquote(content)
                    return {
                        "query_text": content,
                        "trace_id": f.get("traceId"),
                        "conversation_id": f.get("conversationId"),
                        "channel_id": f.get("channelId"),
                        "app_version": f.get("additionalPayload", {})
                                        .get("sessionContextAttributes", {})
                                        .get("userAgent", "unknown"),
                        "experiment_flags": f.get("additionalPayload", {})
                                             .get("requestAttributes", {})
                                             .get("experimentFlags", {}),
                        "show_ads": f.get("additionalPayload", {})
                                     .get("appContextAttributes", {})
                                     .get("showAds", "unknown"),
                        "walmart_plus_status": f.get("additionalPayload", {})
                                                .get("appContextAttributes", {})
                                                .get("walmartPlusStatus", "unknown"),
                        "screen_context": f.get("additionalPayload", {})
                                           .get("appContextAttributes", {})
                                           .get("screen", "unknown"),
                        "client_intent": f.get("additionalPayload", {})
                                          .get("requestAttributes", {})
                                          .get("clientIntent", "unknown"),
                    }
    return {"query_text": "NOT FOUND", "trace_id": None}


def extract_responses(frames: list) -> dict:
    """Extract all response frame types."""
    cot_steps = []
    text_responses = []
    product_carousel = None
    text_pills = []
    carousel_incomplete = False

    for f in frames:
        if not isinstance(f, dict):
            continue

        # Check for parse errors (indicates truncated carousel fragment)
        if "_parse_error" in f:
            raw = f.get("_raw_preview", "")
            if "CAROUSEL" in raw or "cards" in raw or "additionalCards" in raw or raw.startswith("AULT"):
                carousel_incomplete = True
            continue

        messages = f.get("messages", [])
        for msg in messages:
            data = msg.get("data", {})
            content = data.get("content", {})
            if not isinstance(content, dict):
                continue

            responses = content.get("responses", [])
            for resp in responses:
                msg_type = resp.get("messageType", "")
                payload = resp.get("payload", {})

                if msg_type == "COT":
                    text = payload.get("message", {}).get("text", "")
                    if text:
                        cot_steps.append(text)

                elif msg_type == "TEXT":
                    text = payload.get("message", {}).get("text", "")
                    # strip HTML tags
                    text = re.sub(r'<[^>]+>', '', text).strip()
                    if text:
                        text_responses.append(text)

                elif msg_type == "PRODUCT_CAROUSEL":
                    cards = payload.get("cards", [])
                    product_carousel = {
                        "card_count": len(cards),
                        "products": [],
                        "layout": payload.get("configuration", {}).get("layout", "unknown"),
                    }
                    for card in cards:
                        p = card.get("payload", card)
                        product_carousel["products"].append({
                            "title": p.get("title") or p.get("name", ""),
                            "price": p.get("price", {}).get("price") if isinstance(p.get("price"), dict) else p.get("price"),
                            "seller_id": p.get("sellerId", ""),
                            "seller_name": p.get("sellerName", ""),
                            "item_id": p.get("itemId") or p.get("usItemId", ""),
                            "rating": p.get("averageRating", ""),
                            "sponsored": p.get("isSponsored", False),
                        })

                elif msg_type == "TEXT_PILLS":
                    items = payload.get("items", [])
                    for item in items:
                        text_pills.append(item.get("title", ""))

    return {
        "cot_steps": cot_steps,
        "text_responses": text_responses,
        "product_carousel": product_carousel,
        "carousel_incomplete": carousel_incomplete,
        "text_pills": text_pills,
    }


def analyze(parsed: dict) -> None:
    """Print structured analysis to stdout."""
    q = parsed["query"]
    r = parsed["responses"]
    ts = parsed["captured_at"]

    print("=" * 60)
    print("SPARKY WEBSOCKET CAPTURE ANALYSIS")
    print(f"Captured: {ts}")
    print("=" * 60)

    print(f"\n📥 QUERY: {q.get('query_text', 'NOT FOUND')}")
    print(f"   App version:    {q.get('app_version', '?')}")
    print(f"   Screen context: {q.get('screen_context', '?')}")
    print(f"   Client intent:  {q.get('client_intent', '?')}")
    print(f"   showAds:        {q.get('show_ads', '?')}")
    print(f"   Walmart+:       {q.get('walmart_plus_status', '?')}")

    flags = q.get("experiment_flags", {})
    if flags:
        print(f"\n🧪 EXPERIMENT FLAGS ({len(flags)} active):")
        for k, v in flags.items():
            print(f"   {k}: {v}")

    if r["cot_steps"]:
        print(f"\n🧠 CHAIN OF THOUGHT ({len(r['cot_steps'])} steps):")
        for i, step in enumerate(r["cot_steps"], 1):
            print(f"   {i}. {step}")

    if r["text_responses"]:
        print(f"\n💬 TEXT RESPONSE:")
        for t in r["text_responses"]:
            print(f"   {t}")

    carousel = r["product_carousel"]
    if carousel:
        print(f"\n🛒 PRODUCT CAROUSEL ({carousel['card_count']} products, layout: {carousel['layout']}):")
        for i, p in enumerate(carousel["products"], 1):
            seller_tag = "1P" if p.get("seller_id") == "0" else f"3P ({p.get('seller_name', '?')})"
            sponsored_tag = " [SPONSORED]" if p.get("sponsored") else ""
            print(f"   {i}. {p.get('title', 'unknown')} | ${p.get('price', '?')} | {seller_tag}{sponsored_tag}")
    elif r["carousel_incomplete"]:
        print(f"\n⚠️  PRODUCT CAROUSEL: INCOMPLETE — middle of frame was cut off in HTTP Catcher")
        print(f"   → Go back to Messages tab, scroll up to find the large ↓ frame BEFORE the 'AULT' fragment")
        print(f"   → Copy that block, paste it BEFORE the 'AULT' line in new_capture_input.txt")
        print(f"   → Re-run this script")
    else:
        print(f"\n🛒 PRODUCT CAROUSEL: not present in this capture")

    if r["text_pills"]:
        print(f"\n💊 SUGGESTION PILLS ({len(r['text_pills'])}):")
        for pill in r["text_pills"]:
            print(f"   • {pill}")

    # Key observations
    print(f"\n🔍 KEY OBSERVATIONS:")
    if q.get("show_ads") is False or q.get("show_ads") == "false":
        print(f"   ✅ showAds: false (ad infrastructure dormant)")
    elif q.get("show_ads") is True:
        print(f"   🚨 showAds: TRUE — ADS ARE LIVE! Document immediately.")

    if r["text_responses"]:
        combined = " ".join(r["text_responses"]).lower()
        if "f-150" in combined or "truck" in combined:
            print(f"   ⚠️  PAGE CONTEXT OVERRIDE CONFIRMED — query ignored, served page-context products")

    if flags.get("cot_enable") == "true":
        print(f"   ℹ️  COT enabled — routing logic partially visible in chain-of-thought steps")

    print("\n" + "=" * 60)


def main():
    input_path = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE_DIR / "new_capture_input.txt"

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        sys.exit(1)

    raw = input_path.read_text(encoding="utf-8")
    cleaned = clean_fixed_width_text(raw)
    frame_strings = split_frames(cleaned)

    frames = []
    for fs in frame_strings:
        frames.append(parse_frame(fs))

    # Also look for raw AULT-style fragments that didn't parse as JSON
    # These are the tails of truncated carousel frames
    for chunk in re.split(r'\s{2,}', raw):
        chunk = chunk.strip()
        if chunk and not chunk.startswith('{') and ('AULT' in chunk or 'cards' in chunk):
            frames.append({"_parse_error": "truncated fragment", "_raw_preview": chunk})

    query = extract_query(frames)
    responses = extract_responses(frames)

    parsed = {
        "captured_at": datetime.now().isoformat(),
        "input_file": str(input_path),
        "frame_count": len(frame_strings),
        "query": query,
        "responses": responses,
    }

    analyze(parsed)

    # Save parsed JSON
    out_dir = BASE_DIR / "data"
    out_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"ws_parsed_{ts}.json"
    out_path.write_text(json.dumps(parsed, indent=2))
    print(f"\n💾 Saved to: {out_path}")


if __name__ == "__main__":
    main()
