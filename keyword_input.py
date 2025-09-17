"""
Keyword Input GUI

A simple popup interface for entering keywords to scrape.
"""

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk, scrolledtext
from tkinter import font as tkfont
import os
import sys
import json
import logging
from datetime import datetime
import subprocess
import time
import threading
import re

# Import the search and capture functionality
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def get_base_dir():
    """
    Return the base directory for user data (output/, configs, etc.)
    Works for both source runs and PyInstaller bundles.
    """
    if getattr(sys, 'frozen', False):
        # Packaged app (Finder/Dock/Dist)
        return os.path.expanduser("~/Documents/Amazon_Scrape")
    else:
        # Running from source
        return os.path.dirname(os.path.abspath(__file__))

class KeywordInputApp:
    def __init__(self, root):
        """Initialize the application"""
        self.root = root
        self.root.title("Kroger TOA Scraper")
        self.root.geometry("600x700")
        self.root.minsize(600, 700)
        
        # Set placeholder text
        self.placeholder_text = "Enter keywords (one per line)"
        
        # Initialize logger
        self.logger = None
        
        # Load CSS variables from web stylesheet for consistent theming
        css_vars = self.load_css_variables(os.path.join(os.path.dirname(__file__), "static", "css", "style.css"))
        self.primary_color = css_vars.get('--primary-color', '#2962ff')
        self.secondary_color = css_vars.get('--secondary-color', '#455a64')
        self.bg_color = css_vars.get('--background-color', '#f5f7fa')
        self.card_bg_color = css_vars.get('--card-background', '#ffffff')
        self.text_bg_color = "#ffffff"
        self.text_fg_color = "#111827"

        # Apply background color to root window
        self.root.configure(bg=self.bg_color)

        # Typography similar to web (Inter with sensible fallbacks)
        try:
            tkfont.nametofont("TkDefaultFont").configure(family="Inter", size=11)
            tkfont.nametofont("TkTextFont").configure(family="Inter", size=11)
            tkfont.nametofont("TkHeadingFont").configure(family="Inter", size=14, weight="bold")
        except Exception:
            pass

        # ttk styles matching web look
        self.style = ttk.Style()
        try:
            self.style.theme_use('clam')
        except Exception:
            pass
        self.style.configure('App.TFrame', background=self.bg_color)
        self.style.configure('Card.TFrame', background=self.card_bg_color)
        self.style.configure('Card.TLabelframe', background=self.card_bg_color, relief='solid', borderwidth=1)
        self.style.configure('Card.TLabelframe.Label', background=self.card_bg_color, foreground=self.secondary_color, font=("Inter", 10, "bold"))
        self.style.configure('TLabel', background=self.card_bg_color, foreground=self.secondary_color)
        self.style.configure('Body.TLabel', background=self.bg_color, foreground=self.secondary_color)
        self.style.configure('App.TCombobox', fieldbackground=self.card_bg_color, background=self.card_bg_color, foreground="#111827")
        
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
        
        # Check and start scheduler daemon if needed
        self.daemon_status = self.check_daemon_status()
        if not self.daemon_status:
            self.start_daemon_automatically()
        
        # Set up the main frame
        main_frame = ttk.Frame(root, padding=20, style='App.TFrame')
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Client/Product Type field with dropdown
        client_frame = ttk.Frame(main_frame, style='Card.TFrame')
        client_frame.pack(fill=tk.X, pady=(0, 15))

        client_label = ttk.Label(
            client_frame,
            text="Client/Product:",
            style='TLabel'
        )
        client_label.pack(side=tk.LEFT)
        
        # Get existing clients from history
        clients = list(self.client_history.keys())
        # Add default and new options
        dropdown_options = ["<choose from menu>", "New client/product"] + clients
        
        self.client_var = tk.StringVar()
        self.client_var.set(dropdown_options[0])  # Set default text
        
        self.client_dropdown = ttk.Combobox(
            client_frame,
            textvariable=self.client_var,
            values=dropdown_options,
            width=30,
            style='App.TCombobox'
        )
        self.client_dropdown.pack(side=tk.LEFT, padx=(10, 0))
        self.client_dropdown.bind("<<ComboboxSelected>>", self.on_client_selected)
        
        # Instructions
        instructions = ttk.Label(
            main_frame,
            text="Enter keywords to scrape (one per line):",
            style='Body.TLabel'
        )
        instructions.pack(anchor="w", pady=(0, 10))
        
        # Keyword input area
        self.keyword_input = scrolledtext.ScrolledText(main_frame, height=10)
        self.keyword_input.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        self.keyword_input.configure(background=self.card_bg_color, foreground=self.text_fg_color, insertbackground=self.primary_color, borderwidth=1, relief='solid')

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
            var.trace('w', on_day_changed)
        
        # Schedule control buttons
        schedule_buttons_frame = ttk.Frame(schedule_frame, style='Card.TFrame')
        schedule_buttons_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.schedule_button = tk.Button(
            schedule_buttons_frame,
            text="Save Schedule",
            command=self.save_schedule,
            bg=self.primary_color,
            fg="white",
            font=("Inter", 11, "bold"),
            padx=20,
            pady=8,
            relief="flat",
            borderwidth=0
        )
        self.schedule_button.pack(side=tk.LEFT, padx=(0, 10))
        
        
        # Buttons frame
        button_frame = ttk.Frame(main_frame, style='App.TFrame')
        button_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Start scraping button
        self.scrape_button = tk.Button(
            button_frame, 
            text="Start Scraping",
            command=self.start_scraping,
            bg=self.primary_color,
            fg="white",
            font=("Inter", 12, "bold"),
            padx=30,
            pady=10,
            relief="flat",
            borderwidth=0
        )
        self.scrape_button.pack(side=tk.LEFT, padx=(0, 10))
        
        # Clear button
        self.clear_button = tk.Button(
            button_frame, 
            text="Clear",
            command=self.clear_keywords,
            bg="#f44336",
            fg="white",
            font=("Arial", 11),
            padx=15,
            pady=8
        )
        self.clear_button.pack(side=tk.LEFT)
        
        # Status label with daemon status
        daemon_text = "✅ Daemon running" if self.daemon_status else "⚠️ Daemon stopped"
        self.status_label = ttk.Label(
            main_frame,
            text=f"Ready to scrape | {daemon_text}",
            style='Body.TLabel'
        )
        self.status_label.pack(anchor="w", pady=(10, 0))
        
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
        if not client_type:
            messagebox.showerror("Error", "Please enter a client or product type")
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
        
        # Create output directory if it doesn't exist
        output_dir = os.path.join(get_base_dir(), "output", folder_name)
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
        """Run the scraper with the given keywords"""
        try:
            # Get client/product type for output directory
            client_type = self.client_var.get().strip()
            folder_name = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in client_type)
            output_dir = os.path.join(get_base_dir(), "output", folder_name)
            
            # Create a popup window to show progress
            popup = tk.Toplevel(self.root)
            popup.title("Scraping Progress")
            popup.geometry("400x150")
            popup.transient(self.root)  # Set to be on top of the main window
            popup.grab_set()  # Modal window
            
            # Add progress information to popup
            progress_label = tk.Label(popup, text=f"Starting scraper for {client_type}...", pady=10)
            progress_label.pack()
            
            # Progress bar
            progress_var = tk.DoubleVar()
            progress_bar = ttk.Progressbar(popup, variable=progress_var, maximum=len(keywords))
            progress_bar.pack(fill=tk.X, padx=20, pady=10)
            
            # Current keyword label
            keyword_label = tk.Label(popup, text="")
            keyword_label.pack(pady=5)
            
            # Auto-close checkbox
            auto_close_var = tk.BooleanVar(value=True)
            auto_close_cb = tk.Checkbutton(popup, text="Auto-close when complete", variable=auto_close_var)
            auto_close_cb.pack(pady=5)
            
            # Update the main window status as well
            self.status_label.config(text=f"Starting scraper for {client_type}...")
            self.root.update()
            
            # Run the search and capture script for each keyword
            success_count = 0
            for i, keyword in enumerate(keywords):
                # Update progress
                progress_var.set(i)
                keyword_label.config(text=f"Scraping {i+1}/{len(keywords)}: {keyword}")
                if progress_label.winfo_exists():
                    progress_label.config(text=f"Processing keyword {i+1} of {len(keywords)}")
                popup.update()
                
                # Update main window status
                self.status_label.config(text=f"Scraping {i+1}/{len(keywords)}: {keyword}")
                self.root.update()
                
                # Call the search and capture script with output directory
                cmd = [
                    sys.executable,
                    "kroger_search_and_capture.py",
                    "--search",
                    keyword,
                    "--output-dir",
                    output_dir
                ]
                
                # Run the command with retry logic
                max_retries = 3
                retry_count = 0
                success = False
                
                while retry_count < max_retries and not success:
                    if retry_count > 0:
                        retry_msg = f"Retry attempt {retry_count}/{max_retries} for '{keyword}'..."
                        if progress_label.winfo_exists():
                            progress_label.config(text=retry_msg)
                        self.status_label.config(text=retry_msg)
                        popup.update()
                        self.root.update()
                        time.sleep(2)  # Brief pause before retry
                    
                    process = subprocess.Popen(
                        cmd, 
                        stdout=subprocess.PIPE, 
                        stderr=subprocess.PIPE,
                        text=True
                    )
                    # Discard stdout as we only need stderr for error reporting
                    _, stderr = process.communicate()
                    
                    if process.returncode == 0:
                        success = True
                        success_count += 1
                        break
                    else:
                        retry_count += 1
                        if retry_count < max_retries:
                            error_msg = f"Failed to scrape '{keyword}' (attempt {retry_count}/{max_retries}): {stderr}"
                            if progress_label.winfo_exists():
                                progress_label.config(text=f"Error: {error_msg}. Retrying...")
                            popup.update()
                        else:
                            error_msg = f"Failed to scrape '{keyword}' after {max_retries} attempts: {stderr}"
                            if progress_label.winfo_exists():
                                progress_label.config(text=f"Error: {error_msg}")
                            popup.update()
                            messagebox.showerror("Error", error_msg)
            
            # Update progress for processing HTML
            if progress_label.winfo_exists():
                progress_label.config(text="Processing saved HTML files...")
            keyword_label.config(text="")
            popup.update()
            
            # Update main window status
            self.status_label.config(text="Processing saved HTML files...")
            self.root.update()
            
            # Process the saved HTML files with retry logic
            max_retries = 3
            retry_count = 0
            success = False
            
            while retry_count < max_retries and not success:
                if retry_count > 0:
                    retry_msg = f"Retry attempt {retry_count}/{max_retries} for HTML processing..."
                    if progress_label.winfo_exists():
                        progress_label.config(text=retry_msg)
                    self.status_label.config(text=retry_msg)
                    popup.update()
                    self.root.update()
                    time.sleep(2)  # Brief pause before retry
                
                process = subprocess.Popen(
                    [sys.executable, "process_saved_html.py", "--input-dir", output_dir, "--output-dir", output_dir, "--all-files"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                # Discard stdout as we only need stderr for error reporting
                _, stderr = process.communicate()
                
                if process.returncode == 0:
                    success = True
                    break
                else:
                    retry_count += 1
                    if retry_count < max_retries:
                        error_msg = f"Failed to process HTML files (attempt {retry_count}/{max_retries}): {stderr}"
                        if progress_label.winfo_exists():
                            progress_label.config(text=f"Error: {error_msg}. Retrying...")
                        popup.update()
                    else:
                        error_msg = f"Failed to process HTML files after {max_retries} attempts: {stderr}"
                        if progress_label.winfo_exists():
                            progress_label.config(text=f"Error: {error_msg}")
                        popup.update()
                        messagebox.showerror("Error", error_msg)
                        self.status_label.config(text="Error processing HTML files")
            
            # Set progress to complete
            progress_var.set(len(keywords))
            
            if success:
                result_msg = f"Completed scraping {success_count}/{len(keywords)} keywords successfully"
                if progress_label.winfo_exists():
                    progress_label.config(text=result_msg)
                popup.update()
                messagebox.showinfo("Success", result_msg)
                self.status_label.config(text="Scraping completed successfully")
            
            # Auto-close the popup if selected
            if auto_close_var.get():
                popup.after(3000, popup.destroy)  # Close after 3 seconds
            else:
                # Add a close button if not auto-closing
                close_btn = tk.Button(popup, text="Close", command=popup.destroy)
                close_btn.pack(pady=10)
                
        except (subprocess.SubprocessError, IOError, OSError) as e:
            error_msg = f"An error occurred: {str(e)}"
            messagebox.showerror("Error", error_msg)
            self.status_label.config(text=f"Error: {str(e)}")
            
            # Close popup if it exists
            try:
                if 'popup' in locals() and popup.winfo_exists():
                    popup.destroy()
            except (NameError, tk.TclError):
                pass

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
            
        # Scan all client directories for schedule configs
        for client_dir in os.listdir(output_path):
            client_path = os.path.join(output_path, client_dir)
            if not os.path.isdir(client_path):
                continue
                
            schedule_file = os.path.join(client_path, "schedule_config.json")
            if not os.path.exists(schedule_file):
                continue
                
            try:
                with open(schedule_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    
                client_name = config.get("client", client_dir)
                
                # Skip the current client if specified
                if exclude_client and client_name == exclude_client:
                    continue
                    
                # Extract times and days
                times = config.get("times", [])
                days = config.get("days", [])
                
                for hour_str, minute_str, ampm in times:
                    try:
                        hour_12 = int(hour_str)
                        minute = int(minute_str)
                        
                        # Convert to 24-hour format
                        hour_24 = hour_12
                        if ampm == "PM" and hour_12 < 12:
                            hour_24 += 12
                        elif ampm == "AM" and hour_12 == 12:
                            hour_24 = 0
                            
                        # Add to scheduled times for each day
                        for day in days:
                            # Create 5-minute window around the scheduled time
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
                                    
                                scheduled_times.add((day, conflict_hour, conflict_minute))
                                
                    except (ValueError, TypeError):
                        continue
                        
            except (json.JSONDecodeError, IOError):
                continue
                
        return scheduled_times
    
    def is_time_conflicted(self, hour_24, minute, days, exclude_client=None):
        """Check if a specific time conflicts with existing schedules"""
        scheduled_times = self.get_all_scheduled_times(exclude_client)
        
        for day in days:
            if (day, hour_24, minute) in scheduled_times:
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
            # Check for running scheduler_daemon process
            result = subprocess.run(
                ["ps", "aux"], 
                capture_output=True, 
                text=True, 
                timeout=10
            )
            
            # Look for scheduler_daemon.py in the process list
            for line in result.stdout.split('\n'):
                if 'scheduler_daemon.py' in line and 'python' in line:
                    return True
            return False
            
        except Exception as e:
            print(f"Error checking daemon status: {e}")
            return False
    
    def start_daemon_automatically(self):
        """Automatically start the scheduler daemon if it's not running"""
        try:
            print("Scheduler daemon not running. Starting automatically...")
            
            # Determine the project directory
            # If running from PyInstaller, we need to find the original project directory
            if getattr(sys, 'frozen', False):
                # Running from PyInstaller bundle
                # Try to find the project directory by looking for start_scheduler.sh
                possible_paths = [
                    "/Users/dan.maguire/Documents/Amazon_Scrape",  # Absolute path
                    os.path.expanduser("~/Documents/Amazon_Scrape"),  # User home relative
                ]
                
                daemon_script = None
                for path in possible_paths:
                    test_script = os.path.join(path, "start_scheduler.sh")
                    if os.path.exists(test_script):
                        daemon_script = test_script
                        break
            else:
                # Running from source
                daemon_script = os.path.join(os.path.dirname(__file__), "start_scheduler.sh")
            
            if daemon_script and os.path.exists(daemon_script):
                # Start daemon in background
                subprocess.Popen(
                    [daemon_script],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
                print("✅ Scheduler daemon started automatically")
                self.daemon_status = True
                
                # Update status label if it exists
                if hasattr(self, 'status_label'):
                    self.status_label.config(text="Ready to scrape | ✅ Daemon running (auto-started)")
                    
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
                
            if not selected_days or not selected_client or selected_client in ["<choose from menu>", "New client/product"]:
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
    
    def update_client_dropdown(self):
        """Update the client dropdown with history"""
        clients = list(self.client_history.keys())
        # Add default and new options
        dropdown_options = ["<choose from menu>", "New client/product"] + clients
        self.client_dropdown['values'] = dropdown_options
        
    def on_client_selected(self, event):
        """Handle client selection from dropdown"""
        selected_client = self.client_var.get()
        
        if selected_client == "New client/product":
            # Prompt for new client name
            new_client = simpledialog.askstring("New Client", "Enter new client/product name:")
            if new_client and new_client.strip():
                # Update dropdown with new client
                current_values = list(self.client_dropdown["values"])
                if new_client not in current_values:
                    # Keep the default options at the beginning
                    updated_values = current_values[:2] + [new_client] + current_values[2:]
                    self.client_dropdown["values"] = updated_values
                    self.client_var.set(new_client)
                    self.keyword_input.delete(1.0, tk.END)  # Clear keywords
                    self.status_label.config(text=f"Created new client: {new_client}")
            else:
                # If canceled or empty, reset to default
                self.client_var.set("<choose from menu>")
        elif selected_client == "<choose from menu>":
            # Just clear the keywords
            self.keyword_input.delete(1.0, tk.END)
        elif selected_client in self.client_history:
            # Clear current keywords
            self.keyword_input.delete(1.0, tk.END)
            
            # Insert saved keywords
            keywords = self.client_history[selected_client]
            self.keyword_input.insert(tk.END, "\n".join(keywords))
            
            # Load client-specific schedule configuration
            self.schedule_config = self.load_schedule_config(selected_client)
            
            # Update runs per day if specified in config
            if "runs" in self.schedule_config:
                self.runs_var.set(self.schedule_config["runs"])
                # Recreate time selectors with the correct number
                self.update_time_selectors()
            else:
                # Update UI with loaded schedule
                self.load_saved_times()
            
            # Update days checkboxes if days are in the config
            if "days" in self.schedule_config:
                for day in self.day_vars:
                    self.day_vars[day].set(day in self.schedule_config["days"])
            
            self.status_label.config(text=f"Loaded {len(keywords)} keywords for {selected_client}")
            
            # Set up logging for this client
            self.logger = self.setup_logging(selected_client)
    
    def setup_logging(self, client=None):
        """Set up logging to file for scheduler events"""
        if client:
            # Create client-specific log directory
            folder_name = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in client)
            log_dir = os.path.join(get_base_dir(), "output", folder_name)
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
            
            if selected_days and selected_client and selected_client not in ["<choose from menu>", "New client/product"]:
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
            
            # Minute selector
            minute_var = tk.StringVar(value=f"{final_minute:02d}")
            minute_combo = ttk.Combobox(
                time_frame,
                textvariable=minute_var,
                values=[f"{m:02d}" for m in range(0, 60, 5)],  # Every 5 minutes
                width=3,
                style='App.TCombobox'
            )
            minute_combo.pack(side=tk.LEFT, padx=(0, 5))
            
            # AM/PM selector
            ampm_var = tk.StringVar(value=final_ampm)
            ampm_combo = ttk.Combobox(
                time_frame,
                textvariable=ampm_var,
                values=["AM", "PM"],
                width=3,
                style='App.TCombobox'
            )
            ampm_combo.pack(side=tk.LEFT, padx=(5, 0))
            
            # Add conflict indicator label
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
                self.check_and_update_conflict_display(time_widgets)
                
            hour_var.trace('w', check_time_conflict)
            minute_var.trace('w', check_time_conflict)
            ampm_var.trace('w', check_time_conflict)
            
            # Store variables
            self.time_vars.append((hour_var, minute_var, ampm_var))
            self.time_entries.append((hour_combo, minute_combo, ampm_combo))
            
            # Store widget references for conflict checking
            if not hasattr(self, 'time_widget_refs'):
                self.time_widget_refs = []
            self.time_widget_refs.append(time_widgets)
        
        # Load saved times if available - check if we have a selected client
        selected_client = self.client_var.get() if hasattr(self, 'client_var') else None
        if selected_client and selected_client not in ["<choose from menu>", "New client/product"]:
            self.schedule_config = self.load_schedule_config(selected_client)
            self.load_saved_times()
        else:
            # No client selected, just use defaults (already set above)
            pass
    
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
            client_schedule_file = os.path.join(get_base_dir(), "output", folder_name, "schedule_config.json")
            
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
        # Get selected client
        selected_client = self.client_var.get()
        if not selected_client or selected_client == "<choose from menu>":
            messagebox.showerror("Error", "Please select a client/product type before saving schedule")
            return False
            
        # Create client-specific schedule file path
        folder_name = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in selected_client)
        client_schedule_file = os.path.join(get_base_dir(), "output", folder_name, "schedule_config.json")
        
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
            "client": selected_client  # Store client name in config
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
    
    
    

def main():
    print("Starting Kroger TOA Scraper GUI...")
    try:
        print("Creating Tk root window")
        root = tk.Tk()
        print("Root window created successfully")
        print("Initializing KeywordInputApp")
        app = KeywordInputApp(root)
        print("KeywordInputApp initialized successfully")
        print("Starting mainloop")
        root.mainloop()
    except Exception as e:
        print(f"Error in main: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
