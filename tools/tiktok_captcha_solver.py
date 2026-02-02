#!/usr/bin/env python3
"""
TikTok Slide CAPTCHA Solver

Automatically solves TikTok's slide puzzle CAPTCHA by:
1. Downloading the background image (with slot) and puzzle piece
2. Using edge detection to find the slot position
3. Calculating the drag distance
4. Simulating a human-like drag motion
"""

import asyncio
import random
import time
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
import requests
from PIL import Image

# Optional: for standalone testing
try:
    from playwright.async_api import Page
except ImportError:
    Page = None


def download_image(url: str, headers: dict = None) -> np.ndarray:
    """Download image from URL and return as numpy array (BGR format for OpenCV)"""
    default_headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
    }
    if headers:
        default_headers.update(headers)
    
    response = requests.get(url, headers=default_headers, timeout=10)
    response.raise_for_status()
    
    # Convert to numpy array
    img_array = np.frombuffer(response.content, np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_UNCHANGED)
    
    return img


def find_slot_position(background: np.ndarray, piece: np.ndarray) -> int:
    """
    Find the X position of the slot in the background image.
    
    The slot appears as a darkened region with a white border.
    The piece has the actual image content with white/dark borders.
    
    Returns the X coordinate where the piece should be dragged to.
    """
    # Convert to grayscale if needed
    if len(background.shape) == 3:
        bg_gray = cv2.cvtColor(background, cv2.COLOR_BGR2GRAY)
    else:
        bg_gray = background.copy()
    
    if len(piece.shape) == 3:
        # Handle RGBA (piece often has transparency)
        if piece.shape[2] == 4:
            # Use alpha channel to create mask
            piece_alpha = piece[:, :, 3]
            piece_rgb = piece[:, :, :3]
            piece_gray = cv2.cvtColor(piece_rgb, cv2.COLOR_BGR2GRAY)
        else:
            piece_gray = cv2.cvtColor(piece, cv2.COLOR_BGR2GRAY)
            piece_alpha = None
    else:
        piece_gray = piece.copy()
        piece_alpha = None
    
    # Method 1: Edge-based template matching
    # Extract edges from both images
    bg_edges = cv2.Canny(bg_gray, 100, 200)
    piece_edges = cv2.Canny(piece_gray, 100, 200)
    
    # Template matching on edges
    result = cv2.matchTemplate(bg_edges, piece_edges, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    
    print(f"[CAPTCHA] Edge matching confidence: {max_val:.3f}")
    print(f"[CAPTCHA] Detected slot position: x={max_loc[0]}")
    
    # Method 2: Look for the dark slot region (backup)
    # The slot is darker than surrounding area
    if max_val < 0.3:
        print("[CAPTCHA] Low confidence, trying brightness analysis...")
        
        # Look for sudden brightness drops (the shadow in the slot)
        # Scan horizontally in the middle third of the image
        h, w = bg_gray.shape
        scan_region = bg_gray[h//3:2*h//3, :]
        
        # Calculate column-wise variance (slot has different pattern)
        col_std = np.std(scan_region, axis=0)
        
        # Find regions with high variance (edges of slot)
        threshold = np.mean(col_std) + np.std(col_std)
        high_var_cols = np.where(col_std > threshold)[0]
        
        if len(high_var_cols) > 0:
            # The slot is likely around the first cluster of high variance
            # that's not at the very left (where the piece starts)
            for col in high_var_cols:
                if col > w * 0.2:  # Skip the left 20% where piece starts
                    max_loc = (col, max_loc[1])
                    print(f"[CAPTCHA] Brightness analysis found slot at x={col}")
                    break
    
    return max_loc[0]


def find_slot_by_contour(background: np.ndarray) -> int:
    """
    Alternative method: Find the slot by looking for the puzzle piece shaped contour.
    The slot has a distinctive white border that creates strong edges.
    """
    if len(background.shape) == 3:
        bg_gray = cv2.cvtColor(background, cv2.COLOR_BGR2GRAY)
    else:
        bg_gray = background.copy()
    
    # Apply edge detection
    edges = cv2.Canny(bg_gray, 50, 150)
    
    # Dilate to connect nearby edges
    kernel = np.ones((3, 3), np.uint8)
    edges = cv2.dilate(edges, kernel, iterations=1)
    
    # Find contours
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Look for contours that match puzzle piece characteristics
    # - Roughly square-ish aspect ratio
    # - Located in the right portion of the image (not the draggable piece on left)
    h, w = bg_gray.shape
    
    candidates = []
    for contour in contours:
        x, y, cw, ch = cv2.boundingRect(contour)
        
        # Skip if too small or too large
        area = cw * ch
        if area < 1000 or area > (w * h * 0.3):
            continue
        
        # Skip if on the left side (that's the draggable piece)
        if x < w * 0.15:
            continue
        
        # Check aspect ratio (puzzle pieces are roughly square)
        aspect = cw / ch if ch > 0 else 0
        if 0.5 < aspect < 2.0:
            candidates.append((x, y, cw, ch, area))
    
    if candidates:
        # Sort by area and take the largest reasonable one
        candidates.sort(key=lambda c: c[4], reverse=True)
        best = candidates[0]
        print(f"[CAPTCHA] Contour method found slot at x={best[0]}")
        return best[0]
    
    return None


async def solve_captcha(page, timeout: float = 10.0) -> bool:
    """
    Solve TikTok slide CAPTCHA on a Playwright page.
    
    Args:
        page: Playwright page object
        timeout: Max seconds to wait for CAPTCHA elements
        
    Returns:
        True if solved successfully, False otherwise
    """
    try:
        # Wait for CAPTCHA to appear
        print("[CAPTCHA] Waiting for CAPTCHA elements...")
        
        bg_img = page.locator('#captcha-verify-image')
        piece_img = page.locator('.captcha_verify_img_slide')
        drag_handle = page.locator('.secsdk-captcha-drag-icon')
        
        await bg_img.wait_for(timeout=timeout * 1000)
        await piece_img.wait_for(timeout=timeout * 1000)
        await drag_handle.wait_for(timeout=timeout * 1000)
        
        # Get image URLs
        bg_url = await bg_img.get_attribute('src')
        piece_url = await piece_img.get_attribute('src')
        
        print(f"[CAPTCHA] Background: {bg_url[:80]}...")
        print(f"[CAPTCHA] Piece: {piece_url[:80]}...")
        
        # Download images
        background = download_image(bg_url)
        piece = download_image(piece_url)
        
        print(f"[CAPTCHA] Background size: {background.shape}")
        print(f"[CAPTCHA] Piece size: {piece.shape}")
        
        # Find the slot position
        target_x = find_slot_position(background, piece)
        
        # Get the current piece position (it starts on the left)
        piece_style = await piece_img.get_attribute('style')
        # Parse "left: 8px" from style
        import re
        left_match = re.search(r'left:\s*([\d.]+)px', piece_style or '')
        start_offset = float(left_match.group(1)) if left_match else 8
        
        # Calculate drag distance
        # The target_x is relative to the background image
        # We need to account for the piece's starting position
        drag_distance = target_x - start_offset
        
        print(f"[CAPTCHA] Start offset: {start_offset}px")
        print(f"[CAPTCHA] Target X: {target_x}px")
        print(f"[CAPTCHA] Drag distance: {drag_distance}px")
        
        # Get drag handle position
        handle_box = await drag_handle.bounding_box()
        if not handle_box:
            print("[CAPTCHA] Could not get drag handle position")
            return False
        
        start_x = handle_box['x'] + handle_box['width'] / 2
        start_y = handle_box['y'] + handle_box['height'] / 2
        
        # Simulate human-like drag
        print("[CAPTCHA] Performing drag...")
        await human_like_drag(page, start_x, start_y, drag_distance)
        
        # Wait a moment and check if CAPTCHA disappeared
        await asyncio.sleep(1.0)
        
        # Check if CAPTCHA is still visible
        is_visible = await page.locator('#captcha_container').is_visible()
        
        if not is_visible:
            print("[CAPTCHA] ✓ Solved successfully!")
            return True
        else:
            print("[CAPTCHA] ✗ CAPTCHA still visible, may need retry")
            return False
            
    except Exception as e:
        print(f"[CAPTCHA] Error: {e}")
        return False


async def human_like_drag(page, start_x: float, start_y: float, distance: float):
    """
    Simulate a human-like drag motion with:
    - Slight randomness in path
    - Variable speed (slow start, fast middle, slow end)
    - Small overshoot and correction
    """
    # Move to start position
    await page.mouse.move(start_x, start_y)
    await asyncio.sleep(random.uniform(0.1, 0.2))
    
    # Mouse down
    await page.mouse.down()
    await asyncio.sleep(random.uniform(0.05, 0.1))
    
    # Generate human-like path
    # Use easing function for natural acceleration/deceleration
    steps = random.randint(20, 35)
    
    for i in range(steps):
        # Easing: slow-fast-slow (ease-in-out)
        t = i / steps
        # Cubic ease-in-out
        if t < 0.5:
            eased_t = 4 * t * t * t
        else:
            eased_t = 1 - pow(-2 * t + 2, 3) / 2
        
        # Current position
        current_x = start_x + distance * eased_t
        
        # Add slight vertical wobble (humans aren't perfectly horizontal)
        wobble_y = start_y + random.uniform(-2, 2)
        
        # Add slight horizontal noise
        noise_x = current_x + random.uniform(-1, 1)
        
        await page.mouse.move(noise_x, wobble_y)
        
        # Variable delay (faster in middle)
        if t < 0.2 or t > 0.8:
            delay = random.uniform(0.02, 0.04)
        else:
            delay = random.uniform(0.008, 0.015)
        await asyncio.sleep(delay)
    
    # Small overshoot
    overshoot = random.uniform(2, 5)
    await page.mouse.move(start_x + distance + overshoot, start_y + random.uniform(-1, 1))
    await asyncio.sleep(random.uniform(0.05, 0.1))
    
    # Correct back
    await page.mouse.move(start_x + distance, start_y)
    await asyncio.sleep(random.uniform(0.1, 0.2))
    
    # Mouse up
    await page.mouse.up()


def test_with_images(bg_path: str, piece_path: str):
    """Test the solver with local image files"""
    background = cv2.imread(bg_path)
    piece = cv2.imread(piece_path, cv2.IMREAD_UNCHANGED)
    
    if background is None:
        print(f"Could not load background: {bg_path}")
        return
    if piece is None:
        print(f"Could not load piece: {piece_path}")
        return
    
    print(f"Background: {background.shape}")
    print(f"Piece: {piece.shape}")
    
    target_x = find_slot_position(background, piece)
    print(f"\nResult: Drag to X = {target_x}")
    
    # Visualize result
    result = background.copy()
    cv2.line(result, (target_x, 0), (target_x, result.shape[0]), (0, 255, 0), 2)
    
    output_path = Path(bg_path).parent / "captcha_solution.png"
    cv2.imwrite(str(output_path), result)
    print(f"Visualization saved to: {output_path}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) >= 3:
        # Test with local images
        test_with_images(sys.argv[1], sys.argv[2])
    else:
        print("Usage: python tiktok_captcha_solver.py <background.png> <piece.png>")
        print("\nOr import and use with Playwright:")
        print("  from tiktok_captcha_solver import solve_captcha")
        print("  await solve_captcha(page)")
