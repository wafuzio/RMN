#!/usr/bin/env python3
"""
Index Garanimals product catalog and generate query templates.

Usage:
    python3 index_catalog.py
    
This will:
1. Read the Garanimals catalog Excel file
2. Extract product types, categories, attributes
3. Generate query templates for testing
4. Save to queries/generated_queries.json
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Set
import openpyxl


def index_catalog(excel_path: Path) -> Dict[str, any]:
    """
    Parse Garanimals catalog and extract product taxonomy.
    
    Returns:
        Dict with product_types, categories, attributes, etc.
    """
    
    print(f"📖 Reading catalog: {excel_path.name}")
    
    wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
    
    # Try to find the main data sheet
    sheet = wb.active
    print(f"   Using sheet: {sheet.title}")
    
    # Extract headers
    headers = []
    for cell in sheet[1]:
        if cell.value:
            headers.append(str(cell.value).strip())
    
    print(f"   Found {len(headers)} columns")
    
    # Map to actual column names from Garanimals catalog
    fineline_col = None
    style_col = None
    style_name_col = None
    pdp_title_col = None
    color_col = None
    size_col = None
    gender_col = None
    
    for idx, header in enumerate(headers):
        header_lower = header.lower()
        if header == 'Fineline':
            fineline_col = idx
        elif header == 'Style':
            style_col = idx
        elif header == 'StyleName':
            style_name_col = idx
        elif 'PDP' in header and 'Title' in header:
            pdp_title_col = idx
        elif 'Color' in header and 'Short' in header:
            color_col = idx
        elif header == 'Size':
            size_col = idx
        elif header == 'Gender':
            gender_col = idx
    
    # Extract unique values
    finelines = set()
    styles = set()
    style_names = set()
    pdp_titles = set()
    colors = set()
    sizes = set()
    genders = set()
    
    # Extract product types from style names and PDP titles
    product_types = set()
    
    row_count = 0
    for row in sheet.iter_rows(min_row=2, values_only=True):
        row_count += 1
        
        if fineline_col is not None and row[fineline_col]:
            finelines.add(str(row[fineline_col]).strip())
        
        if style_col is not None and row[style_col]:
            styles.add(str(row[style_col]).strip())
        
        if style_name_col is not None and row[style_name_col]:
            style_name = str(row[style_name_col]).strip()
            style_names.add(style_name)
            # Extract product type keywords from style name
            style_lower = style_name.lower()
            for keyword in ['romper', 'jean', 'shirt', 'short', 'dress', 'pajama', 
                           'swim', 'legging', 'outfit', 'bodysuit', 'jumpsuit', 
                           'overall', 'pant', 'skirt', 'hoodie', 'jacket', 'sweater',
                           'tank', 'tee', 'polo', 'cardigan', 'vest']:
                if keyword in style_lower:
                    product_types.add(keyword.title())
        
        if pdp_title_col is not None and row[pdp_title_col]:
            pdp_title = str(row[pdp_title_col]).strip()
            pdp_titles.add(pdp_title)
            # Also extract from PDP title
            title_lower = pdp_title.lower()
            for keyword in ['romper', 'jean', 'shirt', 'short', 'dress', 'pajama', 
                           'swim', 'legging', 'outfit', 'bodysuit', 'jumpsuit', 
                           'overall', 'pant', 'skirt', 'hoodie', 'jacket', 'sweater',
                           'tank', 'tee', 'polo', 'cardigan', 'vest', 'set']:
                if keyword in title_lower:
                    product_types.add(keyword.title())
        
        if color_col is not None and row[color_col]:
            colors.add(str(row[color_col]).strip())
        
        if size_col is not None and row[size_col]:
            sizes.add(str(row[size_col]).strip())
        
        if gender_col is not None and row[gender_col]:
            genders.add(str(row[gender_col]).strip())
    
    print(f"   Processed {row_count} rows")
    print(f"   Found {len(product_types)} product types")
    print(f"   Found {len(finelines)} finelines")
    print(f"   Found {len(styles)} styles")
    print(f"   Found {len(genders)} genders")
    
    return {
        "product_types": sorted(list(product_types)),
        "finelines": sorted(list(finelines)),
        "styles": sorted(list(styles)),
        "style_names": sorted(list(style_names))[:50],  # Sample
        "pdp_titles": sorted(list(pdp_titles))[:50],  # Sample
        "colors": sorted(list(colors)),
        "sizes": sorted(list(sizes)),
        "genders": sorted(list(genders)),
        "total_products": row_count,
        "headers": headers
    }


def generate_query_templates(catalog_data: Dict) -> Dict[str, List[Dict]]:
    """
    Generate query templates based on catalog data.
    
    Returns:
        Dict organized by investigation type
    """
    
    queries = {
        "branded_queries": [],
        "category_queries": [],
        "comparative_queries": [],
        "quality_perception_queries": [],
        "value_queries": [],
        "seasonal_queries": [],
        "mix_and_match_queries": []
    }
    
    # Branded queries - one per product type
    for product_type in catalog_data["product_types"][:20]:  # Limit to top 20
        queries["branded_queries"].append({
            "query": f"garanimals {product_type.lower()}",
            "product_type": product_type,
            "intent": "branded",
            "priority": "high",
            "expected_mode": "product_carousel"
        })
    
    # Category queries - generic category searches
    common_categories = [
        "rompers", "jeans", "t-shirts", "shorts", "dresses", 
        "pajamas", "swimwear", "leggings", "outfits", "bodysuits",
        "jumpsuits", "overalls", "pants", "skirts", "hoodies"
    ]
    
    for category in common_categories:
        queries["category_queries"].append({
            "query": f"toddler {category} walmart",
            "product_type": category,
            "intent": "category",
            "priority": "critical",
            "expected_mode": "product_carousel"
        })
        
        # Also add "best" variant
        queries["category_queries"].append({
            "query": f"best {category} for toddlers",
            "product_type": category,
            "intent": "category_quality",
            "priority": "high",
            "expected_mode": "product_carousel"
        })
    
    # Comparative queries
    competitors = ["children's place", "cat and jack", "carters", "okie dokie"]
    for competitor in competitors:
        queries["comparative_queries"].append({
            "query": f"garanimals vs {competitor}",
            "competitor": competitor,
            "intent": "comparative",
            "priority": "high",
            "expected_mode": "deflection"
        })
        
        queries["comparative_queries"].append({
            "query": f"which is better garanimals or {competitor}",
            "competitor": competitor,
            "intent": "comparative_quality",
            "priority": "high",
            "expected_mode": "deflection"
        })
    
    # Quality perception queries
    quality_queries = [
        "are garanimals clothes good quality",
        "do garanimals clothes hold up in the wash",
        "garanimals reviews",
        "how is garanimals quality",
        "are garanimals durable",
        "do garanimals clothes shrink",
        "garanimals vs target brand quality",
        "is garanimals worth it"
    ]
    
    for query in quality_queries:
        queries["quality_perception_queries"].append({
            "query": query,
            "intent": "quality_perception",
            "priority": "critical",
            "expected_mode": "editorial"
        })
    
    # Value queries
    value_queries = [
        "cheap kids clothes walmart",
        "toddler clothes under $10",
        "affordable kids clothing",
        "best value toddler clothes",
        "budget kids clothes walmart",
        "inexpensive toddler outfits"
    ]
    
    for query in value_queries:
        queries["value_queries"].append({
            "query": query,
            "intent": "value",
            "priority": "medium",
            "expected_mode": "product_carousel"
        })
    
    # Seasonal queries
    seasonal_queries = [
        "back to school toddler clothes walmart",
        "summer clothes for kids",
        "Easter toddler outfits",
        "winter clothes for toddlers",
        "fall toddler clothes",
        "holiday outfits for kids",
        "spring toddler clothes",
        "toddler beach clothes"
    ]
    
    for query in seasonal_queries:
        queries["seasonal_queries"].append({
            "query": query,
            "intent": "seasonal",
            "priority": "medium",
            "expected_mode": "product_carousel"
        })
    
    # Mix-and-match queries (Garanimals' core differentiator)
    mix_match_queries = [
        "mix and match kids clothes",
        "coordinating toddler outfits",
        "kids clothes that go together",
        "matching toddler sets",
        "garanimals mix and match",
        "easy outfit sets for toddlers"
    ]
    
    for query in mix_match_queries:
        queries["mix_and_match_queries"].append({
            "query": query,
            "intent": "mix_and_match",
            "priority": "critical",
            "expected_mode": "product_carousel"
        })
    
    return queries


def main():
    # Find the catalog file
    catalog_path = Path(__file__).parent / "Copy of S26 - WM Garanimals OLX Assortment.xlsx"
    
    if not catalog_path.exists():
        print(f"❌ Error: Catalog not found at {catalog_path}")
        sys.exit(1)
    
    # Index the catalog
    catalog_data = index_catalog(catalog_path)
    
    # Generate queries
    print("\n🔍 Generating query templates...")
    queries = generate_query_templates(catalog_data)
    
    # Count total queries
    total_queries = sum(len(q) for q in queries.values())
    print(f"   Generated {total_queries} total queries:")
    for category, query_list in queries.items():
        print(f"      {category}: {len(query_list)}")
    
    # Save catalog index
    output_dir = Path(__file__).parent / "queries"
    output_dir.mkdir(exist_ok=True)
    
    catalog_output = output_dir / "catalog_index.json"
    with open(catalog_output, 'w') as f:
        json.dump(catalog_data, f, indent=2)
    print(f"\n✅ Catalog index saved to: {catalog_output}")
    
    # Save query templates
    queries_output = output_dir / "generated_queries.json"
    with open(queries_output, 'w') as f:
        json.dump(queries, f, indent=2)
    print(f"✅ Query templates saved to: {queries_output}")
    
    # Save a simple text file for easy copy-paste
    queries_txt = output_dir / "query_list.txt"
    with open(queries_txt, 'w') as f:
        for category, query_list in queries.items():
            f.write(f"\n# {category.upper().replace('_', ' ')}\n")
            for q in query_list:
                f.write(f"{q['query']}\n")
    print(f"✅ Query list saved to: {queries_txt}")
    
    print(f"\n📊 Summary:")
    print(f"   Total product types in catalog: {len(catalog_data['product_types'])}")
    print(f"   Total queries generated: {total_queries}")
    print(f"   Ready for testing!")


if __name__ == "__main__":
    main()
