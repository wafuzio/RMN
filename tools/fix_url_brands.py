#!/usr/bin/env python3
"""
Fix ads with URL-based brand names (www.amazon.com, etc.)

This script:
1. Finds ads with brand names that are URLs or domain names
2. Attempts to extract the real brand from the message field
3. Updates the database and JSON files with the corrected brand
"""

import sys
import os
import json
import re
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from web.db_store import _db_available
from core.brands import canonicalize, add_brand, smart_title
import psycopg2

def get_connection():
    """Get database connection"""
    return psycopg2.connect(
        host="127.0.0.1",
        port=54322,
        database="postgres",
        user="postgres",
        password="postgres"
    )

def is_url_brand(brand):
    """Check if a brand name is actually a URL or domain"""
    if not brand:
        return False
    
    # Check for common URL patterns
    if re.search(r'\.(com|net|org|edu|gov|co\.uk|io|ai)\b', brand, re.IGNORECASE):
        return True
    if re.search(r'^(https?://|www\.)', brand, re.IGNORECASE):
        return True
    if re.search(r'amazon\.com', brand, re.IGNORECASE):
        return True
    
    return False

def extract_brand_from_message(message):
    """Try to extract brand from message field"""
    if not message:
        return None
    
    # Try "Shop the <Brand> Store" pattern
    m = re.search(r'Shop\s+the\s+(.+?)\s+Store', message, re.IGNORECASE)
    if m:
        brand = m.group(1).strip()
        if brand and not is_url_brand(brand):
            return brand
    
    # Try "Visit the <Brand> Store" pattern
    m = re.search(r'Visit\s+the\s+(.+?)\s+Store', message, re.IGNORECASE)
    if m:
        brand = m.group(1).strip()
        if brand and not is_url_brand(brand):
            return brand
    
    return None

def fix_url_brands(dry_run=True):
    """Find and fix ads with URL-based brand names"""
    
    if not _db_available():
        print("❌ Database not available")
        return
    
    conn = get_connection()
    cur = conn.cursor()
    
    # Find ads with URL-based brands
    cur.execute("""
        SELECT a.id, a.original_id, a.brand, a.title, a.message, a.description, r.json_path
        FROM ads a
        JOIN runs r ON a.run_id = r.id
        WHERE a.brand LIKE '%.com%' 
           OR a.brand LIKE 'www.%'
           OR a.brand LIKE 'http%'
        ORDER BY a.id
    """)
    
    rows = cur.fetchall()
    print(f"\n📊 Found {len(rows)} ads with URL-based brand names\n")
    
    fixed_count = 0
    failed_count = 0
    json_updates = {}  # Track JSON files that need updating
    
    for row in rows:
        ad_id, original_id, old_brand, title, message, description, json_path = row
        
        # Try to extract real brand from message
        new_brand = extract_brand_from_message(message)
        
        if new_brand:
            # Canonicalize the brand
            brand_canon = canonicalize(new_brand)
            if not brand_canon:
                add_brand(new_brand)
                brand_canon = smart_title(new_brand)
            
            print(f"✅ {ad_id}: '{old_brand}' → '{brand_canon}'")
            print(f"   Message: {message[:80]}...")
            
            if not dry_run:
                # Update database
                cur.execute("""
                    UPDATE ads 
                    SET brand = %s
                    WHERE id = %s
                """, (brand_canon, ad_id))
                
                # Track JSON file for update
                if json_path:
                    if json_path not in json_updates:
                        json_updates[json_path] = []
                    json_updates[json_path].append({
                        'original_id': original_id,
                        'new_brand': brand_canon
                    })
            
            fixed_count += 1
        else:
            print(f"⚠️  {ad_id}: '{old_brand}' - Could not extract brand from message")
            print(f"   Message: {message[:80] if message else 'None'}...")
            failed_count += 1
    
    if not dry_run:
        # Update JSON files
        print(f"\n📝 Updating {len(json_updates)} JSON files...")
        
        for json_path, updates in json_updates.items():
            json_file = project_root / "output" / json_path
            
            if not json_file.exists():
                print(f"⚠️  JSON file not found: {json_path}")
                continue
            
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                
                ads = data.get('ads', [])
                updated = 0
                
                for update in updates:
                    for ad in ads:
                        if ad.get('id') == update['original_id']:
                            ad['brand'] = update['new_brand']
                            # Also update brand_canonical if it exists
                            if 'brand_canonical' in ad:
                                ad['brand_canonical'] = update['new_brand']
                            updated += 1
                            break
                
                if updated > 0:
                    with open(json_file, 'w') as f:
                        json.dump(data, f, indent=2)
                    print(f"   ✅ Updated {updated} ads in {json_path}")
            
            except Exception as e:
                print(f"   ❌ Error updating {json_path}: {e}")
        
        conn.commit()
    
    cur.close()
    conn.close()
    
    print(f"\n{'📋 DRY RUN SUMMARY' if dry_run else '✅ COMPLETED'}")
    print(f"   Fixed: {fixed_count}")
    print(f"   Failed: {failed_count}")
    print(f"   Total: {len(rows)}")
    
    if dry_run:
        print("\n💡 Run with --apply to actually update the database and JSON files")

if __name__ == "__main__":
    dry_run = "--apply" not in sys.argv
    fix_url_brands(dry_run=dry_run)
