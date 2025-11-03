#!/usr/bin/env python3
"""
Simple Tkinter test script to verify GUI functionality
"""

import tkinter as tk
from tkinter import ttk

def main():
    # Create the main window
    root = tk.Tk()
    root.title("Tkinter Test")
    root.geometry("400x300")
    
    # Create a label
    label = tk.Label(root, text="This is a test label", font=("Arial", 14))
    label.pack(pady=20)
    
    # Create a button
    button = tk.Button(root, text="Test Button", command=lambda: print("Button clicked!"))
    button.pack(pady=10)
    
    # Create an entry field
    entry = tk.Entry(root, width=30)
    entry.pack(pady=10)
    entry.insert(0, "Test entry field")
    
    # Create a dropdown
    combo = ttk.Combobox(root, values=["Option 1", "Option 2", "Option 3"])
    combo.pack(pady=10)
    combo.set("Select an option")
    
    # Start the main loop
    root.mainloop()

if __name__ == "__main__":
    main()
