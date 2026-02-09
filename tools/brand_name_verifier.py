#!/usr/bin/env python3
"""
Brand Name Verifier - Review and approve/edit canonical brand names

Shows each brand name and lets you:
- Approve (A): Mark as verified, won't show again
- Edit (E): Change the canonical name, optionally keeping old name as synonym
- Delete (D): Remove brand entirely from lexicon
- Skip (S): Move to next without changes

Keyboard shortcuts: A=Approve, E=Edit, D=Delete, S=Skip, Q=Quit
"""

import json
import sys
import re
from pathlib import Path
from difflib import SequenceMatcher
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from PIL import Image, ImageTk

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.lexicon_utils import save_lexicon

# Paths
LEXICON_PATH = Path("config/brands.json")
BLACKLIST_PATH = Path("config/brand_blacklist.json")
LOGOS_DIR = Path("output/brand_logos")
LOGOS_DB = Path("output/brand_logos/brand_logo_database.json")
OUTPUT_DIR = Path("output")
BRAND_INDEX_PATH = Path("output/brand_index.json")


def load_blacklist():
    """Load the brand blacklist"""
    if BLACKLIST_PATH.exists():
        try:
            return json.loads(BLACKLIST_PATH.read_text())
        except Exception:
            pass
    return {"brands": [], "metadata": {"description": "Brands that should never be added to the lexicon"}}


def save_blacklist(blacklist):
    """Save the brand blacklist"""
    BLACKLIST_PATH.parent.mkdir(exist_ok=True)
    # Sort brands alphabetically
    blacklist["brands"] = sorted(set(blacklist["brands"]), key=str.lower)
    BLACKLIST_PATH.write_text(json.dumps(blacklist, indent=2))


def add_to_blacklist(brand_name):
    """Add a brand to the blacklist"""
    blacklist = load_blacklist()
    normalized = brand_name.strip().lower()
    if normalized not in [b.lower() for b in blacklist["brands"]]:
        blacklist["brands"].append(brand_name.strip())
        save_blacklist(blacklist)
        return True
    return False


def remove_from_blacklist(brand_name):
    """Remove a brand from the blacklist"""
    blacklist = load_blacklist()
    normalized = brand_name.strip().lower()
    original_len = len(blacklist["brands"])
    blacklist["brands"] = [b for b in blacklist["brands"] if b.lower() != normalized]
    if len(blacklist["brands"]) < original_len:
        save_blacklist(blacklist)
        return True
    return False


def is_blacklisted(brand_name):
    """Check if a brand is blacklisted"""
    blacklist = load_blacklist()
    normalized = brand_name.strip().lower()
    return normalized in [b.lower() for b in blacklist["brands"]]


def normalize_for_matching(name):
    """Normalize brand name for fuzzy matching"""
    name = name.lower()
    name = re.sub(r"[^a-z0-9]", "", name)
    return name


def find_similar_brands(brand_name, all_brands, threshold=0.75, max_results=5):
    """Find brands with similar names"""
    normalized = normalize_for_matching(brand_name)
    similarities = []
    
    # Skip very short names (too many false positives)
    if len(normalized) < 3:
        return []
    
    for other in all_brands:
        other_name = other.get("name", "")
        if other_name.lower() == brand_name.lower():
            continue
        
        other_normalized = normalize_for_matching(other_name)
        
        # Skip very short names
        if len(other_normalized) < 3:
            continue
        
        # Calculate similarity on normalized names
        ratio = SequenceMatcher(None, normalized, other_normalized).ratio()
        
        # Boost if one contains the other (likely variant)
        if normalized in other_normalized or other_normalized in normalized:
            ratio = max(ratio, 0.85)
        
        # Boost if they share the same starting characters (likely same brand)
        if len(normalized) >= 4 and len(other_normalized) >= 4:
            if normalized[:4] == other_normalized[:4]:
                ratio = max(ratio, 0.8)
        
        if ratio >= threshold:
            similarities.append((other_name, ratio, other.get("verified", False)))
    
    # Sort by similarity descending
    similarities.sort(key=lambda x: x[1], reverse=True)
    return similarities[:max_results]


def find_synonym_conflicts(brand_name, all_brands):
    """Find brands where this brand name appears as a synonym (conflict)"""
    normalized = normalize_for_matching(brand_name)
    conflicts = []
    
    for other in all_brands:
        other_name = other.get("name", "")
        # Skip self
        if other_name.lower() == brand_name.lower():
            continue
        
        # Check if brand_name is in other's synonyms
        for syn in other.get("synonyms", []):
            syn_normalized = normalize_for_matching(syn)
            if syn_normalized == normalized or syn.lower() == brand_name.lower():
                conflicts.append((other_name, syn, other.get("verified", False)))
                break
    
    return conflicts


def load_logo_database():
    """Load the brand logo database"""
    if LOGOS_DB.exists():
        try:
            return json.loads(LOGOS_DB.read_text())
        except Exception:
            pass
    return {"brands": {}}


