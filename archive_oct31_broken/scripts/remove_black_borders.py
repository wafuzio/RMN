#!/usr/bin/env python3
"""
Remove black borders from Kroger TOA and Skyscraper images.
This script processes images and crops out black padding/backgrounds.
"""

import os
import sys
from PIL import Image, ImageChops
import glob

def trim_black_borders(image_path, output_path=None, threshold=30):
    """
    Remove black borders from an image by detecting and cropping to content.
    
    Args:
        image_path: Path to input image
        output_path: Path to save trimmed image (None = overwrite original)
        threshold: Pixel value threshold for considering something "black" (0-255)
    
    Returns:
        bool: True if image was trimmed, False if no trimming needed
    """
    try:
        img = Image.open(image_path)
        
        # Convert to RGB if needed
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Get the bounding box of non-black content
        # Create a grayscale version
        gray = img.convert('L')
        
        # Find pixels that are NOT black (above threshold)
        bbox = None
        width, height = gray.size
        pixels = gray.load()
        
        # Find top
        top = 0
        for y in range(height):
            if any(pixels[x, y] > threshold for x in range(width)):
                top = y
                break
        
        # Find bottom
        bottom = height - 1
        for y in range(height - 1, -1, -1):
            if any(pixels[x, y] > threshold for x in range(width)):
                bottom = y
                break
        
        # Find left
        left = 0
        for x in range(width):
            if any(pixels[x, y] > threshold for y in range(top, bottom + 1)):
                left = x
                break
        
        # Find right
        right = width - 1
        for x in range(width - 1, -1, -1):
            if any(pixels[x, y] > threshold for y in range(top, bottom + 1)):
                right = x
                break
        
        # Check if we found a valid bounding box
        if left >= right or top >= bottom:
            print(f"⚠️  No content found in {os.path.basename(image_path)}")
            return False
        
        # Check if trimming is needed (more than 5 pixels of border)
        border_size = min(left, top, width - right - 1, height - bottom - 1)
        if border_size < 5:
            print(f"✓ No trimming needed: {os.path.basename(image_path)}")
            return False
        
        # Crop the image
        cropped = img.crop((left, top, right + 1, bottom + 1))
        
        # Save
        if output_path is None:
            output_path = image_path
        
        cropped.save(output_path, quality=95, optimize=True)
        
        original_size = os.path.getsize(image_path)
        new_size = os.path.getsize(output_path)
        reduction = ((original_size - new_size) / original_size) * 100
        
        print(f"✅ Trimmed: {os.path.basename(image_path)}")
        print(f"   Border removed: {border_size}px, Size: {original_size//1024}KB → {new_size//1024}KB ({reduction:.1f}% reduction)")
        
        return True
        
    except Exception as e:
        print(f"❌ Error processing {image_path}: {e}")
        return False


def process_directory(directory, dry_run=False):
    """
    Process all PNG images in a directory and its subdirectories.
    
    Args:
        directory: Root directory to search
        dry_run: If True, don't actually modify files
    """
    pattern = os.path.join(directory, "**", "*.png")
    image_files = glob.glob(pattern, recursive=True)
    
    print(f"\n🔍 Found {len(image_files)} PNG images in {directory}")
    
    if dry_run:
        print("🔸 DRY RUN MODE - No files will be modified\n")
    
    trimmed_count = 0
    skipped_count = 0
    error_count = 0
    
    for img_path in image_files:
        if dry_run:
            # Just check if trimming would be needed
            try:
                img = Image.open(img_path)
                gray = img.convert('L')
                width, height = gray.size
                pixels = gray.load()
                
                # Quick check for black borders
                has_border = False
                threshold = 30
                
                # Check edges
                if all(pixels[x, 0] < threshold for x in range(min(50, width))):
                    has_border = True
                
                if has_border:
                    print(f"Would trim: {os.path.basename(img_path)}")
                    trimmed_count += 1
                else:
                    skipped_count += 1
                    
            except Exception as e:
                print(f"Error checking {img_path}: {e}")
                error_count += 1
        else:
            # Actually trim
            result = trim_black_borders(img_path)
            if result:
                trimmed_count += 1
            else:
                skipped_count += 1
    
    print(f"\n📊 Summary:")
    print(f"   Trimmed: {trimmed_count}")
    print(f"   Skipped: {skipped_count}")
    print(f"   Errors: {error_count}")
    print(f"   Total: {len(image_files)}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Remove black borders from Kroger ad images")
    parser.add_argument("--directory", "-d", default="output/kroger",
                        help="Directory to process (default: output/kroger)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview what would be trimmed without modifying files")
    parser.add_argument("--toa-only", action="store_true",
                        help="Only process TOA images")
    parser.add_argument("--skyscraper-only", action="store_true",
                        help="Only process Skyscraper images")
    
    args = parser.parse_args()
    
    # Check if PIL is available
    try:
        from PIL import Image
    except ImportError:
        print("❌ PIL/Pillow is required. Install with: pip install Pillow")
        sys.exit(1)
    
    base_dir = args.directory
    
    if args.toa_only:
        dirs = [os.path.join(base_dir, d, "TOA") for d in os.listdir(base_dir) 
                if os.path.isdir(os.path.join(base_dir, d))]
    elif args.skyscraper_only:
        dirs = [os.path.join(base_dir, d, "Skyscraper") for d in os.listdir(base_dir) 
                if os.path.isdir(os.path.join(base_dir, d))]
    else:
        dirs = [base_dir]
    
    for directory in dirs:
        if os.path.exists(directory):
            process_directory(directory, dry_run=args.dry_run)
        else:
            print(f"⚠️  Directory not found: {directory}")
