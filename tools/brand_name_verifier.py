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

# Paths
LEXICON_PATH = Path("config/brands.json")
LOGOS_DIR = Path("output/brand_logos")
LOGOS_DB = Path("output/brand_logos/brand_logo_database.json")
OUTPUT_DIR = Path("output")


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


def save_lexicon(lexicon):
    """Save the brand lexicon"""
    # Sort alphabetically by name
    lexicon.sort(key=lambda x: x.get("name", "").lower())
    LEXICON_PATH.write_text(json.dumps(lexicon, indent=2, ensure_ascii=False))


class BrandNameVerifier:
    def __init__(self, root):
        self.root = root
        self.root.title("Brand Name Verifier")
        self.root.geometry("900x700")
        
        # Load lexicon and logo database
        self.lexicon = load_lexicon()
        self.logo_db = load_logo_database()
        
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
        
        self.logo_canvas = tk.Canvas(logo_frame, width=200, height=150, bg="white")
        self.logo_canvas.pack()
        
        self.logo_status_label = ttk.Label(logo_frame, text="", font=("Arial", 9))
        self.logo_status_label.pack(pady=5)
        
        # NOTE: Sample Ads section REMOVED
        # Sample ads were showing ads by filename match, which caused confusion
        # (e.g., showing Hamburger Helper ads for "Barilla" because filename contained "barilla")
        # Ad mapping verification should be done in the Brand Review Tool, not here.
        # This tool is for lexicon verification only (brand names, logos, synonyms).
        
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
        button_frame.pack(pady=30)
        
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
        nav_frame.pack(pady=10)
        
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
        
        # Update synonyms
        if synonyms:
            syn_text = "\n".join(f"• {s}" for s in synonyms[:10])
            if len(synonyms) > 10:
                syn_text += f"\n... and {len(synonyms) - 10} more"
            self.synonyms_label.config(text=syn_text)
        else:
            self.synonyms_label.config(text="(none)")
        
        # Check for conflicts (this brand name is a synonym of another brand)
        self.show_conflicts(brand_name)
        
        # Update similar brands
        self.show_similar_brands(brand_name)
        
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
    
    def merge_into_brand(self, target_name):
        """Merge current brand into an existing brand"""
        if self.current_index >= len(self.brands_to_review):
            return
        
        lexicon_idx, brand = self.brands_to_review[self.current_index]
        current_name = brand.get("name", "")
        
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
                
                # Mark current for deletion
                self.deleted_indices.add(lexicon_idx)
                self.lexicon = [b for i, b in enumerate(self.lexicon) if i not in self.deleted_indices]
                self.edited_count += 1
                
                save_lexicon(self.lexicon)
                
                # Re-canonicalize ads - change old brand to target brand
                try:
                    from tools.recanon_ads import recanon_brand
                    print(f"[RECANON] Changing '{current_name}' ads to '{target_name}'...")
                    recanon_brand(old_brand=current_name, new_brand=target_name)
                except Exception as e:
                    print(f"[WARN] Failed to recanon ads: {e}")
                
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
                # Check if new name already exists
                existing = next((b for b in self.lexicon if b.get("name", "").lower() == new_name.lower()), None)
                
                if existing and existing != brand:
                    # Merge into existing brand
                    if keep_as_synonym:
                        if old_name not in existing.get("synonyms", []):
                            existing.setdefault("synonyms", []).append(old_name)
                    
                    # Move non-deleted synonyms to existing brand
                    for syn in brand.get("synonyms", []):
                        if syn not in delete_synonyms and syn not in existing.get("synonyms", []):
                            existing.setdefault("synonyms", []).append(syn)
                    
                    existing["verified"] = True
                    
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
            
            # Clean up deleted brands
            self.lexicon = [b for i, b in enumerate(self.lexicon) if i not in self.deleted_indices]
            
            save_lexicon(self.lexicon)
            
            # Re-canonicalize ads if brand was renamed/merged
            if should_recanon and recanon_target:
                try:
                    from tools.recanon_ads import recanon_brand
                    print(f"[RECANON] Changing '{old_name}' ads to '{recanon_target}'...")
                    recanon_brand(old_brand=old_name, new_brand=recanon_target)
                except Exception as e:
                    print(f"[WARN] Failed to recanon ads: {e}")
            
            # Rebuild list (brand was verified/merged/deleted)
            self.rebuild_review_list()
            self.show_current_brand()
    
    def delete_brand(self):
        """Delete the current brand from lexicon (no confirmation, use undo)"""
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
        
        # Remove from lexicon
        self.lexicon = [b for b in self.lexicon if b.get("name") != brand_name]
        self.deleted_count += 1
        
        save_lexicon(self.lexicon)
        
        # Re-canonicalize ads - change this brand to "unknown"
        try:
            from tools.recanon_ads import recanon_brand
            print(f"[RECANON] Changing '{brand_name}' ads to 'unknown'...")
            recanon_brand(old_brand=brand_name, delete=True)
        except Exception as e:
            print(f"[WARN] Failed to recanon ads: {e}")
        
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


def main():
    root = tk.Tk()
    app = BrandNameVerifier(root)
    root.mainloop()


if __name__ == "__main__":
    main()
