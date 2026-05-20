#!/usr/bin/env python3
"""
Scheduler Tab for the GUI - Complete scheduler management interface
"""
import os
import sys
import json
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from pathlib import Path
from datetime import datetime
import subprocess
import threading

def get_base_dir():
    """Get base directory for the project"""
    shared = os.getenv("SCRAPER_HOME")
    if shared and shared.strip():
        return os.path.abspath(shared)
    if getattr(sys, 'frozen', False):
        return os.path.expanduser("~/Documents/Amazon_Scrape")
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class SchedulerTab:
    """Complete scheduler management interface for the GUI"""
    
    def __init__(self, notebook, app_instance):
        """
        Initialize the Scheduler tab.
        
        Args:
            notebook: The ttk.Notebook widget to add the tab to
            app_instance: Reference to the main KeywordInputApp instance
        """
        self.notebook = notebook
        self.app = app_instance
        self.base_dir = Path(get_base_dir())
        
        # Create the tab frame
        self.frame = ttk.Frame(notebook, padding=10, style='App.TFrame')
        self.frame.rowconfigure(0, weight=1)
        self.frame.columnconfigure(0, weight=1)
        notebook.add(self.frame, text="  Scheduler  ")
        
        # Create scrollable canvas
        canvas = tk.Canvas(self.frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        
        scrollable = ttk.Frame(canvas)
        self._window = canvas.create_window((0, 0), window=scrollable, anchor="nw")
        
        def _on_canvas_configure(e):
            canvas.itemconfigure(self._window, width=e.width)
        canvas.bind("<Configure>", _on_canvas_configure)
        
        def _on_inner_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        scrollable.bind("<Configure>", _on_inner_configure)
        
        self.canvas = canvas
        self.scrollable = scrollable
        
        # Build the UI
        self._build_ui()
        
        # Start auto-refresh
        self._auto_refresh()
    
    def _build_ui(self):
        """Build the complete scheduler UI"""
        # Header
        header_frame = ttk.Frame(self.scrollable, style='Card.TFrame')
        header_frame.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(
            header_frame,
            text="Scheduler Management",
            font=("Inter", 16, "bold"),
            style='TLabel'
        ).pack(anchor="w")
        
        ttk.Label(
            header_frame,
            text="Control and monitor automated scraping schedules",
            style='Body.TLabel'
        ).pack(anchor="w", pady=(5, 0))
        
        # Status Section
        self._build_status_section()
        
        # Control Buttons
        self._build_control_section()
        
        # Active Schedules
        self._build_schedules_section()
        
        # Audit Log Viewer
        self._build_audit_section()
        
        # Unknown Brands Analysis
        self._build_brands_section()
    
    def _build_status_section(self):
        """Build scheduler status display"""
        status_frame = ttk.LabelFrame(
            self.scrollable,
            text="Scheduler Status",
            padding=15,
            style='Card.TLabelframe'
        )
        status_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Status indicators
        indicators_frame = ttk.Frame(status_frame, style='Card.TFrame')
        indicators_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Daemon status
        self.daemon_status_label = ttk.Label(
            indicators_frame,
            text="⚪ Checking...",
            font=("Inter", 12, "bold"),
            style='TLabel'
        )
        self.daemon_status_label.pack(side=tk.LEFT, padx=(0, 20))
        
        # Active schedules count
        self.schedules_count_label = ttk.Label(
            indicators_frame,
            text="Schedules: --",
            style='TLabel'
        )
        self.schedules_count_label.pack(side=tk.LEFT, padx=(0, 20))
        
        # Last run time
        self.last_run_label = ttk.Label(
            indicators_frame,
            text="Last run: --",
            style='TLabel'
        )
        self.last_run_label.pack(side=tk.LEFT)
        
        # Details text area
        self.status_text = scrolledtext.ScrolledText(
            status_frame,
            height=4,
            wrap="word",
            font=("Inter", 10)
        )
        self.status_text.pack(fill=tk.X, pady=(10, 0))
        self.status_text.config(state="disabled")
    
    def _build_control_section(self):
        """Build scheduler control buttons"""
        control_frame = ttk.LabelFrame(
            self.scrollable,
            text="Controls",
            padding=15,
            style='Card.TLabelframe'
        )
        control_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Main controls
        main_controls = ttk.Frame(control_frame, style='Card.TFrame')
        main_controls.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(
            main_controls,
            text="▶️ Start Scheduler",
            command=self._start_scheduler,
            style='Primary.TButton',
            width=18
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(
            main_controls,
            text="⏹️ Stop Scheduler",
            command=self._stop_scheduler,
            width=18
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(
            main_controls,
            text="🔄 Restart",
            command=self._restart_scheduler,
            width=12
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(
            main_controls,
            text="🔃 Refresh Status",
            command=self._refresh_status,
            width=15
        ).pack(side=tk.LEFT)
        
        # Secondary controls
        secondary_controls = ttk.Frame(control_frame, style='Card.TFrame')
        secondary_controls.pack(fill=tk.X)
        
        ttk.Button(
            secondary_controls,
            text="📋 View Logs",
            command=self._view_logs,
            width=15
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(
            secondary_controls,
            text="📊 Run History",
            command=self._view_history,
            width=15
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(
            secondary_controls,
            text="⚙️ Edit Schedules",
            command=self._edit_schedules,
            width=15
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(
            secondary_controls,
            text="📂 Open Folder",
            command=self._open_scheduler_folder,
            width=15
        ).pack(side=tk.LEFT)
    
    def _build_schedules_section(self):
        """Build active schedules display"""
        schedules_frame = ttk.LabelFrame(
            self.scrollable,
            text="Active Schedules",
            padding=15,
            style='Card.TLabelframe'
        )
        schedules_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        # Filter controls
        filter_frame = ttk.Frame(schedules_frame, style='Card.TFrame')
        filter_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(filter_frame, text="Filter:", style='TLabel').pack(side=tk.LEFT)
        
        self.filter_var = tk.StringVar(value="all")
        filter_combo = ttk.Combobox(
            filter_frame,
            textvariable=self.filter_var,
            values=["all", "enabled", "disabled", "Proactiv", "Garanimals", "Community Coffee", "MilkPEP"],
            width=20,
            state="readonly"
        )
        filter_combo.pack(side=tk.LEFT, padx=(10, 0))
        filter_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_schedules())
        
        ttk.Button(
            filter_frame,
            text="🔃 Refresh",
            command=self._refresh_schedules,
            width=10
        ).pack(side=tk.RIGHT)
        
        # Schedules tree
        tree_frame = ttk.Frame(schedules_frame, style='Card.TFrame')
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        # Scrollbars
        tree_scroll_y = ttk.Scrollbar(tree_frame, orient="vertical")
        tree_scroll_x = ttk.Scrollbar(tree_frame, orient="horizontal")
        
        self.schedules_tree = ttk.Treeview(
            tree_frame,
            columns=("retailer", "client", "keywords", "times", "days", "enabled"),
            show="headings",
            yscrollcommand=tree_scroll_y.set,
            xscrollcommand=tree_scroll_x.set,
            height=10
        )
        
        tree_scroll_y.config(command=self.schedules_tree.yview)
        tree_scroll_x.config(command=self.schedules_tree.xview)
        
        # Column headers
        self.schedules_tree.heading("retailer", text="Retailer")
        self.schedules_tree.heading("client", text="Client")
        self.schedules_tree.heading("keywords", text="Keywords")
        self.schedules_tree.heading("times", text="Times")
        self.schedules_tree.heading("days", text="Days")
        self.schedules_tree.heading("enabled", text="Status")
        
        # Column widths
        self.schedules_tree.column("retailer", width=100)
        self.schedules_tree.column("client", width=120)
        self.schedules_tree.column("keywords", width=200)
        self.schedules_tree.column("times", width=150)
        self.schedules_tree.column("days", width=100)
        self.schedules_tree.column("enabled", width=80)
        
        # Pack tree and scrollbars
        self.schedules_tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll_y.grid(row=0, column=1, sticky="ns")
        tree_scroll_x.grid(row=1, column=0, sticky="ew")
        
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        
        # Context menu
        self.schedules_tree.bind("<Button-2>", self._show_schedule_context_menu)  # Right-click on Mac
        self.schedules_tree.bind("<Button-3>", self._show_schedule_context_menu)  # Right-click on others
    
    def _build_audit_section(self):
        """Build audit log viewer"""
        audit_frame = ttk.LabelFrame(
            self.scrollable,
            text="Recent Audit Results",
            padding=15,
            style='Card.TLabelframe'
        )
        audit_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Controls
        audit_controls = ttk.Frame(audit_frame, style='Card.TFrame')
        audit_controls.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(audit_controls, text="Show last:", style='TLabel').pack(side=tk.LEFT)
        
        self.audit_limit_var = tk.IntVar(value=10)
        ttk.Spinbox(
            audit_controls,
            from_=5,
            to=50,
            width=8,
            textvariable=self.audit_limit_var,
            command=self._refresh_audits
        ).pack(side=tk.LEFT, padx=(10, 0))
        
        ttk.Button(
            audit_controls,
            text="🔃 Refresh",
            command=self._refresh_audits,
            width=10
        ).pack(side=tk.RIGHT)
        
        # Audit log display
        self.audit_text = scrolledtext.ScrolledText(
            audit_frame,
            height=8,
            wrap="word",
            font=("Courier", 10)
        )
        self.audit_text.pack(fill=tk.X)
        self.audit_text.config(state="disabled")
    
    def _build_brands_section(self):
        """Build unknown brands analysis section"""
        brands_frame = ttk.LabelFrame(
            self.scrollable,
            text="Unknown Brands Analysis",
            padding=15,
            style='Card.TLabelframe'
        )
        brands_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Info text
        ttk.Label(
            brands_frame,
            text="Analyze recent scrapes to identify patterns in unknown brand detections",
            style='Body.TLabel'
        ).pack(anchor="w", pady=(0, 10))
        
        # Controls
        brands_controls = ttk.Frame(brands_frame, style='Card.TFrame')
        brands_controls.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(brands_controls, text="Analyze last:", style='TLabel').pack(side=tk.LEFT)
        
        self.brands_limit_var = tk.IntVar(value=100)
        ttk.Spinbox(
            brands_controls,
            from_=50,
            to=500,
            increment=50,
            width=8,
            textvariable=self.brands_limit_var
        ).pack(side=tk.LEFT, padx=(10, 0))
        
        ttk.Label(brands_controls, text="runs", style='TLabel').pack(side=tk.LEFT, padx=(5, 0))
        
        ttk.Button(
            brands_controls,
            text="🔍 Analyze",
            command=self._analyze_brands,
            style='Primary.TButton',
            width=12
        ).pack(side=tk.RIGHT)
        
        # Results display
        self.brands_text = scrolledtext.ScrolledText(
            brands_frame,
            height=10,
            wrap="word",
            font=("Courier", 10)
        )
        self.brands_text.pack(fill=tk.X)
        self.brands_text.config(state="disabled")
    
    # ===== Status Methods =====
    
    def _refresh_status(self):
        """Refresh scheduler status"""
        try:
            # Check if daemon is running
            lock_file = self.base_dir / "logs" / "scheduler.lock"
            pid_file = self.base_dir / "logs" / "scheduler.pid"
            
            is_running = lock_file.exists()
            
            if is_running:
                self.daemon_status_label.config(text="🟢 Running", foreground="green")
                
                # Get PID
                if pid_file.exists():
                    pid = pid_file.read_text().strip()
                    status_msg = f"Scheduler daemon is running (PID: {pid})\n"
                else:
                    status_msg = "Scheduler daemon is running\n"
            else:
                self.daemon_status_label.config(text="🔴 Stopped", foreground="red")
                status_msg = "Scheduler daemon is not running\n"
            
            # Count active schedules
            schedules_dir = self.base_dir / "schedules"
            if schedules_dir.exists():
                enabled_count = 0
                total_count = 0
                for schedule_file in schedules_dir.glob("*.json"):
                    if schedule_file.name in ["master_schedule.json", "frontpage_capture.json"]:
                        continue
                    total_count += 1
                    try:
                        with open(schedule_file, 'r') as f:
                            config = json.load(f)
                            if config.get("enabled", False):
                                enabled_count += 1
                    except:
                        pass
                
                self.schedules_count_label.config(text=f"Schedules: {enabled_count}/{total_count} enabled")
                status_msg += f"Active schedules: {enabled_count} of {total_count}\n"
            
            # Check last run time from logs
            log_file = self.base_dir / "logs" / "scheduler_daemon.log"
            if log_file.exists():
                try:
                    # Read last few lines
                    with open(log_file, 'r') as f:
                        lines = f.readlines()
                        for line in reversed(lines[-100:]):
                            if "SUCCESS" in line or "SCRAPE_COMPLETE" in line:
                                # Extract timestamp
                                parts = line.split(" - ")
                                if len(parts) > 0:
                                    timestamp = parts[0]
                                    self.last_run_label.config(text=f"Last run: {timestamp}")
                                    status_msg += f"Last successful run: {timestamp}\n"
                                break
                except:
                    pass
            
            # Update status text
            self.status_text.config(state="normal")
            self.status_text.delete("1.0", tk.END)
            self.status_text.insert("1.0", status_msg)
            self.status_text.config(state="disabled")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to refresh status: {e}")
    
    def _auto_refresh(self):
        """Auto-refresh status every 30 seconds"""
        self._refresh_status()
        self._refresh_schedules()
        self.frame.after(30000, self._auto_refresh)
    
    # ===== Control Methods =====
    
    def _start_scheduler(self):
        """Start the scheduler daemon"""
        try:
            # Check if already running
            lock_file = self.base_dir / "logs" / "scheduler.lock"
            if lock_file.exists():
                messagebox.showinfo("Info", "Scheduler is already running")
                return
            
            # Start with caffeinate
            start_script = self.base_dir / "start_scheduler_caffeinated.sh"
            if not start_script.exists():
                messagebox.showerror("Error", f"Start script not found: {start_script}")
                return
            
            # Run in background
            def run_scheduler():
                try:
                    subprocess.Popen(
                        [str(start_script)],
                        cwd=str(self.base_dir),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True
                    )
                except Exception as e:
                    self.app.root.after(0, lambda: messagebox.showerror("Error", f"Failed to start scheduler: {e}"))
            
            threading.Thread(target=run_scheduler, daemon=True).start()
            
            # Wait a moment then refresh
            self.frame.after(2000, self._refresh_status)
            messagebox.showinfo("Success", "Scheduler started with caffeinate (keeps MacBook awake)")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start scheduler: {e}")
    
    def _stop_scheduler(self):
        """Stop the scheduler daemon"""
        try:
            # Remove lock file
            lock_file = self.base_dir / "logs" / "scheduler.lock"
            if lock_file.exists():
                lock_file.unlink()
            
            # Kill scheduler process
            try:
                subprocess.run(["pkill", "-f", "scheduler_entry.py"], check=False)
                subprocess.run(["pkill", "-f", "scheduler_daemon.py"], check=False)
            except:
                pass
            
            # Wait a moment then refresh
            self.frame.after(1000, self._refresh_status)
            messagebox.showinfo("Success", "Scheduler stopped")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to stop scheduler: {e}")
    
    def _restart_scheduler(self):
        """Restart the scheduler"""
        self._stop_scheduler()
        self.frame.after(2000, self._start_scheduler)
    
    def _view_logs(self):
        """Open scheduler logs in a new window"""
        try:
            log_file = self.base_dir / "logs" / "scheduler_daemon.log"
            if not log_file.exists():
                messagebox.showinfo("Info", "No log file found")
                return
            
            # Open in default text editor
            if sys.platform == 'darwin':
                subprocess.run(["open", str(log_file)])
            elif sys.platform == 'linux':
                subprocess.run(["xdg-open", str(log_file)])
            else:
                subprocess.run(["notepad", str(log_file)])
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open logs: {e}")
    
    def _view_history(self):
        """View run history"""
        # Delegate to main app's method if it exists
        if hasattr(self.app, 'view_run_history'):
            self.app.view_run_history()
        else:
            messagebox.showinfo("Info", "Run history viewer not implemented")
    
    def _edit_schedules(self):
        """Open schedules folder"""
        try:
            schedules_dir = self.base_dir / "schedules"
            if sys.platform == 'darwin':
                subprocess.run(["open", str(schedules_dir)])
            elif sys.platform == 'linux':
                subprocess.run(["xdg-open", str(schedules_dir)])
            else:
                subprocess.run(["explorer", str(schedules_dir)])
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open schedules folder: {e}")
    
    def _open_scheduler_folder(self):
        """Open scheduler output folder"""
        try:
            output_dir = self.base_dir / "output"
            if sys.platform == 'darwin':
                subprocess.run(["open", str(output_dir)])
            elif sys.platform == 'linux':
                subprocess.run(["xdg-open", str(output_dir)])
            else:
                subprocess.run(["explorer", str(output_dir)])
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open folder: {e}")
    
    # ===== Schedules Methods =====
    
    def _refresh_schedules(self):
        """Refresh the schedules tree"""
        try:
            # Clear existing items
            for item in self.schedules_tree.get_children():
                self.schedules_tree.delete(item)
            
            # Load schedules
            schedules_dir = self.base_dir / "schedules"
            if not schedules_dir.exists():
                return
            
            filter_value = self.filter_var.get()
            
            for schedule_file in sorted(schedules_dir.glob("*.json")):
                if schedule_file.name in ["master_schedule.json", "frontpage_capture.json"]:
                    continue
                
                try:
                    with open(schedule_file, 'r') as f:
                        config = json.load(f)
                    
                    retailer = config.get("retailer", "")
                    client = config.get("client", "")
                    keywords = config.get("keywords", [])
                    times = config.get("times", [])
                    days = config.get("days", [])
                    enabled = config.get("enabled", False)
                    
                    # Apply filter
                    if filter_value == "enabled" and not enabled:
                        continue
                    elif filter_value == "disabled" and enabled:
                        continue
                    elif filter_value not in ["all", "enabled", "disabled"] and client != filter_value:
                        continue
                    
                    # Format display values
                    keywords_str = f"{len(keywords)} keywords"
                    times_str = ", ".join(times[:3])
                    if len(times) > 3:
                        times_str += f" +{len(times)-3}"
                    days_str = f"{len(days)} days"
                    status_str = "✅ Enabled" if enabled else "❌ Disabled"
                    
                    # Add to tree
                    self.schedules_tree.insert(
                        "",
                        "end",
                        values=(retailer, client, keywords_str, times_str, days_str, status_str),
                        tags=("enabled" if enabled else "disabled",)
                    )
                    
                except Exception as e:
                    print(f"Error loading {schedule_file}: {e}")
            
            # Configure tags
            self.schedules_tree.tag_configure("enabled", foreground="green")
            self.schedules_tree.tag_configure("disabled", foreground="gray")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to refresh schedules: {e}")
    
    def _show_schedule_context_menu(self, event):
        """Show context menu for schedule"""
        # Select item under cursor
        item = self.schedules_tree.identify_row(event.y)
        if item:
            self.schedules_tree.selection_set(item)
            
            # Create context menu
            menu = tk.Menu(self.frame, tearoff=0)
            menu.add_command(label="Enable", command=lambda: self._toggle_schedule(item, True))
            menu.add_command(label="Disable", command=lambda: self._toggle_schedule(item, False))
            menu.add_separator()
            menu.add_command(label="View Details", command=lambda: self._view_schedule_details(item))
            
            menu.post(event.x_root, event.y_root)
    
    def _toggle_schedule(self, item, enabled):
        """Toggle schedule enabled/disabled"""
        try:
            values = self.schedules_tree.item(item)["values"]
            retailer = values[0]
            client = values[1]
            
            # Find matching schedule file
            schedules_dir = self.base_dir / "schedules"
            for schedule_file in schedules_dir.glob(f"{retailer}__{client.lower().replace(' ', '_')}__*.json"):
                with open(schedule_file, 'r') as f:
                    config = json.load(f)
                
                config["enabled"] = enabled
                
                with open(schedule_file, 'w') as f:
                    json.dump(config, f, indent=2)
                
                self._refresh_schedules()
                messagebox.showinfo("Success", f"Schedule {'enabled' if enabled else 'disabled'}")
                return
            
            messagebox.showerror("Error", "Schedule file not found")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to toggle schedule: {e}")
    
    def _view_schedule_details(self, item):
        """View detailed schedule information"""
        try:
            values = self.schedules_tree.item(item)["values"]
            retailer = values[0]
            client = values[1]
            
            # Find matching schedule file
            schedules_dir = self.base_dir / "schedules"
            for schedule_file in schedules_dir.glob(f"{retailer}__{client.lower().replace(' ', '_')}__*.json"):
                with open(schedule_file, 'r') as f:
                    config = json.load(f)
                
                # Show in dialog
                details = json.dumps(config, indent=2)
                
                dialog = tk.Toplevel(self.frame)
                dialog.title(f"Schedule: {client} - {retailer}")
                dialog.geometry("600x400")
                
                text = scrolledtext.ScrolledText(dialog, wrap="word", font=("Courier", 10))
                text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
                text.insert("1.0", details)
                text.config(state="disabled")
                
                return
            
            messagebox.showerror("Error", "Schedule file not found")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to view details: {e}")
    
    # ===== Audit Methods =====
    
    def _refresh_audits(self):
        """Refresh audit log display"""
        try:
            limit = self.audit_limit_var.get()
            
            # Find recent audit logs
            output_dir = self.base_dir / "output"
            audit_logs = []
            
            for retailer_dir in output_dir.iterdir():
                if not retailer_dir.is_dir():
                    continue
                for client_dir in retailer_dir.iterdir():
                    if not client_dir.is_dir():
                        continue
                    audit_file = client_dir / "runs" / "audit_log.jsonl"
                    if audit_file.exists():
                        audit_logs.append(audit_file)
            
            # Read and combine audit entries
            all_audits = []
            for audit_file in audit_logs:
                try:
                    with open(audit_file, 'r') as f:
                        for line in f:
                            try:
                                audit = json.loads(line)
                                all_audits.append(audit)
                            except:
                                pass
                except:
                    pass
            
            # Sort by timestamp, most recent first
            all_audits.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            
            # Display
            self.audit_text.config(state="normal")
            self.audit_text.delete("1.0", tk.END)
            
            if not all_audits:
                self.audit_text.insert("1.0", "No audit logs found. Run some scrapes first.")
            else:
                for audit in all_audits[:limit]:
                    timestamp = audit.get("timestamp", "")[:19]
                    retailer = audit.get("retailer", "")
                    keyword = audit.get("keyword", "")
                    score = audit.get("quality_score", 0)
                    total = audit.get("total_ads", 0)
                    blank = audit.get("blank_ads", 0)
                    unknown = audit.get("unknown_brands", 0)
                    
                    # Color code by score
                    if score >= 80:
                        status = "✅"
                    elif score >= 50:
                        status = "⚠️"
                    else:
                        status = "❌"
                    
                    line = f"{status} {timestamp} | {retailer:10s} | {keyword:20s} | Score: {score:5.1f} | Ads: {total:2d} | Blank: {blank:2d} | Unknown: {unknown:2d}\n"
                    self.audit_text.insert(tk.END, line)
            
            self.audit_text.config(state="disabled")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to refresh audits: {e}")
    
    # ===== Brands Methods =====
    
    def _analyze_brands(self):
        """Run unknown brands analysis"""
        try:
            limit = self.brands_limit_var.get()
            
            self.brands_text.config(state="normal")
            self.brands_text.delete("1.0", tk.END)
            self.brands_text.insert("1.0", f"Analyzing last {limit} runs...\n\n")
            self.brands_text.config(state="disabled")
            
            # Run analysis in background
            def run_analysis():
                try:
                    venv_python = self.base_dir / ".venv" / "bin" / "python3"
                    if not venv_python.exists():
                        venv_python = "python3"
                    
                    result = subprocess.run(
                        [str(venv_python), "tools/analyze_unknown_brands.py", str(limit)],
                        cwd=str(self.base_dir),
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                    
                    # Update UI in main thread
                    def update_ui():
                        self.brands_text.config(state="normal")
                        self.brands_text.delete("1.0", tk.END)
                        if result.returncode == 0:
                            self.brands_text.insert("1.0", result.stdout)
                        else:
                            self.brands_text.insert("1.0", f"Error:\n{result.stderr}")
                        self.brands_text.config(state="disabled")
                    
                    self.app.root.after(0, update_ui)
                    
                except Exception as e:
                    def show_error():
                        self.brands_text.config(state="normal")
                        self.brands_text.delete("1.0", tk.END)
                        self.brands_text.insert("1.0", f"Analysis failed: {e}")
                        self.brands_text.config(state="disabled")
                    
                    self.app.root.after(0, show_error)
            
            threading.Thread(target=run_analysis, daemon=True).start()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start analysis: {e}")
