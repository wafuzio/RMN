# Video Overlay Calibration Guide

This guide explains how to calibrate and implement pixel-perfect video overlays for retail ad platforms.

## Overview

Retail ads often contain video slots embedded within static banner images. To display these properly in the dashboard, we need to:

1. **Identify** the video slot position and dimensions on a reference ad
2. **Calculate** proportional overlay metadata for all ads
3. **Store** the metadata in JSON for the API to serve
4. **Render** the overlay using the metadata in the frontend

---

## Step 1: Identify the Video Slot

### Find a Reference Ad

1. Choose a representative ad with a video from the retailer/ad type you're calibrating
2. Note the **exact image dimensions** (e.g., 1078x341 for Walmart SBV)
3. Open the image in an image editor or browser dev tools

### Measure the Video Slot

You need to determine 4 values in **pixels**:
- **x**: Left edge position (distance from left side of image)
- **y**: Top edge position (distance from top of image)
- **width**: Width of the video slot
- **height**: Height of the video slot

**Methods to measure:**

#### Method A: Browser Dev Tools (Recommended)
1. Create a test page that displays the image and video overlay
2. Use CSS to position a colored `<div>` over the image
3. Adjust the div's position/size until it perfectly covers the video slot
4. Read the final CSS values (top, left, width, height)

#### Method B: Image Editor
1. Open the ad image in Photoshop/GIMP/Figma
2. Use the rectangle selection tool to select the video area
3. Read the selection dimensions from the info panel

#### Method C: Manual Calculation
1. Identify visual landmarks (borders, text, product images)
2. Estimate the video slot boundaries
3. Measure pixel distances using a ruler tool

---

## Step 2: Create the Calibration Script

### Example: Walmart SBV Ads

```python
#!/usr/bin/env python3
"""
Add video_overlay metadata to all [RETAILER] [AD_TYPE] ads.
"""

import json
from pathlib import Path
from PIL import Image

# Reference image dimensions (the ad you measured)
REFERENCE_IMAGE_WIDTH = 1078
REFERENCE_IMAGE_HEIGHT = 341

# Video slot dimensions on the reference image (in pixels)
VIDEO_OVERLAY_PX = {
    "x": 2,
    "y": 15,
    "width": 539,
    "height": 309,
}

def get_image_dimensions(image_path):
    """Get the natural dimensions of an image file."""
    try:
        with Image.open(image_path) as img:
            return img.width, img.height
    except Exception as e:
        print(f"  ⚠️  Could not read image {image_path}: {e}")
        return None, None

def process_json_file(json_path):
    """Process a single JSON file and add video_overlay metadata."""
    print(f"\n📄 Processing: {json_path}")
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    ads = data.get('ads', [])
    updated_count = 0
    
    for ad in ads:
        # Filter for the specific ad type
        ad_type = ad.get('type') or ad.get('ad_type')
        if ad_type != 'SBV':  # Change this to your ad type
            continue
        
        # Get image path
        image_path_rel = ad.get('image_path')
        if not image_path_rel:
            continue
        
        # Construct full image path
        json_dir = Path(json_path).parent
        client_dir = json_dir.parent.parent
        image_path = client_dir / image_path_rel
        
        # Check if video file exists
        video_path = image_path.with_suffix('.mp4')
        if not video_path.exists():
            continue
        
        # Get actual image dimensions
        img_width, img_height = get_image_dimensions(image_path)
        if not img_width or not img_height:
            continue
        
        # Calculate proportional overlay dimensions
        scale_x = img_width / REFERENCE_IMAGE_WIDTH
        scale_y = img_height / REFERENCE_IMAGE_HEIGHT
        
        overlay_x = round(VIDEO_OVERLAY_PX["x"] * scale_x)
        overlay_y = round(VIDEO_OVERLAY_PX["y"] * scale_y)
        overlay_width = round(VIDEO_OVERLAY_PX["width"] * scale_x)
        overlay_height = round(VIDEO_OVERLAY_PX["height"] * scale_y)
        
        # Add video_url if not present
        if not ad.get('video_url'):
            video_path_rel = str(Path(image_path_rel).with_suffix('.mp4'))
            ad['video_url'] = video_path_rel
        
        # Add/update video_overlay metadata
        ad['video_overlay'] = {
            "x": overlay_x,
            "y": overlay_y,
            "width": overlay_width,
            "height": overlay_height,
            "image_width": img_width,
            "image_height": img_height,
        }
        
        updated_count += 1
        print(f"  ✓ Added overlay to: {ad.get('brand', 'unknown')} ({img_width}x{img_height})")
    
    if updated_count > 0:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"  💾 Updated {updated_count} ad(s)")
    
    return updated_count

def main():
    """Process all JSON files."""
    output_dir = Path('output/walmart')  # Change to your retailer
    json_files = list(output_dir.glob('*/runs/*/run_results_*.json'))
    
    total_updated = 0
    for json_file in sorted(json_files):
        updated = process_json_file(json_file)
        total_updated += updated
    
    print(f"\n✅ Complete! Updated {total_updated} ad(s)")

if __name__ == '__main__':
    main()
```

---

## Step 3: Test and Refine

### Create a Test Page

Create a dedicated test page to verify alignment:

