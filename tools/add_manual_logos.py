#!/usr/bin/env python3
"""
Add brand logos manually to the brand logo database
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from brand_logo_database import BrandLogoDatabase

def add_logos():
    """Add Conagra Brands and egglife logos"""
    
    db = BrandLogoDatabase()
    
    # The logos will be added with placeholder URLs since we have the images directly
    # In a real scenario, these would be downloaded from retailer ads
    
    logos_to_add = [
        {
            "brand": "Conagra Brands",
            "logo_url": "manual_upload_conagra",
            "retailer": "manual",
            "verified": True,
            "notes": "Manually added Conagra Brands corporate logo"
        },
        {
            "brand": "egglife",
            "logo_url": "manual_upload_egglife", 
            "retailer": "manual",
            "verified": True,
            "notes": "Manually added egglife brand logo"
        }
    ]
    
    print("Adding logos to brand logo database...\n")
    
    for logo_info in logos_to_add:
        brand = logo_info["brand"]
        
        # Add to database with metadata
        success = db.add_brand_logo(
            brand=brand,
            logo_url=logo_info["logo_url"],
            retailer=logo_info["retailer"],
            metadata={
                "verified": logo_info["verified"],
                "notes": logo_info["notes"],
                "manual_upload": True
            }
        )
        
        if success:
            print(f"✅ Added {brand} to logo database")
        else:
            print(f"⚠️  {brand} already exists in database")
    
    print(f"\n📊 Total brands in database: {len(db.database['brands'])}")
    print(f"📁 Database location: {db.db_file}")

if __name__ == "__main__":
    add_logos()
