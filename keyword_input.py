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
        self.root.geometry("720x900")
        self.root.minsize(720, 800)
        
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
        # Build menubar so you can change themes from the macOS top bar
        self._build_menubar()
        
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
        
        # Set up the main frame
        main_frame = ttk.Frame(root, padding=20, style='App.TFrame')
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Client/Product field + New button
        client_frame = ttk.Frame(main_frame, style='Card.TFrame')
        client_frame.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(client_frame, text="Client/Product:", style='TLabel').pack(side=tk.LEFT)

        # Alphabetize clients
        clients = sorted(self.client_history.keys(), key=str.lower)

        self.client_var = tk.StringVar(value=PLACEHOLDER)

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
        retailer_frame = ttk.LabelFrame(main_frame, text="Select Retailers", style='Card.TLabelframe', padding=10)
        retailer_frame.pack(fill=tk.X, padx=20, pady=(10, 5))
        
        # Determine which retailers are unavailable (not registered)
        all_names = ["Amazon", "Walmart", "Kroger", "Instacart", "Albertsons", "Doordash", "gopuff", "Target", "Hyvee", "Meijer", "Ahold"]
        unavailable = {name for name in all_names if name.lower() not in self._retailer_by_name_ci}
        
        self.retailer_picker = RetailerPicker(retailer_frame, unavailable=unavailable, columns=4)
        self.retailer_picker.pack(fill=tk.X, padx=5, pady=5)
        
        # Pre-select Kroger and Instacart by default
        if "Kroger" in self.retailer_picker.vars:
            self.retailer_picker.vars["Kroger"].set(True)
        if "Instacart" in self.retailer_picker.vars:
            self.retailer_picker.vars["Instacart"].set(True)
        
        # Instructions
        instructions = ttk.Label(
            main_frame,
            text="Enter keywords to scrape (one per line):",
            style='Body.TLabel'
        )
        instructions.pack(anchor="w", pady=(0, 10))
        
        # Keyword input area
        # Get current theme colors
        palette = PALETTE[self.theme]
        
        self.keyword_input = scrolledtext.ScrolledText(main_frame, height=8)
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
        schedule_frame = ttk.Labelframe(main_frame, text="Schedule Settings", padding=10, style='Card.TLabelframe')
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
        
        
        # Buttons frame
        button_frame = ttk.Frame(main_frame, style='App.TFrame')
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 10))
        
        # Start scraping button
        self.scrape_button = ttk.Button(
            button_frame,
            text="Start Scraping",
            command=self.start_scraping,
            style='Primary.TButton'
        )
        self.scrape_button.pack(side=tk.LEFT, padx=(0, 10))

        # Clear button
        self.clear_button = ttk.Button(
            button_frame,
            text="Clear",
            command=self.clear_keywords,
            style='Danger.TButton'
        )
        self.clear_button.pack(side=tk.LEFT)
        
        # Status label with daemon status
        daemon_text = "✅ Daemon running" if self.daemon_status else "⚠️ Daemon stopped"
        self.status_label = ttk.Label(
            main_frame,
            text=f"Ready to scrape | {daemon_text}",
            style='Body.TLabel'
        )
        self.status_label.pack(side=tk.BOTTOM, anchor="w", pady=(0, 10))
        
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
            messagebox.showerror("Error", "Please select a client/product first")
            return
            
        # Create sanitized folder name (remove special characters)
        folder_name = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in client_type)
        
        # Get keywords from the input area
        keywords_text = self.keyword_input.get(1.0, tk.END).strip()
        if not keywords_text:
            messagebox.showerror("Error", "Please enter some keywords")
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
            messagebox.showerror("Error", f"Failed to save keywords: {str(e)}")
    
    def run_scraper(self, keywords):
        """Run the scraper with the given keywords and then post-process images."""
        try:
            import glob

            # Get selected retailers
            selected_retailers = self.retailer_picker.get_selected()
            if not selected_retailers:
                self.log("⚠️ Please select at least one retailer.")
                messagebox.showwarning("No Retailers Selected", "Please select at least one retailer to scrape.")
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
                        self.log(f"⚠️ No adapter slug for '{retailer_name}' (skipping)")
                        continue
                    
                    adapter = get_retailer_adapter(slug)
                    self.log(f"➡️ [{retailer_name}] resolved to slug '{slug}', adapter={getattr(adapter, '__module__', adapter)}")
                    
                    self.log(f"➡️ [{retailer_name}] entering _run_scraper_for_retailer")
                    self._run_scraper_for_retailer(retailer_name, slug, adapter, folder_name, keywords)
                    self.log(f"✅ [{retailer_name}] _run_scraper_for_retailer returned")
                except Exception as e:
                    self.log(f"❌ [{retailer_name}] failed: {e}")
                    import traceback
                    self.log(traceback.format_exc())
                    
            self.log(f"\n{'='*60}")
            self.log(f"✅ Completed scraping for {len(selected_retailers)} retailer(s)")
            self.log(f"{'='*60}\n")
            
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

            max_retries = 3
            retry_count = 0
            scraped = False

            while retry_count < max_retries and not scraped:
                if retry_count > 0:
                    retry_msg = f"Retry attempt {retry_count}/{max_retries} for '{keyword}'..."
                    if progress_label.winfo_exists():
                        progress_label.config(text=retry_msg)
                    self.status_label.config(text=retry_msg)
                    popup.update()
                    self.root.update()
                    time.sleep(1.5)

                try:
                    # Use adapter for all retailers
                    ok = adapter.search_and_capture(keyword, ctx)
                    if ok:
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
                    else:
                        raise RuntimeError("search_and_capture returned False")

                except Exception as e:
                    retry_count += 1
                    if retry_count >= max_retries:
                        err_text = f"Failed to scrape '{keyword}' after {max_retries} attempts: {e}"
                        if progress_label.winfo_exists():
                            progress_label.config(text=f"Error: {err_text}")
                        popup.update()
                        messagebox.showerror("Error", err_text)
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

        max_retries = 3
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
                    
                    # Use adapter to extract images
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
                    messagebox.showerror("Error", error_msg)
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
                messagebox.showinfo("Success", result_msg)
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
                messagebox.showwarning("Extraction incomplete", warn)
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
        
        output_path = os.path.join(get_base_dir(), "output")
        if not os.path.exists(output_path):
            return scheduled_times

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
        """Check if a specific time conflicts with existing schedules"""
        scheduled_times = self.get_all_scheduled_times(exclude_client)
        
        # Get current retailer
        retailer_slug = self._schedule_retailer_slug()
        
        for day in days:
            # Check for conflicts in the same retailer
            if (retailer_slug, day, hour_24, minute) in scheduled_times:
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
    
    def on_closing(self):
        """Handle window closing - actually quit the application"""
        # Clean up and quit properly
        try:
            os.remove('/tmp/kroger_toa_scraper.pid')
        except:
            pass
        self.root.quit()
        self.root.destroy()
    
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
            # PID path supports retailer namespacing if RETAILER is set
            pid_path = os.path.join(base, "logs", retailer, "scheduler.pid") if retailer else os.path.join(base, "logs", "scheduler.pid")

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
                conflict_label.config(text="")
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

            # Conflict indicator label
            conflict_label = ttk.Label(time_frame, text="", style='Body.TLabel')
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
        """Load schedule configuration from file"""
        default_config = {
            "runs": 3, 
            "times": [("8", "00", "AM"), ("12", "00", "PM"), ("4", "00", "PM")],
            "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        }
        
        # If client is specified, try to load client-specific config
        if client:
            folder_name = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in client)
            # Try retailer-scoped path first (new), then fall back to old path
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
            messagebox.showerror("Error", "Please select a client/product before saving schedule")
            return False

        # Detect conflicts
        if self.schedule_has_conflicts():
            messagebox.showerror("Conflicts", "Selected times conflict with other clients. Please adjust before saving.")
            return False
            
        # Check for visual conflicts (should be redundant with above check)
        if self.any_conflicts_current_view():
            if messagebox.askyesno("Conflicts detected",
                               "Some time selections conflict with other clients.\n"
                               "Auto-adjust to the next available times?"):
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
                    messagebox.showerror("Conflicts remain", "Could not resolve all conflicts automatically.")
                    return False
            else:
                messagebox.showwarning("Conflicts", "Resolve schedule conflicts before saving.")
                return False
            
        # Create client-specific schedule file path
        folder_name = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in selected_client)
        
        # Include retailer in the path
        retailer_slug = self._schedule_retailer_slug()
        client_schedule_file = os.path.join(get_base_dir(), "output", retailer_slug, folder_name, "schedule_config.json")
        
        # Get current times
        times = []
        for hour_var, minute_var, ampm_var in self.time_vars:
            times.append((hour_var.get(), minute_var.get(), ampm_var.get()))
        
        # Get selected days
        selected_days = []
        for day, var in self.day_vars.items():
            if var.get():
                selected_days.append(day)
        
        # Create config
        config = {
            "runs": self.runs_var.get(),
            "times": times,
            "days": selected_days,
            "client": selected_client,  # Store client name in config
            "retailer": retailer_slug  # Include retailer in the config
        }
        
        # Save to file
        try:
            os.makedirs(os.path.dirname(client_schedule_file), exist_ok=True)
            with open(client_schedule_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            
            # Update instance variables
            self.schedule_file = client_schedule_file
            self.schedule_config = config
            self.status_label.config(text=f"✅ Schedule saved for {selected_client} - daemon will handle execution")
        
            if self.logger:
                self.logger.info(f"Schedule configuration saved for {selected_client}")
                
            return True
        except (IOError, PermissionError) as e:
            messagebox.showerror("Error", f"Failed to save schedule: {str(e)}")
            self.status_label.config(text=f"Error saving schedule: {str(e)}")
        except json.JSONDecodeError as e:
            messagebox.showerror("Error", f"Failed to encode schedule data: {str(e)}")
            self.status_label.config(text=f"Error encoding schedule data: {str(e)}")
            return False
        return True
    
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

    def _build_menubar(self):
        # Build the submenus first (theme_menu, palette_menu) using self.root as parent
        theme_menu = tk.Menu(self.root, tearoff=0)
        current = self.style.theme_use()
        self.ttk_theme_var = tk.StringVar(value=current)
        names = list(self.style.theme_names())
        if sys.platform == 'darwin' and 'aqua' in names:
            names.remove('aqua')
        for name in names:
            theme_menu.add_radiobutton(
                label=name, value=name, variable=self.ttk_theme_var,
                command=lambda n=name: self.apply_ttk_theme(n),
            )

        palette_menu = tk.Menu(self.root, tearoff=0)
        self.palette_var = tk.StringVar(value=self.theme)
        palette_menu.add_radiobutton(label="Light", value="light", variable=self.palette_var,
                                    command=lambda: self.apply_palette("light"))
        palette_menu.add_radiobutton(label="Dark", value="dark", variable=self.palette_var,
                                    command=lambda: self.apply_palette("dark"))

        # If guard is set, DO NOT attach native menubar; install inline button instead
        if os.environ.get("RAM_NO_NATIVE_MENUBAR") == "1":
            inline = ttk.Menubutton(self.root, text="View")
            inline_menu = tk.Menu(inline, tearoff=0)
            inline_menu.add_cascade(label="Theme", menu=theme_menu)
            inline_menu.add_cascade(label="Palette", menu=palette_menu)
            inline["menu"] = inline_menu
            inline.pack(anchor="ne", padx=8, pady=6)
            return  # IMPORTANT: do not call root.config(menu=...) below

        # Native menubar (only when guard is not set)
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(self.root, tearoff=0)
        file_menu.add_command(label="Quit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        view_menu = tk.Menu(self.root, tearoff=0)
        view_menu.add_cascade(label="Theme", menu=theme_menu)
        view_menu.add_cascade(label="Palette", menu=palette_menu)
        menubar.add_cascade(label="View", menu=view_menu)

        self.root.config(menu=menubar)   

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