def save_logo_database(logo_db):
    """Save the brand logo database"""
    from datetime import datetime, timezone
    logo_db["metadata"] = logo_db.get("metadata", {})
    logo_db["metadata"]["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    logo_db["metadata"]["total_brands"] = len(logo_db.get("brands", {}))
    
    # Sort brands alphabetically
    sorted_brands = dict(sorted(logo_db.get("brands", {}).items(), key=lambda x: x[0].lower()))
    logo_db["brands"] = sorted_brands
    
    LOGOS_DB.write_text(json.dumps(logo_db, indent=2, ensure_ascii=False))


def get_logo_db_key(brand_name):
    """Get the database key for a brand name"""
    return re.sub(r"[^a-z0-9]+", "_", brand_name.lower()).strip("_")


def get_logo_info(brand_name, logo_db):
    """Get logo info (key, data, path) for a brand if it exists"""
    brand_key_underscore = get_logo_db_key(brand_name)
    brand_key_no_space = normalize_for_matching(brand_name)
    
    # Try both key formats
    for brand_key in [brand_key_underscore, brand_key_no_space]:
        brand_data = logo_db.get("brands", {}).get(brand_key)
        if brand_data:
            logo_file = brand_data.get("logo_file", "")
            if logo_file:
                logo_path = LOGOS_DIR / logo_file
                if logo_path.exists():
                    return {"key": brand_key, "data": brand_data, "path": logo_path}
    
    return None


def get_logo_path(brand_name, logo_db):
    """Get logo path for a brand if it exists"""
    # Try multiple key formats since database uses underscores but normalize strips them
    brand_key_no_space = normalize_for_matching(brand_name)  # artesanobread
    brand_key_underscore = re.sub(r"[^a-z0-9]+", "_", brand_name.lower()).strip("_")  # artesano_bread
    
    # Try both key formats
    for brand_key in [brand_key_underscore, brand_key_no_space]:
        brand_data = logo_db.get("brands", {}).get(brand_key)
        if brand_data:
            logo_file = brand_data.get("logo_file", "")
            if logo_file:
                # Handle relative paths
                logo_path = LOGOS_DIR / logo_file
                if logo_path.exists():
                    return logo_path
    
    # Fallback: scan filesystem for logo files with any extension
    extensions = [".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif"]
    
    # Check verified folder first, then unverified
    for folder in ["verified", "unverified", ""]:
        base_dir = LOGOS_DIR / folder if folder else LOGOS_DIR
        if not base_dir.exists():
            continue
        # Try both key formats
        for brand_key in [brand_key_underscore, brand_key_no_space]:
            for ext in extensions:
                logo_path = base_dir / f"{brand_key}{ext}"
                if logo_path.exists():
                    return logo_path
    
    return None


def load_lexicon():
    """Load the brand lexicon"""
    if LEXICON_PATH.exists():
        try:
            return json.loads(LEXICON_PATH.read_text())
        except Exception as e:
            print(f"Error loading lexicon: {e}")
    return []


def load_brand_index():
    """Load the brand index for sample ad lookup, building it if missing"""
    # Check if index exists and is recent (less than 24 hours old)
    needs_rebuild = False
    
    if not BRAND_INDEX_PATH.exists():
        print("⚠️  Brand index not found")
        needs_rebuild = True
    else:
        # Check age
        import time
        age_hours = (time.time() - BRAND_INDEX_PATH.stat().st_mtime) / 3600
        if age_hours > 24:
            print(f"⚠️  Brand index is {age_hours:.1f} hours old")
            needs_rebuild = True
    
    if needs_rebuild:
        print("🔨 Building brand index (this may take 15-30 seconds)...")
        try:
            import subprocess
            result = subprocess.run(
                [sys.executable, "tools/build_brand_index.py"],
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode == 0:
                print("✅ Brand index built successfully")
            else:
                print(f"⚠️  Brand index build had issues: {result.stderr[:200]}")
        except Exception as e:
            print(f"⚠️  Could not build brand index: {e}")
    
    if BRAND_INDEX_PATH.exists():
        try:
            return json.loads(BRAND_INDEX_PATH.read_text())
        except Exception as e:
            print(f"Error loading brand index: {e}")
    
    return {"index": {}}


def get_sample_ad_for_brand(brand_name, brand_index):
    """Get the first sample ad image path for a brand from the index.
    
    Returns tuple of (full_image_path, retailer, ad_type) or (None, None, None) if not found.
    """
    if not brand_index or "index" not in brand_index:
        return None, None, None
    
    # Normalize brand name for lookup (same as build_brand_index.py)
    brand_key = brand_name.strip().lower()
    brand_key = brand_key.replace(".", "")
    brand_key = brand_key.replace("'", "").replace("'", "").replace("`", "")
    brand_key = brand_key.replace(" & ", " and ").replace("&", " and ")
    brand_key = " ".join(brand_key.split())
    
    entries = brand_index.get("index", {}).get(brand_key, [])
    
    for entry in entries:
        sample_image = entry.get("sample_image")
        if sample_image:
            # sample_image is already relative to OUTPUT_DIR (includes retailer/client)
            retailer = entry.get("retailer", "")
            ad_type = entry.get("sample_ad_type", "")
            
            # Build full path: OUTPUT_DIR / sample_image
            full_path = OUTPUT_DIR / sample_image
            if full_path.exists():
                return str(full_path), retailer, ad_type
    
    return None, None, None


def save_lexicon(lexicon):
    """Save the brand lexicon"""
    # Sort alphabetically by name
    lexicon.sort(key=lambda x: x.get("name", "").lower())
    LEXICON_PATH.write_text(json.dumps(lexicon, indent=2, ensure_ascii=False))


class LogoMergeDialog(tk.Toplevel):
    """Dialog to handle logo merging when merging brands"""
    
    def __init__(self, parent, source_name, target_name, source_logo_info, target_logo_info):
        super().__init__(parent)
        self.title("Merge Logos")
        self.geometry("600x400")
        self.transient(parent)
        self.grab_set()
        
        self.result = None  # Will be: "source", "target", "keep_both", or "none"
        self.source_name = source_name
        self.target_name = target_name
        self.source_logo_info = source_logo_info
        self.target_logo_info = target_logo_info
        
        # Keep references to prevent garbage collection
        self.source_photo = None
        self.target_photo = None
        
        self.setup_ui()
        
        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")
    
    def setup_ui(self):
        # Title
        ttk.Label(
            self, 
            text="Choose which logo to keep for the merged brand:",
            font=("Arial", 12, "bold")
        ).pack(pady=10)
        
        # Logos frame
        logos_frame = ttk.Frame(self)
        logos_frame.pack(fill="both", expand=True, padx=20)
        
        # Source logo (left)
        source_frame = ttk.LabelFrame(logos_frame, text=f"From: {self.source_name}", padding=10)
        source_frame.pack(side="left", fill="both", expand=True, padx=5)
        
        source_canvas = tk.Canvas(source_frame, width=200, height=200, bg="white")
        source_canvas.pack()
        
        if self.source_logo_info:
            try:
                img = Image.open(self.source_logo_info["path"])
                img.thumbnail((190, 190), Image.Resampling.LANCZOS)
                self.source_photo = ImageTk.PhotoImage(img)
                source_canvas.create_image(100, 100, image=self.source_photo, anchor="center")
            except Exception:
                source_canvas.create_text(100, 100, text="Error loading", fill="red")
            
            ttk.Button(
                source_frame, 
                text="Use This Logo",
                command=lambda: self.select("source")
            ).pack(pady=10)
        else:
            source_canvas.create_text(100, 100, text="No logo", fill="gray")
        
        # Target logo (right)
        target_frame = ttk.LabelFrame(logos_frame, text=f"To: {self.target_name}", padding=10)
        target_frame.pack(side="right", fill="both", expand=True, padx=5)
        
        target_canvas = tk.Canvas(target_frame, width=200, height=200, bg="white")
        target_canvas.pack()
        
        if self.target_logo_info:
            try:
                img = Image.open(self.target_logo_info["path"])
                img.thumbnail((190, 190), Image.Resampling.LANCZOS)
                self.target_photo = ImageTk.PhotoImage(img)
                target_canvas.create_image(100, 100, image=self.target_photo, anchor="center")
            except Exception:
                target_canvas.create_text(100, 100, text="Error loading", fill="red")
            
            ttk.Button(
                target_frame, 
                text="Use This Logo",
                command=lambda: self.select("target")
            ).pack(pady=10)
        else:
            target_canvas.create_text(100, 100, text="No logo", fill="gray")
        
        # Bottom buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=15)
        
        ttk.Button(
            btn_frame, 
            text="Skip Logo Merge",
            command=lambda: self.select("none")
        ).pack(side="left", padx=10)
        
        ttk.Button(
            btn_frame, 
            text="Cancel Merge",
            command=self.cancel
        ).pack(side="left", padx=10)
    
    def select(self, choice):
        self.result = choice
        self.destroy()
    
    def cancel(self):
        self.result = None
        self.destroy()


def merge_logos(source_name, target_name, logo_db, choice, source_logo_info, target_logo_info):
    """
    Merge logo data when merging brands.
    
    Args:
        source_name: Brand being merged (will be deleted)
        target_name: Brand being merged into (will keep)
        logo_db: The logo database dict
        choice: "source" (use source logo), "target" (keep target logo), or "none" (skip)
        source_logo_info: Logo info dict for source brand
        target_logo_info: Logo info dict for target brand
    
    Returns:
        True if logo database was modified
    """
    if choice == "none":
        return False
    
    target_key = get_logo_db_key(target_name)
    modified = False
    
    if choice == "source" and source_logo_info:
        source_key = source_logo_info["key"]
        source_data = source_logo_info["data"].copy()
        
        # Update brand_name to target
        source_data["brand_name"] = target_name
        
        # If target already has a logo, we're replacing it
        if target_logo_info:
            # Delete old target logo file if different
            old_target_path = target_logo_info["path"]
            new_source_path = source_logo_info["path"]
            if old_target_path != new_source_path and old_target_path.exists():
                try:
                    old_target_path.unlink()
                    print(f"🗑️ Deleted old logo: {old_target_path.name}")
                except Exception as e:
                    print(f"⚠️ Could not delete old logo: {e}")
        
        # Rename source logo file to target key
        source_path = source_logo_info["path"]
        new_filename = f"{target_key}{source_path.suffix}"
        new_path = source_path.parent / new_filename
        
        if source_path != new_path:
            try:
                source_path.rename(new_path)
                # Update logo_file in data
                rel_path = str(new_path.relative_to(LOGOS_DIR))
                source_data["logo_file"] = rel_path
                print(f"📁 Renamed logo: {source_path.name} -> {new_filename}")
            except Exception as e:
                print(f"⚠️ Could not rename logo file: {e}")
        
        # Remove source entry from database
        if source_key in logo_db.get("brands", {}):
            del logo_db["brands"][source_key]
        
        # Add/update target entry
        logo_db["brands"][target_key] = source_data
        modified = True
        print(f"✓ Logo merged: using {source_name}'s logo for {target_name}")
    
    elif choice == "target" and target_logo_info:
        # Keep target logo, just remove source logo entry
        if source_logo_info:
            source_key = source_logo_info["key"]
            if source_key in logo_db.get("brands", {}):
                del logo_db["brands"][source_key]
                modified = True
            
            # Optionally delete source logo file
            source_path = source_logo_info["path"]
            if source_path.exists():
                try:
                    source_path.unlink()
                    print(f"🗑️ Deleted source logo: {source_path.name}")
                except Exception as e:
                    print(f"⚠️ Could not delete source logo: {e}")
        
        print(f"✓ Logo merged: keeping {target_name}'s logo")
    
    elif choice == "source" and source_logo_info and not target_logo_info:
        # Target has no logo, adopt source logo
        source_key = source_logo_info["key"]
        source_data = source_logo_info["data"].copy()
        source_data["brand_name"] = target_name
        
        # Rename source logo file to target key
        source_path = source_logo_info["path"]
        new_filename = f"{target_key}{source_path.suffix}"
        new_path = source_path.parent / new_filename
        
        if source_path != new_path:
            try:
                source_path.rename(new_path)
                rel_path = str(new_path.relative_to(LOGOS_DIR))
                source_data["logo_file"] = rel_path
                print(f"📁 Renamed logo: {source_path.name} -> {new_filename}")
            except Exception as e:
                print(f"⚠️ Could not rename logo file: {e}")
        
        # Remove source entry
        if source_key in logo_db.get("brands", {}):
            del logo_db["brands"][source_key]
        
        # Add target entry
        logo_db["brands"][target_key] = source_data
        modified = True
        print(f"✓ Logo adopted: {target_name} now has {source_name}'s logo")
    
    return modified


class BrandNameVerifier:
    def __init__(self, root):
        self.root = root
        self.root.title("Brand Name Verifier")
        self.root.geometry("1000x800")
        
        # Load lexicon, logo database, and brand index
        self.lexicon = load_lexicon()
        self.logo_db = load_logo_database()
        self.brand_index = load_brand_index()
        
        # Filter to only unverified brands
        self.brands_to_review = [
            (i, brand) for i, brand in enumerate(self.lexicon)
            if not brand.get("verified", False)
        ]
        
        print(f"📊 Found {len(self.brands_to_review)} brands to review")
        print(f"   Already verified: {len(self.lexicon) - len(self.brands_to_review)}")
        
        self.current_index = 0
        self.approved_count = 0
        self.edited_count = 0
        self.deleted_count = 0
        self.skipped_count = 0
        
        # Track deleted indices for proper cleanup
        self.deleted_indices = set()
        
        # Undo stack - stores (action, data) tuples
        self.undo_stack = []
        
        # Setup UI
        self.setup_ui()
        
        # Bind keyboard shortcuts
        self.root.bind('a', lambda e: self.approve_brand())
        self.root.bind('A', lambda e: self.approve_brand())
        self.root.bind('e', lambda e: self.edit_brand())
        self.root.bind('E', lambda e: self.edit_brand())
        self.root.bind('d', lambda e: self.delete_brand())
        self.root.bind('D', lambda e: self.delete_brand())
        self.root.bind('s', lambda e: self.skip_brand())
        self.root.bind('S', lambda e: self.skip_brand())
        self.root.bind('q', lambda e: self.quit_app())
        self.root.bind('Q', lambda e: self.quit_app())
        self.root.bind('z', lambda e: self.undo_action())
        self.root.bind('Z', lambda e: self.undo_action())
        self.root.bind('<Command-z>', lambda e: self.undo_action())
        self.root.bind('<Left>', lambda e: self.prev_brand())
        self.root.bind('<Right>', lambda e: self.skip_brand())
        
        # Show first brand
        if self.brands_to_review:
            self.show_current_brand()
        else:
            self.show_empty_message()
    
    def setup_ui(self):
        """Setup the UI components"""
        # Top frame for progress
        self.progress_label = ttk.Label(
            self.root,
            text="",
            font=("Arial", 12)
        )
        self.progress_label.pack(pady=5)
        
        # Main content frame (horizontal layout)
        content_frame = ttk.Frame(self.root)
        content_frame.pack(fill="both", expand=True, padx=20)
        
        # Left side - Logo and Sample Ads
        left_frame = ttk.Frame(content_frame)
        left_frame.pack(side="left", fill="y", padx=(0, 10))
        
        # Logo section
        logo_frame = ttk.LabelFrame(left_frame, text="Logo", padding=10)
        logo_frame.pack(fill="x")
        
        self.logo_canvas = tk.Canvas(logo_frame, width=150, height=100, bg="white")
        self.logo_canvas.pack()
        
        self.logo_status_label = ttk.Label(logo_frame, text="", font=("Arial", 9))
        self.logo_status_label.pack(pady=5)
        
        # Sample Ad section - shows the actual ad that led to this brand being added
        sample_frame = ttk.LabelFrame(left_frame, text="Sample Ad (from scraper)", padding=10)
        sample_frame.pack(fill="x", pady=(10, 0))
        
        self.sample_ad_canvas = tk.Canvas(sample_frame, width=500, height=300, bg="#f0f0f0", cursor="hand2")
        self.sample_ad_canvas.pack()
        
        # Bind click to show full-size image
        self.sample_ad_canvas.bind("<Button-1>", self.show_fullsize_sample_ad)
        self.current_sample_path = None  # Track current sample image path
        
        self.sample_ad_label = ttk.Label(sample_frame, text="", font=("Arial", 9), wraplength=500)
        self.sample_ad_label.pack(pady=5)
        
        # File path label (clickable to open in Finder)
        self.sample_path_label = ttk.Label(
            sample_frame, 
            text="", 
            font=("Arial", 8), 
            foreground="blue",
            cursor="hand2",
            wraplength=500
        )
        self.sample_path_label.pack(pady=(0, 5))
        self.sample_path_label.bind("<Button-1>", self.open_sample_in_finder)
        
        # Right side - Brand info
        info_frame = ttk.Frame(content_frame)
        info_frame.pack(side="left", fill="both", expand=True)
        
        # Brand name label (large)
        self.brand_label = ttk.Label(
            info_frame,
            text="",
            font=("Arial", 28, "bold")
        )
        self.brand_label.pack(pady=10, anchor="w")
        
        # Synonyms frame
        self.synonyms_frame = ttk.LabelFrame(info_frame, text="Synonyms", padding=10)
        self.synonyms_frame.pack(pady=5, fill="x")
        
        self.synonyms_label = ttk.Label(
            self.synonyms_frame,
            text="",
            font=("Arial", 10),
            wraplength=500,
            justify="left"
        )
        self.synonyms_label.pack(anchor="w")
        
        # Parent company frame
        self.parent_frame = ttk.LabelFrame(info_frame, text="Parent Company", padding=10)
        self.parent_frame.pack(pady=5, fill="x")
        
        self.parent_label = ttk.Label(
            self.parent_frame,
            text="",
            font=("Arial", 10),
            foreground="blue"
        )
        self.parent_label.pack(anchor="w")
        
        # Conflict frame (brand exists as synonym elsewhere) - RED warning
        self.conflict_frame = ttk.LabelFrame(info_frame, text="⚠️ CONFLICT: This brand is a synonym of another!", padding=10)
        self.conflict_buttons_frame = ttk.Frame(self.conflict_frame)
        self.conflict_buttons_frame.pack(anchor="w")
        
        # Similar brands frame
        self.similar_frame = ttk.LabelFrame(info_frame, text="Similar Brands (click to merge)", padding=10)
        self.similar_frame.pack(pady=5, fill="x")
        
        self.similar_buttons_frame = ttk.Frame(self.similar_frame)
        self.similar_buttons_frame.pack(anchor="w")
        
        self.no_similar_label = ttk.Label(self.similar_frame, text="(none found)", font=("Arial", 10))
        
        # Shorter name alternatives frame (for multi-word brands)
        self.shorter_frame = ttk.LabelFrame(info_frame, text="Shorter Names (click to rename)", padding=10)
        self.shorter_buttons_frame = ttk.Frame(self.shorter_frame)
        self.shorter_buttons_frame.pack(anchor="w")
        
        # Stats frame
        stats_frame = ttk.Frame(info_frame)
        stats_frame.pack(pady=10)
        
        self.stats_label = ttk.Label(
            stats_frame,
            text="",
            font=("Arial", 10)
        )
        self.stats_label.pack()
        
        # Button frame
        button_frame = ttk.Frame(self.root)
        button_frame.pack(pady=10)
        
        # Approve button
        self.approve_btn = ttk.Button(
            button_frame,
            text="✓ Approve (A)",
            command=self.approve_brand,
            width=15
        )
        self.approve_btn.pack(side="left", padx=10)
        
        # Edit button
        self.edit_btn = ttk.Button(
            button_frame,
            text="✎ Edit (E)",
            command=self.edit_brand,
            width=15
        )
        self.edit_btn.pack(side="left", padx=10)
        
        # Delete button
        self.delete_btn = ttk.Button(
            button_frame,
            text="✗ Delete (D)",
            command=self.delete_brand,
            width=15
        )
        self.delete_btn.pack(side="left", padx=10)
        
        # Skip button
        self.skip_btn = ttk.Button(
            button_frame,
            text="→ Skip (S)",
            command=self.skip_brand,
            width=15
        )
        self.skip_btn.pack(side="left", padx=10)
        
        # Navigation frame
        nav_frame = ttk.Frame(self.root)
        nav_frame.pack(pady=5)
        
        self.prev_btn = ttk.Button(
            nav_frame,
            text="← Previous",
            command=self.prev_brand,
            width=12
        )
        self.prev_btn.pack(side="left", padx=10)
        
        self.undo_btn = ttk.Button(
            nav_frame,
            text="↩ Undo (Z)",
            command=self.undo_action,
            width=12
        )
        self.undo_btn.pack(side="left", padx=10)
        
        self.quit_btn = ttk.Button(
            nav_frame,
            text="Quit (Q)",
            command=self.quit_app,
            width=12
        )
        self.quit_btn.pack(side="left", padx=10)
        
        # Blacklist button
        self.blacklist_btn = ttk.Button(
            nav_frame,
            text="📋 Blacklist",
            command=self.show_blacklist_editor,
            width=12
        )
        self.blacklist_btn.pack(side="left", padx=10)
    
    def show_current_brand(self):
        """Display the current brand"""
        if self.current_index >= len(self.brands_to_review):
            self.show_complete_message()
            return
        
        lexicon_idx, brand = self.brands_to_review[self.current_index]
        brand_name = brand.get("name", "Unknown")
        synonyms = brand.get("synonyms", [])
        
        # Update progress
        self.progress_label.config(
            text=f"Brand {self.current_index + 1} of {len(self.brands_to_review)}"
        )
        
        # Update brand name
        self.brand_label.config(text=brand_name)
        
        # Update logo
        self.show_logo(brand_name)
        
        # Update sample ad from brand index
        self.show_sample_ad(brand_name)
        
        # Update synonyms
        if synonyms:
            syn_text = "\n".join(f"• {s}" for s in synonyms[:10])
            if len(synonyms) > 10:
                syn_text += f"\n... and {len(synonyms) - 10} more"
            self.synonyms_label.config(text=syn_text)
        else:
            self.synonyms_label.config(text="(none)")
        
        # Update parent company
        try:
            from core.brands import get_parent_company
            parent = get_parent_company(brand_name)
            if parent:
                self.parent_label.config(text=f"🏢 {parent['name']}")
            else:
                self.parent_label.config(text="(not assigned)")
        except Exception:
            self.parent_label.config(text="(not assigned)")
        
        # Check for conflicts (this brand name is a synonym of another brand)
        self.show_conflicts(brand_name)
        
        # Update similar brands
        self.show_similar_brands(brand_name)
        
        # Show shorter name alternatives for multi-word brands
        self.show_shorter_names(brand_name)
        
        # Update stats
        self.stats_label.config(
            text=f"Approved: {self.approved_count} | Edited: {self.edited_count} | "
                 f"Deleted: {self.deleted_count} | Skipped: {self.skipped_count}"
        )
    
    def show_logo(self, brand_name):
        """Display the logo for the brand if available"""
        self.logo_canvas.delete("all")
        self.current_logo_image = None  # Keep reference to prevent garbage collection
        
        logo_path = get_logo_path(brand_name, self.logo_db)
        
        if logo_path:
            try:
                img = Image.open(logo_path)
                # Resize to fit canvas while maintaining aspect ratio
                img.thumbnail((190, 190), Image.Resampling.LANCZOS)
                self.current_logo_image = ImageTk.PhotoImage(img)
                
                # Center image on canvas
                x = 100
                y = 100
                self.logo_canvas.create_image(x, y, image=self.current_logo_image, anchor="center")
                
                # Show status
                is_verified = "verified" in str(logo_path)
                status = "✓ Verified" if is_verified else "⚠ Unverified"
                self.logo_status_label.config(text=status)
            except Exception as e:
                self.logo_canvas.create_text(100, 100, text="Error loading", fill="red")
                self.logo_status_label.config(text=str(e)[:30])
        else:
            self.logo_canvas.create_text(100, 75, text="No logo", fill="gray")
            self.logo_status_label.config(text="")
    
    def show_sample_ad(self, brand_name):
        """Display a sample ad from the brand index"""
        self.sample_ad_canvas.delete("all")
        self.current_sample_image = None  # Keep reference to prevent garbage collection
        
        sample_path, retailer, ad_type = get_sample_ad_for_brand(brand_name, self.brand_index)
        
        if sample_path:
            try:
                img = Image.open(sample_path)
                
                # Handle RGBA images - composite onto gray background
                if img.mode == 'RGBA':
                    bg = Image.new('RGB', img.size, (240, 240, 240))
                    bg.paste(img, mask=img.split()[3])
                    img = bg
                elif img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Store the full path for click handler
                self.current_sample_path = sample_path
                
                # Resize to fit canvas while maintaining aspect ratio
                img.thumbnail((580, 430), Image.Resampling.LANCZOS)
                self.current_sample_image = ImageTk.PhotoImage(img)
                
                # Center image on canvas
                self.sample_ad_canvas.create_image(300, 225, image=self.current_sample_image, anchor="center")
                
                # Show info
                info = f"{retailer} • {ad_type}" if retailer and ad_type else "Sample ad"
                self.sample_ad_label.config(text=info)
                
                # Show file path (clickable)
                self.sample_path_label.config(text=f"📁 {sample_path}")
            except Exception as e:
                self.sample_ad_canvas.create_text(300, 225, text="Error loading", fill="red")
                self.sample_ad_label.config(text=str(e)[:40])
                self.sample_path_label.config(text="")
                self.current_sample_path = None
        else:
            self.sample_ad_canvas.create_text(300, 225, text="No sample ad\nin brand index", fill="gray", justify="center")
            self.sample_ad_label.config(text="Run: python3 tools/build_brand_index.py")
            self.sample_path_label.config(text="")
            self.current_sample_path = None
    
    def open_sample_in_finder(self, event=None):
        """Open the sample ad file location in Finder"""
        if not self.current_sample_path:
            return
        
        try:
            import subprocess
            import os
            
            # Get the directory containing the file
            file_path = os.path.abspath(self.current_sample_path)
            
            if os.path.exists(file_path):
                # Open Finder and select the file
                subprocess.run(["open", "-R", file_path])
            else:
                print(f"File not found: {file_path}")
        except Exception as e:
            print(f"Error opening in Finder: {e}")
    
    def show_fullsize_sample_ad(self, event=None):
        """Show full-size sample ad in a popup window"""
        if not self.current_sample_path:
            return
        
        try:
            # Create popup window
            popup = tk.Toplevel(self.root)
            popup.title("Sample Ad - Full Size")
            
            # Load full-size image
            img = Image.open(self.current_sample_path)
            
            # Handle RGBA images
            if img.mode == 'RGBA':
                bg = Image.new('RGB', img.size, (240, 240, 240))
                bg.paste(img, mask=img.split()[3])
                img = bg
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Get screen dimensions
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            
            # Scale image if larger than 90% of screen
            max_width = int(screen_width * 0.9)
            max_height = int(screen_height * 0.9)
            
            if img.width > max_width or img.height > max_height:
                img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
            
            photo = ImageTk.PhotoImage(img)
            
            # Create canvas and display image
            canvas = tk.Canvas(popup, width=img.width, height=img.height)
            canvas.pack()
            canvas.create_image(0, 0, anchor="nw", image=photo)
            
            # Keep reference to prevent garbage collection
            canvas.image = photo
            
            # Center popup on screen
            popup.update_idletasks()
            x = (screen_width - popup.winfo_width()) // 2
            y = (screen_height - popup.winfo_height()) // 2
            popup.geometry(f"+{x}+{y}")
            
            # Close on click or Escape
            popup.bind("<Button-1>", lambda e: popup.destroy())
            popup.bind("<Escape>", lambda e: popup.destroy())
            
        except Exception as e:
            print(f"Error showing full-size image: {e}")
    
    def show_conflicts(self, brand_name):
        """Show conflicts where this brand name is a synonym of another brand"""
        # Clear existing buttons
        for widget in self.conflict_buttons_frame.winfo_children():
            widget.destroy()
        
        # Find conflicts
        conflicts = find_synonym_conflicts(brand_name, self.lexicon)
        
        if conflicts:
            # Show the conflict frame
            self.conflict_frame.pack(pady=5, fill="x", before=self.similar_frame)
            
            # Add label explaining the conflict
            for parent_name, matched_syn, is_verified in conflicts:
                verified_mark = " ✓" if is_verified else ""
                
                # Frame for each conflict
                conflict_row = ttk.Frame(self.conflict_buttons_frame)
                conflict_row.pack(anchor="w", pady=2)
                
                ttk.Label(
                    conflict_row,
                    text=f"'{brand_name}' is a synonym of: ",
                    font=("Arial", 10)
                ).pack(side="left")
                
                # Button to merge into the parent brand
                btn = ttk.Button(
                    conflict_row,
                    text=f"Merge into {parent_name}{verified_mark}",
                    command=lambda n=parent_name: self.merge_into_brand(n)
                )
                btn.pack(side="left", padx=5)
                
                # Button to keep this as separate brand (remove from parent's synonyms)
                keep_btn = ttk.Button(
                    conflict_row,
                    text=f"Keep separate (remove from {parent_name})",
                    command=lambda n=parent_name, s=matched_syn: self.remove_synonym_from_brand(n, s)
                )
                keep_btn.pack(side="left", padx=5)
        else:
            # Hide the conflict frame
            self.conflict_frame.pack_forget()
    
    def remove_synonym_from_brand(self, parent_name, synonym):
        """Remove a synonym from a parent brand (to resolve conflict)"""
        parent = next((b for b in self.lexicon if b.get("name") == parent_name), None)
        if parent and synonym in parent.get("synonyms", []):
            parent["synonyms"].remove(synonym)
            save_lexicon(self.lexicon)
            
            # Refresh display
            lexicon_idx, brand = self.brands_to_review[self.current_index]
            self.show_conflicts(brand.get("name", ""))
            messagebox.showinfo("Resolved", f"Removed '{synonym}' from {parent_name}'s synonyms.")
    
    def show_similar_brands(self, brand_name):
        """Show similar brand suggestions"""
        # Clear existing buttons
        for widget in self.similar_buttons_frame.winfo_children():
            widget.destroy()
        self.no_similar_label.pack_forget()
        
        # Find similar brands
        similar = find_similar_brands(brand_name, self.lexicon)
        
        if similar:
            for other_name, ratio, is_verified in similar:
                # Create button for each similar brand
                verified_mark = " ✓" if is_verified else ""
                btn_text = f"{other_name}{verified_mark} ({ratio:.0%})"
                btn = ttk.Button(
                    self.similar_buttons_frame,
                    text=btn_text,
                    command=lambda n=other_name: self.merge_into_brand(n)
                )
                btn.pack(side="left", padx=2, pady=2)
        else:
            self.no_similar_label.pack(anchor="w")
    
    def show_shorter_names(self, brand_name):
        """Show clickable shorter name alternatives for multi-word brands.
        
        For 'Seed Prebiotic And', shows buttons: 'Seed Prebiotic' and 'Seed'
        Clicking renames the brand and keeps the old name as a synonym.
        """
        # Clear existing buttons
        for widget in self.shorter_buttons_frame.winfo_children():
            widget.destroy()
        
        words = brand_name.split()
        if len(words) <= 1:
            # Single-word brand — hide the frame
            self.shorter_frame.pack_forget()
            return
        
        # Show the frame (between similar brands and stats)
        self.shorter_frame.pack(pady=5, fill="x", after=self.similar_frame)
        
        # Generate shorter alternatives: N-1 words, N-2 words, ..., 1 word
        for n in range(len(words) - 1, 0, -1):
            shorter = " ".join(words[:n])
            btn = ttk.Button(
                self.shorter_buttons_frame,
                text=shorter,
                command=lambda s=shorter: self.rename_brand_to(s)
            )
            btn.pack(side="left", padx=2, pady=2)
    
    def rename_brand_to(self, new_name):
        """Rename the current brand, keeping the old name as a synonym."""
        if self.current_index >= len(self.brands_to_review):
            return
        
        lexicon_idx, brand = self.brands_to_review[self.current_index]
        old_name = brand.get("name", "")
        
        if old_name == new_name:
            return
        
        # Check if new_name already exists in lexicon
        existing = next((b for b in self.lexicon if b.get("name", "").lower() == new_name.lower()), None)
        
        if existing:
            # Merge into existing brand: add old name as synonym
            if old_name not in existing.get("synonyms", []):
                existing.setdefault("synonyms", []).append(old_name)
            # Move any synonyms from current brand to existing
            for syn in brand.get("synonyms", []):
                if syn not in existing.get("synonyms", []):
                    existing.setdefault("synonyms", []).append(syn)
            existing["verified"] = True
            # Remove the current brand entry
            self.lexicon.pop(lexicon_idx)
            print(f"[VERIFIER] Merged '{old_name}' into existing '{new_name}'")
        else:
            # Rename: update the brand entry, keep old name as synonym
            brand["name"] = new_name
            if old_name not in brand.get("synonyms", []):
                brand.setdefault("synonyms", []).append(old_name)
            brand["verified"] = True
            print(f"[VERIFIER] Renamed '{old_name}' -> '{new_name}' (old name kept as synonym)")
        
        self.edited_count += 1
        save_lexicon(self.lexicon)
        
        self.rebuild_review_list()
        self.show_current_brand()
    
    def merge_into_brand(self, target_name):
        """Merge current brand into an existing brand"""
        if self.current_index >= len(self.brands_to_review):
            return
        
        lexicon_idx, brand = self.brands_to_review[self.current_index]
        current_name = brand.get("name", "")
        
        # Check for logos on both brands
        source_logo_info = get_logo_info(current_name, self.logo_db)
        target_logo_info = get_logo_info(target_name, self.logo_db)
        
        # Determine if we need to show logo merge dialog
        logo_choice = None
        if source_logo_info and target_logo_info:
            # Both have logos - show dialog to choose
            dialog = LogoMergeDialog(
                self.root, 
                current_name, 
                target_name, 
                source_logo_info, 
                target_logo_info
            )
            self.root.wait_window(dialog)
            
            if dialog.result is None:
                # User cancelled the merge
                return
            logo_choice = dialog.result
            
        elif source_logo_info and not target_logo_info:
            # Only source has logo - ask if they want to adopt it
            if messagebox.askyesno(
                "Adopt Logo?",
                f"'{current_name}' has a logo but '{target_name}' does not.\n\n"
                f"Would you like to use '{current_name}'s logo for '{target_name}'?"
            ):
                logo_choice = "source"
            else:
                logo_choice = "none"
        
        # Now confirm the merge
        if messagebox.askyesno("Confirm Merge", 
                               f"Merge '{current_name}' into '{target_name}'?\n\n"
                               f"'{current_name}' will be added as a synonym of '{target_name}'.\n"
                               f"All ads labeled '{current_name}' will be relabeled to '{target_name}'."):
            # Find target brand
            target = next((b for b in self.lexicon if b.get("name") == target_name), None)
            
            if target:
                # Add current name as synonym
                if current_name not in target.get("synonyms", []):
                    target.setdefault("synonyms", []).append(current_name)
                
                # Move synonyms to target
                for syn in brand.get("synonyms", []):
                    if syn not in target.get("synonyms", []):
                        target["synonyms"].append(syn)
                
                # Mark current for deletion and apply immediately
                self.deleted_indices.add(lexicon_idx)
                self.lexicon = [b for i, b in enumerate(self.lexicon) if i not in self.deleted_indices]
                self.deleted_indices.clear()  # Clear after applying to prevent stale indices
                self.edited_count += 1
                
                save_lexicon(self.lexicon)
                
                # Handle logo merging
                if logo_choice and logo_choice != "none":
                    if merge_logos(current_name, target_name, self.logo_db, logo_choice, 
                                   source_logo_info, target_logo_info):
                        save_logo_database(self.logo_db)
                elif source_logo_info and not target_logo_info and logo_choice is None:
                    # Edge case: source has logo, target doesn't, and we haven't asked yet
                    # This shouldn't happen with the flow above, but handle it just in case
                    pass
                
                # Re-canonicalize ads in background thread to prevent UI freeze
                def recanon_merge_in_background():
                    try:
                        from tools.recanon_ads import recanon_brand
                        print(f"[RECANON] Changing '{current_name}' ads to '{target_name}'...")
                        recanon_brand(old_brand=current_name, new_brand=target_name)
                        print(f"[RECANON] Complete for '{current_name}' -> '{target_name}'")
                    except Exception as e:
                        print(f"[WARN] Failed to recanon ads: {e}")
                
                import threading
                thread = threading.Thread(target=recanon_merge_in_background, daemon=True)
                thread.start()
                
                # Rebuild list (brand was merged/deleted)
                self.rebuild_review_list()
                self.show_current_brand()
    
    def show_empty_message(self):
        """Show message when no brands to review"""
        self.progress_label.config(text="")
        self.brand_label.config(text="✓ All brands verified!")
        self.synonyms_label.config(text="No brands need review.")
        self.logo_canvas.delete("all")
        self.logo_canvas.create_text(100, 100, text="🎉", font=("Arial", 48))
        self.logo_status_label.config(text="")
        
        # Clear similar brands
        for widget in self.similar_buttons_frame.winfo_children():
            widget.destroy()
        
        for btn in [self.approve_btn, self.edit_btn, self.delete_btn, self.skip_btn, self.prev_btn]:
            btn.config(state="disabled")
    
    def show_complete_message(self):
        """Show completion message"""
        self.progress_label.config(text="Review Complete!")
        self.brand_label.config(text="✓ Done!")
        self.synonyms_label.config(
            text=f"Approved: {self.approved_count}\n"
                 f"Edited: {self.edited_count}\n"
                 f"Deleted: {self.deleted_count}\n"
                 f"Skipped: {self.skipped_count}"
        )
        
        for btn in [self.approve_btn, self.edit_btn, self.delete_btn, self.skip_btn]:
            btn.config(state="disabled")
    
    def rebuild_review_list(self):
        """Rebuild the brands_to_review list after modifications"""
        # Get current brand name before rebuilding (to find new position)
        current_brand_name = None
        if self.current_index < len(self.brands_to_review):
            _, brand = self.brands_to_review[self.current_index]
            current_brand_name = brand.get("name")
        
        # Rebuild list
        self.brands_to_review = [
            (i, b) for i, b in enumerate(self.lexicon)
            if not b.get("verified", False)
        ]
        
        # Try to find the next unverified brand after current position
        # (don't reset to 0, continue from where we were)
        if self.current_index >= len(self.brands_to_review):
            self.current_index = len(self.brands_to_review)  # Will show complete message
    
    def approve_brand(self):
        """Approve the current brand name"""
        if self.current_index >= len(self.brands_to_review):
            return
        
        lexicon_idx, brand = self.brands_to_review[self.current_index]
        brand["verified"] = True
        self.approved_count += 1
        
        save_lexicon(self.lexicon)
        
        # Rebuild list and advance (the approved brand is now gone from list)
        self.rebuild_review_list()
        # Don't increment - the list shifted, current_index now points to next unverified
        self.show_current_brand()
    
    def edit_brand(self):
        """Edit the current brand name"""
        if self.current_index >= len(self.brands_to_review):
            return
        
        lexicon_idx, brand = self.brands_to_review[self.current_index]
        old_name = brand.get("name", "")
        
        # Create edit dialog
        dialog = EditBrandDialog(self.root, old_name, brand.get("synonyms", []))
        self.root.wait_window(dialog.top)
        
        if dialog.result:
            new_name, keep_as_synonym, delete_synonyms = dialog.result
            should_recanon = False
            recanon_target = None
            
            if new_name and new_name != old_name:
                # Check if new name is blacklisted
                from core.brands import is_blacklisted
                if is_blacklisted(new_name):
                    response = messagebox.askyesno(
                        "Blacklisted Brand Warning",
                        f"'{new_name}' is in the brand blacklist.\n\n"
                        f"Blacklisted brands are filtered from the frontend.\n"
                        f"This is typically used for retailer house ads.\n\n"
                        f"Continue anyway?"
                    )
                    if not response:
                        return
                
                # Check if new name already exists
                existing = next((b for b in self.lexicon if b.get("name", "").lower() == new_name.lower()), None)
                
                if existing and existing != brand:
                    # Check for logos before merging
                    source_logo_info = get_logo_info(old_name, self.logo_db)
                    target_logo_info = get_logo_info(new_name, self.logo_db)
                    
                    logo_choice = None
                    if source_logo_info and target_logo_info:
                        # Both have logos - show dialog to choose
                        dialog = LogoMergeDialog(
                            self.root, 
                            old_name, 
                            new_name, 
                            source_logo_info, 
                            target_logo_info
                        )
                        self.root.wait_window(dialog)
                        
                        if dialog.result is None:
                            # User cancelled
                            return
                        logo_choice = dialog.result
                        
                    elif source_logo_info and not target_logo_info:
                        # Only source has logo - ask if they want to adopt it
                        if messagebox.askyesno(
                            "Adopt Logo?",
                            f"'{old_name}' has a logo but '{new_name}' does not.\n\n"
                            f"Would you like to use '{old_name}'s logo for '{new_name}'?"
                        ):
                            logo_choice = "source"
                        else:
                            logo_choice = "none"
                    
                    # Merge into existing brand
                    if keep_as_synonym:
                        if old_name not in existing.get("synonyms", []):
                            existing.setdefault("synonyms", []).append(old_name)
                    
                    # Move non-deleted synonyms to existing brand
                    for syn in brand.get("synonyms", []):
                        if syn not in delete_synonyms and syn not in existing.get("synonyms", []):
                            existing.setdefault("synonyms", []).append(syn)
                    
                    existing["verified"] = True
                    
                    # Handle logo merging
                    if logo_choice and logo_choice != "none":
                        if merge_logos(old_name, new_name, self.logo_db, logo_choice, 
                                       source_logo_info, target_logo_info):
                            save_logo_database(self.logo_db)
                    
                    # Mark for deletion
                    self.deleted_indices.add(lexicon_idx)
                    should_recanon = True
                    recanon_target = new_name
                    messagebox.showinfo("Merged", f"Merged '{old_name}' into existing '{new_name}'")
                else:
                    # Rename brand
                    brand["name"] = new_name
                    
                    if keep_as_synonym:
                        brand.setdefault("synonyms", []).append(old_name)
                    
                    # Remove deleted synonyms
                    brand["synonyms"] = [s for s in brand.get("synonyms", []) if s not in delete_synonyms]
                    brand["verified"] = True
                    should_recanon = True
                    recanon_target = new_name
                
                self.edited_count += 1
            else:
                # Just remove deleted synonyms and approve
                brand["synonyms"] = [s for s in brand.get("synonyms", []) if s not in delete_synonyms]
                brand["verified"] = True
                self.approved_count += 1
            
            # Clean up deleted brands (only if there are any to delete)
            if self.deleted_indices:
                self.lexicon = [b for i, b in enumerate(self.lexicon) if i not in self.deleted_indices]
                self.deleted_indices.clear()  # Clear after applying to prevent stale indices
            
            save_lexicon(self.lexicon)
            
            # Re-canonicalize ads in background thread to prevent UI freeze
            if should_recanon and recanon_target:
                def recanon_edit_in_background():
                    try:
                        from tools.recanon_ads import recanon_brand
                        print(f"[RECANON] Changing '{old_name}' ads to '{recanon_target}'...")
                        recanon_brand(old_brand=old_name, new_brand=recanon_target)
                        print(f"[RECANON] Complete for '{old_name}' -> '{recanon_target}'")
                    except Exception as e:
                        print(f"[WARN] Failed to recanon ads: {e}")
                
                import threading
                thread = threading.Thread(target=recanon_edit_in_background, daemon=True)
                thread.start()
            
            # Rebuild list (brand was verified/merged/deleted)
            self.rebuild_review_list()
            self.show_current_brand()
    
    def delete_brand(self):
        """Delete the current brand from lexicon and add to blacklist"""
        if self.current_index >= len(self.brands_to_review):
            return
        
        lexicon_idx, brand = self.brands_to_review[self.current_index]
        brand_name = brand.get("name", "")
        brand_copy = dict(brand)  # Copy for undo
        
        # Save to undo stack
        self.undo_stack.append(("delete", {
            "brand": brand_copy,
            "index": self.current_index
        }))
        
        # Add to blacklist (prevents re-adding from scraped data)
        add_to_blacklist(brand_name)
        # Also blacklist synonyms
        for syn in brand.get("synonyms", []):
            add_to_blacklist(syn)
        
        # Remove from lexicon
        self.lexicon = [b for b in self.lexicon if b.get("name") != brand_name]
        self.deleted_count += 1
        
        save_lexicon(self.lexicon)
        
        # Re-canonicalize ads in background thread to prevent UI freeze
        def recanon_in_background():
            try:
                from tools.recanon_ads import recanon_brand
                print(f"[RECANON] Changing '{brand_name}' ads to 'unknown'...")
                recanon_brand(old_brand=brand_name, delete=True)
                print(f"[RECANON] Complete for '{brand_name}'")
            except Exception as e:
                print(f"[WARN] Failed to recanon ads: {e}")
        
        import threading
        thread = threading.Thread(target=recanon_in_background, daemon=True)
        thread.start()
        
        print(f"[BLACKLIST] Added '{brand_name}' to blacklist")
        
        # Rebuild list (brand was deleted)
        self.rebuild_review_list()
        self.show_current_brand()
    
    def skip_brand(self):
        """Skip to next brand without changes"""
        if self.current_index >= len(self.brands_to_review):
            return
        
        self.skipped_count += 1
        self.current_index += 1
        self.show_current_brand()
    
    def undo_action(self):
        """Undo the last action"""
        if not self.undo_stack:
            return
        
        action, data = self.undo_stack.pop()
        
        if action == "delete":
            # Restore deleted brand
            brand = data["brand"]
            self.lexicon.append(brand)
            self.deleted_count -= 1
            
            # Remove from blacklist
            brand_name = brand.get("name", "")
            remove_from_blacklist(brand_name)
            for syn in brand.get("synonyms", []):
                remove_from_blacklist(syn)
            print(f"[BLACKLIST] Removed '{brand_name}' from blacklist (undo)")
            
            save_lexicon(self.lexicon)
            
            # Rebuild and find restored brand
            self.rebuild_review_list()
            
            # Go to the restored brand
            for i, (_, b) in enumerate(self.brands_to_review):
                if b.get("name") == brand.get("name"):
                    self.current_index = i
                    break
            
            self.show_current_brand()
    
    def prev_brand(self):
        """Go to previous brand"""
        if self.current_index > 0:
            self.current_index -= 1
            self.show_current_brand()
    
    def quit_app(self):
        """Save and quit"""
        # Clean up any pending deletions
        self.lexicon = [b for i, b in enumerate(self.lexicon) if i not in self.deleted_indices]
        save_lexicon(self.lexicon)
        
        print(f"\n📊 Session Summary:")
        print(f"   Approved: {self.approved_count}")
        print(f"   Edited: {self.edited_count}")
        print(f"   Deleted: {self.deleted_count}")
        print(f"   Skipped: {self.skipped_count}")
        
        self.root.destroy()
    
    def show_blacklist_editor(self):
        """Show the blacklist editor dialog"""
        dialog = BlacklistEditorDialog(self.root)
        self.root.wait_window(dialog.top)


class BlacklistEditorDialog:
    """Dialog for viewing and editing the brand blacklist"""
    
    def __init__(self, parent):
        self.top = tk.Toplevel(parent)
        self.top.title("Brand Blacklist Editor")
        self.top.geometry("500x600")
        self.top.transient(parent)
        self.top.grab_set()
        
        # Center on parent
        self.top.geometry(f"+{parent.winfo_x() + 50}+{parent.winfo_y() + 50}")
        
        # Title
        ttk.Label(
            self.top, 
            text="Brand Blacklist", 
            font=("Arial", 16, "bold")
        ).pack(pady=10)
        
        ttk.Label(
            self.top, 
            text="Brands on this list will never be auto-added to the lexicon.",
            font=("Arial", 10)
        ).pack(pady=(0, 10))
        
        # Listbox with scrollbar
        list_frame = ttk.Frame(self.top)
        list_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")
        
        self.listbox = tk.Listbox(
            list_frame, 
            font=("Arial", 12),
            yscrollcommand=scrollbar.set,
            selectmode=tk.EXTENDED
        )
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.listbox.yview)
        
        # Button frame
        btn_frame = ttk.Frame(self.top)
        btn_frame.pack(pady=10)
        
        ttk.Button(
            btn_frame,
            text="Add Brand",
            command=self.add_brand,
            width=15
        ).pack(side="left", padx=5)
        
        ttk.Button(
            btn_frame,
            text="Remove Selected",
            command=self.remove_selected,
            width=15
        ).pack(side="left", padx=5)
        
        ttk.Button(
            btn_frame,
            text="Close",
            command=self.top.destroy,
            width=15
        ).pack(side="left", padx=5)
        
        # Count label (must be created before refresh_list)
        self.count_label = ttk.Label(self.top, text="", font=("Arial", 10))
        self.count_label.pack(pady=5)
        
        # Load blacklist (after count_label is created)
        self.refresh_list()
    
    def refresh_list(self):
        """Refresh the listbox from blacklist file"""
        self.listbox.delete(0, tk.END)
        blacklist = load_blacklist()
        for brand in sorted(blacklist["brands"], key=str.lower):
            self.listbox.insert(tk.END, brand)
        self.update_count()
    
    def update_count(self):
        """Update the count label"""
        count = self.listbox.size()
        self.count_label.config(text=f"{count} brands blacklisted")
    
    def add_brand(self):
        """Add a brand to the blacklist"""
        brand = simpledialog.askstring(
            "Add to Blacklist",
            "Enter brand name to blacklist:",
            parent=self.top
        )
        if brand and brand.strip():
            if add_to_blacklist(brand.strip()):
                self.refresh_list()
            else:
                messagebox.showinfo("Already Exists", f"'{brand}' is already blacklisted.")
    
    def remove_selected(self):
        """Remove selected brands from blacklist"""
        selected = self.listbox.curselection()
        if not selected:
            return
        
        brands_to_remove = [self.listbox.get(i) for i in selected]
        
        for brand in brands_to_remove:
            remove_from_blacklist(brand)
        
        self.refresh_list()


class EditBrandDialog:
    """Dialog for editing a brand name"""
    
    def __init__(self, parent, current_name, synonyms):
        self.result = None
        self.current_name = current_name
        self.synonyms = synonyms
        self.synonym_vars = {}
        
        self.top = tk.Toplevel(parent)
        self.top.title("Edit Brand Name")
        self.top.geometry("500x400")
        self.top.transient(parent)
        self.top.grab_set()
        
        # Center on parent
        self.top.geometry(f"+{parent.winfo_x() + 100}+{parent.winfo_y() + 100}")
        
        # Current name label
        ttk.Label(self.top, text="Current name:", font=("Arial", 10)).pack(pady=(20, 5), anchor="w", padx=20)
        ttk.Label(self.top, text=current_name, font=("Arial", 14, "bold")).pack(anchor="w", padx=20)
        
        # New name entry
        ttk.Label(self.top, text="New name:", font=("Arial", 10)).pack(pady=(20, 5), anchor="w", padx=20)
        self.name_entry = ttk.Entry(self.top, width=40, font=("Arial", 14))
        self.name_entry.insert(0, current_name)
        self.name_entry.pack(padx=20, anchor="w")
        self.name_entry.select_range(0, tk.END)
        self.name_entry.focus()
        
        # Keep as synonym checkbox
        self.keep_synonym_var = tk.BooleanVar(value=True)
        self.keep_checkbox = ttk.Checkbutton(
            self.top,
            text=f"Keep '{current_name}' as synonym of new name",
            variable=self.keep_synonym_var
        )
        self.keep_checkbox.pack(pady=10, anchor="w", padx=20)
        
        # Synonyms to delete
        if synonyms:
            syn_frame = ttk.LabelFrame(self.top, text="Synonyms (uncheck to delete)", padding=10)
            syn_frame.pack(pady=10, fill="x", padx=20)
            
            # Scrollable frame for synonyms
            canvas = tk.Canvas(syn_frame, height=100)
            scrollbar = ttk.Scrollbar(syn_frame, orient="vertical", command=canvas.yview)
            scrollable_frame = ttk.Frame(canvas)
            
            scrollable_frame.bind(
                "<Configure>",
                lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
            )
            
            canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)
            
            for syn in synonyms:
                var = tk.BooleanVar(value=True)
                self.synonym_vars[syn] = var
                cb = ttk.Checkbutton(scrollable_frame, text=syn, variable=var)
                cb.pack(anchor="w")
            
            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")
        
        # Buttons
        btn_frame = ttk.Frame(self.top)
        btn_frame.pack(pady=20)
        
        ttk.Button(btn_frame, text="Save", command=self.save, width=10).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="Cancel", command=self.cancel, width=10).pack(side="left", padx=10)
        
        # Bind Enter key
        self.top.bind('<Return>', lambda e: self.save())
        self.top.bind('<Escape>', lambda e: self.cancel())
    
    def save(self):
        new_name = self.name_entry.get().strip()
        keep_as_synonym = self.keep_synonym_var.get() if new_name != self.current_name else False
        delete_synonyms = [syn for syn, var in self.synonym_vars.items() if not var.get()]
        
        self.result = (new_name, keep_as_synonym, delete_synonyms)
        self.top.destroy()
    
    def cancel(self):
        self.top.destroy()


def sync_missing_brands():
    """Auto-add missing brands from brand_index to lexicon before review"""
    print("🔄 Syncing new brands from scraper data...")
    try:
        import subprocess
        result = subprocess.run(
            ["python3", "tools/lexicon_gap_report.py", "--auto-add", "--exclude-unknown"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parents[1])
        )
        # Print output (shows what was added)
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                if line.startswith('✅') or line.startswith('🚫') or line.startswith('⏭️'):
                    print(f"   {line}")
    except Exception as e:
        print(f"   ⚠️ Sync failed: {e}")
    print()


def main():
    # Sync missing brands before launching UI
    sync_missing_brands()
    
    root = tk.Tk()
    app = BrandNameVerifier(root)
    root.mainloop()


if __name__ == "__main__":
    main()
