#!/usr/bin/env python3
"""
Logo Verifier GUI - Review and approve/reject brand logos

Shows each logo with its brand name and metadata.
Press 'Y' to keep, 'N' to delete, 'Q' to quit.
"""

import os
# Set library path for cairo (needed for SVG rendering on macOS)
# Must be done before importing svglib/reportlab
if 'DYLD_LIBRARY_PATH' not in os.environ:
    os.environ['DYLD_LIBRARY_PATH'] = '/opt/homebrew/lib:/usr/local/lib'

import json
import re
import sys
from pathlib import Path
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import ttk, simpledialog
from difflib import SequenceMatcher

# Paths - use absolute paths relative to project root
PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOGOS_DIR = PROJECT_ROOT / "output/brand_logos"
LOGOS_DB = PROJECT_ROOT / "output/brand_logos/brand_logo_database.json"
BRANDS_LEXICON = PROJECT_ROOT / "config/brands.json"


def load_database():
    """Load the brand logo database"""
    if LOGOS_DB.exists():
        try:
            return json.loads(LOGOS_DB.read_text())
        except Exception:
            pass
    return {"brands": {}, "metadata": {"last_updated": None, "total_brands": 0}}


def save_database(db):
    """Save the brand logo database"""
    from datetime import datetime, timezone
    db["metadata"]["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db["metadata"]["total_brands"] = len(db["brands"])
    
    # Sort brands alphabetically
    sorted_brands = dict(sorted(db["brands"].items(), key=lambda x: x[0].lower()))
    db["brands"] = sorted_brands
    
    LOGOS_DB.write_text(json.dumps(db, indent=2, ensure_ascii=False))


def load_lexicon():
    """Load the brand lexicon"""
    if BRANDS_LEXICON.exists():
        try:
            return json.loads(BRANDS_LEXICON.read_text())
        except Exception:
            pass
    return []


def find_similar_brands(brand_name, lexicon, threshold=0.6):
    """Find similar brands in lexicon using fuzzy matching"""
    similar = []
    brand_lower = brand_name.lower()
    
    for brand in lexicon:
        lex_name = brand.get('name', '')
        lex_lower = lex_name.lower()
        
        # Check exact substring match
        if brand_lower in lex_lower or lex_lower in brand_lower:
            similar.append((lex_name, 1.0, 'substring'))
            continue
        
        # Check synonyms
        for syn in brand.get('synonyms', []):
            syn_lower = syn.lower()
            if brand_lower in syn_lower or syn_lower in brand_lower:
                similar.append((lex_name, 0.95, 'synonym'))
                break
        
        # Fuzzy match on name
        ratio = SequenceMatcher(None, brand_lower, lex_lower).ratio()
        if ratio >= threshold:
            similar.append((lex_name, ratio, 'fuzzy'))
    
    # Sort by score descending
    similar.sort(key=lambda x: x[1], reverse=True)
    return similar[:5]  # Return top 5 matches


class LogoVerifier:
    def get_timestamp(self):
        """Get current timestamp in ISO format"""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    def __init__(self, root):
        self.root = root
        self.root.title("Logo Verifier")
        self.root.geometry("800x950")
        
        # Load database and lexicon
        self.db = load_database()
        self.lexicon = load_lexicon()
        
        # Build list of logos to review from TWO sources:
        # 1. Database entries that aren't verified yet (with existing files)
        # 2. Files in unverified/ folder not yet in database (NEW logos to add)
        
        all_brands = list(self.db.get("brands", {}).items())
        self.brands = []
        skipped_no_file = 0
        skipped_verified = 0
        
        # Track which files are already in database
        db_files = set()
        
        # Source 1: Unverified database entries with existing files
        for brand_key, brand_data in all_brands:
            logo_file = brand_data.get("logo_file", "")
            if logo_file:
                db_files.add(logo_file)
                # Also track without prefix
                if logo_file.startswith("unverified/"):
                    db_files.add(logo_file.replace("unverified/", ""))
            
            # Skip already verified logos
            if brand_data.get("verified", False):
                skipped_verified += 1
                continue
            
            # Handle both path formats
            if logo_file.startswith("brand_logos/"):
                logo_file = logo_file.replace("brand_logos/", "")
            
            logo_path = LOGOS_DIR / logo_file
            
            if logo_path.exists():
                self.brands.append((brand_key, brand_data))
            else:
                skipped_no_file += 1
                print(f"⊘ Skipping {brand_key}: file not found ({logo_file})")
        
        # Source 2: Scan unverified/ folder for NEW files not in database
        unverified_dir = LOGOS_DIR / "unverified"
        new_files = 0
        if unverified_dir.exists():
            for logo_file in unverified_dir.iterdir():
                if logo_file.is_file() and logo_file.suffix.lower() in ('.png', '.jpg', '.jpeg', '.svg', '.webp', '.gif', '.bin'):
                    rel_path = f"unverified/{logo_file.name}"
                    # Check if this file is already tracked in database
                    if rel_path not in db_files and logo_file.name not in db_files:
                        # NEW file - create a placeholder entry for review
                        # Derive brand name from filename (e.g., "annie_chun.png" -> "Annie Chun")
                        brand_key = logo_file.stem.lower().replace('-', '_')
                        brand_name = logo_file.stem.replace('_', ' ').replace('-', ' ').title()
                        
                        brand_data = {
                            "brand_name": brand_name,
                            "logo_file": rel_path,
                            "logo_url": None,
                            "retailers": ["amazon"],  # Default, can be edited
                            "first_seen": self.get_timestamp(),
                            "source": "unknown",
                            "_is_new": True,  # Flag to indicate this needs to be added to DB
                        }
                        self.brands.append((brand_key, brand_data))
                        new_files += 1
                        print(f"➕ New file found: {logo_file.name} -> '{brand_name}'")
        
        print(f"\n📊 Found {len(self.brands)} logos to verify")
        print(f"   From database: {len(self.brands) - new_files} unverified entries")
        print(f"   New files: {new_files} (will be added to database)")
        print(f"   Skipped: {skipped_verified} already verified, {skipped_no_file} missing files")
        
        self.current_index = 0
        self.deleted_count = 0
        self.kept_count = 0
        
        # Setup UI
        self.setup_ui()
        
        # Show first logo
        if self.brands:
            self.show_current_logo()
        else:
            self.show_empty_message()
    
    def setup_ui(self):
        """Setup the UI components"""
        # Progress label
        self.progress_label = ttk.Label(
            self.root,
            text="",
            font=("Arial", 12)
        )
        self.progress_label.pack(pady=10)
        
        # Brand name label
        self.brand_label = ttk.Label(
            self.root,
            text="",
            font=("Arial", 20, "bold")
        )
        self.brand_label.pack(pady=10)
        
        # Image canvas
        self.canvas = tk.Canvas(self.root, width=600, height=400, bg="white")
        self.canvas.pack(pady=20)
        
        # Metadata frame
        self.metadata_frame = ttk.Frame(self.root)
        self.metadata_frame.pack(pady=10, fill="x", padx=20)
        
        self.source_label = ttk.Label(self.metadata_frame, text="", font=("Arial", 10))
        self.source_label.pack(anchor="w")
        
        self.path_label = ttk.Label(self.metadata_frame, text="", font=("Arial", 10))
        self.path_label.pack(anchor="w")
        
        self.retailers_label = ttk.Label(self.metadata_frame, text="", font=("Arial", 10))
        self.retailers_label.pack(anchor="w")
        
        # Similar brands frame
        self.similar_frame = ttk.LabelFrame(self.root, text="Similar Existing Brands", padding=10)
        self.similar_frame.pack(pady=10, fill="x", padx=20)
        
        self.similar_text = tk.Text(
            self.similar_frame,
            height=4,
            width=70,
            font=("Arial", 10),
            wrap="word",
            state="disabled"
        )
        self.similar_text.pack()
        
        # Button frame
        button_frame = ttk.Frame(self.root)
        button_frame.pack(pady=20)
        
        # Keep button
        self.keep_btn = ttk.Button(
            button_frame,
            text="✓ Keep (Y)",
            command=self.keep_logo,
            width=15
        )
        self.keep_btn.pack(side="left", padx=10)
        
        # Delete button
        self.delete_btn = ttk.Button(
            button_frame,
            text="✗ Delete (N)",
            command=self.delete_logo,
            width=15
        )
        self.delete_btn.pack(side="left", padx=10)
        
        # Rename button
        self.rename_btn = ttk.Button(
            button_frame,
            text="✎ Rename (R)",
            command=self.rename_brand,
            width=15
        )
        self.rename_btn.pack(side="left", padx=10)
        
        # Merge button
        self.merge_btn = ttk.Button(
            button_frame,
            text="⇄ Merge (M)",
            command=self.merge_with_existing,
            width=15
        )
        self.merge_btn.pack(side="left", padx=10)
        
        # Quit button
        self.quit_btn = ttk.Button(
            button_frame,
            text="Quit (Q)",
            command=self.quit_app,
            width=15
        )
        self.quit_btn.pack(side="left", padx=10)
        
        # Stats label
        self.stats_label = ttk.Label(
            self.root,
            text="",
            font=("Arial", 10, "italic")
        )
        self.stats_label.pack(pady=10)
        
        # Keyboard bindings
        self.root.bind('y', lambda e: self.keep_logo())
        self.root.bind('Y', lambda e: self.keep_logo())
        self.root.bind('n', lambda e: self.delete_logo())
        self.root.bind('N', lambda e: self.delete_logo())
        self.root.bind('r', lambda e: self.rename_brand())
        self.root.bind('R', lambda e: self.rename_brand())
        self.root.bind('m', lambda e: self.merge_with_existing())
        self.root.bind('M', lambda e: self.merge_with_existing())
        self.root.bind('q', lambda e: self.quit_app())
        self.root.bind('Q', lambda e: self.quit_app())
        self.root.bind('<Left>', lambda e: self.previous_logo())
        self.root.bind('<Right>', lambda e: self.next_logo())
    
    def show_empty_message(self):
        """Show message when no logos to verify"""
        self.brand_label.config(text="No logos to verify!")
        self.progress_label.config(text="Database is empty")
    
    def show_current_logo(self):
        """Display the current logo"""
        if self.current_index >= len(self.brands):
            self.show_completion()
            return
        
        brand_key, brand_data = self.brands[self.current_index]
        logo_file = brand_data.get("logo_file", "")
        
        # Check if this is a NEW entry
        is_new = brand_data.get("_is_new", False)
        
        # Update progress
        status = " [NEW]" if is_new else ""
        self.progress_label.config(
            text=f"Logo {self.current_index + 1} of {len(self.brands)}{status}"
        )
        
        # Update brand name (use brand_name if available, else convert key)
        brand_name = brand_data.get("brand_name") or brand_key.replace("_", " ").title()
        if is_new:
            brand_name = f"➕ {brand_name}"
        self.brand_label.config(text=brand_name)
        
        # Update metadata
        source = brand_data.get("source", "unknown")
        retailers = ", ".join(brand_data.get("retailers", []))
        
        self.source_label.config(text=f"Source: {source}")
        self.path_label.config(text=f"File: {logo_file}")
        self.retailers_label.config(text=f"Retailers: {retailers}")
        
        # Find and display similar brands
        similar_brands = find_similar_brands(brand_name.replace("➕ ", ""), self.lexicon)
        self.display_similar_brands(similar_brands)
        
        # Update stats
        self.stats_label.config(
            text=f"Kept: {self.kept_count} | Deleted: {self.deleted_count}"
        )
        
        # Load and display image
        # Handle both "afia.png" and "brand_logos/afia.png" formats
        if logo_file.startswith("brand_logos/"):
            logo_file = logo_file.replace("brand_logos/", "")
        
        logo_path = LOGOS_DIR / logo_file
        if logo_path.exists():
            try:
                # Handle SVG files specially (PIL doesn't support SVG)
                if logo_path.suffix.lower() == '.svg':
                    try:
                        from svglib.svglib import svg2rlg
                        from reportlab.graphics import renderPM
                        from io import BytesIO
                        # Convert SVG to PNG in memory
                        drawing = svg2rlg(str(logo_path))
                        if drawing:
                            # Scale to fit
                            scale = min(580 / drawing.width, 380 / drawing.height) if drawing.width and drawing.height else 1
                            drawing.width *= scale
                            drawing.height *= scale
                            drawing.scale(scale, scale)
                            png_data = renderPM.drawToString(drawing, fmt="PNG")
                            img = Image.open(BytesIO(png_data))
                        else:
                            raise ValueError("Could not parse SVG")
                    except ImportError:
                        # svglib not installed - show placeholder
                        self.canvas.delete("all")
                        self.canvas.create_text(
                            300, 200,
                            text=f"SVG file (install svglib to preview)\n{logo_path.name}",
                            font=("Arial", 12),
                            fill="orange"
                        )
                        return
                    except Exception as svg_err:
                        # SVG parsing failed - show error
                        self.canvas.delete("all")
                        self.canvas.create_text(
                            300, 200,
                            text=f"SVG preview error:\n{svg_err}\n{logo_path.name}",
                            font=("Arial", 10),
                            fill="orange"
                        )
                        return
                else:
                    # Load regular image
                    img = Image.open(logo_path)
                
                # Handle RGBA images - composite onto a light gray background
                # so transparent logos are visible
                if img.mode == 'RGBA':
                    # Create a light gray background (checkerboard pattern for transparency)
                    bg = Image.new('RGB', img.size, (240, 240, 240))
                    bg.paste(img, mask=img.split()[3])  # Use alpha channel as mask
                    img = bg
                elif img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Resize to fit canvas while maintaining aspect ratio
                max_width, max_height = 580, 380
                img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
                
                # Convert to PhotoImage
                self.photo = ImageTk.PhotoImage(img)
                
                # Clear canvas and display image
                self.canvas.delete("all")
                
                # Center the image
                x = (600 - img.width) // 2
                y = (400 - img.height) // 2
                
                self.canvas.create_image(x, y, anchor="nw", image=self.photo)
                
            except Exception as e:
                self.canvas.delete("all")
                self.canvas.create_text(
                    300, 200,
                    text=f"Error loading image:\n{str(e)}",
                    font=("Arial", 12),
                    fill="red"
                )
        else:
            self.canvas.delete("all")
            self.canvas.create_text(
                300, 200,
                text=f"File not found:\n{logo_path}",
                font=("Arial", 12),
                fill="red"
            )
    
    def keep_logo(self):
        """Keep the current logo and move to next"""
        if self.current_index >= len(self.brands):
            return
        
        brand_key, brand_data = self.brands[self.current_index]
        
        # Check if this is a NEW entry (from unverified folder scan)
        is_new = brand_data.get("_is_new", False)
        
        if is_new:
            # ADD new entry to database
            new_entry = {
                "brand_name": brand_data.get("brand_name", brand_key.replace("_", " ").title()),
                "logo_url": brand_data.get("logo_url"),
                "logo_file": brand_data.get("logo_file"),
                "retailers": brand_data.get("retailers", ["amazon"]),
                "first_seen": brand_data.get("first_seen", self.get_timestamp()),
                "last_seen": self.get_timestamp(),
                "source": brand_data.get("source", "unknown"),
                "verified": True,
                "verified_at": self.get_timestamp(),
            }
            self.db["brands"][brand_key] = new_entry
            entry = new_entry
            print(f"➕ Added new brand to database: {brand_key}")
        elif brand_key in self.db["brands"]:
            entry = self.db["brands"][brand_key]
            entry["verified"] = True
            entry["verified_at"] = self.get_timestamp()
        else:
            # Shouldn't happen, but handle gracefully
            self.kept_count += 1
            self.next_logo()
            return

        # Move file from unverified/ to verified/ bucket
        logo_file = (entry.get("logo_file", "") or "").strip()
        if logo_file.startswith("brand_logos/"):
            logo_file = logo_file[len("brand_logos/"):]
        
        src_path = (LOGOS_DIR / logo_file) if logo_file else None
        filename = src_path.name if src_path else None
        if src_path and filename and src_path.exists():
            verified_dir = LOGOS_DIR / "verified"
            verified_dir.mkdir(parents=True, exist_ok=True)
            dest_rel = f"verified/{filename}"
            dest_path = verified_dir / filename
            if dest_path != src_path:
                try:
                    src_path.rename(dest_path)
                    print(f"📁 Moved {logo_file} -> {dest_rel}")
                except Exception as e:
                    print(f"⚠️  Could not move file: {e}")
                    # If rename fails, keep original path
                    dest_rel = logo_file or filename
            # Store path relative to logo root (no brand_logos/ prefix)
            entry["logo_file"] = dest_rel
            # Update in-memory brand_data so subsequent operations see it
            self.brands[self.current_index] = (brand_key, entry)
        
        save_database(self.db)
        self.kept_count += 1
        self.next_logo()
    
    def display_similar_brands(self, similar_brands):
        """Display similar brands in the UI"""
        self.similar_text.config(state="normal")
        self.similar_text.delete("1.0", "end")
        
        if not similar_brands:
            self.similar_text.insert("1.0", "No similar brands found in lexicon.")
        else:
            lines = []
            for i, (name, score, match_type) in enumerate(similar_brands, 1):
                score_pct = int(score * 100)
                match_label = {"substring": "⊂", "synonym": "≈", "fuzzy": "~"}[match_type]
                
                # Check if this brand has a logo
                brand_key = name.lower().replace(" ", "_").replace("'", "")
                has_logo = "✓" if (LOGOS_DIR / f"verified/{brand_key}.png").exists() or \
                                   (LOGOS_DIR / f"verified/{brand_key}.jpg").exists() else "○"
                
                lines.append(f"{i}. {has_logo} {name} ({score_pct}% {match_label})")
            
            self.similar_text.insert("1.0", "\n".join(lines))
        
        self.similar_text.config(state="disabled")
    
    def rename_brand(self):
        """Rename the brand and update lexicon + logo database"""
        if self.current_index >= len(self.brands):
            return
        
        brand_key, brand_data = self.brands[self.current_index]
        current_name = brand_data.get("brand_name") or brand_key.replace("_", " ").title()
        
        # Ask for new name
        new_name = simpledialog.askstring(
            "Rename Brand",
            f"Enter new name for '{current_name}':",
            initialvalue=current_name,
            parent=self.root
        )
        
        if not new_name or new_name == current_name:
            return
        
        # Create new key from new name
        new_key = re.sub(r"[^a-z0-9]+", "_", new_name.lower()).strip("_")
        old_key = brand_key
        
        print(f"✎ Renaming: {current_name} -> {new_name}")
        
        # Update logo database
        if old_key in self.db["brands"]:
            entry = self.db["brands"][old_key]
            entry["brand_name"] = new_name
            
            # Rename the logo file too
            old_logo = entry.get("logo_file", "")
            if old_logo:
                # Get file extension
                old_path = LOGOS_DIR / old_logo
                if old_path.exists():
                    ext = old_path.suffix
                    # Determine if in verified or unverified
                    if "verified/" in old_logo:
                        new_logo = f"verified/{new_key}{ext}"
                    else:
                        new_logo = f"unverified/{new_key}{ext}"
                    
                    new_path = LOGOS_DIR / new_logo
                    try:
                        new_path.parent.mkdir(parents=True, exist_ok=True)
                        old_path.rename(new_path)
                        entry["logo_file"] = new_logo
                        print(f"   Renamed file: {old_logo} -> {new_logo}")
                    except Exception as e:
                        print(f"   [WARN] Could not rename file: {e}")
            
            # Move to new key in database
            if new_key != old_key:
                self.db["brands"][new_key] = entry
                del self.db["brands"][old_key]
            
            # Update in-memory list
            self.brands[self.current_index] = (new_key, entry)
        
        # Update lexicon - add old name as synonym of new name
        try:
            from core.lexicon_utils import load_lexicon, save_lexicon
            lexicon = load_lexicon()
            
            # Find if old brand exists in lexicon
            old_entry = next((b for b in lexicon if b.get("name", "").lower() == current_name.lower()), None)
            new_entry = next((b for b in lexicon if b.get("name", "").lower() == new_name.lower()), None)
            
            if old_entry and new_entry and old_entry != new_entry:
                # Merge old into new
                if current_name not in new_entry.get("synonyms", []):
                    new_entry.setdefault("synonyms", []).append(current_name)
                for syn in old_entry.get("synonyms", []):
                    if syn not in new_entry.get("synonyms", []):
                        new_entry["synonyms"].append(syn)
                lexicon.remove(old_entry)
                print(f"   Merged '{current_name}' into '{new_name}' in lexicon")
            elif old_entry:
                # Rename existing entry
                old_entry["name"] = new_name
                old_entry.setdefault("synonyms", []).append(current_name)
                print(f"   Renamed in lexicon: {current_name} -> {new_name}")
            elif not new_entry:
                # Create new entry with old name as synonym
                lexicon.append({
                    "name": new_name,
                    "synonyms": [current_name],
                    "verified": False
                })
                print(f"   Added to lexicon: {new_name} (with synonym {current_name})")
            
            save_lexicon(lexicon)
            
            # Re-canonicalize ads
            try:
                from tools.recanon_ads import recanon_brand
                print(f"   [RECANON] Changing '{current_name}' ads to '{new_name}'...")
                recanon_brand(old_brand=current_name, new_brand=new_name)
            except Exception as e:
                print(f"   [WARN] Failed to recanon ads: {e}")
                
        except Exception as e:
            print(f"   [WARN] Could not update lexicon: {e}")
        
        # Refresh display
        self.show_current_logo()
    
    def delete_logo(self):
        """Delete the current logo and move to next"""
        if self.current_index >= len(self.brands):
            return
        
        brand_key, brand_data = self.brands[self.current_index]
        logo_file = brand_data.get("logo_file", "")
        is_new = brand_data.get("_is_new", False)
        
        # Strip brand_logos/ prefix if present to avoid double path
        if logo_file.startswith("brand_logos/"):
            logo_file = logo_file[len("brand_logos/"):]
        
        logo_path = LOGOS_DIR / logo_file
        
        # Delete file
        if logo_path.exists():
            logo_path.unlink()
            print(f"🗑️  Deleted: {logo_file}")
        else:
            print(f"⚠️  File not found: {logo_path}")
        
        # Remove from database (only if it was in there - not for new files)
        if not is_new and brand_key in self.db["brands"]:
            del self.db["brands"][brand_key]
            save_database(self.db)
        
        # Remove from brands list
        self.brands.pop(self.current_index)
        
        self.deleted_count += 1
        
        # Show next logo (don't increment index since we removed current)
        self.show_current_logo()
    
    def merge_with_existing(self):
        """Merge current logo with an existing brand from lexicon"""
        if self.current_index >= len(self.brands):
            return
        
        brand_key, brand_data = self.brands[self.current_index]
        current_name = brand_data.get("brand_name", brand_key.replace("_", " ").title())
        
        # Get similar brands
        similar_brands = find_similar_brands(current_name, self.lexicon)
        
        if not similar_brands:
            tk.messagebox.showinfo("No Matches", "No similar brands found in lexicon to merge with.")
            return
        
        # Show dialog with options
        choices = [f"{name} ({int(score*100)}%)" for name, score, _ in similar_brands]
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Merge with Existing Brand")
        dialog.geometry("500x400")
        
        ttk.Label(
            dialog,
            text=f"Merge '{current_name}' with which existing brand?",
            font=("Arial", 12, "bold")
        ).pack(pady=10)
        
        listbox = tk.Listbox(dialog, font=("Arial", 11), height=10)
        for choice in choices:
            listbox.insert("end", choice)
        listbox.pack(pady=10, fill="both", expand=True, padx=20)
        
        selected_brand = [None]
        
        def on_select():
            selection = listbox.curselection()
            if selection:
                idx = selection[0]
                selected_brand[0] = similar_brands[idx][0]
                dialog.destroy()
        
        ttk.Button(dialog, text="Merge", command=on_select).pack(pady=5)
        ttk.Button(dialog, text="Cancel", command=dialog.destroy).pack(pady=5)
        
        dialog.wait_window()
        
        if selected_brand[0]:
            # Merge: move logo to verified with the existing brand's name
            existing_name = selected_brand[0]
            existing_key = existing_name.lower().replace(" ", "_").replace("'", "")
            
            # Get current logo file
            logo_file = brand_data.get("logo_file", "")
            if logo_file.startswith("brand_logos/"):
                logo_file = logo_file.replace("brand_logos/", "")
            
            src_path = LOGOS_DIR / logo_file
            
            if src_path.exists():
                # Determine extension
                ext = src_path.suffix
                dest_path = LOGOS_DIR / f"verified/{existing_key}{ext}"
                
                # Copy to verified with existing brand's name
                import shutil
                shutil.copy2(src_path, dest_path)
                
                # Update database
                if existing_key not in self.db["brands"]:
                    self.db["brands"][existing_key] = {
                        "brand_name": existing_name,
                        "verified": True,
                        "verified_at": self.get_timestamp(),
                        "logo_file": f"verified/{existing_key}{ext}",
                        "retailers": brand_data.get("retailers", []),
                        "source": brand_data.get("source", "unknown"),
                        "first_seen": self.get_timestamp(),
                        "last_seen": self.get_timestamp()
                    }
                else:
                    # Update existing entry
                    self.db["brands"][existing_key]["verified"] = True
                    self.db["brands"][existing_key]["verified_at"] = self.get_timestamp()
                    self.db["brands"][existing_key]["logo_file"] = f"verified/{existing_key}{ext}"
                
                # Remove old entry if it was in database
                if brand_key in self.db["brands"] and brand_key != existing_key:
                    del self.db["brands"][brand_key]
                
                # Delete source file
                src_path.unlink()
                
                save_database(self.db)
                
                print(f"✓ Merged '{current_name}' → '{existing_name}'")
                self.kept_count += 1
                self.next_logo()
    
    def next_logo(self):
        """Move to next logo"""
        self.current_index += 1
        self.show_current_logo()
    
    def previous_logo(self):
        """Move to previous logo"""
        if self.current_index > 0:
            self.current_index -= 1
            self.show_current_logo()
    
    def show_completion(self):
        """Show completion message"""
        self.brand_label.config(text="✅ Verification Complete!")
        self.progress_label.config(text="All logos reviewed")
        self.canvas.delete("all")
        self.canvas.create_text(
            300, 200,
            text=f"Kept: {self.kept_count}\nDeleted: {self.deleted_count}",
            font=("Arial", 16),
            fill="green"
        )
        
        # Disable buttons
        self.keep_btn.config(state="disabled")
        self.delete_btn.config(state="disabled")
    
    def quit_app(self):
        """Save database and quit"""
        print(f"\n📊 Session Summary:")
        print(f"   Kept: {self.kept_count}")
        print(f"   Deleted: {self.deleted_count}")
        print(f"   Remaining: {self.current_index}/{len(self.brands)}")
        
        # Save database
        save_database(self.db)
        print(f"✅ Database saved: {LOGOS_DB}")
        
        self.root.quit()


def main():
    root = tk.Tk()
    app = LogoVerifier(root)
    root.mainloop()


if __name__ == "__main__":
    main()
