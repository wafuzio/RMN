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
from tkinter import ttk, messagebox, font, scrolledtext
from PIL import Image, ImageTk
import json
import os
import glob
import shutil
import re
from pathlib import Path
from utils.lexicon_utils import save_lexicon

# Import image hashing for visual similarity matching
try:
    import imagehash
    IMAGEHASH_AVAILABLE = True
except ImportError:
    IMAGEHASH_AVAILABLE = False
    print("[WARN] imagehash not available - install with: pip install imagehash")

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
        # Track delete-armed state for double-click delete behavior
        self.delete_armed_index = None
        self.lexicon_path = "config/brands.json"
        self.blacklist_path = "config/brand_blacklist.json"
        self.lexicon_brands = []  # Cache lexicon in memory
        self.blacklisted_brands = set()  # Brands to never show again
        # Image hash to brand mapping - persists across corrections for batch matching
        self.hash_to_brand = {}  # {image_hash: [brand_names]}
        
        # Load blacklist
        self.load_blacklist()
        
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
        
        # Load unknown brands in background thread to prevent UI freeze
        self.loading_complete = False
        import threading
        
        def load_in_background():
            self.load_unknown_brands()
            self.loading_complete = True
            # Schedule UI update on main thread
            self.root.after(0, self.on_loading_complete)
        
        thread = threading.Thread(target=load_in_background, daemon=True)
        thread.start()
        
        # Update progress label periodically during loading
        self.update_loading_progress()
    
    def update_loading_progress(self):
        """Update the loading progress in the UI"""
        if not self.loading_complete:
            count = len(self.unknown_ads)
            self.progress_label.config(text=f"Loading... ({count} ads found)")
            self.root.after(500, self.update_loading_progress)
    
    def on_loading_complete(self):
        """Called when background loading is complete"""
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
        
        # Image path entry (selectable/copyable, clickable to open in Finder)
        self.image_path_var = tk.StringVar()
        self.image_path_label = tk.Entry(
            left_frame,
            textvariable=self.image_path_var,
            font=("Arial", 11),
            fg="blue",
            cursor="hand2",
            readonlybackground="white",
            relief="flat",
            state="readonly"
        )
        self.image_path_label.pack(pady=(10, 5), fill="x")
        self.image_path_label.bind("<Button-1>", self.open_image_in_finder)
        self.current_image_path = None
        
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
        
        ttk.Button(button_frame, text="1 Previous", command=self.previous_ad).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Skip", command=self.next_ad).pack(side=tk.LEFT, padx=5)
        # Store delete button so we can change its label when armed
        self.delete_button = ttk.Button(button_frame, text="Delete Ad", command=self.delete_current_ad)
        self.delete_button.pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Save All Similar & Next 1", command=self.save_correction, style="Accent.TButton").pack(side=tk.LEFT, padx=5)
        # Dynamic house ad button - will show "Mark as Kroger House Ad" or "Mark as Walmart House Ad"
        self.house_ad_button = ttk.Button(button_frame, text="Mark as House Ad", command=self.mark_as_house_ad)
        self.house_ad_button.pack(side=tk.LEFT, padx=5)
        
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
    
    def load_blacklist(self):
        """Load blacklisted brands that should never be shown again"""
        try:
            if os.path.exists(self.blacklist_path):
                with open(self.blacklist_path, 'r') as f:
                    data = json.load(f)
                # Normalize to lowercase for case-insensitive matching
                self.blacklisted_brands = set(b.lower() for b in data.get('brands', []))
                print(f"[INFO] Loaded {len(self.blacklisted_brands)} blacklisted brands")
            else:
                self.blacklisted_brands = set()
        except Exception as e:
            print(f"[WARN] Failed to load blacklist: {e}")
            self.blacklisted_brands = set()
    
    def save_blacklist(self):
        """Save blacklisted brands to disk"""
        try:
            os.makedirs(os.path.dirname(self.blacklist_path), exist_ok=True)
            with open(self.blacklist_path, 'w') as f:
                json.dump({'brands': sorted(list(self.blacklisted_brands))}, f, indent=2)
        except Exception as e:
            print(f"[WARN] Failed to save blacklist: {e}")
    
    def add_to_blacklist(self, brand_name):
        """Add a brand name to the blacklist"""
        if brand_name and brand_name.strip():
            normalized = brand_name.strip().lower()
            self.blacklisted_brands.add(normalized)
            self.save_blacklist()
            print(f"[BLACKLIST] Added '{brand_name}' to blacklist")
    
    def is_blacklisted(self, brand_name):
        """Check if a brand name is blacklisted"""
        if not brand_name:
            return False
        return brand_name.strip().lower() in self.blacklisted_brands
    
    def is_brand_in_lexicon(self, brand):
        """Check if a brand exists in the lexicon (uses cached data)"""
        from utils.brand_utils import normalize_brand_for_matching
        
        if not brand:
            return False
        
        normalized = normalize_brand_for_matching(brand)
        
        # Check if brand name matches (case-insensitive, punctuation-insensitive)
        for lex_brand in self.lexicon_brands:
            if normalize_brand_for_matching(lex_brand['name']) == normalized:
                return True
            # Also check synonyms
            if any(normalize_brand_for_matching(syn) == normalized for syn in lex_brand.get('synonyms', [])):
                return True
        
        return False
    
    def get_canonical_brand_name(self, brand):
        """Return the canonical display name from the lexicon, or None if not found."""
        from utils.brand_utils import normalize_brand_for_matching
        
        if not brand:
            return None
        
        normalized = normalize_brand_for_matching(brand)
        
        for lex_brand in self.lexicon_brands:
            if normalize_brand_for_matching(lex_brand['name']) == normalized:
                return lex_brand['name']
            for syn in lex_brand.get('synonyms', []):
                if normalize_brand_for_matching(syn) == normalized:
                    return lex_brand['name']
        
        return None
    
    def match_message_to_lexicon(self, message):
        """Check if message text matches a known brand's message synonym.
        
        This is primarily used to identify KROGER HOUSE ADS (retailer marketing materials)
        by their exact, repeating message text. These are NOT real brand ads and should be
        auto-skipped from the review tool.
        
        Note: This is different from brand name extraction (canonicalize function).
        Message matching is for identifying house ads to exclude, not for extracting brands.
        
        Returns the brand name if matched, None otherwise.
        """
        if not message:
            return None
        
        message_clean = message.strip()
        
        # Check all brands in lexicon for message synonyms
        for lex_brand in self.lexicon_brands:
            for synonym in lex_brand.get('synonyms', []):
                # Check for MSG: prefix (indicates message-based synonym)
                if synonym.startswith('MSG:'):
                    synonym_text = synonym[4:].strip()  # Remove "MSG:" prefix
                    # Exact match (case-insensitive) - these messages repeat verbatim
                    if message_clean.lower() == synonym_text.lower():
                        return lex_brand['name']
        
        return None
    
    def load_unknown_brands(self):
        """Load all ads with unknown or uncertain brands"""
        print("Scanning for unknown brands...")
        
        # Scan all retailer JSON files (Kroger, Walmart, Instacart, Amazon, Target, etc.)
        json_files = []
        
        # Kroger/Target: output/retailer/client/runs/*.json
        for retailer in ['kroger', 'target']:
            pattern = f'output/{retailer}/*/runs/*.json'
            retailer_files = glob.glob(pattern)
            # Filter out malformed paths where "runs" is treated as a client
            retailer_files = [f for f in retailer_files if '/runs/runs/' not in f]
            json_files.extend(retailer_files)
            if retailer_files:
                print(f"  Found {len(retailer_files)} {retailer} files")
        
        # Instacart: output/instacart/client/runs/TIMESTAMP/run_results_*.json
        instacart_pattern = 'output/instacart/*/runs/*/run_results_*.json'
        instacart_files = glob.glob(instacart_pattern)
        json_files.extend(instacart_files)
        if instacart_files:
            print(f"  Found {len(instacart_files)} instacart files")
        
        # Amazon: output/amazon/client/runs/*.json OR output/amazon/client/runs/TIMESTAMP/*.json
        amazon_pattern1 = 'output/amazon/*/runs/*.json'
        amazon_pattern2 = 'output/amazon/*/runs/*/*.json'
        amazon_files = glob.glob(amazon_pattern1) + glob.glob(amazon_pattern2)
        amazon_files = [f for f in amazon_files if '/runs/runs/' not in f]
        amazon_files = list(set(amazon_files))
        json_files.extend(amazon_files)
        if amazon_files:
            print(f"  Found {len(amazon_files)} amazon files")
        
        # Walmart: output/walmart/client/TIMESTAMP/run_results_*.json (new structure)
        #          output/walmart/client/runs/run_results_*.json (legacy structure)
        walmart_pattern1 = 'output/walmart/*/*/run_results_*.json'
        walmart_pattern2 = 'output/walmart/*/runs/run_results_*.json'
        walmart_files = glob.glob(walmart_pattern1) + glob.glob(walmart_pattern2)
        # Remove duplicates
        walmart_files = list(set(walmart_files))
        json_files.extend(walmart_files)
        if walmart_files:
            print(f"  Found {len(walmart_files)} walmart files")
        
        print(f"Total: {len(json_files)} JSON files to scan")
        
        for json_file in json_files:
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                
                # Handle both canonical and legacy structures
                ads_to_check = []
                
                # Canonical structure takes priority: {"ads": [...]}
                if 'ads' in data and isinstance(data['ads'], list):
                    ads_to_check = data['ads']
                # Legacy structure: {"results": [{"ads": [...]}]}
                elif 'results' in data:
                    for result in data.get('results', []):
                        ads_to_check.extend(result.get('ads', []))
                
                for ad in ads_to_check:
                        # Skip Kroji house ads entirely
                        if self.is_kroji_house_ad(ad):
                            continue
                        
                        # Skip "Main" ad types (full-page screengrabs, intentionally brandless)
                        if ad.get('type') == 'main':
                            continue
                        
                        # Skip Product_Listing ads with no brand/advertisers - these are organic product
                        # search results, not brand ads that can be corrected
                        if ad.get('type') == 'Product_Listing':
                            if not ad.get('brand') and not ad.get('advertisers'):
                                continue
                        
                        # Skip Amazon house ad modules (not brand-specific ads)
                        ad_type_lower = (ad.get('type') or '').lower()
                        ad_subtype_lower = (ad.get('subtype') or '').lower()
                        message_lower = (ad.get('message') or '').lower()
                        title_lower = (ad.get('title') or '').lower()
                        skip_patterns = [
                            'frequently shopped brands',
                            'seen on social media',
                            'customers frequently viewed',
                            'frequently bought together',
                            'customers who viewed this',
                            'customers also bought',
                            'inspired by your browsing',
                            'related to items you',
                            'picks from amazon influencers',
                            'trending now',
                            'other items to consider',
                        ]
                        if any(pattern in message_lower or pattern in title_lower or 
                               pattern in ad_type_lower or pattern in ad_subtype_lower 
                               for pattern in skip_patterns):
                            continue
                        
                        # Check if message text matches a known brand synonym (e.g., Kroger house ads)
                        message = ad.get('message', '')
                        if message:
                            matched_brand = self.match_message_to_lexicon(message)
                            if matched_brand:
                                print(f"✓ Auto-skipping ad with known message: '{message[:60]}...' -> {matched_brand}")
                                continue
                            
                            # ALSO check if this exact message is blacklisted (already reviewed)
                            # Blacklist stores messages with "MSG:" prefix
                            message_key = f"MSG:{message.strip()}"
                            if self.is_blacklisted(message_key):
                                print(f"✓ Skipping blacklisted message: '{message[:60]}...'")
                                continue
                        
                        advertisers = ad.get('advertisers', [])
                        
                        # Check if unknown or uncertain in JSON
                        is_unknown_in_json = (
                            not advertisers or
                            advertisers == ['unknown'] or
                            advertisers == ['Unknown'] or
                            any(adv and adv.lower() == 'unknown' for adv in advertisers) or
                            any(self.is_uncertain_brand(adv) for adv in advertisers)
                        )
                        
                        # Find associated image file first
                        image_path = self.find_ad_image(ad, json_file)
                        
                        # CRITICAL: Also check if image filename contains "unknown"
                        # This catches cases where JSON has a brand but screenshot failed to match it
                        is_unknown_in_filename = False
                        
                        # STRICT MODE: Verify that the found image matches what JSON expects
                        # This prevents showing wrong images due to fuzzy matching
                        if image_path:
                            expected_path = self.expected_image_path_from_json(ad, json_file)
                            if expected_path and os.path.basename(image_path) != os.path.basename(expected_path):
                                # The found image has a different filename than what JSON specifies
                                # This is a MISMATCH - do NOT show the wrong image
                                print(f"[STRICT] Rejecting mismatched image")
                                print(f"[STRICT]   Expected: {os.path.basename(expected_path)}")
                                print(f"[STRICT]   Found: {os.path.basename(image_path)}")
                                image_path = None  # Show "no image" rather than wrong image
                        
                        # NOTE: Fuzzy fallback search REMOVED to prevent mismatches
                        # If JSON specifies a path but file doesn't exist, we show "no image"
                        # This is better than showing the WRONG image which causes confusion
                        
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
                                        # Before flagging, check if both resolve to the same canonical brand
                                        file_canonical = self.get_canonical_brand_name(brand_slug_in_file)
                                        adv_canonicals = [self.get_canonical_brand_name(a) for a in (advertisers or [])]
                                        if file_canonical and file_canonical in adv_canonicals:
                                            print(f"[OK] Filename slug '{brand_slug_in_file}' and advertisers resolve to same brand: {file_canonical}")
                                        else:
                                            is_unknown_in_filename = True
                                            print(f"[WARN] Filename brand slug '{brand_slug_in_file}' ≠ advertisers {adv_slugs}")
                        
                        # FIX #4: Flag broken JSON references - JSON has a path but no file exists after all reconciliation
                        if not image_path:
                            # Check if JSON has any image path field
                            has_json_path = (ad.get('image_path') or 
                                           ad.get('toa_image_path') or 
                                           ad.get('skyscraper_image_path') or 
                                           ad.get('carousel_image_path'))
                            if has_json_path:
                                print(f"[WARN] JSON has an image path but no matching file exists after reconciliation")
                                print(f"[WARN]   Ad type: {ad.get('type')}, Advertisers: {advertisers}")
                                is_unknown_in_filename = True
                        
                        # Flag as unknown if EITHER condition is true
                        if is_unknown_in_json or is_unknown_in_filename:
                            current_brand = advertisers[0] if advertisers else 'unknown'
                            
                            # Skip if brand is blacklisted
                            if self.is_blacklisted(current_brand):
                                print(f"✓ Skipping blacklisted brand: '{current_brand}'")
                                continue
                            
                            # Skip if brand is already verified in lexicon (even if image is missing)
                            # These don't need manual review - we already know the brand is correct
                            if current_brand and current_brand.lower() != 'unknown':
                                if self.is_brand_in_lexicon(current_brand):
                                    print(f"✓ Skipping verified brand: '{current_brand}' (in lexicon)")
                                    continue
                            
                            print(f"[FLAGGED] Ad type={ad.get('type')}, advertisers={advertisers}")
                            print(f"[FLAGGED]   is_unknown_in_json={is_unknown_in_json}, is_unknown_in_filename={is_unknown_in_filename}")
                            print(f"[FLAGGED]   image_path={image_path}")
                            
                            # Compute image hash for visual similarity matching
                            img_hash = None
                            if IMAGEHASH_AVAILABLE and image_path and os.path.exists(image_path):
                                try:
                                    img = Image.open(image_path)
                                    img_hash = str(imagehash.phash(img))
                                except Exception as e:
                                    print(f"[WARN] Failed to compute image hash: {e}")
                            
                            self.unknown_ads.append({
                                'json_file': json_file,
                                'ad': ad,
                                'image_path': image_path,
                                'current_brand': current_brand,
                                'image_hash': img_hash
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
    
    def is_kroji_house_ad(self, ad):
        """Check if ad is a Kroger house ad (Kroji mascot)"""
        # Check message field for "Kroji"
        message = ad.get('message') or ''
        if 'kroji' in message.lower():
            return True
        
        # Check header field
        header = ad.get('header') or ''
        if 'kroji' in header.lower():
            return True
        
        # Check advertisers
        advertisers = ad.get('advertisers', [])
        if any('kroji' in str(adv).lower() for adv in advertisers):
            return True
        
        return False
    
    def expected_image_path_from_json(self, ad, json_file):
        """Return the full path that the JSON points to, even if it doesn't exist."""
        # Determine retailer and base_dir (same logic as find_ad_image)
        try:
            path_parts = Path(json_file).parts
            output_idx = path_parts.index('output')
            retailer = path_parts[output_idx + 1]
        except Exception:
            retailer = 'kroger'

        runs_dir = os.path.dirname(json_file)
        base_dir = os.path.dirname(runs_dir)
        if retailer == 'walmart' and re.match(r'\d{14}$', os.path.basename(runs_dir)):
            base_dir = os.path.dirname(base_dir)

        # Map ad types to their JSON path fields, like in find_ad_image
        if retailer == 'kroger':
            type_to_path_field = {
                'TOA': 'toa_image_path',
                'Skyscraper': 'skyscraper_image_path',
                'CuratedCarousel': 'carousel_image_path'
            }
        elif retailer == 'walmart':
            type_to_path_field = {
                'sba': 'image_path',
                'sbv': 'image_path',
                'tile_takeover': 'image_path',
                'top_banner': 'image_path'
            }
        elif retailer == 'instacart':
            type_to_path_field = {
                'display_ad': 'image_path',
                'shoppable_recipe_ad': 'image_path',
                'main': 'image_path'
            }
        else:
            type_to_path_field = {}

        path_field = type_to_path_field.get(ad.get('type'), 'image_path')
        rel = ad.get(path_field)
        if not rel:
            return None

        # If JSON path is relative, join to base_dir; otherwise return as-is
        if not os.path.isabs(rel):
            return os.path.join(base_dir, rel)
        return rel

    def find_existing_image_ignoring_brand(self, expected_full_path):
        """Given an expected filename, find a file in the same folder that matches
        all parts except the brand slug segment (second segment)."""
        if not expected_full_path:
            return None

        dname, bname = os.path.split(expected_full_path)
        parts = bname.split('__')
        # Expect retailer__brand__adtype__client__search__D...png
        if len(parts) < 3:
            return None

        # Build a wildcard that ignores the brand slug segment
        pattern = os.path.join(dname, f"{parts[0]}__*__{'__'.join(parts[2:])}")
        candidates = glob.glob(pattern)
        # If there are multiple, pick the most recent
        if candidates:
            candidates.sort(key=os.path.getmtime, reverse=True)
            return candidates[0]
        return None
    
    def is_uncertain_brand(self, brand):
        """Check if a brand name looks uncertain or like a campaign code"""
        if not brand or (brand and brand.lower() == 'unknown'):
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
        # Kroger: output/retailer/CLIENT/runs/*.json -> base_dir = output/retailer/CLIENT
        # Instacart: output/instacart/CLIENT/runs/TIMESTAMP/*.json -> base_dir = output/instacart/CLIENT
        # Walmart: output/walmart/CLIENT/TIMESTAMP/*.json -> base_dir = output/walmart/CLIENT
        runs_dir = os.path.dirname(json_file)
        base_dir = os.path.dirname(runs_dir)
        
        # For Instacart, runs_dir is output/.../runs/TIMESTAMP, need to go up 2 levels
        if retailer == 'instacart' and re.match(r'^\d{14}$', os.path.basename(runs_dir)):
            base_dir = os.path.dirname(os.path.dirname(runs_dir))
        # For Walmart, if runs_dir ends with timestamp, go up one more level
        elif retailer == 'walmart' and re.match(r'\d{14}$', os.path.basename(runs_dir)):
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
                'Shoppable_Display_Ad': 'Shoppable_Display_Ads',
                'Shoppable_Video_Ad': 'Shoppable_Video_Ads',
                'main': 'Main'
            }
            type_to_path_field = {
                'display_ad': 'image_path',
                'shoppable_recipe_ad': 'image_path',
                'Shoppable_Display_Ad': 'image_path',
                'Shoppable_Video_Ad': 'image_path',
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
            # STRICT MODE: If JSON specifies a path but file doesn't exist, return None
            # Do NOT fall back to fuzzy search - this causes mismatches
            print(f"[STRICT] JSON specifies path but file not found: {image_path_from_json}")
            return None
        
        # Only use fallback search if JSON has NO path specified
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
        
        # Reset delete-armed state when changing ads
        self.delete_armed_index = None
        if hasattr(self, 'delete_button'):
            self.delete_button.config(text="Delete Ad")

        ad_data = self.unknown_ads[self.current_index]
        ad = ad_data['ad']
        
        # Update progress - show unique brands count
        unique_brands = len(set(ad['current_brand'] for ad in self.unknown_ads))
        self.progress_label.config(
            text=f"Ad {self.current_index + 1} of {len(self.unknown_ads)} ({unique_brands} unique brands)"
        )
        
        # Update current brand(s) - show all if co-branded, with proper display names
        advertisers = ad.get('advertisers', ['unknown'])
        display_brands = []
        for adv in advertisers:
            canonical = self.get_canonical_brand_name(adv) if adv and adv.lower() != 'unknown' else None
            display_brands.append(canonical or (adv.replace('_', ' ').title() if '_' in (adv or '') else (adv or 'unknown')))
        brand_text = ", ".join(display_brands)
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
            # Check if this was a guessed path (no path in JSON)
            # A stored path means the JSON has an explicit image_path field
            has_stored_path = bool(ad.get('image_path') or 
                                   ad.get('toa_image_path') or 
                                   ad.get('skyscraper_image_path') or 
                                   ad.get('carousel_image_path'))
            
            if not has_stored_path:
                self.image_path_var.set(f"⚠️ 📁 {ad_data['image_path']} (may not match)")
                self.image_path_label.config(foreground="orange")
            else:
                self.image_path_var.set(f"📁 {ad_data['image_path']}")
                self.image_path_label.config(foreground="blue")
            self.current_image_path = ad_data['image_path']
        else:
            self.image_path_var.set("Image: Not found")
            self.image_path_label.config(foreground="gray")
            self.current_image_path = None
        
        # Load and display image
        if ad_data['image_path'] and os.path.exists(ad_data['image_path']):
            self.display_image(ad_data['image_path'])
        else:
            self.image_label.config(text="No image available", image='')
            if ad_data['image_path']:
                print(f"[WARNING] Image path exists in data but file not found: {ad_data['image_path']}")
        
        # Generate suggestions
        self.show_suggestions(ad, json_file=ad_data.get('json_file'))
        
        # Populate brand entry fields with existing brands (resolved to canonical names)
        resolved_brands = []
        for adv in advertisers:
            if adv and adv.lower() != 'unknown':
                canonical = self.get_canonical_brand_name(adv)
                resolved_brands.append(canonical or (adv.replace('_', ' ').title() if '_' in adv else adv))
            else:
                resolved_brands.append(adv)
        self.set_brand_entries(resolved_brands)
        
        # Update house ad button text based on retailer
        json_file = ad_data['json_file']
        if '/walmart/' in json_file:
            self.house_ad_button.config(text="Mark as Walmart House Ad")
        elif '/kroger/' in json_file:
            self.house_ad_button.config(text="Mark as Kroger House Ad")
        elif '/instacart/' in json_file:
            self.house_ad_button.config(text="Mark as Instacart House Ad")
        else:
            self.house_ad_button.config(text="Mark as House Ad")
        
        # Focus first entry
        self.brand_entries[0].focus()
    
    def format_ad_details(self, ad):
        """Format ad details for display"""
        # Get current ad data to access JSON file path
        ad_data = self.unknown_ads[self.current_index]
        json_file = ad_data.get('json_file', 'Unknown')
        
        # Read client and keyword from the actual JSON file (not path parsing)
        client = 'Unknown'
        search_term = 'Unknown'
        if json_file and os.path.exists(json_file):
            try:
                with open(json_file, 'r') as f:
                    json_data = json.load(f)
                # Read actual fields from JSON
                client = json_data.get('client', 'Unknown')
                search_term = json_data.get('keyword', 'Unknown')
            except Exception:
                pass
        
        # Fallback to path parsing only if JSON read failed
        if client == 'Unknown' and json_file:
            parts = json_file.split(os.sep)
            # Find 'output' index and get client from there
            try:
                output_idx = parts.index('output')
                if len(parts) > output_idx + 2:
                    client = parts[output_idx + 2]  # output/retailer/CLIENT/...
            except ValueError:
                if len(parts) >= 3:
                    client = parts[-3]
        
        if search_term == 'Unknown' and json_file:
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
        advertisers = ad.get('advertisers', ['unknown'])
        current_brand_raw = advertisers[0] if advertisers else 'unknown'
        current_brand_display = self.get_canonical_brand_name(current_brand_raw) if current_brand_raw and current_brand_raw.lower() != 'unknown' else None
        if not current_brand_display:
            current_brand_display = current_brand_raw.replace('_', ' ').title() if '_' in (current_brand_raw or '') else current_brand_raw
        details.append(f"Current Brand: {current_brand_display}")
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
    
    def open_image_in_finder(self, event=None):
        """Open the current image file location in Finder"""
        if not self.current_image_path:
            return
        
        try:
            import subprocess
            
            file_path = os.path.abspath(self.current_image_path)
            
            if os.path.exists(file_path):
                # Open Finder and select the file
                subprocess.run(["open", "-R", file_path])
            else:
                print(f"File not found: {file_path}")
        except Exception as e:
            print(f"Error opening in Finder: {e}")
    
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
    
    def extract_brands_from_html(self, json_file):
        """Extract brand names from the companion HTML file's accessibility text.
        
        Parses 'Sponsored Ad.\nBranded image.\n{PRODUCT_TITLE}\n' patterns
        from inline <span> accessibility text (no reliance on div/class names).
        Cross-references against the brand lexicon for verified matches.
        
        Returns list of (brand_name, is_verified) tuples, sorted verified-first.
        """
        results = []
        if not json_file or not os.path.exists(json_file):
            return results
        
        try:
            # Load the JSON to get the companion HTML filename
            with open(json_file, 'r') as f:
                json_data = json.load(f)
            html_filename = json_data.get('html')
            if not html_filename:
                return results
            
            html_path = os.path.join(os.path.dirname(json_file), html_filename)
            if not os.path.exists(html_path):
                return results
            
            with open(html_path, 'r', errors='ignore') as f:
                html_content = f.read()
            
            # Extract product titles from accessibility text
            # Variants found in HTML:
            #   Sponsored Ad.\nBranded image.\n{TITLE}\n
            #   Sponsored Ad.\nBrand logo.\nBranded image.\n{TITLE}\n
            #   Sponsored Ad.\nBrand logo.\nProduct image.\n{TITLE}\n
            #   Sponsored Ad.\nProduct image.\n{TITLE}\n
            titles = re.findall(
                r'Sponsored Ad\\.\\\\n(?:Brand logo\\.\\\\n)?(?:(?:Branded|Product) image\\.\\\\n)?(.+?)\\\\n',
                html_content
            )
            # Pattern 2: aria-label="Sponsored Ad - {TITLE}" (sponsored product listings)
            aria_titles = re.findall(
                r'aria-label="Sponsored Ad - (.+?)"',
                html_content
            )
            titles.extend(aria_titles)
            
            if not titles:
                return results
            
            print(f"[HTML] Found {len(titles)} sponsored ad titles in HTML")
            
            # Extract verified lexicon matches and unverified guesses from HTML titles.
            # Verified matches are shown first; unverified guesses are marked with ❓.
            seen = set()
            for raw_title in titles:
                # Decode HTML entities
                title = raw_title.replace('&amp;amp;', '&').replace('&amp;', '&').strip()
                
                matched_lexicon = False
                # Check against lexicon brands (names + synonyms)
                for lex_brand in self.lexicon_brands:
                    brand_name = lex_brand['name']
                    # Check if brand name appears at the start of the title (case-insensitive)
                    if title.lower().startswith(brand_name.lower()) and brand_name.lower() not in seen:
                        seen.add(brand_name.lower())
                        results.append((brand_name, True))
                        matched_lexicon = True
                        print(f"[HTML] ✅ Verified lexicon match: '{brand_name}' from title '{title[:60]}'")
                    # Also check synonyms
                    for synonym in lex_brand.get('synonyms', []):
                        if synonym.startswith('MSG:'):
                            continue
                        if title.lower().startswith(synonym.lower()) and brand_name.lower() not in seen:
                            seen.add(brand_name.lower())
                            results.append((brand_name, True))
                            matched_lexicon = True
                            print(f"[HTML] ✅ Verified synonym match: '{brand_name}' (via '{synonym}') from title '{title[:60]}'")
                
                # If no lexicon match, extract first word(s) as unverified clickable guess
                if not matched_lexicon:
                    # Try "Brand - Product" pattern first (e.g., "Minor Figures - Oat Milk")
                    dash_match = re.match(r'^(.+?)\s*-\s', title)
                    if dash_match:
                        guess = dash_match.group(1).strip()
                    else:
                        # Fall back to first 1-2 capitalized words
                        word_match = re.match(r'^([A-Z][A-Za-z&\'\-]+(?:\s+[A-Z][A-Za-z&\'\-]+)?)', title)
                        guess = word_match.group(1) if word_match else None
                    
                    if guess and guess.lower() not in seen and len(guess) > 2:
                        seen.add(guess.lower())
                        results.append((guess, False))
                        print(f"[HTML] ❓ Unverified guess: '{guess}' from title '{title[:60]}'")
            
            # Sort: verified first, then unverified
            results.sort(key=lambda x: (not x[1], x[0]))
            
        except Exception as e:
            print(f"[HTML] Error extracting brands from HTML: {e}")
        
        return results
    
    def show_suggestions(self, ad, json_file=None):
        """Generate and show brand suggestions.
        
        Sources (in priority order):
        1. Current brand/advertisers fields (resolved to canonical display name)
        2. Product titles in the ad JSON (leading brand words)
        3. TOA campaign codes
        4. URL path segments
        5. Message/header text
        6. Companion HTML file (Sponsored Ad accessibility text)
        
        Each suggestion is checked against the lexicon for verification.
        Verified (✅) suggestions sort before unverified (❓) ones.
        """
        from utils.brand_utils import normalize_brand_for_matching
        
        # Clear existing suggestions
        for widget in self.suggestions_frame.winfo_children():
            widget.destroy()
        
        # ranked: list of (display_text, brand_name, is_verified)
        ranked = []
        seen_normalized = set()
        
        # Generic words that should never be suggested as brand names
        skip_words = {
            'brand', 'sponsored', 'shop', 'save', 'deal', 'free', 'best',
            'from', 'with', 'your', 'more', 'less', 'huge', 'sale', 'new',
        }
        
        def _add(raw_name):
            """Add a suggestion, resolving to canonical name if in lexicon."""
            if not raw_name or len(raw_name) < 2:
                return
            if raw_name.lower() in skip_words:
                return
            norm = normalize_brand_for_matching(raw_name)
            if norm in seen_normalized or not norm:
                return
            seen_normalized.add(norm)
            canonical = self.get_canonical_brand_name(raw_name)
            if canonical:
                display = canonical
                is_verified = True
            else:
                # Use proper title case for display (un-slug)
                display = raw_name.replace('_', ' ').title() if '_' in raw_name else raw_name
                is_verified = False
            prefix = "✅ " if is_verified else "❓ "
            ranked.append((prefix + display, display, is_verified))
            print(f"[SUGGESTION] {'✅' if is_verified else '❓'} {display} (from: {raw_name})")
        
        # --- Source 1: Current brand / advertisers fields ---
        brand_field = (ad.get('brand') or '').strip()
        if brand_field and brand_field.lower() != 'unknown':
            _add(brand_field)
        for adv in (ad.get('advertisers') or []):
            if adv and adv.lower() != 'unknown':
                _add(adv)
        
        # --- Source 2: Product titles (leading brand words) ---
        for product in ad.get('products', []):
            title = product.get('title', '')
            if not title:
                continue
            # Try "BRAND Product..." pattern (all-caps brand prefix)
            caps_match = re.match(r'^([A-Z][A-Z0-9]+(?:\s+[A-Z][A-Z0-9]+)*)\s', title)
            if caps_match:
                _add(caps_match.group(1).title())
            # Try "Brand Name - Product..." or "Brand Name Product..."
            dash_match = re.match(r'^(.+?)\s*[-–|]\s', title)
            if dash_match:
                _add(dash_match.group(1).strip())
            # Try leading capitalized words (e.g., "Purito Oat In..." -> "Purito")
            word_match = re.match(r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})', title)
            if word_match:
                _add(word_match.group(1))
        
        # --- Source 3: TOA campaign codes ---
        current_adv = ad.get('advertisers', [''])[0] if ad.get('advertisers') else ''
        if current_adv:
            toa_match = re.match(r'^TOA([A-Z][a-z]+)', current_adv, re.IGNORECASE)
            if toa_match:
                _add(toa_match.group(1))
        
        # --- Source 4: URL path segments ---
        href = ad.get('href', '')
        if href:
            url_brands = re.findall(r'/([a-z][a-z-]+)/', href.lower())
            for brand in url_brands:
                if len(brand) > 3 and brand not in ['search', 'product', 'kroger', 'stores', 'page', 'amazon']:
                    _add(brand.replace('-', ' ').title())
        
        # --- Source 5: Message/header text ---
        for field in ['message', 'header']:
            text = ad.get(field, '')
            if text:
                words = re.findall(r'\b[A-Z][A-Za-z&\'\-]+(?:\s+[A-Z][A-Za-z&\'\-]+)?', text)
                for word in words[:2]:
                    if len(word) > 3:
                        _add(word)
        
        # HTML companion extraction removed from suggestions.
        # It returns ALL brands on the page, not just the current ad's brand,
        # causing wrong suggestions (e.g. Califia Farms for a CyberPower ad).
        # The capture script now handles brand extraction at scrape time via
        # iframe piercing + positional matching (_try_hybrid_extraction).
        
        # Sort: verified first, then alphabetical
        ranked.sort(key=lambda x: (not x[2], x[0]))
        
        # Display up to 6 suggestions as buttons
        for i, (display_text, brand_name, _) in enumerate(ranked[:6]):
            btn = ttk.Button(
                self.suggestions_frame,
                text=display_text,
                command=lambda s=brand_name: self.use_suggestion(s)
            )
            btn.grid(row=i, column=0, padx=5, pady=3, sticky=tk.EW)
        
        self.suggestions_frame.columnconfigure(0, weight=1)
    
    def use_suggestion(self, suggestion):
        """Use a suggested brand name"""
        self.brand_entries[0].delete(0, tk.END)
        self.brand_entries[0].insert(0, suggestion)
        self.brand_entries[0].focus()
    
    def save_correction(self):
        """Save the corrected brand name(s) - applies to all similar ads"""
        try:
            print("[DEBUG] save_correction called")
            corrected_brands = self.get_all_brands()
            print(f"[DEBUG] Corrected brands: {corrected_brands}")
            
            if not corrected_brands:
                print("[DEBUG] No brands entered, showing warning")
                messagebox.showwarning("Missing Brand", "Please enter at least one brand name")
                return
            
            # Just call apply_to_all_similar with auto_confirm=True
            print("[DEBUG] Calling apply_to_all_similar")
            self.apply_to_all_similar(auto_confirm=True)
        except Exception as e:
            print(f"[ERROR] Exception in save_correction: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Error", f"Failed to save correction: {e}")
    
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
        
        # Handle both canonical and legacy formats
        ads_to_check = []
        
        # Canonical format: {"ads": [...]}
        if 'ads' in data and isinstance(data['ads'], list):
            ads_to_check = data['ads']
        # Legacy format: {"results": [{"ads": [...]}]}
        elif 'results' in data:
            results = data.get('results', [])
            if not isinstance(results, list):
                raise Exception(f"'results' is not a list: {type(results)}")
            
            for result_idx, result in enumerate(results):
                if not isinstance(result, dict):
                    raise Exception(f"result[{result_idx}] is not a dict: {type(result)}")
                
                ads = result.get('ads', [])
                if not isinstance(ads, list):
                    raise Exception(f"'ads' in result[{result_idx}] is not a list: {type(ads)}")
                
                ads_to_check.extend(ads)
        
        # Update the matching ad
        for i, ad in enumerate(ads_to_check):
            if not isinstance(ad, dict):
                raise Exception(f"ad[{i}] is not a dict: {type(ad)}")
            
            # Match by multiple criteria to ensure we get the right ad
            # Priority 1: Match by unique 'id' field (Instacart uses this)
            target_id = target_ad.get('id')
            ad_id = ad.get('id')
            
            # If target has an id, ONLY match by id (strict matching for Instacart)
            if target_id:
                if ad_id != target_id:
                    continue  # Skip this ad, keep looking
                # Found the matching id
            else:
                # Fallback for ads without id: Match by type+position (Kroger/Walmart)
                type_match = ad.get('type') == target_type
                position_match = ad.get('position') == target_position
                
                # Additional matching criteria
                image_url_match = ad.get('image_url') == target_ad.get('image_url') if target_ad.get('image_url') else True
                href_match = ad.get('href') == target_ad.get('href') if target_ad.get('href') else True
                
                if not ((type_match and position_match and (image_url_match or href_match)) or ad == target_ad):
                    continue  # No match, keep looking
            
            # Found a match - update it
            ad['advertisers'] = corrected_brands
            # Also update 'brand' field to match first advertiser
            ad['brand'] = corrected_brands[0] if corrected_brands else None
            
            # Update image path even if it doesn't literally contain the old brand slug
            for path_key in ['carousel_image_path', 'toa_image_path', 'skyscraper_image_path', 'image_path']:
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
        
        if not updated:
            print(f"[ERROR] Could not find ad in JSON")
            print(f"  Looking for: type={target_type}, position={target_position}")
            print(f"  image_url={target_ad.get('image_url')}, href={target_ad.get('href')}")
            print(f"  Total ads in JSON: {len(ads_to_check)}")
            raise Exception(f"Could not find ad in JSON (type={target_type}, position={target_position})")
        
        # Save updated JSON
        print(f"[DEBUG] Saving updated JSON: {json_file}")
        with open(json_file, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"[DEBUG] JSON saved successfully")
    
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
                # Save with validation and deduplication
                lexicon_brands_sorted = save_lexicon(lexicon_brands, self.lexicon_path)
                print(f"[SYNC] Added {added_count} brands from logo database to lexicon")
                
                # Reload lexicon cache
                self.lexicon_brands = lexicon_brands_sorted
        except Exception as e:
            print(f"[WARN] Failed to sync logo brands to lexicon: {e}")
    
    def update_lexicon(self, corrected_brand, old_brand, message_signal=None, header_signal=None):
        """Add corrected brand to lexicon and add old brand + header + message as aliases"""
        # NEVER add "unknown" to lexicon
        if corrected_brand.lower() == 'unknown':
            print(f"[LEXICON] Skipping - 'unknown' cannot be added to lexicon")
            return
        
        # Load lexicon (it's a list of {name, synonyms} objects)
        with open(self.lexicon_path, 'r') as f:
            brands = json.load(f)
        
        # Check if corrected_brand exists as a synonym anywhere - if so, remove it
        for brand in brands:
            if corrected_brand in brand['synonyms']:
                brand['synonyms'].remove(corrected_brand)
                print(f"[LEXICON] Removed '{corrected_brand}' from synonyms of '{brand['name']}' (promoting to main brand)")
        
        # Check if brand already exists as a main entry
        existing_brand = None
        for brand in brands:
            if brand['name'].lower() == corrected_brand.lower():
                existing_brand = brand
                break
        
        # Collect synonyms to add
        synonyms_to_add = []
        if old_brand.lower() != 'unknown':
            synonyms_to_add.append(old_brand)
        
        # Generic phrases that should NOT be added as synonyms
        generic_phrases = {
            'shop now', 'buy now', 'add to cart', 'learn more', 'see more',
            'featured', 'sponsored', 'ad', 'advertisement', 'new', 'sale',
            'save', 'deal', 'deals', 'offer', 'offers', 'discount', 'free',
            'best seller', 'top rated', 'popular', 'trending', 'recommended',
            'shop', 'buy', 'get', 'try', 'discover', 'explore', 'view',
            'click here', 'order now', 'subscribe', 'sign up', 'join',
        }
        
        def is_substantial_text(text):
            """Check if text is substantial enough to be a useful synonym"""
            if not text:
                return False
            text_lower = text.lower().strip()
            # Too short
            if len(text_lower) < 5:
                return False
            # Is a generic phrase
            if text_lower in generic_phrases:
                return False
            # Only 1-2 common words
            words = text_lower.split()
            if len(words) <= 2 and all(w in generic_phrases for w in words):
                return False
            return True
        
        # Add header as a synonym (this is often the brand display text from the ad)
        if header_signal and is_substantial_text(header_signal):
            header_clean = header_signal.strip()
            # Don't add if it's the same as the corrected brand or old brand
            if header_clean.lower() != corrected_brand.lower() and header_clean.lower() != old_brand.lower():
                synonyms_to_add.append(header_clean)
                print(f"[LEXICON] Adding header '{header_clean}' as synonym")
        
        # Add message as a synonym only if substantial
        if message_signal and is_substantial_text(message_signal):
            msg_clean = message_signal.strip()
            # Don't add if same as brand, old brand, or header
            if (msg_clean.lower() != corrected_brand.lower() and 
                msg_clean.lower() != old_brand.lower() and
                msg_clean.lower() != (header_signal or '').lower().strip()):
                synonyms_to_add.append(f"MSG:{msg_clean}")
                print(f"[LEXICON] Adding message '{msg_clean}' as synonym")
        
        if existing_brand:
            # Mark as verified (user explicitly confirmed this brand)
            existing_brand['verified'] = True
            # Add synonyms if not already there
            for syn in synonyms_to_add:
                if syn not in existing_brand['synonyms']:
                    existing_brand['synonyms'].append(syn)
                    if syn.startswith('MSG:'):
                        print(f"[LEXICON] Added message signal for '{existing_brand['name']}'")
                    else:
                        print(f"[LEXICON] Added '{syn}' as synonym for '{existing_brand['name']}'")
        else:
            # Add new brand (marked verified since user explicitly entered it)
            new_brand = {
                'name': corrected_brand,
                'synonyms': synonyms_to_add,
                'verified': True
            }
            brands.append(new_brand)
            if synonyms_to_add:
                print(f"[LEXICON] Added new brand '{corrected_brand}' with {len(synonyms_to_add)} synonym(s)")
            else:
                print(f"[LEXICON] Added new brand '{corrected_brand}'")
        
        # Save with validation and deduplication
        brands_sorted = save_lexicon(brands, self.lexicon_path)
        
        # Reload lexicon cache
        self.lexicon_brands = brands_sorted
    
    def apply_to_all_similar(self, auto_confirm=False):
        """Apply the corrected brand(s) to all similar ads with the same message/header/URL"""
        print(f"[DEBUG] apply_to_all_similar called, auto_confirm={auto_confirm}")
        
        # Bounds check - make sure we have ads to process
        if not self.unknown_ads or self.current_index >= len(self.unknown_ads):
            print(f"[DEBUG] No ads to process (index={self.current_index}, len={len(self.unknown_ads)})")
            messagebox.showinfo("Complete", "All ads have been reviewed!")
            return
        
        corrected_brands = self.get_all_brands()
        print(f"[DEBUG] Corrected brands in apply_to_all_similar: {corrected_brands}")
        
        if not corrected_brands:
            print("[DEBUG] No brands, returning")
            messagebox.showwarning("Missing Brand", "Please enter at least one brand name")
            return
        
        # Prevent saving "unknown" as a brand
        if any(brand.lower() == 'unknown' for brand in corrected_brands):
            messagebox.showerror("Invalid Brand", "'unknown' cannot be used as a brand name.\n\nPlease enter the actual brand name.")
            return
        
        # Check if any brand is blacklisted and warn user
        from core.brands import is_blacklisted
        blacklisted_brands = [b for b in corrected_brands if is_blacklisted(b)]
        if blacklisted_brands:
            response = messagebox.askyesno(
                "Blacklisted Brand Warning",
                f"The following brand(s) are in the blacklist:\n\n"
                f"{', '.join(blacklisted_brands)}\n\n"
                f"Blacklisted brands are filtered from the frontend.\n"
                f"Did you mean to use 'Mark as House Ad' instead?\n\n"
                f"Continue anyway?"
            )
            if not response:
                return
        
        ad_data = self.unknown_ads[self.current_index]
        current_ad = ad_data['ad']
        original_uncertain_brand = ad_data['current_brand']  # Save for lexicon update
        
        print(f"[DEBUG] Current ad: type={current_ad.get('type')}, brand={original_uncertain_brand}")
        
        # Get identifying features from current ad
        current_message = (current_ad.get('message') or '').strip()
        current_header = (current_ad.get('header') or '').strip()
        current_url = (current_ad.get('href') or '').strip()
        
        print(f"[DEBUG] Matching criteria: message={bool(current_message)}, header={bool(current_header)}, url={bool(current_url)}")
        
        # Find all ads with matching content
        similar_ads = []
        for i, ad in enumerate(self.unknown_ads):
            ad_obj = ad['ad']
            
            # Always include the current ad
            if i == self.current_index:
                similar_ads.append((i, ad))
                continue
            
            # Match by message, header, or URL
            matches = False
            if current_message and (ad_obj.get('message') or '').strip() == current_message:
                matches = True
            elif current_header and (ad_obj.get('header') or '').strip() == current_header:
                matches = True
            elif current_url and (ad_obj.get('href') or '').strip() == current_url:
                matches = True
            
            if matches:
                similar_ads.append((i, ad))
        
        print(f"[DEBUG] Found {len(similar_ads)} similar ads (text-based)")
        
        # If no text matches found and we have an image hash, offer hash-based matching
        current_hash = ad_data.get('image_hash')
        if len(similar_ads) == 1 and current_hash and IMAGEHASH_AVAILABLE:
            # First check if this hash was already corrected in a previous save
            # Use Hamming distance for fuzzy matching (allows minor differences)
            cached_brands = None
            best_distance = 999
            for cached_hash, brands in self.hash_to_brand.items():
                try:
                    dist = imagehash.hex_to_hash(current_hash) - imagehash.hex_to_hash(cached_hash)
                    if dist <= 5 and dist < best_distance:  # Allow up to 5 bits difference
                        best_distance = dist
                        cached_brands = brands
                except:
                    if current_hash == cached_hash:
                        cached_brands = brands
                        best_distance = 0
            
            if cached_brands:
                print(f"[DEBUG] Found cached hash match (distance={best_distance}): {cached_brands}")
                # Auto-fill the brand from cache and show confirmation
                response = messagebox.askyesno(
                    "🔍 IMAGE HASH MATCH (from previous correction)",
                    f"This image matches a previously corrected ad.\n\n"
                    f"Cached brand: {', '.join(cached_brands)}\n"
                    f"Your input: {', '.join(corrected_brands)}\n\n"
                    f"Use the cached brand instead?"
                )
                if response:
                    corrected_brands = cached_brands
                    print(f"[DEBUG] Using cached brands: {corrected_brands}")
            
            # Find ads with matching image hash in the current queue (fuzzy match)
            hash_matches = []
            for i, ad in enumerate(self.unknown_ads):
                if i == self.current_index:
                    continue
                ad_hash = ad.get('image_hash')
                if ad_hash:
                    try:
                        dist = imagehash.hex_to_hash(current_hash) - imagehash.hex_to_hash(ad_hash)
                        if dist <= 5:  # Allow up to 5 bits difference
                            hash_matches.append((i, ad))
                    except:
                        if ad_hash == current_hash:
                            hash_matches.append((i, ad))
            
            if hash_matches:
                print(f"[DEBUG] Found {len(hash_matches)} image hash matches in queue")
                # Show visual confirmation dialog for each hash match
                confirmed_matches = self.confirm_hash_matches(ad_data, hash_matches, corrected_brands)
                similar_ads.extend(confirmed_matches)
                print(f"[DEBUG] User confirmed {len(confirmed_matches)} hash matches")
        
        # Save this hash -> brand mapping for future matches
        if current_hash and corrected_brands:
            self.hash_to_brand[current_hash] = corrected_brands
            print(f"[DEBUG] Cached hash {current_hash[:16]}... -> {corrected_brands}")
        
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
        updated_indices = set()
        
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
                updated_indices.add(idx)
            except Exception as e:
                print(f"[ERROR] Failed to update ad {idx}: {e}")
                error_count += 1
        
        # Update lexicon for each brand with the original uncertain brand, header, and message signal
        try:
            current_ad = ad_data['ad']
            message_signal = (current_ad.get('message') or '').strip()
            header_signal = (current_ad.get('header') or '').strip()
            
            for brand in corrected_brands:
                self.update_lexicon(brand, original_uncertain_brand, 
                                   message_signal=message_signal,
                                   header_signal=header_signal)
        except Exception as e:
            print(f"[ERROR] Failed to update lexicon: {e}")
        
        # Remove only the ads that were actually updated (by index)
        old_count = len(self.unknown_ads)
        self.unknown_ads = [ad for i, ad in enumerate(self.unknown_ads) if i not in updated_indices]
        
        # ALSO filter out any remaining ads whose messages now match the lexicon
        # (This catches ads with the same message that weren't in the similar_ads list)
        if message_signal:
            before_filter = len(self.unknown_ads)
            self.unknown_ads = [
                ad for ad in self.unknown_ads
                if not self.match_message_to_lexicon((ad['ad'].get('message') or '').strip())
            ]
            extra_filtered = before_filter - len(self.unknown_ads)
            if extra_filtered > 0:
                print(f"[INFO] Filtered out {extra_filtered} additional ads with matching message")
        
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

    def confirm_hash_matches(self, current_ad_data, hash_matches, corrected_brands):
        """Show visual confirmation dialog for image hash matches.
        
        Displays the current ad image alongside each potential match for human validation.
        Returns list of confirmed matches as (index, ad_data) tuples.
        """
        confirmed = []
        brand_text = ", ".join(corrected_brands)
        
        for idx, match_ad in hash_matches:
            # Create a dialog showing both images side-by-side
            dialog = tk.Toplevel(self.root)
            dialog.title("🔍 IMAGE HASH MATCH - Visual Confirmation Required")
            dialog.geometry("1200x900")
            dialog.transient(self.root)
            dialog.grab_set()
            
            # Result variable
            result = {'confirmed': False}
            
            # Header label
            header = ttk.Label(
                dialog,
                text=f"⚠️ IMAGE HASH MATCH DETECTED ⚠️\nApply brand '{brand_text}' to this matching ad?",
                font=("Arial", 14, "bold"),
                foreground="orange"
            )
            header.pack(pady=10)
            
            # Images frame
            images_frame = ttk.Frame(dialog)
            images_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            # Current ad (left side)
            left_frame = ttk.LabelFrame(images_frame, text="CURRENT AD (just corrected)", padding=10)
            left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
            
            current_path = current_ad_data.get('image_path', '')
            if current_path and os.path.exists(current_path):
                try:
                    img = Image.open(current_path)
                    img.thumbnail((500, 500), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    img_label = ttk.Label(left_frame, image=photo)
                    img_label.image = photo
                    img_label.pack()
                except Exception:
                    ttk.Label(left_frame, text="[Image load error]").pack()
            else:
                ttk.Label(left_frame, text="[No image]").pack()
            
            ttk.Label(left_frame, text=os.path.basename(current_path) if current_path else "N/A", 
                     font=("Courier", 9), wraplength=450).pack(pady=5)
            
            # Match ad (right side)
            right_frame = ttk.LabelFrame(images_frame, text="POTENTIAL MATCH (hash-based)", padding=10)
            right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5)
            
            match_path = match_ad.get('image_path', '')
            if match_path and os.path.exists(match_path):
                try:
                    img = Image.open(match_path)
                    img.thumbnail((500, 500), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    img_label = ttk.Label(right_frame, image=photo)
                    img_label.image = photo
                    img_label.pack()
                except Exception:
                    ttk.Label(right_frame, text="[Image load error]").pack()
            else:
                ttk.Label(right_frame, text="[No image]").pack()
            
            ttk.Label(right_frame, text=os.path.basename(match_path) if match_path else "N/A",
                     font=("Courier", 9), wraplength=450).pack(pady=5)
            
            # Match details
            match_json = os.path.basename(match_ad.get('json_file', 'Unknown'))
            match_keyword = match_ad.get('ad', {}).get('metadata', {}).get('keyword_token', 'Unknown')
            details_text = f"JSON: {match_json} | Keyword: {match_keyword}"
            ttk.Label(right_frame, text=details_text, font=("Arial", 10)).pack(pady=5)
            
            # Buttons
            button_frame = ttk.Frame(dialog)
            button_frame.pack(pady=15)
            
            def on_yes():
                result['confirmed'] = True
                dialog.destroy()
            
            def on_no():
                result['confirmed'] = False
                dialog.destroy()
            
            yes_btn = ttk.Button(button_frame, text="✓ Yes, Same Ad - Apply Brand", command=on_yes)
            yes_btn.pack(side=tk.LEFT, padx=20)
            
            no_btn = ttk.Button(button_frame, text="✗ No, Different Ad - Skip", command=on_no)
            no_btn.pack(side=tk.LEFT, padx=20)
            
            # Wait for dialog to close
            dialog.wait_window()
            
            if result['confirmed']:
                confirmed.append((idx, match_ad))
        
        return confirmed

    def delete_current_ad(self):
        """Two-step delete: first click arms, second click deletes without popups."""
        if not self.unknown_ads:
            return

        # First click: arm delete for this index
        if self.delete_armed_index != self.current_index:
            self.delete_armed_index = self.current_index
            if hasattr(self, 'delete_button'):
                self.delete_button.config(text="Confirm Delete")
            return

        # Second click on the same ad: perform deletion
        ad_data = self.unknown_ads[self.current_index]
        json_file = ad_data.get('json_file')
        target_ad = ad_data.get('ad') or {}
        
        # Add the current brand to blacklist so it won't be shown again
        current_brand = ad_data.get('current_brand') or target_ad.get('brand')
        if current_brand and current_brand.lower() != 'unknown':
            self.add_to_blacklist(current_brand)
        
        # ALSO blacklist the message text if present (for house ads)
        # This prevents the same message from appearing again in future runs
        message = target_ad.get('message', '').strip()
        if message:
            message_key = f"MSG:{message}"
            self.add_to_blacklist(message_key)
            print(f"[BLACKLIST] Also blacklisted message: '{message[:60]}...')")

        # Capture content signature for bulk-deleting identical ads without images
        base_header = (target_ad.get('header') or '').strip()
        base_products = [
            (p.get('title') or '').strip()
            for p in (target_ad.get('products') or [])
        ]

        if not json_file:
            # Nothing we can safely update; just remove from in-memory queue
            del self.unknown_ads[self.current_index]
            self.delete_armed_index = None
            if hasattr(self, 'delete_button'):
                self.delete_button.config(text="Delete Ad")
            if self.unknown_ads:
                if self.current_index >= len(self.unknown_ads):
                    self.current_index = max(0, len(self.unknown_ads) - 1)
                self.show_current_ad()
            else:
                messagebox.showinfo("Complete", "All unknown brands have been reviewed!")
                self.root.quit()
            return

        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read JSON:\n{e}")
            return

        target_type = target_ad.get('type')
        target_position = target_ad.get('position')
        target_image_url = target_ad.get('image_url')
        target_href = target_ad.get('href')

        def _matches(ad_obj):
            if not isinstance(ad_obj, dict):
                return False
            type_match = ad_obj.get('type') == target_type
            position_match = ad_obj.get('position') == target_position
            image_url_match = (
                target_image_url is None or
                ad_obj.get('image_url') == target_image_url
            )
            href_match = (
                target_href is None or
                ad_obj.get('href') == target_href
            )
            return ((type_match and position_match and (image_url_match or href_match)) or ad_obj == target_ad)

        deleted = False

        # Canonical format: {"ads": [...]} 
        if 'ads' in data and isinstance(data['ads'], list):
            ads_list = data['ads']
            for idx, ad_obj in enumerate(ads_list):
                if _matches(ad_obj):
                    del ads_list[idx]
                    deleted = True
                    break
        # Legacy format: {"results": [{"ads": [...]}]}
        elif 'results' in data:
            results = data.get('results', [])
            for result in results:
                ads_list = result.get('ads', [])
                if not isinstance(ads_list, list):
                    continue
                for idx, ad_obj in enumerate(ads_list):
                    if _matches(ad_obj):
                        del ads_list[idx]
                        deleted = True
                        break
                if deleted:
                    break

        if not deleted:
            # If we can't find it in JSON, still drop it from the queue
            del self.unknown_ads[self.current_index]
            self.delete_armed_index = None
            if hasattr(self, 'delete_button'):
                self.delete_button.config(text="Delete Ad")
            if self.unknown_ads:
                if self.current_index >= len(self.unknown_ads):
                    self.current_index = max(0, len(self.unknown_ads) - 1)
                self.show_current_ad()
            else:
                messagebox.showinfo("Complete", "All unknown brands have been reviewed!")
                self.root.quit()
            return

        # Save updated JSON
        try:
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            # If saving fails, still fall through to removing from the queue
            pass

        # Attempt to delete the image file if it exists
        image_path = ad_data.get('image_path')
        if image_path and os.path.exists(image_path):
            try:
                os.remove(image_path)
            except Exception as e:
                print(f"[WARN] Failed to delete image file {image_path}: {e}")

        # Helper to compare header + full product titles list
        def _same_header_and_products(ad_obj):
            if not isinstance(ad_obj, dict):
                return False
            header = (ad_obj.get('header') or '').strip()
            if header != base_header:
                return False
            products = [
                (p.get('title') or '').strip()
                for p in (ad_obj.get('products') or [])
            ]
            return products == base_products

        # Remove from in-memory queue for the primary ad
        del self.unknown_ads[self.current_index]

        # Also delete any other ads in the queue with matching header+products and no image
        extra_indices = []
        for idx, info in enumerate(self.unknown_ads):
            ad_obj = info.get('ad') or {}
            if not _same_header_and_products(ad_obj):
                continue
            img_path = info.get('image_path')
            if img_path and os.path.exists(img_path):
                continue  # has an image; keep it
            extra_indices.append(idx)

        # For each matching extra ad, prune it from its JSON and delete its image if present
        for idx in extra_indices:
            info = self.unknown_ads[idx]
            jf = info.get('json_file')
            if not jf:
                continue
            try:
                with open(jf, 'r', encoding='utf-8') as f:
                    data2 = json.load(f)
            except Exception:
                continue

            removed_any = False

            def _prune_ads_list(ads_list):
                nonlocal removed_any
                if not isinstance(ads_list, list):
                    return
                new_ads = []
                for a in ads_list:
                    if _same_header_and_products(a):
                        removed_any = True
                        continue
                    new_ads.append(a)
                if removed_any:
                    ads_list[:] = new_ads

            if 'ads' in data2 and isinstance(data2['ads'], list):
                _prune_ads_list(data2['ads'])
            elif 'results' in data2:
                for res in data2.get('results', []):
                    _prune_ads_list(res.get('ads', []))

            if removed_any:
                try:
                    with open(jf, 'w', encoding='utf-8') as f:
                        json.dump(data2, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass

            img2 = info.get('image_path')
            if img2 and os.path.exists(img2):
                try:
                    os.remove(img2)
                except Exception as e:
                    print(f"[WARN] Failed to delete image file {img2}: {e}")

        # Remove matching extras from in-memory queue (from highest index down)
        for idx in sorted(extra_indices, reverse=True):
            if 0 <= idx < len(self.unknown_ads):
                del self.unknown_ads[idx]

        # Reset delete state and advance
        self.delete_armed_index = None
        if hasattr(self, 'delete_button'):
            self.delete_button.config(text="Delete Ad")

        if self.unknown_ads:
            if self.current_index >= len(self.unknown_ads):
                self.current_index = max(0, len(self.unknown_ads) - 1)
            self.show_current_ad()
        else:
            messagebox.showinfo("Complete", "All unknown brands have been reviewed!")
            self.root.quit()

    def mark_as_house_ad(self):
        """Mark the current ad as a retailer house ad (Kroger or Walmart)"""
        # Get retailer from current ad's JSON file path
        ad_data = self.unknown_ads[self.current_index]
        json_file = ad_data['json_file']
        target_ad = ad_data.get('ad') or {}
        
        # Determine retailer from path
        retailer = "unknown"  # Default - don't assume Kroger
        if '/walmart/' in json_file:
            retailer = "Walmart"
        elif '/kroger/' in json_file:
            retailer = "Kroger"
        elif '/instacart/' in json_file:
            retailer = "Instacart"
        elif '/target/' in json_file:
            retailer = "Target"
        elif '/amazon/' in json_file:
            retailer = "Amazon"
        
        # Blacklist the message text so this exact house ad won't appear again
        message = target_ad.get('message', '').strip()
        if message:
            message_key = f"MSG:{message}"
            self.add_to_blacklist(message_key)
            print(f"[HOUSE AD] Blacklisted message: '{message[:60]}...'")
        
        # Clear all co-brand fields
        while len(self.brand_entries) > 1:
            self.remove_cobrand_field(1)
        
        # Set first field to retailer name
        self.brand_entries[0].delete(0, tk.END)
        self.brand_entries[0].insert(0, retailer)
        self.save_correction()
    
    def to_slug(self, text):
        """Convert text to slug format with robust normalization"""
        # Lowercase
        s = text.lower()
        # Replace '&' with 'and'
        s = s.replace('&', 'and')
        # Remove apostrophes
        s = s.replace("'", '')
        # Collapse any non-alphanumeric into underscores
        s = re.sub(r'[^a-z0-9]+', '_', s)
        # Collapse multiple underscores
        s = re.sub(r'_+', '_', s).strip('_')
        return s
    
    def next_ad(self):
        """Move to next ad, skipping any retailer house ads"""
        self.current_index += 1
        # Skip any house ads (Kroger, Walmart, Instacart)
        house_ad_brands = {'kroger', 'walmart', 'instacart'}
        while self.current_index < len(self.unknown_ads):
            if self.unknown_ads[self.current_index]['current_brand'].lower() not in house_ad_brands:
                break
            self.current_index += 1
        self.show_current_ad()
    
    def previous_ad(self):
        """Move to previous ad, skipping any retailer house ads"""
        if self.current_index > 0:
            self.current_index -= 1
            # Skip any house ads (Kroger, Walmart, Instacart)
            house_ad_brands = {'kroger', 'walmart', 'instacart'}
            while self.current_index > 0:
                if self.unknown_ads[self.current_index]['current_brand'].lower() not in house_ad_brands:
                    break
                self.current_index -= 1
            self.show_current_ad()

def run_kroger_reconciliation():
    """Run image reconciliation for all Kroger clients before starting brand review"""
    import subprocess
    from pathlib import Path
    
    print("\n" + "="*60)
    print("🔗 Running Kroger Image Reconciliation")
    print("="*60)
    print("This ensures all images are properly linked to JSON files...")
    
    # Find all Kroger clients
    kroger_output = Path("output/kroger")
    if not kroger_output.exists():
        print("⚠️  No Kroger output directory found, skipping reconciliation")
        return
    
    clients = [d.name for d in kroger_output.iterdir() if d.is_dir()]
    
    if not clients:
        print("⚠️  No Kroger clients found, skipping reconciliation")
        return
    
    print(f"📋 Found {len(clients)} Kroger clients")
    
    total_updated = 0
    for client in clients:
        try:
            result = subprocess.run(
                ["python3", "tools/reconcile_kroger_images_to_json.py", "--client", client],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                # Extract summary from output
                for line in result.stdout.split('\n'):
                    if 'Total ads updated:' in line:
                        count = line.split(':')[-1].strip()
                        if count != '0':
                            print(f"  ✅ {client}: {count} ads updated")
                            total_updated += int(count)
                        break
            else:
                print(f"  ⚠️  {client}: reconciliation failed")
                
        except Exception as e:
            print(f"  ⚠️  {client}: {e}")
    
    print(f"\n✅ Reconciliation complete: {total_updated} total ads updated")
    print("="*60 + "\n")

if __name__ == "__main__":
    # Run reconciliation first
    run_kroger_reconciliation()
    
    # Then start the brand review tool
    root = tk.Tk()
    app = BrandReviewTool(root)
    root.mainloop()
