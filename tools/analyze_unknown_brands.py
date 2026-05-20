#!/usr/bin/env python3
"""
Analyze 'unknown' brand occurrences and suggest improvements to brand detection.
"""
import json
import sys
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Tuple

def load_brand_database(project_root: Path) -> Dict:
    """Load the brand database and synonyms"""
    brands_file = project_root / "data" / "brands.json"
    
    if not brands_file.exists():
        return {"brands": {}, "synonyms": {}}
    
    try:
        with open(brands_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading brands database: {e}")
        return {"brands": {}, "synonyms": {}}

def analyze_unknown_brands(output_dir: Path, limit: int = 100) -> Tuple[List[Dict], Dict]:
    """
    Scan recent run files for ads with brand='unknown' and analyze patterns.
    
    Returns:
        - List of unknown brand instances with context
        - Statistics dict
    """
    unknown_instances = []
    stats = {
        "total_ads": 0,
        "unknown_ads": 0,
        "by_retailer": defaultdict(int),
        "by_ad_type": defaultdict(int),
        "product_titles": Counter(),
        "image_urls": []
    }
    
    # Find recent run JSON files
    run_files = []
    for retailer_dir in output_dir.iterdir():
        if not retailer_dir.is_dir():
            continue
        
        for client_dir in retailer_dir.iterdir():
            if not client_dir.is_dir():
                continue
            
            runs_dir = client_dir / "runs"
            if runs_dir.exists():
                run_files.extend(runs_dir.glob("*.json"))
    
    # Sort by modification time, most recent first
    run_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    
    # Analyze up to limit files
    for run_file in run_files[:limit]:
        try:
            with open(run_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            retailer = data.get("retailer", "unknown")
            keyword = data.get("keyword", "unknown")
            timestamp = data.get("timestamp", "unknown")
            
            ads = data.get("ads", [])
            stats["total_ads"] += len(ads)
            
            for ad in ads:
                brand = ad.get("brand", "").lower()
                
                if brand == "unknown" or not brand:
                    stats["unknown_ads"] += 1
                    stats["by_retailer"][retailer] += 1
                    
                    ad_type = ad.get("ad_type", "unknown")
                    stats["by_ad_type"][ad_type] += 1
                    
                    # Collect context for analysis
                    product_title = ad.get("product_title", "")
                    if product_title:
                        stats["product_titles"][product_title] += 1
                    
                    image_url = ad.get("image_url", "")
                    
                    unknown_instances.append({
                        "retailer": retailer,
                        "keyword": keyword,
                        "timestamp": timestamp,
                        "ad_type": ad_type,
                        "product_title": product_title,
                        "image_url": image_url,
                        "position": ad.get("position"),
                        "run_file": str(run_file)
                    })
                    
        except Exception as e:
            print(f"Error processing {run_file}: {e}")
            continue
    
    return unknown_instances, stats

def suggest_brand_additions(unknown_instances: List[Dict], brands_db: Dict) -> List[Dict]:
    """
    Analyze unknown instances and suggest potential brand additions.
    
    Returns list of suggestions with:
    - suggested_brand: str
    - confidence: str (high/medium/low)
    - occurrences: int
    - example_titles: List[str]
    """
    suggestions = []
    
    # Group by product title patterns
    title_groups = defaultdict(list)
    for instance in unknown_instances:
        title = instance.get("product_title", "").lower()
        if title:
            title_groups[title].append(instance)
    
    # Look for repeated patterns that might be brands
    for title, instances in title_groups.items():
        if len(instances) < 2:  # Only suggest if seen multiple times
            continue
        
        # Extract potential brand names from title
        # Common patterns: "Brand Name Product" or "Product by Brand"
        words = title.split()
        
        # Check if first 1-2 words might be a brand
        for i in range(1, min(3, len(words) + 1)):
            potential_brand = " ".join(words[:i])
            
            # Skip if already in database
            if potential_brand in brands_db.get("brands", {}):
                continue
            if potential_brand in brands_db.get("synonyms", {}):
                continue
            
            # Skip common words
            common_words = {"the", "a", "an", "and", "or", "for", "with", "by", "in", "on"}
            if potential_brand in common_words:
                continue
            
            suggestions.append({
                "suggested_brand": potential_brand,
                "confidence": "medium" if len(instances) >= 5 else "low",
                "occurrences": len(instances),
                "example_titles": [inst["product_title"] for inst in instances[:3]],
                "retailers": list(set(inst["retailer"] for inst in instances))
            })
    
    # Sort by occurrences
    suggestions.sort(key=lambda x: x["occurrences"], reverse=True)
    
    return suggestions

def main():
    project_root = Path(__file__).resolve().parent.parent
    output_dir = project_root / "output"
    
    print("🔍 Analyzing unknown brands...\n")
    
    # Load brand database
    brands_db = load_brand_database(project_root)
    print(f"Loaded {len(brands_db.get('brands', {}))} brands and {len(brands_db.get('synonyms', {}))} synonyms\n")
    
    # Analyze recent runs
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    unknown_instances, stats = analyze_unknown_brands(output_dir, limit)
    
    # Print statistics
    print(f"=== Statistics (last {limit} run files) ===")
    print(f"Total ads analyzed: {stats['total_ads']}")
    print(f"Unknown brands: {stats['unknown_ads']} ({stats['unknown_ads']/max(1, stats['total_ads'])*100:.1f}%)")
    
    print(f"\nBy Retailer:")
    for retailer, count in sorted(stats['by_retailer'].items(), key=lambda x: x[1], reverse=True):
        print(f"  {retailer}: {count}")
    
    print(f"\nBy Ad Type:")
    for ad_type, count in sorted(stats['by_ad_type'].items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {ad_type}: {count}")
    
    # Generate suggestions
    suggestions = suggest_brand_additions(unknown_instances, brands_db)
    
    if suggestions:
        print(f"\n=== Suggested Brand Additions ({len(suggestions)} found) ===")
        for i, sugg in enumerate(suggestions[:20], 1):
            print(f"\n{i}. '{sugg['suggested_brand']}' (confidence: {sugg['confidence']})")
            print(f"   Occurrences: {sugg['occurrences']}")
            print(f"   Retailers: {', '.join(sugg['retailers'])}")
            print(f"   Example titles:")
            for title in sugg['example_titles']:
                print(f"     - {title[:80]}")
    else:
        print("\n✅ No clear brand patterns found in unknown ads")
    
    # Save detailed report
    report_file = project_root / "logs" / "unknown_brands_report.json"
    report_file.parent.mkdir(exist_ok=True)
    
    report = {
        "timestamp": str(Path.ctime(Path(__file__))),
        "stats": {
            "total_ads": stats["total_ads"],
            "unknown_ads": stats["unknown_ads"],
            "by_retailer": dict(stats["by_retailer"]),
            "by_ad_type": dict(stats["by_ad_type"])
        },
        "suggestions": suggestions[:50],  # Top 50
        "sample_unknowns": unknown_instances[:100]  # First 100 examples
    }
    
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n📄 Detailed report saved to: {report_file}")

if __name__ == "__main__":
    main()
