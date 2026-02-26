#!/usr/bin/env python3
"""
Brand Deduplication Tool

Finds duplicate/similar brand entries in the logo database, shows them
side-by-side with logo previews, and lets you pick the best name and
best logo independently. The winner entry is kept with the chosen
name + logo; loser names become synonyms in the lexicon.

Usage:
    python3 tools/brand_dedup_tool.py
"""

import os
if 'DYLD_LIBRARY_PATH' not in os.environ:
    os.environ['DYLD_LIBRARY_PATH'] = '/opt/homebrew/lib:/usr/local/lib'

import json
import re
import shutil
import sys
from pathlib import Path
from difflib import SequenceMatcher
from datetime import datetime, timezone

from PIL import Image, ImageTk
import tkinter as tk
from tkinter import ttk, messagebox

# ── Paths ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOGOS_DIR = PROJECT_ROOT / "output" / "brand_logos"
LOGOS_DB = PROJECT_ROOT / "output" / "brand_logos" / "brand_logo_database.json"
BRANDS_LEXICON = PROJECT_ROOT / "config" / "brands.json"


# ── Data helpers ───────────────────────────────────────────────────────

def load_database():
    if LOGOS_DB.exists():
        try:
            return json.loads(LOGOS_DB.read_text())
        except Exception:
            pass
    return {"brands": {}, "metadata": {"last_updated": None, "total_brands": 0}}


