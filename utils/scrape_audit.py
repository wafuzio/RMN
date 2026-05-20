#!/usr/bin/env python3
"""
Audit system for scrape quality - checks for blank ads, missing brands, etc.
Called immediately after each scrape completes to log issues.
"""
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class ScrapeAuditor:
    """Audits scrape results for quality issues"""
    
    def __init__(self, log_dir: Path):
        self.log_dir = Path(log_dir)
        self.audit_log = self.log_dir / "audit_log.jsonl"
        
    def audit_run(self, run_json_path: Path) -> Dict:
        """
        Audit a single run JSON file for quality issues.
        
        Returns dict with:
        - total_ads: int
        - blank_ads: int (ads with no image or broken image)
        - unknown_brands: int (ads with brand='unknown')
        - unbound_ads: int (ads missing critical fields)
        - issues: List[str] (human-readable issue descriptions)
        """
        try:
            with open(run_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to read {run_json_path}: {e}")
            return {"error": str(e)}
        
        ads = data.get("ads", [])
        total_ads = len(ads)
        
        blank_ads = 0
        unknown_brands = 0
        unbound_ads = 0
        issues = []
        
        for i, ad in enumerate(ads):
            ad_type = ad.get("ad_type", "unknown")
            position = ad.get("position", i+1)
            
            # Check for blank/missing images
            image_url = ad.get("image_url", "")
            image_path = ad.get("image_path", "")
            
            if not image_url and not image_path:
                blank_ads += 1
                issues.append(f"Ad #{position} ({ad_type}): No image URL or path")
            elif image_path and not Path(image_path).exists():
                blank_ads += 1
                issues.append(f"Ad #{position} ({ad_type}): Image file missing: {image_path}")
            
            # Check for unknown brands
            brand = ad.get("brand", "").lower()
            if brand == "unknown" or not brand:
                unknown_brands += 1
                issues.append(f"Ad #{position} ({ad_type}): Brand is 'unknown' or missing")
            
            # Check for unbound ads (missing critical fields)
            missing_fields = []
            critical_fields = ["ad_type", "position"]
            
            for field in critical_fields:
                if not ad.get(field):
                    missing_fields.append(field)
            
            if missing_fields:
                unbound_ads += 1
                issues.append(f"Ad #{position}: Missing critical fields: {', '.join(missing_fields)}")
        
        # Build audit result
        result = {
            "timestamp": datetime.now().isoformat(),
            "run_file": str(run_json_path),
            "keyword": data.get("keyword", "unknown"),
            "retailer": data.get("retailer", "unknown"),
            "total_ads": total_ads,
            "blank_ads": blank_ads,
            "unknown_brands": unknown_brands,
            "unbound_ads": unbound_ads,
            "issues": issues,
            "quality_score": self._calculate_quality_score(total_ads, blank_ads, unknown_brands, unbound_ads)
        }
        
        # Log to audit file
        self._log_audit(result)
        
        return result
    
    def _calculate_quality_score(self, total: int, blank: int, unknown: int, unbound: int) -> float:
        """Calculate quality score 0-100 based on issues found"""
        if total == 0:
            return 0.0
        
        # Deduct points for each issue type
        blank_penalty = (blank / total) * 40  # Up to 40 points off for blank ads
        unknown_penalty = (unknown / total) * 30  # Up to 30 points off for unknown brands
        unbound_penalty = (unbound / total) * 30  # Up to 30 points off for unbound ads
        
        score = 100 - blank_penalty - unknown_penalty - unbound_penalty
        return max(0.0, round(score, 2))
    
    def _log_audit(self, result: Dict):
        """Append audit result to JSONL log file"""
        try:
            with open(self.audit_log, 'a', encoding='utf-8') as f:
                f.write(json.dumps(result) + '\n')
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")
    
    def get_recent_audits(self, limit: int = 10) -> List[Dict]:
        """Get most recent audit results"""
        if not self.audit_log.exists():
            return []
        
        try:
            with open(self.audit_log, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Get last N lines
            recent_lines = lines[-limit:]
            return [json.loads(line) for line in recent_lines]
        except Exception as e:
            logger.error(f"Failed to read audit log: {e}")
            return []
    
    def audit_latest_run(self, runs_dir: Path, keyword: str) -> Optional[Dict]:
        """
        Find and audit the most recent run for a keyword.
        
        Args:
            runs_dir: Directory containing run JSON files
            keyword: Keyword to search for
            
        Returns:
            Audit result dict or None if no matching run found
        """
        runs_dir = Path(runs_dir)
        if not runs_dir.exists():
            return None
        
        # Find all JSON files - different retailers use different naming patterns
        # Amazon: run_results_amazon_<client>_<timestamp>.json
        # Target: run_results_<timestamp>.json
        # Instacart: run_results_<timestamp>.json (in nested runs/<timestamp>/ dirs)
        # Walmart: walmart_<keyword>_meta.json
        
        matching_files = []
        
        # Strategy 1: Look for run_results_*.json files (Amazon, Target, Instacart)
        matching_files.extend(runs_dir.glob("run_results_*.json"))
        
        # Strategy 2: Look in nested timestamp directories (Instacart pattern)
        for subdir in runs_dir.glob("*/"):
            if subdir.is_dir():
                matching_files.extend(subdir.glob("run_results_*.json"))
        
        # Strategy 3: Look for keyword-specific files (Walmart pattern)
        keyword_safe = keyword.replace(' ', '_').replace('/', '_')
        matching_files.extend(runs_dir.glob(f"*{keyword_safe}*.json"))
        
        # Strategy 4: Broader search if nothing found
        if not matching_files:
            matching_files = [f for f in runs_dir.glob("*.json") 
                            if keyword.lower() in f.name.lower()]
        
        # Filter out duplicates
        matching_files = list(set(matching_files))
        
        if not matching_files:
            # Only warn if truly no files exist - this is now a real issue
            logger.debug(f"No run files found for keyword: {keyword} in {runs_dir}")
            return None
        
        # Get most recent by modification time
        latest_file = max(matching_files, key=lambda p: p.stat().st_mtime)
        
        return self.audit_run(latest_file)


def audit_scrape_result(run_json_path: str, log_dir: str = None) -> Dict:
    """
    Convenience function to audit a single scrape result.
    
    Args:
        run_json_path: Path to run JSON file
        log_dir: Directory for audit logs (defaults to same dir as run file)
        
    Returns:
        Audit result dict
    """
    run_path = Path(run_json_path)
    
    if log_dir is None:
        log_dir = run_path.parent
    
    auditor = ScrapeAuditor(log_dir)
    return auditor.audit_run(run_path)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python3 scrape_audit.py <run_json_path>")
        sys.exit(1)
    
    result = audit_scrape_result(sys.argv[1])
    
    print(f"\n=== Audit Results ===")
    print(f"File: {result.get('run_file')}")
    print(f"Keyword: {result.get('keyword')}")
    print(f"Retailer: {result.get('retailer')}")
    print(f"Total Ads: {result.get('total_ads')}")
    print(f"Quality Score: {result.get('quality_score')}/100")
    print(f"\nIssues Found:")
    print(f"  - Blank Ads: {result.get('blank_ads')}")
    print(f"  - Unknown Brands: {result.get('unknown_brands')}")
    print(f"  - Unbound Ads: {result.get('unbound_ads')}")
    
    if result.get('issues'):
        print(f"\nDetailed Issues:")
        for issue in result['issues'][:10]:  # Show first 10
            print(f"  • {issue}")
        if len(result['issues']) > 10:
            print(f"  ... and {len(result['issues']) - 10} more")
