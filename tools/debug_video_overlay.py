#!/usr/bin/env python3
"""
Debug tools for video overlay detection.

Three modes:
1. preview - Show image with detected overlay box (green) and save to file
2. scan - Print row/column intensity analysis for edge detection debugging
3. browse - Open file picker to select an image (defaults to output folder)

Usage:
    python tools/debug_video_overlay.py preview <image_path>
    python tools/debug_video_overlay.py scan <image_path> [--edge top|bottom|left|right]
    python tools/debug_video_overlay.py browse [--mode preview|scan]
"""

import argparse
import sys
from pathlib import Path

try:
    import cv2
    import numpy as np
except ImportError:
    print("❌ OpenCV not installed. Run: pip install opencv-python numpy")
    sys.exit(1)

# Default output folder
DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent / "output"

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.auto_detect_video_overlay import auto_detect_video_bounds


def extract_retailer_and_adtype(image_path: Path) -> tuple:
    """Extract retailer and ad_type from file path."""
    # Path pattern: output/{retailer}/{client}/{ad_type_folder}/filename.png
    parts = image_path.parts
    
    # Find 'output' in path and get retailer from next part
    retailer = None
    ad_type = None
    
    for i, part in enumerate(parts):
        if part == 'output' and i + 1 < len(parts):
            retailer = parts[i + 1]
            if i + 3 < len(parts):
                # ad_type folder is 2 levels after retailer (retailer/client/ad_type_folder)
                ad_type_folder = parts[i + 3]
                # Map folder names to ad types
                folder_to_adtype = {
                    'Sponsored_Brand_Video': 'Sponsored_Brand_Video',
                    'Shoppable_Video_Ads': 'Shoppable_Video_Ad',
                    'SBV': 'SBV',
                    'Video': 'Video',
                }
                ad_type = folder_to_adtype.get(ad_type_folder, ad_type_folder)
            break
    
    # Fallback: try to extract from filename
    if not retailer:
        filename = image_path.stem
        parts = filename.split('__')
        if parts:
            retailer = parts[0]
    
    return retailer or 'unknown', ad_type or 'Video'


