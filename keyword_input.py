"""
Keyword Input GUI

A simple popup interface for entering keywords to scrape.
"""

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk, scrolledtext
import os
import sys
import json
import logging
from datetime import datetime
import subprocess
import time
import threading

# Import the search and capture functionality
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

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
        
        self.root.update()  # Update to ensure it takes effect
        self.root.resizable(True, True)
        
        print("Building UI...")
        
        print("✅ UI built")
        
        # Set light mode colors
        self.bg_color = "#f0f0f0"  # Light gray background
        self.text_bg_color = "#ffffff"  # White background for text areas
        self.text_fg_color = "#000000"  # Black text
        
        # Apply background color to root window
        self.root.configure(bg=self.bg_color)
        
        # Client history file
        self.history_file = os.path.join("output", "client_history.json")
        self.client_history = self.load_client_history()
        
        # Scheduler variables
        self.schedule_file = os.path.join("output", "schedule_config.json")
        self.schedule_config = self.load_schedule_config()
        self.scheduler_thread = None
        self.schedule_running = False
        self.day_vars = {}  # Will store day checkbox variables
        
        # Set up the main frame
        main_frame = tk.Frame(root, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Client/Product Type field with dropdown
        client_frame = tk.Frame(main_frame)
        client_frame.pack(fill=tk.X, pady=(0, 15))
        
        client_label = tk.Label(
            client_frame, 
            text="Client/Product Type:", 
            font=("Arial", 12)
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
            width=30
        )
        self.client_dropdown.pack(side=tk.LEFT, padx=(10, 0))
        self.client_dropdown.bind("<<ComboboxSelected>>", self.on_client_selected)
        
        # Instructions
        instructions = tk.Label(
            main_frame, 
            text="Enter keywords to scrape (one per line):",
            font=("Arial", 12)
        )
        instructions.pack(anchor="w", pady=(0, 10))
        
        # Keyword input area
        self.keyword_input = scrolledtext.ScrolledText(main_frame, height=10)
        self.keyword_input.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        # Add placeholder text
        self.placeholder_text = "<enter keywords here>"
        self.keyword_input.insert(tk.END, self.placeholder_text)
        self.keyword_input.config(fg="gray")
        
        # Bind events to handle placeholder behavior
        self.keyword_input.bind("<FocusIn>", self.on_keyword_focus_in)
        self.keyword_input.bind("<FocusOut>", self.on_keyword_focus_out)
        
        # Schedule frame
        schedule_frame = tk.LabelFrame(main_frame, text="Schedule Settings", padx=10, pady=10)
        schedule_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Number of runs per day
        runs_frame = tk.Frame(schedule_frame)
        runs_frame.pack(fill=tk.X, pady=(0, 10))
        
        runs_label = tk.Label(runs_frame, text="Runs per day:")
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
        self.times_frame = tk.Frame(schedule_frame)
        self.times_frame.pack(fill=tk.X)
        
        # Time selector variables
        self.time_vars = []
        self.time_entries = []
        
        # Create initial time selectors (default to 3)
        self.update_time_selectors()
        
        # Days of week selection
        days_frame = tk.LabelFrame(schedule_frame, text="Days to Run", padx=5, pady=5)
        days_frame.pack(fill=tk.X, pady=(10, 0))
        
        # Create day checkboxes
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_boxes_frame = tk.Frame(days_frame)
        day_boxes_frame.pack(fill=tk.X, pady=5)
        
        # Create checkboxes for each day
        for i, day in enumerate(day_names):
            var = tk.BooleanVar(value=True)  # Default to selected
            self.day_vars[day] = var
            
            cb = tk.Checkbutton(day_boxes_frame, text=day[:3], variable=var)
            cb.grid(row=0, column=i, padx=5)
        
        # Schedule control buttons
        schedule_buttons_frame = tk.Frame(schedule_frame)
        schedule_buttons_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.schedule_button = tk.Button(
            schedule_buttons_frame,
            text="Start Schedule",
            command=self.toggle_schedule,
            bg="#2196F3",
            fg="white",
            font=("Arial", 10),
            padx=10,
            pady=5
        )
        self.schedule_button.pack(side=tk.LEFT, padx=(0, 10))
        
        save_schedule_button = tk.Button(
            schedule_buttons_frame,
            text="Save Schedule",
            command=self.save_schedule,
            bg="#9C27B0",
            fg="white",
            font=("Arial", 10),
            padx=10,
            pady=5
        )
        save_schedule_button.pack(side=tk.LEFT)
        
        # Buttons frame
        button_frame = tk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Start scraping button
        self.scrape_button = tk.Button(
            button_frame, 
            text="Start Scraping",
            command=self.start_scraping,
            bg="#4CAF50",
            fg="white",
            font=("Arial", 11, "bold"),
            padx=15,
            pady=8
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
        
        # Status label
        self.status_label = tk.Label(
            main_frame, 
            text="Ready to scrape",
            font=("Arial", 10),
            fg="#555"
        )
        self.status_label.pack(anchor="w", pady=(10, 0))
        
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
            messagebox.showerror("Error", "Please enter at least one keyword")
            return
            
        # Parse keywords
        keywords = [k.strip() for k in keywords_text.split("\n") if k.strip()]
        
        # Create output directory for this client/product
        output_dir = os.path.join("output", folder_name)
        os.makedirs(output_dir, exist_ok=True)
        
        # Save keywords to a file in the client directory
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
            output_dir = os.path.join("output", folder_name)
            
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
            log_dir = os.path.join("output", folder_name)
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
        
        # Clear variables
        self.time_vars = []
        self.time_entries = []
        
        # Get number of runs
        num_runs = self.runs_var.get()
        
        # Create time selectors
        for i in range(num_runs):
            # Create frame for this time selector
            time_frame = tk.Frame(self.times_frame)
            time_frame.pack(fill=tk.X, pady=(0, 5))
            
            # Label
            label = tk.Label(time_frame, text=f"Run {i+1} at:")
            label.pack(side=tk.LEFT)
            
            # Hour selector
            hour_var = tk.StringVar()
            hour_values = [f"{h}" for h in range(1, 13)]
            hour_combo = ttk.Combobox(
                time_frame,
                textvariable=hour_var,
                values=hour_values,
                width=3
            )
            hour_combo.pack(side=tk.LEFT, padx=(10, 0))
            
            # Default values based on common run times
            if i == 0:
                hour_var.set("8")  # 8 AM
            elif i == 1:
                hour_var.set("12")  # 12 PM
            elif i == 2:
                hour_var.set("4")  # 4 PM
            else:
                hour_var.set(f"{(8 + i*4) % 12 or 12}")  # Spaced out times
            
            # Colon label
            colon_label = tk.Label(time_frame, text=":")
            colon_label.pack(side=tk.LEFT)
            
            # Minute selector
            minute_var = tk.StringVar(value="00")
            minute_combo = ttk.Combobox(
                time_frame,
                textvariable=minute_var,
                values=[f"{m:02d}" for m in range(0, 60, 5)],  # Every 5 minutes
                width=3
            )
            minute_combo.pack(side=tk.LEFT, padx=(0, 5))
            
            # AM/PM selector
            if i == 0:
                ampm_default = "AM"  # 8 AM
            elif i == 1:
                ampm_default = "PM"  # 12 PM
            elif i == 2:
                ampm_default = "PM"  # 4 PM
            else:
                ampm_default = "PM"  # Default to PM for additional times
            ampm_var = tk.StringVar(value=ampm_default)
            ampm_combo = ttk.Combobox(
                time_frame,
                textvariable=ampm_var,
                values=["AM", "PM"],
                width=3
            )
            ampm_combo.pack(side=tk.LEFT)
            
            # Store variables
            self.time_vars.append((hour_var, minute_var, ampm_var))
            self.time_entries.append((hour_combo, minute_combo, ampm_combo))
        
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
            client_schedule_file = os.path.join("output", folder_name, "schedule_config.json")
            
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
        client_schedule_file = os.path.join("output", folder_name, "schedule_config.json")
        
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
            self.status_label.config(text=f"Schedule saved for {selected_client}")
            
            # Set up logging for this client
            self.logger = self.setup_logging(selected_client)
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
    
    def run_scheduler(self):
        """Run the scheduler in a background thread"""
        while self.schedule_running:
            now = datetime.now()
            current_hour = now.hour
            current_minute = now.minute
            current_day = now.strftime("%A")  # Get day name (Monday, Tuesday, etc.)
            
            # Check each scheduled time
            for i, (hour_var, minute_var, ampm_var) in enumerate(self.time_vars):
                try:
                    # Get scheduled time in 12-hour format
                    hour_12 = int(hour_var.get())
                    minute = int(minute_var.get())
                    ampm = ampm_var.get()
                    
                    # Convert to 24-hour for comparison
                    scheduled_hour = hour_12
                    if ampm == "PM" and hour_12 < 12:
                        scheduled_hour += 12
                    elif ampm == "AM" and hour_12 == 12:
                        scheduled_hour = 0
                    
                    # If it's time to run (within a 1-minute window)
                    if current_hour == scheduled_hour and current_minute == minute:
                        # Check if today is a scheduled day
                        if current_day not in [day for day, var in self.day_vars.items() if var.get()]:
                            # Log error in the main thread
                            self.root.after(0, lambda: self.status_label.config(
                                text=f"Scheduled run skipped - Today ({current_day}) is not a scheduled day")
                            )
                            time.sleep(60)
                            continue
                        
                        # Check if client/product is still selected
                        selected_client = self.client_var.get()
                        if not selected_client or selected_client == "<choose from menu>":
                            # Log error in the main thread
                            self.root.after(0, lambda: self.status_label.config(
                                text="Scheduled run skipped - No client/product selected")
                            )
                            time.sleep(60)
                            continue
                            
                        # Check if keywords are entered
                        keywords = self.get_keywords()
                        if not keywords:
                            # Log error in the main thread
                            self.root.after(0, lambda: self.status_label.config(
                                text="Scheduled run skipped - No keywords entered")
                            )
                            time.sleep(60)
                            continue
                        
                        # Update status in the main thread
                        time_str = f"{hour_12}:{minute:02d} {ampm}"
                        self.root.after(0, lambda time_str=time_str, client=selected_client: 
                            self.status_label.config(
                                text=f"Running scheduled scrape for {client} at {time_str}")
                        )
                        
                        # Run the scraper
                        self.root.after(0, self.start_scraping)
                        
                        # Wait a bit to avoid duplicate runs
                        time.sleep(60)
                except ValueError:
                    # Invalid time format, skip this one
                    continue
            
            # Check every 30 seconds
            time.sleep(30)
    
    def toggle_schedule(self):
        """Toggle the scheduler on/off"""
        if self.schedule_running:
            # Stop the scheduler
            self.schedule_running = False
            self.schedule_button.config(text="Start Schedule", bg="#2196F3")
            self.status_label.config(text="Scheduler stopped")
        else:
            # Check if client/product is selected
            selected_client = self.client_var.get()
            if not selected_client or selected_client == "<choose from menu>":
                messagebox.showerror("Error", "Please select a client/product type before scheduling")
                return
                
            # Verify client has saved keywords in history
            keywords = self.client_history.get(selected_client, [])
            if not keywords:
                messagebox.showerror("Error", f"No saved keywords for {selected_client}. Please add and save keywords first.")
                return
                
            # Validate time inputs
            for i, (hour_var, minute_var, ampm_var) in enumerate(self.time_vars):
                try:
                    hour = int(hour_var.get())
                    minute = int(minute_var.get())
                    if hour < 1 or hour > 12 or minute < 0 or minute > 59:
                        messagebox.showerror("Error", f"Invalid time format for Run {i+1}")
                        return
                except ValueError:
                    messagebox.showerror("Error", f"Invalid time format for Run {i+1}")
                    return
            
            # Set up client-specific logging
            self.logger = self.setup_logging(selected_client)
            if self.logger:
                self.logger.info(f"Scheduler started for {selected_client}")
            
            # Save schedule to client-specific file
            if not self.save_schedule():  # This will update self.schedule_file to client-specific path
                return  # If save failed, don't start the scheduler
                
            self.schedule_running = True
            self.schedule_button.config(text="Stop Schedule", bg="#F44336")
            self.status_label.config(text=f"Scheduler started for {selected_client} - waiting for next run time")
            
            # Start scheduler thread if not already running
            if not self.scheduler_thread or not self.scheduler_thread.is_alive():
                self.scheduler_thread = threading.Thread(target=self.run_scheduler, daemon=True)
                self.scheduler_thread.start()
    
    def run_scheduler(self):
        """Run the scheduler in a background thread"""
        while self.schedule_running:
            now = datetime.now()
            current_hour = now.hour
            current_minute = now.minute
            
            # Check each scheduled time
            for i, (hour_var, minute_var) in enumerate(self.time_vars):
                try:
                    scheduled_hour = int(hour_var.get())
                    scheduled_minute = int(minute_var.get())
                    
                    # If it's time to run (within a 1-minute window)
                    if current_hour == scheduled_hour and current_minute == scheduled_minute:
                        # Check if client/product is still selected
                        selected_client = self.client_var.get()
                        if not selected_client or selected_client == "Select client/product":
                            # Log error in the main thread and to file
                            error_msg = "Scheduled run skipped - No client/product selected"
                            if self.logger:
                                self.logger.warning(error_msg)
                            self.root.after(0, lambda: self.status_label.config(text=error_msg))
                            time.sleep(60)
                            continue
                            
                        # Use saved keywords from client_history instead of text box
                        keywords = self.client_history.get(selected_client, [])
                        if not keywords:
                            # Log error in the main thread and to file
                            error_msg = f"Scheduled run skipped - No saved keywords for {selected_client}"
                            if self.logger:
                                self.logger.warning(error_msg)
                            self.root.after(0, lambda: self.status_label.config(text=error_msg))
                            time.sleep(60)
                            continue
                        
                        # Check if today is a scheduled day
                        if current_day not in [day for day, var in self.day_vars.items() if var.get()]:
                            # Log error in the main thread
                            self.root.after(0, lambda: self.status_label.config(
                                text=f"Scheduled run skipped - Today ({current_day}) is not a scheduled day")
                            )
                            time.sleep(60)
                            continue
                        
                        # Update status in the main thread
                        time_str = f"{scheduled_hour:02d}:{scheduled_minute:02d}"
                        self.root.after(0, lambda time_str=time_str, client=selected_client: 
                            self.status_label.config(
                                text=f"Running scheduled scrape for {client} at {time_str}")
                        )
                        
                        # Run the scraper
                        self.root.after(0, self.start_scraping)
                        
                        # Wait a bit to avoid duplicate runs
                        time.sleep(60)
                except ValueError:
                    # Invalid time format, skip this one
                    continue
            
            # Check every 30 seconds
            time.sleep(30)

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
