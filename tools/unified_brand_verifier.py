#!/usr/bin/env python3
"""
Unified Brand Verifier - Single tool for brand name + logo verification

This tool combines brand name verification and logo verification into one workflow,
ensuring both the brand lexicon and logo database stay in sync.

Features:
- Review unverified brands with their logos side-by-side
- Approve/edit brand names and logos together
- Automatic sync between brands.json and brand_logo_database.json
- Confidence scoring for auto-approval of high-confidence brands
"""

import json
import sys
import re
from pathlib import Path
from datetime import datetime, timezone
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from PIL import Image, ImageTk

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.brand_matcher import BrandMatcher

# Paths
LEXICON_PATH = Path("config/brands.json")
LOGOS_DIR = Path("output/brand_logos")
LOGOS_DB = LOGOS_DIR / "brand_logo_database.json"


def now_iso_z():
    """Return current UTC time in ISO 8601 Z format"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def brand_to_slug(name: str) -> str:
    """Convert brand name to database slug"""
    slug = name.lower()
    slug = slug.replace("'", "").replace("'", "").replace("`", "")
    slug = slug.replace(".", "")
    slug = slug.replace(" & ", " and ").replace("&", " and ")
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_")


def load_lexicon():
    """Load brand lexicon"""
    if LEXICON_PATH.exists():
        try:
            return json.loads(LEXICON_PATH.read_text(encoding='utf-8'))
        except Exception as e:
            print(f"Error loading lexicon: {e}")
    return []


def save_lexicon(lexicon):
    """Save brand lexicon"""
    lexicon.sort(key=lambda x: x.get("name", "").lower())
    LEXICON_PATH.write_text(json.dumps(lexicon, indent=2, ensure_ascii=False), encoding='utf-8')


def load_logo_db():
    """Load logo database"""
    if LOGOS_DB.exists():
        try:
            return json.loads(LOGOS_DB.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {"brands": {}, "metadata": {}}


def save_logo_db(logo_db):
    """Save logo database"""
    logo_db["metadata"]["last_updated"] = now_iso_z()
    logo_db["metadata"]["total_brands"] = len(logo_db.get("brands", {}))
    
    # Sort brands alphabetically
    sorted_brands = dict(sorted(logo_db.get("brands", {}).items(), key=lambda x: x[0].lower()))
    logo_db["brands"] = sorted_brands
    
    LOGOS_DB.write_text(json.dumps(logo_db, indent=2, ensure_ascii=False), encoding='utf-8')


def get_logo_path(brand_name: str, logo_db: dict) -> Path | None:
    """Get logo path for a brand"""
    slug = brand_to_slug(brand_name)
    
    # Try database first
    brand_data = logo_db.get("brands", {}).get(slug)
    if brand_data:
        logo_file = brand_data.get("logo_file", "")
        if logo_file:
            path = LOGOS_DIR / logo_file
            if path.exists():
                return path
    
    # Fallback: scan filesystem
    for folder in ["verified", "unverified", ""]:
        base_dir = LOGOS_DIR / folder if folder else LOGOS_DIR
        if not base_dir.exists():
            continue
        
        for ext in [".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif"]:
            logo_path = base_dir / f"{slug}{ext}"
            if logo_path.exists():
                return logo_path
    
    return None


class UnifiedBrandVerifier:
    def __init__(self, root):
        self.root = root
        self.root.title("Unified Brand Verifier")
        self.root.geometry("1000x800")
        
        # Load data
        self.lexicon = load_lexicon()
        self.logo_db = load_logo_db()
        self.matcher = BrandMatcher()
        
        # Filter to unverified brands OR brands with unverified logos
        self.brands_to_review = []
        for i, brand in enumerate(self.lexicon):
            brand_name = brand.get("name", "")
            brand_verified = brand.get("verified", False)
            
            # Check logo verification status
            slug = brand_to_slug(brand_name)
            logo_data = self.logo_db.get("brands", {}).get(slug, {})
            logo_verified = logo_data.get("verified", False)
            
            # Include if either brand or logo is unverified
            if not brand_verified or not logo_verified:
                self.brands_to_review.append({
                    "index": i,
                    "brand": brand,
                    "brand_verified": brand_verified,
                    "logo_verified": logo_verified,
                    "logo_data": logo_data
                })
        
        print(f"📊 Found {len(self.brands_to_review)} brands to review")
        print(f"   Brand unverified: {sum(1 for b in self.brands_to_review if not b['brand_verified'])}")
        print(f"   Logo unverified: {sum(1 for b in self.brands_to_review if not b['logo_verified'])}")
        
        self.current_index = 0
        self.stats = {
            "approved": 0,
            "edited": 0,
            "skipped": 0
        }
        
        self.setup_ui()
        self.bind_shortcuts()
        
        if self.brands_to_review:
            self.show_current_brand()
        else:
            self.show_complete_message()
    
    def setup_ui(self):
        """Setup the UI"""
        # Progress bar
        self.progress_label = ttk.Label(self.root, text="", font=("Arial", 12))
        self.progress_label.pack(pady=5)
        
        # Main content frame
        content_frame = ttk.Frame(self.root)
        content_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        # Left: Logo display
        left_frame = ttk.LabelFrame(content_frame, text="Logo", padding=10)
        left_frame.pack(side="left", fill="y", padx=(0, 10))
        
        self.logo_canvas = tk.Canvas(left_frame, width=250, height=250, bg="white")
        self.logo_canvas.pack()
        
        self.logo_status = ttk.Label(left_frame, text="", font=("Arial", 10))
        self.logo_status.pack(pady=5)
        
        # Right: Brand info
        right_frame = ttk.Frame(content_frame)
        right_frame.pack(side="left", fill="both", expand=True)
        
        # Brand name
        self.brand_label = ttk.Label(right_frame, text="", font=("Arial", 24, "bold"))
        self.brand_label.pack(pady=10, anchor="w")
        
        # Verification status
        status_frame = ttk.Frame(right_frame)
        status_frame.pack(fill="x", pady=5)
        
        self.brand_status_label = ttk.Label(status_frame, text="", font=("Arial", 11))
        self.brand_status_label.pack(anchor="w")
        
        self.logo_status_label = ttk.Label(status_frame, text="", font=("Arial", 11))
        self.logo_status_label.pack(anchor="w")
        
        # Synonyms
        syn_frame = ttk.LabelFrame(right_frame, text="Synonyms", padding=10)
        syn_frame.pack(fill="x", pady=10)
        
        self.synonyms_label = ttk.Label(syn_frame, text="", font=("Arial", 10), wraplength=600)
        self.synonyms_label.pack(anchor="w")
        
        # Stats
        self.stats_label = ttk.Label(right_frame, text="", font=("Arial", 10))
        self.stats_label.pack(pady=10)
        
        # Action buttons
        button_frame = ttk.Frame(self.root)
        button_frame.pack(pady=20)
        
        ttk.Button(button_frame, text="✓ Approve Both (A)", command=self.approve_both, width=18).pack(side="left", padx=5)
        ttk.Button(button_frame, text="✎ Edit Brand (E)", command=self.edit_brand, width=18).pack(side="left", padx=5)
        ttk.Button(button_frame, text="→ Skip (S)", command=self.skip, width=18).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Quit (Q)", command=self.quit_app, width=18).pack(side="left", padx=5)
    
    def bind_shortcuts(self):
        """Bind keyboard shortcuts"""
        self.root.bind('a', lambda e: self.approve_both())
        self.root.bind('A', lambda e: self.approve_both())
        self.root.bind('e', lambda e: self.edit_brand())
        self.root.bind('E', lambda e: self.edit_brand())
        self.root.bind('s', lambda e: self.skip())
        self.root.bind('S', lambda e: self.skip())
        self.root.bind('q', lambda e: self.quit_app())
        self.root.bind('Q', lambda e: self.quit_app())
    
    def show_current_brand(self):
        """Display current brand"""
        if self.current_index >= len(self.brands_to_review):
            self.show_complete_message()
            return
        
        item = self.brands_to_review[self.current_index]
        brand = item["brand"]
        brand_name = brand.get("name", "")
        
        # Update progress
        self.progress_label.config(
            text=f"Brand {self.current_index + 1} of {len(self.brands_to_review)}"
        )
        
        # Update brand name
        self.brand_label.config(text=brand_name)
        
        # Update verification status
        brand_status = "✓ Brand Verified" if item["brand_verified"] else "⚠ Brand Unverified"
        logo_status = "✓ Logo Verified" if item["logo_verified"] else "⚠ Logo Unverified"
        
        self.brand_status_label.config(
            text=brand_status,
            foreground="green" if item["brand_verified"] else "orange"
        )
        self.logo_status_label.config(
            text=logo_status,
            foreground="green" if item["logo_verified"] else "orange"
        )
        
        # Update synonyms
        synonyms = brand.get("synonyms", [])
        if synonyms:
            syn_text = "\n".join(f"• {s}" for s in synonyms[:10])
            if len(synonyms) > 10:
                syn_text += f"\n... and {len(synonyms) - 10} more"
            self.synonyms_label.config(text=syn_text)
        else:
            self.synonyms_label.config(text="(none)")
        
        # Show logo
        self.show_logo(brand_name)
        
        # Update stats
        self.stats_label.config(
            text=f"Approved: {self.stats['approved']} | Edited: {self.stats['edited']} | Skipped: {self.stats['skipped']}"
        )
    
    def show_logo(self, brand_name):
        """Display logo"""
        self.logo_canvas.delete("all")
        self.current_logo_image = None
        
        logo_path = get_logo_path(brand_name, self.logo_db)
        
        if logo_path:
            try:
                img = Image.open(logo_path)
                img.thumbnail((240, 240), Image.Resampling.LANCZOS)
                self.current_logo_image = ImageTk.PhotoImage(img)
                self.logo_canvas.create_image(125, 125, image=self.current_logo_image, anchor="center")
                
                is_verified = "verified" in str(logo_path)
                status = "✓ Verified" if is_verified else "⚠ Unverified"
                self.logo_status.config(text=status)
            except Exception as e:
                self.logo_canvas.create_text(125, 125, text="Error loading", fill="red")
                self.logo_status.config(text=str(e)[:40])
        else:
            self.logo_canvas.create_text(125, 125, text="No logo found", fill="gray")
            self.logo_status.config(text="Missing")
    
    def approve_both(self):
        """Approve both brand name and logo"""
        if self.current_index >= len(self.brands_to_review):
            return
        
        item = self.brands_to_review[self.current_index]
        brand = item["brand"]
        brand_name = brand.get("name", "")
        slug = brand_to_slug(brand_name)
        
        # Update brand verification in lexicon
        if not item["brand_verified"]:
            brand["verified"] = True
            print(f"✓ Verified brand: {brand_name}")
        
        # Update logo verification in database
        if not item["logo_verified"]:
            if slug in self.logo_db.get("brands", {}):
                self.logo_db["brands"][slug]["verified"] = True
                self.logo_db["brands"][slug]["verified_at"] = now_iso_z()
                
                # Move logo to verified folder if in unverified
                logo_file = self.logo_db["brands"][slug].get("logo_file", "")
                if logo_file.startswith("unverified/"):
                    old_path = LOGOS_DIR / logo_file
                    new_filename = logo_file.replace("unverified/", "")
                    new_path = LOGOS_DIR / "verified" / new_filename
                    
                    if old_path.exists():
                        new_path.parent.mkdir(exist_ok=True)
                        old_path.rename(new_path)
                        self.logo_db["brands"][slug]["logo_file"] = f"verified/{new_filename}"
                        print(f"📁 Moved logo to verified: {new_filename}")
                
                print(f"✓ Verified logo: {brand_name}")
        
        self.stats["approved"] += 1
        self.save_and_next()
    
    def edit_brand(self):
        """Edit brand name"""
        if self.current_index >= len(self.brands_to_review):
            return
        
        item = self.brands_to_review[self.current_index]
        brand = item["brand"]
        old_name = brand.get("name", "")
        
        new_name = simpledialog.askstring(
            "Edit Brand Name",
            f"Current: {old_name}\n\nEnter new canonical name:",
            initialvalue=old_name
        )
        
        if new_name and new_name != old_name:
            brand["name"] = new_name
            brand["verified"] = True
            self.stats["edited"] += 1
            print(f"✎ Renamed: {old_name} → {new_name}")
            self.save_and_next()
    
    def skip(self):
        """Skip current brand"""
        self.stats["skipped"] += 1
        self.current_index += 1
        self.show_current_brand()
    
    def save_and_next(self):
        """Save changes and move to next"""
        save_lexicon(self.lexicon)
        save_logo_db(self.logo_db)
        
        self.current_index += 1
        self.show_current_brand()
    
    def show_complete_message(self):
        """Show completion message"""
        self.brand_label.config(text="✅ All brands reviewed!")
        self.logo_canvas.delete("all")
        self.logo_canvas.create_text(125, 125, text="Complete", fill="green", font=("Arial", 16))
        
        messagebox.showinfo(
            "Complete",
            f"All brands have been reviewed!\n\n"
            f"Approved: {self.stats['approved']}\n"
            f"Edited: {self.stats['edited']}\n"
            f"Skipped: {self.stats['skipped']}"
        )
    
    def quit_app(self):
        """Quit application"""
        if messagebox.askyesno("Quit", "Save changes and quit?"):
            save_lexicon(self.lexicon)
            save_logo_db(self.logo_db)
            self.root.quit()


def main():
    root = tk.Tk()
    app = UnifiedBrandVerifier(root)
    root.mainloop()


if __name__ == "__main__":
    main()
