#!/usr/bin/env python3
"""
Slot Inspector — side-by-side visual validation tool.

Left panel:  zoomable, scrollable screenshot
Right panel: slot table with type/brand/title per row

Clicking a row in the slot table:
  - Highlights the row
  - Finds the product thumbnail in the screenshot via template matching (cv2)
  - Draws a bounding box around the matched region and scrolls to it

Usage:
    python3 tools/slot_inspector.py <json_path>
    python3 tools/slot_inspector.py output/walmart/bomb_pop/runs/20260225161800/run_results_20260225161800.json

The script uses the backfill_slots_<retailer> parser to build slots live from HTML,
OR falls back to the slots[] already in the JSON if no HTML is found.
"""

import argparse
import importlib
import json
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import cv2
import numpy as np
from PIL import Image, ImageTk, ImageDraw

# ── Colour palette per ad type ─────────────────────────────────────────────
TYPE_COLORS = {
    "Sponsored_Display":       "#e74c3c",   # red
    "SBA":                     "#8e44ad",   # purple
    "SBV":                     "#2980b9",   # blue
    "Sponsored_Brand":         "#8e44ad",
    "Sponsored_Brand_Video":   "#2980b9",
    "Sponsored_Brand_Card":    "#6c3483",
    "Sponsored_Carousel":      "#1abc9c",   # teal
    "Sponsored_Product":       "#e67e22",   # orange
    "Gallery_Cards":           "#16a085",
    "Tile_Takeover":           "#c0392b",   # dark red
    "Shoppable_Display_Ad":    "#8e44ad",
    "Shoppable_Video_Ad":      "#2980b9",
    "Shoppable_Ad_Item":       "#e67e22",
    "TOA":                     "#c0392b",
    "Skyscraper":              "#2980b9",
    "CuratedCarousel":         "#1abc9c",
    "Product_Listing":         "#7f8c8d",   # grey
    "ListingPageBannerAd":     "#e74c3c",
    "Sponsored_Logo":          "#8e44ad",
}
DEFAULT_COLOR = "#2c3e50"
MATCHED_BG   = "#eafaf1"   # light green row bg  → matched
UNMATCHED_BG = "#fdedec"   # light red row bg    → unmatched
SELECTED_BG  = "#d5e8d4"   # selected row

BOX_COLOR    = (255, 60, 60)   # RGB for bounding box
BOX_WIDTH    = 4


_MATCH_SS_MAX_W = 300   # downsample screenshot to this width for matching


def _screenshot_to_gray(screenshot_img):
    """Convert a PIL Image to a (downsampled) grayscale array + the scale factor used."""
    orig_w = screenshot_img.width
    scale  = _MATCH_SS_MAX_W / orig_w if orig_w > _MATCH_SS_MAX_W else 1.0
    if scale < 1.0:
        new_w = _MATCH_SS_MAX_W
        new_h = int(screenshot_img.height * scale)
        small = screenshot_img.resize((new_w, new_h), Image.LANCZOS)
    else:
        small = screenshot_img
    arr  = np.array(small.convert("RGB"))
    gray = cv2.cvtColor(cv2.cvtColor(arr, cv2.COLOR_RGB2BGR), cv2.COLOR_BGR2GRAY)
    return gray, scale