```typescript
// client/pages/VideoOverlayTest.tsx
export default function VideoOverlayTest() {
  const videoMetadata: VideoOverlay = {
    x: 2,
    y: 15,
    width: 539,
    height: 309,
    image_width: 1078,
    image_height: 341,
  };

  const calculateOverlay = useCallback((
    metadata: VideoOverlay,
    imgEl: HTMLImageElement | null,
    containerEl: HTMLElement | null
  ): any => {
    if (!metadata || !imgEl || !containerEl) return null;

    const containerRect = containerEl.getBoundingClientRect();
    const imgRect = imgEl.getBoundingClientRect();
    
    // Calculate image offset within container (for centering)
    const offsetX = imgRect.left - containerRect.left;
    const offsetY = imgRect.top - containerRect.top;
    
    // Calculate scale based on rendered vs natural size
    const scaleX = imgRect.width / metadata.image_width;
    const scaleY = imgRect.height / metadata.image_height;

    return {
      left: offsetX + (metadata.x * scaleX),
      top: offsetY + (metadata.y * scaleY),
      width: metadata.width * scaleX,
      height: metadata.height * scaleY,
    };
  }, []);

  // ... render image and video with overlay
}
```

### Iterative Refinement

1. **Run the script** to apply initial metadata
2. **View test ads** in the dashboard
3. **Identify misalignment** (gaps, overlaps, offsets)
4. **Adjust reference values** in the script:
   - Gap at top? → Decrease `y`
   - Gap at bottom? → Increase `height`
   - Gap at left? → Decrease `x`
   - Gap at right? → Increase `width`
   - Video too wide? → Decrease `width`
   - Video too narrow? → Increase `width`
5. **Re-run the script** to update all ads
6. **Repeat** until alignment is pixel-perfect

### Common Adjustments

**Walmart SBV Example:**
- Initial calibration: `x=0, y=18, width=544, height=301`
- After testing: `x=2, y=19, width=539, height=305` (shift right, down, narrower)
- Final values: `x=2, y=15, width=539, height=309` (shift up, taller)

**Tips:**
- Start with conservative values (slightly smaller overlay)
- Test on multiple ads with different image dimensions
- Look for patterns in misalignment across ads
- Make small adjustments (1-5 pixels) at a time

---

## Step 4: Backend Integration

### Add to Shared Types

```typescript
// shared/api.ts
export interface VideoOverlay {
  x: number;
  y: number;
  width: number;
  height: number;
  image_width: number;
  image_height: number;
}

export interface AdCardItem {
  // ... other fields
  video_overlay?: VideoOverlay;
}
```

### Update Flask API

```python
# web/builder_server_v2.py
# In the card building section:

# Include video_overlay metadata if present
if ad.get("video_overlay"):
    card["video_overlay"] = ad["video_overlay"]
```

---

## Step 5: Frontend Implementation

### Main Modal Component

```typescript
// client/components/dashboard/AdModal.tsx
const calculateOverlay = useCallback((
  metadata: VideoOverlay,
  imgEl: HTMLImageElement | null,
  containerEl: HTMLElement | null
): any => {
  if (!metadata || !imgEl || !containerEl) return null;

  const containerRect = containerEl.getBoundingClientRect();
  const imgRect = imgEl.getBoundingClientRect();
  
  const offsetX = imgRect.left - containerRect.left;
  const offsetY = imgRect.top - containerRect.top;
  
  const scaleX = imgRect.width / metadata.image_width;
  const scaleY = imgRect.height / metadata.image_height;

  return {
    left: offsetX + (metadata.x * scaleX),
    top: offsetY + (metadata.y * scaleY),
    width: metadata.width * scaleX,
    height: metadata.height * scaleY,
  };
}, []);

// Use in render:
const overlayPosition = calculateOverlay(
  ad.video_overlay,
  imageRef.current,
  containerRef.current
);

<video
  style={{
    position: 'absolute',
    top: `${overlayPosition.top}px`,
    left: `${overlayPosition.left}px`,
    width: `${overlayPosition.width}px`,
    height: `${overlayPosition.height}px`,
  }}
/>
```

---

## Retailer-Specific Notes

### Walmart SBV
- **Image dimensions:** Vary (1078x333 to 1090x371)
- **Video position:** Left half of banner
- **Reference:** 1078x341
- **Overlay:** x=2, y=15, width=539, height=309

### Instacart (To Be Calibrated)
- **Image dimensions:** TBD
- **Video position:** TBD
- **Reference:** TBD
- **Overlay:** TBD

---

## Troubleshooting

### Videos Not Showing
- Check that `video_url` field is set in JSON
- Verify video file exists at the path
- Check Flask API is returning `video_overlay` in response

### Misalignment in Fullscreen
- Ensure container offset calculation includes fullscreen container
- Check that image is fully loaded before calculating overlay
- Use `useEffect` with proper dependencies to recalculate on fullscreen toggle

### Inconsistent Alignment
- Verify all ads have correct `image_width` and `image_height` in metadata
- Check that proportional scaling is being applied correctly
- Test with ads of different dimensions to ensure scaling works

### Video Shifting on Reload
- Store overlay position in state, not recalculate on every render
- Use `useCallback` to memoize calculation function
- Only recalculate when image actually loads, not on every state change

---

## Checklist

- [ ] Identify reference ad with video
- [ ] Measure video slot dimensions (x, y, width, height)
- [ ] Create calibration script with reference values
- [ ] Run script on test ad, verify in browser
- [ ] Iteratively refine values until pixel-perfect
- [ ] Run script on all ads to apply metadata
- [ ] Update backend API to serve video_overlay
- [ ] Implement frontend overlay calculation
- [ ] Test on multiple ads with varying dimensions
- [ ] Commit changes to git

---

## Example: Walmart SBV Implementation

See:
- Script: `scripts/add_sbv_overlay_metadata.py`
- Test page: `client/pages/VideoOverlayTest.tsx`
- Backend: `web/builder_server_v2.py` (line 1571)
- Types: `shared/api.ts` (VideoOverlay interface)

**Results:** 589 Walmart SBV ads with pixel-perfect video overlay alignment across varying image dimensions (1078x333 to 1090x371).