def preview_overlay(image_path: Path, output_path: Path = None):
    """
    Display image with detected overlay box drawn on it.
    Green box = detected video bounds
    """
    img = cv2.imread(str(image_path))
    if img is None:
        print(f"❌ Could not load image: {image_path}")
        return False
    
    height, width = img.shape[:2]
    print(f"Image dimensions: {width} x {height}")
    
    # Extract retailer and ad_type from path
    retailer, ad_type = extract_retailer_and_adtype(image_path)
    print(f"Retailer: {retailer}, Ad Type: {ad_type}")
    
    # Detect overlay
    result = auto_detect_video_bounds(image_path, retailer, ad_type)
    
    if result is None:
        print("❌ Detection failed - no overlay found")
        return False
    
    print(f"\n✅ Detection result:")
    print(f"   x: {result['x']}, y: {result['y']}")
    print(f"   width: {result['width']}, height: {result['height']}")
    print(f"   image_width: {result['image_width']}, image_height: {result['image_height']}")
    print(f"   method: {result.get('detection_method', 'unknown')}")
    if 'border_radius' in result:
        print(f"   border_radius: {result['border_radius']}")
    
    # Draw the overlay box
    x, y = result['x'], result['y']
    w, h = result['width'], result['height']
    
    # Green box for detected bounds
    cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)
    
    # Add corner markers
    marker_size = 10
    # Top-left
    cv2.line(img, (x, y), (x + marker_size, y), (0, 255, 0), 3)
    cv2.line(img, (x, y), (x, y + marker_size), (0, 255, 0), 3)
    # Top-right
    cv2.line(img, (x + w, y), (x + w - marker_size, y), (0, 255, 0), 3)
    cv2.line(img, (x + w, y), (x + w, y + marker_size), (0, 255, 0), 3)
    # Bottom-left
    cv2.line(img, (x, y + h), (x + marker_size, y + h), (0, 255, 0), 3)
    cv2.line(img, (x, y + h), (x, y + h - marker_size), (0, 255, 0), 3)
    # Bottom-right
    cv2.line(img, (x + w, y + h), (x + w - marker_size, y + h), (0, 255, 0), 3)
    cv2.line(img, (x + w, y + h), (x + w, y + h - marker_size), (0, 255, 0), 3)
    
    # Add text label
    label = f"Video: {w}x{h} @ ({x},{y})"
    cv2.putText(img, label, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    
    # Save or display
    if output_path is None:
        output_path = image_path.parent / f"{image_path.stem}_overlay_debug.png"
    
    cv2.imwrite(str(output_path), img)
    print(f"\n📁 Saved preview to: {output_path}")
    
    # Try to display (may not work in all environments)
    try:
        cv2.imshow("Video Overlay Preview", img)
        print("Press any key to close...")
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    except:
        pass
    
    return True


def scan_edge(image_path: Path, edge: str = "all", range_size: int = 150):
    """
    Print intensity analysis for edge detection debugging.
    Shows mean and std for each row/column near the specified edge.
    """
    img = cv2.imread(str(image_path))
    if img is None:
        print(f"❌ Could not load image: {image_path}")
        return False
    
    height, width = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    print(f"Image dimensions: {width} x {height}")
    print()
    
    def classify_row(mean_val, std_val):
        """Classify a row/column based on intensity."""
        if mean_val >= 252 and std_val < 5:
            return "WHITE (solid)"
        elif mean_val >= 250:
            return "WHITE"
        elif 200 < mean_val < 250 and std_val < 10:
            return "GRAY BORDER"
        elif std_val > 30 and mean_val > 200:
            return "TEXT"
        elif mean_val < 150:
            return "VIDEO CONTENT"
        else:
            return ""
    
    if edge in ("top", "all"):
        print("=" * 50)
        print("=== TOP EDGE ANALYSIS (rows) ===")
        print("=" * 50)
        # Use middle portion for analysis (avoid left/right edges)
        x_start = width // 4
        x_end = width * 3 // 4
        for y in range(min(range_size, height)):
            row = gray[y, x_start:x_end]
            mean_val = np.mean(row)
            std_val = np.std(row)
            label = classify_row(mean_val, std_val)
            marker = f" <- {label}" if label else ""
            print(f"y={y:3d}: mean={mean_val:5.1f}, std={std_val:4.1f}{marker}")
        print()
    
    if edge in ("bottom", "all"):
        print("=" * 50)
        print("=== BOTTOM EDGE ANALYSIS (rows, from bottom) ===")
        print("=" * 50)
        x_start = width // 4
        x_end = width * 3 // 4
        for i in range(min(range_size, height)):
            y = height - 1 - i
            row = gray[y, x_start:x_end]
            mean_val = np.mean(row)
            std_val = np.std(row)
            label = classify_row(mean_val, std_val)
            marker = f" <- {label}" if label else ""
            print(f"y={y:3d} (bottom-{i:3d}): mean={mean_val:5.1f}, std={std_val:4.1f}{marker}")
        print()
    
    if edge in ("left", "all"):
        print("=" * 50)
        print("=== LEFT EDGE ANALYSIS (columns) ===")
        print("=" * 50)
        # Use middle portion for analysis (avoid top/bottom edges)
        y_start = height // 4
        y_end = height * 3 // 4
        for x in range(min(range_size, width)):
            col = gray[y_start:y_end, x]
            mean_val = np.mean(col)
            std_val = np.std(col)
            label = classify_row(mean_val, std_val)
            marker = f" <- {label}" if label else ""
            print(f"x={x:3d}: mean={mean_val:5.1f}, std={std_val:4.1f}{marker}")
        print()
    
    if edge in ("right", "all"):
        print("=" * 50)
        print("=== RIGHT EDGE ANALYSIS (columns, from right) ===")
        print("=" * 50)
        y_start = height // 4
        y_end = height * 3 // 4
        for i in range(min(range_size, width)):
            x = width - 1 - i
            col = gray[y_start:y_end, x]
            mean_val = np.mean(col)
            std_val = np.std(col)
            label = classify_row(mean_val, std_val)
            marker = f" <- {label}" if label else ""
            print(f"x={x:3d} (right-{i:3d}): mean={mean_val:5.1f}, std={std_val:4.1f}{marker}")
        print()
    
    return True


def get_available_retailers():
    """Get list of retailers from output directory."""
    retailers = []
    if DEFAULT_OUTPUT_DIR.exists():
        for d in DEFAULT_OUTPUT_DIR.iterdir():
            if d.is_dir() and not d.name.startswith('.'):
                retailers.append(d.name)
    return sorted(retailers)


def get_available_clients(retailer: str = None):
    """Get list of clients, optionally filtered by retailer."""
    clients = set()
    search_dirs = []
    
    if retailer and retailer != "all":
        retailer_dir = DEFAULT_OUTPUT_DIR / retailer
        if retailer_dir.exists():
            search_dirs = [retailer_dir]
    else:
        search_dirs = [d for d in DEFAULT_OUTPUT_DIR.iterdir() if d.is_dir() and not d.name.startswith('.')]
    
    for retailer_dir in search_dirs:
        for client_dir in retailer_dir.iterdir():
            if client_dir.is_dir() and not client_dir.name.startswith('.'):
                clients.add(client_dir.name)
    
    return sorted(clients)


def get_available_brands(retailer: str = None, client: str = None):
    """Get list of brands from video ad filenames."""
    brands = set()
    images = find_video_images(retailer, client)
    
    for img in images:
        # Extract brand from filename pattern: retailer__brand__ad_type__...
        parts = img.stem.split('__')
        if len(parts) >= 2:
            brand = parts[1].replace('_', ' ').title()
            brands.add(brand)
    
    return sorted(brands)


def find_video_images(retailer: str = None, client: str = None, brand: str = None):
    """Find all video ad images matching filters."""
    images = []
    
    # Video ad folder patterns by retailer
    video_folders = {
        "amazon": ["Sponsored_Brand_Video"],
        "instacart": ["Shoppable_Video_Ads"],
        "walmart": ["SBV"],
        "kroger": ["Video"],
        "target": ["Video"],
    }
    
    search_dirs = []
    if retailer and retailer != "all":
        search_dirs = [DEFAULT_OUTPUT_DIR / retailer]
    else:
        search_dirs = [d for d in DEFAULT_OUTPUT_DIR.iterdir() if d.is_dir() and not d.name.startswith('.')]
    
    for retailer_dir in search_dirs:
        if not retailer_dir.exists():
            continue
        
        retailer_name = retailer_dir.name
        folders_to_check = video_folders.get(retailer_name, ["Video", "Shoppable_Video_Ads", "SBV", "Sponsored_Brand_Video"])
        
        for client_dir in retailer_dir.iterdir():
            if not client_dir.is_dir() or client_dir.name.startswith('.'):
                continue
            if client and client != "all" and client_dir.name != client:
                continue
            
            for folder_name in folders_to_check:
                video_dir = client_dir / folder_name
                if video_dir.exists():
                    for img in video_dir.glob("*.png"):
                        # Filter by brand if specified
                        if brand and brand != "all":
                            parts = img.stem.split('__')
                            if len(parts) >= 2:
                                img_brand = parts[1].replace('_', ' ').title()
                                if img_brand.lower() != brand.lower():
                                    continue
                        images.append(img)
    
    return images


def launch_gui():
    """
    Launch a GUI with mode selection and file picker.
    """
    try:
        import tkinter as tk
        from tkinter import ttk, filedialog, messagebox
        import random
    except ImportError:
        print("❌ tkinter not available")
        return False
    
    selected_files = []  # List of files to process
    
    def update_file_label():
        if len(selected_files) == 0:
            file_label.config(text="No file selected", foreground="gray")
            run_btn.config(state=tk.DISABLED)
        elif len(selected_files) == 1:
            f = selected_files[0]
            file_label.config(text=f".../{f.parent.name}/{f.name}", foreground="black")
            run_btn.config(state=tk.NORMAL)
        else:
            file_label.config(text=f"{len(selected_files)} files selected", foreground="black")
            run_btn.config(state=tk.NORMAL)
    
    def browse_file():
        retailer = retailer_var.get()
        client = client_var.get()
        
        # Determine initial directory based on filters
        if retailer != "all" and client != "all":
            initial_dir = DEFAULT_OUTPUT_DIR / retailer / client
        elif retailer != "all":
            initial_dir = DEFAULT_OUTPUT_DIR / retailer
        else:
            initial_dir = DEFAULT_OUTPUT_DIR
        
        if not initial_dir.exists():
            initial_dir = DEFAULT_OUTPUT_DIR if DEFAULT_OUTPUT_DIR.exists() else Path.home()
        
        file_path = filedialog.askopenfilename(
            title="Select Video Ad Image",
            initialdir=str(initial_dir),
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.webp"),
                ("PNG files", "*.png"),
                ("All files", "*.*")
            ]
        )
        if file_path:
            selected_files.clear()
            selected_files.append(Path(file_path))
            update_file_label()
    
    def use_path_entry():
        path_str = path_entry.get().strip()
        if not path_str:
            messagebox.showerror("Error", "Please enter a file path")
            return
        
        path = Path(path_str)
        if not path.exists():
            messagebox.showerror("Error", f"File not found: {path}")
            return
        
        selected_files.clear()
        selected_files.append(path)
        update_file_label()
    
    def select_random_10():
        retailer = retailer_var.get()
        client = client_var.get()
        brand = brand_var.get()
        
        images = find_video_images(
            retailer if retailer != "all" else None,
            client if client != "all" else None,
            brand if brand != "all" else None
        )
        
        if not images:
            messagebox.showwarning("No Images", "No video ad images found matching filters")
            return
        
        import random
        sample_size = min(10, len(images))
        selected_files.clear()
        selected_files.extend(random.sample(images, sample_size))
        update_file_label()
    
    def on_retailer_change(*args):
        # Update client and brand dropdowns when retailer changes
        retailer = retailer_var.get()
        clients = ["all"] + get_available_clients(retailer if retailer != "all" else None)
        client_combo['values'] = clients
        client_var.set("all")
        # Update brands
        brands = ["all"] + get_available_brands(retailer if retailer != "all" else None, None)
        brand_combo['values'] = brands
        brand_var.set("all")
    
    def on_client_change(*args):
        # Update brand dropdown when client changes
        retailer = retailer_var.get()
        client = client_var.get()
        brands = ["all"] + get_available_brands(
            retailer if retailer != "all" else None,
            client if client != "all" else None
        )
        brand_combo['values'] = brands
        brand_var.set("all")
    
    def run_action():
        if not selected_files:
            messagebox.showerror("Error", "No file selected")
            return
        
        mode = mode_var.get()
        edge = edge_var.get()
        
        root.destroy()
        
        for i, file_path in enumerate(selected_files):
            if len(selected_files) > 1:
                print(f"\n{'='*60}")
                print(f"[{i+1}/{len(selected_files)}] {file_path.name}")
                print('='*60)
            
            print(f"📁 File: {file_path}")
            print(f"🔧 Mode: {mode}")
            print()
            
            if mode == "preview":
                preview_overlay(file_path)
            elif mode == "scan":
                scan_edge(file_path, edge, 150)
    
    # Create main window
    root = tk.Tk()
    root.title("Video Overlay Debug Tool")
    root.geometry("550x530")
    root.resizable(True, True)
    root.minsize(500, 500)
    
    # Center window on screen
    root.update_idletasks()
    x = (root.winfo_screenwidth() - 550) // 2
    y = (root.winfo_screenheight() - 530) // 2
    root.geometry(f"550x530+{x}+{y}")
    
    # Make window appear on top
    root.attributes('-topmost', True)
    root.after(100, lambda: root.attributes('-topmost', False))
    
    # Main frame with padding
    main_frame = ttk.Frame(root, padding="20")
    main_frame.pack(fill=tk.BOTH, expand=True)
    
    # Title
    title_label = ttk.Label(main_frame, text="Video Overlay Debug Tool", font=("Helvetica", 16, "bold"))
    title_label.pack(pady=(0, 15))
    
    # Filter frame
    filter_frame = ttk.LabelFrame(main_frame, text="Filters", padding="10")
    filter_frame.pack(fill=tk.X, pady=5)
    
    filter_row = ttk.Frame(filter_frame)
    filter_row.pack(fill=tk.X)
    
    ttk.Label(filter_row, text="Retailer:").pack(side=tk.LEFT)
    retailer_var = tk.StringVar(value="all")
    retailers = ["all"] + get_available_retailers()
    retailer_combo = ttk.Combobox(filter_row, textvariable=retailer_var, values=retailers, width=12, state="readonly")
    retailer_combo.pack(side=tk.LEFT, padx=(5, 15))
    retailer_var.trace('w', on_retailer_change)
    
    ttk.Label(filter_row, text="Client:").pack(side=tk.LEFT)
    client_var = tk.StringVar(value="all")
    clients = ["all"] + get_available_clients()
    client_combo = ttk.Combobox(filter_row, textvariable=client_var, values=clients, width=15, state="readonly")
    client_combo.pack(side=tk.LEFT, padx=(5, 15))
    client_var.trace('w', on_client_change)
    
    # Second row for brand filter
    filter_row2 = ttk.Frame(filter_frame)
    filter_row2.pack(fill=tk.X, pady=(10, 0))
    
    ttk.Label(filter_row2, text="Brand:").pack(side=tk.LEFT)
    brand_var = tk.StringVar(value="all")
    brands = ["all"] + get_available_brands()
    brand_combo = ttk.Combobox(filter_row2, textvariable=brand_var, values=brands, width=25, state="readonly")
    brand_combo.pack(side=tk.LEFT, padx=5)
    
    # File selection frame
    file_frame = ttk.LabelFrame(main_frame, text="Select Image", padding="10")
    file_frame.pack(fill=tk.X, pady=10)
    
    # Row 1: Browse and Random buttons
    btn_row = ttk.Frame(file_frame)
    btn_row.pack(fill=tk.X, pady=(0, 10))
    
    ttk.Button(btn_row, text="Browse...", command=browse_file).pack(side=tk.LEFT, padx=(0, 10))
    ttk.Button(btn_row, text="Random 10", command=select_random_10).pack(side=tk.LEFT)
    
    # Row 2: Path entry
    path_row = ttk.Frame(file_frame)
    path_row.pack(fill=tk.X, pady=(0, 5))
    
    ttk.Label(path_row, text="Or paste path:").pack(side=tk.LEFT)
    path_entry = ttk.Entry(path_row, width=35)
    path_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
    ttk.Button(path_row, text="Use", command=use_path_entry, width=6).pack(side=tk.LEFT)
    
    # Selected file label
    file_label = ttk.Label(file_frame, text="No file selected", foreground="gray")
    file_label.pack(anchor=tk.W, pady=(5, 0))
    
    # Mode selection
    mode_frame = ttk.LabelFrame(main_frame, text="Mode", padding="10")
    mode_frame.pack(fill=tk.X, pady=5)
    
    mode_var = tk.StringVar(value="preview")
    
    ttk.Radiobutton(mode_frame, text="Preview - Show detected overlay box on image", 
                   variable=mode_var, value="preview").pack(anchor=tk.W)
    ttk.Radiobutton(mode_frame, text="Scan - Print edge intensity analysis", 
                   variable=mode_var, value="scan").pack(anchor=tk.W)
    
    # Edge selection (for scan mode)
    edge_frame = ttk.LabelFrame(main_frame, text="Edge to Scan (scan mode only)", padding="10")
    edge_frame.pack(fill=tk.X, pady=5)
    
    edge_var = tk.StringVar(value="all")
    edge_options = ttk.Frame(edge_frame)
    edge_options.pack(fill=tk.X)
    
    for edge in ["all", "top", "bottom", "left", "right"]:
        ttk.Radiobutton(edge_options, text=edge.capitalize(), 
                       variable=edge_var, value=edge).pack(side=tk.LEFT, padx=5)
    
    # Run button
    run_btn = ttk.Button(main_frame, text="Run", command=run_action, state=tk.DISABLED)
    run_btn.pack(pady=15)
    
    root.mainloop()
    return True


