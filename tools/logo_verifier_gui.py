#!/usr/bin/env python3
"""
Logo Verifier GUI - Review and approve/reject brand logos

Shows each logo with its brand name and metadata.
Press 'Y' to keep, 'N' to delete, 'Q' to quit.
"""

import json
import sys
from pathlib import Path
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import ttk

# Paths
LOGOS_DIR = Path("output/brand_logos")
LOGOS_DB = Path("output/brand_logos/brand_logo_database.json")


def load_database():
    """Load the brand logo database"""
    if LOGOS_DB.exists():
        try:
            return json.loads(LOGOS_DB.read_text())
        except Exception:
            pass
    return {"brands": {}, "metadata": {"last_updated": None, "total_brands": 0}}


def save_database(db):
    """Save the brand logo database"""
    from datetime import datetime, timezone
    db["metadata"]["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db["metadata"]["total_brands"] = len(db["brands"])
    
    # Sort brands alphabetically
    sorted_brands = dict(sorted(db["brands"].items(), key=lambda x: x[0].lower()))
    db["brands"] = sorted_brands
    
    LOGOS_DB.write_text(json.dumps(db, indent=2, ensure_ascii=False))


class LogoVerifier:
    def get_timestamp(self):
        """Get current timestamp in ISO format"""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    def __init__(self, root):
        self.root = root
        self.root.title("Logo Verifier")
        self.root.geometry("800x900")
        
        # Load database
        self.db = load_database()
        
        # Filter to only brands with existing logo files that haven't been verified
        all_brands = list(self.db.get("brands", {}).items())
        self.brands = []
        skipped_no_file = 0
        skipped_verified = 0
        
        for brand_key, brand_data in all_brands:
            # Skip already verified logos
            if brand_data.get("verified", False):
                skipped_verified += 1
                continue
            
            logo_file = brand_data.get("logo_file", "")
            
            # Handle both path formats
            if logo_file.startswith("brand_logos/"):
                logo_file = logo_file.replace("brand_logos/", "")
            
            logo_path = LOGOS_DIR / logo_file
            
            if logo_path.exists():
                self.brands.append((brand_key, brand_data))
            else:
                skipped_no_file += 1
                print(f"⊘ Skipping {brand_key}: file not found ({logo_file})")
        
        print(f"\n📊 Found {len(self.brands)} logos to verify")
        print(f"   Skipped: {skipped_verified} already verified, {skipped_no_file} no file")
        
        self.current_index = 0
        self.deleted_count = 0
        self.kept_count = 0
        
        # Setup UI
        self.setup_ui()
        
        # Show first logo
        if self.brands:
            self.show_current_logo()
        else:
            self.show_empty_message()
    
    def setup_ui(self):
        """Setup the UI components"""
        # Progress label
        self.progress_label = ttk.Label(
            self.root,
            text="",
            font=("Arial", 12)
        )
        self.progress_label.pack(pady=10)
        
        # Brand name label
        self.brand_label = ttk.Label(
            self.root,
            text="",
            font=("Arial", 20, "bold")
        )
        self.brand_label.pack(pady=10)
        
        # Image canvas
        self.canvas = tk.Canvas(self.root, width=600, height=400, bg="white")
        self.canvas.pack(pady=20)
        
        # Metadata frame
        self.metadata_frame = ttk.Frame(self.root)
        self.metadata_frame.pack(pady=10, fill="x", padx=20)
        
        self.source_label = ttk.Label(self.metadata_frame, text="", font=("Arial", 10))
        self.source_label.pack(anchor="w")
        
        self.path_label = ttk.Label(self.metadata_frame, text="", font=("Arial", 10))
        self.path_label.pack(anchor="w")
        
        self.retailers_label = ttk.Label(self.metadata_frame, text="", font=("Arial", 10))
        self.retailers_label.pack(anchor="w")
        
        # Button frame
        button_frame = ttk.Frame(self.root)
        button_frame.pack(pady=20)
        
        # Keep button
        self.keep_btn = ttk.Button(
            button_frame,
            text="✓ Keep (Y)",
            command=self.keep_logo,
            width=15
        )
        self.keep_btn.pack(side="left", padx=10)
        
        # Delete button
        self.delete_btn = ttk.Button(
            button_frame,
            text="✗ Delete (N)",
            command=self.delete_logo,
            width=15
        )
        self.delete_btn.pack(side="left", padx=10)
        
        # Quit button
        self.quit_btn = ttk.Button(
            button_frame,
            text="Quit (Q)",
            command=self.quit_app,
            width=15
        )
        self.quit_btn.pack(side="left", padx=10)
        
        # Stats label
        self.stats_label = ttk.Label(
            self.root,
            text="",
            font=("Arial", 10, "italic")
        )
        self.stats_label.pack(pady=10)
        
        # Keyboard bindings
        self.root.bind('y', lambda e: self.keep_logo())
        self.root.bind('Y', lambda e: self.keep_logo())
        self.root.bind('n', lambda e: self.delete_logo())
        self.root.bind('N', lambda e: self.delete_logo())
        self.root.bind('q', lambda e: self.quit_app())
        self.root.bind('Q', lambda e: self.quit_app())
        self.root.bind('<Left>', lambda e: self.previous_logo())
        self.root.bind('<Right>', lambda e: self.next_logo())
    
    def show_empty_message(self):
        """Show message when no logos to verify"""
        self.brand_label.config(text="No logos to verify!")
        self.progress_label.config(text="Database is empty")
    
    def show_current_logo(self):
        """Display the current logo"""
        if self.current_index >= len(self.brands):
            self.show_completion()
            return
        
        brand_key, brand_data = self.brands[self.current_index]
        logo_file = brand_data.get("logo_file", "")
        
        # Update progress
        self.progress_label.config(
            text=f"Logo {self.current_index + 1} of {len(self.brands)}"
        )
        
        # Update brand name (convert key back to readable format)
        brand_name = brand_key.replace("_", " ").title()
        self.brand_label.config(text=brand_name)
        
        # Update metadata
        source = brand_data.get("source", "unknown")
        retailers = ", ".join(brand_data.get("retailers", []))
        
        self.source_label.config(text=f"Source: {source}")
        self.path_label.config(text=f"File: {logo_file}")
        self.retailers_label.config(text=f"Retailers: {retailers}")
        
        # Update stats
        self.stats_label.config(
            text=f"Kept: {self.kept_count} | Deleted: {self.deleted_count}"
        )
        
        # Load and display image
        # Handle both "afia.png" and "brand_logos/afia.png" formats
        if logo_file.startswith("brand_logos/"):
            logo_file = logo_file.replace("brand_logos/", "")
        
        logo_path = LOGOS_DIR / logo_file
        if logo_path.exists():
            try:
                # Load image
                img = Image.open(logo_path)
                
                # Resize to fit canvas while maintaining aspect ratio
                max_width, max_height = 580, 380
                img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
                
                # Convert to PhotoImage
                self.photo = ImageTk.PhotoImage(img)
                
                # Clear canvas and display image
                self.canvas.delete("all")
                
                # Center the image
                x = (600 - img.width) // 2
                y = (400 - img.height) // 2
                
                self.canvas.create_image(x, y, anchor="nw", image=self.photo)
                
            except Exception as e:
                self.canvas.delete("all")
                self.canvas.create_text(
                    300, 200,
                    text=f"Error loading image:\n{str(e)}",
                    font=("Arial", 12),
                    fill="red"
                )
        else:
            self.canvas.delete("all")
            self.canvas.create_text(
                300, 200,
                text=f"File not found:\n{logo_path}",
                font=("Arial", 12),
                fill="red"
            )
    
    def keep_logo(self):
        """Keep the current logo and move to next"""
        if self.current_index >= len(self.brands):
            return
        
        # Mark as verified in database
        brand_key, brand_data = self.brands[self.current_index]
        if brand_key in self.db["brands"]:
            self.db["brands"][brand_key]["verified"] = True
            self.db["brands"][brand_key]["verified_at"] = self.get_timestamp()
        
        self.kept_count += 1
        self.next_logo()
    
    def delete_logo(self):
        """Delete the current logo and move to next"""
        if self.current_index >= len(self.brands):
            return
        
        brand_key, brand_data = self.brands[self.current_index]
        logo_file = brand_data.get("logo_file", "")
        
        # Strip brand_logos/ prefix if present to avoid double path
        if logo_file.startswith("brand_logos/"):
            logo_file = logo_file[len("brand_logos/"):]
        
        logo_path = LOGOS_DIR / logo_file
        
        # Delete file
        if logo_path.exists():
            logo_path.unlink()
            print(f"🗑️  Deleted: {logo_file}")
        
        # Remove from database
        if brand_key in self.db["brands"]:
            del self.db["brands"][brand_key]
        
        # Remove from brands list
        self.brands.pop(self.current_index)
        
        self.deleted_count += 1
        
        # Show next logo (don't increment index since we removed current)
        self.show_current_logo()
    
    def next_logo(self):
        """Move to next logo"""
        self.current_index += 1
        self.show_current_logo()
    
    def previous_logo(self):
        """Move to previous logo"""
        if self.current_index > 0:
            self.current_index -= 1
            self.show_current_logo()
    
    def show_completion(self):
        """Show completion message"""
        self.brand_label.config(text="✅ Verification Complete!")
        self.progress_label.config(text="All logos reviewed")
        self.canvas.delete("all")
        self.canvas.create_text(
            300, 200,
            text=f"Kept: {self.kept_count}\nDeleted: {self.deleted_count}",
            font=("Arial", 16),
            fill="green"
        )
        
        # Disable buttons
        self.keep_btn.config(state="disabled")
        self.delete_btn.config(state="disabled")
    
    def quit_app(self):
        """Save database and quit"""
        print(f"\n📊 Session Summary:")
        print(f"   Kept: {self.kept_count}")
        print(f"   Deleted: {self.deleted_count}")
        print(f"   Remaining: {self.current_index}/{len(self.brands)}")
        
        # Save database
        save_database(self.db)
        print(f"✅ Database saved: {LOGOS_DB}")
        
        self.root.quit()


def main():
    root = tk.Tk()
    app = LogoVerifier(root)
    root.mainloop()


if __name__ == "__main__":
    main()
