"""
Keyword Input GUI

A simple popup interface for entering keywords to scrape.
"""

# Guards must be set BEFORE importing tkinter to prevent Tk's console/menubar init in embedded app
import os, sys
os.environ.setdefault("TK_CONSOLE", "0")
os.environ.setdefault("TK_NO_CONSOLE", "1")
# Help Tk find the correct embedded interpreter (prevents some weird Cocoa/Tk state)
os.environ.setdefault("PYTHONEXECUTABLE", sys.executable)

# --- ultra-early boot log for embedded debugging ---
import time, traceback
_logdir = os.path.join(os.environ.get("SCRAPER_HOME", os.path.expanduser("~/Documents/Amazon_Scrape")), "logs")
os.makedirs(_logdir, exist_ok=True)
_gui_boot = os.path.join(_logdir, "gui_boot.log")
def _glog(msg):
    try:
        with open(_gui_boot, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass

_glog("START keyword_input.py")

# Load environment variables from config/launcher.env if present
def _load_launcher_env():
    env_file = os.path.join(os.environ.get("SCRAPER_HOME", os.path.expanduser("~/Documents/Amazon_Scrape")), "config", "launcher.env")
    if os.path.exists(env_file):
        _glog(f"Loading env from {env_file}")
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
                _glog(f"  Set {k.strip()}={v.strip()}")
    else:
        _glog(f"No launcher.env found at {env_file}")

_load_launcher_env()

try:
    _glog("before tkinter import")
    import tkinter as tk
    from tkinter import messagebox, simpledialog, ttk, scrolledtext
    from tkinter import font as tkfont
    _glog("after tkinter import")
except Exception as e:
    _glog(f"tkinter import failed: {e}\n{traceback.format_exc()}")
    raise

import json
import logging
from datetime import datetime
import subprocess
import threading
import re

# Ensure module imports resolve to run in-process (no extra Python app)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Base dir resolver (shared across GUI/scheduler/tools)
def get_base_dir():
    """
    Return the root directory for user data (output/, logs/, etc.).
    Prefers SCRAPER_HOME so everything is centralized.
    Falls back to Documents/Amazon_Scrape when packaged, or source dir when dev.
    """
    shared = os.getenv("SCRAPER_HOME")
    if shared and shared.strip():
        return os.path.abspath(shared)
    if getattr(sys, 'frozen', False):
        # Packaged app default
        return os.path.expanduser("~/Documents/Amazon_Scrape")
    # Source default
    return os.path.dirname(os.path.abspath(__file__))

# Set up logging (now using SCRAPER_HOME-aware base)
import logging
base_dir = get_base_dir()
log_dir = os.path.join(base_dir, "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "keyword_input.log")
logging.basicConfig(
    filename=log_file,
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)
logging.info("\n\n=== KEYWORD_INPUT STARTED ===")
logging.info(f"Python: {sys.version}")
logging.info(f"Executable: {sys.executable}")
logging.info(f"Working directory: {os.getcwd()}")
logging.info(f"sys.path: {sys.path}")

# Avoid NameError in lazy-import checks later
ksc_search_and_capture = None 
kproc_latest_missing = None

# Constants and placeholders
PLACEHOLDER = "<choose from menu>"
DEFAULT_PROFILE = "/Users/dan.maguire/ChromeProfiles/kroger_clean_profile"  # used elsewhere already

# --- UI tokens (light + dark palettes) ---
PALETTE = {
    "light": {
        "bg":        "#f5f7fa",   # app background
        "card":      "#ffffff",
        "text":      "#0f172a",
        "muted":     "#475569",
        "border":    "#e5e7eb",
        "primary":   "#2563eb",   # blue-600
        "primary_h": "#1e40af",   # hover/press
        "secondary": "#334155",   # slate-700
        "secondary_h":"#1f2937",
        "danger":    "#dc2626",
        "danger_h":  "#b91c1c",
        "success":   "#16a34a",
        "bar":       "#2563eb",
        "trough":    "#e5e7eb",
        "field_bg":  "#ffffff",
        "field_fg":  "#0f172a",
    },
    "dark": {
        "bg":        "#0b1220",
        "card":      "#101827",
        "text":      "#e5e7eb",
        "muted":     "#9ca3af",
        "border":    "#1f2a3a",
        "primary":   "#3b82f6",
        "primary_h": "#1d4ed8",
        "secondary": "#475569",
        "secondary_h":"#334155",
        "danger":    "#ef4444",
        "danger_h":  "#b91c1c",
        "success":   "#22c55e",
        "bar":       "#3b82f6",
        "trough":    "#1f2937",
        "field_bg":  "#0f172a",
        "field_fg":  "#e5e7eb",
    }
}

# Retailer adapter registry
from core.retailers import get as get_retailer_adapter, list_adapters
from core.run_context import RunContext
from core.paths import output_dir_for, logs_dir_for
from widgets.retailer_picker import RetailerPicker
# ensure retailer adapters are registered
import retailers.kroger.adapter  # noqa: F401
import retailers.amazon.adapter  # noqa: F401
import retailers.instacart.adapter  # noqa: F401
import retailers.walmart.adapter  # noqa: F401
import retailers.target.adapter  # noqa: F401
import retailers.tiktokshop.adapter  # noqa: F401

# Optional: try eager imports; if they fail, globals stay None and the lazy path runs later
try:
    from kroger_search_and_capture import search_and_capture as ksc_search_and_capture
except Exception:
    pass

try:
    from process_saved_html import process_latest_missing as kproc_latest_missing
except Exception:
    pass

class KeywordInputApp:
    def _safe_ttk_themes(self):
        """Return list of safe ttk themes (exclude aqua on macOS to avoid menu crash)."""
        names = list(self.style.theme_names())
        # Tk + macOS: aqua can crash when building the menubar
        if sys.platform == 'darwin' and 'aqua' in names:
            names.remove('aqua')
        return names
    
    def __init__(self, root):
        """Initialize the application"""
        self.root = root
        self.root.title("Retail Ad Monitor")
        
        # Load saved window geometry or use adaptive defaults based on screen size
        self.geometry_file = os.path.join(get_base_dir(), "logs", "window_geometry.txt")
        self.state_file = os.path.join(get_base_dir(), "logs", "gui_state.json")
        saved_geometry = self.load_window_geometry()
        if saved_geometry:
            self.root.geometry(saved_geometry)
        else:
            # Adaptive sizing: use 70% of screen, capped at reasonable max
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            win_w = min(int(screen_w * 0.7), 1200)
            win_h = min(int(screen_h * 0.8), 900)
            # Center on screen
            x = (screen_w - win_w) // 2
            y = (screen_h - win_h) // 2
            self.root.geometry(f"{win_w}x{win_h}+{x}+{y}")
        
        self.root.minsize(700, 500)
        
        # Save geometry on window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Set up grid layout for main window: [row 0 = scrollable content | row 1 = fixed footer]
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        
        self.placeholder_text = "Enter keywords (one per line)"
        
        # Initialize logger
        self.logger = None
        
        # Theme will be applied through apply_theme function
        self.theme = "light"  # Could be made user-configurable in the future
        
        # Typography similar to web (Inter with sensible fallbacks)
        try:
            tkfont.nametofont("TkDefaultFont").configure(family="Inter", size=11)
            tkfont.nametofont("TkTextFont").configure(family="Inter", size=11)
            tkfont.nametofont("TkHeadingFont").configure(family="Inter", size=14, weight="bold")
        except Exception:
            pass

        # ttk styles matching web look
        self.style = ttk.Style()
        
        # Try to use a theme that honors color overrides (avoid 'aqua' which ignores most styling)
        theme_applied = False
        for tname in self._safe_ttk_themes():
            try:
                self.style.theme_use(tname)
                print(f"Applied theme: {tname}")
                theme_applied = True
                break
            except Exception as e:
                print(f"Failed to apply theme {tname}: {e}")
        
        if not theme_applied:
            print("Warning: Could not apply any compatible theme. UI styling may be limited.")
            
        # Apply the theme
        self.apply_theme(self.style, mode=self.theme)
        
        # Load saved UI prefs and apply (ttk theme + our palette)
        prefs = self._load_ui_prefs()
        tt = prefs.get("ttk_theme")
        # Coerce aqua -> clam on macOS to avoid crash
        if sys.platform == 'darwin' and tt == 'aqua':
            tt = 'clam'
            self._save_ui_prefs(ttk_theme=tt, palette=prefs.get("palette", "light"))
        if tt and tt in self.style.theme_names():
            self.apply_ttk_theme(tt)
        # apply our palette (light/dark)
        self.apply_palette(prefs.get("palette", "light"))
        
        # Use the path resolver function
        self.project_dir = get_base_dir()
        
        # Set application icon
        try:
            icon_path = os.path.join(self.project_dir, "icon2.png")
            if os.path.exists(icon_path):
                self.root.iconphoto(True, tk.PhotoImage(file=icon_path))
        except Exception as e:
            print(f"Could not load icon: {e}")
        
        # Set up signal handler for dock icon clicks
        self.setup_signal_handler()
        
        # Initialize variables with correct paths using path resolver
        self.history_file = os.path.join(get_base_dir(), "output", "client_history.json")
        self.schedule_file = os.path.join(get_base_dir(), "output", "schedule_config.json")
        
        self.client_history = self.load_client_history()
        self.schedule_config = self.load_schedule_config()
        self.day_vars = {}  # Will store day checkbox variables
        
        # Check scheduler daemon status (no auto-start by default)
        self.daemon_status = self.check_daemon_status()
        if not self.daemon_status and os.getenv("GUI_AUTO_START_DAEMON") == "1":
            self.start_daemon_automatically()
            self.daemon_status = True
        
        # Start periodic daemon status refresh (every 30 seconds)
        self.refresh_daemon_status()
        
        # Set up the main frame with notebook (tabs)
        main_frame = ttk.Frame(root, padding=10, style='App.TFrame')
        main_frame.grid(row=0, column=0, sticky="nsew")
        main_frame.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)

        # Create notebook for tabs
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.grid(row=0, column=0, sticky="nsew")
        
        # ===== TAB 1: Ad Scraper (existing functionality) =====
        ad_scraper_frame = ttk.Frame(self.notebook, padding=10, style='App.TFrame')
        ad_scraper_frame.rowconfigure(0, weight=1)
        ad_scraper_frame.columnconfigure(0, weight=1)
        self.notebook.add(ad_scraper_frame, text="  Ad Scraper  ")
        
        # Create a canvas for scrolling (inside Ad Scraper tab)
        canvas = tk.Canvas(ad_scraper_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(ad_scraper_frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        # Place canvas + scrollbar into the grid
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        # Create scrollable frame inside canvas
        scrollable_frame = ttk.Frame(canvas)

        # Create window in canvas for scrollable content and keep a reference
        self._sf_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        # Make the canvas height track contents and the width match canvas
        def _on_canvas_configure(e):
            canvas.itemconfigure(self._sf_window, width=e.width)
        canvas.bind("<Configure>", _on_canvas_configure)

        # Keep the scrollregion updated when the inner frame changes size
        def _on_inner_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        scrollable_frame.bind("<Configure>", _on_inner_configure)

        # Store references
        self.canvas = canvas
        self.scrollable_frame = scrollable_frame
        
        # Store reference to get_active_canvas for use in scroll handlers
        def _get_active_canvas():
            """Get the canvas for the currently active tab."""
            try:
                active_tab = self.notebook.index(self.notebook.select())
                if active_tab == 0:
                    return self.canvas  # Ad Scraper tab
                elif active_tab == 1 and hasattr(self, 'sc_canvas'):
                    return self.sc_canvas  # Screen Capture tab
            except:
                pass
            return self.canvas
        
        self._get_active_canvas = _get_active_canvas
        
        # Mouse wheel scroll handler
        def _on_mousewheel(event):
            # Don't scroll if we're in a dropdown
            widget_class = str(event.widget.winfo_class())
            if 'Listbox' in widget_class or 'Combobox' in widget_class:
                return "break"
            
            target_canvas = self._get_active_canvas()
            
            # On macOS, delta can be positive or negative
            # Positive delta = scroll up, negative = scroll down
            if event.delta:
                # macOS uses smaller delta values, scale appropriately
                if sys.platform == 'darwin':
                    # macOS: delta is typically 1-4 for trackpad, larger for mouse
                    scroll_units = -int(event.delta)
                else:
                    # Windows: delta is ±120
                    scroll_units = -int(event.delta / 120) * 3
                target_canvas.yview_scroll(scroll_units, "units")
            return "break"
        
        # Linux scroll buttons
        def _on_scroll_up(event):
            target_canvas = self._get_active_canvas()
            target_canvas.yview_scroll(-3, "units")
            return "break"
        
        def _on_scroll_down(event):
            target_canvas = self._get_active_canvas()
            target_canvas.yview_scroll(3, "units")
            return "break"
        
        # Bind scroll events globally
        self.root.bind_all("<MouseWheel>", _on_mousewheel)
        if sys.platform != 'darwin':
            # Linux scroll buttons
            self.root.bind_all("<Button-4>", _on_scroll_up)
            self.root.bind_all("<Button-5>", _on_scroll_down)
        
        # Keyboard scroll support (arrow keys, page up/down)
        def _on_key_scroll(event):
            # Skip if focus is in a text entry widget
            widget = event.widget
            if isinstance(widget, (tk.Entry, tk.Text, ttk.Entry)):
                return
            
            target_canvas = self._get_active_canvas()
            
            if event.keysym == 'Up':
                target_canvas.yview_scroll(-1, "units")
            elif event.keysym == 'Down':
                target_canvas.yview_scroll(1, "units")
            elif event.keysym == 'Prior':  # Page Up
                target_canvas.yview_scroll(-1, "pages")
            elif event.keysym == 'Next':  # Page Down
                target_canvas.yview_scroll(1, "pages")
            elif event.keysym == 'Home':
                target_canvas.yview_moveto(0)
            elif event.keysym == 'End':
                target_canvas.yview_moveto(1)
        
        self.root.bind_all("<Up>", _on_key_scroll)
        self.root.bind_all("<Down>", _on_key_scroll)
        self.root.bind_all("<Prior>", _on_key_scroll)
        self.root.bind_all("<Next>", _on_key_scroll)
        self.root.bind_all("<Home>", _on_key_scroll)
        self.root.bind_all("<End>", _on_key_scroll)
        
        # ===== TAB 2: Screen Capture =====
        self._build_screen_capture_tab()

        # Client/Product field + New button
        client_frame = ttk.Frame(scrollable_frame, style='Card.TFrame')
        client_frame.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(client_frame, text="Client/Product:", style='TLabel').pack(side=tk.LEFT)

        # Alphabetize clients
        clients = sorted(self.client_history.keys(), key=str.lower)

        # Load saved state to restore last selected client
        saved_state = self.load_gui_state()
        last_client = saved_state.get("selected_client", PLACEHOLDER) if saved_state else PLACEHOLDER
        # Verify the client still exists
        if last_client not in clients and last_client != PLACEHOLDER:
            last_client = PLACEHOLDER
        
        self.client_var = tk.StringVar(value=last_client)

        self.client_dropdown = ttk.Combobox(
            client_frame,
            textvariable=self.client_var,
            values=[PLACEHOLDER] + clients,
            width=30,
            style='App.TCombobox',
            state="readonly",
        )
        self.client_dropdown.pack(side=tk.LEFT, padx=(10, 6))
        self.client_dropdown.bind("<<ComboboxSelected>>", self.on_client_selected)
        
        # Note: Combobox dropdown list scrolling is handled internally by ttk
        # We prevent the main window scroll in the canvas mousewheel handler
        # by checking if the event widget is a Combobox

        # True "New…" button (not inside the dropdown)
        self.new_client_btn = ttk.Button(
            client_frame,
            text="New…",
            command=self.on_new_client,
            style='Primary.TButton',
        )
        self.new_client_btn.state(['!disabled'])  # ensure enabled
        self.new_client_btn.pack(side=tk.LEFT)
        
        self.remove_client_btn = ttk.Button(
            client_frame,
            text="Remove…",
            command=self.on_remove_client,
        )
        self.remove_client_btn.pack(side=tk.LEFT, padx=(4, 0))
        
        # Build adapter maps (exact and case-insensitive)
        adapters = list_adapters()
        self._retailer_by_name = {a.display_name: a.slug for a in adapters}
        self._retailer_by_name_ci = {a.display_name.lower(): a.slug for a in adapters}
        print(f"Registered adapters: {self._retailer_by_name}")
        
        # Multi-select retailer picker
        retailer_frame = ttk.LabelFrame(scrollable_frame, text="Select Retailers", style='Card.TLabelframe', padding=10)
        retailer_frame.pack(fill=tk.X, padx=20, pady=(10, 5))
        
        # Determine which retailers are unavailable (not registered)
        all_names = ["Amazon", "Walmart", "Kroger", "Instacart", "Albertsons", "Doordash", "gopuff", "Target", "Hyvee", "Meijer", "Ahold"]
        unavailable = {name for name in all_names if name.lower() not in self._retailer_by_name_ci}
        
        self.retailer_picker = RetailerPicker(retailer_frame, unavailable=unavailable, columns=4)
        self.retailer_picker.pack(fill=tk.X, padx=5, pady=5)

        # --- Profile Health Status Bar ---
        self._health_frame = ttk.Frame(retailer_frame, style='Card.TFrame')
        self._health_frame.pack(fill=tk.X, padx=5, pady=(0, 5))
        self._health_labels: dict[str, tk.Label] = {}
        self._build_health_bar()

        # Restore saved retailer selections or use defaults
        if saved_state and "selected_retailers" in saved_state:
            # Restore from saved state
            for retailer in saved_state["selected_retailers"]:
                if retailer in self.retailer_picker.vars:
                    self.retailer_picker.vars[retailer].set(True)
        else:
            # Pre-select Kroger and Instacart by default (first time only)
            if "Kroger" in self.retailer_picker.vars:
                self.retailer_picker.vars["Kroger"].set(True)
            if "Instacart" in self.retailer_picker.vars:
                self.retailer_picker.vars["Instacart"].set(True)
        
        # --- Debug Options (collapsible, collapsed by default) ---
        debug_header_frame = ttk.Frame(scrollable_frame, style='Card.TFrame')
        debug_header_frame.pack(fill=tk.X, padx=20, pady=(6, 0))
        
        self.debug_expanded = tk.BooleanVar(value=False)  # Collapsed by default
        
        def toggle_debug():
            if self.debug_expanded.get():
                debug_content_frame.pack(fill=tk.X, padx=20, pady=(0, 10))
                debug_toggle_btn.config(text="▼ Debug Options")
            else:
                debug_content_frame.pack_forget()
                debug_toggle_btn.config(text="▶ Debug Options")
        
        debug_toggle_btn = ttk.Button(
            debug_header_frame, 
            text="▶ Debug Options",
            command=lambda: (self.debug_expanded.set(not self.debug_expanded.get()), toggle_debug()),
            width=20
        )
        debug_toggle_btn.pack(side=tk.LEFT)
        
        debug_content_frame = ttk.LabelFrame(scrollable_frame, text="", style='Card.TLabelframe', padding=10)
        # Don't pack initially - collapsed by default

        self.debug_vars = {}
        self.debug_vars['break_on_px']        = tk.BooleanVar(value=False)
        self.debug_vars['break_on_blocked']   = tk.BooleanVar(value=False)
        self.debug_vars['line_trace']         = tk.BooleanVar(value=False)
        self.debug_vars['pdb_on_exception']   = tk.BooleanVar(value=True)
        self.debug_vars['open_run_folder']    = tk.BooleanVar(value=True)

        ttk.Checkbutton(debug_content_frame, text="Break on PX",        variable=self.debug_vars['break_on_px']).grid(row=0, column=0, sticky="w", padx=(0,20))
        ttk.Checkbutton(debug_content_frame, text="Break on /blocked",  variable=self.debug_vars['break_on_blocked']).grid(row=0, column=1, sticky="w", padx=(0,20))
        ttk.Checkbutton(debug_content_frame, text="Line trace (typing)",variable=self.debug_vars['line_trace']).grid(row=0, column=2, sticky="w", padx=(0,20))
        ttk.Checkbutton(debug_content_frame, text="PDB on exception",   variable=self.debug_vars['pdb_on_exception']).grid(row=0, column=3, sticky="w")

        paths_frame = ttk.Frame(debug_content_frame, style='Card.TFrame')
        paths_frame.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        paths_frame.columnconfigure(0, weight=1)
        paths_frame.columnconfigure(1, weight=1)

        ttk.Label(paths_frame, text="Profile dir:", style='TLabel').grid(row=0, column=0, sticky="w", pady=(0,5))
        self.profile_dir_var = tk.StringVar(value="<auto: retailer-specific>")
        ttk.Entry(paths_frame, textvariable=self.profile_dir_var, width=50).grid(row=1, column=0, sticky="ew", padx=(0,10))

        ttk.Label(paths_frame, text="Output root:", style='TLabel').grid(row=0, column=1, sticky="w", pady=(0,5))
        self.output_root_var = tk.StringVar(value="<auto: retailer-specific>")
        ttk.Entry(paths_frame, textvariable=self.output_root_var, width=50).grid(row=1, column=1, sticky="ew")

        ttk.Checkbutton(debug_content_frame, text="Open run folder when done", variable=self.debug_vars['open_run_folder']).grid(row=2, column=0, columnspan=2, sticky="w", pady=(5,0))
        
        # Instructions
        instructions = ttk.Label(
            scrollable_frame,
            text="Enter keywords to scrape (one per line):",
            style='Body.TLabel'
        )
        instructions.pack(anchor="w", pady=(0, 10))
        
        # Keyword input area
        # Get current theme colors
        palette = PALETTE[self.theme]
        
        self.keyword_input = scrolledtext.ScrolledText(scrollable_frame, height=5)
        self.keyword_input.pack(fill=tk.X, expand=False, pady=(0, 15))
        self.keyword_input.configure(
            background=palette["field_bg"], 
            foreground=palette["field_fg"], 
            insertbackground=palette["text"], 
            borderwidth=1, 
            relief='solid',
            font=("Inter", 11)
        )

        # Add placeholder text
        self.placeholder_text = "<enter keywords here>"
        self.keyword_input.insert(tk.END, self.placeholder_text)
        self.keyword_input.config(fg="gray")
        
        # Bind events to handle placeholder behavior
        self.keyword_input.bind("<FocusIn>", self.on_keyword_focus_in)
        self.keyword_input.bind("<FocusOut>", self.on_keyword_focus_out)
        
        # Schedule frame
        schedule_frame = ttk.Labelframe(scrollable_frame, text="Schedule Settings", padding=10, style='Card.TLabelframe')
        schedule_frame.pack(fill=tk.X, pady=(0, 15))

        # Number of runs per day
        runs_frame = ttk.Frame(schedule_frame, style='Card.TFrame')
        runs_frame.pack(fill=tk.X, pady=(0, 10))

        runs_label = ttk.Label(runs_frame, text="Runs per day:", style='TLabel')
        runs_label.pack(side=tk.LEFT)
        
        self.runs_var = tk.IntVar(value=3)  # Default to 3 runs per day
        runs_spinbox = ttk.Spinbox(
            runs_frame, 
            from_=1, 
            to=5, 
            width=5, 
            textvariable=self.runs_var,
            command=self.update_time_selectors
        )
        runs_spinbox.pack(side=tk.LEFT, padx=(10, 0))
        
        # Time selectors frame
        self.times_frame = ttk.Frame(schedule_frame, style='Card.TFrame')
        self.times_frame.pack(fill=tk.X)
        
        # Time selector variables
        self.time_vars = []
        self.time_entries = []
        
        # Create initial time selectors (default to 3)
        self.update_time_selectors()
        # Immediately compute conflict status for initial selectors
        try:
            if hasattr(self, 'refresh_all_conflict_displays'):
                self.refresh_all_conflict_displays()
        except Exception:
            pass
        
        # Days of week selection
        days_frame = ttk.Labelframe(schedule_frame, text="Days to Run", padding=5, style='Card.TLabelframe')
        days_frame.pack(fill=tk.X, pady=(10, 0))

        # Create day checkboxes
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_boxes_frame = ttk.Frame(days_frame, style='Card.TFrame')
        day_boxes_frame.pack(fill=tk.X, pady=5)
        
        # Create checkboxes for each day
        for i, day in enumerate(day_names):
            var = tk.BooleanVar(value=True)  # Default to selected
            self.day_vars[day] = var
            
            cb = ttk.Checkbutton(day_boxes_frame, text=day[:3], variable=var)
            cb.grid(row=0, column=i, padx=5)
            
            # Add event handler to refresh conflict displays when days change
            def on_day_changed(*args):
                if hasattr(self, 'refresh_all_conflict_displays'):
                    self.refresh_all_conflict_displays()
                    self.refresh_save_button_state()
            var.trace('w', on_day_changed)
        
        # Schedule control buttons
        schedule_buttons_frame = ttk.Frame(schedule_frame, style='Card.TFrame')
        schedule_buttons_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.schedule_button = ttk.Button(
            schedule_buttons_frame,
            text="Save Schedule",
            command=self.save_schedule,
            style='Primary.TButton'
        )
        self.schedule_button.pack(side=tk.LEFT, padx=(0, 5))
        self.schedule_button.state(['disabled'])
        
        self.clear_schedule_button = ttk.Button(
            schedule_buttons_frame,
            text="🗑 Clear Schedule",
            command=self.clear_schedule,
            width=16
        )
        self.clear_schedule_button.pack(side=tk.LEFT, padx=(0, 10))
        
        # Scheduler management buttons (right side of Schedule Settings)
        ttk.Button(
            schedule_buttons_frame,
            text="📊 Run History",
            command=self.view_run_history,
            width=14
        ).pack(side=tk.RIGHT, padx=2)
        
        ttk.Button(
            schedule_buttons_frame,
            text="📋 View Logs",
            command=self.view_scheduler_logs,
            width=12
        ).pack(side=tk.RIGHT, padx=2)
        
        ttk.Button(
            schedule_buttons_frame,
            text="🔄 Restart",
            command=self.restart_scheduler,
            width=10
        ).pack(side=tk.RIGHT, padx=2)
        
        # Fixed footer with Scrape / Clear buttons (always visible)
        footer = ttk.Frame(self.root)
        footer.grid(row=1, column=0, sticky="ew", pady=(4, 8))
        footer.columnconfigure(0, weight=1)

        # Start scraping button
        self.scrape_button = ttk.Button(
            footer,
            text="Start Scraping",
            command=self.start_scraping,
            style='Primary.TButton'
        )
        self.scrape_button.pack(side=tk.RIGHT, padx=(8, 12))
        
        # Review Brands button
        self.review_brands_button = ttk.Button(
            footer,
            text="Review Brands",
            command=self.launch_brand_review_tool,
            style='Secondary.TButton'
        )
        self.review_brands_button.pack(side=tk.RIGHT, padx=(0, 8))

        # Clear button
        self.clear_button = ttk.Button(
            footer,
            text="Clear",
            command=self.clear_keywords,
            style='Danger.TButton'
        )
        self.clear_button.pack(side=tk.RIGHT)

        # Status label in footer
        daemon_text = "✅ Daemon running" if self.daemon_status else "⚠️ Daemon stopped"
        self.status_label = ttk.Label(
            footer,
            text=f"Ready to scrape | {daemon_text}",
            style='Body.TLabel'
        )
        self.status_label.pack(side=tk.LEFT, padx=(12, 0))
        
        # Daemon control buttons
        daemon_controls_frame = ttk.Frame(footer, style='App.TFrame')
        daemon_controls_frame.pack(side=tk.LEFT, padx=(10, 0))
        
        ttk.Button(
            daemon_controls_frame,
            text="🔄 Refresh",
            command=self.refresh_daemon_status_manual,
            width=10
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Button(
            daemon_controls_frame,
            text="▶️ Start",
            command=self.start_daemon_manual,
            width=10
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Button(
            daemon_controls_frame,
            text="⏹️ Stop",
            command=self.stop_daemon_manual,
            width=10
        ).pack(side=tk.LEFT, padx=2)
        
        # Schedule viewer button
        ttk.Button(
            daemon_controls_frame,
            text="📅 See Full Schedule",
            command=self.show_full_schedule,
            width=18
        ).pack(side=tk.LEFT, padx=2)

        # --- App log console (scrollable content) ---
        log_frame = ttk.LabelFrame(scrollable_frame, text="Activity", style='Card.TLabelframe', padding=8)
        log_frame.pack(fill=tk.BOTH, expand=False, pady=(10, 0))

        self.app_log = scrolledtext.ScrolledText(log_frame, height=12, wrap="word")
        self.app_log.pack(fill=tk.BOTH, expand=True)
        self.app_log.configure(font=("Inter", 10), state="disabled")
        
        # Enable smooth scrolling for activity log
        def _on_log_scroll(event):
            if event.delta > 0 or getattr(event, "num", None) == 4:
                self.app_log.yview_scroll(-1, "units")
            else:
                self.app_log.yview_scroll(1, "units")
            return "break"  # Prevent event propagation
        self.app_log.bind("<MouseWheel>", _on_log_scroll)
        self.app_log.bind("<Button-4>", _on_log_scroll)
        self.app_log.bind("<Button-5>", _on_log_scroll)

        # Initialize save button state
        self.refresh_save_button_state()
    
    def _schedule_retailer_slug(self) -> str:
        """
        Return a single retailer slug used for scheduling/file paths.
        - If exactly one retailer is selected in the picker, use it.
        - Otherwise, fall back to 'kroger' for backward compatibility.
        """
        try:
            sel = self.retailer_picker.get_selected()
            if len(sel) == 1:
                name = sel[0]
                return self._retailer_by_name.get(name, name.lower())
        except Exception:
            pass
        return "kroger"
    
    # --- Profile Health Bar ---------------------------------------------------

    def _build_health_bar(self):
        """Build per-retailer health indicators in self._health_frame."""
        from utils.profile_health import get_all_statuses
        statuses = get_all_statuses()

        # Clear existing widgets
        for w in self._health_frame.winfo_children():
            w.destroy()
        self._health_labels.clear()

        _STATUS_ICON = {"healthy": "🟢", "degraded": "🟡", "blocked": "🔴"}
        registered_slugs = sorted(self._retailer_by_name.values())

        for slug in registered_slugs:
            entry = statuses.get(slug, {})
            status = entry.get("status", "healthy")
            icon = _STATUS_ICON.get(status, "⚪")
            consec = entry.get("consecutive_failures", 0)
            tip = f"{slug.title()}: {status}"
            if consec:
                tip += f" ({consec} consecutive failures)"

            lbl = tk.Label(
                self._health_frame,
                text=f" {icon} {slug.title()} ",
                font=("Inter", 9),
                bg="#2b2b2b" if status == "healthy" else ("#3d3520" if status == "degraded" else "#3d2020"),
                fg="#e0e0e0",
                padx=4, pady=1,
            )
            lbl.pack(side=tk.LEFT, padx=(0, 4))
            self._health_labels[slug] = lbl

        # Reset button (only shown if any retailer is blocked)
        any_blocked = any(
            statuses.get(s, {}).get("status") == "blocked"
            for s in registered_slugs
        )
        if any_blocked:
            reset_btn = tk.Button(
                self._health_frame,
                text="🔄 Reset after re-login",
                font=("Inter", 9),
                bg="#3a5a3a", fg="#e0e0e0",
                activebackground="#4a7a4a", activeforeground="#ffffff",
                relief="flat", padx=6, pady=1,
                command=self._reset_profile_health,
            )
            reset_btn.pack(side=tk.RIGHT, padx=(4, 0))

    def _refresh_health_bar(self):
        """Rebuild the health bar (call after scrapes complete)."""
        try:
            self._build_health_bar()
        except Exception:
            pass

    def _reset_profile_health(self):
        """Reset all blocked retailers to healthy (after manual re-login)."""
        from utils.profile_health import get_all_statuses, reset_retailer
        statuses = get_all_statuses()
        reset_names = []
        for slug, entry in statuses.items():
            if entry.get("status") in ("blocked", "degraded"):
                reset_retailer(slug)
                reset_names.append(slug.title())
        if reset_names:
            self.notify(f"Reset profile health for: {', '.join(reset_names)}", "info")
        self._build_health_bar()

    # --- End Profile Health Bar -----------------------------------------------

    def log(self, msg: str):
        """Log to stdout and to client-specific logger if configured."""
        try:
            print(msg)
        except Exception:
            pass
        try:
            if hasattr(self, 'logger') and self.logger:
                self.logger.info(msg)
        except Exception:
            pass
    
    def _log_console(self, msg: str):
        """Write to the activity console."""
        try:
            self.app_log.configure(state="normal")
            self.app_log.insert("end", msg.rstrip() + "\n")
            self.app_log.see("end")
        finally:
            self.app_log.configure(state="disabled")
    
    def activity_clear(self):
        """Clear the activity console."""
        try:
            self.app_log.configure(state="normal")
            self.app_log.delete("1.0", "end")
            self.app_log.configure(state="disabled")
        except Exception:
            pass
    
    def _activity_line(self, msg: str, kind: str = "info"):
        """Write one formatted line to the Activity console."""
        from datetime import datetime
        badge = {"info": "•", "warn": "⚠️", "error": "❌", "success": "✅"}.get(kind, "•")
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {badge} {msg}\n"
        try:
            self.app_log.configure(state="normal")
            self.app_log.insert("end", line)
            self.app_log.see("end")
        finally:
            self.app_log.configure(state="disabled")
        # keep status in sync
        if hasattr(self, "status_label"):
            self.status_label.config(text=msg)
    
    def step(self, retailer: str, msg: str, kind: str = "info"):
        """Convenience: prefix message with [Retailer]."""
        self._activity_line(f"[{retailer}] {msg}", kind)
    
    def ok(self, retailer: str, msg: str = "Done"):
        """Mark retailer step as successful."""
        self.step(retailer, msg, "success")
    
    def fail(self, retailer: str, msg: str):
        """Mark retailer step as failed."""
        self.step(retailer, msg, "error")
    
    def timed_step(self, retailer: str, label: str):
        """Context manager for timing a step."""
        from time import monotonic
        from contextlib import contextmanager
        
        @contextmanager
        def _timed():
            t0 = monotonic()
            self.step(retailer, f"{label}…")
            try:
                yield
            finally:
                dt = monotonic() - t0
                self.step(retailer, f"{label} done ({dt:.1f}s)")
        
        return _timed()
    
    def notify(self, msg: str, kind: str = "info"):
        """
        Non-modal notification:
        - writes to console
        - updates status label
        - prints to stdout / file logger if configured
        kind: 'info' | 'warn' | 'error' | 'success'
        """
        prefix = {"info": "ℹ️", "warn": "⚠️", "error": "❌", "success": "✅"}.get(kind, "ℹ️")
        line = f"{prefix} {msg}"
        
        # console
        if hasattr(self, "app_log"):
            self._log_console(line)
        
        # status
        if hasattr(self, "status_label"):
            self.status_label.config(text=msg)
        
        # stdout + file logger
        try:
            print(line)
        except Exception:
            pass
        try:
            if self.logger:
                if kind == "error":
                    self.logger.error(msg)
                elif kind == "warn":
                    self.logger.warning(msg)
                else:
                    self.logger.info(msg)
        except Exception:
            pass
        
    def load_css_variables(self, css_path):
        """Parse :root CSS variables from a stylesheet for reuse in Tkinter."""
        vars_map = {}
        try:
            with open(css_path, 'r', encoding='utf-8') as f:
                css = f.read()
            m = re.search(r":root\s*\{([^}]*)\}", css, re.MULTILINE | re.DOTALL)
            if not m:
                return vars_map
            root_block = m.group(1)
            for line in root_block.splitlines():
                line = line.strip()
                if not line or not line.startswith('--') or ':' not in line:
                    continue
                name, value = line.split(':', 1)
                value = value.strip().rstrip(';')
                vars_map[name.strip()] = value
        except Exception:
            pass
        return vars_map

    def clear_keywords(self):
        """Clear the keyword input area"""
        self.keyword_input.delete(1.0, tk.END)
        self.status_label.config(text="Keywords cleared")
        
    def start_scraping(self):
        """Start the scraping process with the entered keywords"""
        # Get client/product type
        client_type = self.client_var.get().strip()
        if not client_type or client_type == PLACEHOLDER:
            self.notify("Please select a client/product first", "error")
            return
            
        # Create sanitized folder name (remove special characters)
        folder_name = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in client_type)
        
        # Get keywords from the input area
        keywords_text = self.keyword_input.get(1.0, tk.END).strip()
        if not keywords_text:
            self.notify("Please enter some keywords", "warn")
            return
            
        # Split keywords by newlines and clean them
        keywords = [kw.strip() for kw in keywords_text.split('\n') if kw.strip()]
        
        # Get retailer for proper output path
        retailer_slug = self._schedule_retailer_slug()
        
        # Create output directory using retailer-scoped path
        base = get_base_dir()
        output_dir = output_dir_for(base, retailer_slug, folder_name)
        os.makedirs(output_dir, exist_ok=True)
        
        # Save keywords to file
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        keywords_file = os.path.join(output_dir, f"keywords_{timestamp}.txt")
        
        try:
            with open(keywords_file, "w", encoding="utf-8") as f:
                f.write("\n".join(keywords))
                
            self.status_label.config(text=f"Saved {len(keywords)} keywords to {keywords_file}")
            
            # Save client and keywords to history
            self.save_to_history(client_type, keywords)
            
            # Update the dropdown
            self.update_client_dropdown()
            
            # Start the scraping process
            self.run_scraper(keywords)
            
        except (IOError, PermissionError) as e:
            self.notify(f"Failed to save keywords: {e}", "error")
    
    def run_scraper(self, keywords):
        """Run the scraper with the given keywords and then post-process images."""
        try:
            import glob
            
            # Clear activity console and start fresh
            self.activity_clear()
            self._activity_line("Starting run…")

            # Get selected retailers
            selected_retailers = self.retailer_picker.get_selected()
            if not selected_retailers:
                self.notify("Please select at least one retailer to scrape.", "warn")
                return
            
            self.log(f"Selected retailers: {selected_retailers}")
            self.log(f"Adapter map: {self._retailer_by_name}")
            
            # Resolve paths
            client_type = self.client_var.get().strip()
            folder_name = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in client_type)

            # Run sequentially for each selected retailer
            for retailer_name in selected_retailers:
                try:
                    slug = self._retailer_by_name_ci.get(retailer_name.lower())
                    if not slug:
                        self.fail(retailer_name, "No adapter found (skipping)")
                        continue
                    
                    adapter = get_retailer_adapter(slug)
                    self.step(retailer_name, "Setting up…")
                    
                    self._run_scraper_for_retailer(retailer_name, slug, adapter, folder_name, keywords)
                    self.ok(retailer_name, "Finished")
                except Exception as e:
                    self.fail(retailer_name, f"{e}")
                    import traceback
                    self._activity_line(traceback.format_exc(), "warn")
            
            # End-of-run summary
            self._activity_line("All retailers finished.", "success")
            self._refresh_health_bar()
            
        except Exception as e:
            self.log(f"❌ Error: {str(e)}")
            import traceback
            self.log(traceback.format_exc())
    
    def _run_scraper_for_retailer(self, retailer_name, retailer_slug, adapter, folder_name, keywords):
        """Run scraper for a single retailer."""
        import glob

        base = get_base_dir()
        out_dir = output_dir_for(base, retailer_slug, folder_name)
        logs_dir = logs_dir_for(base, retailer_slug)

        profile_dir = os.environ.get(adapter.profile_env) or None

        if profile_dir and not os.path.isdir(profile_dir):
            self.log(f"[{retailer_name}] profile dir not found or not a directory: {profile_dir} (continuing without persistent profile)")
            profile_dir = None

        ctx = RunContext(
            retailer=retailer_slug,
            client=folder_name,
            base_dir=base,
            output_dir=out_dir,
            runs_dir=os.path.join(out_dir, "runs"),
            logs_dir=logs_dir,
            profile_dir=profile_dir,  # Already validated above, can be None
            script_dir=os.path.dirname(os.path.abspath(__file__)),
        )

        # Set up GUI callback for activity logging (required for Walmart scraper)
        ctx.emit = lambda kind, msg, rn=retailer_name: self.step(rn, msg, kind)
        
        # Pass DebugConfig to the core through the adapter
        try:
            from walmart_search_and_capture import DebugConfig
            ctx.debug = DebugConfig(
                break_on_px      = self.debug_vars['break_on_px'].get(),
                break_on_blocked = self.debug_vars['break_on_blocked'].get(),
                line_trace       = self.debug_vars['line_trace'].get(),
                pdb_on_exception = self.debug_vars['pdb_on_exception'].get(),
            )
        except Exception:
            ctx.debug = None

        # Profile dir (do NOT add /Default; PW/Chrome will manage Default inside)
        # Only use debug profile override if it's not the default placeholder
        debug_profile = self.profile_dir_var.get().strip()
        if debug_profile and not debug_profile.startswith("<auto:"):
            ctx.profile_dir = os.path.expanduser(debug_profile)
            # Set environment variable for the specific retailer, not just walmart
            env_var = f"{retailer_slug.upper()}_PROFILE_DIR"
            os.environ[env_var] = ctx.profile_dir
        # else: keep the profile_dir that was already set based on retailer-specific logic above
        
        output_dir = ctx.output_dir  # keep your existing variable name for reuse
        runs_dir = ctx.runs_dir
        
        # Record run start time and baseline JSON set
        run_start_ts = time.time()
        import glob, re
        
        # Baseline before we create any new files this run
        baseline_json = set(glob.glob(os.path.join(runs_dir, "run_results_*.json")))
        # Track what we collect in this GUI run only
        run_pairs = []      # list of tuples: (json_path, html_path)
        seen_json = set()   # to avoid double-adding

        # Build popup
        popup = tk.Toplevel(self.root)
        popup.title(f"Scraping Progress - {retailer_name}")
        popup.geometry("400x150")
        popup.transient(self.root)
        popup.grab_set()

        progress_label = tk.Label(popup, text=f"Starting scraper for {retailer_name}...", pady=10)
        progress_label.pack()

        progress_var = tk.DoubleVar()
        progress_bar = ttk.Progressbar(popup, variable=progress_var, maximum=len(keywords), style='blue.Horizontal.TProgressbar')
        progress_bar.pack(fill=tk.X, padx=20, pady=10)

        keyword_label = tk.Label(popup, text="")
        keyword_label.pack(pady=5)

        auto_close_var = tk.BooleanVar(value=True)
        auto_close_cb = tk.Checkbutton(popup, text="Auto-close when complete", variable=auto_close_var)
        auto_close_cb.pack(pady=5)

        self.status_label.config(text=f"Starting scraper for {retailer_name}...")
        self.root.update()

        # Scrape loop
        success_count = 0
        for i, keyword in enumerate(keywords):
            progress_var.set(i)
            keyword_label.config(text=f"Scraping {i+1}/{len(keywords)}: {keyword}")
            if progress_label.winfo_exists():
                progress_label.config(text=f"Processing keyword {i+1} of {len(keywords)}")
            popup.update()

            self.status_label.config(text=f"Scraping {i+1}/{len(keywords)}: {keyword}")
            self.root.update()

            # Force single-shot runs globally (no retries)
            max_retries = 1
            retry_count = 0
            scraped = False

            while retry_count < max_retries and not scraped:
                if retry_count > 0:
                    retry_msg = f"Retry attempt {retry_count}/{max_retries} for '{keyword}'..."
                    if progress_label.winfo_exists():
                        progress_label.config(text=retry_msg)
                    self.status_label.config(text=retry_msg)
                    self.step(retailer_name, f"Retrying ({retry_count}/{max_retries})...", "warn")
                    popup.update()
                    self.root.update()
                    time.sleep(1.5)

                try:
                    # Show we're fetching with timing
                    with self.timed_step(retailer_name, f"Fetch '{keyword}'"):
                        # Use adapter for all retailers
                        res = adapter.search_and_capture(keyword, ctx)
                    
                    # Normalize result (supports both bool and dict)
                    if isinstance(res, bool):
                        ok, bail, reason = res, False, None
                    else:
                        ok = bool(res.get('ok'))
                        bail = bool(res.get('bail'))
                        reason = res.get('reason')
                    
                    if ok:
                        self.step(retailer_name, f"HTML captured ({i+1}/{len(keywords)})")
                        
                        # Use adapter to collect pairs for this run
                        new_pairs = adapter.collect_pairs_for_run(ctx, run_start_ts)
                        # De-dup by seen_json
                        for (j, h) in new_pairs:
                            if j not in seen_json:
                                run_pairs.append((j, h))
                                seen_json.add(j)
                        
                        scraped = True
                        success_count += 1
                        break
                    
                    # Not ok; decide whether to retry
                    if bail:
                        msg = f"Bailing (no retries): {reason or 'non-retryable'}"
                        self.step(retailer_name, msg, "warn")
                        break  # Stop retrying immediately
                    else:
                        raise RuntimeError("search_and_capture returned False")

                except Exception as e:
                    retry_count += 1
                    if retry_count >= max_retries:
                        err_text = f"Failed to scrape '{keyword}' after {max_retries} attempts: {e}"
                        if progress_label.winfo_exists():
                            progress_label.config(text=f"Error: {err_text}")
                        popup.update()
                        self.notify(err_text, "error")
                        # Continue to next keyword, do not abort whole run

        # Debug print of collected pairs
        print(f"\n📊 Collected {len(run_pairs)} JSON/HTML pairs from this run")
        for i, (jpath, hpath) in enumerate(run_pairs):
            print(f"  {i+1}. JSON: {os.path.basename(jpath)}")
            print(f"     HTML: {os.path.basename(hpath)}")
        
        # Post-processing: TOA/Skyscraper images
        if progress_label.winfo_exists():
            progress_label.config(text="Processing saved HTML files...")
        keyword_label.config(text="")
        popup.update()

        self.status_label.config(text="Processing saved HTML files...")
        self.root.update()

        # Force single-shot runs globally (no retries)
        max_retries = 1
        retry_count = 0
        post_success = False
        last_error = ""
        loop_deadline = time.time() + 6 * 60  # 6-minute watchdog

        while retry_count < max_retries and not post_success:
            if time.time() > loop_deadline:
                last_error = last_error or "Timed out waiting for image extraction."
                break

            if retry_count > 0:
                retry_msg = f"Retry attempt {retry_count}/{max_retries} for HTML processing..."
                if progress_label.winfo_exists():
                    progress_label.config(text=retry_msg)
                self.status_label.config(text=retry_msg)
                popup.update()
                self.root.update()
                time.sleep(1.5)

            try:
                # Small flush delay
                time.sleep(0.75)
                
                # Safety: if for some reason collection missed files, fallback minimally
                if not run_pairs:
                    # Collect ONLY files created during this GUI session (mtime gate)
                    # Search both flat (runs/run_results_*.json) and date subdirs (runs/*/run_results_*.json)
                    all_cands = glob.glob(os.path.join(runs_dir, "run_results_*.json")) + \
                                glob.glob(os.path.join(runs_dir, "*", "run_results_*.json"))
                    cands = sorted([p for p in all_cands
                                    if os.path.getmtime(p) >= run_start_ts - 2], key=os.path.getmtime)
                    for jpath in cands:
                        hpath = jpath.replace("run_results_", "search_results_").replace(".json", ".html")
                        if os.path.exists(hpath):
                            run_pairs.append((jpath, hpath))
                
                if not run_pairs:
                    last_error = "No new run_results_*.json were created in this run."
                    break
                
                total_toa = total_sky = total_car = 0
                per_file_summary = []
                
                for idx, (json_path, html_path) in enumerate(run_pairs, start=1):
                    if progress_label.winfo_exists():
                        progress_label.config(text=f"[{idx}/{len(run_pairs)}] Extracting images...")
                        popup.update()
                    
                    # Use adapter to extract images with timing
                    with self.timed_step(retailer_name, f"Extract images [{idx}/{len(run_pairs)}]"):
                        res = adapter.extract_images(json_path, html_path, ctx)
                    
                    n_toa, n_sky, n_car = res.get("toa", 0), res.get("sky", 0), res.get("car", 0)
                    total_toa += n_toa
                    total_sky += n_sky
                    total_car += n_car
                    per_file_summary.append((os.path.basename(json_path), n_toa, n_sky, n_car))
                    
                    # Update progress with results
                    if progress_label.winfo_exists():
                        progress_label.config(text=f"[{idx}/{len(run_pairs)}] Extracted: TOA={n_toa}, Sky={n_sky}, Car={n_car}")
                        popup.update()
                
                # Summarize across all terms from this run
                # TOA/Skyscraper is only meaningful for Kroger; other retailers
                # capture images during search_and_capture and don't produce TOA output.
                requires_toa = (retailer_slug == "kroger")
                toa_ok = (total_toa + total_sky) > 0
                if toa_ok or not requires_toa:
                    total_imgs = total_toa + total_sky + total_car
                    self.step(retailer_name, f"Images captured ({total_imgs})")
                    print("✅ Image extraction completed for this run:")
                    for jf, a, b, c in per_file_summary:
                        print(f"   - {jf}: TOA={a} Skyscraper={b} Carousel={c}")
                    print(f"TOTAL: TOA={total_toa} Skyscraper={total_sky} Carousel={total_car}")
                    post_success = True
                    break
                else:
                    last_error = "No TOA/Skyscraper produced for any search in this run."
                    retry_count += 1
                    if retry_count < max_retries:
                        print(f"⚠️ None produced; will retry ({retry_count}/{max_retries}).")
                    else:
                        print("❌ Extraction failed after maximum retries.")

            except Exception as e:
                retry_count += 1
                error_msg = f"HTML processing error: {e}" if retry_count < max_retries else f"Failed to process HTML files after {max_retries} attempts: {e}"
                if progress_label.winfo_exists():
                    progress_label.config(text=f"Error: {error_msg}")
                popup.update()
                if retry_count >= max_retries:
                    self.notify(error_msg, "error")
                    self.status_label.config(text="Error processing HTML files")

                if time.time() > loop_deadline:
                    last_error = last_error or "Timed out waiting for image extraction."
                    break

        # Final UI
        progress_var.set(len(keywords))
        if post_success:
                result_msg = f"Completed scraping {success_count}/{len(keywords)} keywords successfully"
                if progress_label.winfo_exists():
                    progress_label.config(text=result_msg)
                popup.update()
                self.notify(result_msg, "success")
                self.status_label.config(text="Scraping completed successfully")
                post_processing_label = tk.Label(
                    popup,
                    text="\n✅ TOA/Skyscraper extraction completed successfully.\nAll images have been generated.\n",
                    fg="green"
                )
                post_processing_label.pack(pady=5)
        else:
                warn = last_error or "No ad images were generated."
                if progress_label.winfo_exists():
                    progress_label.config(text=f"⚠️ {warn}")
                popup.update()
                self.notify(f"Extraction incomplete: {warn}", "warn")
                self.status_label.config(text=f"Extraction incomplete: {warn}")

        tk.Button(popup, text="Close", command=popup.destroy).pack(pady=10)
        if auto_close_var.get():
            popup.after(3000, popup.destroy)

    def load_client_history(self):
        """Load client history from file"""
        if not os.path.exists(self.history_file):
            return {}
            
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    
    def get_all_scheduled_times(self, exclude_client=None):
        """Get all scheduled times from all clients to detect conflicts"""
        scheduled_times = set()
        
        # NEW: Scan schedules/ directory using shared library
        try:
            from pathlib import Path
            import sys
            base = get_base_dir()
            sys.path.insert(0, str(base))
            from schedules.schedules_lib import scan_schedules
            
            schedules = scan_schedules(Path(base))
            for sched in schedules:
                if not sched.enabled:
                    continue
                # Skip the current client if specified
                if exclude_client and sched.client == exclude_client:
                    continue
                
                # Process each time in 24h format
                for time_24h in sched.times:
                    try:
                        hour_24, minute = map(int, time_24h.split(':'))
                        # 5-minute window
                        for day in sched.days:
                            for offset in range(-2, 3):  # -2, -1, 0, 1, 2 minutes
                                conflict_minute = minute + offset
                                conflict_hour = hour_24
                                
                                # Handle minute overflow/underflow
                                if conflict_minute >= 60:
                                    conflict_minute -= 60
                                    conflict_hour += 1
                                elif conflict_minute < 0:
                                    conflict_minute += 60
                                    conflict_hour -= 1
                                    
                                # Handle hour overflow/underflow
                                if conflict_hour >= 24:
                                    conflict_hour = 0
                                elif conflict_hour < 0:
                                    conflict_hour = 23
                                    
                                scheduled_times.add((sched.retailer, day, conflict_hour, conflict_minute))
                    except (ValueError, TypeError):
                        continue
        except Exception as e:
            print(f"Error scanning schedules/ for conflicts: {e}")
        
        # LEGACY: Scan output/ directory
        output_path = os.path.join(get_base_dir(), "output")
        if os.path.exists(output_path):
            def _process_schedule(file_path, client_name_guess):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                    retailer = config.get("retailer", "kroger")
                    client_name = config.get("client", client_name_guess)
                    times = config.get("times", [])
                    days = config.get("days", [])
                    
                    # Skip the current client if specified
                    if exclude_client and client_name == exclude_client:
                        return
                        
                    for hour_str, minute_str, ampm in times:
                        try:
                            hour_12 = int(hour_str); minute = int(minute_str)
                            hour_24 = hour_12
                            if ampm == "PM" and hour_12 < 12: hour_24 += 12
                            elif ampm == "AM" and hour_12 == 12: hour_24 = 0
                            # 5-minute window
                            for day in days:
                                for offset in range(-2, 3):  # -2, -1, 0, 1, 2 minutes
                                    conflict_minute = minute + offset
                                    conflict_hour = hour_24
                                    
                                    # Handle minute overflow/underflow
                                    if conflict_minute >= 60:
                                        conflict_minute -= 60
                                        conflict_hour += 1
                                    elif conflict_minute < 0:
                                        conflict_minute += 60
                                        conflict_hour -= 1
                                        
                                    # Handle hour overflow/underflow
                                    if conflict_hour >= 24:
                                        conflict_hour = 0
                                    elif conflict_hour < 0:
                                        conflict_hour = 23
                                        
                                    scheduled_times.add((retailer, day, conflict_hour, conflict_minute))
                        except (ValueError, TypeError):
                            continue
                except Exception:
                    pass

            # New layout: output/<retailer>/<client>/schedule_config.json
            for rdir in os.listdir(output_path):
                rpath = os.path.join(output_path, rdir)
                if not os.path.isdir(rpath):
                    continue
                for cdir in os.listdir(rpath):
                    cpath = os.path.join(rpath, cdir)
                    if not os.path.isdir(cpath):
                        continue
                    sched = os.path.join(cpath, "schedule_config.json")
                    if os.path.exists(sched):
                        _process_schedule(sched, cdir)

            # Back-compat: old layout output/<client>/schedule_config.json
            for cdir in os.listdir(output_path):
                cpath = os.path.join(output_path, cdir)
                if os.path.isdir(cpath):
                    sched = os.path.join(cpath, "schedule_config.json")
                    if os.path.exists(sched):
                        _process_schedule(sched, cdir)
                
        return scheduled_times
    
    def is_time_conflicted(self, hour_24, minute, days, exclude_client=None):
        """Check if a specific time conflicts with existing schedules.
        
        Only checks within the SAME retailer since each retailer uses its own
        Chrome profile and can run independently.
        """
        scheduled_times = self.get_all_scheduled_times(exclude_client)
        
        # Get current retailer - conflicts only matter within same retailer
        retailer_slug = self._schedule_retailer_slug()
        
        for day in days:
            day_lower = day.lower()
            
            # Only check conflicts within the SAME retailer (same Chrome profile)
            for sched_retailer, sched_day, sched_hour, sched_minute in scheduled_times:
                if sched_retailer == retailer_slug and sched_day.lower() == day_lower and sched_hour == hour_24 and sched_minute == minute:
                    return True
        return False
    
    def find_next_available_time(self, preferred_hour, preferred_minute, preferred_ampm, days, exclude_client=None):
        """Find the next available time slot that doesn't conflict"""
        # Convert preferred time to 24-hour format
        hour_24 = preferred_hour
        if preferred_ampm == "PM" and preferred_hour < 12:
            hour_24 += 12
        elif preferred_ampm == "AM" and preferred_hour == 12:
            hour_24 = 0
            
        # Start checking from the preferred time
        current_hour = hour_24
        current_minute = preferred_minute
        
        # Check up to 24 hours ahead in 5-minute increments
        for _ in range(24 * 12):  # 24 hours * 12 five-minute periods per hour
            if not self.is_time_conflicted(current_hour, current_minute, days, exclude_client):
                # Convert back to 12-hour format
                if current_hour == 0:
                    return 12, current_minute, "AM"
                elif current_hour < 12:
                    return current_hour, current_minute, "AM"
                elif current_hour == 12:
                    return 12, current_minute, "PM"
                else:
                    return current_hour - 12, current_minute, "PM"
                    
            # Increment by 5 minutes
            current_minute += 5
            if current_minute >= 60:
                current_minute = 0
                current_hour += 1
                if current_hour >= 24:
                    current_hour = 0
                    
        # If no available time found, return the original
        return preferred_hour, preferred_minute, preferred_ampm
    
    def get_allowed_minutes_for_hour(self, hour_12: int, ampm: str, days, exclude_client=None):
        """Return a list of mm strings (00..55 step 5) that are free for ALL selected days for given hour."""
        # Convert to 24h
        hour_24 = hour_12
        if ampm == "PM" and hour_12 < 12:
            hour_24 += 12
        elif ampm == "AM" and hour_12 == 12:
            hour_24 = 0

        # Get current retailer - only check conflicts within same retailer
        retailer_slug = self._schedule_retailer_slug()
        scheduled = self.get_all_scheduled_times(exclude_client=exclude_client)
        
        allowed = []
        for m in range(0, 60, 5):
            # Only check conflicts within the SAME retailer (same Chrome profile)
            conflicted = False
            for day in days:
                day_lower = day.lower()
                for sched_retailer, sched_day, sched_hour, sched_minute in scheduled:
                    if sched_retailer == retailer_slug and sched_day.lower() == day_lower and sched_hour == hour_24 and sched_minute == m:
                        conflicted = True
                        break
                if conflicted:
                    break
            if not conflicted:
                allowed.append(f"{m:02d}")
        return allowed

    def schedule_has_conflicts(self):
        """Return True if any current time selector is conflicted for selected days."""
        selected_client = self.client_var.get()
        if not selected_client or selected_client == PLACEHOLDER:
            return True  # treat as not-saveable
        selected_days = [day for day, var in self.day_vars.items() if var.get()]
        if not selected_days:
            return True

        # Get current retailer - only check conflicts within same retailer
        retailer_slug = self._schedule_retailer_slug()
        scheduled = self.get_all_scheduled_times(exclude_client=selected_client)
        
        for hour_var, minute_var, ampm_var in self.time_vars:
            try:
                h = int(hour_var.get())
                m = int(minute_var.get())
                a = ampm_var.get()
                # 24h
                h24 = h
                if a == "PM" and h < 12: h24 += 12
                if a == "AM" and h == 12: h24 = 0
                
                # Only check conflicts within the SAME retailer (same Chrome profile)
                for day in selected_days:
                    day_lower = day.lower()
                    for sched_retailer, sched_day, sched_hour, sched_minute in scheduled:
                        if sched_retailer == retailer_slug and sched_day.lower() == day_lower and sched_hour == h24 and sched_minute == m:
                            return True
            except Exception:
                return True
        return False

    def refresh_save_button_state(self):
        """Enable Save only when selection is valid and non-conflicting."""
        try:
            if not hasattr(self, 'schedule_button'):
                return
                
            if self.schedule_has_conflicts():
                try:
                    self.schedule_button.state(['disabled'])
                except Exception:
                    # Fall back to config method if state doesn't work
                    self.schedule_button.config(state="disabled")
            else:
                try:
                    self.schedule_button.state(['!disabled'])
                except Exception:
                    # Fall back to config method if state doesn't work
                    self.schedule_button.config(state="normal")
        except Exception as e:
            print(f"Error in refresh_save_button_state: {e}")
            try:
                self.schedule_button.config(state="disabled")
            except Exception:
                pass
    
    # =========================================================================
    # SCREEN CAPTURE TAB
    # =========================================================================
    
    # Retailer department URLs for screen capture
    RETAILER_DEPARTMENTS = {
        "kroger": {
            "main": ("Homepage", "https://www.kroger.com/"),
            "departments": [
                ("Dairy & Eggs", "https://www.kroger.com/pl/dairy-eggs/06"),
                ("Frozen", "https://www.kroger.com/pl/frozen/04"),
                ("Beverages", "https://www.kroger.com/pl/beverages/02"),
                ("Snacks", "https://www.kroger.com/pl/snacks/07"),
                ("Pantry", "https://www.kroger.com/pl/pantry/03"),
                ("Meat & Seafood", "https://www.kroger.com/pl/meat-seafood/05"),
                ("Deli", "https://www.kroger.com/pl/deli/80"),
                ("Bakery", "https://www.kroger.com/pl/bakery/81"),
            ]
        },
        "walmart": {
            "main": ("Homepage", "https://www.walmart.com/"),
            "departments": [
                ("Grocery", "https://www.walmart.com/browse/food/976759"),
                ("Frozen Food", "https://www.walmart.com/browse/food/frozen-food/976759_976791"),
                ("Dairy & Eggs", "https://www.walmart.com/browse/food/dairy-eggs/976759_976782"),
                ("Beverages", "https://www.walmart.com/browse/food/beverages/976759_976780"),
                ("Snacks", "https://www.walmart.com/browse/food/snacks-cookies-chips/976759_976787"),
                ("Pantry", "https://www.walmart.com/browse/food/pantry/976759_976794"),
                ("Meat & Seafood", "https://www.walmart.com/browse/food/meat-seafood/976759_976785"),
            ]
        },
        "amazon": {
            "main": ("Homepage", "https://www.amazon.com/"),
            "departments": [
                ("Grocery & Gourmet", "https://www.amazon.com/grocery-gourmet-food/b?node=16310101"),
                ("Snack Foods", "https://www.amazon.com/Snack-Foods-Grocery/b?node=16322721"),
                ("Beverages", "https://www.amazon.com/Beverages/b?node=16318401"),
                ("Breakfast Foods", "https://www.amazon.com/Breakfast-Foods-Grocery/b?node=16310231"),
                ("Candy & Chocolate", "https://www.amazon.com/Candy-Chocolate-Grocery/b?node=16322461"),
            ]
        },
        "instacart": {
            "main": ("Homepage", "https://www.instacart.com/"),
            "departments": [
                ("Dairy & Eggs", "https://www.instacart.com/store/publix/collections/dairy-eggs"),
                ("Frozen", "https://www.instacart.com/store/publix/collections/frozen"),
                ("Beverages", "https://www.instacart.com/store/publix/collections/beverages"),
                ("Snacks & Candy", "https://www.instacart.com/store/publix/collections/snacks-candy"),
                ("Pantry", "https://www.instacart.com/store/publix/collections/pantry"),
            ]
        },
        "target": {
            "main": ("Homepage", "https://www.target.com/"),
            "departments": [
                ("Grocery", "https://www.target.com/c/grocery/-/N-5xt1a"),
                ("Frozen Foods", "https://www.target.com/c/frozen-foods-grocery/-/N-5xt0z"),
                ("Dairy", "https://www.target.com/c/dairy-grocery/-/N-5xt0y"),
                ("Beverages", "https://www.target.com/c/beverages-grocery/-/N-5xt0p"),
                ("Snacks", "https://www.target.com/c/snacks-grocery/-/N-5xt1d"),
            ]
        },
    }
    
    def _build_screen_capture_tab(self):
        """Build the Screen Capture tab with front page and department capture options."""
        # Create frame for Screen Capture tab
        screen_capture_frame = ttk.Frame(self.notebook, padding=10, style='App.TFrame')
        screen_capture_frame.rowconfigure(0, weight=1)
        screen_capture_frame.columnconfigure(0, weight=1)
        self.notebook.add(screen_capture_frame, text="  Screen Capture  ")
        
        # Create scrollable canvas for this tab
        sc_canvas = tk.Canvas(screen_capture_frame, highlightthickness=0)
        sc_scrollbar = ttk.Scrollbar(screen_capture_frame, orient="vertical", command=sc_canvas.yview)
        sc_canvas.configure(yscrollcommand=sc_scrollbar.set)
        
        sc_canvas.grid(row=0, column=0, sticky="nsew")
        sc_scrollbar.grid(row=0, column=1, sticky="ns")
        
        sc_scrollable = ttk.Frame(sc_canvas)
        self._sc_window = sc_canvas.create_window((0, 0), window=sc_scrollable, anchor="nw")
        
        def _on_sc_canvas_configure(e):
            sc_canvas.itemconfigure(self._sc_window, width=e.width)
        sc_canvas.bind("<Configure>", _on_sc_canvas_configure)
        
        def _on_sc_inner_configure(e):
            sc_canvas.configure(scrollregion=sc_canvas.bbox("all"))
        sc_scrollable.bind("<Configure>", _on_sc_inner_configure)
        
        # Store reference
        self.sc_canvas = sc_canvas
        self.sc_scrollable = sc_scrollable
        
        # Initialize capture state
        self.sc_retailer_vars = {}  # {retailer: {main: BooleanVar, depts: {name: BooleanVar}, custom_urls: []}}
        self.sc_custom_url_entries = {}  # {retailer: [Entry widgets]}
        self.sc_capture_status = {}  # {retailer: Label widget for status}
        
        # ===== Header =====
        header_frame = ttk.Frame(sc_scrollable, style='Card.TFrame')
        header_frame.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(
            header_frame, 
            text="Front Page & Department Screenshots",
            font=("Inter", 14, "bold"),
            style='TLabel'
        ).pack(anchor="w")
        
        ttk.Label(
            header_frame,
            text="Capture homepage and department pages for competitive intelligence",
            style='Body.TLabel'
        ).pack(anchor="w", pady=(5, 0))
        
        # ===== Output Path Display =====
        output_frame = ttk.Frame(sc_scrollable, style='Card.TFrame')
        output_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(output_frame, text="Output:", style='TLabel').pack(side=tk.LEFT)
        
        output_root = self._get_screen_capture_output_root()
        self.sc_output_label = ttk.Label(
            output_frame, 
            text=str(output_root),
            style='Body.TLabel'
        )
        self.sc_output_label.pack(side=tk.LEFT, padx=(10, 0))
        
        ttk.Button(
            output_frame,
            text="📂 Open",
            command=self._open_screen_capture_folder,
            width=8
        ).pack(side=tk.RIGHT)
        
        # ===== Retailer Sections =====
        for retailer in ["kroger", "walmart", "amazon", "instacart", "target"]:
            self._build_retailer_capture_section(sc_scrollable, retailer)
        
        # ===== Global Controls =====
        controls_frame = ttk.Frame(sc_scrollable, style='Card.TFrame')
        controls_frame.pack(fill=tk.X, pady=(15, 10))
        
        ttk.Button(
            controls_frame,
            text="📸 Capture Selected",
            command=self._run_screen_captures,
            style='Primary.TButton'
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(
            controls_frame,
            text="Select All Main Pages",
            command=self._select_all_main_pages,
            style='Secondary.TButton'
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(
            controls_frame,
            text="Clear All",
            command=self._clear_all_captures,
            style='Danger.TButton'
        ).pack(side=tk.LEFT)
        
        # ===== Schedule Settings =====
        self._build_frontpage_schedule_section(sc_scrollable)
        
        # ===== Capture Log =====
        log_frame = ttk.LabelFrame(sc_scrollable, text="Capture Log", style='Card.TLabelframe', padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        
        self.sc_log = scrolledtext.ScrolledText(log_frame, height=10, wrap="word")
        self.sc_log.pack(fill=tk.BOTH, expand=True)
        self.sc_log.configure(font=("Inter", 10), state="disabled")
    
    def _build_frontpage_schedule_section(self, parent):
        """Build the scheduling section for front page captures."""
        schedule_frame = ttk.LabelFrame(parent, text="Scheduled Captures", style='Card.TLabelframe', padding=10)
        schedule_frame.pack(fill=tk.X, pady=(15, 0))
        
        # Load existing config
        config = self._load_frontpage_schedule()
        
        # Enable/disable toggle
        enable_frame = ttk.Frame(schedule_frame, style='Card.TFrame')
        enable_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.sc_schedule_enabled = tk.BooleanVar(value=config.get("enabled", True))
        ttk.Checkbutton(
            enable_frame,
            text="Enable scheduled front page captures",
            variable=self.sc_schedule_enabled,
            command=self._on_frontpage_schedule_changed
        ).pack(side=tk.LEFT)
        
        # Times frame
        times_outer = ttk.Frame(schedule_frame, style='Card.TFrame')
        times_outer.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(times_outer, text="Capture times:", style='TLabel').pack(side=tk.LEFT)
        
        # Time entries (up to 3)
        self.sc_time_vars = []
        times = config.get("times", ["08:00"])
        for i in range(3):
            var = tk.StringVar(value=times[i] if i < len(times) else "")
            self.sc_time_vars.append(var)
            entry = ttk.Entry(times_outer, textvariable=var, width=6)
            entry.pack(side=tk.LEFT, padx=(10, 0))
            # Bind to detect changes
            var.trace_add('write', lambda *args: self._on_frontpage_schedule_changed())
        
        ttk.Label(times_outer, text="(24h format, e.g. 08:00, 14:30)", style='Body.TLabel').pack(side=tk.LEFT, padx=(10, 0))
        
        # Days of week
        days_frame = ttk.LabelFrame(schedule_frame, text="Days to Run", padding=5, style='Card.TLabelframe')
        days_frame.pack(fill=tk.X, pady=(0, 10))
        
        day_boxes = ttk.Frame(days_frame, style='Card.TFrame')
        day_boxes.pack(fill=tk.X, pady=5)
        
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        config_days = set(d.lower() for d in config.get("days", day_names))
        
        self.sc_day_vars = {}
        for i, day in enumerate(day_names):
            var = tk.BooleanVar(value=day.lower() in config_days)
            self.sc_day_vars[day] = var
            cb = ttk.Checkbutton(day_boxes, text=day[:3], variable=var, command=self._on_frontpage_schedule_changed)
            cb.grid(row=0, column=i, padx=5)
        
        # Retailer selection for scheduled captures
        retailers_frame = ttk.LabelFrame(schedule_frame, text="Retailers to Capture", padding=5, style='Card.TLabelframe')
        retailers_frame.pack(fill=tk.X, pady=(0, 10))
        
        retailer_boxes = ttk.Frame(retailers_frame, style='Card.TFrame')
        retailer_boxes.pack(fill=tk.X, pady=5)
        
        all_retailers = ["kroger", "walmart", "amazon", "instacart", "target"]
        config_retailers = set(config.get("retailers", all_retailers))
        
        self.sc_sched_retailer_vars = {}
        for i, retailer in enumerate(all_retailers):
            var = tk.BooleanVar(value=retailer in config_retailers)
            self.sc_sched_retailer_vars[retailer] = var
            cb = ttk.Checkbutton(retailer_boxes, text=retailer.title(), variable=var, command=self._on_frontpage_schedule_changed)
            cb.grid(row=0, column=i, padx=8)
        
        # Save button
        buttons_frame = ttk.Frame(schedule_frame, style='Card.TFrame')
        buttons_frame.pack(fill=tk.X)
        
        self.sc_schedule_save_btn = ttk.Button(
            buttons_frame,
            text="Save Schedule",
            command=self._save_frontpage_schedule,
            style='Primary.TButton'
        )
        self.sc_schedule_save_btn.pack(side=tk.LEFT, padx=(0, 10))
        self.sc_schedule_save_btn.state(['disabled'])
        
        # Status label
        self.sc_schedule_status = ttk.Label(buttons_frame, text="", style='Body.TLabel')
        self.sc_schedule_status.pack(side=tk.LEFT)
        
        # Show current schedule status
        self._update_frontpage_schedule_status()
    
    def _load_frontpage_schedule(self):
        """Load the front page capture schedule config."""
        config_path = os.path.join(get_base_dir(), "schedules", "frontpage_capture.json")
        default = {
            "enabled": True,
            "days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
            "times": ["08:00"],
            "retailers": ["kroger", "walmart", "target", "amazon", "instacart"]
        }
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                for k, v in default.items():
                    config.setdefault(k, v)
                return config
            except Exception:
                pass
        return default
    
    def _on_frontpage_schedule_changed(self, *args):
        """Called when any schedule setting changes - enable save button."""
        if hasattr(self, 'sc_schedule_save_btn'):
            self.sc_schedule_save_btn.state(['!disabled'])
    
    def _save_frontpage_schedule(self):
        """Save the front page capture schedule to JSON."""
        # Gather values
        times = [v.get().strip() for v in self.sc_time_vars if v.get().strip()]
        # Validate time format
        valid_times = []
        for t in times:
            if len(t) >= 4 and ':' in t:
                try:
                    h, m = t.split(':')
                    h, m = int(h), int(m)
                    if 0 <= h <= 23 and 0 <= m <= 59:
                        valid_times.append(f"{h:02d}:{m:02d}")
                except ValueError:
                    pass
        
        if not valid_times:
            valid_times = ["08:00"]  # Default
        
        days = [day.lower() for day, var in self.sc_day_vars.items() if var.get()]
        retailers = [r for r, var in self.sc_sched_retailer_vars.items() if var.get()]
        
        config = {
            "enabled": self.sc_schedule_enabled.get(),
            "days": days,
            "times": valid_times,
            "retailers": retailers,
            "description": "Daily front page screenshot capture"
        }
        
        # Save to file
        config_path = os.path.join(get_base_dir(), "schedules", "frontpage_capture.json")
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
            
            self.sc_schedule_save_btn.state(['disabled'])
            self._update_frontpage_schedule_status()
            self._sc_log(f"Schedule saved: {', '.join(valid_times)} on {len(days)} days for {len(retailers)} retailers")
        except Exception as e:
            self._sc_log(f"Failed to save schedule: {e}")
    
    def _update_frontpage_schedule_status(self):
        """Update the schedule status label."""
        config = self._load_frontpage_schedule()
        if config.get("enabled"):
            times = config.get("times", [])
            days = config.get("days", [])
            retailers = config.get("retailers", [])
            status = f"✓ Active: {', '.join(times)} on {len(days)} days ({len(retailers)} retailers)"
        else:
            status = "○ Disabled"
        
        if hasattr(self, 'sc_schedule_status'):
            self.sc_schedule_status.configure(text=status)
    
    def _build_retailer_capture_section(self, parent, retailer: str):
        """Build a collapsible section for a single retailer's capture options."""
        dept_config = self.RETAILER_DEPARTMENTS.get(retailer, {})
        main_name, main_url = dept_config.get("main", ("Homepage", f"https://www.{retailer}.com/"))
        departments = dept_config.get("departments", [])
        
        # Initialize state for this retailer
        self.sc_retailer_vars[retailer] = {
            "main": tk.BooleanVar(value=True),  # Main page enabled by default
            "depts": {},
            "custom_urls": [],
        }
        self.sc_custom_url_entries[retailer] = []
        
        # Retailer frame
        retailer_frame = ttk.LabelFrame(
            parent, 
            text=f"  {retailer.title()}  ",
            style='Card.TLabelframe',
            padding=10
        )
        retailer_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Main page row
        main_row = ttk.Frame(retailer_frame, style='Card.TFrame')
        main_row.pack(fill=tk.X, pady=(0, 8))
        
        ttk.Checkbutton(
            main_row,
            text=f"📍 {main_name}",
            variable=self.sc_retailer_vars[retailer]["main"]
        ).pack(side=tk.LEFT)
        
        ttk.Label(
            main_row,
            text=main_url,
            style='Body.TLabel',
            foreground='gray'
        ).pack(side=tk.LEFT, padx=(10, 0))
        
        # Status label for this retailer
        self.sc_capture_status[retailer] = ttk.Label(
            main_row,
            text="",
            style='Body.TLabel'
        )
        self.sc_capture_status[retailer].pack(side=tk.RIGHT)
        
        # Departments section
        if departments:
            dept_label = ttk.Label(
                retailer_frame,
                text="Departments:",
                style='TLabel',
                font=("Inter", 10, "bold")
            )
            dept_label.pack(anchor="w", pady=(5, 5))
            
            # Grid of department checkboxes (2 columns)
            dept_grid = ttk.Frame(retailer_frame, style='Card.TFrame')
            dept_grid.pack(fill=tk.X, padx=(20, 0))
            
            for i, (dept_name, dept_url) in enumerate(departments):
                var = tk.BooleanVar(value=False)
                self.sc_retailer_vars[retailer]["depts"][dept_name] = (var, dept_url)
                
                row = i // 2
                col = i % 2
                
                cb = ttk.Checkbutton(
                    dept_grid,
                    text=dept_name,
                    variable=var
                )
                cb.grid(row=row, column=col, sticky="w", padx=(0, 30), pady=2)
        
        # Custom URL section
        custom_frame = ttk.Frame(retailer_frame, style='Card.TFrame')
        custom_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Label(
            custom_frame,
            text="Custom URLs:",
            style='TLabel',
            font=("Inter", 10, "bold")
        ).pack(anchor="w")
        
        # Container for custom URL entries
        self.sc_custom_url_containers = getattr(self, 'sc_custom_url_containers', {})
        url_container = ttk.Frame(custom_frame, style='Card.TFrame')
        url_container.pack(fill=tk.X, padx=(20, 0), pady=(5, 0))
        self.sc_custom_url_containers[retailer] = url_container
        
        # Add URL button
        ttk.Button(
            custom_frame,
            text="+ Add URL",
            command=lambda r=retailer: self._add_custom_url_entry(r),
            width=12
        ).pack(anchor="w", padx=(20, 0), pady=(5, 0))
    
    def _add_custom_url_entry(self, retailer: str):
        """Add a new custom URL entry field for a retailer."""
        container = self.sc_custom_url_containers.get(retailer)
        if not container:
            return
        
        row_frame = ttk.Frame(container, style='Card.TFrame')
        row_frame.pack(fill=tk.X, pady=(2, 0))
        
        # Name entry
        name_var = tk.StringVar(value="")
        name_entry = ttk.Entry(row_frame, textvariable=name_var, width=20)
        name_entry.pack(side=tk.LEFT, padx=(0, 5))
        name_entry.insert(0, "Page Name")
        name_entry.bind("<FocusIn>", lambda e: name_entry.delete(0, tk.END) if name_entry.get() == "Page Name" else None)
        
        # URL entry
        url_var = tk.StringVar(value="")
        url_entry = ttk.Entry(row_frame, textvariable=url_var, width=50)
        url_entry.pack(side=tk.LEFT, padx=(0, 5))
        url_entry.insert(0, "https://")
        
        # Enabled checkbox
        enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row_frame, variable=enabled_var).pack(side=tk.LEFT, padx=(0, 5))
        
        # Remove button
        def remove_entry():
            row_frame.destroy()
            # Remove from tracking list
            for i, entry in enumerate(self.sc_custom_url_entries[retailer]):
                if entry.get("frame") == row_frame:
                    self.sc_custom_url_entries[retailer].pop(i)
                    break
        
        ttk.Button(
            row_frame,
            text="✕",
            command=remove_entry,
            width=3
        ).pack(side=tk.LEFT)
        
        # Track this entry
        self.sc_custom_url_entries[retailer].append({
            "frame": row_frame,
            "name_var": name_var,
            "url_var": url_var,
            "enabled_var": enabled_var,
        })
    
    def _get_screen_capture_output_root(self):
        """Get the output root for screen captures."""
        from pathlib import Path
        
        if os.getenv("FRONT_PAGE_OUTPUT_ROOT"):
            return Path(os.getenv("FRONT_PAGE_OUTPUT_ROOT"))
        
        base = get_base_dir()
        return Path(base) / "output" / "screen_capture"
    
    def _resolve_capture_profile(self, retailer: str) -> str | None:
        """
        Resolve profile directory for screen capture - uses same logic as 
        screenshot_front_page.py and retailer adapters for consistency.
        
        Priority:
        1. {RETAILER}_PROFILE_DIR env var
        2. SCRAPER_HOME/profiles/{retailer}
        3. ~/ChromeProfiles/{retailer}_clean_profile (main scraper pattern)
        4. ~/ChromeProfiles/{retailer}
        5. Project root profiles/{retailer}
        6. None (incognito mode)
        """
        from pathlib import Path
        
        # Priority 1: Retailer-specific env var (same as adapters use)
        env_var = f"{retailer.upper()}_PROFILE_DIR"
        env_path = os.getenv(env_var)
        if env_path and os.path.isdir(env_path):
            return env_path
        
        # Priority 2: SCRAPER_HOME/profiles/<retailer>
        scraper_home = os.getenv("SCRAPER_HOME")
        if scraper_home:
            profile_path = Path(scraper_home) / "profiles" / retailer
            if profile_path.is_dir():
                return str(profile_path)
        
        # Priority 3: ~/ChromeProfiles/<retailer>_clean_profile (matches main scraper)
        chrome_profiles = Path.home() / "ChromeProfiles"
        if chrome_profiles.is_dir():
            # Try retailer_clean_profile first (Kroger pattern)
            clean_profile = chrome_profiles / f"{retailer}_clean_profile"
            if clean_profile.is_dir():
                return str(clean_profile)
            # Try just retailer name
            retailer_profile = chrome_profiles / retailer
            if retailer_profile.is_dir():
                return str(retailer_profile)
        
        # Priority 4: Project root profiles/<retailer>
        base = get_base_dir()
        profile_path = Path(base) / "profiles" / retailer
        if profile_path.is_dir():
            return str(profile_path)
        
        # No profile found - will use incognito mode
        return None
    
    def _open_screen_capture_folder(self):
        """Open the screen capture output folder in Finder."""
        output_root = self._get_screen_capture_output_root()
        output_root.mkdir(parents=True, exist_ok=True)
        
        if sys.platform == "darwin":
            subprocess.run(["open", str(output_root)])
        elif sys.platform == "win32":
            subprocess.run(["explorer", str(output_root)])
        else:
            subprocess.run(["xdg-open", str(output_root)])
    
    def _select_all_main_pages(self):
        """Select all main page checkboxes."""
        for retailer in self.sc_retailer_vars:
            self.sc_retailer_vars[retailer]["main"].set(True)
    
    def _clear_all_captures(self):
        """Clear all capture selections."""
        for retailer in self.sc_retailer_vars:
            self.sc_retailer_vars[retailer]["main"].set(False)
            for dept_name, (var, url) in self.sc_retailer_vars[retailer]["depts"].items():
                var.set(False)
    
    def _sc_log_message(self, msg: str):
        """Write a message to the screen capture log."""
        try:
            self.sc_log.configure(state="normal")
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.sc_log.insert("end", f"[{timestamp}] {msg}\n")
            self.sc_log.see("end")
        finally:
            self.sc_log.configure(state="disabled")
    
    def _run_screen_captures(self):
        """Run screen captures for all selected pages."""
        # Collect all URLs to capture
        captures = []  # List of (retailer, name, url)
        
        for retailer, config in self.sc_retailer_vars.items():
            dept_config = self.RETAILER_DEPARTMENTS.get(retailer, {})
            
            # Main page
            if config["main"].get():
                main_name, main_url = dept_config.get("main", ("Homepage", f"https://www.{retailer}.com/"))
                captures.append((retailer, main_name, main_url))
            
            # Departments
            for dept_name, (var, dept_url) in config["depts"].items():
                if var.get():
                    captures.append((retailer, dept_name, dept_url))
            
            # Custom URLs
            for entry in self.sc_custom_url_entries.get(retailer, []):
                if entry["enabled_var"].get():
                    name = entry["name_var"].get().strip()
                    url = entry["url_var"].get().strip()
                    if url and url != "https://":
                        if not name or name == "Page Name":
                            name = "Custom"
                        captures.append((retailer, name, url))
        
        if not captures:
            self._sc_log_message("⚠️ No pages selected for capture")
            return
        
        self._sc_log_message(f"Starting capture of {len(captures)} page(s)...")
        
        # Run captures in background thread
        def run_captures():
            from pathlib import Path
            
            output_root = self._get_screen_capture_output_root()
            success_count = 0
            
            for i, (retailer, name, url) in enumerate(captures, 1):
                # Update status
                self.root.after(0, lambda r=retailer: self.sc_capture_status[r].config(text="⏳ Capturing..."))
                
                # Log profile being used
                profile = self._resolve_capture_profile(retailer)
                profile_msg = f"profile: {os.path.basename(profile)}" if profile else "incognito"
                self.root.after(0, lambda msg=f"[{i}/{len(captures)}] {retailer}: {name} ({profile_msg})...": self._sc_log_message(msg))
                
                try:
                    result = self._capture_single_page(retailer, name, url, output_root)
                    
                    if result["success"]:
                        success_count += 1
                        self.root.after(0, lambda r=retailer: self.sc_capture_status[r].config(text="✅"))
                        self.root.after(0, lambda msg=f"  ✓ Saved: {result['path']}": self._sc_log_message(msg))
                    else:
                        self.root.after(0, lambda r=retailer: self.sc_capture_status[r].config(text="❌"))
                        self.root.after(0, lambda msg=f"  ✗ Failed: {result['error']}": self._sc_log_message(msg))
                
                except Exception as e:
                    self.root.after(0, lambda r=retailer: self.sc_capture_status[r].config(text="❌"))
                    self.root.after(0, lambda msg=f"  ✗ Error: {e}": self._sc_log_message(msg))
            
            # Final summary
            self.root.after(0, lambda: self._sc_log_message(f"\n{'='*40}"))
            self.root.after(0, lambda: self._sc_log_message(f"Completed: {success_count}/{len(captures)} successful"))
            self.root.after(0, lambda: self._sc_log_message(f"{'='*40}\n"))
        
        # Start in background thread
        thread = threading.Thread(target=run_captures, daemon=True)
        thread.start()
    
    def _capture_single_page(self, retailer: str, page_name: str, url: str, output_root) -> dict:
        """Capture a single page screenshot."""
        from pathlib import Path
        import base64
        
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
        except ImportError:
            return {"success": False, "path": None, "error": "Playwright not installed"}
        
        # Generate output path
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M.%S")
        safe_name = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in page_name.lower())
        filename = f"{retailer}__{safe_name}__D{timestamp}.png"
        
        # Determine subfolder based on page type
        if page_name.lower() in ["homepage", "main", "front page"]:
            subfolder = "front_pages"
        else:
            subfolder = "departments"
        
        output_path = Path(output_root) / retailer / subfolder / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Get profile directory (same resolution as screenshot_front_page.py and adapters)
        profile_dir = self._resolve_capture_profile(retailer)
        
        # Retry logic for profile lock conflicts
        max_retries = 6  # Wait up to 60 seconds (6 x 10s)
        retry_delay = 10
        
        for attempt in range(max_retries):
            try:
                return self._do_capture(
                    retailer, url, page_name, output_path, profile_dir
                )
            except Exception as e:
                error_msg = str(e).lower()
                # Check if it's a profile lock error
                if 'processsingleton' in error_msg or 'already in use' in error_msg or 'singletonlock' in error_msg:
                    if attempt < max_retries - 1:
                        print(f"  [{retailer}] Profile in use, waiting {retry_delay}s... (attempt {attempt + 1}/{max_retries})")
                        import time
                        time.sleep(retry_delay)
                        continue
                    else:
                        return {"success": False, "path": None, "error": f"Profile busy after {max_retries} attempts: {e}"}
                # Not a lock error
                return {"success": False, "path": None, "error": str(e)}
        
        return {"success": False, "path": None, "error": "Unexpected error in retry loop"}
    
    def _do_capture(self, retailer: str, url: str, page_name: str, output_path, profile_dir: str):
        """Actually perform the capture - separated for retry logic."""
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            # Launch browser
            if profile_dir and os.path.isdir(profile_dir):
                context = p.chromium.launch_persistent_context(
                    user_data_dir=profile_dir,
                    headless=False,
                    viewport={"width": 1920, "height": 1080},
                    device_scale_factor=1.0,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        # Focus prevention - don't steal focus from user's active window
                        "--no-startup-window",
                        "--silent-launch",
                        "--disable-focus-on-load",
                        "--noerrdialogs",
                    ]
                )
                page = context.pages[0] if context.pages else context.new_page()
                browser = None
            else:
                browser = p.chromium.launch(
                    headless=False,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        # Focus prevention - don't steal focus from user's active window
                        "--no-startup-window",
                        "--silent-launch",
                        "--disable-focus-on-load",
                        "--noerrdialogs",
                    ]
                )
                context = browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    device_scale_factor=1.0,
                )
                page = context.new_page()
            
            try:
                # Navigate
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except:
                    pass  # Continue even if networkidle times out
                
                page.wait_for_timeout(2000)
                
                # Retailer-specific handling
                if retailer == "kroger":
                    # Close Kroger popups (store selector, newsletter, terms, etc.)
                    popup_selectors = [
                        'button.kds-Modal-closeButton',  # Kroger's modal close button class
                        'button[aria-label="Close pop-up"]',  # Terms modal
                        'button[aria-label="Close"]',
                        'button[aria-label="close"]',
                        '[data-testid="ModalCloseButton"]',
                        '[data-testid="modal-close-button"]',
                        '.kds-DismissalButton',  # Kroger dismissal button
                        '.ReactModal__Content button[aria-label*="lose"]',
                        '[role="dialog"] button[aria-label*="lose"]',
                        '[role="dialog"] button[aria-label*="pop-up"]',
                    ]
                    for selector in popup_selectors:
                        try:
                            popup_btn = page.locator(selector).first
                            if popup_btn.is_visible(timeout=500):
                                popup_btn.click()
                                print(f"[{retailer}] Closed popup: {selector}")
                                page.wait_for_timeout(500)
                        except:
                            pass
                    
                    # Hide any remaining modals via JS (removes from DOM rendering)
                    page.evaluate("""
                        () => {
                            // Hide modal overlays
                            document.querySelectorAll('.ReactModalPortal, .kds-Modal-overlay, [role="dialog"], [class*="Modal"], [class*="Overlay"]')
                                .forEach(el => el.remove());
                        }
                    """)
                    page.wait_for_timeout(300)
                
                elif retailer == "target":
                    # Target needs extra time for hydration
                    hydration_selectors = [
                        '[data-test="@web/Homepage"]',
                        '[data-test="carousel"]',
                        '[data-test="product-card"]',
                        '[class*="ProductCard"]',
                    ]
                    for selector in hydration_selectors:
                        try:
                            page.wait_for_selector(selector, timeout=5000)
                            break
                        except:
                            pass
                    
                    # Extra scroll to trigger lazy loading
                    page.evaluate("window.scrollTo(0, 500)")
                    page.wait_for_timeout(1000)
                    page.evaluate("window.scrollTo(0, 1500)")
                    page.wait_for_timeout(1000)
                    page.evaluate("window.scrollTo(0, 0)")
                    page.wait_for_timeout(1500)
                
                # Disable animations
                page.add_style_tag(content="""
                    * { animation: none !important; transition: none !important; }
                    html { scroll-behavior: auto !important; }
                """)
                
                # Neutralize ALL sticky/fixed elements before scrolling
                page.evaluate("""
                    () => {
                        document.querySelectorAll('*').forEach(el => {
                            const style = window.getComputedStyle(el);
                            if (style.position === 'sticky' || style.position === 'fixed') {
                                el.style.setProperty('position', 'relative', 'important');
                            }
                        });
                    }
                """)
                
                # Warm up lazy content (multiple passes for Target)
                try:
                    vh = page.evaluate("() => window.innerHeight")
                    doc_h = page.evaluate("() => document.body.scrollHeight")
                    step = int(vh * 0.7)
                    
                    # First pass: scroll down slowly to trigger lazy loading
                    y = 0
                    while y < doc_h - vh:
                        page.evaluate(f"window.scrollTo(0, {y})")
                        page.wait_for_timeout(300)
                        y += step
                        doc_h = page.evaluate("() => document.body.scrollHeight")
                    
                    # Scroll to absolute bottom
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(500)
                    
                    # Target, Walmart, Instacart: second pass with longer waits for full hydration
                    if retailer in ('target', 'walmart', 'instacart'):
                        print(f"  [{retailer}] Running second scroll pass for full hydration...")
                        page.evaluate("window.scrollTo(0, 0)")
                        page.wait_for_timeout(300)
                        # Re-check doc height after first pass
                        doc_h = page.evaluate("() => document.body.scrollHeight")
                        y = 0
                        while y < doc_h - vh:
                            page.evaluate(f"window.scrollTo(0, {y})")
                            page.wait_for_timeout(400)
                            y += step
                        # Final scroll to bottom and wait
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        page.wait_for_timeout(500)
                    
                    page.evaluate("window.scrollTo(0, 0)")
                    page.wait_for_timeout(800)
                except:
                    pass
                
                # Capture screenshot using CDP (consistent viewport width for all retailers)
                client = context.new_cdp_session(page)
                
                # For Target/Instacart: extra step to ensure sticky elements are fully neutralized
                if retailer in ('target', 'instacart'):
                    print(f"  [{retailer}] Ensuring consistent viewport for capture...")
                    page.evaluate("""
                        () => {
                            // Remove all sticky/fixed positioning
                            const allElements = document.querySelectorAll('*');
                            allElements.forEach(el => {
                                const style = window.getComputedStyle(el);
                                if (style.position === 'sticky' || style.position === 'fixed') {
                                    el.style.setProperty('position', 'relative', 'important');
                                }
                            });
                            // Also hide any overlay/modal elements that might interfere
                            document.querySelectorAll('[class*="overlay"], [class*="Overlay"], [class*="modal"], [class*="Modal"]').forEach(el => {
                                el.style.setProperty('display', 'none', 'important');
                            });
                        }
                    """)
                    page.wait_for_timeout(300)
                
                shot = client.send("Page.captureScreenshot", {
                    "format": "png",
                    "fromSurface": True,
                    "captureBeyondViewport": True
                })
                data = base64.b64decode(shot["data"])
                output_path.write_bytes(data)
                
                # Save HTML
                html_path = output_path.with_suffix('.html')
                try:
                    html_content = page.content()
                    html_path.write_text(html_content, encoding='utf-8')
                except Exception as e:
                    print(f"[warn] Failed to save HTML: {e}")
                    html_path = None
                
                # Save readable text
                text_path = output_path.with_suffix('.txt')
                try:
                    from scripts.screenshot_front_page import extract_readable_text
                    title = page.title() or "Unknown"
                    page_url = page.url
                    timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    header = f"""{'='*70}
FRONT PAGE TEXT CAPTURE
{'='*70}
Title: {title}
URL: {page_url}
Retailer: {retailer}
Captured: {timestamp_str}
{'='*70}

"""
                    text_content = extract_readable_text(page, retailer)
                    text_path.write_text(header + text_content, encoding='utf-8')
                except Exception as e:
                    print(f"[warn] Failed to save text: {e}")
                    text_path = None
                
                # Cleanup
                context.close()
                if browser:
                    browser.close()
                
                return {
                    "success": True,
                    "path": str(output_path),
                    "html_path": str(html_path) if html_path else None,
                    "text_path": str(text_path) if text_path else None,
                    "error": None
                }
            except Exception as e:
                context.close()
                if browser:
                    browser.close()
                raise
    
    def apply_theme(self, style: ttk.Style, mode="light"):
        """Apply theme styling to all widgets"""
        c = PALETTE[mode]
        
        # Print available themes for debugging
        print(f"Available themes: {style.theme_names()}")
        print(f"Current theme: {style.theme_use()}")
        
        # Base frames/labels
        style.configure('App.TFrame', background=c["bg"])
        style.configure('Card.TFrame', background=c["card"])
        style.configure('Card.TLabelframe', background=c["card"], relief='solid', borderwidth=1)
        style.configure('Card.TLabelframe.Label', background=c["card"], foreground=c["muted"], font=("Inter", 10, "bold"))
        style.configure('Body.TLabel', background=c["bg"], foreground=c["muted"])
        style.configure('TLabel', background=c["card"], foreground=c["muted"])
        
        # Apply styles to standard widgets too
        style.configure('TFrame', background=c["bg"])
        style.configure('TLabelframe', background=c["card"], bordercolor=c["border"])
        style.configure('TLabelframe.Label', foreground=c["text"])

        # Combobox (readable text + field bg)
        style.configure('App.TCombobox',
            fieldbackground=c["field_bg"], foreground=c["field_fg"], background=c["field_bg"])
        style.map('App.TCombobox',
            fieldbackground=[('readonly', c["field_bg"])],
            foreground=[('readonly', c["field_fg"])])

        # Buttons - enhanced for macOS visibility
        # Standard button style override
        style.configure('TButton', 
            background=c["secondary"], foreground='white',
            padding=(10, 6), font=("Inter", 11), borderwidth=1)
        style.map('TButton',
            background=[('active', c["secondary_h"]), ('disabled', '#9aa5b1')],
            foreground=[('disabled', '#ffffff')])
            
        # Primary button (blue)
        style.configure('Primary.TButton',
            background=c["primary"], foreground='white',
            padding=(14, 8), font=("Inter", 11, "bold"), borderwidth=1,
            relief="raised")
        style.map('Primary.TButton',
            background=[('active', c["primary_h"]), ('pressed', c["primary_h"]), ('disabled', '#9aa5b1')],
            foreground=[('disabled', '#ffffff')],
            relief=[('pressed', 'sunken'), ('active', 'raised')])

        # Secondary button (gray)
        style.configure('Secondary.TButton',
            background=c["secondary"], foreground='white',
            padding=(14, 8), font=("Inter", 11, "bold"), borderwidth=1,
            relief="raised")
        style.map('Secondary.TButton',
            background=[('active', c["secondary_h"]), ('pressed', c["secondary_h"]), ('disabled', '#9aa5b1')],
            foreground=[('disabled', '#ffffff')],
            relief=[('pressed', 'sunken'), ('active', 'raised')])

        # Danger button (red)
        style.configure('Danger.TButton',
            background=c["danger"], foreground='white',
            padding=(14, 8), font=("Inter", 11, "bold"), borderwidth=1,
            relief="raised")
        style.map('Danger.TButton',
            background=[('active', c["danger_h"]), ('pressed', c["danger_h"]), ('disabled', '#fca5a5')],
            foreground=[('disabled', '#ffffff')],
            relief=[('pressed', 'sunken'), ('active', 'raised')])

        # Progressbar
        style.configure('blue.Horizontal.TProgressbar',
            troughcolor=c["trough"], background=c["bar"], bordercolor=c["trough"], lightcolor=c["bar"], darkcolor=c["bar"])

        # Notebook (tabs) - selected tab is larger/more prominent
        style.configure('TNotebook', background=c["bg"], borderwidth=0)
        style.configure('TNotebook.Tab', 
            background=c["border"], foreground=c["muted"],
            padding=(12, 6), font=("Inter", 10))
        style.map('TNotebook.Tab',
            background=[('selected', c["primary"]), ('active', c["card"])],
            foreground=[('selected', 'white'), ('active', c["text"])],
            padding=[('selected', (18, 10))],  # Larger padding when selected
            font=[('selected', ("Inter", 12, "bold"))])

        # Global bg for root window (non-ttk)
        try:
            self.root.configure(bg=c["bg"])
        except Exception:
            pass
    
    def setup_signal_handler(self):
        """Set up signal handler for dock icon clicks"""
        import signal
        signal.signal(signal.SIGUSR1, self.signal_restore_window)
    
    def signal_restore_window(self, signum, frame):
        """Restore window when signal is received"""
        self.root.after(0, self.restore_window)
    
    def restore_window(self):
        """Restore window when dock icon is clicked"""
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
    
    def check_daemon_status(self):
        """Check if scheduler daemon is currently running"""
        try:
            base = get_base_dir()
            retailer = os.getenv("RETAILER", "").strip()
            
            # Check both central and retailer-specific PID locations
            candidates = [os.path.join(base, "logs", "scheduler.pid")]
            if retailer:
                candidates.append(os.path.join(base, "logs", retailer, "scheduler.pid"))
            
            for pid_path in candidates:
                if os.path.exists(pid_path):
                    with open(pid_path, "r") as pf:
                        pid = pf.read().strip()
                    if pid.isdigit():
                        # macOS doesn't have /proc — do both checks safely
                        if os.path.exists(f"/proc/{pid}") or self._ps_contains_pid(pid):
                            return True

            # Fallback: name-based scan (brittle but better than nothing)
            return self._ps_contains_name("scheduler_daemon.py")
        except Exception as e:
            print(f"Error checking daemon status: {e}")
            return False

    def _ps_contains_pid(self, pid: str) -> bool:
        try:
            result = subprocess.run(["ps", "-p", str(pid), "-o", "pid="],
                                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5)
            return str(pid) in (result.stdout or "").strip()
        except Exception:
            return False

    def _ps_contains_name(self, name: str) -> bool:
        try:
            result = subprocess.run(["ps", "aux"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
            for line in (result.stdout or "").splitlines():
                if name in line and "grep" not in line:
                    return True
            return False
        except Exception:
            return False
    
    def refresh_daemon_status(self):
        """Periodically refresh daemon status and update UI"""
        try:
            # Check current daemon status
            new_status = self.check_daemon_status()
            
            # Update if status changed
            if new_status != self.daemon_status:
                self.daemon_status = new_status
                if hasattr(self, 'status_label'):
                    daemon_text = "✅ Daemon running" if self.daemon_status else "⚠️ Daemon stopped"
                    self.status_label.config(text=f"Ready to scrape | {daemon_text}")
        except Exception as e:
            print(f"Error refreshing daemon status: {e}")
        
        # Schedule next refresh in 30 seconds
        self.root.after(30000, self.refresh_daemon_status)
    
    def refresh_daemon_status_manual(self):
        """Manually refresh daemon status (called by button)"""
        try:
            new_status = self.check_daemon_status()
            self.daemon_status = new_status
            daemon_text = "✅ Daemon running" if self.daemon_status else "⚠️ Daemon stopped"
            self.status_label.config(text=f"Ready to scrape | {daemon_text}")
            self.notify(f"Daemon status: {'Running' if new_status else 'Stopped'}", "info")
        except Exception as e:
            self.notify(f"Error checking daemon status: {e}", "error")
    
    def start_daemon_manual(self):
        """Manually start the daemon (called by button)"""
        if self.daemon_status:
            self.notify("Daemon is already running", "info")
            return
        
        try:
            base = get_base_dir()
            daemon_script = os.path.join(base, "start_scheduler.sh")
            lock_file = os.path.join(base, "logs", "scheduler.lock")
            
            if not os.path.exists(daemon_script):
                self.notify("start_scheduler.sh not found", "error")
                return
            
            # Check for stale lock file
            if os.path.exists(lock_file):
                # Verify daemon is actually NOT running
                if not self.check_daemon_status():
                    # Lock file is stale, remove it
                    try:
                        os.remove(lock_file)
                        self.notify("Removed stale lock file", "info")
                    except Exception as e:
                        self.notify(f"Could not remove lock file: {e}", "error")
                        return
                else:
                    self.notify("Daemon is already running", "info")
                    return
            
            # Set required environment variable for centralized scheduler
            env = os.environ.copy()
            env['CENTRAL_SCHEDULER'] = '1'
            env['SCRAPER_HOME'] = base
            
            # Start daemon in background (non-blocking)
            subprocess.Popen(
                [daemon_script], 
                cwd=base,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True  # Detach from parent process
            )
            
            # Wait a moment then check status
            self.root.after(2000, lambda: self.refresh_daemon_status_manual())
            self.notify("Starting daemon...", "info")
            
        except Exception as e:
            self.notify(f"Error starting daemon: {e}", "error")
    
    def stop_daemon_manual(self):
        """Manually stop the daemon AND all child scraper processes."""
        if not self.daemon_status:
            self.notify("Daemon is not running", "info")
            return
        
        try:
            # Collect PIDs for the full process tree:
            #   scheduler_entry.py, scheduler_daemon.py, and all scraper scripts
            scraper_scripts = [
                "scheduler_entry.py", "scheduler_daemon.py",
                "kroger_search_and_capture.py", "walmart_search_and_capture.py",
                "target_search_and_capture.py", "amazon_search_and_capture.py",
                "instacart_search_and_capture.py", "tiktokshop_search_and_capture.py",
                "screenshot_front_page.py",
            ]
            
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True, text=True, timeout=5
            )
            
            pids_to_kill = []
            for line in result.stdout.splitlines():
                if "grep" in line:
                    continue
                if any(s in line for s in scraper_scripts):
                    parts = line.split()
                    if len(parts) > 1 and parts[1].isdigit():
                        pids_to_kill.append(int(parts[1]))
            
            if not pids_to_kill:
                self.notify("Could not find daemon/scraper processes", "error")
                return
            
            # Phase 1: SIGTERM all
            for pid in pids_to_kill:
                try:
                    os.kill(pid, 15)  # SIGTERM
                except (ProcessLookupError, PermissionError):
                    pass
            
            self.notify(f"Stopping {len(pids_to_kill)} process(es)...", "info")
            
            # Phase 2: after 4 seconds, SIGKILL any survivors and clean up
            def _force_kill_and_cleanup():
                for pid in pids_to_kill:
                    try:
                        os.kill(pid, 9)  # SIGKILL
                    except (ProcessLookupError, PermissionError):
                        pass
                # Clean up stale lock/pid files
                base = get_base_dir()
                for f in ["logs/scheduler.lock", "logs/scheduler.pid"]:
                    path = os.path.join(base, f)
                    try:
                        if os.path.exists(path):
                            os.remove(path)
                    except Exception:
                        pass
                self.refresh_daemon_status_manual()
            
            self.root.after(4000, _force_kill_and_cleanup)
                
        except Exception as e:
            self.notify(f"Error stopping daemon: {e}", "error")
    
    def view_scheduler_logs(self):
        """Open scheduler logs in a new window"""
        try:
            base = get_base_dir()
            log_file = os.path.join(base, "logs", "scheduler_daemon.log")
            
            if not os.path.exists(log_file):
                self.notify("No scheduler logs found", "warn")
                return
            
            # Create new window
            log_window = tk.Toplevel(self.root)
            log_window.title("Scheduler Logs")
            log_window.geometry("900x600")
            
            # Add scrolled text widget
            log_text = scrolledtext.ScrolledText(log_window, wrap="word", font=("Monaco", 10))
            log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            # Load and display last 500 lines
            with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
                log_text.insert("1.0", ''.join(lines[-500:]))
            
            log_text.see("end")
            log_text.configure(state="disabled")
            
        except Exception as e:
            self.notify(f"Error viewing logs: {e}", "error")
    
    def view_run_history(self):
        """Show last 24 hours of scheduler activity"""
        try:
            base = get_base_dir()
            check_script = os.path.join(base, "check_runs.sh")
            
            if not os.path.exists(check_script):
                self.notify("check_runs.sh not found", "warn")
                return
            
            # Run the check_runs script
            result = subprocess.run(
                [check_script],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=10,
                cwd=base
            )
            
            # Create new window
            history_window = tk.Toplevel(self.root)
            history_window.title("Scheduler Run History (Last 24 Hours)")
            history_window.geometry("1000x700")
            
            # Add scrolled text widget
            history_text = scrolledtext.ScrolledText(history_window, wrap="word", font=("Monaco", 9))
            history_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            # Display output
            history_text.insert("1.0", result.stdout)
            history_text.see("1.0")
            history_text.configure(state="disabled")
            
        except Exception as e:
            self.notify(f"Error viewing run history: {e}", "error")
    
    def restart_scheduler(self):
        """Restart the scheduler daemon"""
        try:
            base = get_base_dir()
            manage_script = os.path.join(base, "manage_launchagent.sh")
            
            if os.path.exists(manage_script):
                # Use LaunchAgent restart
                self.notify("Restarting scheduler via LaunchAgent...", "info")
                subprocess.Popen(
                    [manage_script, "restart"],
                    cwd=base,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            else:
                # Manual restart
                self.notify("Restarting scheduler...", "info")
                self.stop_daemon_manual()
                self.root.after(2000, self.start_daemon_manual)
            
            # Refresh status after delay
            self.root.after(3000, self.refresh_daemon_status_manual)
            
        except Exception as e:
            self.notify(f"Error restarting scheduler: {e}", "error")
    
    def load_gui_state(self):
        """Load saved GUI state (selected client and retailers)"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Could not load GUI state: {e}")
        return None
    
    def save_gui_state(self):
        """Save current GUI state (selected client and retailers)"""
        try:
            # Get selected retailers
            selected_retailers = []
            if hasattr(self, 'retailer_picker'):
                selected_retailers = [
                    name for name, var in self.retailer_picker.vars.items() 
                    if var.get()
                ]
            
            # Get selected client
            selected_client = self.client_var.get() if hasattr(self, 'client_var') else PLACEHOLDER
            
            state = {
                "selected_client": selected_client,
                "selected_retailers": selected_retailers
            }
            
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"Could not save GUI state: {e}")
    
    def load_window_geometry(self):
        """Load saved window geometry from file"""
        try:
            if os.path.exists(self.geometry_file):
                with open(self.geometry_file, 'r') as f:
                    geometry = f.read().strip()
                    
                # Validate geometry string format (widthxheight+x+y or widthxheight-x-y)
                if geometry and ('x' in geometry):
                    # Parse geometry to check if position is reasonable
                    # Format: 900x1100+100+50 or 900x1100-100-50
                    parts = geometry.replace('-', '+').split('+')
                    if len(parts) >= 3:
                        try:
                            x = int(parts[1])
                            y = int(parts[2])
                            # Check if position is completely off-screen (negative or too large)
                            # Allow negative values for multi-monitor setups
                            # But reject if position is way off (> 10000 pixels)
                            if abs(x) < 10000 and abs(y) < 10000:
                                return geometry
                        except ValueError:
                            pass
                    return geometry  # Return even if we can't parse, let Tk handle it
        except Exception as e:
            print(f"Could not load window geometry: {e}")
        return None
    
    def save_window_geometry(self):
        """Save current window geometry to file"""
        try:
            geometry = self.root.geometry()
            os.makedirs(os.path.dirname(self.geometry_file), exist_ok=True)
            with open(self.geometry_file, 'w') as f:
                f.write(geometry)
        except Exception as e:
            print(f"Could not save window geometry: {e}")
    
    def check_and_launch_brand_review(self):
        """Check if there are unknown brands and auto-launch review tool"""
        try:
            print("[BRAND CHECK] Checking for unknown brands...")
            unknown_count, uncertain_count = self.count_unknown_brands()
            total = unknown_count + uncertain_count
            print(f"[BRAND CHECK] Found {unknown_count} unknown, {uncertain_count} uncertain brands")
            
            if total > 0:
                message_parts = []
                if unknown_count > 0:
                    message_parts.append(f"{unknown_count} ad(s) with unknown brands (extraction failed)")
                if uncertain_count > 0:
                    message_parts.append(f"{uncertain_count} ad(s) with uncertain brands (need confirmation)")
                
                response = messagebox.askyesno(
                    "Brand Review Needed",
                    "Found:\n" + "\n".join(message_parts) + "\n\n"
                    f"Total: {total} ad(s) need review.\n\n"
                    f"Would you like to review them now?",
                    icon='info'
                )
                if response:
                    self.launch_brand_review_tool()
            else:
                print("[BRAND CHECK] No unknown brands found")
        except Exception as e:
            logging.error(f"Error checking for unknown brands: {e}")
            print(f"[BRAND CHECK ERROR] {e}")
            import traceback
            traceback.print_exc()
    
    def count_unknown_brands(self):
        """Count ads with unknown/uncertain brands and return (unknown_count, uncertain_count)"""
        import glob
        import re
        
        unknown_count = 0  # Ads with brand="unknown"
        uncertain_count = 0  # Ads with uncertain brands (not "unknown")
        
        # Scan all retailers (same as brand_review_tool.py)
        json_files = []
        base = get_base_dir()
        for retailer in ['kroger', 'walmart', 'instacart']:
            pattern1 = os.path.join(base, f'output/{retailer}/*/runs/*.json')
            pattern2 = os.path.join(base, f'output/{retailer}/*/runs/*/*.json')
            json_files.extend(glob.glob(pattern1))
            json_files.extend(glob.glob(pattern2))
        
        # Remove duplicates
        json_files = list(set(json_files))
        
        for json_file in json_files:  # Scan ALL files, not just 50
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                
                for result in data.get('results', []):
                    for ad in result.get('ads', []):
                        advertisers = ad.get('advertisers', [])
                        brand = advertisers[0] if advertisers else 'unknown'
                        
                        # Separate "unknown" from other uncertain brands
                        if not advertisers or brand == 'unknown':
                            unknown_count += 1
                        elif self.is_uncertain_brand(brand):
                            uncertain_count += 1
            except:
                continue
        
        return (unknown_count, uncertain_count)
    
    def is_uncertain_brand(self, brand):
        """Check if a brand name looks uncertain (same logic as brand_review_tool)"""
        if not brand or brand == 'unknown':
            return True
        
        # Check if brand is in lexicon - if so, it's valid
        try:
            lexicon_path = os.path.join(get_base_dir(), 'config/brands.json')
            with open(lexicon_path, 'r') as f:
                lexicon_brands = json.load(f)
            
            brand_lower = brand.lower()
            for lex_brand in lexicon_brands:
                if lex_brand['name'].lower() == brand_lower:
                    return False
                if any(syn.lower() == brand_lower for syn in lex_brand.get('synonyms', [])):
                    return False
        except:
            pass
        
        # Kroger and Kroger-branded products are valid, not uncertain
        if brand.lower().startswith('kroger'):
            return False
        
        # Single word that's too short or generic
        if len(brand) <= 3:
            return True
        
        uncertain_patterns = [
            r'^(TOAOB|MSM|SSM|ZB)',
            r'^\w+\d{4,}$',
            r'(KB|MB|TOA|Scale|Act)\d+',
            r'(Q\d+|FY\d+|H\d+)$',
        ]
        
        for pattern in uncertain_patterns:
            if re.search(pattern, brand, re.IGNORECASE):
                return True
        
        return False
    
    def launch_brand_review_tool(self):
        """Launch brand review pipeline sequentially: Logo Verifier → Name Verifier → Unknown Ad Review.
        Each tool runs and must be closed before the next one opens, so changes from one
        step are reflected in the next."""
        try:
            base_dir = get_base_dir()
            
            steps = [
                ("Logo Verifier", os.path.join(base_dir, 'tools', 'logo_verifier_gui.py')),
                ("Brand Name Verifier", os.path.join(base_dir, 'tools', 'brand_name_verifier.py')),
                ("Unknown Ad Review", os.path.join(base_dir, 'brand_review_tool.py')),
            ]
            
            # Validate all paths first
            missing = [name for name, path in steps if not os.path.exists(path)]
            if missing:
                messagebox.showerror("Error", f"Missing tools:\n" + "\n".join(missing))
                return
            
            # Run sequentially in a background thread so the main UI stays responsive
            def run_pipeline():
                for name, path in steps:
                    logging.info(f"[REVIEW] Starting {name}...")
                    try:
                        proc = subprocess.Popen([sys.executable, path], cwd=base_dir)
                        proc.wait()  # Block until this tool is closed
                        logging.info(f"[REVIEW] {name} closed (exit code {proc.returncode})")
                    except Exception as e:
                        logging.error(f"[REVIEW] {name} failed: {e}")
                logging.info("[REVIEW] Brand review pipeline complete")
            
            import threading
            thread = threading.Thread(target=run_pipeline, daemon=True)
            thread.start()
            
        except Exception as e:
            logging.error(f"Error launching brand review tools: {e}")
            messagebox.showerror("Error", f"Failed to launch brand review tools:\n{str(e)}")
    
    def on_closing(self):
        """Handle window close event"""
        # Save window geometry and GUI state
        self.save_window_geometry()
        self.save_gui_state()
        # Destroy window
        self.root.destroy()
    
    def show_full_schedule(self):
        """Show a popup window with all scheduled runs across all clients and retailers"""
        # Create popup window
        popup = tk.Toplevel(self.root)
        popup.title("Full Schedule View")
        popup.geometry("1000x700")
        popup.transient(self.root)
        
        # Main container
        main_frame = ttk.Frame(popup, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Filters frame at top
        filters_frame = ttk.LabelFrame(main_frame, text="Filters", padding=10)
        filters_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Retailer filter
        ttk.Label(filters_frame, text="Retailer:").grid(row=0, column=0, padx=5, sticky="w")
        retailer_var = tk.StringVar(value="All")
        retailer_filter = ttk.Combobox(filters_frame, textvariable=retailer_var, width=20, state="readonly")
        retailer_filter.grid(row=0, column=1, padx=5)
        
        # Client filter
        ttk.Label(filters_frame, text="Client:").grid(row=0, column=2, padx=5, sticky="w")
        client_var = tk.StringVar(value="All")
        client_filter = ttk.Combobox(filters_frame, textvariable=client_var, width=30, state="readonly")
        client_filter.grid(row=0, column=3, padx=5)
        
        # Day filter
        ttk.Label(filters_frame, text="Day:").grid(row=0, column=4, padx=5, sticky="w")
        day_var = tk.StringVar(value="All")
        day_filter = ttk.Combobox(
            filters_frame, 
            textvariable=day_var, 
            values=["All", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
            width=15,
            state="readonly"
        )
        day_filter.grid(row=0, column=5, padx=5)
        
        # Show empty slots checkbox
        show_empty_var = tk.BooleanVar(value=False)
        show_empty_check = ttk.Checkbutton(
            filters_frame,
            text="Show empty slots",
            variable=show_empty_var
        )
        show_empty_check.grid(row=0, column=6, padx=15, sticky="w")
        
        # Schedule display area with scrollbar
        schedule_frame = ttk.Frame(main_frame)
        schedule_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create Treeview for schedule display (matrix view: time x retailers)
        # Columns will be dynamically set based on available retailers
        tree = ttk.Treeview(schedule_frame, show="tree headings", height=25)
        
        # Scrollbars
        scrollbar_y = ttk.Scrollbar(schedule_frame, orient="vertical", command=tree.yview)
        scrollbar_x = ttk.Scrollbar(schedule_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)
        
        tree.grid(row=0, column=0, sticky="nsew")
        scrollbar_y.grid(row=0, column=1, sticky="ns")
        scrollbar_x.grid(row=1, column=0, sticky="ew")
        
        schedule_frame.grid_rowconfigure(0, weight=1)
        schedule_frame.grid_columnconfigure(0, weight=1)
        
        # ── Schedule file helpers (used by load, delete, toggle) ──
        schedules_dir = os.path.join(get_base_dir(), "schedules")
        
        # Map: schedule_file_path → parsed config dict (for management actions)
        schedule_file_map = {}
        
        def _rebuild_master_index():
            """Rebuild the master schedule index after changes."""
            try:
                from pathlib import Path
                sys.path.insert(0, str(get_base_dir()))
                from schedules.schedules_lib import build_master_index
                build_master_index(Path(get_base_dir()))
            except Exception:
                pass
        
        def load_schedules(include_disabled=False):
            """Load all schedule configs using shared library.
            
            Returns list of dicts with keys: time, day, retailer, client, keywords,
            enabled, file_path (absolute path to the JSON file).
            """
            schedules = []
            base = get_base_dir()
            
            # Use shared library to scan schedules
            try:
                from pathlib import Path
                import sys
                sys.path.insert(0, str(base))
                from schedules.schedules_lib import scan_schedules
                
                schedule_objects = scan_schedules(Path(base))
                
                # Convert Schedule objects to display format
                for sched in schedule_objects:
                    if not include_disabled and not sched.enabled:
                        continue
                    
                    # Track the source file
                    file_path = str(sched.source_path) if hasattr(sched, 'source_path') and sched.source_path else None
                    if not file_path:
                        # Reconstruct from convention
                        client_slug = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in sched.client.lower())
                        kw_slug = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in sched.keywords[0].lower()) if sched.keywords else "default"
                        file_path = os.path.join(base, "schedules", f"{sched.retailer}__{client_slug}__{kw_slug}.json")
                    
                    # Cache the config for management
                    if file_path and os.path.exists(file_path):
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                schedule_file_map[file_path] = json.load(f)
                        except Exception:
                            pass
                    
                    keywords_str = ", ".join(sched.keywords[:3])
                    if len(sched.keywords) > 3:
                        keywords_str += f" (+{len(sched.keywords)-3} more)"
                    
                    # Convert 24h times back to 12h for display
                    for time_24h in sched.times:
                        try:
                            h, m = map(int, time_24h.split(':'))
                            ampm = "AM" if h < 12 else "PM"
                            if h == 0:
                                h = 12
                            elif h > 12:
                                h -= 12
                            time_str = f"{h}:{m:02d} {ampm}"
                            
                            for day in sched.days:
                                schedules.append({
                                    "time": time_str,
                                    "time_24h": time_24h,
                                    "day": day.capitalize(),
                                    "retailer": sched.retailer,
                                    "client": sched.client,
                                    "keywords": keywords_str,
                                    "enabled": sched.enabled,
                                    "file_path": file_path,
                                })
                        except (ValueError, AttributeError):
                            continue
                
                return schedules
            except Exception as e:
                print(f"Error loading schedules: {e}")
                # Fallback to legacy method
                pass
            
            # LEGACY FALLBACK: Scan output/<retailer>/<client>/schedule_config.json
            output_dir = os.path.join(base, "output")
            if not os.path.exists(output_dir):
                return schedules
            
            for retailer in os.listdir(output_dir):
                retailer_dir = os.path.join(output_dir, retailer)
                if not os.path.isdir(retailer_dir):
                    continue
                    
                for client in os.listdir(retailer_dir):
                    client_dir = os.path.join(retailer_dir, client)
                    if not os.path.isdir(client_dir):
                        continue
                    
                    config_file = os.path.join(client_dir, "schedule_config.json")
                    if os.path.exists(config_file):
                        try:
                            with open(config_file, 'r') as f:
                                config = json.load(f)
                            
                            # Get keywords
                            keywords = config.get("keywords", [])
                            keywords_str = ", ".join(keywords[:3])
                            if len(keywords) > 3:
                                keywords_str += f" (+{len(keywords)-3} more)"
                            
                            # Parse schedule (support both old and new format)
                            if "days" in config and "times" in config:
                                # New format
                                days = config["days"]
                                times = config["times"]
                                for time_slot in times:
                                    hour, minute, ampm = time_slot
                                    time_str = f"{hour}:{minute} {ampm}"
                                    for day in days:
                                        schedules.append({
                                            "time": time_str,
                                            "day": day,
                                            "retailer": retailer,
                                            "client": client,
                                            "keywords": keywords_str,
                                            "enabled": config.get("enabled", True),
                                            "file_path": config_file,
                                        })
                            elif "schedule" in config:
                                # Old format
                                for day, times in config["schedule"].items():
                                    for time_str in times:
                                        schedules.append({
                                            "time": time_str,
                                            "day": day.capitalize(),
                                            "retailer": retailer,
                                            "client": client,
                                            "keywords": keywords_str,
                                            "enabled": config.get("enabled", True),
                                            "file_path": config_file,
                                        })
                        except Exception as e:
                            print(f"Error loading {config_file}: {e}")
            
            return schedules
        
        # ── Row metadata: tree item id → schedule info for context menu ──
        row_meta = {}  # tree_item_id → {"day", "time", "retailer", "client", "file_path", "enabled"}
        
        # Include disabled schedules checkbox
        include_disabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            filters_frame,
            text="Include disabled",
            variable=include_disabled_var
        ).grid(row=0, column=7, padx=5, sticky="w")
        
        # Populate filters and tree
        def refresh_display():
            """Refresh the tree view as a matrix: rows=time slots, columns=retailers"""
            # Clear tree and metadata
            for item in tree.get_children():
                tree.delete(item)
            row_meta.clear()
            schedule_file_map.clear()
            
            # Get filter values
            client_filter_val = client_var.get()
            day_filter_val = day_var.get()
            show_empty = show_empty_var.get()
            include_disabled = include_disabled_var.get()
            
            # Load all schedules
            all_schedules = load_schedules(include_disabled=include_disabled)
            
            # Get all unique retailers from schedules AND from output directory
            scheduled_retailers = set(s["retailer"] for s in all_schedules)
            
            # Also scan output directory for retailers without schedules
            base = get_base_dir()
            output_dir = os.path.join(base, "output")
            all_retailers = set()
            if os.path.exists(output_dir):
                for item in os.listdir(output_dir):
                    item_path = os.path.join(output_dir, item)
                    if os.path.isdir(item_path) and item not in ["runs", "brand_logos"]:
                        all_retailers.add(item)
            
            all_retailers = sorted(all_retailers)
            all_clients = sorted(set(s["client"] for s in all_schedules))
            
            # Update filter dropdowns
            retailer_filter["values"] = ["All"] + all_retailers
            client_filter["values"] = ["All"] + all_clients
            
            # Apply client filter
            if client_filter_val != "All":
                all_schedules = [s for s in all_schedules if s["client"] == client_filter_val]
            
            # Determine which days to show
            all_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            if day_filter_val != "All":
                all_days = [day_filter_val]
            
            # Generate all time slots (5-minute intervals)
            def generate_time_slots():
                slots = []
                for hour in range(24):
                    for minute in [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]:
                        if hour == 0:
                            time_str = f"12:{minute:02d} AM"
                        elif hour < 12:
                            time_str = f"{hour}:{minute:02d} AM"
                        elif hour == 12:
                            time_str = f"12:{minute:02d} PM"
                        else:
                            time_str = f"{hour-12}:{minute:02d} PM"
                        slots.append(time_str)
                return slots
            
            all_time_slots = generate_time_slots()
            
            # Build matrix: {(day, time, retailer): [(client, enabled, file_path)]}
            matrix = {}
            for s in all_schedules:
                key = (s["day"], s["time"], s["retailer"])
                if key not in matrix:
                    matrix[key] = []
                matrix[key].append((s["client"], s.get("enabled", True), s.get("file_path", "")))
            
            # Configure tree columns: Day/Time + one column per retailer
            columns = ["time_day"] + all_retailers
            tree["columns"] = columns
            tree.column("#0", width=0, stretch=False)  # Hide tree column
            tree.column("time_day", width=150, anchor="w")
            tree.heading("time_day", text="Day / Time")
            
            for retailer in all_retailers:
                tree.column(retailer, width=200, anchor="w")
                tree.heading(retailer, text=retailer.capitalize())
            
            # Populate tree
            occupied_count = 0
            disabled_count = 0
            total_slots = 0
            
            for day in all_days:
                # Add day header (open=True makes it expanded by default)
                day_node = tree.insert("", "end", text=day, values=[f"═══ {day} ═══"] + [""] * len(all_retailers), tags=("day_header",), open=True)
                
                for time_slot in all_time_slots:
                    # Check if this time slot has any assignments
                    has_assignment = any((day, time_slot, r) in matrix for r in all_retailers)
                    
                    if not show_empty and not has_assignment:
                        continue
                    
                    total_slots += 1
                    
                    # Build row values and track metadata per cell
                    row_values = [time_slot]
                    row_has_disabled = False
                    row_clients_info = []  # For context menu
                    
                    for retailer in all_retailers:
                        key = (day, time_slot, retailer)
                        if key in matrix:
                            entries = matrix[key]
                            display_parts = []
                            for client, enabled, fpath in entries:
                                if not enabled:
                                    display_parts.append(f"⏸ {client}")
                                    row_has_disabled = True
                                    disabled_count += 1
                                else:
                                    display_parts.append(client)
                                    occupied_count += 1
                                row_clients_info.append({
                                    "day": day, "time": time_slot, "retailer": retailer,
                                    "client": client, "enabled": enabled, "file_path": fpath,
                                })
                            row_values.append(", ".join(display_parts))
                        else:
                            row_values.append("—" if show_empty else "")
                    
                    # Insert row
                    if row_has_disabled:
                        tags = ("disabled_row",)
                    elif not has_assignment:
                        tags = ("empty",)
                    else:
                        tags = ()
                    
                    item_id = tree.insert(day_node, "end", values=row_values, tags=tags)
                    
                    # Store metadata for this row (for context menu)
                    if row_clients_info:
                        row_meta[item_id] = row_clients_info
            
            # Configure tags
            tree.tag_configure("day_header", font=("Inter", 11, "bold"), background="#e0e0e0")
            tree.tag_configure("empty", foreground="gray")
            tree.tag_configure("disabled_row", foreground="#999999")
            
            # Update count
            parts = [f"{occupied_count} active runs"]
            if disabled_count:
                parts.append(f"{disabled_count} disabled")
            if show_empty:
                parts.append(f"{total_slots} total slots")
            count_label.config(text="Showing " + "  |  ".join(parts))
        
        # ── Right-click context menu ──
        ctx_menu = tk.Menu(popup, tearoff=0)
        
        def _get_row_schedules(event=None):
            """Get schedule info for the row under the cursor."""
            item = tree.identify_row(event.y) if event else tree.focus()
            if not item or item not in row_meta:
                return None, None
            return item, row_meta[item]
        
        def _toggle_schedule(file_path, enable):
            """Enable or disable a schedule by modifying its JSON file."""
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                config["enabled"] = enable
                config["updated_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=2)
                _rebuild_master_index()
                return True
            except Exception as e:
                messagebox.showerror("Error", f"Failed to update schedule:\n{e}")
                return False
        
        def _remove_time_from_schedule(file_path, time_24h):
            """Remove a specific time slot from a schedule file."""
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                times = config.get("times", [])
                if time_24h in times:
                    times.remove(time_24h)
                    config["times"] = times
                    config["updated_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                    if not times:
                        # No times left — delete the file entirely
                        os.remove(file_path)
                    else:
                        with open(file_path, 'w', encoding='utf-8') as f:
                            json.dump(config, f, indent=2)
                    _rebuild_master_index()
                    return True
            except Exception as e:
                messagebox.showerror("Error", f"Failed to remove time slot:\n{e}")
            return False
        
        def _delete_schedule_file(file_path):
            """Delete an entire schedule file."""
            try:
                fname = os.path.basename(file_path)
                confirm = messagebox.askyesno(
                    "Delete Schedule",
                    f"Permanently delete this schedule?\n\n{fname}\n\nThis cannot be undone."
                )
                if not confirm:
                    return False
                os.remove(file_path)
                _rebuild_master_index()
                return True
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete schedule:\n{e}")
                return False
        
        def on_right_click(event):
            """Show context menu on right-click."""
            item, schedules_info = _get_row_schedules(event)
            if not schedules_info:
                return
            
            ctx_menu.delete(0, tk.END)
            
            # If there's exactly one schedule in this cell, show direct actions
            # If multiple, show a submenu per client
            unique_files = {}
            for info in schedules_info:
                fp = info.get("file_path", "")
                if fp and fp not in unique_files:
                    unique_files[fp] = info
            
            for fp, info in unique_files.items():
                client = info["client"]
                retailer = info["retailer"]
                enabled = info["enabled"]
                label_prefix = f"{retailer}/{client}"
                fname = os.path.basename(fp)
                
                # Enable/Disable toggle
                if enabled:
                    ctx_menu.add_command(
                        label=f"⏸  Disable: {label_prefix}",
                        command=lambda f=fp: (_toggle_schedule(f, False), refresh_display())
                    )
                else:
                    ctx_menu.add_command(
                        label=f"▶  Enable: {label_prefix}",
                        command=lambda f=fp: (_toggle_schedule(f, True), refresh_display())
                    )
                
                # Remove this specific time slot
                # Find the 24h time for this row
                time_24h_val = None
                for s in schedules_info:
                    if s.get("file_path") == fp:
                        # Convert display time back to 24h
                        t = s.get("time", "")
                        try:
                            parts = t.replace(":", " ").split()
                            h = int(parts[0]); m = int(parts[1]); ap = parts[2].upper()
                            if ap == "AM":
                                if h == 12: h = 0
                            else:
                                if h != 12: h += 12
                            time_24h_val = f"{h:02d}:{m:02d}"
                        except (ValueError, IndexError):
                            pass
                        break
                
                if time_24h_val:
                    ctx_menu.add_command(
                        label=f"🕐  Remove time {info['time']}: {label_prefix}",
                        command=lambda f=fp, t=time_24h_val: (_remove_time_from_schedule(f, t), refresh_display())
                    )
                
                ctx_menu.add_command(
                    label=f"🗑  Delete entire schedule: {label_prefix}",
                    command=lambda f=fp: (_delete_schedule_file(f) and refresh_display())
                )
                
                ctx_menu.add_separator()
            
            # Show file path info
            if len(unique_files) == 1:
                fp = list(unique_files.keys())[0]
                ctx_menu.add_command(label=f"📄 {os.path.basename(fp)}", state="disabled")
            
            ctx_menu.tk_popup(event.x_root, event.y_root)
        
        # Bind right-click (macOS: Button-2 or Control-Button-1)
        tree.bind("<Button-2>", on_right_click)
        tree.bind("<Control-Button-1>", on_right_click)
        if sys.platform != "darwin":
            tree.bind("<Button-3>", on_right_click)
        
        # Bind filter changes
        retailer_var.trace("w", lambda *args: refresh_display())
        client_var.trace("w", lambda *args: refresh_display())
        day_var.trace("w", lambda *args: refresh_display())
        show_empty_var.trace("w", lambda *args: refresh_display())
        include_disabled_var.trace("w", lambda *args: refresh_display())
        
        # ── Bottom bar: count + action buttons ──
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X, pady=(5, 0))
        
        count_label = ttk.Label(bottom_frame, text="", font=("Inter", 10))
        count_label.pack(side=tk.LEFT)
        
        ttk.Button(
            bottom_frame,
            text="🔄 Refresh",
            command=refresh_display,
            width=10
        ).pack(side=tk.RIGHT, padx=2)
        
        def _delete_client_schedules():
            """Delete all schedules for a specific client."""
            sel_client = client_var.get()
            if sel_client == "All" or not sel_client:
                messagebox.showinfo("Select Client", "Filter to a specific client first, then use this button.")
                return
            
            # Find all files for this client
            matching = set()
            for info_list in row_meta.values():
                for info in info_list:
                    if info["client"] == sel_client and info.get("file_path"):
                        matching.add(info["file_path"])
            
            if not matching:
                messagebox.showinfo("No Schedules", f"No schedule files found for '{sel_client}'")
                return
            
            confirm = messagebox.askyesno(
                "Delete All Client Schedules",
                f"Delete ALL {len(matching)} schedule(s) for '{sel_client}'?\n\n"
                + "\n".join(f"  • {os.path.basename(f)}" for f in sorted(matching))
                + "\n\nThis cannot be undone."
            )
            if not confirm:
                return
            
            deleted = 0
            for fp in matching:
                try:
                    os.remove(fp)
                    deleted += 1
                except Exception:
                    pass
            
            _rebuild_master_index()
            refresh_display()
            messagebox.showinfo("Done", f"Deleted {deleted} schedule(s) for '{sel_client}'")
        
        ttk.Button(
            bottom_frame,
            text="🗑 Delete Client Schedules",
            command=_delete_client_schedules,
            width=22
        ).pack(side=tk.RIGHT, padx=2)
        
        ttk.Label(
            bottom_frame,
            text="  Right-click a row for actions  ",
            font=("Inter", 9), foreground="gray"
        ).pack(side=tk.RIGHT, padx=5)
        
        # Initial load
        refresh_display()
    
    def start_daemon_automatically(self):
        """Optionally start the scheduler daemon if it's not running (opt-in only)."""
        try:
            print("Scheduler daemon not running. Starting automatically (opt-in)...")

            # Locate start script
            if getattr(sys, 'frozen', False):
                possible_paths = [
                    os.path.join(get_base_dir(), "start_scheduler.sh"),
                    os.path.expanduser("~/Documents/Amazon_Scrape/start_scheduler.sh"),
                ]
                daemon_script = next((p for p in possible_paths if os.path.exists(p)), None)
            else:
                daemon_script = os.path.join(os.path.dirname(__file__), "start_scheduler.sh")

            if daemon_script and os.path.exists(daemon_script):
                env = os.environ.copy()
                # Ensure the central scheduler gate is set if you want to start from GUI
                env.setdefault("SCRAPER_HOME", get_base_dir())
                env.setdefault("CENTRAL_SCHEDULER", "1")  # required by our guarded start script
                env.setdefault("PYTHONIOENCODING", "utf-8")  # ensure child writes UTF-8
                # RETAILER is optional; if you run per-retailer schedulers, set it in the environment

                subprocess.Popen(
                    [daemon_script],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                    env=env,
                    text=True,
                    encoding="utf-8",
                    errors="replace"
                )
                print("✅ Scheduler daemon start attempted")
                # Allow a brief moment then re-check status
                time.sleep(1.0)
                self.daemon_status = self.check_daemon_status()

                if hasattr(self, 'status_label'):
                    daemon_text = "✅ Daemon running (auto-started)" if self.daemon_status else "⚠️ Daemon start attempted"
                    self.status_label.config(text=f"Ready to scrape | {daemon_text}")
            else:
                print("⚠️ Scheduler daemon script not found")
                if hasattr(self, 'status_label'):
                    self.status_label.config(text="⚠️ Daemon script not found - manual start required")
        except Exception as e:
            print(f"Error starting daemon: {e}")
            if hasattr(self, 'status_label'):
                self.status_label.config(text=f"Error starting daemon: {e}")
    
    def check_and_update_conflict_display(self, time_widgets):
        """Check for time conflicts and update the conflict display"""
        try:
            hour_var = time_widgets['hour_var']
            minute_var = time_widgets['minute_var']
            ampm_var = time_widgets['ampm_var']
            conflict_label = time_widgets['conflict_label']
            hour_combo = time_widgets['hour_combo']
            minute_combo = time_widgets['minute_combo']
            ampm_combo = time_widgets['ampm_combo']
            
            # Get current values
            hour_str = hour_var.get()
            minute_str = minute_var.get()
            ampm = ampm_var.get()
            
            if not hour_str or not minute_str or not ampm:
                conflict_label.config(text="")
                return
                
            try:
                hour_12 = int(hour_str)
                minute = int(minute_str)
            except ValueError:
                conflict_label.config(text="")
                return
                
            # Convert to 24-hour format
            hour_24 = hour_12
            if ampm == "PM" and hour_12 < 12:
                hour_24 += 12
            elif ampm == "AM" and hour_12 == 12:
                hour_24 = 0
                
            # Get selected days and client
            selected_client = self.client_var.get() if hasattr(self, 'client_var') else None
            selected_days = []
            if hasattr(self, 'day_vars'):
                selected_days = [day for day, var in self.day_vars.items() if var.get()]
                
            if not selected_days or not selected_client or selected_client == PLACEHOLDER:
                conflict_label.config(text="(select client & days)", fg="gray")
                return
                
            # Check for conflicts
            if self.is_time_conflicted(hour_24, minute, selected_days, selected_client):
                conflict_label.config(text="⚠ CONFLICT", fg="red")
                
                # Gray out the conflicted time selectors
                hour_combo.config(foreground="gray")
                minute_combo.config(foreground="gray")
                ampm_combo.config(foreground="gray")
                
                # Find and suggest alternative
                alt_hour, alt_minute, alt_ampm = self.find_next_available_time(
                    hour_12, minute, ampm, selected_days, selected_client
                )
                
                if (alt_hour, alt_minute, alt_ampm) != (hour_12, minute, ampm):
                    suggestion_text = f"⚠ CONFLICT - Try {alt_hour}:{alt_minute:02d} {alt_ampm}"
                    conflict_label.config(text=suggestion_text, fg="orange")
                    
                    # Add click handler to apply suggestion
                    def apply_suggestion():
                        hour_var.set(str(alt_hour))
                        minute_var.set(f"{alt_minute:02d}")
                        ampm_var.set(alt_ampm)
                        
                    conflict_label.config(cursor="hand2")
                    conflict_label.bind("<Button-1>", lambda e: apply_suggestion())
                    
            else:
                conflict_label.config(text="✓ Available", fg="green")
                # Reset normal colors
                hour_combo.config(foreground="black")
                minute_combo.config(foreground="black") 
                ampm_combo.config(foreground="black")
                conflict_label.config(cursor="")
                conflict_label.unbind("<Button-1>")
                
        except Exception as e:
            # Silently handle any errors in conflict checking
            if 'conflict_label' in time_widgets:
                time_widgets['conflict_label'].config(text="")
        
        # Update save button state based on conflicts
        try:
            self.refresh_save_button_state()
        except Exception:
            pass
    
    def refresh_all_conflict_displays(self):
        """Refresh conflict displays for all time selectors"""
        if hasattr(self, 'time_widget_refs'):
            for time_widgets in self.time_widget_refs:
                self.check_and_update_conflict_display(time_widgets)
    
    def save_to_history(self, client_type, keywords):
        """Save client and keywords to history"""
        # Update the history dictionary
        self.client_history[client_type] = keywords
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
        
        # Save to file
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self.client_history, f, indent=2)
        except IOError as e:
            print(f"Warning: Could not save client history: {e}")
    
    def update_client_dropdown(self, select=None):
        clients = sorted(self.client_history.keys(), key=str.lower)
        self.client_dropdown['values'] = [PLACEHOLDER] + clients
        if select and select in clients:
            self.client_var.set(select)
        elif self.client_var.get() not in ([PLACEHOLDER] + clients):
            self.client_var.set(PLACEHOLDER)
        
    def on_new_client(self):
        name = simpledialog.askstring("New Client", "Enter new client/product name:")
        if not name or not name.strip():
            return
        name = name.strip()
        # add to history and persist
        if name not in self.client_history:
            self.client_history[name] = []
            self.save_to_history(name, self.client_history[name])

        # refresh dropdown alphabetically and select
        clients = sorted(self.client_history.keys(), key=str.lower)
        self.client_dropdown['values'] = [PLACEHOLDER] + clients
        self.client_var.set(name)
        self.keyword_input.delete(1.0, tk.END)
        self.status_label.config(text=f"Created new client: {name}")
        # set up logging for this client
        self.logger = self.setup_logging(name)
        # refresh schedule UI/conflicts
        try:
            if hasattr(self, 'refresh_all_conflict_displays'):
                self.refresh_all_conflict_displays()
            self.refresh_save_button_state()
        except Exception:
            pass
    
    def on_remove_client(self):
        """Remove a client: unschedule only (keep folders) or full delete (folders + schedules)."""
        selected_client = self.client_var.get()
        if not selected_client or selected_client == PLACEHOLDER:
            self.notify("Select a client to remove first", "error")
            return
        
        # Gather info about what exists for this client
        base = get_base_dir()
        schedules_dir = os.path.join(base, "schedules")
        client_slug = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in selected_client.lower())
        
        # Find schedule files
        schedule_files = []
        if os.path.exists(schedules_dir):
            for f in os.listdir(schedules_dir):
                if f.endswith('.json') and f != 'master_schedule.json':
                    try:
                        with open(os.path.join(schedules_dir, f), 'r', encoding='utf-8') as fh:
                            cfg = json.load(fh)
                        cfg_client = cfg.get("client", "")
                        cfg_slug = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in cfg_client.lower())
                        if cfg_slug == client_slug or cfg_client == selected_client:
                            schedule_files.append(f)
                    except Exception:
                        # Fallback: match by filename convention
                        if f'__{client_slug}__' in f:
                            schedule_files.append(f)
        
        # Find output folders (across all retailers)
        output_dir = os.path.join(base, "output")
        client_folders = []
        if os.path.exists(output_dir):
            for retailer in os.listdir(output_dir):
                retailer_dir = os.path.join(output_dir, retailer)
                if not os.path.isdir(retailer_dir) or retailer in ["runs", "brand_logos"]:
                    continue
                for folder in os.listdir(retailer_dir):
                    folder_slug = folder.lower()
                    if folder_slug == client_slug or folder == selected_client:
                        full_path = os.path.join(retailer_dir, folder)
                        if os.path.isdir(full_path):
                            # Count files inside
                            file_count = sum(len(files) for _, _, files in os.walk(full_path))
                            client_folders.append((f"{retailer}/{folder}", full_path, file_count))
        
        if not schedule_files and not client_folders and selected_client not in self.client_history:
            self.notify(f"Nothing found for '{selected_client}'", "warn")
            return
        
        # Build the removal dialog
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Remove Client: {selected_client}")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        
        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text=f"Remove '{selected_client}'", font=("Inter", 14, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Choose what to remove:", font=("Inter", 10)).pack(anchor="w", pady=(5, 10))
        
        # Summary of what exists
        summary_frame = ttk.LabelFrame(frame, text="What exists", padding=8)
        summary_frame.pack(fill=tk.X, pady=(0, 10))
        
        if schedule_files:
            ttk.Label(summary_frame, text=f"📅  {len(schedule_files)} schedule file(s)").pack(anchor="w")
            for sf in schedule_files:
                ttk.Label(summary_frame, text=f"      {sf}", foreground="gray").pack(anchor="w")
        else:
            ttk.Label(summary_frame, text="📅  No schedule files", foreground="gray").pack(anchor="w")
        
        if client_folders:
            total_files = sum(fc for _, _, fc in client_folders)
            ttk.Label(summary_frame, text=f"📁  {len(client_folders)} data folder(s)  ({total_files} files)").pack(anchor="w")
            for label, _, fc in client_folders:
                ttk.Label(summary_frame, text=f"      {label}/  ({fc} files)", foreground="gray").pack(anchor="w")
        else:
            ttk.Label(summary_frame, text="📁  No data folders", foreground="gray").pack(anchor="w")
        
        if selected_client in self.client_history:
            kw_count = len(self.client_history[selected_client])
            ttk.Label(summary_frame, text=f"📝  Client entry with {kw_count} keyword(s)").pack(anchor="w")
        
        # Checkboxes for what to remove
        options_frame = ttk.LabelFrame(frame, text="Remove", padding=8)
        options_frame.pack(fill=tk.X, pady=(0, 10))
        
        remove_schedules_var = tk.BooleanVar(value=True)
        remove_history_var = tk.BooleanVar(value=True)
        remove_folders_var = tk.BooleanVar(value=False)
        
        ttk.Checkbutton(
            options_frame, text="Schedule files (stops all automated runs)",
            variable=remove_schedules_var
        ).pack(anchor="w")
        
        ttk.Checkbutton(
            options_frame, text="Client from dropdown (remove from history)",
            variable=remove_history_var
        ).pack(anchor="w")
        
        folder_cb = ttk.Checkbutton(
            options_frame,
            text="Data folders and all contents (⚠️ cannot be undone)",
            variable=remove_folders_var
        )
        folder_cb.pack(anchor="w")
        
        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        result = {"confirmed": False}
        
        def do_remove():
            result["confirmed"] = True
            dialog.destroy()
        
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(btn_frame, text="Remove", command=do_remove, style='Primary.TButton').pack(side=tk.RIGHT)
        
        # Center dialog on parent
        dialog.update_idletasks()
        w = dialog.winfo_width()
        h = dialog.winfo_height()
        x = self.root.winfo_x() + (self.root.winfo_width() - w) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - h) // 2
        dialog.geometry(f"+{x}+{y}")
        
        dialog.wait_window()
        
        if not result["confirmed"]:
            return
        
        removed_parts = []
        
        # 1. Remove schedule files
        if remove_schedules_var.get() and schedule_files:
            deleted = 0
            for sf in schedule_files:
                try:
                    os.remove(os.path.join(schedules_dir, sf))
                    deleted += 1
                except Exception as e:
                    print(f"Error deleting schedule {sf}: {e}")
            removed_parts.append(f"{deleted} schedule(s)")
            
            # Rebuild master index
            try:
                from pathlib import Path
                sys.path.insert(0, str(base))
                from schedules.schedules_lib import build_master_index
                build_master_index(Path(base))
            except Exception:
                pass
        
        # 2. Remove from client history
        if remove_history_var.get() and selected_client in self.client_history:
            del self.client_history[selected_client]
            try:
                os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
                with open(self.history_file, "w", encoding="utf-8") as f:
                    json.dump(self.client_history, f, indent=2)
            except Exception as e:
                print(f"Error saving client history: {e}")
            removed_parts.append("client entry")
        
        # 3. Remove data folders
        if remove_folders_var.get() and client_folders:
            import shutil
            deleted_folders = 0
            for label, full_path, _ in client_folders:
                try:
                    shutil.rmtree(full_path)
                    deleted_folders += 1
                except Exception as e:
                    print(f"Error deleting folder {full_path}: {e}")
            removed_parts.append(f"{deleted_folders} folder(s)")
        
        # Update UI
        self.update_client_dropdown()
        self.client_var.set(PLACEHOLDER)
        self.keyword_input.delete(1.0, tk.END)
        
        summary = ", ".join(removed_parts) if removed_parts else "nothing"
        self.notify(f"Removed {summary} for '{selected_client}'", "success")
        self.status_label.config(text=f"Removed {summary} for {selected_client}")
        self._activity_line(f"Removed client '{selected_client}': {summary}", "info")
        
        try:
            if hasattr(self, 'refresh_all_conflict_displays'):
                self.refresh_all_conflict_displays()
            self.refresh_save_button_state()
        except Exception:
            pass
    
    def on_client_selected(self, event):
        sel = self.client_var.get()
        if sel == PLACEHOLDER:
            self.keyword_input.delete(1.0, tk.END)
            self.status_label.config(text="Ready to scrape")
            try:
                self.schedule_button.state(['disabled'])
            except Exception:
                try:
                    self.schedule_button.config(state="disabled")
                except Exception:
                    pass
            return

        self.keyword_input.delete(1.0, tk.END)
        if sel in self.client_history:
            kws = self.client_history[sel]
            self.keyword_input.insert(tk.END, "\n".join(kws))
            self.status_label.config(text=f"Loaded {len(kws)} keywords for {sel}")

        # load schedule config
        self.schedule_config = self.load_schedule_config(sel)
        if "runs" in self.schedule_config:
            self.runs_var.set(self.schedule_config["runs"])
            self.update_time_selectors()
        else:
            self.load_saved_times()
        if "days" in self.schedule_config:
            for day in self.day_vars:
                self.day_vars[day].set(day in self.schedule_config["days"])
        
        # Schedule keywords are the source of truth — override client_history if present
        if "keywords" in self.schedule_config and self.schedule_config["keywords"]:
            kws = self.schedule_config["keywords"]
            self.keyword_input.delete(1.0, tk.END)
            self.keyword_input.insert(tk.END, "\n".join(kws))
            self.status_label.config(text=f"Loaded {len(kws)} keywords for {sel} (from schedule)")
            # Keep client_history in sync
            if sel in self.client_history and self.client_history[sel] != kws:
                self.client_history[sel] = kws
                self.save_to_history(sel, kws)

        self.logger = self.setup_logging(sel)
        try:
            if hasattr(self, 'refresh_all_conflict_displays'):
                self.refresh_all_conflict_displays()
            self.refresh_save_button_state()
        except Exception:
            pass
    
    def setup_logging(self, client=None):
        """Set up logging to file for scheduler events"""
        if client:
            # Create client-specific log directory (retailer-scoped)
            folder_name = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in client)
            # Default to kroger for backward compatibility
            retailer_slug = "kroger"
            base = get_base_dir()
            log_dir = output_dir_for(base, retailer_slug, folder_name)
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, "scheduler.log")
            
            # Configure logger
            logger = logging.getLogger(f"scheduler_{client}")
            logger.setLevel(logging.INFO)
            
            # Create file handler
            handler = logging.FileHandler(log_file)
            handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            
            # Clear existing handlers and add new one
            logger.handlers = []
            logger.addHandler(handler)
            
            return logger
        return None
            
    def on_keyword_focus_in(self, event):
        """Handle focus in event for keyword input - clear placeholder"""
        if self.keyword_input.get(1.0, "end-1c") == self.placeholder_text:
            self.keyword_input.delete(1.0, tk.END)
            self.keyword_input.config(fg="black")
    
    def on_keyword_focus_out(self, event):
        """Handle focus out event for keyword input - restore placeholder if empty"""
        if not self.keyword_input.get(1.0, "end-1c").strip():
            self.keyword_input.delete(1.0, tk.END)
            self.keyword_input.insert(tk.END, self.placeholder_text)
            self.keyword_input.config(fg="gray")
    
    def update_time_selectors(self, *args):
        """Update time selector fields based on number of runs"""
        # Clear existing time selectors
        for widget in self.times_frame.winfo_children():
            widget.destroy()
        self.time_vars.clear()
        self.time_entries.clear()
        
        # Clear widget references for conflict checking
        if hasattr(self, 'time_widget_refs'):
            self.time_widget_refs.clear()
        
        # Get number of runs
        num_runs = self.runs_var.get()
        
        # Get saved times from schedule_config if available
        saved_times = []
        if hasattr(self, 'schedule_config') and "times" in self.schedule_config:
            saved_times = self.schedule_config.get("times", [])
            print(f"[DEBUG] update_time_selectors: Found {len(saved_times)} saved times: {saved_times}")
        
        # Create time selectors
        for i in range(num_runs):
            # Create frame for this time selector
            time_frame = ttk.Frame(self.times_frame, style='Card.TFrame')
            time_frame.pack(fill=tk.X, pady=(0, 5))

            # Label
            label = ttk.Label(time_frame, text=f"Run {i+1} at:", style='TLabel')
            label.pack(side=tk.LEFT)
            
            # Hour selector
            hour_var = tk.StringVar()
            hour_values = [f"{h}" for h in range(1, 13)]
            hour_combo = ttk.Combobox(
                time_frame,
                textvariable=hour_var,
                values=hour_values,
                width=3,
                style='App.TCombobox'
            )
            hour_combo.pack(side=tk.LEFT, padx=(10, 0))
            
            # Use saved times if available, otherwise use defaults
            if i < len(saved_times):
                # Use saved time from schedule
                saved_hour, saved_minute, saved_ampm = saved_times[i]
                default_hour = int(saved_hour)
                default_minute = int(saved_minute)
                default_ampm = saved_ampm
                print(f"[DEBUG] Using saved time for slot {i}: {default_hour}:{default_minute:02d} {default_ampm}")
            else:
                # Fall back to default times
                default_times = [
                    (8, 0, "AM"),   # 8 AM
                    (12, 0, "PM"),  # 12 PM  
                    (4, 0, "PM"),   # 4 PM
                ]
                
                if i < len(default_times):
                    default_hour, default_minute, default_ampm = default_times[i]
                else:
                    # Generate spaced out times for additional runs
                    base_hour = 8 + (i * 4)
                    default_hour = base_hour % 12 or 12
                    default_minute = 0
                    default_ampm = "AM" if base_hour < 12 else "PM"
            
            # Check for conflicts and find alternative if needed
            selected_client = self.client_var.get() if hasattr(self, 'client_var') else None
            selected_days = []
            if hasattr(self, 'day_vars'):
                selected_days = [day for day, var in self.day_vars.items() if var.get()]
            
            # Store the final values to use after creating the variables
            final_hour = default_hour
            final_minute = default_minute
            final_ampm = default_ampm
            
            if selected_days and selected_client and selected_client != PLACEHOLDER:
                # Convert to 24-hour for conflict checking
                hour_24 = default_hour
                if default_ampm == "PM" and default_hour < 12:
                    hour_24 += 12
                elif default_ampm == "AM" and default_hour == 12:
                    hour_24 = 0
                    
                if self.is_time_conflicted(hour_24, default_minute, selected_days, selected_client):
                    # Find next available time and store the values
                    final_hour, final_minute, final_ampm = self.find_next_available_time(
                        default_hour, default_minute, default_ampm, selected_days, selected_client
                    )
            
            # Set the hour variable now that it exists
            hour_var.set(str(final_hour))
            
            # Colon label
            colon_label = ttk.Label(time_frame, text=":", style='TLabel')
            colon_label.pack(side=tk.LEFT)
            
            # Minute selector (populate with allowed minutes for the initial hour/ampm)
            minute_var = tk.StringVar(value=f"{final_minute:02d}")
            minute_combo = ttk.Combobox(
                time_frame,
                textvariable=minute_var,
                values=[f"{m:02d}" for m in range(0, 60, 5)],  # temporary, will filter next
                width=3,
                style='App.TCombobox',
                state="readonly",
            )
            minute_combo.pack(side=tk.LEFT, padx=(0, 5))

            # AM/PM selector
            ampm_var = tk.StringVar(value=final_ampm)
            ampm_combo = ttk.Combobox(
                time_frame,
                textvariable=ampm_var,
                values=["AM", "PM"],
                width=3,
                style='App.TCombobox',
                state="readonly",
            )
            ampm_combo.pack(side=tk.LEFT, padx=(5, 0))

            # After both hour and ampm exist, filter minutes to allowed set
            selected_client = self.client_var.get() if hasattr(self, 'client_var') else None
            selected_days = [day for day, var in self.day_vars.items() if var.get()] if hasattr(self, 'day_vars') else []
            allowed_minutes = self.get_allowed_minutes_for_hour(final_hour, final_ampm, selected_days, exclude_client=selected_client)
            if allowed_minutes:
                minute_combo["values"] = allowed_minutes
                if minute_var.get() not in allowed_minutes:
                    minute_var.set(allowed_minutes[0])
            else:
                # No allowed minutes in that hour; auto-suggest next available
                alt_h, alt_m, alt_a = self.find_next_available_time(final_hour, final_minute, final_ampm, selected_days, selected_client)
                hour_var.set(str(alt_h))
                ampm_var.set(alt_a)
                minute_combo["values"] = self.get_allowed_minutes_for_hour(alt_h, alt_a, selected_days, exclude_client=selected_client)
                minute_var.set(f"{alt_m:02d}")

            # Conflict indicator label (use tk.Label for better color control)
            conflict_label = tk.Label(
                time_frame, 
                text="", 
                width=25,
                anchor="w",
                bg=self.root.cget('bg') if hasattr(self, 'root') else 'white',
                font=('SF Pro', 11)
            )
            conflict_label.pack(side=tk.LEFT, padx=(5, 0))
            
            # Store references for conflict checking
            time_widgets = {
                'hour_combo': hour_combo,
                'minute_combo': minute_combo, 
                'ampm_combo': ampm_combo,
                'conflict_label': conflict_label,
                'hour_var': hour_var,
                'minute_var': minute_var,
                'ampm_var': ampm_var
            }
            
            # Add event handlers for real-time conflict checking
            def check_time_conflict(*args):
                # re-filter minute options for current hour/ampm/days
                try:
                    selected_client = self.client_var.get()
                    days = [day for day, var in self.day_vars.items() if var.get()]
                    h_str = hour_var.get()
                    a = ampm_var.get()
                    if h_str and a and days:
                        h = int(h_str)
                        allowed = self.get_allowed_minutes_for_hour(h, a, days, exclude_client=selected_client)
                        minute_combo["values"] = allowed or [minute_var.get()]
                        if allowed and minute_var.get() not in allowed:
                            minute_var.set(allowed[0])
                except Exception:
                    pass
                # keep your existing label update
                self.check_and_update_conflict_display(time_widgets)
                self.refresh_save_button_state()
                
            hour_var.trace('w', check_time_conflict)
            minute_var.trace('w', check_time_conflict)
            ampm_var.trace('w', check_time_conflict)
            
            # Initial filter
            try:
                check_time_conflict()
            except Exception as e:
                print(f"Error in initial check_time_conflict: {e}")
            
            # Store variables
            self.time_vars.append((hour_var, minute_var, ampm_var))
            self.time_entries.append((hour_combo, minute_combo, ampm_combo))
            
            # Store widget references for conflict checking
            if not hasattr(self, 'time_widget_refs'):
                self.time_widget_refs = []
            self.time_widget_refs.append(time_widgets)
        
        # Saved times are now loaded at the start of this method from self.schedule_config
        # No need to reload here - just refresh conflict displays
        try:
            if hasattr(self, 'refresh_all_conflict_displays'):
                self.refresh_all_conflict_displays()
        except Exception:
            pass
        
        # Update save button state based on conflicts
        self.refresh_save_button_state()
    
    def load_saved_times(self):
        """Load saved times from schedule configuration"""
        config = getattr(self, 'schedule_config', {})
        if "times" in config and len(config["times"]) > 0:
            # Update the number of runs
            num_times = min(len(config["times"]), len(self.time_vars))
            
            # Set the values for each time selector
            for i in range(num_times):
                if i < len(self.time_vars):
                    hour_var, minute_var, ampm_var = self.time_vars[i]
                    saved_hour, saved_minute, saved_ampm = config["times"][i]
                    
                    hour_var.set(saved_hour)
                    minute_var.set(saved_minute)
                    ampm_var.set(saved_ampm)

        # After loading saved values, refresh conflict indicators
        try:
            if hasattr(self, 'refresh_all_conflict_displays'):
                self.refresh_all_conflict_displays()
        except Exception:
            pass
    
    def load_schedule_config(self, client=None):
        """Load schedule configuration from file using shared library"""
        default_config = {
            "runs": 3, 
            "times": [("8", "00", "AM"), ("12", "00", "PM"), ("4", "00", "PM")],
            "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        }
        
        # If client is specified, try to load from new schedules/ directory
        if client:
            try:
                from pathlib import Path
                import sys
                base = get_base_dir()
                sys.path.insert(0, str(base))
                from schedules.schedules_lib import scan_schedules
                
                # Scan all schedules and find matching client
                schedules = scan_schedules(Path(base))
                retailer_slug = self._schedule_retailer_slug()
                
                print(f"[DEBUG LOAD] Looking for client='{client}' retailer='{retailer_slug}'")
                print(f"[DEBUG LOAD] Found {len(schedules)} total schedules")
                
                for sched in schedules:
                    print(f"[DEBUG LOAD] Checking: {sched.retailer}/{sched.client}")
                    if sched.client.lower() == client.lower() and sched.retailer == retailer_slug:
                        print(f"[DEBUG LOAD] MATCH FOUND! Loading schedule for {sched.client}")
                        # Convert 24h times back to 12h format for GUI
                        times_12h = []
                        for time_24h in sched.times:
                            h, m = map(int, time_24h.split(':'))
                            ampm = "AM" if h < 12 else "PM"
                            if h == 0:
                                h = 12
                            elif h > 12:
                                h -= 12
                            times_12h.append((str(h), f"{m:02d}", ampm))
                        
                        # Convert lowercase days to capitalized
                        days_cap = [d.capitalize() for d in sched.days]
                        
                        # Update schedule file path
                        self.schedule_file = sched.source_path
                        
                        return {
                            "runs": len(sched.times),
                            "times": times_12h,
                            "days": days_cap,
                            "keywords": sched.keywords,
                            "client": sched.client,
                            "retailer": sched.retailer
                        }
                
                print(f"[DEBUG LOAD] No matching schedule found for {client}/{retailer_slug}")
            except Exception as e:
                print(f"[DEBUG LOAD] Error loading schedule from library: {e}")
                import traceback
                traceback.print_exc()
                pass  # Fall back to legacy method
            
            # LEGACY: Try old output/ location
            folder_name = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in client)
            base = get_base_dir()
            retailer_slug = "kroger"  # Default for backward compatibility
            client_schedule_file = os.path.join(base, "output", retailer_slug, folder_name, "schedule_config.json")
            
            # Fall back to old path if new path doesn't exist
            if not os.path.exists(client_schedule_file):
                client_schedule_file = os.path.join(base, "output", folder_name, "schedule_config.json")
            
            if os.path.exists(client_schedule_file):
                try:
                    with open(client_schedule_file, "r", encoding="utf-8") as f:
                        config = json.load(f)
                    # Update the schedule file path to use client-specific path
                    self.schedule_file = client_schedule_file
                    return config
                except (json.JSONDecodeError, IOError):
                    pass  # Fall back to default or global config
        
        # Try to load from the current schedule file path
        if os.path.exists(self.schedule_file):
            try:
                with open(self.schedule_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass  # Fall back to default config
                
        return default_config
    
    def save_schedule(self):
        """Save schedule configuration to file"""
        selected_client = self.client_var.get()
        if not selected_client or selected_client == PLACEHOLDER:
            self.notify("Select a client/product before saving schedule", "error")
            return False
        
        # Get selected retailers
        try:
            selected_retailers = self.retailer_picker.get_selected()
            if not selected_retailers:
                self.notify("Select at least one retailer before saving schedule", "error")
                return False
        except Exception:
            self.notify("Error getting selected retailers", "error")
            return False

        # Detect conflicts
        if self.schedule_has_conflicts():
            self.notify("Selected times conflict with other clients. Adjust before saving.", "error")
            return False
            
        # Check for visual conflicts (should be redundant with above check)
        if self.any_conflicts_current_view():
            # Auto-fix conflicts without modal prompt
            self.notify("Conflicts detected. Auto-adjusting to next available times.", "warn")
            # auto-fix by applying next available time for each conflicting slot
            for tw in getattr(self, 'time_widget_refs', []):
                lbl = tw.get('conflict_label')
                if not lbl:
                    continue
                if "CONFLICT" in (lbl.cget("text") or ""):
                    # Pull current selection
                    hv = tw['hour_var'].get()
                    mv = tw['minute_var'].get()
                    av = tw['ampm_var'].get()
                    try:
                        hour_12 = int(hv); minute = int(mv)
                    except ValueError:
                        continue
                    # compute next available
                    selected_days = [day for day, var in self.day_vars.items() if var.get()]
                    alt_h, alt_m, alt_a = self.find_next_available_time(hour_12, minute, av, selected_days, selected_client)
                    # apply
                    tw['hour_var'].set(str(alt_h))
                    tw['minute_var'].set(f"{alt_m:02d}")
                    tw['ampm_var'].set(alt_a)
            # refresh
            self.refresh_all_conflict_displays()
            self.refresh_save_button_state()
            if self.any_conflicts_current_view():
                self.notify("Could not resolve all conflicts automatically.", "error")
                return False
            
        # Create client slug
        client_slug = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in selected_client.lower())
        
        # Get current times and convert to 24-hour format
        times_24h = []
        for hour_var, minute_var, ampm_var in self.time_vars:
            try:
                hour = int(hour_var.get())
                minute = int(minute_var.get())
                ampm = ampm_var.get().upper()
                
                # Convert to 24-hour
                if ampm == "AM":
                    if hour == 12:
                        hour = 0
                elif ampm == "PM":
                    if hour != 12:
                        hour += 12
                
                times_24h.append(f"{hour:02d}:{minute:02d}")
            except (ValueError, AttributeError):
                continue
        
        # Get selected days and normalize to lowercase
        selected_days = []
        for day, var in self.day_vars.items():
            if var.get():
                selected_days.append(day.lower())
        
        # Get keywords from text area
        keywords_text = self.keyword_input.get("1.0", tk.END).strip()
        keywords = [kw.strip() for kw in keywords_text.split('\n') if kw.strip() and kw.strip() != self.placeholder_text]
        
        # Guard: don't save empty schedules
        if not keywords:
            self.notify("No keywords to save in schedule.", "warn")
            return False
        
        # Save a schedule for EACH selected retailer
        schedules_dir = os.path.join(get_base_dir(), "schedules")
        os.makedirs(schedules_dir, exist_ok=True)
        
        saved_count = 0
        from datetime import datetime
        now_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        
        for retailer_name in selected_retailers:
            # Convert retailer display name to slug
            retailer_slug = self._retailer_by_name.get(retailer_name, retailer_name.lower())
            
            # Generate schedule ID
            import hashlib
            key = f"{retailer_slug}|{client_slug}|{','.join(keywords)}|{','.join(selected_days)}|{','.join(times_24h)}"
            dhash = hashlib.sha1(key.encode()).hexdigest()[:8]
            kw_slug = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in keywords[0].lower()) if keywords else "default"
            schedule_id = f"{retailer_slug}_{client_slug}_{kw_slug}_{dhash}"
            
            # Create schedule file path
            schedule_filename = f"{retailer_slug}__{client_slug}__{kw_slug}.json"
            client_schedule_file = os.path.join(schedules_dir, schedule_filename)
            
            # Create normalized config
            config = {
                "id": schedule_id,
                "retailer": retailer_slug,
                "client": selected_client,
                "keywords": keywords,
                "days": sorted(selected_days),
                "times": sorted(times_24h),
                "enabled": True,
                "tz": "",  # Optional timezone
                "created_at": now_iso,
                "updated_at": now_iso
            }
            
            # Save to file
            try:
                with open(client_schedule_file, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2)
                
                saved_count += 1
                if self.logger:
                    self.logger.info(f"Schedule saved to {client_schedule_file}")
            except (IOError, PermissionError) as e:
                self.notify(f"Failed to save schedule for {retailer_name}: {e}", "error")
                continue
        
        # After saving all retailer schedules, rebuild master index
        if saved_count > 0:
            try:
                from pathlib import Path
                import sys
                sys.path.insert(0, str(get_base_dir()))
                from schedules.schedules_lib import build_master_index
                
                master_path = build_master_index(Path(get_base_dir()))
                if self.logger:
                    self.logger.info(f"Master schedule index rebuilt: {master_path}")
                
                # Update status
                retailers_str = ", ".join(selected_retailers)
                self.status_label.config(text=f"✅ Saved {saved_count} schedule(s) for {selected_client} ({retailers_str})")
                self.notify(f"Saved {saved_count} schedule(s) for {retailers_str}", "success")
                
                # Notify user that scheduler will pick up changes on next tick
                self._activity_line(f"Scheduler will pick up new schedules within 1 minute", "info")
                
            except Exception as e:
                # Non-fatal - master index will be rebuilt on next daemon tick
                if self.logger:
                    self.logger.warning(f"Could not rebuild master index: {e}")
                print(f"Warning: Could not rebuild master index: {e}")
                import traceback
                traceback.print_exc()
                
            return True
        else:
            self.notify("Failed to save any schedules", "error")
            return False
    
    def clear_schedule(self):
        """Delete all schedule files for the currently selected client across all retailers."""
        selected_client = self.client_var.get()
        if not selected_client or selected_client == PLACEHOLDER:
            self.notify("Select a client/product first", "error")
            return
        
        # Find all schedule files for this client
        schedules_dir = os.path.join(get_base_dir(), "schedules")
        if not os.path.exists(schedules_dir):
            self.notify("No schedules directory found", "warn")
            return
        
        client_slug = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in selected_client.lower())
        
        matching_files = []
        for f in os.listdir(schedules_dir):
            if f.endswith('.json') and f'__{client_slug}__' in f:
                matching_files.append(f)
        
        if not matching_files:
            self.notify(f"No schedules found for '{selected_client}'", "warn")
            return
        
        # Confirm deletion
        retailers = set()
        for f in matching_files:
            parts = f.split('__')
            if parts:
                retailers.add(parts[0])
        
        confirm = messagebox.askyesno(
            "Clear Schedule",
            f"Delete {len(matching_files)} schedule(s) for '{selected_client}'?\n\n"
            f"Retailers: {', '.join(sorted(retailers))}\n\n"
            f"Files:\n" + "\n".join(f"  • {f}" for f in matching_files) +
            "\n\nThis cannot be undone."
        )
        if not confirm:
            return
        
        deleted = 0
        for f in matching_files:
            try:
                os.remove(os.path.join(schedules_dir, f))
                deleted += 1
            except Exception as e:
                print(f"Error deleting {f}: {e}")
        
        # Rebuild master index
        try:
            from pathlib import Path
            sys.path.insert(0, str(get_base_dir()))
            from schedules.schedules_lib import build_master_index
            build_master_index(Path(get_base_dir()))
        except Exception:
            pass
        
        self.notify(f"Deleted {deleted} schedule(s) for '{selected_client}'", "success")
        self.status_label.config(text=f"🗑 Cleared {deleted} schedule(s) for {selected_client}")
        self._activity_line(f"Cleared {deleted} schedule(s) for {selected_client}", "info")
    
    def any_conflicts_current_view(self) -> bool:
        """Return True if any time selector shows a conflict."""
        if not hasattr(self, 'time_widget_refs'):
            return False
        for tw in self.time_widget_refs:
            lbl = tw.get('conflict_label')
            if lbl and ("CONFLICT" in (lbl.cget("text") or "")):
                return True
        return False

    def update_save_button_state(self):
        """Enable Save only when there are no conflicts and a client is selected."""
        try:
            if hasattr(self, 'schedule_button'):
                selected_client = self.client_var.get()
                if selected_client and selected_client != PLACEHOLDER and not self.any_conflicts_current_view():
                    self.schedule_button.config(state="normal")
                else:
                    self.schedule_button.config(state="disabled")
        except Exception:
            pass
        
    # --- Theme persistence + menu ---

    def _ui_config_path(self):
        """Where we persist UI prefs."""
        cfg_dir = os.path.join(get_base_dir(), "config")
        os.makedirs(cfg_dir, exist_ok=True)
        return os.path.join(cfg_dir, "ui.json")

    def _load_ui_prefs(self):
        """Return {'ttk_theme': 'clam'|'aqua'|..., 'palette': 'light'|'dark'}"""
        try:
            with open(self._ui_config_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                "ttk_theme": data.get("ttk_theme"),
                "palette": data.get("palette", "light"),
            }
        except Exception:
            return {"ttk_theme": None, "palette": "light"}

    def _save_ui_prefs(self, ttk_theme=None, palette=None):
        """Merge & save current prefs."""
        cur = self._load_ui_prefs()
        if ttk_theme:
            cur["ttk_theme"] = ttk_theme
        if palette:
            cur["palette"] = palette
        try:
            with open(self._ui_config_path(), "w", encoding="utf-8") as f:
                json.dump(cur, f, indent=2)
        except Exception:
            pass

    def apply_ttk_theme(self, name: str):
        """Switch ttk base theme; reapply custom palette styles after."""
        try:
            # Safety: coerce aqua -> clam on macOS to avoid menu crash
            if sys.platform == 'darwin' and name == 'aqua':
                name = 'clam'
            if name not in self.style.theme_names():
                return False
            self.style.theme_use(name)
            # Update radio var and persist
            if hasattr(self, "ttk_theme_var"):
                self.ttk_theme_var.set(name)
            self._save_ui_prefs(ttk_theme=name, palette=self.theme)
            # Re-apply our color palette styling on top
            self.apply_theme(self.style, mode=self.theme)
            return True
        except Exception as e:
            print(f"Failed to apply ttk theme {name}: {e}")
            return False

    def apply_palette(self, palette: str):
        """Switch our light/dark palette; persist."""
        if palette not in ("light", "dark"):
            return
        self.theme = palette
        self._save_ui_prefs(ttk_theme=self.style.theme_use(), palette=palette)
        self.apply_theme(self.style, mode=self.theme)
        if hasattr(self, "palette_var"):
            self.palette_var.set(palette)

   

def main():
    _glog("main: start")
    try:
        # Prime Cocoa so Tk doesn't have to bootstrap NSApplication while AppleEvents are in flight
        try:
            _glog("main: priming NSApplication")
            from AppKit import NSApplication, NSApp, NSApplicationActivationPolicyRegular
            NSApplication.sharedApplication()
            # Don't set activation policy aggressively; Tk will manage windows. This call ensures NSApp exists.
            _glog("main: NSApplication primed")
        except Exception as e:
            _glog(f"main: NSApplication prime skipped: {e}")

        _glog("main: creating Tk()")
        root = tk.Tk()
        _glog("main: Tk() created")

        app = KeywordInputApp(root)
        _glog("main: app initialized")

        root.mainloop()
    except Exception as e:
        _glog(f"main: exception: {e}\n{traceback.format_exc()}")
        # Mirror to stdout for Terminal runs
        print(f"Error in main: {e}")
        traceback.print_exc()
        raise

if __name__ == "__main__":
    main()
