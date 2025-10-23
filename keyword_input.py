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
        
        # Load saved window geometry or use defaults
        self.geometry_file = os.path.join(get_base_dir(), "logs", "window_geometry.txt")
        self.state_file = os.path.join(get_base_dir(), "logs", "gui_state.json")
        saved_geometry = self.load_window_geometry()
        if saved_geometry:
            self.root.geometry(saved_geometry)
        else:
            self.root.geometry("900x1100")
        
        self.root.minsize(760, 1000)
        
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
        
        # Set up the main frame
        main_frame = ttk.Frame(root, padding=20, style='App.TFrame')
        main_frame.grid(row=0, column=0, sticky="nsew")
        main_frame.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)

        # Create a canvas for scrolling
        canvas = tk.Canvas(main_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        # Place canvas + scrollbar into the grid (this is what was missing)
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

        # Mouse wheel support (mac/Win/Linux)
        def _on_mousewheel(event):
            # Only scroll if mouse is over the canvas
            widget = event.widget
            # Don't scroll canvas if we're over a combobox, scrolledtext, or listbox (dropdown popup)
            if isinstance(widget, (ttk.Combobox, tk.Text, tk.Listbox)):
                return
            # Also check widget class name for ttk popdown listbox
            widget_class = widget.winfo_class()
            if widget_class in ('Listbox', 'TCombobox'):
                return
            if getattr(event, "num", None) == 4 or event.delta > 0:
                canvas.yview_scroll(-1, "units")
            else:
                canvas.yview_scroll(1, "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)  # Win/mac
        canvas.bind_all("<Button-4>", _on_mousewheel)   # Linux up
        canvas.bind_all("<Button-5>", _on_mousewheel)   # Linux down

        # Store references
        self.canvas = canvas
        self.scrollable_frame = scrollable_frame

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
        
        # --- Debug Options (restored) ---
        debug_frame = ttk.LabelFrame(scrollable_frame, text="Debug Options", style='Card.TLabelframe', padding=10)
        debug_frame.pack(fill=tk.X, padx=20, pady=(6, 10))

        self.debug_vars = {}
        self.debug_vars['break_on_px']        = tk.BooleanVar(value=False)
        self.debug_vars['break_on_blocked']   = tk.BooleanVar(value=False)
        self.debug_vars['line_trace']         = tk.BooleanVar(value=False)
        self.debug_vars['pdb_on_exception']   = tk.BooleanVar(value=True)
        self.debug_vars['open_run_folder']    = tk.BooleanVar(value=True)

        ttk.Checkbutton(debug_frame, text="Break on PX",        variable=self.debug_vars['break_on_px']).grid(row=0, column=0, sticky="w", padx=(0,20))
        ttk.Checkbutton(debug_frame, text="Break on /blocked",  variable=self.debug_vars['break_on_blocked']).grid(row=0, column=1, sticky="w", padx=(0,20))
        ttk.Checkbutton(debug_frame, text="Line trace (typing)",variable=self.debug_vars['line_trace']).grid(row=0, column=2, sticky="w", padx=(0,20))
        ttk.Checkbutton(debug_frame, text="PDB on exception",   variable=self.debug_vars['pdb_on_exception']).grid(row=0, column=3, sticky="w")

        paths_frame = ttk.Frame(debug_frame, style='Card.TFrame')
        paths_frame.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        paths_frame.columnconfigure(0, weight=1)
        paths_frame.columnconfigure(1, weight=1)

        ttk.Label(paths_frame, text="Profile dir:", style='TLabel').grid(row=0, column=0, sticky="w", pady=(0,5))
        self.profile_dir_var = tk.StringVar(value=os.path.expanduser("~/ChromeProfiles/walmart"))
        ttk.Entry(paths_frame, textvariable=self.profile_dir_var, width=50).grid(row=1, column=0, sticky="ew", padx=(0,10))

        ttk.Label(paths_frame, text="Output root:", style='TLabel').grid(row=0, column=1, sticky="w", pady=(0,5))
        self.output_root_var = tk.StringVar(value=os.path.expanduser("~/Documents/Amazon_Scrape/output/walmart"))
        ttk.Entry(paths_frame, textvariable=self.output_root_var, width=50).grid(row=1, column=1, sticky="ew")

        ttk.Checkbutton(debug_frame, text="Open run folder when done", variable=self.debug_vars['open_run_folder']).grid(row=2, column=0, columnspan=2, sticky="w", pady=(5,0))
        
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
        self.schedule_button.pack(side=tk.LEFT, padx=(0, 10))
        self.schedule_button.state(['disabled'])
        
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

        profile_dir = os.environ.get(adapter.profile_env) or os.environ.get("KROGER_PROFILE_DIR") or DEFAULT_PROFILE
        
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
        ctx.profile_dir = os.path.expanduser(self.profile_dir_var.get().strip())
        os.environ["WALMART_PROFILE_DIR"] = ctx.profile_dir  # optional: legacy paths still read env
        
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
                    cands = sorted([p for p in glob.glob(os.path.join(runs_dir, "run_results_*.json"))
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
                if (total_toa + total_sky) > 0:
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
        """Check if a specific time conflicts with existing schedules
        
        IMPORTANT: Checks across ALL retailers because they share the same Playwright browser.
        Multiple scrapers cannot run simultaneously regardless of retailer.
        """
        scheduled_times = self.get_all_scheduled_times(exclude_client)
        
        # Get current retailer (for debug logging only)
        retailer_slug = self._schedule_retailer_slug()
        
        # DEBUG: Log what we're checking
        print(f"[DEBUG] Checking conflicts for {retailer_slug} at {hour_24}:{minute:02d} on {days}")
        print(f"[DEBUG] Total scheduled times: {len(scheduled_times)}")
        print(f"[DEBUG] Sample scheduled times: {list(scheduled_times)[:5]}")
        
        for day in days:
            # Check for conflicts across ALL retailers (not just same retailer)
            # Format: (retailer, day, hour, minute)
            # We need to check if ANY retailer has this time scheduled
            for scheduled_tuple in scheduled_times:
                sched_retailer, sched_day, sched_hour, sched_minute = scheduled_tuple
                if sched_day == day and sched_hour == hour_24 and sched_minute == minute:
                    print(f"[DEBUG] CONFLICT FOUND: {scheduled_tuple} conflicts with {retailer_slug}/{day}/{hour_24}:{minute:02d}")
                    return True
        print(f"[DEBUG] No conflicts found")
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

        retailer_slug = self._schedule_retailer_slug()
        scheduled = self.get_all_scheduled_times(exclude_client=exclude_client)
        allowed = []
        for m in range(0, 60, 5):
            conflicted = any((retailer_slug, day, hour_24, m) in scheduled for day in days)
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
                for day in selected_days:
                    if (retailer_slug, day, h24, m) in scheduled:
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
        """Manually stop the daemon (called by button)"""
        if not self.daemon_status:
            self.notify("Daemon is not running", "info")
            return
        
        try:
            # Find scheduler_daemon.py process
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            daemon_pid = None
            for line in result.stdout.splitlines():
                if "scheduler_daemon.py" in line and "grep" not in line:
                    parts = line.split()
                    if len(parts) > 1:
                        daemon_pid = parts[1]
                        break
            
            if daemon_pid and daemon_pid.isdigit():
                # Send SIGTERM to gracefully stop
                os.kill(int(daemon_pid), 15)
                self.notify("Stopping daemon...", "info")
                
                # Wait a moment then check status
                self.root.after(1500, lambda: self.refresh_daemon_status_manual())
            else:
                self.notify("Could not find daemon process", "error")
                
        except ProcessLookupError:
            self.notify("Daemon process not found (already stopped?)", "warn")
            self.refresh_daemon_status_manual()
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
        
        # Load all schedules
        def load_schedules():
            """Load all schedule configs using shared library"""
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
                    if not sched.enabled:
                        continue
                    
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
                                    "day": day.capitalize(),
                                    "retailer": sched.retailer,
                                    "client": sched.client,
                                    "keywords": keywords_str
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
                                            "keywords": keywords_str
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
                                            "keywords": keywords_str
                                        })
                        except Exception as e:
                            print(f"Error loading {config_file}: {e}")
            
            return schedules
        
        # Populate filters and tree
        def refresh_display():
            """Refresh the tree view as a matrix: rows=time slots, columns=retailers"""
            # Clear tree
            for item in tree.get_children():
                tree.delete(item)
            
            # Get filter values
            client_filter_val = client_var.get()
            day_filter_val = day_var.get()
            show_empty = show_empty_var.get()
            
            # Load all schedules
            all_schedules = load_schedules()
            
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
            
            # Build matrix: {(day, time, retailer): [clients]}
            matrix = {}
            for s in all_schedules:
                key = (s["day"], s["time"], s["retailer"])
                if key not in matrix:
                    matrix[key] = []
                matrix[key].append(s["client"])
            
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
                    
                    # Build row values
                    row_values = [time_slot]
                    for retailer in all_retailers:
                        key = (day, time_slot, retailer)
                        if key in matrix:
                            clients = matrix[key]
                            row_values.append(", ".join(clients))
                            occupied_count += len(clients)
                        else:
                            row_values.append("—" if show_empty else "")
                    
                    # Insert row
                    tags = ("empty",) if not has_assignment else ()
                    tree.insert(day_node, "end", values=row_values, tags=tags)
            
            # Configure tags
            tree.tag_configure("day_header", font=("Inter", 11, "bold"), background="#e0e0e0")
            tree.tag_configure("empty", foreground="gray")
            
            # Update count
            if show_empty:
                count_label.config(text=f"Showing {total_slots} time slots with {occupied_count} scheduled runs")
            else:
                count_label.config(text=f"Showing {occupied_count} scheduled runs")
        
        # Bind filter changes
        retailer_var.trace("w", lambda *args: refresh_display())
        client_var.trace("w", lambda *args: refresh_display())
        day_var.trace("w", lambda *args: refresh_display())
        show_empty_var.trace("w", lambda *args: refresh_display())
        
        # Count label at bottom
        count_label = ttk.Label(main_frame, text="", font=("Inter", 10))
        count_label.pack(pady=(5, 0))
        
        # Refresh button
        ttk.Button(
            main_frame,
            text="🔄 Refresh",
            command=refresh_display
        ).pack(pady=5)
        
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
            
            # Default values based on common run times with conflict checking
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
        
        # Load saved times if available - check if we have a selected client
        selected_client = self.client_var.get() if hasattr(self, 'client_var') else None
        if selected_client and selected_client != PLACEHOLDER:
            self.schedule_config = self.load_schedule_config(selected_client)
            self.load_saved_times()
        else:
            # No client selected, just use defaults (already set above)
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
