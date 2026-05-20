#!/usr/bin/env python3
"""
Helper script to generate CAPTURE_LOG.md entries from parsed JSON.

Usage:
    python3 add_to_log.py data/captures/YYYYMMDD_HHMMSS_query_parsed.json
    
This will print a formatted log entry that you can copy-paste into CAPTURE_LOG.md
"""

import json
import sys
from pathlib import Path
from datetime import datetime


def format_log_entry(parsed_data: dict, capture_number: int = None) -> str:
    """Generate a formatted log entry from parsed capture data."""
    
    query = parsed_data['query_metadata']['query_text']
    timestamp = parsed_data['query_metadata']['timestamp']
    date = datetime.fromisoformat(timestamp).strftime('%b %d, %Y')
    
    mode = parsed_data['response_classification']['response_mode']
    mode_display = {
        'product_carousel': 'Product Carousel',
        'editorial': 'Editorial',
        'deflection': 'Deflection',
        'hybrid': 'Hybrid'
    }.get(mode, mode.title())
    
    products = parsed_data['product_metrics']['products']
    editorial = parsed_data['editorial_metrics']
    
    # Build entry
    lines = []
    
    # Header
    if capture_number:
        lines.append(f"## Capture #{capture_number} - {query}")
    else:
        lines.append(f"## Capture - {query}")
    lines.append(f"**Date:** {date}")
    lines.append(f'**Query:** "{query}"')
    lines.append(f"**Response Mode:** {mode_display}")
    lines.append("")
    
    # Products
    if products:
        lines.append("### Products Shown (Position 1-5)")
        for p in products[:5]:
            brand = p['brand']
            name = p['name']
            price = f"${p['price']:.2f}" if p['price'] else "N/A"
            rating = f"{p['rating']:.1f}" if p['rating'] else "N/A"
            seller = p['seller']
            badges = ', '.join(p['badges']) if p['badges'] else "None"
            
            lines.append(f"{p['position']}. **{brand}** - {name} - {price} - Rating: {rating} - Seller: {seller} - Badge: {badges}")
        lines.append("")
    else:
        lines.append("### Products Shown")
        lines.append("- None (editorial response only)")
        lines.append("")
    
    # Editorial
    lines.append("### Editorial Content")
    lines.append(f"- **Preamble:** {editorial['preamble'] if editorial['preamble'] else 'None'}")
    lines.append(f"- **Followup:** {editorial['followup'] if editorial['followup'] else 'None'}")
    
    if editorial['source_domains']:
        lines.append(f"- **Google Sources:** {', '.join(editorial['source_domains'])}")
    else:
        lines.append("- **Google Sources:** None")
    
    lines.append(f"- **Garanimals Mentioned:** {'Yes' if editorial['garanimals_mentioned'] else 'No'}")
    lines.append("")
    
    # Technical details
    ad_infra = parsed_data['ad_infrastructure']
    search_reform = parsed_data['search_query_reformulation']
    
    lines.append("### Technical Details")
    lines.append(f"- **Intent Name:** {parsed_data['response_classification']['intent_name']}")
    lines.append(f"- **Search Query Reformulation:** {search_reform['original']} → {search_reform['reformulated']}")
    lines.append(f"- **Max Ads:** {ad_infra['max_ads']}")
    lines.append(f"- **Ads Active:** {'Yes' if ad_infra['ads_active'] else 'No'}")
    lines.append(f"- **Specificity:** {ad_infra['specificity']}")
    lines.append("")
    
    # Observable facts
    lines.append("### Observable Facts")
    
    metrics = parsed_data['product_metrics']
    if products:
        garan_count = metrics['garanimals_count']
        total = metrics['total_products']
        garan_pct = metrics['garanimals_share']
        positions = metrics['garanimals_positions']
        
        lines.append(f"- Garanimals appeared in {garan_count} out of {total} products ({garan_pct:.0f}%)")
        if positions:
            lines.append(f"- Garanimals positions: {', '.join(map(str, positions))}")
        else:
            lines.append(f"- **CRITICAL:** No Garanimals visibility")
        
        # Seller breakdown
        seller_1p = metrics['seller_breakdown']['1P']
        seller_3p = metrics['seller_breakdown']['3P']
        lines.append(f"- Seller breakdown: {seller_1p} 1P (Walmart.com), {seller_3p} 3P (third-party)")
        
        # Price analysis
        if garan_count > 0:
            avg_garan = metrics['avg_garanimals_price']
            avg_comp = metrics['avg_competitor_price']
            lines.append(f"- Avg Garanimals price: ${avg_garan:.2f}")
            if avg_comp > 0:
                lines.append(f"- Avg competitor price: ${avg_comp:.2f}")
        
        # Badges
        badge_dist = metrics['badge_distribution']
        if any(badge_dist.values()):
            lines.append(f"- Badges: {badge_dist['best_seller']} Best Seller, {badge_dist['clearance']} Clearance, {badge_dist['other']} Other")
        
        # Brands present
        brands = metrics['brands']
        lines.append(f"- Brands present: {', '.join(brands)}")
    
    # Query characteristics
    query_lower = query.lower()
    query_keywords = []
    if 'best' in query_lower:
        query_keywords.append('"best"')
    if 'cheap' in query_lower or 'budget' in query_lower or 'affordable' in query_lower:
        query_keywords.append('price-focused')
    if 'quality' in query_lower or 'durable' in query_lower:
        query_keywords.append('quality-focused')
    if 'vs' in query_lower or 'or' in query_lower:
        query_keywords.append('comparative')
    if 'garanimals' in query_lower:
        query_keywords.append('branded')
    
    if query_keywords:
        lines.append(f"- Query keywords: {', '.join(query_keywords)}")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    
    return '\n'.join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 add_to_log.py <parsed_json_file>")
        print("\nExample:")
        print("  python3 add_to_log.py data/captures/20260316_175242_sample_romper_query_parsed.json")
        sys.exit(1)
    
    input_file = Path(sys.argv[1])
    
    if not input_file.exists():
        print(f"Error: File not found: {input_file}")
        sys.exit(1)
    
    with open(input_file, 'r') as f:
        parsed_data = json.load(f)
    
    # Generate entry
    entry = format_log_entry(parsed_data)
    
    print("=" * 80)
    print("COPY THE FOLLOWING INTO CAPTURE_LOG.md:")
    print("=" * 80)
    print()
    print(entry)
    print()
    print("=" * 80)
    print(f"✅ Log entry generated from: {input_file.name}")
    print("📋 Copy the text above and paste into CAPTURE_LOG.md")
    

if __name__ == "__main__":
    main()
