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
from tkinter import ttk, simpledialog, filedialog, messagebox
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


def check_logo_quality(logo_path):
    """Check logo quality. Returns 'good', 'poor', or 'missing'.
    
    'poor' means the logo exists but has quality issues:
    - No transparency (not RGBA/LA/PA) and background isn't white
    - Very small dimensions (< 150px)
    - White background but small (< 200px) — still poor
    """
    if not logo_path or not Path(logo_path).exists():
        return "missing"
    
    path = Path(logo_path)
    
    # SVG files are vector — always good quality
    if path.suffix.lower() == '.svg':
        return "good"
    
    try:
        img = Image.open(path)
        w, h = img.size
        
        # Very small images are always poor quality
        if w < 150 or h < 150:
            return "poor"
        
        # Check for transparency
        has_alpha = img.mode in ('RGBA', 'LA', 'PA')
        
        if has_alpha:
            # Has alpha channel — check if it's actually used
            alpha = img.getchannel('A')
            alpha_data = alpha.getdata()
            min_alpha = min(alpha_data)
            # If minimum alpha < 250, transparency is actually used → good
            if min_alpha < 250:
                return "good"
            # Alpha channel exists but fully opaque — treat as no transparency
        
        # No real transparency — check if background is white
        # Sample corner pixels (top-left, top-right, bottom-left, bottom-right)
        rgb = img.convert('RGB')
        corners = [
            rgb.getpixel((0, 0)),
            rgb.getpixel((w - 1, 0)),
            rgb.getpixel((0, h - 1)),
            rgb.getpixel((w - 1, h - 1)),
        ]
        
        # Also sample a few pixels along edges
        edge_pixels = corners[:]
        for x in (w // 4, w // 2, 3 * w // 4):
            edge_pixels.append(rgb.getpixel((x, 0)))
            edge_pixels.append(rgb.getpixel((x, h - 1)))
        for y in (h // 4, h // 2, 3 * h // 4):
            edge_pixels.append(rgb.getpixel((0, y)))
            edge_pixels.append(rgb.getpixel((w - 1, y)))
        
        # Check if most edge pixels are near-white (R,G,B all > 240)
        white_count = sum(1 for r, g, b in edge_pixels if r > 240 and g > 240 and b > 240)
        white_ratio = white_count / len(edge_pixels)
        
        if white_ratio >= 0.6:
            # White background — acceptable only if reasonably sized
            if w >= 200 and h >= 200:
                return "good"
            return "poor"  # White bg but too small
        
        # Not transparent and not white background → poor
        return "poor"
        
    except Exception:
        return "poor"


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
        
        # Second row of buttons
        button_frame2 = ttk.Frame(self.root)
        button_frame2.pack(pady=5)
        
        # Browse All Brands button
        self.browse_btn = ttk.Button(
            button_frame2,
            text="📋 Browse All Brands (B)",
            command=self.show_brand_browser,
            width=25
        )
        self.browse_btn.pack(side="left", padx=10)
        
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
        self.root.bind('b', lambda e: self.show_brand_browser())
        self.root.bind('B', lambda e: self.show_brand_browser())
    
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
        
        # Record rejection so the logo won't be re-harvested
        logo_url = brand_data.get("logo_url")
        if logo_url:
            if "rejected_logos" not in self.db:
                self.db["rejected_logos"] = {}
            self.db["rejected_logos"].setdefault(brand_key, [])
            if logo_url not in self.db["rejected_logos"][brand_key]:
                self.db["rejected_logos"][brand_key].append(logo_url)
                print(f"🚫 Rejected logo URL for {brand_key} (won't be re-harvested)")
        
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
    
    def show_brand_browser(self):
        """Show a browsable list of all brands with their logo status.
        
        Allows filtering to brands without logos, previewing existing logos,
        and uploading logos for any brand.
        """
        dialog = tk.Toplevel(self.root)
        dialog.title("Brand Logo Browser")
        dialog.geometry("900x700")
        dialog.transient(self.root)
        
        # --- Build brand data (rebuilt on each refresh) ---
        def build_all_rows():
            """Rebuild brand rows from live lexicon + DB state.
            
            Each row is (name, key, quality, logo_path, verified) where
            quality is 'good', 'poor', or 'missing'.
            """
            db_brands = self.db.get("brands", {})
            rows = []
            seen_keys = set()
            
            for entry in self.lexicon:
                name = entry.get("name", "").strip()
                if not name:
                    continue
                key = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
                seen_keys.add(key)
                
                db_entry = db_brands.get(key)
                if db_entry:
                    logo_file = db_entry.get("logo_file", "")
                    if logo_file.startswith("brand_logos/"):
                        logo_file = logo_file[len("brand_logos/"):]
                    logo_path = LOGOS_DIR / logo_file if logo_file else None
                    quality = check_logo_quality(logo_path)
                    verified = db_entry.get("verified", False)
                else:
                    quality = "missing"
                    logo_path = None
                    verified = False
                
                rows.append((name, key, quality, logo_path, verified))
            
            # Also include logo DB brands not in lexicon
            for key, db_entry in db_brands.items():
                if key not in seen_keys:
                    name = db_entry.get("brand_name", key.replace("_", " ").title())
                    logo_file = db_entry.get("logo_file", "")
                    if logo_file.startswith("brand_logos/"):
                        logo_file = logo_file[len("brand_logos/"):]
                    logo_path = LOGOS_DIR / logo_file if logo_file else None
                    quality = check_logo_quality(logo_path)
                    verified = db_entry.get("verified", False)
                    rows.append((name, key, quality, logo_path, verified))
            
            rows.sort(key=lambda r: r[0].lower())
            return rows
        
        all_rows = build_all_rows()
        
        def _summary_text(rows):
            good = sum(1 for r in rows if r[2] == "good")
            poor = sum(1 for r in rows if r[2] == "poor")
            miss = sum(1 for r in rows if r[2] == "missing")
            return f"{len(rows)} brands  |  ✅ {good} good  |  🟡 {poor} poor quality  |  ❌ {miss} missing"
        
        # --- Header ---
        header_frame = ttk.Frame(dialog)
        header_frame.pack(fill="x", padx=10, pady=(10, 5))
        
        summary_label = ttk.Label(
            header_frame,
            text=_summary_text(all_rows),
            font=("Arial", 12, "bold")
        )
        summary_label.pack(side="left")
        
        # Filter controls
        filter_frame = ttk.Frame(dialog)
        filter_frame.pack(fill="x", padx=10, pady=(0, 2))
        
        filter_var = tk.StringVar(value="all")
        
        def apply_filter():
            populate_list()
        
        for val, label in [("all", "All"), ("missing", "❌ Missing"), ("poor", "🟡 Poor Quality"), ("needs_work", "❌+🟡 Needs Work")]:
            ttk.Radiobutton(
                filter_frame, text=label, variable=filter_var,
                value=val, command=apply_filter
            ).pack(side="left", padx=5)
        
        # Search box
        search_frame = ttk.Frame(dialog)
        search_frame.pack(fill="x", padx=10, pady=(0, 5))
        
        ttk.Label(search_frame, text="Search:").pack(side="left", padx=(0, 5))
        search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=search_var, width=30)
        search_entry.pack(side="left", fill="x", expand=True)
        search_var.trace_add("write", lambda *_: populate_list())
        
        # --- Treeview list ---
        tree_frame = ttk.Frame(dialog)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        columns = ("status", "brand", "verified")
        tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=20)
        tree.heading("status", text="Logo")
        tree.heading("brand", text="Brand Name")
        tree.heading("verified", text="Verified")
        tree.column("status", width=60, anchor="center")
        tree.column("brand", width=600, anchor="w")
        tree.column("verified", width=80, anchor="center")
        
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Store filtered rows for selection lookup
        filtered_rows = []
        
        def populate_list():
            nonlocal filtered_rows, all_rows
            # Rebuild from live DB state (picks up uploads)
            all_rows = build_all_rows()
            summary_label.config(text=_summary_text(all_rows))
            
            tree.delete(*tree.get_children())
            
            query = search_var.get().lower().strip()
            filt = filter_var.get()
            
            filtered_rows = []
            for row in all_rows:
                name, key, quality, logo_path, verified = row
                if filt == "missing" and quality != "missing":
                    continue
                if filt == "poor" and quality != "poor":
                    continue
                if filt == "needs_work" and quality == "good":
                    continue
                if query and query not in name.lower():
                    continue
                filtered_rows.append(row)
            
            status_map = {"good": "✅", "poor": "🟡", "missing": "❌"}
            for row in filtered_rows:
                name, key, quality, logo_path, verified = row
                status = status_map.get(quality, "❌")
                v_text = "✓" if verified else ""
                tree.insert("", "end", values=(status, name, v_text))
            
            count_label.config(text=f"Showing {len(filtered_rows)} of {len(all_rows)}")
        
        count_label = ttk.Label(dialog, text="", font=("Arial", 10, "italic"))
        count_label.pack(pady=(0, 5))
        
        # --- Preview + action area ---
        bottom_frame = ttk.Frame(dialog)
        bottom_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        # Preview canvas (left)
        preview_canvas = tk.Canvas(bottom_frame, width=200, height=150, bg="white",
                                   highlightthickness=1, highlightbackground="#ccc")
        preview_canvas.pack(side="left", padx=(0, 10))
        
        # Info + buttons (right)
        action_frame = ttk.Frame(bottom_frame)
        action_frame.pack(side="left", fill="both", expand=True)
        
        selected_label = ttk.Label(action_frame, text="Select a brand above", font=("Arial", 11))
        selected_label.pack(anchor="w", pady=(0, 5))
        
        file_label = ttk.Label(action_frame, text="", font=("Arial", 9), foreground="gray")
        file_label.pack(anchor="w")
        
        upload_btn = ttk.Button(
            action_frame,
            text="📁 Upload Logo...",
            command=lambda: self._upload_logo_for_selected(tree, filtered_rows, dialog, populate_list),
            width=20
        )
        upload_btn.pack(anchor="w", pady=5)
        
        merge_btn = ttk.Button(
            action_frame,
            text="🔀 Merge into existing...",
            command=lambda: self._merge_brand_in_browser(tree, filtered_rows, dialog, populate_list),
            width=24
        )
        merge_btn.pack(anchor="w", pady=(0, 5))
        
        # URL paste + download
        url_frame = ttk.Frame(action_frame)
        url_frame.pack(anchor="w", fill="x", pady=(2, 5))
        
        url_var = tk.StringVar()
        url_entry = ttk.Entry(url_frame, textvariable=url_var, width=40)
        url_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        url_entry.insert(0, "")
        # Placeholder hint
        url_entry.bind("<FocusIn>", lambda e: url_entry.select_range(0, "end"))
        
        url_btn = ttk.Button(
            url_frame,
            text="🔗 Fetch URL",
            command=lambda: self._fetch_logo_from_url(
                tree, filtered_rows, dialog, populate_list, url_var
            ),
            width=12
        )
        url_btn.pack(side="left")
        
        # Keep a reference to prevent GC of preview image
        dialog._preview_photo = None
        
        def on_select(event):
            sel = tree.selection()
            if not sel:
                return
            idx = tree.index(sel[0])
            if idx >= len(filtered_rows):
                return
            name, key, quality, logo_path, verified = filtered_rows[idx]
            
            selected_label.config(text=name)
            
            # Show preview
            preview_canvas.delete("all")
            if quality != "missing" and logo_path and logo_path.exists():
                file_label.config(text=str(logo_path.relative_to(LOGOS_DIR)))
                try:
                    img = Image.open(logo_path)
                    if img.mode == 'RGBA':
                        bg = Image.new('RGB', img.size, (240, 240, 240))
                        bg.paste(img, mask=img.split()[3])
                        img = bg
                    elif img.mode != 'RGB':
                        img = img.convert('RGB')
                    img.thumbnail((190, 140), Image.Resampling.LANCZOS)
                    dialog._preview_photo = ImageTk.PhotoImage(img)
                    x = (200 - img.width) // 2
                    y = (150 - img.height) // 2
                    preview_canvas.create_image(x, y, anchor="nw", image=dialog._preview_photo)
                except Exception as e:
                    preview_canvas.create_text(100, 75, text=f"Error:\n{e}", font=("Arial", 9), fill="red")
            else:
                file_label.config(text="No logo file")
                preview_canvas.create_text(100, 75, text="No logo", font=("Arial", 11), fill="#999")
        
        tree.bind("<<TreeviewSelect>>", on_select)
        
        # Initial populate
        populate_list()
        search_entry.focus()
    
    def _upload_logo_for_selected(self, tree, filtered_rows, dialog, refresh_fn):
        """Upload a logo file for the currently selected brand in the browser."""
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("No Selection", "Please select a brand first.", parent=dialog)
            return
        
        idx = tree.index(sel[0])
        if idx >= len(filtered_rows):
            return
        
        name, key, quality, existing_path, verified = filtered_rows[idx]
        
        # Ask for file
        file_path = filedialog.askopenfilename(
            title=f"Select logo for '{name}'",
            parent=dialog,
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.svg *.webp *.gif"),
                ("PNG", "*.png"),
                ("JPEG", "*.jpg *.jpeg"),
                ("SVG", "*.svg"),
                ("All files", "*.*"),
            ]
        )
        
        if not file_path:
            return
        
        src = Path(file_path)
        
        # --- Validate the file ---
        warnings = []
        
        # Check extension
        valid_exts = {'.png', '.jpg', '.jpeg', '.svg', '.webp', '.gif'}
        if src.suffix.lower() not in valid_exts:
            warnings.append(f"Unsupported file type: {src.suffix}\nExpected: {', '.join(sorted(valid_exts))}")
        
        # Check file size
        file_size = src.stat().st_size
        if file_size > 5 * 1024 * 1024:  # 5 MB
            warnings.append(f"File is very large ({file_size / 1024 / 1024:.1f} MB). Logos should typically be under 1 MB.")
        if file_size < 100:
            warnings.append(f"File is suspiciously small ({file_size} bytes). It may be corrupt.")
        
        # Try to open with PIL (skip for SVG)
        if src.suffix.lower() != '.svg':
            try:
                img = Image.open(src)
                w, h = img.size
                
                # Check dimensions
                if w < 32 or h < 32:
                    warnings.append(f"Image is very small ({w}x{h}px). Logos should be at least 64x64px for clarity.")
                if w > 4000 or h > 4000:
                    warnings.append(f"Image is very large ({w}x{h}px). Consider resizing to a reasonable logo size.")
                
                # Check aspect ratio (logos are usually roughly square or wide, not extremely tall)
                ratio = max(w, h) / max(min(w, h), 1)
                if ratio > 6:
                    warnings.append(f"Extreme aspect ratio ({w}x{h}). This may not be a logo image.")
                
            except Exception as e:
                warnings.append(f"Cannot open as image: {e}\nThe file may be corrupt or not a valid image.")
        
        # Show warnings and ask for confirmation
        if warnings:
            msg = f"Potential issues with '{src.name}':\n\n"
            msg += "\n\n".join(f"⚠️  {w}" for w in warnings)
            msg += "\n\nUpload anyway?"
            if not messagebox.askyesno("Logo Validation Warning", msg, parent=dialog, icon="warning"):
                return
        
        # Confirm overwrite if brand already has a logo
        if quality != "missing" and existing_path and existing_path.exists():
            if not messagebox.askyesno(
                "Replace Existing Logo",
                f"'{name}' already has a logo.\nReplace it?",
                parent=dialog
            ):
                return
        
        # --- Copy file to verified/ ---
        import shutil
        dest_dir = LOGOS_DIR / "verified"
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        ext = src.suffix.lower()
        dest_path = dest_dir / f"{key}{ext}"
        
        try:
            shutil.copy2(str(src), str(dest_path))
        except Exception as e:
            messagebox.showerror("Upload Failed", f"Could not copy file:\n{e}", parent=dialog)
            return
        
        # --- Update logo database ---
        db_entry = self.db.setdefault("brands", {}).get(key)
        now = self.get_timestamp()
        
        if db_entry:
            # Delete old file if different path
            old_file = db_entry.get("logo_file", "")
            if old_file.startswith("brand_logos/"):
                old_file = old_file[len("brand_logos/"):]
            old_path = LOGOS_DIR / old_file if old_file else None
            if old_path and old_path.exists() and old_path != dest_path:
                try:
                    old_path.unlink()
                    print(f"🗑️  Removed old logo: {old_file}")
                except Exception:
                    pass
            
            db_entry["logo_file"] = f"verified/{key}{ext}"
            db_entry["verified"] = True
            db_entry["verified_at"] = now
            db_entry["source"] = db_entry.get("source", "manual_upload")
        else:
            self.db["brands"][key] = {
                "brand_name": name,
                "logo_file": f"verified/{key}{ext}",
                "verified": True,
                "verified_at": now,
                "source": "manual_upload",
                "first_seen": now,
                "last_seen": now,
                "retailers": [],
            }
        
        save_database(self.db)
        print(f"✅ Uploaded logo for '{name}': {dest_path.name}")
        
        # Refresh the list
        refresh_fn()
        
        messagebox.showinfo("Logo Uploaded", f"Logo for '{name}' saved successfully.", parent=dialog)
    
    def _fetch_logo_from_url(self, tree, filtered_rows, dialog, refresh_fn, url_var):
        """Download a logo from a URL for the currently selected brand."""
        import urllib.request
        import tempfile
        
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("No Selection", "Please select a brand first.", parent=dialog)
            return
        
        idx = tree.index(sel[0])
        if idx >= len(filtered_rows):
            return
        
        url = url_var.get().strip()
        if not url:
            messagebox.showinfo("No URL", "Please paste a URL into the text field.", parent=dialog)
            return
        
        if not url.startswith(("http://", "https://")):
            messagebox.showwarning("Invalid URL", "URL must start with http:// or https://", parent=dialog)
            return
        
        name, key, quality, existing_path, verified = filtered_rows[idx]
        
        # Confirm overwrite if brand already has a logo
        if quality != "missing" and existing_path and existing_path.exists():
            if not messagebox.askyesno(
                "Replace Existing Logo",
                f"'{name}' already has a logo.\nReplace it?",
                parent=dialog
            ):
                return
        
        # Determine extension from URL
        from urllib.parse import urlparse
        parsed = urlparse(url)
        url_path = parsed.path.lower()
        ext = ".png"  # default
        for candidate in ('.png', '.jpg', '.jpeg', '.svg', '.webp', '.gif'):
            if url_path.endswith(candidate):
                ext = candidate
                break
        
        # Download to temp file first
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
                content_type = resp.headers.get("Content-Type", "")
        except Exception as e:
            messagebox.showerror("Download Failed", f"Could not fetch URL:\n{e}", parent=dialog)
            return
        
        # Infer extension from content-type if URL didn't have one
        ct_map = {
            "image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
            "image/webp": ".webp", "image/svg+xml": ".svg",
        }
        for ct, ct_ext in ct_map.items():
            if ct in content_type:
                ext = ct_ext
                break
        
        # Validate downloaded data
        warnings = []
        
        if len(data) < 100:
            warnings.append(f"Downloaded file is suspiciously small ({len(data)} bytes).")
        if len(data) > 5 * 1024 * 1024:
            warnings.append(f"Downloaded file is very large ({len(data) / 1024 / 1024:.1f} MB).")
        
        if ext != '.svg':
            try:
                from io import BytesIO
                img = Image.open(BytesIO(data))
                w, h = img.size
                if w < 32 or h < 32:
                    warnings.append(f"Image is very small ({w}x{h}px).")
                if w > 4000 or h > 4000:
                    warnings.append(f"Image is very large ({w}x{h}px).")
                ratio = max(w, h) / max(min(w, h), 1)
                if ratio > 6:
                    warnings.append(f"Extreme aspect ratio ({w}x{h}).")
            except Exception as e:
                warnings.append(f"Cannot open as image: {e}")
        
        if "text/html" in content_type:
            warnings.append("Server returned HTML instead of an image.\nThe URL may require authentication or is not a direct image link.")
        
        if warnings:
            msg = f"Potential issues with downloaded file:\n\n"
            msg += "\n\n".join(f"⚠️  {w}" for w in warnings)
            msg += "\n\nSave anyway?"
            if not messagebox.askyesno("Logo Validation Warning", msg, parent=dialog, icon="warning"):
                return
        
        # Save to verified/
        dest_dir = LOGOS_DIR / "verified"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / f"{key}{ext}"
        
        try:
            dest_path.write_bytes(data)
        except Exception as e:
            messagebox.showerror("Save Failed", f"Could not save file:\n{e}", parent=dialog)
            return
        
        # Update logo database
        now = self.get_timestamp()
        db_entry = self.db.get("brands", {}).get(key)
        
        if db_entry:
            old_file = db_entry.get("logo_file", "")
            if old_file.startswith("brand_logos/"):
                old_file = old_file[len("brand_logos/"):]
            old_path = LOGOS_DIR / old_file if old_file else None
            if old_path and old_path.exists() and old_path != dest_path:
                try:
                    old_path.unlink()
                except Exception:
                    pass
            
            db_entry["logo_file"] = f"verified/{key}{ext}"
            db_entry["logo_url"] = url
            db_entry["verified"] = True
            db_entry["verified_at"] = now
            db_entry["source"] = db_entry.get("source", "manual_url")
        else:
            self.db.setdefault("brands", {})[key] = {
                "brand_name": name,
                "logo_file": f"verified/{key}{ext}",
                "logo_url": url,
                "verified": True,
                "verified_at": now,
                "source": "manual_url",
                "first_seen": now,
                "last_seen": now,
                "retailers": [],
            }
        
        save_database(self.db)
        print(f"✅ Fetched logo for '{name}' from URL: {dest_path.name}")
        
        # Clear URL field and refresh
        url_var.set("")
        refresh_fn()
        
        messagebox.showinfo("Logo Fetched", f"Logo for '{name}' saved successfully.", parent=dialog)
    
    def _merge_brand_in_browser(self, tree, filtered_rows, dialog, refresh_fn):
        """Merge the selected brand into an existing brand that has a logo.
        
        - Copies the target's logo to the source brand
        - Adds the source brand name as a synonym of the target in the lexicon
        - Updates the logo database
        """
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("No Selection", "Please select a brand to merge first.", parent=dialog)
            return
        
        idx = tree.index(sel[0])
        if idx >= len(filtered_rows):
            return
        
        src_name, src_key, src_quality, src_logo_path, src_verified = filtered_rows[idx]
        
        # Build list of brands that have logos (potential merge targets)
        db_brands = self.db.get("brands", {})
        targets = []
        for entry in self.lexicon:
            t_name = entry.get("name", "").strip()
            if not t_name:
                continue
            t_key = re.sub(r"[^a-z0-9]+", "_", t_name.lower()).strip("_")
            if t_key == src_key:
                continue  # Skip self
            t_db = db_brands.get(t_key)
            if t_db:
                t_logo = t_db.get("logo_file", "")
                if t_logo:
                    targets.append((t_name, t_key, t_db))
        
        if not targets:
            messagebox.showinfo("No Targets", "No other brands with logos found.", parent=dialog)
            return
        
        # Show a searchable picker dialog
        picker = tk.Toplevel(dialog)
        picker.title(f"Merge '{src_name}' into...")
        picker.geometry("500x500")
        picker.transient(dialog)
        picker.grab_set()
        
        ttk.Label(picker, text=f"Select the brand to merge '{src_name}' into:",
                  font=("Arial", 11)).pack(padx=10, pady=(10, 5), anchor="w")
        
        # Search
        search_frame = ttk.Frame(picker)
        search_frame.pack(fill="x", padx=10, pady=(0, 5))
        ttk.Label(search_frame, text="Search:").pack(side="left", padx=(0, 5))
        pick_search = tk.StringVar()
        pick_entry = ttk.Entry(search_frame, textvariable=pick_search, width=30)
        pick_entry.pack(side="left", fill="x", expand=True)
        
        # Listbox
        lb_frame = ttk.Frame(picker)
        lb_frame.pack(fill="both", expand=True, padx=10, pady=5)
        lb = tk.Listbox(lb_frame, font=("Arial", 11))
        lb_scroll = ttk.Scrollbar(lb_frame, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=lb_scroll.set)
        lb.pack(side="left", fill="both", expand=True)
        lb_scroll.pack(side="right", fill="y")
        
        # Preview of target logo
        preview_frame = ttk.Frame(picker)
        preview_frame.pack(fill="x", padx=10, pady=5)
        target_preview = tk.Canvas(preview_frame, width=100, height=80, bg="white",
                                   highlightthickness=1, highlightbackground="#ccc")
        target_preview.pack(side="left", padx=(0, 10))
        target_info = ttk.Label(preview_frame, text="", font=("Arial", 10))
        target_info.pack(side="left", anchor="w")
        picker._preview_photo = None
        
        visible_targets = list(targets)
        
        def populate_picker():
            nonlocal visible_targets
            lb.delete(0, tk.END)
            q = pick_search.get().lower().strip()
            visible_targets = [t for t in targets if q in t[0].lower()] if q else list(targets)
            for t_name, _, _ in visible_targets:
                lb.insert(tk.END, t_name)
        
        def on_pick_select(event):
            sel_idx = lb.curselection()
            if not sel_idx:
                return
            t_name, t_key, t_db = visible_targets[sel_idx[0]]
            target_info.config(text=t_name)
            target_preview.delete("all")
            t_logo = t_db.get("logo_file", "")
            if t_logo.startswith("brand_logos/"):
                t_logo = t_logo[len("brand_logos/"):]
            t_path = LOGOS_DIR / t_logo if t_logo else None
            if t_path and t_path.exists():
                try:
                    img = Image.open(t_path)
                    if img.mode == 'RGBA':
                        bg = Image.new('RGB', img.size, (240, 240, 240))
                        bg.paste(img, mask=img.split()[3])
                        img = bg
                    elif img.mode != 'RGB':
                        img = img.convert('RGB')
                    img.thumbnail((90, 70), Image.Resampling.LANCZOS)
                    picker._preview_photo = ImageTk.PhotoImage(img)
                    target_preview.create_image(50, 40, anchor="center", image=picker._preview_photo)
                except Exception:
                    target_preview.create_text(50, 40, text="?", font=("Arial", 14))
        
        lb.bind("<<ListboxSelect>>", on_pick_select)
        pick_search.trace_add("write", lambda *_: populate_picker())
        
        def do_merge():
            sel_idx = lb.curselection()
            if not sel_idx:
                messagebox.showinfo("No Selection", "Please select a target brand.", parent=picker)
                return
            
            t_name, t_key, t_db = visible_targets[sel_idx[0]]
            
            if not messagebox.askyesno(
                "Confirm Merge",
                f"Merge '{src_name}' into '{t_name}'?\n\n"
                f"• '{src_name}' will use '{t_name}'s logo\n"
                f"• '{src_name}' will be added as a synonym of '{t_name}' in the lexicon",
                parent=picker
            ):
                return
            
            import shutil
            
            # 1. Copy target's logo to source brand key
            t_logo = t_db.get("logo_file", "")
            if t_logo.startswith("brand_logos/"):
                t_logo = t_logo[len("brand_logos/"):]
            t_path = LOGOS_DIR / t_logo
            
            if t_path.exists():
                ext = t_path.suffix
                dest_dir = LOGOS_DIR / "verified"
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest_path = dest_dir / f"{src_key}{ext}"
                
                try:
                    shutil.copy2(str(t_path), str(dest_path))
                except Exception as e:
                    messagebox.showerror("Merge Failed", f"Could not copy logo:\n{e}", parent=picker)
                    return
                
                # Update source brand in logo DB
                now = self.get_timestamp()
                self.db.setdefault("brands", {})[src_key] = {
                    "brand_name": src_name,
                    "logo_file": f"verified/{src_key}{ext}",
                    "logo_url": t_db.get("logo_url", ""),
                    "verified": True,
                    "verified_at": now,
                    "source": f"merged_from_{t_key}",
                    "first_seen": now,
                    "last_seen": now,
                    "retailers": t_db.get("retailers", []),
                }
                save_database(self.db)
            
            # 2. Add source name as synonym of target in lexicon
            target_entry = next((b for b in self.lexicon if b.get("name", "").lower() == t_name.lower()), None)
            if target_entry:
                syns = target_entry.setdefault("synonyms", [])
                if src_name not in syns:
                    syns.append(src_name)
                    from utils.lexicon_utils import save_lexicon as _save_lex
                    _save_lex(self.lexicon)
                    print(f"[MERGE] Added '{src_name}' as synonym of '{t_name}'")
            
            print(f"✅ Merged '{src_name}' -> '{t_name}' (logo copied, synonym added)")
            
            picker.destroy()
            refresh_fn()
            messagebox.showinfo("Merge Complete",
                                f"'{src_name}' now uses '{t_name}'s logo.\n"
                                f"Added as synonym in lexicon.",
                                parent=dialog)
        
        btn_frame = ttk.Frame(picker)
        btn_frame.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(btn_frame, text="Merge", command=do_merge).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=picker.destroy).pack(side="right")
        
        populate_picker()
        pick_entry.focus()
    
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
