#!/usr/bin/env python3
"""
Brand Review Tool - Interactive GUI for correcting unknown/uncertain brand extractions

Features:
- Shows ads with unknown/uncertain brands
- Displays ad screenshot for visual confirmation
- Allows manual brand name input
- Updates JSON files with corrected brand
- Renames image files to match corrected brand
- Adds brand to lexicon
- Adds campaign codes as aliases for future matching
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from PIL import Image, ImageTk
import json
import os
import glob
import re
from pathlib import Path
import shutil

# Import brand logo database
try:
    from brand_logo_database import BrandLogoDatabase
    LOGO_DB_AVAILABLE = True
except ImportError:
    LOGO_DB_AVAILABLE = False
    print("[WARN] Brand logo database not available")

class BrandReviewTool:
    def __init__(self, root):
        self.root = root
        self.root.title("Brand Review Tool - Correct Unknown Brands")
        self.root.geometry("1200x900")
        
        # Data
        self.unknown_ads = []
        self.current_index = 0
        self.lexicon_path = "config/brands.json"
        self.lexicon_brands = []  # Cache lexicon in memory
        
        # Initialize logo database
        if LOGO_DB_AVAILABLE:
            try:
                # Point to output/ directory where logos are stored
                base_dir = Path(os.getcwd()) / "output"
                self.logo_db = BrandLogoDatabase(base_dir=str(base_dir))
                brand_count = len(self.logo_db.database.get('brands', {}))
                print(f"[INFO] Brand logo database loaded ({brand_count} brands)")
            except Exception as e:
                print(f"[WARN] Failed to load logo database: {e}")
                self.logo_db = None
        else:
            self.logo_db = None
        
        # Load lexicon into memory
        self.load_lexicon()
        
        # Sync logo database brands to lexicon
        self.sync_logo_brands_to_lexicon()
        
        # Setup UI
        self.setup_ui()
        
        # Load unknown brands
        self.load_unknown_brands()
        
        if self.unknown_ads:
            self.show_current_ad()
        else:
            messagebox.showinfo("No Unknown Brands", "All brands have been identified!")
            self.root.quit()
    
    def setup_ui(self):
        """Setup the GUI layout"""
        # Top frame - Progress
        progress_frame = ttk.Frame(self.root, padding="10")
        progress_frame.pack(fill=tk.X)
        
        self.progress_label = ttk.Label(progress_frame, text="Loading...", font=("Arial", 12, "bold"))
        self.progress_label.pack(side=tk.LEFT)
        
        # Main content frame
        content_frame = ttk.Frame(self.root, padding="10")
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Left side - Image preview
        left_frame = ttk.LabelFrame(content_frame, text="Ad Preview", padding="10")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        self.image_label = ttk.Label(left_frame)
        self.image_label.pack(fill=tk.BOTH, expand=True)
        
        # Right side - Ad details and input
        right_frame = ttk.Frame(content_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        # Ad details
        details_frame = ttk.LabelFrame(right_frame, text="Ad Details", padding="10")
        details_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.details_text = scrolledtext.ScrolledText(details_frame, height=15, wrap=tk.WORD, font=("Courier", 10))
        self.details_text.pack(fill=tk.BOTH, expand=True)
        
        # Image path display
        self.image_path_label = ttk.Label(details_frame, text="", foreground="blue", font=("Courier", 8), wraplength=400)
        self.image_path_label.pack(fill=tk.X, pady=(5, 0))
        
        # Brand input with co-brand support
        input_frame = ttk.LabelFrame(right_frame, text="Correct Brand Name(s)", padding="10")
        input_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Current brand with logo
        brand_row = ttk.Frame(input_frame)
        brand_row.grid(row=0, column=0, columnspan=3, sticky=tk.EW, pady=5)
        
        ttk.Label(brand_row, text="Current Brand:", font=("Arial", 10, "bold")).pack(side=tk.LEFT)
        self.current_brand_label = ttk.Label(brand_row, text="", foreground="red", font=("Arial", 10))
        self.current_brand_label.pack(side=tk.LEFT, padx=(10, 10))
        
        # Brand logo display (small thumbnail)
        self.brand_logo_label = ttk.Label(brand_row)
        self.brand_logo_label.pack(side=tk.LEFT, padx=(0, 10))
        
        # Container for brand entries
        self.brand_entries_frame = ttk.Frame(input_frame)
        self.brand_entries_frame.grid(row=1, column=0, columnspan=3, sticky=tk.EW, pady=5)
        
        # Track brand entry widgets
        self.brand_entries = []
        self.brand_labels = []
        self.remove_buttons = []
        
        # Add co-brand button (create before entries so update_add_button_state works)
        self.add_cobrand_button = ttk.Button(input_frame, text="+ Add Co-Brand", command=self.add_cobrand_field)
        self.add_cobrand_button.grid(row=2, column=0, columnspan=3, pady=(5, 0))
        
        # Create first brand entry
        self.create_brand_entry(0)
        
        input_frame.columnconfigure(1, weight=1)
        
        # Suggestions
        suggestions_frame = ttk.LabelFrame(right_frame, text="Suggestions (click to use)", padding="10")
        suggestions_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.suggestions_frame = ttk.Frame(suggestions_frame)
        self.suggestions_frame.pack(fill=tk.X)
        
        # Action buttons
        button_frame = ttk.Frame(right_frame)
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="← Previous", command=self.previous_ad).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Skip", command=self.next_ad).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Save All Similar & Next →", command=self.save_correction, style="Accent.TButton").pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Mark as Kroger House Ad", command=self.mark_as_kroger).pack(side=tk.LEFT, padx=5)
        
        # Style
        style = ttk.Style()
        style.configure("Accent.TButton", foreground="green", font=("Arial", 10, "bold"))
    
    def create_brand_entry(self, index):
        """Create a brand entry field with label and optional remove button"""
        row_frame = ttk.Frame(self.brand_entries_frame)
        row_frame.pack(fill=tk.X, pady=2)
        
        # Label (Brand A, Brand B, etc.)
        label_text = chr(65 + index) if index == 0 else chr(65 + index)  # A, B, C, D
        label = ttk.Label(row_frame, text=f"Brand {label_text}:", font=("Arial", 10, "bold"), width=10)
        label.pack(side=tk.LEFT)
        
        # Entry field
        entry = ttk.Entry(row_frame, font=("Arial", 11))
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        entry.bind('<Return>', lambda e: self.save_correction())
        
        # Remove button (only for co-brands, not the first one)
        if index > 0:
            remove_btn = ttk.Button(row_frame, text="✕", width=3, command=lambda: self.remove_cobrand_field(index))
            remove_btn.pack(side=tk.LEFT)
            self.remove_buttons.append(remove_btn)
        else:
            self.remove_buttons.append(None)
        
        self.brand_entries.append(entry)
        self.brand_labels.append(label)
        
        # Update button visibility
        self.update_add_button_state()
    
    def add_cobrand_field(self):
        """Add a new co-brand entry field"""
        if len(self.brand_entries) < 4:
            self.create_brand_entry(len(self.brand_entries))
    
    def remove_cobrand_field(self, index):
        """Remove a co-brand entry field"""
        if index > 0 and index < len(self.brand_entries):
            # Get the row frame (parent of the entry)
            row_frame = self.brand_entries[index].master
            row_frame.destroy()
            
            # Remove from tracking lists
            self.brand_entries.pop(index)
            self.brand_labels.pop(index)
            self.remove_buttons.pop(index)
            
            # Re-label remaining entries
            for i, label in enumerate(self.brand_labels):
                label_text = chr(65 + i)
                label.config(text=f"Brand {label_text}:")
            
            # Update button visibility
            self.update_add_button_state()
    
    def update_add_button_state(self):
        """Enable/disable the add co-brand button based on current count"""
        if len(self.brand_entries) >= 4:
            self.add_cobrand_button.config(state='disabled')
        else:
            self.add_cobrand_button.config(state='normal')
    
    def get_all_brands(self):
        """Get all non-empty brand names from entry fields"""
        brands = []
        for entry in self.brand_entries:
            brand = entry.get().strip()
            if brand:
                brands.append(brand)
        return brands
    
    def set_brand_entries(self, brands):
        """Set the brand entry fields with given brands"""
        # Clear existing entries beyond the first
        while len(self.brand_entries) > 1:
            self.remove_cobrand_field(1)
        
        # Set first brand
        if brands:
            self.brand_entries[0].delete(0, tk.END)
            self.brand_entries[0].insert(0, brands[0])
        
        # Add additional brands
        for i, brand in enumerate(brands[1:], 1):
            if i < 4:  # Max 4 brands
                self.add_cobrand_field()
                self.brand_entries[i].delete(0, tk.END)
                self.brand_entries[i].insert(0, brand)
    
    def load_lexicon(self):
        """Load brand lexicon into memory"""
        try:
            with open(self.lexicon_path, 'r') as f:
                self.lexicon_brands = json.load(f)
            print(f"[INFO] Loaded {len(self.lexicon_brands)} brands from lexicon")
        except Exception as e:
            print(f"[WARN] Failed to load lexicon: {e}")
            self.lexicon_brands = []
    
    def is_brand_in_lexicon(self, brand):
        """Check if a brand exists in the lexicon (uses cached data)"""
        if not brand:
            return False
        
        brand_lower = brand.lower()
        
        # Check if brand name matches (case-insensitive)
        for lex_brand in self.lexicon_brands:
            if lex_brand['name'].lower() == brand_lower:
                return True
            # Also check synonyms
            if any(syn.lower() == brand_lower for syn in lex_brand.get('synonyms', [])):
                return True
        
        return False
    
    def load_unknown_brands(self):
        """Load all ads with unknown or uncertain brands"""
        print("Scanning for unknown brands...")
        
        # Scan all retailer JSON files (Kroger, Walmart, Instacart, etc.)
        json_files = []
        for retailer in ['kroger', 'walmart', 'instacart']:
            # Kroger/Instacart: output/retailer/client/runs/*.json
            pattern1 = f'output/{retailer}/*/runs/*.json'
            # Walmart: output/walmart/client/runs/TIMESTAMP/*.json
            pattern2 = f'output/{retailer}/*/runs/*/*.json'
            
            retailer_files = glob.glob(pattern1) + glob.glob(pattern2)
            # Remove duplicates
            retailer_files = list(set(retailer_files))
            json_files.extend(retailer_files)
            if retailer_files:
                print(f"  Found {len(retailer_files)} {retailer} files")
        
        print(f"Total: {len(json_files)} JSON files to scan")
        
        for json_file in json_files:
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                
                for result in data.get('results', []):
                    for ad in result.get('ads', []):
                        advertisers = ad.get('advertisers', [])
                        
                        # Check if unknown or uncertain in JSON
                        is_unknown_in_json = (
                            not advertisers or
                            advertisers == ['unknown'] or
                            any(self.is_uncertain_brand(adv) for adv in advertisers)
                        )
                        
                        # Find associated image file first
                        image_path = self.find_ad_image(ad, json_file)
                        
                        # CRITICAL: Also check if image filename contains "unknown"
                        # This catches cases where JSON has a brand but screenshot failed to match it
                        is_unknown_in_filename = False
                        
                        # If image_path from JSON doesn't exist, search for unknown files
                        if image_path and not os.path.exists(image_path):
                            # Try to find an unknown file with similar timestamp
                            # Handle nested timestamp dirs (Walmart: runs/TIMESTAMP/file.json)
                            base_dir = os.path.dirname(os.path.dirname(json_file))
                            # If base_dir ends with a timestamp pattern, go up one more level
                            if re.match(r'\d{14}$', os.path.basename(base_dir)):
                                base_dir = os.path.dirname(base_dir)
                            
                            ad_type = ad.get('type')
                            # Map ad types to subfolders
                            type_to_folder = {
                                'TOA': 'TOA',
                                'Skyscraper': 'Skyscraper',
                                'CuratedCarousel': 'Carousel',
                                'sba': 'SBA',
                                'sbv': 'SBV',
                                'tile_takeover': 'Tile',
                                'top_banner': 'Banner'
                            }
                            subfolder = type_to_folder.get(ad_type)
                            
                            if subfolder:
                                search_dir = os.path.join(base_dir, subfolder)
                                if os.path.exists(search_dir):
                                    # Look for unknown files
                                    for filename in os.listdir(search_dir):
                                        if '__unknown__' in filename:
                                            # Check if timestamp matches roughly (date + hour + minute, ignore seconds)
                                            stored_filename = os.path.basename(image_path)
                                            # Extract timestamp from both (date and hour-minute only)
                                            import re
                                            stored_ts = re.search(r'D(\d{4}-\d{2}-\d{2}_T\d{2}-\d{2})', stored_filename)
                                            unknown_ts = re.search(r'D(\d{4}-\d{2}-\d{2}_T\d{2}-\d{2})', filename)
                                            
                                            # Match if date+hour+minute are the same (ignore seconds)
                                            if stored_ts and unknown_ts:
                                                stored_dt = stored_ts.group(1)  # e.g., 2025-10-24_T02-58
                                                unknown_dt = unknown_ts.group(1)
                                                if stored_dt == unknown_dt:
                                                    # Found matching unknown file
                                                    image_path = os.path.join(search_dir, filename)
                                                    is_unknown_in_filename = True
                                                    print(f"[WARN] JSON path doesn't exist, found unknown file instead")
                                                    print(f"      Advertisers in JSON: {advertisers}")
                                                    print(f"      Unknown file: {filename}")
                                                    break
                        
                        # Also check if the existing path looks like a campaign-code brand segment
                        if image_path and os.path.exists(image_path):
                            filename = os.path.basename(image_path)
                            # Flag explicit unknown
                            if '__unknown__' in filename and not is_unknown_in_filename:
                                is_unknown_in_filename = True
                                print(f"[WARN] Found 'unknown' in filename but JSON has: {advertisers}")
                            else:
                                # Parse taxonomy filename: retailer__brand_slug__ad_type__client__search__Dts_idx.ext
                                parts = filename.split('__')
                                if len(parts) >= 2:
                                    brand_slug_in_file = parts[1]
                                    # Compare against advertiser slugs
                                    adv_slugs = [self.to_slug(a) for a in (advertisers or [])]
                                    if brand_slug_in_file not in adv_slugs:
                                        # If filename brand slug looks like a campaign code per heuristics, flag it
                                        looks_like_code = self.is_uncertain_brand(brand_slug_in_file.replace('_', ' '))
                                        if looks_like_code:
                                            is_unknown_in_filename = True
                                            print(f"[WARN] Filename brand slug '{brand_slug_in_file}' doesn't match advertisers {adv_slugs}")
                        
                        # Flag as unknown if EITHER condition is true
                        if is_unknown_in_json or is_unknown_in_filename:
                            self.unknown_ads.append({
                                'json_file': json_file,
                                'ad': ad,
                                'image_path': image_path,
                                'current_brand': advertisers[0] if advertisers else 'unknown'
                            })
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Error reading {json_file}: {e}")
                continue
        
        print(f"\n📊 Scan complete:")
        print(f"   Files scanned: {len(json_files)}")
        print(f"   Uncertain ads found: {len(self.unknown_ads)}")
        
        # Show breakdown by reason
        unknown_count = sum(1 for ad in self.unknown_ads if ad['current_brand'] == 'unknown')
        pattern_count = sum(1 for ad in self.unknown_ads if ad['current_brand'] != 'unknown')
        print(f"   - Explicitly 'unknown': {unknown_count}")
        print(f"   - Uncertain patterns: {pattern_count}")
    
    def is_uncertain_brand(self, brand):
        """Check if a brand name looks uncertain or like a campaign code"""
        if not brand or brand == 'unknown':
            return True
        
        # Check if brand is in lexicon - if so, it's valid
        if self.is_brand_in_lexicon(brand):
            return False
        
        # Kroger and Kroger-branded products are valid, not uncertain
        if brand.lower().startswith('kroger'):
            return False
        
        # Single word that's too short or generic
        if len(brand) <= 3:
            return True
        
        # Specific campaign code patterns
        uncertain_patterns = [
            r'^(TOAOB|MSM|SSM|FWGOL)',  # Kroger campaign prefixes
            r'(KB|MB|TOA|Scale|Act)\d+',  # Campaign type codes
            r'(Q\d+|FY\d+|H\d+)$',  # Quarter/fiscal year codes
            r'^NT\d+\s*NT$',  # NT codes
        ]
        
        for pattern in uncertain_patterns:
            if re.search(pattern, brand, re.IGNORECASE):
                return True
        
        # HEURISTIC: Check if it looks like a campaign code vs a real brand
        # Count digits
        digit_count = sum(c.isdigit() for c in brand)
        letter_count = sum(c.isalpha() for c in brand)
        
        # If more than 30% digits, likely a campaign code
        if letter_count > 0 and digit_count / len(brand) > 0.3:
            return True
        
        # If contains 4-digit year (2024, 2025, etc.)
        if re.search(r'20\d{2}', brand):
            return True
        
        # If has month names mixed with other stuff (as whole words, not substrings)
        months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
        brand_lower = brand.lower()
        for month in months:
            # Use word boundary to avoid matching "may" in "Mayer"
            if re.search(r'\b' + month + r'\b', brand_lower) and len(brand) > 8:
                return True
        
        # If has weird capitalization (multiple capitals not at start)
        capitals = [i for i, c in enumerate(brand) if c.isupper()]
        if len(capitals) > 2:
            if any(i > 0 and brand[i-1].islower() for i in capitals[1:]):
                return True
        
        # If ends with 4+ digits
        if re.search(r'\d{4,}$', brand):
            return True
        
        return False
    
    def find_ad_image(self, ad, json_file, search_term=None):
        """Find the image file associated with this ad"""
        ad_type = ad.get('type', '')
        
        # Detect retailer from JSON path (output/RETAILER/CLIENT/runs/...)
        retailer = None
        try:
            path_parts = Path(json_file).parts
            output_idx = path_parts.index('output')
            if output_idx + 1 < len(path_parts):
                retailer = path_parts[output_idx + 1]  # kroger, walmart, instacart
        except (ValueError, IndexError):
            retailer = 'kroger'  # Default fallback
        
        # Get base directory from JSON path
        # Kroger/Instacart: output/retailer/CLIENT/runs/*.json
        # Walmart: output/walmart/CLIENT/runs/TIMESTAMP/*.json
        runs_dir = os.path.dirname(json_file)
        base_dir = os.path.dirname(runs_dir)
        
        # For Walmart, if runs_dir ends with timestamp, go up one more level
        if retailer == 'walmart' and re.match(r'\d{14}$', os.path.basename(runs_dir)):
            base_dir = os.path.dirname(base_dir)
        
        # Extract timestamp from JSON filename to match images from same run
        # Format: run_results_KEYWORD_YYYY-MM-DD_HH-MM-SS.json
        json_basename = os.path.basename(json_file)
        timestamp_match = re.search(r'(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})', json_basename)
        run_timestamp = timestamp_match.group(1) if timestamp_match else None
        
        print(f"\n[DEBUG] Finding image for {ad_type} ad (retailer: {retailer})")
        print(f"[DEBUG] JSON file: {json_file}")
        print(f"[DEBUG] Base dir: {base_dir}")
        print(f"[DEBUG] Run timestamp: {run_timestamp}")
        print(f"[DEBUG] Search term: {search_term}")
        
        # Map ad types to subfolders based on retailer
        if retailer == 'kroger':
            type_to_folder = {
                'TOA': 'TOA',
                'Skyscraper': 'Skyscraper',
                'CuratedCarousel': 'Carousel'
            }
            type_to_path_field = {
                'TOA': 'toa_image_path',
                'Skyscraper': 'skyscraper_image_path',
                'CuratedCarousel': 'carousel_image_path'
            }
        elif retailer == 'walmart':
            type_to_folder = {
                'sba': 'SBA',
                'sbv': 'SBV',
                'tile_takeover': 'Tile',
                'top_banner': 'Banner'
            }
            type_to_path_field = {
                'sba': 'image_path',
                'sbv': 'image_path',
                'tile_takeover': 'image_path',
                'top_banner': 'image_path'
            }
        elif retailer == 'instacart':
            type_to_folder = {
                'display_ad': 'DisplayAd',
                'shoppable_recipe_ad': 'ShoppableRecipe',
                'main': 'Main'
            }
            type_to_path_field = {
                'display_ad': 'image_path',
                'shoppable_recipe_ad': 'image_path',
                'main': 'image_path'
            }
        else:
            type_to_folder = {}
            type_to_path_field = {}
        
        # Try to get image path from JSON first
        path_field = type_to_path_field.get(ad_type, 'image_path')
        image_path_from_json = ad.get(path_field, '')
        
        if image_path_from_json:
            # Try relative to base_dir
            full_path = os.path.join(base_dir, image_path_from_json)
            if os.path.exists(full_path):
                return full_path
            # Try absolute path
            if os.path.exists(image_path_from_json):
                return image_path_from_json
        
        # Fallback: search by pattern in the appropriate subfolder
        subfolder = type_to_folder.get(ad_type)
        if subfolder:
            search_dir = os.path.join(base_dir, subfolder)
            if os.path.exists(search_dir):
                advertiser = ad.get('advertisers', ['unknown'])[0] if ad.get('advertisers') else 'unknown'
                advertiser_slug = self.to_slug(advertiser)
                
                # Search for images matching the advertiser
                import glob as glob_module
                pattern = os.path.join(search_dir, f"*__{advertiser_slug}__*.png")
                matches = glob_module.glob(pattern)
                
                if matches:
                    # Filter by timestamp if available
                    if run_timestamp:
                        date_part = run_timestamp.split('_')[0]
                        time_part = run_timestamp.split('_')[1] if '_' in run_timestamp else ''
                        time_formatted = time_part.rsplit('-', 1)[0] + '.' + time_part.rsplit('-', 1)[1] if time_part and '-' in time_part else time_part
                        timestamp_matches = [m for m in matches if f"D{date_part}_T{time_formatted}" in m]
                        if timestamp_matches:
                            matches = timestamp_matches
                    
                    # Return most recent match
                    matches.sort(key=os.path.getmtime, reverse=True)
                    return matches[0]
        
        # Legacy Kroger-specific logic (keeping for backward compatibility)
        if ad_type == 'CuratedCarousel':
            carousel_path = ad.get('carousel_image_path', '')
            print(f"[DEBUG] Carousel path from JSON: {carousel_path}")
            if carousel_path:
                # Path is relative to base_dir (e.g., "Carousel/kroger__...png")
                full_path = os.path.join(base_dir, carousel_path)
                print(f"[DEBUG] Trying full path: {full_path}")
                print(f"[DEBUG] Exists? {os.path.exists(full_path)}")
                if os.path.exists(full_path):
                    return full_path
                # Also try absolute path
                if os.path.exists(carousel_path):
                    print(f"[DEBUG] Found as absolute path")
                    return carousel_path
        
        elif ad_type == 'TOA':
            toa_path = ad.get('toa_image_path', '')
            print(f"[DEBUG] TOA path from JSON: {toa_path}")
            if toa_path:
                full_path = os.path.join(base_dir, toa_path)
                print(f"[DEBUG] Trying full path: {full_path}")
                print(f"[DEBUG] Exists? {os.path.exists(full_path)}")
                if os.path.exists(full_path):
                    return full_path
                if os.path.exists(toa_path):
                    return toa_path
            
            # TOA images may not have path in JSON, try to find by pattern
            toa_dir = os.path.join(base_dir, 'TOA')
            if os.path.exists(toa_dir):
                print(f"[DEBUG] Searching TOA directory: {toa_dir}")
                advertiser = ad.get('advertisers', ['unknown'])[0] if ad.get('advertisers') else 'unknown'
                advertiser_slug = self.to_slug(advertiser)
                
                import glob as glob_module
                pattern = os.path.join(toa_dir, f"*__{advertiser_slug}__toa__*.png")
                matches = glob_module.glob(pattern)
                print(f"[DEBUG] Pattern: {pattern}")
                print(f"[DEBUG] All matches: {len(matches)}")
                
                # Filter by timestamp if available
                if run_timestamp and matches:
                    # Image format: kroger__BRAND__toa__CLIENT__KEYWORD__DYYYY-MM-DD_THH-MM.SS_N.png
                    # Convert timestamp format: 2025-10-22_00-26-00 -> D2025-10-22_T00-26.00
                    # Extract date and time parts
                    date_part = run_timestamp.split('_')[0]  # 2025-10-22
                    time_part = run_timestamp.split('_')[1] if '_' in run_timestamp else ''  # 00-26-00
                    # Convert HH-MM-SS to HH-MM.SS (replace last dash with dot)
                    time_formatted = time_part.rsplit('-', 1)[0] + '.' + time_part.rsplit('-', 1)[1] if time_part and '-' in time_part else time_part
                    
                    # Match images with this date and time
                    timestamp_matches = [m for m in matches if f"D{date_part}_T{time_formatted}" in m]
                    if timestamp_matches:
                        matches = timestamp_matches
                        print(f"[DEBUG] Filtered by timestamp: {len(matches)}")
                    
                    # Further filter by position if available
                    ad_position = ad.get('position')
                    if ad_position and matches:
                        # Image filename ends with _N.png where N is the position
                        position_matches = [m for m in matches if m.endswith(f"_{ad_position}.png")]
                        if position_matches:
                            matches = position_matches
                            print(f"[DEBUG] Filtered by position {ad_position}: {len(matches)}")
                
                if matches:
                    # If multiple matches, prefer the one with matching position
                    matches.sort(key=os.path.getmtime, reverse=True)
                    print(f"[DEBUG] Using: {matches[0]}")
                    return matches[0]
        
        elif ad_type == 'Skyscraper':
            sky_path = ad.get('skyscraper_image_path', '')
            print(f"[DEBUG] Skyscraper path from JSON: {sky_path}")
            if sky_path:
                full_path = os.path.join(base_dir, sky_path)
                print(f"[DEBUG] Trying full path: {full_path}")
                print(f"[DEBUG] Exists? {os.path.exists(full_path)}")
                if os.path.exists(full_path):
                    return full_path
                if os.path.exists(sky_path):
                    return sky_path
            
            # Skyscraper images may not have path in JSON, try to find by pattern
            # Look in Skyscraper directory for matching files
            skyscraper_dir = os.path.join(base_dir, 'Skyscraper')
            if os.path.exists(skyscraper_dir):
                print(f"[DEBUG] Searching Skyscraper directory: {skyscraper_dir}")
                # Get advertiser from ad
                advertiser = ad.get('advertisers', ['unknown'])[0] if ad.get('advertisers') else 'unknown'
                advertiser_slug = self.to_slug(advertiser)
                
                # List all files and find matches
                import glob as glob_module
                pattern = os.path.join(skyscraper_dir, f"*__{advertiser_slug}__skyscraper__*.png")
                matches = glob_module.glob(pattern)
                print(f"[DEBUG] Pattern: {pattern}")
                print(f"[DEBUG] All matches: {len(matches)}")
                
                # Filter by timestamp if available
                if run_timestamp and matches:
                    date_part = run_timestamp.split('_')[0]
                    time_part = run_timestamp.split('_')[1] if '_' in run_timestamp else ''
                    # Convert HH-MM-SS to HH-MM.SS (replace last dash with dot)
                    time_formatted = time_part.rsplit('-', 1)[0] + '.' + time_part.rsplit('-', 1)[1] if time_part and '-' in time_part else time_part
                    
                    timestamp_matches = [m for m in matches if f"D{date_part}_T{time_formatted}" in m]
                    if timestamp_matches:
                        matches = timestamp_matches
                        print(f"[DEBUG] Filtered by timestamp: {len(matches)}")
                    
                    # Further filter by position if available
                    ad_position = ad.get('position')
                    if ad_position and matches:
                        position_matches = [m for m in matches if m.endswith(f"_{ad_position}.png")]
                        if position_matches:
                            matches = position_matches
                            print(f"[DEBUG] Filtered by position {ad_position}: {len(matches)}")
                
                if matches:
                    matches.sort(key=os.path.getmtime, reverse=True)
                    print(f"[DEBUG] Using: {matches[0]}")
                    return matches[0]
        
        print(f"[DEBUG] No image found")
        return None
    
    def show_current_ad(self):
        """Display the current ad for review"""
        if not self.unknown_ads or self.current_index >= len(self.unknown_ads):
            messagebox.showinfo("Complete", "All unknown brands have been reviewed!")
            self.root.quit()
            return
        
        ad_data = self.unknown_ads[self.current_index]
        ad = ad_data['ad']
        
        # Update progress - show unique brands count
        unique_brands = len(set(ad['current_brand'] for ad in self.unknown_ads))
        self.progress_label.config(
            text=f"Ad {self.current_index + 1} of {len(self.unknown_ads)} ({unique_brands} unique brands)"
        )
        
        # Update current brand(s) - show all if co-branded
        advertisers = ad.get('advertisers', ['unknown'])
        if len(advertisers) > 1:
            brand_text = ", ".join(advertisers)
        else:
            brand_text = ad_data['current_brand']
        self.current_brand_label.config(text=brand_text)
        
        # Display brand logo if available (use first brand)
        if advertisers and advertisers[0] != 'unknown':
            self.display_brand_logo(advertisers[0])
        else:
            self.brand_logo_label.config(image='')
        
        # Clear and update details
        self.details_text.delete('1.0', tk.END)
        details = self.format_ad_details(ad)
        self.details_text.insert('1.0', details)
        
        # Display actual image path that was found
        if ad_data['image_path']:
            # Show just the filename for readability
            filename = os.path.basename(ad_data['image_path'])
            
            # Check if this was a guessed path (no path in JSON)
            ad_type = ad.get('type')
            has_stored_path = False
            if ad_type == 'CuratedCarousel' and 'carousel_image_path' in ad:
                has_stored_path = True
            elif ad_type == 'TOA' and 'toa_image_path' in ad:
                has_stored_path = True
            elif ad_type == 'Skyscraper' and 'skyscraper_image_path' in ad:
                has_stored_path = True
            
            if not has_stored_path:
                self.image_path_label.config(text=f"⚠️ Image: {filename} (may not match - path not in JSON)", foreground="orange")
            else:
                self.image_path_label.config(text=f"Image: {filename}", foreground="blue")
        else:
            self.image_path_label.config(text="Image: Not found")
        
        # Load and display image
        if ad_data['image_path'] and os.path.exists(ad_data['image_path']):
            self.display_image(ad_data['image_path'])
        else:
            self.image_label.config(text="No image available", image='')
            if ad_data['image_path']:
                print(f"[WARNING] Image path exists in data but file not found: {ad_data['image_path']}")
        
        # Generate suggestions
        self.show_suggestions(ad)
        
        # Populate brand entry fields with existing brands
        self.set_brand_entries(advertisers)
        
        # Focus first entry
        self.brand_entries[0].focus()
    
    def format_ad_details(self, ad):
        """Format ad details for display"""
        # Get current ad data to access JSON file path
        ad_data = self.unknown_ads[self.current_index]
        json_file = ad_data.get('json_file', 'Unknown')
        
        # Extract client and search term from JSON path
        # e.g., output/kroger/MilkPEP/runs/run_results_protein_drinks_2025-10-24_16-19-00.json
        client = 'Unknown'
        search_term = 'Unknown'
        if json_file:
            parts = json_file.split(os.sep)
            if len(parts) >= 3:
                client = parts[-3]  # MilkPEP
            filename = os.path.basename(json_file)
            # Extract search term from filename: run_results_<term>_<timestamp>.json
            if filename.startswith('run_results_'):
                term_part = filename.replace('run_results_', '').rsplit('_', 4)[0]
                search_term = term_part.replace('_', ' ')
        
        details = []
        details.append(f"Client: {client}")
        details.append(f"Search Term: {search_term}")
        details.append(f"JSON: {os.path.basename(json_file) if json_file else 'Unknown'}")
        details.append("")
        details.append(f"Type: {ad.get('type', 'Unknown')}")
        details.append(f"Position: {ad.get('position', 'N/A')}")
        details.append(f"Current Brand: {ad.get('advertisers', ['unknown'])[0]}")
        details.append("")
        
        if ad.get('message'):
            details.append(f"Message: {ad.get('message')}")
        
        if ad.get('header'):
            details.append(f"Header: {ad.get('header')}")
        
        if ad.get('href'):
            details.append(f"URL: {ad.get('href')}")
        
        if ad.get('products'):
            details.append(f"\nProducts ({len(ad['products'])}):")
            for i, product in enumerate(ad['products'][:5], 1):
                title = product.get('title', 'No title')
                details.append(f"  {i}. {title}")
            if len(ad['products']) > 5:
                details.append(f"  ... and {len(ad['products']) - 5} more")
        
        return "\n".join(details)
    
    def display_image(self, image_path):
        """Load and display the ad image"""
        try:
            img = Image.open(image_path)
            
            # Resize to fit display area (max 600x600)
            img.thumbnail((600, 600), Image.Resampling.LANCZOS)
            
            photo = ImageTk.PhotoImage(img)
            self.image_label.config(image=photo, text='')
            self.image_label.image = photo  # Keep a reference
        except Exception as e:
            self.image_label.config(text=f"Error loading image:\n{str(e)}", image='')
    
    def display_brand_logo(self, brand_name):
        """Display brand logo thumbnail if available"""
        if not self.logo_db:
            return
        
        try:
            logo_info = self.logo_db.get_brand_logo(brand_name)
            if logo_info and 'logo_file' in logo_info:
                logo_path = logo_info['logo_file']
                
                # Check if file exists (relative to project root or absolute)
                if not os.path.isabs(logo_path):
                    logo_path = os.path.join(os.getcwd(), 'output', logo_path)
                
                if os.path.exists(logo_path):
                    img = Image.open(logo_path)
                    
                    # Resize to small thumbnail (40x40)
                    img.thumbnail((40, 40), Image.Resampling.LANCZOS)
                    
                    photo = ImageTk.PhotoImage(img)
                    self.brand_logo_label.config(image=photo)
                    self.brand_logo_label.image = photo  # Keep reference
                    print(f"[LOGO] Displayed logo for {brand_name}")
                else:
                    self.brand_logo_label.config(image='')
                    print(f"[LOGO] Logo file not found: {logo_path}")
            else:
                self.brand_logo_label.config(image='')
        except Exception as e:
            self.brand_logo_label.config(image='')
            print(f"[LOGO] Error displaying logo: {e}")
    
    def show_suggestions(self, ad):
        """Generate and show brand suggestions"""
        # Clear existing suggestions
        for widget in self.suggestions_frame.winfo_children():
            widget.destroy()
        
        suggestions = set()
        
        # Extract brand from TOA campaign codes (e.g., TOABoostAugDec2025 -> Boost)
        current_brand = ad.get('advertisers', [''])[0] if ad.get('advertisers') else ''
        if current_brand:
            # Pattern: TOA + BrandName + Month + Month + Year
            toa_match = re.match(r'^TOA([A-Z][a-z]+)', current_brand, re.IGNORECASE)
            if toa_match:
                extracted_brand = toa_match.group(1)
                suggestions.add(extracted_brand)
                print(f"[SUGGESTION] Extracted '{extracted_brand}' from TOA code '{current_brand}'")
        
        # Extract from URL
        href = ad.get('href', '')
        if href:
            url_brands = re.findall(r'/([a-z][a-z-]+)/', href.lower())
            for brand in url_brands:
                if len(brand) > 3 and brand not in ['search', 'product', 'kroger']:
                    suggestions.add(brand.replace('-', ' ').title())
        
        # Extract from product titles
        for product in ad.get('products', [])[:3]:
            title = product.get('title', '')
            # Get first 2-3 capitalized words
            words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?', title)
            if words:
                suggestions.add(words[0])
        
        # Extract from message/header
        for field in ['message', 'header']:
            text = ad.get(field, '')
            if text:
                words = re.findall(r'\b[A-Z][A-Za-z&\'\-]+(?:\s+[A-Z][A-Za-z&\'\-]+)?', text)
                for word in words[:2]:
                    if len(word) > 3:
                        suggestions.add(word)
        
        # Display suggestions as buttons
        for i, suggestion in enumerate(sorted(suggestions)[:6]):
            btn = ttk.Button(
                self.suggestions_frame,
                text=suggestion,
                command=lambda s=suggestion: self.use_suggestion(s)
            )
            btn.grid(row=i//3, column=i%3, padx=5, pady=5, sticky=tk.EW)
        
        for i in range(3):
            self.suggestions_frame.columnconfigure(i, weight=1)
    
    def use_suggestion(self, suggestion):
        """Use a suggested brand name"""
        self.brand_entries[0].delete(0, tk.END)
        self.brand_entries[0].insert(0, suggestion)
        self.brand_entries[0].focus()
    
    def save_correction(self):
        """Save the corrected brand name(s) - applies to all similar ads"""
        # Just call apply_to_all_similar with auto_confirm=True
        self.apply_to_all_similar(auto_confirm=True)
    
    def update_json(self, ad_data, corrected_brands):
        """Update the JSON file with corrected brand(s)"""
        json_file = ad_data['json_file']
        
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
        except Exception as e:
            raise Exception(f"Failed to read JSON: {e}")
        
        # Find and update the ad by comparing ad type and position
        target_ad = ad_data['ad']
        
        try:
            target_type = target_ad.get('type')
            target_position = target_ad.get('position')
        except AttributeError as e:
            raise Exception(f"target_ad is not a dict: {type(target_ad)}, value: {target_ad}")
        
        updated = False
        results = data.get('results', [])
        
        if not isinstance(results, list):
            raise Exception(f"'results' is not a list: {type(results)}")
        
        for result_idx, result in enumerate(results):
            if not isinstance(result, dict):
                raise Exception(f"result[{result_idx}] is not a dict: {type(result)}")
            
            ads = result.get('ads', [])
            
            if not isinstance(ads, list):
                raise Exception(f"'ads' in result[{result_idx}] is not a list: {type(ads)}")
            
            for i, ad in enumerate(ads):
                if not isinstance(ad, dict):
                    raise Exception(f"ad[{i}] is not a dict: {type(ad)}")
                
                # Match by type and position, or by exact match
                if (ad.get('type') == target_type and ad.get('position') == target_position) or ad == target_ad:
                    ad['advertisers'] = corrected_brands
                    
                    # Update image path even if it doesn't literally contain the old brand slug
                    for path_key in ['carousel_image_path', 'toa_image_path', 'skyscraper_image_path']:
                        if path_key in ad:
                            old_path = ad[path_key]
                            new_slug = self.to_slug(corrected_brands[0])
                            # Try direct replacement using old_slug first
                            old_slug = self.to_slug(ad_data['current_brand'])
                            new_path = old_path.replace(f'__{old_slug}__', f'__{new_slug}__')
                            if new_path == old_path:
                                # Generic replacement: swap the second segment of the basename
                                dname, bname = os.path.split(old_path)
                                parts = bname.split('__')
                                if len(parts) >= 2:
                                    parts[1] = new_slug
                                    bname_new = '__'.join(parts)
                                    new_path = os.path.join(dname, bname_new)
                            ad[path_key] = new_path
                    
                    updated = True
                    break
            if updated:
                break
        
        if not updated:
            raise Exception(f"Could not find ad in JSON (type={target_type}, position={target_position})")
        
        # Save updated JSON
        with open(json_file, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def rename_image_file(self, ad_data, old_brand, new_brand):
        """Rename the image file to match corrected brand, regardless of previous slug"""
        old_path = ad_data['image_path']
        if not old_path:
            print(f"[WARN] No image path in ad_data, skipping rename")
            return
        if not os.path.exists(old_path):
            print(f"[WARN] Image file doesn't exist: {old_path}")
            return
        # Build new filename by replacing the brand slug segment (second segment)
        new_slug = self.to_slug(new_brand)
        dname, bname = os.path.split(old_path)
        parts = bname.split('__')
        if len(parts) >= 2:
            parts[1] = new_slug
            bname_new = '__'.join(parts)
            new_path = os.path.join(dname, bname_new)
        else:
            # Fallback to simple replace using old brand slug
            new_path = old_path.replace(f"__{self.to_slug(old_brand)}__", f"__{new_slug}__")
        if old_path != new_path:
            try:
                shutil.move(old_path, new_path)
                ad_data['image_path'] = new_path
                print(f"[FILE] Renamed image file:")
                print(f"       {os.path.basename(old_path)}")
                print(f"    -> {os.path.basename(new_path)}")
            except Exception as e:
                print(f"[ERROR] Failed to rename image file: {e}")
                print(f"        Old: {old_path}")
                print(f"        New: {new_path}")
        else:
            print(f"[INFO] Image filename already correct (no rename needed)")
    
    def sync_logo_brands_to_lexicon(self):
        """Sync brands from logo database into lexicon"""
        if not self.logo_db:
            return
        
        try:
            # Get all brands from logo database
            logo_brands = self.logo_db.list_all_brands()
            
            # Load lexicon
            with open(self.lexicon_path, 'r') as f:
                lexicon_brands = json.load(f)
            
            # Create a set of existing brand names (lowercase for comparison)
            existing_names = {brand['name'].lower() for brand in lexicon_brands}
            
            # Add missing brands from logo database (skip "unknown")
            added_count = 0
            for logo_brand in logo_brands:
                # NEVER add "unknown" to lexicon
                if logo_brand.lower() == 'unknown':
                    continue
                
                if logo_brand.lower() not in existing_names:
                    # Add to lexicon
                    lexicon_brands.append({
                        'name': logo_brand,
                        'synonyms': []
                    })
                    added_count += 1
                    print(f"[SYNC] Added '{logo_brand}' from logo database to lexicon")
            
            if added_count > 0:
                # Sort and save
                lexicon_brands_sorted = sorted(lexicon_brands, key=lambda x: x['name'].lower())
                with open(self.lexicon_path, 'w') as f:
                    json.dump(lexicon_brands_sorted, f, indent=2, ensure_ascii=False)
                print(f"[SYNC] Added {added_count} brands from logo database to lexicon")
                
                # Reload lexicon cache
                self.lexicon_brands = lexicon_brands_sorted
        except Exception as e:
            print(f"[WARN] Failed to sync logo brands to lexicon: {e}")
    
    def update_lexicon(self, corrected_brand, old_brand):
        """Add corrected brand to lexicon and add old brand as alias"""
        # NEVER add "unknown" to lexicon
        if corrected_brand.lower() == 'unknown':
            print(f"[LEXICON] Skipping - 'unknown' cannot be added to lexicon")
            return
        
        # Load lexicon (it's a list of {name, synonyms} objects)
        with open(self.lexicon_path, 'r') as f:
            brands = json.load(f)
        
        # Check if brand already exists
        existing_brand = None
        for brand in brands:
            if brand['name'].lower() == corrected_brand.lower():
                existing_brand = brand
                break
        
        if existing_brand:
            # Add old brand as synonym if it's not already there and not "unknown"
            if old_brand.lower() != 'unknown' and old_brand not in existing_brand['synonyms']:
                existing_brand['synonyms'].append(old_brand)
                print(f"[LEXICON] Added '{old_brand}' as synonym for '{existing_brand['name']}'")
        else:
            # Add new brand
            new_brand = {
                'name': corrected_brand,
                'synonyms': [old_brand] if old_brand.lower() != 'unknown' else []
            }
            brands.append(new_brand)
            print(f"[LEXICON] Added new brand '{corrected_brand}' with synonym '{old_brand}'")
        
        # Sort brands alphabetically by name (case-insensitive)
        brands_sorted = sorted(brands, key=lambda x: x['name'].lower())
        
        # Save lexicon (keep it as a list)
        with open(self.lexicon_path, 'w') as f:
            json.dump(brands_sorted, f, indent=2, ensure_ascii=False)
        
        # Reload lexicon cache
        self.lexicon_brands = brands_sorted
    
    def apply_to_all_similar(self, auto_confirm=False):
        """Apply the corrected brand(s) to all similar ads with the same message/header/URL"""
        corrected_brands = self.get_all_brands()
        
        if not corrected_brands:
            messagebox.showwarning("Missing Brand", "Please enter at least one brand name")
            return
        
        ad_data = self.unknown_ads[self.current_index]
        current_ad = ad_data['ad']
        original_uncertain_brand = ad_data['current_brand']  # Save for lexicon update
        
        # Get identifying features from current ad
        current_message = current_ad.get('message', '').strip()
        current_header = current_ad.get('header', '').strip()
        current_url = current_ad.get('href', '').strip()
        
        # Find all ads with matching content
        similar_ads = []
        for i, ad in enumerate(self.unknown_ads):
            ad_obj = ad['ad']
            
            # Match by message, header, or URL
            matches = False
            if current_message and ad_obj.get('message', '').strip() == current_message:
                matches = True
            elif current_header and ad_obj.get('header', '').strip() == current_header:
                matches = True
            elif current_url and ad_obj.get('href', '').strip() == current_url:
                matches = True
            
            if matches:
                similar_ads.append((i, ad))
        
        # Confirm with user (unless auto_confirm is True)
        if not auto_confirm:
            # Show what we're matching on
            match_criteria = []
            if current_message:
                match_criteria.append(f"Message: {current_message[:50]}...")
            if current_header:
                match_criteria.append(f"Header: {current_header[:50]}...")
            if current_url:
                match_criteria.append(f"URL: {current_url[:50]}...")
            
            criteria_text = "\n".join(match_criteria) if match_criteria else "No identifying content"
            
            count = len(similar_ads)
            brand_text = ", ".join(corrected_brands) if len(corrected_brands) > 1 else corrected_brands[0]
            response = messagebox.askyesno(
                "Apply to All Similar",
                f"Found {count} ad(s) matching:\n{criteria_text}\n\n"
                f"Apply '{brand_text}' to all of them?"
            )
            
            if not response:
                return
        
        # Apply to all
        success_count = 0
        error_count = 0
        
        for idx, ad in similar_ads:
            try:
                # Get this ad's current brand (before updating)
                old_brand_for_this_ad = ad['current_brand']
                
                # Update JSON with all brands
                self.update_json(ad, corrected_brands)
                
                # Rename image file using this ad's old brand (use first brand for filename)
                if ad['image_path']:
                    self.rename_image_file(ad, old_brand_for_this_ad, corrected_brands[0])
                
                success_count += 1
            except Exception as e:
                print(f"[ERROR] Failed to update ad {idx}: {e}")
                error_count += 1
        
        # Update lexicon for each brand with the original uncertain brand
        try:
            for brand in corrected_brands:
                self.update_lexicon(brand, original_uncertain_brand)
        except Exception as e:
            print(f"[ERROR] Failed to update lexicon: {e}")
        
        # Remove all ads that had the original uncertain brand BEFORE updating current_brand
        # (otherwise the filter won't work)
        old_count = len(self.unknown_ads)
        self.unknown_ads = [ad for ad in self.unknown_ads if ad['current_brand'] != original_uncertain_brand]
        removed_count = old_count - len(self.unknown_ads)
        if removed_count > 1:
            print(f"[INFO] Filtered out {removed_count} ads with brand '{original_uncertain_brand}' from review list")
        
        # Adjust index if needed - stay at same index to show next ad in list
        if self.current_index >= len(self.unknown_ads):
            self.current_index = max(0, len(self.unknown_ads) - 1)
        
        # Show success message
        brand_text = ", ".join(corrected_brands) if len(corrected_brands) > 1 else corrected_brands[0]
        messagebox.showinfo(
            "Success",
            f"Updated brand to: {brand_text}\n"
            f"({success_count} similar ads updated, {error_count} errors)\n"
            f"({removed_count} ads removed from review queue)"
        )
        
        # Show the ad at current index (don't increment - the list shifted)
        if self.unknown_ads:
            self.show_current_ad()
        else:
            messagebox.showinfo("Complete", "All unknown brands have been reviewed!")
            self.root.quit()
    
    def mark_as_kroger(self):
        """Mark the current ad as a Kroger house ad"""
        # Clear all co-brand fields
        while len(self.brand_entries) > 1:
            self.remove_cobrand_field(1)
        
        # Set first field to Kroger
        self.brand_entries[0].delete(0, tk.END)
        self.brand_entries[0].insert(0, "Kroger")
        self.save_correction()
    
    def to_slug(self, text):
        """Convert text to slug format"""
        return text.lower().replace(' ', '_').replace("'", '').replace('&', 'and')
    
    def next_ad(self):
        """Move to next ad, skipping any Kroger house ads"""
        self.current_index += 1
        # Skip any Kroger ads
        while self.current_index < len(self.unknown_ads):
            if self.unknown_ads[self.current_index]['current_brand'].lower() != 'kroger':
                break
            self.current_index += 1
        self.show_current_ad()
    
    def previous_ad(self):
        """Move to previous ad, skipping any Kroger house ads"""
        if self.current_index > 0:
            self.current_index -= 1
            # Skip any Kroger ads
            while self.current_index > 0:
                if self.unknown_ads[self.current_index]['current_brand'].lower() != 'kroger':
                    break
                self.current_index -= 1
            self.show_current_ad()

if __name__ == "__main__":
    root = tk.Tk()
    app = BrandReviewTool(root)
    root.mainloop()
