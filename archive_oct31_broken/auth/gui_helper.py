# auth/gui_helper.py
import os
import json
import subprocess
import tkinter as tk
from tkinter import messagebox, simpledialog
from pathlib import Path

def get_profile_config_path():
    """Get the path to the profiles configuration file."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, "auth", "profiles.json")

def load_profile_config():
    """Load the profile configuration from the JSON file."""
    config_path = get_profile_config_path()
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def save_profile_config(config):
    """Save the profile configuration to the JSON file."""
    config_path = get_profile_config_path()
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

def get_profile_dir(retailer):
    """Get the profile directory for the specified retailer."""
    config = load_profile_config()
    return config.get(retailer, "")

def set_profile_dir(retailer, profile_dir):
    """Set the profile directory for the specified retailer."""
    config = load_profile_config()
    config[retailer] = profile_dir
    save_profile_config(config)

def manage_retailer_login(parent, retailer):
    """Open a dialog to manage the retailer login profile."""
    config = load_profile_config()
    current_profile = config.get(retailer, "")
    
    # Ask for profile directory
    default_dir = current_profile or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "profiles",
        retailer
    )
    
    profile_dir = simpledialog.askstring(
        f"Manage {retailer.title()} Login",
        f"Enter profile directory for {retailer.title()}:",
        initialvalue=default_dir,
        parent=parent
    )
    
    if not profile_dir:
        return False
    
    # Ensure the directory exists
    os.makedirs(profile_dir, exist_ok=True)
    
    # Run the authentication script
    try:
        script_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "retailer_auth.py"
        )
        
        subprocess.run([
            "python3", script_path,
            "--retailer", retailer,
            "--profile-dir", profile_dir
        ])
        
        # Save the profile directory
        set_profile_dir(retailer, profile_dir)
        
        # Set environment variable
        env_var = f"{retailer.upper()}_PROFILE_DIR"
        os.environ[env_var] = profile_dir
        
        messagebox.showinfo(
            "Profile Saved",
            f"{retailer.title()} profile saved at: {profile_dir}\n"
            f"Environment variable {env_var} has been set."
        )
        
        return True
    except Exception as e:
        messagebox.showerror(
            "Error",
            f"Failed to manage {retailer.title()} login: {str(e)}"
        )
        return False
