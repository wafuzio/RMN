#!/usr/bin/env python3
"""
Video Overlay Calibration Tool

Visual tool for calibrating video overlay bounds on ad screenshots.
- Groups ads by video file (same video = same overlay)
- Shows image with adjustable overlay rectangle
- Approved overlays are saved and applied to all matching ads

Usage:
    python video_overlay_calibration_tool.py
    python video_overlay_calibration_tool.py --retailer walmart
"""

import json
import hashlib
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from PIL import Image, ImageTk, ImageDraw
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import os

# Configuration
OUTPUT_ROOT = Path("/Users/dan.maguire/Documents/Amazon_Scrape/output")
CALIBRATION_DB_PATH = Path("/Users/dan.maguire/Documents/Amazon_Scrape/config/video_overlay_calibrations.json")

# Video ad types to process
VIDEO_AD_TYPES = ['SBV', 'Sponsored_Brand_Video', 'Shoppable_Video_Ad', 'Shoppable_Video_Ads']


def get_video_hash(video_path: Path) -> Optional[str]:
    """Get a hash of the video file for deduplication."""
    if not video_path.exists():
        return None
    try:
        # Use file size + first 8KB for quick hash
        size = video_path.stat().st_size
        with open(video_path, 'rb') as f:
            data = f.read(8192)
        return hashlib.md5(f"{size}:{data}".encode() if isinstance(data, str) else f"{size}:".encode() + data).hexdigest()[:12]
    except Exception:
        return None