def _find_product_in_screenshot(ss_gray_scale, image_path, min_size=20):
    """
    Use cv2 template matching to locate a product thumbnail inside the
    full-page screenshot.  Returns (x, y, w, h) in ORIGINAL-image pixels,
    or None if not found / confidence too low.

    ss_gray_scale: tuple (gray_array, scale) from _screenshot_to_gray.
    image_path: path to the cached product image file.
    """
    if ss_gray_scale is None or not image_path or not os.path.exists(image_path):
        return None

    ss_gray, scale = ss_gray_scale

    try:
        prod = Image.open(image_path).convert("RGB")
        prod_arr = np.array(prod)
        prod_gray = cv2.cvtColor(
            cv2.cvtColor(prod_arr, cv2.COLOR_RGB2BGR), cv2.COLOR_BGR2GRAY
        )

        orig_h, orig_w = prod_gray.shape[:2]
        if orig_w == 0 or orig_h == 0:
            return None

        ss_h, ss_w = ss_gray.shape[:2]

        # Target widths in downsampled-screenshot space (thumbnails ~40-120px at this scale)
        min_tw = max(min_size, int(40 * scale))
        max_tw = min(ss_w - 1, int(160 * scale))
        step   = max(2, int(10 * scale))

        best_val = -1.0
        best_loc = None
        best_wh  = None

        for target_w in range(min_tw, max_tw, step):
            target_h = int(orig_h * target_w / orig_w)
            if target_h < min_size or target_h >= ss_h or target_w >= ss_w:
                continue
            tmpl = cv2.resize(prod_gray, (target_w, target_h), interpolation=cv2.INTER_AREA)
            res  = cv2.matchTemplate(ss_gray, tmpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            if max_val > best_val:
                best_val = max_val
                best_loc = max_loc
                best_wh  = (target_w, target_h)

        if best_val < 0.55 or best_loc is None:
            return None

        # Map back to original-image pixel coordinates
        x = int(best_loc[0] / scale)
        y = int(best_loc[1] / scale)
        w = int(best_wh[0]  / scale)
        h = int(best_wh[1]  / scale)
        return (x, y, w, h)

    except Exception:
        return None


def type_color(ad_type):
    return TYPE_COLORS.get(ad_type, DEFAULT_COLOR)


# ── Slot loading ───────────────────────────────────────────────────────────

def _retailer_from_json(data, json_path):
    """Infer retailer from JSON metadata or path."""
    r = data.get("retailer", "")
    if r:
        return r.lower()
    for name in ["walmart", "amazon", "target", "instacart", "kroger"]:
        if name in json_path.lower():
            return name
    return ""


def _fmt_price(raw_price, retailer):
    """Normalise price strings for display.

    Walmart stores prices as integer cents with a leading '$':
      '$297'  -> '$2.97'
      '$1024' -> '$10.24'
    Other retailers already have decimal prices:
      '$2.97' -> '$2.97'
    """
    if not raw_price:
        return ""
    s = str(raw_price).strip()
    # Strip leading dollar sign for processing
    prefix = ""
    if s.startswith("$"):
        prefix = "$"
        s = s[1:]
    # Remove any commas
    s = s.replace(",", "")
    if retailer == "walmart":
        try:
            cents = int(s)
            return f"${cents / 100:.2f}"
        except ValueError:
            pass
    # Already has decimal or unknown retailer — return as-is
    return prefix + s


def _display_brand(slot, retailer):
    """Best-effort brand string for display in the table."""
    brand = slot.get("brand") or ""
    if brand:
        return brand
    # For Sponsored_Display: extract domain hint from iframe_src
    if slot.get("ad_type") == "Sponsored_Display":
        src = slot.get("iframe_src", "")
        if src:
            import urllib.parse
            host = urllib.parse.urlparse(src).hostname or ""
            # strip common prefixes
            host = host.replace("www.", "").replace("i5.", "").replace("i2.", "")
            return host[:30]
        loc = slot.get("slot_location", "")
        return f"[{loc}]" if loc else "[display]"
    return ""


def load_slots(json_path):
    """
    Returns (slots, screenshot_path, json_ads, retailer).
    Tries live HTML parse first; falls back to slots[] in JSON.
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    retailer = _retailer_from_json(data, json_path)
    json_ads = data.get("ads", [])

    # --- Pre-load image store for path lookups ---
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from product_image_store import get_image_path as _get_img
    except Exception:
        _get_img = None

    # --- Try live parse via backfill module ---
    slots = None
    module_name = f"backfill_slots_{retailer}" if retailer else None
    if module_name:
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
            mod = importlib.import_module(module_name)
            parse_fn_name = f"parse_{retailer}_html"
            match_fn = getattr(mod, "match_slots_to_json", None)
            parse_fn = getattr(mod, parse_fn_name, None)
            find_fn  = getattr(mod, "_find_html_for_json", None)

            if parse_fn and match_fn and find_fn:
                html_path = find_fn(json_path)
                if html_path:
                    raw_slots = parse_fn(html_path)
                    matched   = match_fn(raw_slots, json_ads)
                    slots = []
                    from collections import Counter
                    total = len(matched)
                    type_counts   = Counter(s["ad_type"] for s, _ in matched)
                    type_running  = Counter()
                    for i, (s, jad) in enumerate(matched):
                        at = s["ad_type"]
                        wt = type_running[at]
                        type_running[at] += 1
                        d  = s.get("detail", {})
                        brand = ""
                        if jad:
                            brand = jad.get("brand") or jad.get("brand_canonical") or ""
                        pid = d.get("asin") or d.get("item_id") or d.get("product_id") or d.get("upc") or ""
                        img_path = ""
                        if pid and _get_img:
                            try:
                                img_path = _get_img(retailer, pid) or ""
                            except Exception:
                                pass
                        entry = {
                            "slot":               i,
                            "slot_within_type":   wt,
                            "total_slots":        total,
                            "total_slots_of_type": type_counts[at],
                            "ad_type":            at,
                            "is_sponsored":       d.get("is_sponsored", at != "Product_Listing"),
                            "product_id":         pid,
                            "title":              d.get("title", ""),
                            "price":              _fmt_price(d.get("price", ""), retailer),
                            "brand":              brand,
                            "matched":            jad is not None,
                            "slot_location":      d.get("slot_location", ""),
                            "iframe_src":         d.get("iframe_src", ""),
                            "image_path":         img_path,
                        }
                        slots.append(entry)
        except Exception as e:
            print(f"[slot_inspector] Live parse failed ({e}), falling back to JSON slots")

    # --- Fall back to slots[] already in JSON ---
    if not slots:
        raw = data.get("slots", [])
        if raw:
            slots = []
            for entry in raw:
                slots.append({
                    "slot":               entry.get("slot", entry.get("position", len(slots))),
                    "slot_within_type":   entry.get("slot_within_type", 0),
                    "total_slots":        entry.get("total_slots", len(raw)),
                    "total_slots_of_type": entry.get("total_slots_of_type", 0),
                    "ad_type":            entry.get("ad_type", ""),
                    "is_sponsored":       entry.get("is_sponsored", False),
                    "product_id":         entry.get("product_id", ""),
                    "title":              entry.get("title", ""),
                    "price":              _fmt_price(entry.get("price", ""), retailer),
                    "brand":              entry.get("brand") or "",
                    "matched":            entry.get("matched_ad_index") is not None,
                    "slot_location":      entry.get("slot_location", ""),
                    "iframe_src":         entry.get("iframe_src", ""),
                    "image_path":         entry.get("image_path") or "",
                })

    # --- Resolve screenshot path ---
    ss_path = None
    ss_rel  = data.get("screenshot_path", "")
    run_dir = os.path.dirname(json_path)
    if ss_rel:
        candidate = os.path.normpath(os.path.join(run_dir, ss_rel))
        if os.path.exists(candidate):
            ss_path = candidate
    if not ss_path:
        # Walk up and look for Main/ folder; pick screenshot closest in time to the run
        import re as _re
        from datetime import datetime as _dt

        def _ts_from_name(name):
            """Extract a comparable datetime from a filename."""
            # Run JSON: ...20260226133248... → compact 14-digit timestamp
            m = _re.search(r'(\d{14})', name)
            if m:
                try:
                    return _dt.strptime(m.group(1), "%Y%m%d%H%M%S")
                except ValueError:
                    pass
            # Screenshot: ...D2026-02-26_T13-31.33... → parse date+time
            m2 = _re.search(r'D(\d{4}-\d{2}-\d{2})_T(\d{2}-\d{2}[.\d]*)', name)
            if m2:
                try:
                    ds = m2.group(1)
                    ts = m2.group(2).replace('-', ':').replace('.', ':').split(':')
                    h, mn = int(ts[0]), int(ts[1])
                    return _dt.strptime(f"{ds} {h:02d}:{mn:02d}", "%Y-%m-%d %H:%M")
                except Exception:
                    pass
            return None

        run_ts = _ts_from_name(os.path.basename(json_path))

        for up in range(1, 5):
            check = run_dir
            for _ in range(up):
                check = os.path.dirname(check)
            main_dir = os.path.join(check, "Main")
            if os.path.isdir(main_dir):
                pngs = [f for f in os.listdir(main_dir)
                        if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
                if not pngs:
                    break
                if run_ts:
                    # Pick the screenshot with timestamp closest to the run
                    def _key(name):
                        t = _ts_from_name(name)
                        if t is None:
                            return float('inf')
                        return abs((t - run_ts).total_seconds())
                    best = min(pngs, key=_key)
                else:
                    best = sorted(pngs)[-1]
                ss_path = os.path.join(main_dir, best)
                break

    return slots or [], ss_path, json_ads, retailer


# ── Main application ───────────────────────────────────────────────────────

class SlotInspector(tk.Tk):
    ZOOM_STEPS = [0.15, 0.2, 0.25, 0.33, 0.4, 0.5, 0.65, 0.75, 1.0, 1.25, 1.5, 2.0]
    INITIAL_ZOOM_INDEX = 4   # 0.4

    def __init__(self, json_path):
        super().__init__()
        self.title("Slot Inspector")
        self.geometry("1600x900")
        self.configure(bg="#1e1e2e")

        self.json_path   = json_path
        self.zoom_index  = self.INITIAL_ZOOM_INDEX
        self.zoom        = self.ZOOM_STEPS[self.zoom_index]
        self._orig_image  = None
        self._tk_image    = None
        self._highlight_box  = None   # (x, y, w, h) in original-image pixels
        self._slot_coords    = {}     # pid/cel_widget → {x,y,w,h} from sidecar
        self._coords_status  = ""     # status string shown in status bar
        self.slots        = []
        self.selected_iid = None

        self._build_ui()
        self._load(json_path)

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self):
        # Top toolbar
        toolbar = tk.Frame(self, bg="#2d2d44", pady=4)
        toolbar.pack(fill=tk.X, side=tk.TOP)

        tk.Button(toolbar, text="Open…", command=self._open_file,
                  bg="#3a3a5c", fg="white", relief=tk.FLAT, padx=10).pack(side=tk.LEFT, padx=4)

        self.lbl_file = tk.Label(toolbar, text="", bg="#2d2d44", fg="#aaaacc",
                                 font=("Helvetica", 11), anchor="w")
        self.lbl_file.pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)

        # Zoom controls
        tk.Button(toolbar, text="−", command=self._zoom_out,
                  bg="#3a3a5c", fg="white", relief=tk.FLAT, width=3).pack(side=tk.RIGHT, padx=2)
        self.lbl_zoom = tk.Label(toolbar, text="40%", bg="#2d2d44", fg="white",
                                 font=("Helvetica", 11), width=5)
        self.lbl_zoom.pack(side=tk.RIGHT)
        tk.Button(toolbar, text="+", command=self._zoom_in,
                  bg="#3a3a5c", fg="white", relief=tk.FLAT, width=3).pack(side=tk.RIGHT, padx=2)
        tk.Label(toolbar, text="Zoom:", bg="#2d2d44", fg="#aaaacc").pack(side=tk.RIGHT, padx=6)

        # Status bar
        self.status_var = tk.StringVar(value="")
        status_bar = tk.Label(self, textvariable=self.status_var,
                              bg="#2d2d44", fg="#aaaacc", anchor="w",
                              font=("Helvetica", 10), pady=2)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        # Main pane
        pane = tk.PanedWindow(self, orient=tk.HORIZONTAL, bg="#1e1e2e",
                              sashwidth=6, sashrelief=tk.RAISED)
        pane.pack(fill=tk.BOTH, expand=True)

        # ── Left: image panel ──────────────────────────────────────────
        img_frame = tk.Frame(pane, bg="#1e1e2e")
        pane.add(img_frame, minsize=300, width=760)

        # Canvas + scrollbars
        self.img_canvas = tk.Canvas(img_frame, bg="#111122", highlightthickness=0,
                                    cursor="crosshair")
        h_scroll = tk.Scrollbar(img_frame, orient=tk.HORIZONTAL,
                                 command=self.img_canvas.xview)
        v_scroll = tk.Scrollbar(img_frame, orient=tk.VERTICAL,
                                 command=self.img_canvas.yview)
        self.img_canvas.configure(xscrollcommand=h_scroll.set,
                                   yscrollcommand=v_scroll.set)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        v_scroll.pack(side=tk.RIGHT,  fill=tk.Y)
        self.img_canvas.pack(fill=tk.BOTH, expand=True)

        # Mousewheel zoom (Cmd/Ctrl + scroll) and plain scroll
        self.img_canvas.bind("<MouseWheel>",      self._on_mousewheel)
        self.img_canvas.bind("<Button-4>",        self._on_mousewheel)
        self.img_canvas.bind("<Button-5>",        self._on_mousewheel)

        # ── Right: slot table ──────────────────────────────────────────
        slot_frame = tk.Frame(pane, bg="#1e1e2e")
        pane.add(slot_frame, minsize=300, width=760)

        # Header labels
        hdr = tk.Frame(slot_frame, bg="#2d2d44", pady=4)
        hdr.pack(fill=tk.X)
        self.lbl_slots = tk.Label(hdr, text="Slots", bg="#2d2d44", fg="white",
                                   font=("Helvetica", 13, "bold"))
        self.lbl_slots.pack(side=tk.LEFT, padx=10)
        self.lbl_match = tk.Label(hdr, text="", bg="#2d2d44", fg="#aaaacc",
                                   font=("Helvetica", 11))
        self.lbl_match.pack(side=tk.LEFT, padx=6)

        # Filter bar
        filter_frame = tk.Frame(slot_frame, bg="#1e1e2e", pady=4)
        filter_frame.pack(fill=tk.X)
        tk.Label(filter_frame, text="Filter:", bg="#1e1e2e", fg="#aaaacc").pack(side=tk.LEFT, padx=6)
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_: self._apply_filter())
        filter_entry = tk.Entry(filter_frame, textvariable=self.filter_var,
                                bg="#2d2d44", fg="white", insertbackground="white",
                                relief=tk.FLAT, font=("Helvetica", 11))
        filter_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        tk.Button(filter_frame, text="✕", command=lambda: self.filter_var.set(""),
                  bg="#2d2d44", fg="#aaaacc", relief=tk.FLAT).pack(side=tk.LEFT)

        # Treeview
        cols = ("slot", "type", "match", "brand", "price", "title")
        self.tree = ttk.Treeview(slot_frame, columns=cols, show="headings",
                                  selectmode="browse")

        # Style
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview",
                        background="#1e1e2e", foreground="white",
                        fieldbackground="#1e1e2e", rowheight=24,
                        font=("Helvetica", 11))
        style.configure("Treeview.Heading",
                        background="#2d2d44", foreground="#aaaacc",
                        relief=tk.FLAT, font=("Helvetica", 11, "bold"))
        style.map("Treeview", background=[("selected", "#3a5f8a")])

        col_widths = {"slot": 45, "type": 185, "match": 50,
                      "brand": 130, "price": 65, "title": 280}
        for c in cols:
            self.tree.heading(c, text=c.capitalize(),
                              command=lambda _c=c: self._sort_by(_c))
            self.tree.column(c, width=col_widths[c], stretch=(c == "title"))

        tree_scroll = tk.Scrollbar(slot_frame, orient=tk.VERTICAL,
                                    command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(fill=tk.BOTH, expand=True)

        # Tag colours
        self.tree.tag_configure("matched",   background=MATCHED_BG,   foreground="#1e1e2e")
        self.tree.tag_configure("unmatched", background=UNMATCHED_BG, foreground="#1e1e2e")
        self.tree.tag_configure("selected",  background=SELECTED_BG,  foreground="#1e1e2e")

        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # Detail pane at bottom of right panel
        detail_frame = tk.Frame(slot_frame, bg="#2d2d44", pady=6)
        detail_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.detail_var = tk.StringVar(value="Click a row to see details")
        tk.Label(detail_frame, textvariable=self.detail_var,
                 bg="#2d2d44", fg="#ddeeff",
                 font=("Helvetica", 11), anchor="w", wraplength=700,
                 justify=tk.LEFT).pack(fill=tk.X, padx=10)

    # ── Data loading ───────────────────────────────────────────────────────

    def _load(self, json_path):
        self.json_path = json_path
        self.lbl_file.config(text=os.path.basename(json_path))
        self.title(f"Slot Inspector — {os.path.basename(os.path.dirname(json_path))}")

        try:
            self.slots, ss_path, json_ads, retailer = load_slots(json_path)
        except Exception as e:
            messagebox.showerror("Load error", str(e))
            return

        n_matched = sum(1 for s in self.slots if s.get("matched"))
        total     = len(self.slots)
        self.lbl_slots.config(text=f"{total} slots")
        self.lbl_match.config(text=f"({n_matched} matched, {total - n_matched} unmatched)")
        self.status_var.set(
            f"Retailer: {retailer or '?'}  |  JSON: {json_path}  |  "
            f"Screenshot: {ss_path or 'not found'}"
        )

        self._populate_tree(self.slots)
        self._slot_coords   = {}
        self._coords_status = ""
        self._load_coords_async(json_path)

        if ss_path and os.path.exists(ss_path):
            self._load_image(ss_path)
        else:
            self.img_canvas.delete("all")
            self.img_canvas.create_text(
                200, 200, text="Screenshot not found",
                fill="#aaaacc", font=("Helvetica", 14))

    def _open_file(self):
        path = filedialog.askopenfilename(
            title="Open run JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*")],
            initialdir=os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "output"))
        if path:
            self._load(path)

    # ── Image ──────────────────────────────────────────────────────────────

    def _load_coords_async(self, json_path):
        """Try to load cached coords sidecar; if missing, build it in background."""
        import importlib, sys as _sys
        _sys.path.insert(0, os.path.dirname(__file__))
        try:
            bsc = importlib.import_module('build_slot_coords')
        except Exception:
            return

        try:
            html_path = bsc._html_path_for_json(json_path)
        except Exception:
            return
        if not html_path or not os.path.exists(html_path):
            return

        sidecar = bsc.coords_path_for_html(html_path)

        if os.path.exists(sidecar):
            try:
                with open(sidecar) as f:
                    self._slot_coords = json.load(f)
                self._coords_status = f"coords: {len(self._slot_coords)} rects (cached)"
                self._update_status()
            except Exception:
                pass
            return

        # Build in background
        self._coords_status = "coords: building…"
        self._update_status()
        def _build():
            try:
                coords, _ = bsc.build_and_cache(json_path)
                def _apply():
                    self._slot_coords   = coords
                    self._coords_status = f"coords: {len(coords)} rects"
                    self._update_status()
                self.after(0, _apply)
            except Exception as e:
                def _err():
                    self._coords_status = f"coords: build failed ({e})"
                    self._update_status()
                self.after(0, _err)
        threading.Thread(target=_build, daemon=True).start()

    def _update_status(self):
        base = self.status_var.get().split('  |  coords')[0]
        if self._coords_status:
            self.status_var.set(base + f'  |  {self._coords_status}')

    def _load_image(self, path):
        self._orig_image    = Image.open(path)
        self._highlight_box = None
        self._render_image()

    def _render_image(self):
        if not self._orig_image:
            return
        w = int(self._orig_image.width  * self.zoom)
        h = int(self._orig_image.height * self.zoom)
        resized = self._orig_image.resize((w, h), Image.LANCZOS)

        # Draw bounding box if a product was located
        if self._highlight_box is not None:
            ox, oy, ow, oh = self._highlight_box
            bx = int(ox * self.zoom)
            by = int(oy * self.zoom)
            bw = int(ow * self.zoom)
            bh = int(oh * self.zoom)
            draw = ImageDraw.Draw(resized)
            lw = max(2, int(BOX_WIDTH * self.zoom))
            r = tuple(int(c) for c in BOX_COLOR)
            for t in range(lw):
                draw.rectangle(
                    [(bx - t, by - t), (bx + bw + t, by + bh + t)],
                    outline=r
                )

        self._tk_image = ImageTk.PhotoImage(resized)
        self.img_canvas.delete("all")
        self.img_canvas.create_image(0, 0, anchor=tk.NW, image=self._tk_image)
        self.img_canvas.configure(scrollregion=(0, 0, w, h))
        self.lbl_zoom.config(text=f"{int(self.zoom * 100)}%")

    def _zoom_in(self):
        if self.zoom_index < len(self.ZOOM_STEPS) - 1:
            self.zoom_index += 1
            self.zoom = self.ZOOM_STEPS[self.zoom_index]
            self._render_image()

    def _zoom_out(self):
        if self.zoom_index > 0:
            self.zoom_index -= 1
            self.zoom = self.ZOOM_STEPS[self.zoom_index]
            self._render_image()

    def _on_mousewheel(self, event):
        # Ctrl/Cmd held → zoom; otherwise scroll
        if event.state & 0x4 or event.state & 0x8:  # Ctrl or Cmd
            if event.num == 4 or getattr(event, "delta", 0) > 0:
                self._zoom_in()
            else:
                self._zoom_out()
        else:
            if event.num == 4 or getattr(event, "delta", 0) > 0:
                self.img_canvas.yview_scroll(-3, "units")
            elif event.num == 5 or getattr(event, "delta", 0) < 0:
                self.img_canvas.yview_scroll(3, "units")

    def _scroll_image_to_fraction(self, frac):
        """Scroll image so that vertical fraction `frac` is near the top."""
        frac = max(0.0, min(1.0, frac))
        self.img_canvas.yview_moveto(max(0.0, frac - 0.05))

    # ── Slot table ─────────────────────────────────────────────────────────

    def _populate_tree(self, slots):
        self.tree.delete(*self.tree.get_children())
        filt = self.filter_var.get().lower()
        for s in slots:
            at     = s["ad_type"]
            brand  = _display_brand(s, "")
            title  = s.get("title", "")[:70]
            price  = s.get("price", "")
            pid    = s.get("product_id", "")
            loc    = s.get("slot_location", "")
            matched = s.get("matched", False)

            type_display = at
            if loc:
                type_display = f"{at} [{loc}]"

            match_icon = "✓" if matched else "·"

            # Filter
            haystack = f"{at} {brand} {title} {pid}".lower()
            if filt and filt not in haystack:
                continue

            tag = "matched" if matched else "unmatched"
            iid = self.tree.insert(
                "", tk.END,
                values=(s["slot"], type_display, match_icon, brand, price, title),
                tags=(tag,),
            )
            # Store the slot index on the item
            self.tree.set(iid, "slot", s["slot"])

    def _apply_filter(self):
        self._populate_tree(self.slots)

    def _sort_by(self, col):
        data = [(self.tree.set(iid, col), iid) for iid in self.tree.get_children("")]
        try:
            data.sort(key=lambda x: int(x[0]))
        except ValueError:
            data.sort(key=lambda x: x[0].lower())
        for i, (_, iid) in enumerate(data):
            self.tree.move(iid, "", i)

    def _on_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        iid  = sel[0]
        slot_idx = int(self.tree.set(iid, "slot"))

        # Find slot data
        slot = next((s for s in self.slots if s["slot"] == slot_idx), None)
        if not slot:
            return

        # Detail text
        loc   = f" [{slot['slot_location']}]" if slot.get("slot_location") else ""
        parts = [
            f"Slot {slot['slot']}  ·  {slot['ad_type']}{loc}",
            f"Within type: {slot['slot_within_type']+1} of {slot['total_slots_of_type']}  "
            f"(total slots: {slot['total_slots']})",
        ]
        if slot.get("brand"):
            parts.append(f"Brand: {slot['brand']}")
        if slot.get("product_id"):
            parts.append(f"ID: {slot['product_id']}")
        if slot.get("price"):
            parts.append(f"Price: {slot['price']}")
        if slot.get("title"):
            parts.append(f"Title: {slot['title'][:120]}")
        self.detail_var.set("   |   ".join(parts))

        # Look up DOM coords from sidecar
        slot_idx = slot["slot"]
        total    = slot["total_slots"]
        pid      = slot.get("product_id") or ""
        box      = None

        if self._slot_coords:
            # Try by ASIN/product_id first
            rect = self._slot_coords.get(pid)
            if not rect and slot.get("ad_type") not in ("Product_Listing", "Sponsored_Product"):
                # Try cel_widget keys for non-product slots
                # Match by slot_within_type index into matching cel: entries
                at = slot["ad_type"]
                cel_prefix_map = {
                    "Sponsored_Brand":       "cel:sb-",
                    "SBA":                   "cel:sb-",
                    "Sponsored_Brand_Video": "cel:VIDEO_SINGLE_PRODUCT",
                    "SBV":                   "cel:VIDEO_SINGLE_PRODUCT",
                    "Sponsored_Carousel":    "cel:FEATURED_ASINS_LIST",
                    "Sponsored_Display":     "cel:loom-desktop",
                }
                prefix = cel_prefix_map.get(at, "")
                if prefix:
                    matches = sorted(k for k in self._slot_coords if k.startswith(prefix))
                    idx_in_type = slot.get("slot_within_type", 0)
                    if idx_in_type < len(matches):
                        rect = self._slot_coords[matches[idx_in_type]]
            if rect:
                # Scale coords: sidecar uses VIEWPORT_W=1385, screenshot may differ
                img_w = self._orig_image.width if self._orig_image else 1385
                scale = img_w / 1385
                box = (
                    int(rect["x"] * scale),
                    int(rect["y"] * scale),
                    int(rect["w"] * scale),
                    int(rect["h"] * scale),
                )

        if box:
            self._highlight_box = box
            ox, oy, ow, oh = box
            img_h = self._orig_image.height if self._orig_image else 1
            frac  = oy / img_h if img_h else 0
            self._render_image()
            self._scroll_image_to_fraction(frac)
        else:
            # Fallback: linear fraction
            self._highlight_box = None
            if total > 0:
                self._render_image()
                self._scroll_image_to_fraction(slot_idx / total)

        self.status_var.set(
            f"Slot {slot['slot']}  ·  {slot['ad_type']}{loc}  "
            f"·  matched={'yes' if slot.get('matched') else 'no'}  "
            f"·  {os.path.basename(self.json_path)}"
        )


# ── Entry point ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Slot Inspector — visual slot validation")
    parser.add_argument("json_path", nargs="?", help="Path to run_results*.json")
    args = parser.parse_args()

    json_path = args.json_path
    if not json_path:
        # Show file picker if no argument given
        root = tk.Tk()
        root.withdraw()
        json_path = filedialog.askopenfilename(
            title="Open run JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*")],
            initialdir=os.path.join(os.path.dirname(os.path.dirname(__file__)), "output"),
        )
        root.destroy()
        if not json_path:
            sys.exit(0)

    if not os.path.exists(json_path):
        print(f"ERROR: file not found: {json_path}")
        sys.exit(1)

    app = SlotInspector(json_path)
    app.mainloop()


if __name__ == "__main__":
    main()