def save_database(db):
    db["metadata"]["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db["metadata"]["total_brands"] = len(db["brands"])
    sorted_brands = dict(sorted(db["brands"].items(), key=lambda x: x[0].lower()))
    db["brands"] = sorted_brands
    LOGOS_DB.write_text(json.dumps(db, indent=2, ensure_ascii=False))


def load_lexicon():
    if BRANDS_LEXICON.exists():
        try:
            return json.loads(BRANDS_LEXICON.read_text())
        except Exception:
            pass
    return []


def save_lexicon(lexicon):
    BRANDS_LEXICON.write_text(json.dumps(lexicon, indent=2, ensure_ascii=False))


def normalize_key(name):
    """Normalize a brand name to a database key.
    
    Preserves dots (e.g. 'e.l.f.' stays as 'e.l.f.'), hyphens,
    and apostrophes since they can be intentional brand styling.
    """
    key = name.lower().strip()
    key = re.sub(r'[®™©]', '', key)
    key = re.sub(r"[\u2018\u2019\u0060]", "'", key)  # smart quotes → apostrophe
    key = re.sub(r'\s+', '_', key)
    return key


def strip_key(k):
    """Strip a key down to bare alphanumeric for comparison."""
    return re.sub(r'[^a-z0-9]', '', k.lower())


def check_logo_quality(logo_path):
    """Returns 'good', 'poor', or 'missing'."""
    if not logo_path or not Path(logo_path).exists():
        return "missing"
    path = Path(logo_path)
    if path.suffix.lower() == '.svg':
        return "good"
    try:
        img = Image.open(path)
        w, h = img.size
        if w < 150 or h < 150:
            return "poor"
        has_alpha = img.mode in ('RGBA', 'LA', 'PA')
        if has_alpha:
            alpha = img.getchannel('A')
            min_alpha = min(alpha.getdata())
            if min_alpha < 250:
                return "good"
        rgb = img.convert('RGB')
        edge_pixels = [
            rgb.getpixel((0, 0)), rgb.getpixel((w-1, 0)),
            rgb.getpixel((0, h-1)), rgb.getpixel((w-1, h-1)),
        ]
        for x in (w//4, w//2, 3*w//4):
            edge_pixels.append(rgb.getpixel((x, 0)))
            edge_pixels.append(rgb.getpixel((x, h-1)))
        for y in (h//4, h//2, 3*h//4):
            edge_pixels.append(rgb.getpixel((0, y)))
            edge_pixels.append(rgb.getpixel((w-1, y)))
        white_count = sum(1 for r, g, b in edge_pixels if r > 240 and g > 240 and b > 240)
        if white_count / len(edge_pixels) >= 0.6:
            if w >= 200 and h >= 200:
                return "good"
            return "poor"
        return "poor"
    except Exception:
        return "poor"


# ── Cluster detection ──────────────────────────────────────────────────

def find_duplicate_clusters(db):
    """
    Find clusters of brand keys that likely refer to the same brand.
    
    Uses multiple heuristics:
    - Stripped alphanumeric comparison (catches punctuation/spacing diffs)
    - One key is the other with a _N suffix (e.g. starbucks vs starbucks_2)
    - High SequenceMatcher ratio on stripped keys
    """
    brands = db.get("brands", {})
    keys = sorted(brands.keys())
    
    # Build stripped-key → [original keys] map
    stripped_map = {}
    for k in keys:
        s = strip_key(k)
        stripped_map.setdefault(s, []).append(k)
    
    seen = set()
    clusters = []
    
    # Phase 1: exact stripped-key matches
    for s, group in stripped_map.items():
        if len(group) > 1:
            for k in group:
                seen.add(k)
            clusters.append(group)
    
    # Phase 2: _N suffix duplicates (e.g. "brand" and "brand_2")
    suffix_re = re.compile(r'^(.+?)_(\d+)$')
    for k in keys:
        if k in seen:
            continue
        m = suffix_re.match(k)
        if m:
            base = m.group(1)
            if base in brands and base not in seen:
                cluster = [base, k]
                # Check for more suffixes
                for n in range(3, 10):
                    candidate = f"{base}_{n}"
                    if candidate in brands:
                        cluster.append(candidate)
                for c in cluster:
                    seen.add(c)
                clusters.append(cluster)
    
    # Phase 3: fuzzy matching on remaining keys
    remaining = [k for k in keys if k not in seen]
    for i, k1 in enumerate(remaining):
        if k1 in seen:
            continue
        s1 = strip_key(k1)
        if len(s1) < 3:
            continue
        cluster = [k1]
        for k2 in remaining[i+1:]:
            if k2 in seen:
                continue
            s2 = strip_key(k2)
            if len(s2) < 3:
                continue
            ratio = SequenceMatcher(None, s1, s2).ratio()
            if ratio >= 0.85:
                cluster.append(k2)
                seen.add(k2)
        if len(cluster) > 1:
            seen.add(k1)
            clusters.append(cluster)
    
    # Filter out false positives: clusters where brand names are clearly different
    filtered = []
    for cluster in clusters:
        names = [brands[k].get("brand_name", k) for k in cluster]
        # If all stripped names are identical or very similar, keep
        stripped_names = [strip_key(n) for n in names]
        # Check pairwise similarity
        all_similar = True
        for i_idx in range(len(stripped_names)):
            for j_idx in range(i_idx + 1, len(stripped_names)):
                r = SequenceMatcher(None, stripped_names[i_idx], stripped_names[j_idx]).ratio()
                if r < 0.7:
                    all_similar = False
                    break
            if not all_similar:
                break
        if all_similar:
            filtered.append(cluster)
    
    return filtered


# ── Logo loading helper ────────────────────────────────────────────────

def resolve_logo_path(logo_file):
    """Resolve a logo_file value to an absolute path."""
    if not logo_file:
        return None
    # Handle various path formats in the database
    if logo_file.startswith("brand_logos/"):
        logo_file = logo_file.replace("brand_logos/", "")
    p = LOGOS_DIR / logo_file
    if p.exists():
        return p
    # Try verified/ prefix
    p2 = LOGOS_DIR / "verified" / Path(logo_file).name
    if p2.exists():
        return p2
    # Try unverified/ prefix
    p3 = LOGOS_DIR / "unverified" / Path(logo_file).name
    if p3.exists():
        return p3
    return None


def load_logo_thumbnail(logo_path, size=(200, 200)):
    """Load a logo as a PIL PhotoImage thumbnail. Returns (PhotoImage, dimensions_str, quality)."""
    if not logo_path or not Path(logo_path).exists():
        return None, "no file", "missing"
    
    quality = check_logo_quality(logo_path)
    path = Path(logo_path)
    
    try:
        if path.suffix.lower() == '.svg':
            # Try to render SVG
            try:
                from svglib.svglib import svg2rlg
                from reportlab.graphics import renderPM
                import io
                drawing = svg2rlg(str(path))
                if drawing:
                    png_data = renderPM.drawToString(drawing, fmt="PNG")
                    img = Image.open(io.BytesIO(png_data))
                else:
                    return None, "SVG render failed", quality
            except ImportError:
                return None, "SVG (no renderer)", quality
        else:
            img = Image.open(logo_path)
        
        w, h = img.size
        dims = f"{w}×{h}"
        
        # Convert to RGBA for display
        if img.mode not in ('RGBA', 'RGB'):
            img = img.convert('RGBA')
        
        img.thumbnail(size, Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        return photo, dims, quality
        
    except Exception as e:
        return None, f"error: {e}", quality


# ── GUI ────────────────────────────────────────────────────────────────

class BrandDedupTool:
    def __init__(self, root):
        self.root = root
        self.root.title("Brand Deduplication Tool")
        self.root.geometry("1050x700")
        self.root.minsize(900, 600)
        
        # Load data
        self.db = load_database()
        self.lexicon = load_lexicon()
        self.clusters = find_duplicate_clusters(self.db)
        
        self.current_index = 0
        self.merged_count = 0
        self.skipped_count = 0
        
        # Track PhotoImage references to prevent GC
        self._photo_refs = []
        
        self.setup_ui()
        
        if self.clusters:
            self.show_current_cluster()
        else:
            self.show_done_message("No duplicate clusters found!")
    
    def setup_ui(self):
        # ── Top status bar ──
        status_frame = ttk.Frame(self.root, padding=8)
        status_frame.pack(fill=tk.X)
        
        self.status_label = ttk.Label(status_frame, text="", font=("Helvetica", 13, "bold"))
        self.status_label.pack(side=tk.LEFT)
        
        self.progress_label = ttk.Label(status_frame, text="", font=("Helvetica", 11))
        self.progress_label.pack(side=tk.RIGHT)
        
        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X)
        
        # ── Main content area ──
        self.content_frame = ttk.Frame(self.root, padding=10)
        self.content_frame.pack(fill=tk.BOTH, expand=True)
        
        # ── Bottom action bar ──
        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X)
        action_frame = ttk.Frame(self.root, padding=10)
        action_frame.pack(fill=tk.X)
        
        self.merge_btn = ttk.Button(action_frame, text="✅  Merge Selected", command=self.do_merge)
        self.merge_btn.pack(side=tk.LEFT, padx=5)
        
        self.skip_btn = ttk.Button(action_frame, text="⏭  Skip (Not Duplicates)", command=self.do_skip)
        self.skip_btn.pack(side=tk.LEFT, padx=5)
        
        self.not_brand_btn = ttk.Button(action_frame, text="🗑  Delete All (Not a Brand)", command=self.do_delete_all)
        self.not_brand_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(action_frame, text="  Keyboard: M=merge  S=skip  D=delete", 
                  font=("Helvetica", 10), foreground="gray").pack(side=tk.RIGHT)
        
        # Key bindings — ignore when typing in an Entry widget
        def _if_not_entry(action):
            def handler(e):
                if not isinstance(e.widget, (tk.Entry, ttk.Entry)):
                    action()
            return handler
        
        self.root.bind('m', _if_not_entry(self.do_merge))
        self.root.bind('M', _if_not_entry(self.do_merge))
        self.root.bind('s', _if_not_entry(self.do_skip))
        self.root.bind('S', _if_not_entry(self.do_skip))
        self.root.bind('d', _if_not_entry(self.do_delete_all))
        self.root.bind('D', _if_not_entry(self.do_delete_all))
        self.root.bind('<Right>', _if_not_entry(self.do_skip))
        self.root.bind('<Return>', _if_not_entry(self.do_merge))
    
    def clear_content(self):
        for w in self.content_frame.winfo_children():
            w.destroy()
        self._photo_refs.clear()
    
    def show_current_cluster(self):
        self.clear_content()
        
        if self.current_index >= len(self.clusters):
            self.show_done_message()
            return
        
        cluster = self.clusters[self.current_index]
        brands = self.db.get("brands", {})
        
        # Update status
        total = len(self.clusters)
        self.status_label.config(
            text=f"Cluster {self.current_index + 1} of {total}  •  "
                 f"{len(cluster)} entries"
        )
        self.progress_label.config(
            text=f"Merged: {self.merged_count}  |  Skipped: {self.skipped_count}  |  "
                 f"Remaining: {total - self.current_index}"
        )
        
        # ── Name selection section ──
        name_frame = ttk.LabelFrame(self.content_frame, text="  Pick Best Name  ", padding=10)
        name_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.name_var = tk.StringVar(value=cluster[0])
        
        # Also allow custom name entry
        name_grid = ttk.Frame(name_frame)
        name_grid.pack(fill=tk.X)
        
        for i, key in enumerate(cluster):
            entry = brands.get(key, {})
            display_name = entry.get("brand_name", key)
            source = entry.get("source", "?")
            
            rb = ttk.Radiobutton(
                name_grid, text=f'"{display_name}"',
                variable=self.name_var, value=key,
                style="Name.TRadiobutton"
            )
            rb.grid(row=i, column=0, sticky=tk.W, padx=(0, 15))
            
            ttk.Label(name_grid, text=f"key: {key}", foreground="gray",
                     font=("Courier", 10)).grid(row=i, column=1, sticky=tk.W, padx=(0, 15))
            ttk.Label(name_grid, text=f"source: {source}", foreground="gray",
                     font=("Helvetica", 10)).grid(row=i, column=2, sticky=tk.W)
        
        # Custom name option — pre-fill with first entry's name for easy editing
        custom_row = len(cluster)
        first_name = brands.get(cluster[0], {}).get("brand_name", cluster[0])
        self.custom_name_var = tk.StringVar(value=first_name)
        rb_custom = ttk.Radiobutton(
            name_grid, text="Custom:",
            variable=self.name_var, value="__custom__"
        )
        rb_custom.grid(row=custom_row, column=0, sticky=tk.W, padx=(0, 15), pady=(5, 0))
        
        custom_entry = ttk.Entry(name_grid, textvariable=self.custom_name_var, width=40)
        custom_entry.grid(row=custom_row, column=1, columnspan=2, sticky=tk.W, pady=(5, 0))
        # Auto-select custom radio when user clicks/types in the entry
        custom_entry.bind("<FocusIn>", lambda e: self.name_var.set("__custom__"))
        
        # ── Logo selection section ──
        logo_frame = ttk.LabelFrame(self.content_frame, text="  Pick Best Logo  ", padding=10)
        logo_frame.pack(fill=tk.BOTH, expand=True)
        
        self.logo_var = tk.StringVar(value=cluster[0])
        
        # Create a scrollable frame for logos
        logo_canvas = tk.Canvas(logo_frame, highlightthickness=0)
        logo_scrollbar = ttk.Scrollbar(logo_frame, orient=tk.HORIZONTAL, command=logo_canvas.xview)
        logo_inner = ttk.Frame(logo_canvas)
        
        logo_inner.bind("<Configure>", lambda e: logo_canvas.configure(scrollregion=logo_canvas.bbox("all")))
        logo_canvas.create_window((0, 0), window=logo_inner, anchor=tk.NW)
        logo_canvas.configure(xscrollcommand=logo_scrollbar.set)
        
        logo_canvas.pack(fill=tk.BOTH, expand=True)
        logo_scrollbar.pack(fill=tk.X)
        
        for i, key in enumerate(cluster):
            entry = brands.get(key, {})
            display_name = entry.get("brand_name", key)
            logo_file = entry.get("logo_file", "")
            logo_path = resolve_logo_path(logo_file)
            
            # Card frame for each logo
            card = ttk.Frame(logo_inner, padding=10, relief=tk.RIDGE, borderwidth=1)
            card.grid(row=0, column=i, padx=8, pady=5, sticky=tk.N)
            
            # Radio button
            rb = ttk.Radiobutton(
                card, text=f'"{display_name}"',
                variable=self.logo_var, value=key
            )
            rb.pack(anchor=tk.W)
            
            # Logo preview
            preview_canvas = tk.Canvas(card, width=220, height=220, bg="#f0f0f0",
                                       highlightthickness=1, highlightbackground="#ccc")
            preview_canvas.pack(pady=5)
            
            photo, dims, quality = load_logo_thumbnail(logo_path, size=(210, 210))
            
            if photo:
                self._photo_refs.append(photo)
                preview_canvas.create_image(110, 110, image=photo, anchor=tk.CENTER)
            else:
                preview_canvas.create_text(110, 110, text="No Logo", fill="#999",
                                          font=("Helvetica", 14))
            
            # Quality indicator
            q_icon = {"good": "✅", "poor": "🟡", "missing": "❌"}.get(quality, "?")
            q_color = {"good": "green", "poor": "#B8860B", "missing": "red"}.get(quality, "gray")
            
            info_frame = ttk.Frame(card)
            info_frame.pack(fill=tk.X)
            
            ttk.Label(info_frame, text=f"{q_icon} {quality}", foreground=q_color,
                     font=("Helvetica", 11)).pack(side=tk.LEFT)
            ttk.Label(info_frame, text=dims, foreground="gray",
                     font=("Helvetica", 10)).pack(side=tk.RIGHT)
            
            # File path
            ttk.Label(card, text=logo_file or "(no file)", foreground="gray",
                     font=("Courier", 9), wraplength=200).pack(anchor=tk.W, pady=(3, 0))
            
            # Source info
            source = entry.get("source", "unknown")
            ttk.Label(card, text=f"src: {source}", foreground="gray",
                     font=("Helvetica", 9)).pack(anchor=tk.W)
            
            verified = entry.get("verified", False)
            v_text = "✓ verified" if verified else "✗ unverified"
            v_color = "green" if verified else "gray"
            ttk.Label(card, text=v_text, foreground=v_color,
                     font=("Helvetica", 9)).pack(anchor=tk.W)
    
    def show_done_message(self, msg=None):
        self.clear_content()
        if not msg:
            msg = (f"All done!\n\n"
                   f"Merged: {self.merged_count} clusters\n"
                   f"Skipped: {self.skipped_count} clusters\n\n"
                   f"Database and lexicon have been saved.")
        
        ttk.Label(self.content_frame, text=msg, font=("Helvetica", 16),
                 justify=tk.CENTER).pack(expand=True)
        
        self.merge_btn.config(state=tk.DISABLED)
        self.skip_btn.config(state=tk.DISABLED)
        self.not_brand_btn.config(state=tk.DISABLED)
        
        self.status_label.config(text="Complete")
        self.progress_label.config(
            text=f"Merged: {self.merged_count}  |  Skipped: {self.skipped_count}"
        )
    
    def do_skip(self):
        """Skip this cluster — they are not duplicates."""
        self.skipped_count += 1
        self.current_index += 1
        self.show_current_cluster()
    
    def do_delete_all(self):
        """Delete all entries in this cluster (none are real brands)."""
        cluster = self.clusters[self.current_index]
        brands = self.db.get("brands", {})
        
        names = [brands.get(k, {}).get("brand_name", k) for k in cluster]
        confirm = messagebox.askyesno(
            "Delete All",
            f"Delete ALL {len(cluster)} entries?\n\n" +
            "\n".join(f"  • {n}" for n in names) +
            "\n\nThis removes them from the logo database.\n"
            "Logo files will NOT be deleted from disk."
        )
        if not confirm:
            return
        
        for key in cluster:
            if key in brands:
                del brands[key]
        
        save_database(self.db)
        self.current_index += 1
        self.show_current_cluster()
    
    def do_merge(self):
        """Merge the cluster using selected name and logo."""
        cluster = self.clusters[self.current_index]
        brands = self.db.get("brands", {})
        
        if len(cluster) < 2:
            self.do_skip()
            return
        
        # Determine winning name
        name_winner_key = self.name_var.get()
        if name_winner_key == "__custom__":
            custom = self.custom_name_var.get().strip()
            if not custom:
                messagebox.showwarning("Custom Name", "Please enter a custom name or select one above.")
                return
            winning_name = custom
        else:
            winning_name = brands.get(name_winner_key, {}).get("brand_name", name_winner_key)
        
        # Determine winning logo
        logo_winner_key = self.logo_var.get()
        logo_winner_entry = brands.get(logo_winner_key, {})
        winning_logo_file = logo_winner_entry.get("logo_file", "")
        
        # Build the merged entry
        # Start from the logo winner's entry (preserves metadata)
        merged = dict(logo_winner_entry)
        merged["brand_name"] = winning_name
        merged["logo_file"] = winning_logo_file
        merged["verified"] = True
        merged["verified_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        merged["dedup_merged_from"] = cluster  # audit trail
        
        # Determine the canonical key for the merged entry
        new_key = normalize_key(winning_name)
        
        # Collect all brand names from the cluster (for synonyms)
        all_names = set()
        all_logo_urls = set()
        for key in cluster:
            entry = brands.get(key, {})
            bn = entry.get("brand_name", "")
            if bn:
                all_names.add(bn)
            url = entry.get("logo_url")
            if url:
                all_logo_urls.add(url)
        
        # Remove the winning name from synonym candidates
        synonym_names = all_names - {winning_name}
        
        # Remove all old cluster entries from the database
        for key in cluster:
            if key in brands:
                del brands[key]
        
        # Add the merged entry
        brands[new_key] = merged
        
        # ── Update the lexicon ──
        # Find the lexicon entry for the winning name (or any cluster name)
        lex_entry = None
        lex_indices = []
        for idx, entry in enumerate(self.lexicon):
            lex_name = entry.get("name", "").lower()
            for key in cluster:
                brand_name = self.db.get("brands", brands).get(key, {}).get("brand_name", key)
                # Check by key or name
                if lex_name == key.lower() or lex_name == brand_name.lower() or lex_name == winning_name.lower():
                    lex_indices.append(idx)
                    break
                # Check synonyms
                for syn in entry.get("synonyms", []):
                    if syn.lower() == key.lower() or syn.lower() == brand_name.lower():
                        lex_indices.append(idx)
                        break
        
        lex_indices = sorted(set(lex_indices))
        
        if lex_indices:
            # Merge all matching lexicon entries into one
            primary_idx = lex_indices[0]
            primary_entry = self.lexicon[primary_idx]
            
            # Collect all synonyms from all matching entries
            all_syns = set(primary_entry.get("synonyms", []))
            for idx in lex_indices[1:]:
                other = self.lexicon[idx]
                other_name = other.get("name", "")
                if other_name and other_name != winning_name:
                    all_syns.add(other_name)
                all_syns.update(other.get("synonyms", []))
            
            # Add the loser names as synonyms
            for sn in synonym_names:
                if sn != winning_name:
                    all_syns.add(sn)
            
            # Remove the winning name from synonyms if present
            all_syns.discard(winning_name)
            
            # Update primary entry
            primary_entry["name"] = winning_name
            primary_entry["synonyms"] = sorted(all_syns)
            primary_entry["verified"] = True
            
            # Remove duplicate lexicon entries (in reverse order to preserve indices)
            for idx in reversed(lex_indices[1:]):
                self.lexicon.pop(idx)
        else:
            # No lexicon entry found — create one
            new_lex = {
                "name": winning_name,
                "synonyms": sorted(synonym_names),
                "verified": True,
            }
            self.lexicon.append(new_lex)
        
        # Rename the logo file if the key changed
        if winning_logo_file:
            old_path = resolve_logo_path(winning_logo_file)
            if old_path and old_path.exists():
                ext = old_path.suffix
                new_filename = f"verified/{new_key}{ext}"
                new_path = LOGOS_DIR / new_filename
                if old_path != new_path:
                    try:
                        new_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(str(old_path), str(new_path))
                        merged["logo_file"] = new_filename
                    except Exception as e:
                        print(f"  ⚠️  Could not copy logo: {e}")
        
        # Save
        save_database(self.db)
        save_lexicon(self.lexicon)
        
        print(f"  ✅ Merged: {cluster} → \"{winning_name}\" (key={new_key}, logo={winning_logo_file})")
        
        self.merged_count += 1
        self.current_index += 1
        self.show_current_cluster()


# ── Main ───────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    
    # Style
    style = ttk.Style()
    style.configure("Name.TRadiobutton", font=("Helvetica", 12))
    
    app = BrandDedupTool(root)
    root.mainloop()


if __name__ == "__main__":
    main()