def browse_and_select(initial_dir: Path = None, mode: str = "preview"):
    """
    Open a file picker dialog to select an image, then run the specified mode.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        print("❌ tkinter not available for file picker")
        return False
    
    # Use default output dir if not specified
    if initial_dir is None:
        initial_dir = DEFAULT_OUTPUT_DIR
    
    # Ensure directory exists
    if not initial_dir.exists():
        initial_dir = Path.home()
    
    # Create hidden root window
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)  # Bring dialog to front
    
    # Open file picker
    file_path = filedialog.askopenfilename(
        title="Select Video Ad Image",
        initialdir=str(initial_dir),
        filetypes=[
            ("Image files", "*.png *.jpg *.jpeg *.webp"),
            ("PNG files", "*.png"),
            ("All files", "*.*")
        ]
    )
    
    root.destroy()
    
    if not file_path:
        print("❌ No file selected")
        return False
    
    image_path = Path(file_path)
    print(f"📁 Selected: {image_path}")
    print()
    
    if mode == "preview":
        return preview_overlay(image_path)
    elif mode == "scan":
        return scan_edge(image_path, "all", 150)
    else:
        print(f"❌ Unknown mode: {mode}")
        return False


def main():
    # If no arguments, launch GUI
    if len(sys.argv) == 1:
        launch_gui()
        return
    
    parser = argparse.ArgumentParser(
        description="Debug tools for video overlay detection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Launch GUI (no arguments)
    python tools/debug_video_overlay.py
    
    # Preview detected overlay on image
    python tools/debug_video_overlay.py preview path/to/image.png
    
    # Scan all edges
    python tools/debug_video_overlay.py scan path/to/image.png
    
    # Scan only top edge
    python tools/debug_video_overlay.py scan path/to/image.png --edge top
    
    # Scan with more rows/columns
    python tools/debug_video_overlay.py scan path/to/image.png --range 200
    
    # Browse for file (opens file picker, defaults to output folder)
    python tools/debug_video_overlay.py browse
    python tools/debug_video_overlay.py browse --mode scan
"""
    )
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Preview command
    preview_parser = subparsers.add_parser("preview", help="Show image with detected overlay box")
    preview_parser.add_argument("image", type=Path, help="Path to image file")
    preview_parser.add_argument("-o", "--output", type=Path, help="Output path for preview image")
    
    # Scan command
    scan_parser = subparsers.add_parser("scan", help="Print edge intensity analysis")
    scan_parser.add_argument("image", type=Path, help="Path to image file")
    scan_parser.add_argument("--edge", choices=["top", "bottom", "left", "right", "all"], 
                            default="all", help="Which edge to analyze")
    scan_parser.add_argument("--range", type=int, default=150, 
                            help="Number of rows/columns to analyze")
    
    # Browse command
    browse_parser = subparsers.add_parser("browse", help="Open file picker to select image")
    browse_parser.add_argument("--mode", choices=["preview", "scan"], default="preview",
                              help="What to do after selecting file (default: preview)")
    browse_parser.add_argument("--dir", type=Path, default=None,
                              help="Initial directory for file picker")
    
    args = parser.parse_args()
    
    if args.command == "browse":
        success = browse_and_select(args.dir, args.mode)
    elif not args.image.exists():
        print(f"❌ Image not found: {args.image}")
        sys.exit(1)
    elif args.command == "preview":
        success = preview_overlay(args.image, args.output)
    elif args.command == "scan":
        success = scan_edge(args.image, args.edge, args.range)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