def get_image_hash(image_path: Path) -> Optional[str]:
    """Get MD5 hash of image file for pixel-perfect matching."""
    if not image_path.exists():
        return None
    try:
        with open(image_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    except Exception:
        return None


def get_video_signature(ad: dict, client_root: Path) -> Optional[str]:
    """
    Get a signature for the ad based on image hash.
    Only pixel-perfect identical images will share the same signature.
    Returns: (signature, image_hash) tuple
    """
    image_path_rel = ad.get('image_path')
    image_hash = None
    
    if image_path_rel:
        image_path = client_root / image_path_rel
        image_hash = get_image_hash(image_path)
    
    if image_hash:
        # Use image hash as signature - only identical images match
        return f"img_{image_hash[:16]}"
    
    # Fallback: no image found, return None (skip this ad)
    return None


def load_calibration_db() -> Dict:
    """Load the calibration database."""
    if CALIBRATION_DB_PATH.exists():
        try:
            return json.loads(CALIBRATION_DB_PATH.read_text())
        except Exception:
            pass
    return {"calibrations": {}, "applied_count": 0}


def save_calibration_db(db: Dict):
    """Save the calibration database."""
    CALIBRATION_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    CALIBRATION_DB_PATH.write_text(json.dumps(db, indent=2))


def find_video_ads() -> Dict[str, List[dict]]:
    """
    Find all video ads and group them by image hash (pixel-perfect matching).
    Returns: {signature: [list of (ad, json_path, client_root) tuples]}
    """
    grouped = defaultdict(list)
    
    for retailer_dir in OUTPUT_ROOT.iterdir():
        if not retailer_dir.is_dir():
            continue
        retailer = retailer_dir.name
        
        for client_dir in retailer_dir.iterdir():
            if not client_dir.is_dir():
                continue
            
            runs_dir = client_dir / "runs"
            if not runs_dir.exists():
                continue
            
            for json_file in runs_dir.glob("*/run_results_*.json"):
                try:
                    data = json.loads(json_file.read_text())
                    ads = data.get('ads', [])
                    
                    for ad in ads:
                        ad_type = ad.get('type') or ad.get('ad_type', '')
                        if ad_type not in VIDEO_AD_TYPES:
                            continue
                        
                        sig = get_video_signature(ad, client_dir)
                        if sig:
                            grouped[sig].append({
                                'ad': ad,
                                'json_path': json_file,
                                'client_root': client_dir,
                                'retailer': retailer,
                                'ad_type': ad_type,
                                'brand': ad.get('brand', 'unknown'),
                            })
                except Exception as e:
                    print(f"Error reading {json_file}: {e}")
    
    return dict(grouped)


class VideoOverlayCalibrationTool:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Video Overlay Calibration Tool")
        self.root.geometry("1400x900")
        
        # Data
        self.calibration_db = load_calibration_db()
        self.video_groups = {}
        self.current_signature = None
        self.current_image = None
        self.current_photo = None
        self.current_ad_info = None
        
        # Overlay bounds (will be set per image)
        self.overlay_x = tk.IntVar(value=0)
        self.overlay_y = tk.IntVar(value=0)
        self.overlay_width = tk.IntVar(value=100)
        self.overlay_height = tk.IntVar(value=100)
        self.border_radius = tk.IntVar(value=0)  # Rounded corners
        self.image_width = 0
        self.image_height = 0
        
        # Canvas drag state
        self.drag_start = None
        self.drag_mode = None  # 'move', 'resize_br', etc.
        
        self._build_ui()
        self._load_data()
    
    def _build_ui(self):
        # Main layout: left panel (list), center (image), right panel (controls)
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left panel - video signature list
        left_frame = ttk.LabelFrame(main_frame, text="Video Ads (by signature)")
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        
        # Filter frame
        filter_frame = ttk.Frame(left_frame)
        filter_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(filter_frame, text="Filter:").pack(side=tk.LEFT)
        self.filter_var = tk.StringVar()
        self.filter_var.trace('w', self._filter_list)
        filter_entry = ttk.Entry(filter_frame, textvariable=self.filter_var, width=20)
        filter_entry.pack(side=tk.LEFT, padx=5)
        
        # Show only uncalibrated checkbox
        self.show_uncalibrated = tk.BooleanVar(value=True)
        ttk.Checkbutton(filter_frame, text="Uncalibrated only", 
                       variable=self.show_uncalibrated, 
                       command=self._filter_list).pack(side=tk.LEFT)
        
        # Listbox with scrollbar
        list_frame = ttk.Frame(left_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.sig_listbox = tk.Listbox(list_frame, width=35, height=30, 
                                       yscrollcommand=scrollbar.set)
        self.sig_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.sig_listbox.yview)
        self.sig_listbox.bind('<<ListboxSelect>>', self._on_select_signature)
        
        # Stats label
        self.stats_label = ttk.Label(left_frame, text="")
        self.stats_label.pack(pady=5)
        
        # Center panel - image canvas
        center_frame = ttk.LabelFrame(main_frame, text="Preview")
        center_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        self.canvas = tk.Canvas(center_frame, bg='#333', width=800, height=600)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.canvas.bind('<Button-1>', self._on_canvas_click)
        self.canvas.bind('<B1-Motion>', self._on_canvas_drag)
        self.canvas.bind('<ButtonRelease-1>', self._on_canvas_release)
        
        # Right panel - controls
        right_frame = ttk.LabelFrame(main_frame, text="Overlay Controls")
        right_frame.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Info section
        info_frame = ttk.LabelFrame(right_frame, text="Current Ad")
        info_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.info_label = ttk.Label(info_frame, text="Select an ad from the list", 
                                    wraplength=250, justify=tk.LEFT)
        self.info_label.pack(padx=5, pady=5)
        
        # Overlay bounds controls
        bounds_frame = ttk.LabelFrame(right_frame, text="Overlay Bounds")
        bounds_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # X position
        row = ttk.Frame(bounds_frame)
        row.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(row, text="X:", width=8).pack(side=tk.LEFT)
        self.x_spinbox = ttk.Spinbox(row, from_=0, to=2000, textvariable=self.overlay_x, 
                                      width=8, command=self._update_preview)
        self.x_spinbox.pack(side=tk.LEFT)
        self.x_spinbox.bind('<Return>', lambda e: self._update_preview())
        
        # Y position
        row = ttk.Frame(bounds_frame)
        row.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(row, text="Y:", width=8).pack(side=tk.LEFT)
        self.y_spinbox = ttk.Spinbox(row, from_=0, to=2000, textvariable=self.overlay_y,
                                      width=8, command=self._update_preview)
        self.y_spinbox.pack(side=tk.LEFT)
        self.y_spinbox.bind('<Return>', lambda e: self._update_preview())
        
        # Width
        row = ttk.Frame(bounds_frame)
        row.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(row, text="Width:", width=8).pack(side=tk.LEFT)
        self.w_spinbox = ttk.Spinbox(row, from_=1, to=2000, textvariable=self.overlay_width,
                                      width=8, command=self._update_preview)
        self.w_spinbox.pack(side=tk.LEFT)
        self.w_spinbox.bind('<Return>', lambda e: self._update_preview())
        
        # Height
        row = ttk.Frame(bounds_frame)
        row.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(row, text="Height:", width=8).pack(side=tk.LEFT)
        self.h_spinbox = ttk.Spinbox(row, from_=1, to=2000, textvariable=self.overlay_height,
                                      width=8, command=self._update_preview)
        self.h_spinbox.pack(side=tk.LEFT)
        self.h_spinbox.bind('<Return>', lambda e: self._update_preview())
        
        # Border radius
        row = ttk.Frame(bounds_frame)
        row.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(row, text="Radius:", width=8).pack(side=tk.LEFT)
        self.r_spinbox = ttk.Spinbox(row, from_=0, to=50, textvariable=self.border_radius,
                                      width=8, command=self._update_preview)
        self.r_spinbox.pack(side=tk.LEFT)
        self.r_spinbox.bind('<Return>', lambda e: self._update_preview())
        
        # Quick adjust buttons
        adjust_frame = ttk.LabelFrame(right_frame, text="Quick Adjust")
        adjust_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Nudge buttons
        nudge_frame = ttk.Frame(adjust_frame)
        nudge_frame.pack(pady=5)
        
        ttk.Button(nudge_frame, text="↑", width=3, 
                  command=lambda: self._nudge(0, -1)).grid(row=0, column=1)
        ttk.Button(nudge_frame, text="←", width=3,
                  command=lambda: self._nudge(-1, 0)).grid(row=1, column=0)
        ttk.Button(nudge_frame, text="→", width=3,
                  command=lambda: self._nudge(1, 0)).grid(row=1, column=2)
        ttk.Button(nudge_frame, text="↓", width=3,
                  command=lambda: self._nudge(0, 1)).grid(row=2, column=1)
        
        # Size adjust
        size_frame = ttk.Frame(adjust_frame)
        size_frame.pack(pady=5)
        
        ttk.Button(size_frame, text="W+", width=4,
                  command=lambda: self._resize(1, 0)).pack(side=tk.LEFT, padx=2)
        ttk.Button(size_frame, text="W-", width=4,
                  command=lambda: self._resize(-1, 0)).pack(side=tk.LEFT, padx=2)
        ttk.Button(size_frame, text="H+", width=4,
                  command=lambda: self._resize(0, 1)).pack(side=tk.LEFT, padx=2)
        ttk.Button(size_frame, text="H-", width=4,
                  command=lambda: self._resize(0, -1)).pack(side=tk.LEFT, padx=2)
        
        # Presets
        preset_frame = ttk.LabelFrame(right_frame, text="Presets")
        preset_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(preset_frame, text="Walmart SBV Default",
                  command=self._preset_walmart_sbv).pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(preset_frame, text="Instacart Video Default",
                  command=self._preset_instacart_video).pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(preset_frame, text="Left Half",
                  command=self._preset_left_half).pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(preset_frame, text="Auto-detect (CV)",
                  command=self._auto_detect).pack(fill=tk.X, padx=5, pady=2)
        
        # Action buttons
        action_frame = ttk.Frame(right_frame)
        action_frame.pack(fill=tk.X, padx=5, pady=10)
        
        ttk.Button(action_frame, text="✓ Approve & Apply to All",
                  command=self._approve_calibration).pack(fill=tk.X, pady=2)
        ttk.Button(action_frame, text="Skip",
                  command=self._skip_to_next).pack(fill=tk.X, pady=2)
        ttk.Button(action_frame, text="Clear Calibration",
                  command=self._clear_calibration).pack(fill=tk.X, pady=2)
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    
    def _load_data(self):
        """Load video ads data."""
        self.status_var.set("Loading video ads...")
        self.root.update()
        
        self.video_groups = find_video_ads()
        self._filter_list()
        
        total_ads = sum(len(v) for v in self.video_groups.values())
        calibrated = len(self.calibration_db.get('calibrations', {}))
        self.stats_label.config(text=f"{len(self.video_groups)} unique videos\n{total_ads} total ads\n{calibrated} calibrated")
        self.status_var.set(f"Loaded {len(self.video_groups)} video signatures")
    
    def _filter_list(self, *args):
        """Filter the signature list."""
        self.sig_listbox.delete(0, tk.END)
        
        filter_text = self.filter_var.get().lower()
        show_uncalibrated = self.show_uncalibrated.get()
        calibrations = self.calibration_db.get('calibrations', {})
        
        for sig in sorted(self.video_groups.keys()):
            items = self.video_groups[sig]
            brand = items[0].get('brand', 'unknown') if items else 'unknown'
            retailer = items[0].get('retailer', '') if items else ''
            is_calibrated = sig in calibrations
            
            # Apply filters - search in brand, retailer, and signature
            searchable = f"{brand} {retailer} {sig}".lower()
            if filter_text and filter_text not in searchable:
                continue
            # When "Uncalibrated only" is checked, skip calibrated items
            if show_uncalibrated and is_calibrated:
                continue
            
            count = len(items)
            status = "✓" if is_calibrated else "○"
            # Store full signature at end for reliable extraction
            self.sig_listbox.insert(tk.END, f"{status} {brand} [{retailer}] ({count}) | {sig}")
    
    def _auto_save_current(self):
        """Auto-save current calibration to DB and apply to JSON files."""
        if self.current_signature is None or self.image_width == 0:
            return
        
        calibration = {
            'x': self.overlay_x.get(),
            'y': self.overlay_y.get(),
            'width': self.overlay_width.get(),
            'height': self.overlay_height.get(),
            'border_radius': self.border_radius.get(),
            'image_width': self.image_width,
            'image_height': self.image_height,
        }
        
        if 'calibrations' not in self.calibration_db:
            self.calibration_db['calibrations'] = {}
        self.calibration_db['calibrations'][self.current_signature] = calibration
        save_calibration_db(self.calibration_db)
        
        # Apply to all JSON files immediately
        self._apply_calibration_to_json(self.current_signature, calibration)
    
    def _apply_calibration_to_json(self, signature: str, calibration: dict):
        """Apply calibration to all matching ads in JSON files."""
        if signature not in self.video_groups:
            return
        
        ads = self.video_groups[signature]
        updated_files = set()
        
        for ad_info in ads:
            json_path = ad_info['json_path']
            updated_files.add(json_path)
        
        # Save all modified JSON files
        for json_path in updated_files:
            try:
                data = json.loads(json_path.read_text())
                for ad in data.get('ads', []):
                    sig = get_video_signature(ad, json_path.parent.parent.parent)
                    if sig == signature:
                        ad['video_overlay'] = {
                            'x': calibration['x'],
                            'y': calibration['y'],
                            'width': calibration['width'],
                            'height': calibration['height'],
                            'border_radius': calibration.get('border_radius', 0),
                            'image_width': calibration['image_width'],
                            'image_height': calibration['image_height'],
                        }
                json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            except Exception as e:
                print(f"Error saving {json_path}: {e}")
    
    def _on_select_signature(self, event):
        """Handle signature selection."""
        # Auto-save current calibration before switching
        self._auto_save_current()
        
        selection = self.sig_listbox.curselection()
        if not selection:
            return
        
        item = self.sig_listbox.get(selection[0])
        # Extract signature after the pipe separator
        # Format: "○ Brand [retailer] (count) | img_hash"
        if ' | ' in item:
            sig = item.split(' | ')[-1].strip()
        else:
            # Fallback for old format
            parts = item.split()
            sig = parts[-1] if parts else None
        
        if not sig or sig not in self.video_groups:
            print(f"Signature not found: {sig}")
            return
        
        self.current_signature = sig
        ads = self.video_groups[sig]
        
        # Find an ad with an existing image
        for ad_info in ads:
            ad = ad_info['ad']
            client_root = ad_info['client_root']
            image_path_rel = ad.get('image_path')
            if image_path_rel:
                image_path = client_root / image_path_rel
                if image_path.exists():
                    self.current_ad_info = ad_info
                    self._load_image(image_path)
                    
                    # Load existing calibration if any
                    if sig in self.calibration_db.get('calibrations', {}):
                        cal = self.calibration_db['calibrations'][sig]
                        self.overlay_x.set(cal['x'])
                        self.overlay_y.set(cal['y'])
                        self.overlay_width.set(cal['width'])
                        self.overlay_height.set(cal['height'])
                        self.border_radius.set(cal.get('border_radius', 0))
                    else:
                        # Set initial overlay from ad or default
                        existing = ad.get('video_overlay')
                        if existing:
                            self.overlay_x.set(existing.get('x', 0))
                            self.overlay_y.set(existing.get('y', 0))
                            self.overlay_width.set(existing.get('width', self.image_width // 2))
                            self.overlay_height.set(existing.get('height', self.image_height))
                            self.border_radius.set(existing.get('border_radius', 0))
                        else:
                            # Apply retailer-specific default
                            if ad_info['retailer'] == 'instacart':
                                self._preset_instacart_video()
                            else:
                                self._preset_walmart_sbv()
                    
                    # Update info
                    self.info_label.config(text=f"Signature: {sig}\n"
                                                f"Retailer: {ad_info['retailer']}\n"
                                                f"Type: {ad_info['ad_type']}\n"
                                                f"Brand: {ad.get('brand', 'unknown')}\n"
                                                f"Instances: {len(ads)}")
                    self._update_preview()
                    return
        
        self.status_var.set(f"No image found for {sig}")
    
    def _load_image(self, image_path: Path):
        """Load and display an image."""
        try:
            img = Image.open(image_path)
            self.image_width, self.image_height = img.size
            
            # Scale to fit canvas while maintaining aspect ratio
            canvas_w = self.canvas.winfo_width() or 800
            canvas_h = self.canvas.winfo_height() or 600
            
            scale = min(canvas_w / self.image_width, canvas_h / self.image_height, 1.0)
            self.display_scale = scale
            
            new_w = int(self.image_width * scale)
            new_h = int(self.image_height * scale)
            
            self.current_image = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            self._update_preview()
            
        except Exception as e:
            self.status_var.set(f"Error loading image: {e}")
    
    def _update_preview(self, *args):
        """Update the canvas with current overlay."""
        if self.current_image is None:
            return
        
        # Create a copy to draw on
        img = self.current_image.copy()
        draw = ImageDraw.Draw(img)
        
        # Scale overlay bounds to display size
        scale = self.display_scale
        x = int(self.overlay_x.get() * scale)
        y = int(self.overlay_y.get() * scale)
        w = int(self.overlay_width.get() * scale)
        h = int(self.overlay_height.get() * scale)
        r = int(self.border_radius.get() * scale)  # Scaled border radius
        
        # Draw overlay rectangle (with rounded corners if radius > 0)
        if r > 0:
            # Draw rounded rectangle using arcs and lines
            draw.arc([x, y, x + 2*r, y + 2*r], 180, 270, fill='#00FF00', width=2)
            draw.arc([x + w - 2*r, y, x + w, y + 2*r], 270, 360, fill='#00FF00', width=2)
            draw.arc([x, y + h - 2*r, x + 2*r, y + h], 90, 180, fill='#00FF00', width=2)
            draw.arc([x + w - 2*r, y + h - 2*r, x + w, y + h], 0, 90, fill='#00FF00', width=2)
            # Connect with lines
            draw.line([x + r, y, x + w - r, y], fill='#00FF00', width=2)  # Top
            draw.line([x + r, y + h, x + w - r, y + h], fill='#00FF00', width=2)  # Bottom
            draw.line([x, y + r, x, y + h - r], fill='#00FF00', width=2)  # Left
            draw.line([x + w, y + r, x + w, y + h - r], fill='#00FF00', width=2)  # Right
        else:
            draw.rectangle([x, y, x + w, y + h], outline='#00FF00', width=2)
        
        # Draw corner handles
        handle_size = 8
        for cx, cy in [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]:
            draw.rectangle([cx - handle_size//2, cy - handle_size//2,
                           cx + handle_size//2, cy + handle_size//2],
                          fill='#00FF00', outline='#00FF00')
        
        # Draw center crosshair
        cx, cy = x + w//2, y + h//2
        draw.line([cx - 10, cy, cx + 10, cy], fill='#00FF00', width=1)
        draw.line([cx, cy - 10, cx, cy + 10], fill='#00FF00', width=1)
        
        # Update canvas
        self.current_photo = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        
        # Position image on canvas with more left margin
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        left_margin = 50  # Extra left margin for visibility
        img_x = left_margin + (canvas_w - img.width - left_margin) // 2
        img_y = (canvas_h - img.height) // 2
        self.img_offset = (img_x, img_y)
        
        self.canvas.create_image(img_x, img_y, anchor=tk.NW, image=self.current_photo)
    
    def _on_canvas_click(self, event):
        """Handle canvas click for drag start."""
        if self.current_image is None:
            return
        
        # Convert to image coordinates
        img_x, img_y = self.img_offset
        x = (event.x - img_x) / self.display_scale
        y = (event.y - img_y) / self.display_scale
        
        # Check if clicking on overlay
        ox, oy = self.overlay_x.get(), self.overlay_y.get()
        ow, oh = self.overlay_width.get(), self.overlay_height.get()
        
        # Check corners first (for resize)
        corner_size = 15
        if abs(x - (ox + ow)) < corner_size and abs(y - (oy + oh)) < corner_size:
            self.drag_mode = 'resize_br'
        elif abs(x - ox) < corner_size and abs(y - oy) < corner_size:
            self.drag_mode = 'resize_tl'
        elif ox <= x <= ox + ow and oy <= y <= oy + oh:
            self.drag_mode = 'move'
        else:
            self.drag_mode = None
            return
        
        self.drag_start = (x, y, ox, oy, ow, oh)
    
    def _on_canvas_drag(self, event):
        """Handle canvas drag."""
        if self.drag_start is None or self.drag_mode is None:
            return
        
        img_x, img_y = self.img_offset
        x = (event.x - img_x) / self.display_scale
        y = (event.y - img_y) / self.display_scale
        
        start_x, start_y, ox, oy, ow, oh = self.drag_start
        dx = x - start_x
        dy = y - start_y
        
        if self.drag_mode == 'move':
            self.overlay_x.set(max(0, int(ox + dx)))
            self.overlay_y.set(max(0, int(oy + dy)))
        elif self.drag_mode == 'resize_br':
            self.overlay_width.set(max(10, int(ow + dx)))
            self.overlay_height.set(max(10, int(oh + dy)))
        elif self.drag_mode == 'resize_tl':
            new_x = max(0, int(ox + dx))
            new_y = max(0, int(oy + dy))
            self.overlay_x.set(new_x)
            self.overlay_y.set(new_y)
            self.overlay_width.set(max(10, int(ow - dx)))
            self.overlay_height.set(max(10, int(oh - dy)))
        
        self._update_preview()
    
    def _on_canvas_release(self, event):
        """Handle canvas release."""
        self.drag_start = None
        self.drag_mode = None
    
    def _nudge(self, dx: int, dy: int):
        """Nudge overlay position."""
        self.overlay_x.set(max(0, self.overlay_x.get() + dx))
        self.overlay_y.set(max(0, self.overlay_y.get() + dy))
        self._update_preview()
    
    def _resize(self, dw: int, dh: int):
        """Resize overlay."""
        self.overlay_width.set(max(10, self.overlay_width.get() + dw))
        self.overlay_height.set(max(10, self.overlay_height.get() + dh))
        self._update_preview()
    
    def _preset_walmart_sbv(self):
        """Apply Walmart SBV default overlay."""
        if self.image_width == 0:
            return
        # Based on calibrated values: x=2, y=15, width=539, height=302 on 1078x333
        self.overlay_x.set(2)
        self.overlay_y.set(round(self.image_height * 0.045))
        self.overlay_width.set(round(self.image_width * 0.50))
        self.overlay_height.set(round(self.image_height * 0.907))
        self.border_radius.set(0)  # Walmart has no rounded corners
        self._update_preview()
    
    def _preset_instacart_video(self):
        """Apply Instacart Shoppable Video default overlay."""
        if self.image_width == 0:
            return
        # Instacart videos are more inset with rounded corners
        # Based on screenshot: ~24px left margin, ~90px top margin, rounded corners ~8px
        self.overlay_x.set(24)
        self.overlay_y.set(round(self.image_height * 0.14))  # ~14% from top
        self.overlay_width.set(round(self.image_width * 0.35))  # Narrower than Walmart
        self.overlay_height.set(round(self.image_height * 0.45))  # Shorter proportionally
        self.border_radius.set(8)  # Rounded corners
        self._update_preview()
    
    def _preset_left_half(self):
        """Apply left half preset."""
        if self.image_width == 0:
            return
        self.overlay_x.set(0)
        self.overlay_y.set(0)
        self.overlay_width.set(self.image_width // 2)
        self.overlay_height.set(self.image_height)
        self._update_preview()
    
    def _auto_detect(self):
        """Try to auto-detect overlay using CV."""
        if self.current_ad_info is None:
            return
        
        try:
            # Import CV detection
            from scripts.detect_video_overlay_cv import detect_video_overlay
            
            ad = self.current_ad_info['ad']
            client_root = self.current_ad_info['client_root']
            image_path = client_root / ad.get('image_path', '')
            
            if image_path.exists():
                result = detect_video_overlay(
                    image_path,
                    self.current_ad_info['retailer'],
                    self.current_ad_info['ad_type']
                )
                if result:
                    self.overlay_x.set(result['x'])
                    self.overlay_y.set(result['y'])
                    self.overlay_width.set(result['width'])
                    self.overlay_height.set(result['height'])
                    self._update_preview()
                    self.status_var.set(f"Auto-detected: {result.get('detection_method', 'unknown')} (conf={result.get('confidence', 0):.2f})")
                else:
                    self.status_var.set("Auto-detection failed")
        except Exception as e:
            self.status_var.set(f"Auto-detect error: {e}")
    
    def _approve_calibration(self):
        """Approve current calibration and apply to all matching ads."""
        if self.current_signature is None:
            return
        
        calibration = {
            'x': self.overlay_x.get(),
            'y': self.overlay_y.get(),
            'width': self.overlay_width.get(),
            'height': self.overlay_height.get(),
            'border_radius': self.border_radius.get(),
            'image_width': self.image_width,
            'image_height': self.image_height,
            'pending': False,  # Mark as applied
        }
        
        # Save to calibration DB
        if 'calibrations' not in self.calibration_db:
            self.calibration_db['calibrations'] = {}
        self.calibration_db['calibrations'][self.current_signature] = calibration
        save_calibration_db(self.calibration_db)
        
        # Apply to all matching ads
        ads = self.video_groups[self.current_signature]
        updated_files = set()
        
        for ad_info in ads:
            json_path = ad_info['json_path']
            ad = ad_info['ad']
            
            # Calculate scaled overlay for this specific ad's image dimensions
            ad_overlay = dict(calibration)
            
            # If this ad has different image dimensions, scale proportionally
            existing = ad.get('video_overlay', {})
            if existing.get('image_width') and existing.get('image_height'):
                scale_x = existing['image_width'] / calibration['image_width']
                scale_y = existing['image_height'] / calibration['image_height']
                ad_overlay = {
                    'x': round(calibration['x'] * scale_x),
                    'y': round(calibration['y'] * scale_y),
                    'width': round(calibration['width'] * scale_x),
                    'height': round(calibration['height'] * scale_y),
                    'image_width': existing['image_width'],
                    'image_height': existing['image_height'],
                }
            
            ad['video_overlay'] = ad_overlay
            updated_files.add(json_path)
        
        # Save all modified JSON files
        for json_path in updated_files:
            try:
                # Re-read to get full data
                data = json.loads(json_path.read_text())
                # Find and update matching ads
                for ad in data.get('ads', []):
                    sig = get_video_signature(ad, json_path.parent.parent.parent)
                    if sig == self.current_signature:
                        ad['video_overlay'] = calibration
                json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            except Exception as e:
                print(f"Error saving {json_path}: {e}")
        
        self.status_var.set(f"✓ Applied calibration to {len(ads)} ads in {len(updated_files)} files")
        
        # Update stats and move to next
        self.calibration_db['applied_count'] = self.calibration_db.get('applied_count', 0) + len(ads)
        save_calibration_db(self.calibration_db)
        
        self._filter_list()
        self._skip_to_next()
    
    def _skip_to_next(self):
        """Skip to next uncalibrated signature."""
        current_idx = self.sig_listbox.curselection()
        if current_idx:
            next_idx = current_idx[0] + 1
            if next_idx < self.sig_listbox.size():
                self.sig_listbox.selection_clear(0, tk.END)
                self.sig_listbox.selection_set(next_idx)
                self.sig_listbox.see(next_idx)
                self._on_select_signature(None)
    
    def _clear_calibration(self):
        """Clear calibration for current signature."""
        if self.current_signature is None:
            return
        
        if self.current_signature in self.calibration_db.get('calibrations', {}):
            del self.calibration_db['calibrations'][self.current_signature]
            save_calibration_db(self.calibration_db)
            self._filter_list()
            self.status_var.set(f"Cleared calibration for {self.current_signature}")


def main():
    root = tk.Tk()
    app = VideoOverlayCalibrationTool(root)
    root.mainloop()


if __name__ == '__main__':
    main()
