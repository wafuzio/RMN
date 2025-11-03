# Example of how to integrate the auth helper with the GUI
# This is just a sample - you would integrate these parts into your keyword_input.py

import tkinter as tk
from tkinter import ttk
from auth.gui_helper import manage_retailer_login

def add_manage_login_button(parent_frame, retailer_var):
    """
    Add a 'Manage Login' button to the GUI.
    
    Parameters:
    - parent_frame: The frame to add the button to
    - retailer_var: StringVar containing the selected retailer
    
    Returns:
    - The created button
    """
    manage_login_btn = ttk.Button(
        parent_frame,
        text="Manage Login…",
        command=lambda: on_manage_login(parent_frame, retailer_var)
    )
    return manage_login_btn

def on_manage_login(parent, retailer_var):
    """Handle the 'Manage Login' button click."""
    retailer = retailer_var.get().lower()
    # Map display names to slugs if needed
    retailer_map = {
        "Kroger": "kroger",
        "Amazon": "amazon",
        "Walmart": "walmart"
    }
    retailer_slug = retailer_map.get(retailer, retailer)
    
    # Open the login management dialog
    manage_retailer_login(parent, retailer_slug)

# Example of how to use in your KeywordInputApp class:
"""
# In your __init__ method, after creating the retailer dropdown:
self.manage_login_btn = add_manage_login_button(client_frame, self.retailer_var)
self.manage_login_btn.pack(side=tk.LEFT, padx=(5, 0))

# Or directly in your code:
self.manage_login_btn = ttk.Button(
    client_frame,
    text="Manage Login…",
    command=lambda: on_manage_login(self.root, self.retailer_var)
)
self.manage_login_btn.pack(side=tk.LEFT, padx=(5, 0))
"""
