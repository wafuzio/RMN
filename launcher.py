#!/usr/bin/env python3
"""
Grocery Retail Ad Monitor App Launcher
This Python script serves as the main executable for the app bundle
"""

import os
import sys
import subprocess

def main():
    # Get the directory where the app bundle is located
    app_bundle_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    script_dir = app_bundle_path
    
    # Change to the script directory
    os.chdir(script_dir)
    
    # Launch the main application
    try:
        # Import and run the main application directly
        sys.path.insert(0, script_dir)
        import keyword_input
        
        # Run the application
        if __name__ == '__main__':
            print("Starting Grocery Retail Ad Monitor GUI...")
            import tkinter as tk
            
            print("Creating Tk root window")
            root = tk.Tk()
            print("Root window created successfully")
            
            print("Initializing KeywordInputApp")
            app = keyword_input.KeywordInputApp(root)
            print("KeywordInputApp initialized successfully")
            
            print("Starting mainloop")
            root.mainloop()
            
    except Exception as e:
        print(f"Error launching application: {e}")
        # Fallback to subprocess launch
        subprocess.run([sys.executable, "keyword_input.py"])

if __name__ == '__main__':
    main()
