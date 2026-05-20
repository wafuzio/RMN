#!/usr/bin/env python3
"""
Parse Sparky API captures and extract structured data.

Usage:
    python3 parse_sparky_capture.py <response_json_file>
    
Or import and use programmatically:
    from parse_sparky_capture import parse_sparky_response
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from urllib.parse import unquote


def parse_sparky_response(response_data: Dict[str, Any], query_text: str = None) -> Dict[str, Any]:
    """
    Parse a Sparky API response into structured metrics.
    
    Args:
        response_data: The JSON response from Sparky API
        query_text: Optional original query text (will try to extract from response if not provided)
    
    Returns:
        Structured data dict with all metrics
    """
    
    # Extract query metadata
    entities = response_data.get("entities", {})
    response_msg = response_data.get("responseMessage", {})
    
    # Try to extract query from rawResponse if not provided
    if not query_text:
        raw_response = response_msg.get("rawResponse", [])
        if raw_response and len(raw_response) > 0:
            query_text = raw_response[0].get("query", "")
    
    # Determine response mode
    has_products = bool(response_msg.get("rawResponse", [{}])[0].get("products"))
    has_google_sources = bool(response_msg.get("sourcesResponse", {}).get("google", {}).get("sources"))
    
    if has_products and not has_google_sources:
        response_mode = "product_carousel"
    elif has_google_sources and not has_products:
        response_mode = "editorial"
    elif has_products and has_google_sources:
        response_mode = "hybrid"
    else:
        response_mode = "deflection"
    
    # Parse products if present
    products = []
    garanimals_count = 0
    garanimals_positions = []
    brands = set()
    seller_1p_count = 0
    seller_3p_count = 0
    total_price = 0.0
    garanimals_total_price = 0.0
    badge_counts = {"best_seller": 0, "clearance": 0, "other": 0}
    
    raw_response = response_msg.get("rawResponse", [])
    if raw_response and len(raw_response) > 0:
        product_list = raw_response[0].get("products", [])
        
        for idx, product in enumerate(product_list, start=1):
            name = product.get("name", "")
            price = product.get("price", 0.0)
            seller = product.get("sellerName", "")
            
            # Detect brand (simple heuristic - first word or check for known brands)
            brand = "Unknown"
            name_lower = name.lower()
            if "garanimals" in name_lower:
                brand = "Garanimals"
                garanimals_count += 1
                garanimals_positions.append(idx)
                garanimals_total_price += price
            elif "children's place" in name_lower or "tcp" in name_lower:
                brand = "The Children's Place"
            elif "john deere" in name_lower:
                brand = "John Deere"
            else:
                # Try to extract first word as brand
                words = name.split()
                if words:
                    brand = words[0]
            
            brands.add(brand)
            total_price += price
            
            # Detect 1P vs 3P seller
            if seller.lower() in ["walmart.com", "walmart"]:
                seller_1p_count += 1
            else:
                seller_3p_count += 1
            
            # Parse badges
            badges = product.get("badges", {})
            groups_v2 = badges.get("groupsV2", []) or []
            for group in groups_v2:
                if group.get("name") == "flags":
                    for member in group.get("members", []):
                        for content in member.get("content", []):
                            badge_value = content.get("value", "").lower()
                            if "best seller" in badge_value:
                                badge_counts["best_seller"] += 1
                            elif "clearance" in badge_value:
                                badge_counts["clearance"] += 1
                            else:
                                badge_counts["other"] += 1
            
            products.append({
                "position": idx,
                "name": name,
                "brand": brand,
                "price": price,
                "seller": seller,
                "is_garanimals": brand == "Garanimals",
                "rating": product.get("rating", {}).get("averageRating"),
                "review_count": product.get("rating", {}).get("numberOfReviews"),
                "badges": [c.get("value") for g in groups_v2 for m in g.get("members", []) for c in m.get("content", [])]
            })
    
    # Parse editorial content
    preamble = entities.get("preamble", [""])[0] if entities.get("preamble") else ""
    followup = entities.get("followup", [""])[0] if entities.get("followup") else ""
    full_response = entities.get("response", [""])[0] if entities.get("response") else ""
    
    garanimals_mentioned = "garanimals" in full_response.lower()
    
    # Parse Google sources
    google_sources = response_msg.get("sourcesResponse", {}).get("google", {}).get("sources", [])
    source_domains = []
    
    interaction_bar = response_msg.get("interactionBar", {})
    if interaction_bar and interaction_bar.get("sources"):
        for source in interaction_bar["sources"]:
            domain = source.get("name", "")
            if domain:
                source_domains.append(domain)
    
    # Parse ad infrastructure
    ads_beacon_str = entities.get("adsBeacon", [""])[0] if entities.get("adsBeacon") else ""
    max_ads = 0
    ads_active = False
    specificity = ""
    brands_targeted = []
    
    if ads_beacon_str:
        try:
            ads_beacon = json.loads(ads_beacon_str)
            module_info_str = ads_beacon.get("moduleInfo", "")
            if module_info_str:
                module_info = json.loads(module_info_str)
                max_ads = ads_beacon.get("max_ads", 0)
                ads_active = len(ads_beacon.get("adSlots", [])) > 0
                specificity = module_info.get("specificity", "")
                brands_targeted = module_info.get("brands", [])
        except json.JSONDecodeError:
            pass
    
    # Parse search query reformulation
    search_query = entities.get("searchQuery", [""])[0] if entities.get("searchQuery") else ""
    
    # Build structured output
    return {
        "query_metadata": {
            "query_text": query_text,
            "timestamp": datetime.now().isoformat(),
            "conversation_title": entities.get("converseConversationTitle", [""])[0] if entities.get("converseConversationTitle") else ""
        },
        "response_classification": {
            "response_mode": response_mode,
            "intent_name": response_data.get("intentName", ""),
            "has_products": has_products,
            "has_editorial": bool(preamble or followup),
            "has_google_grounding": bool(google_sources)
        },
        "product_metrics": {
            "total_products": len(products),
            "garanimals_count": garanimals_count,
            "garanimals_positions": garanimals_positions,
            "garanimals_share": (garanimals_count / len(products) * 100) if products else 0.0,
            "brands": list(brands),
            "avg_garanimals_price": (garanimals_total_price / garanimals_count) if garanimals_count > 0 else 0.0,
            "avg_competitor_price": ((total_price - garanimals_total_price) / (len(products) - garanimals_count)) if (len(products) - garanimals_count) > 0 else 0.0,
            "seller_breakdown": {
                "1P": seller_1p_count,
                "3P": seller_3p_count
            },
            "badge_distribution": badge_counts,
            "products": products
        },
        "editorial_metrics": {
            "garanimals_mentioned": garanimals_mentioned,
            "preamble": preamble,
            "followup": followup,
            "full_response": full_response,
            "source_domains": source_domains,
            "source_count": len(source_domains)
        },
        "ad_infrastructure": {
            "max_ads": max_ads,
            "ads_active": ads_active,
            "specificity": specificity,
            "brands_targeted": brands_targeted
        },
        "search_query_reformulation": {
            "original": query_text,
            "reformulated": search_query
        }
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 parse_sparky_capture.py <response_json_file>")
        sys.exit(1)
    
    input_file = Path(sys.argv[1])
    
    if not input_file.exists():
        print(f"Error: File not found: {input_file}")
        sys.exit(1)
    
    with open(input_file, 'r') as f:
        response_data = json.load(f)
    
    # Extract query from filename or response
    query_text = input_file.stem.replace("_", " ")
    
    parsed = parse_sparky_response(response_data, query_text)
    
    # Save to data/captures (use script directory if input is from /tmp)
    if str(input_file).startswith('/tmp'):
        script_dir = Path(__file__).parent
        output_dir = script_dir / "data" / "captures"
    else:
        output_dir = input_file.parent / "data" / "captures"
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"{timestamp}_{input_file.stem}_parsed.json"
    
    with open(output_file, 'w') as f:
        json.dump(parsed, f, indent=2)
    
    print(f"✅ Parsed capture saved to: {output_file}")
    print(f"\n📊 Summary:")
    print(f"   Response Mode: {parsed['response_classification']['response_mode']}")
    print(f"   Products: {parsed['product_metrics']['total_products']}")
    print(f"   Garanimals: {parsed['product_metrics']['garanimals_count']} ({parsed['product_metrics']['garanimals_share']:.1f}%)")
    print(f"   Positions: {parsed['product_metrics']['garanimals_positions']}")
    print(f"   Editorial Mention: {'Yes' if parsed['editorial_metrics']['garanimals_mentioned'] else 'No'}")
    print(f"   Google Sources: {parsed['editorial_metrics']['source_count']}")
    

if __name__ == "__main__":
    main()
