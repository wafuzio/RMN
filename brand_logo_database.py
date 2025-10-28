"""
Brand Logo Database Manager

Downloads and manages brand logos from retailer ads for reuse in the frontend.
Creates a centralized database of brand logos with metadata.
"""

import os
import json
import hashlib
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from utils.time_utils import now_iso_z
from core.brands import canonicalize


class BrandLogoDatabase:
    def __init__(self, base_dir: str = None):
        """Initialize the brand logo database
        
        Args:
            base_dir: Base directory for the project (defaults to script directory)
        """
        if base_dir is None:
            base_dir = Path(__file__).parent
        else:
            base_dir = Path(base_dir)
        
        self.base_dir = base_dir
        self.logos_dir = base_dir / "brand_logos"
        self.db_file = self.logos_dir / "brand_logo_database.json"
        
        # Create directories
        self.logos_dir.mkdir(exist_ok=True)
        
        # Load existing database
        self.database = self._load_database()
    
    def _load_database(self) -> Dict[str, Any]:
        """Load the brand logo database from JSON"""
        if self.db_file.exists():
            try:
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Warning: Could not load brand logo database: {e}")
                return {"brands": {}, "metadata": {"last_updated": None, "total_brands": 0}}
        else:
            return {"brands": {}, "metadata": {"last_updated": None, "total_brands": 0}}
    
    def _save_database(self):
        """Save the brand logo database to JSON"""
        self.database["metadata"]["last_updated"] = now_iso_z()
        self.database["metadata"]["total_brands"] = len(self.database["brands"])
        
        with open(self.db_file, 'w', encoding='utf-8') as f:
            json.dump(self.database, f, indent=2, ensure_ascii=False)
    
    def _normalize_brand_name(self, brand: str) -> str:
        """Normalize brand name for database key (lowercase, no special chars)"""
        return brand.lower().replace("'", "").replace("&", "and").replace(".", "").replace(" ", "_").strip()
    
    def _find_next_logo_number(self, brand_key: str, ext: str) -> int:
        """Find the next available number for a brand logo"""
        existing_files = list(self.logos_dir.glob(f"{brand_key}*.{ext}"))
        if not existing_files:
            return 1
        
        # Extract numbers from existing files
        numbers = []
        for f in existing_files:
            # Match pattern: brand_key.ext or brand_key_N.ext
            name = f.stem  # filename without extension
            if name == brand_key:
                numbers.append(1)
            elif name.startswith(f"{brand_key}_"):
                try:
                    num = int(name.split('_')[-1])
                    numbers.append(num)
                except ValueError:
                    pass
        
        return max(numbers) + 1 if numbers else 1
    
    def _download_logo(self, url: str, brand_key: str) -> Optional[str]:
        """Download logo from URL and save to logos directory
        
        Uses content-based hashing to deduplicate identical images.
        Multiple different logos for the same brand get numbered (brand.png, brand_2.png, etc.)
        
        Args:
            url: URL of the logo image
            brand_key: Normalized brand name for filename
            
        Returns:
            Relative path to saved logo file, or None if download failed
        """
        try:
            # Download image
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            # Hash the actual image content for deduplication
            content_hash = hashlib.md5(response.content).hexdigest()
            
            # Determine file extension from URL or content-type
            ext = "png"  # Default
            if url.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                ext = url.split('.')[-1].split('?')[0]
            elif 'content-type' in response.headers:
                content_type = response.headers['content-type']
                if 'jpeg' in content_type:
                    ext = 'jpg'
                elif 'png' in content_type:
                    ext = 'png'
                elif 'gif' in content_type:
                    ext = 'gif'
                elif 'webp' in content_type:
                    ext = 'webp'
            
            # Check if this exact image content already exists for this brand
            existing_files = list(self.logos_dir.glob(f"{brand_key}*.{ext}"))
            for existing_file in existing_files:
                existing_hash = hashlib.md5(existing_file.read_bytes()).hexdigest()
                if existing_hash == content_hash:
                    # Exact same image already exists, reuse it
                    return f"brand_logos/{existing_file.name}"
            
            # New unique image - find next available number
            logo_number = self._find_next_logo_number(brand_key, ext)
            
            if logo_number == 1:
                filename = f"{brand_key}.{ext}"
            else:
                filename = f"{brand_key}_{logo_number}.{ext}"
            
            filepath = self.logos_dir / filename
            
            # Save image
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            return f"brand_logos/{filename}"
        
        except Exception as e:
            print(f"Warning: Could not download logo from {url}: {e}")
            return None
    
    def add_brand_logo(self, brand: str, logo_url: str, retailer: str, metadata: Dict[str, Any] = None) -> bool:
        """Add or update a brand logo in the database
        
        Args:
            brand: Brand name (e.g., "Lay's", "Sour Patch Kids")
            logo_url: URL of the brand logo
            retailer: Retailer where logo was found (e.g., "instacart", "kroger")
            metadata: Additional metadata (ad_type, keyword, etc.)
            
        Returns:
            True if logo was added/updated, False otherwise
        """
        # NEVER add "unknown" to logo database
        if not brand or brand.lower() == 'unknown':
            return False
        
        # Canonicalize brand name using lexicon
        canon = canonicalize(brand) if brand else None
        display_name = canon or brand
        
        # Double-check after canonicalization
        if display_name.lower() == 'unknown':
            return False
        
        brand_key = self._normalize_brand_name(display_name)
        
        # Check if we already have this logo
        if brand_key in self.database["brands"]:
            existing = self.database["brands"][brand_key]
            # If same URL, just update metadata
            if existing.get("logo_url") == logo_url:
                if retailer not in existing.get("retailers", []):
                    existing["retailers"].append(retailer)
                existing["last_seen"] = now_iso_z()
                self._save_database()
                return True
        
        # Download the logo
        logo_path = self._download_logo(logo_url, brand_key)
        if not logo_path:
            return False
        
        # Add to database
        self.database["brands"][brand_key] = {
            "brand_name": display_name,  # Canonical brand name with proper casing
            "logo_url": logo_url,  # Original URL
            "logo_file": logo_path,  # Local file path
            "retailers": [retailer],
            "first_seen": now_iso_z(),
            "last_seen": now_iso_z(),
            "metadata": metadata or {}
        }
        
        self._save_database()
        print(f"✅ Added brand logo: {brand} → {logo_path}")
        return True
    
    def get_brand_logo(self, brand: str) -> Optional[Dict[str, Any]]:
        """Get brand logo information from database
        
        Args:
            brand: Brand name
            
        Returns:
            Dictionary with logo information, or None if not found
        """
        brand_key = self._normalize_brand_name(brand)
        return self.database["brands"].get(brand_key)
    
    def get_logo_path(self, brand: str) -> Optional[str]:
        """Get the local file path for a brand's logo
        
        Args:
            brand: Brand name
            
        Returns:
            Relative path to logo file, or None if not found
        """
        logo_info = self.get_brand_logo(brand)
        if logo_info:
            return logo_info.get("logo_file")
        return None
    
    def list_all_brands(self) -> list:
        """Get list of all brands in database"""
        return [info["brand_name"] for info in self.database["brands"].values()]
    
    def get_frontend_map(self) -> Dict[str, str]:
        """
        Get a simple mapping of brand names to logo file paths for frontend use
        
        Returns:
            Dictionary mapping brand names to logo file paths
        """
        frontend_map = {
            info["brand_name"]: info["logo_file"]
            for info in self.database["brands"].values()
        }
        
        return frontend_map
    
    def export_for_frontend(self, output_file: str = None) -> Dict[str, str]:
        """Export brand logo mapping for frontend use
        
        Args:
            output_file: Optional file to save JSON export
            
        Returns:
            Dictionary mapping brand names to logo file paths
        """
        frontend_map = self.get_frontend_map()
        
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(frontend_map, f, indent=2, ensure_ascii=False)
        
        return frontend_map
    
    def sync_to_lexicon(self, lexicon_path: str = "config/brands.json"):
        """
        Sync all brands from logo database to the brand lexicon
        Ensures every brand with a logo is also in the lexicon
        """
        import json
        
        try:
            # Load lexicon
            with open(lexicon_path, 'r') as f:
                lexicon_brands = json.load(f)
            
            # Create set of existing brand names (lowercase)
            existing_names = {brand['name'].lower() for brand in lexicon_brands}
            
            # Add missing brands
            added_count = 0
            for brand_info in self.database["brands"].values():
                brand_name = brand_info["brand_name"]
                if brand_name.lower() not in existing_names:
                    lexicon_brands.append({
                        'name': brand_name,
                        'synonyms': []
                    })
                    added_count += 1
            
            if added_count > 0:
                # Sort and save
                lexicon_brands_sorted = sorted(lexicon_brands, key=lambda x: x['name'].lower())
                with open(lexicon_path, 'w') as f:
                    json.dump(lexicon_brands_sorted, f, indent=2, ensure_ascii=False)
                print(f"[LOGO DB] Synced {added_count} brands to lexicon")
            
            return added_count
        except Exception as e:
            print(f"[LOGO DB] Failed to sync to lexicon: {e}")
            return 0


# Example usage
if __name__ == "__main__":
    db = BrandLogoDatabase()
    
    # Example: Add a brand logo
    db.add_brand_logo(
        brand="Lay's",
        logo_url="https://display.instacart.com/cdn-cgi/image/dpr=1,q=50,sharpen=0,f=auto,animate=false,metadata=copyright,/public/72917cb9-cc41-404c-9a7e-dcdedf0a7ee5-1.png",
        retailer="instacart",
        metadata={"ad_type": "Display Ad", "keyword": "chips"}
    )
    
    # Get logo path
    logo_path = db.get_logo_path("Lay's")
    print(f"Lay's logo: {logo_path}")
    
    # List all brands
    print(f"Total brands: {len(db.list_all_brands())}")
    
    # Export for frontend
    frontend_map = db.export_for_frontend("brand_logos/frontend_logos.json")
    print(f"Exported {len(frontend_map)} brand logos for frontend")
