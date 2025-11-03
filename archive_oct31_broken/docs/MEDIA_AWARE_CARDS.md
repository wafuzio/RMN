# Media-Aware Card System (Images + Videos)

**Problem:** Video files (`.mp4`) were appearing in `image_url` fields, causing Builder.io to fail when trying to render them in `<img>` tags.

**Solution:** Separate image and video handling - images for grid display, videos as optional secondary media for modals.

---

## Architecture

### Card Structure

```typescript
{
  // Required for grid display
  "image_url": "/api/image/walmart/client/SBV/poster.png",
  
  // Optional for modal/detail view
  "video_url": "/api/video/walmart/client/SBV/video.mp4",
  "poster_url": "/api/image/walmart/client/SBV/poster.png",
  
  // Other card fields...
  "brand": "Halo Top",
  "ad_type": "SBV",
  // ...
}
```

### Strategy

1. **Grid:** Always displays `image_url` (never a video)
2. **Modal:** Shows video if `video_url` exists, otherwise shows large image
3. **Poster:** Video `<video>` tag uses `poster_url` for thumbnail

---

## Backend Implementation

### Flask API (`web/builder_server_v2.py`)

#### 1. Helper Functions

```python
def is_video_filename(name: str) -> bool:
    """Check if filename is a video file"""
    return str(name).lower().endswith((".mp4", ".webm", ".mov", ".m4v"))

def find_poster_for_video(retailer: str, client: str, rel_video_path: str) -> str | None:
    """
    Find a poster image with the same basename as the video.
    Looks in same folder, then Main/ folder.
    """
    base = Path(rel_video_path).with_suffix("")
    # Try same folder
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        candidate = f"{base}{ext}"
        f2, r2 = find_image_file(retailer, client, candidate)
        if f2: return r2
    # Try Main/ folder
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        candidate = f"Main/{base.name}{ext}"
        f2, r2 = find_image_file(retailer, client, candidate)
        if f2: return r2
    return None

def build_media_urls_for_ad(retailer: str, client: str, ad: dict) -> dict:
    """
    Returns: {
      "image_url": str (always for grid),
      "video_url": str (optional for modal),
      "poster_url": str (optional for video poster)
    }
    """
    media = {}
    
    # Get canonical or legacy path
    rel = (ad.get("image_path") or ad.get("screenshot"))
    if not rel:
        for k, v in ad.items():
            if isinstance(k, str) and k.endswith("_image_path") and v:
                rel = v
                break
    
    # If path is a video
    if rel and is_video_filename(rel):
        f, r = find_image_file(retailer, client, rel)
        if f:
            media["video_url"] = f"/api/video/{retailer}/{client}/{r}"
            poster_rel = find_poster_for_video(retailer, client, r)
            if poster_rel:
                media["image_url"] = f"/api/image/{retailer}/{client}/{poster_rel}"
                media["poster_url"] = f"/api/image/{retailer}/{client}/{poster_rel}"
    
    # If path is an image
    elif rel:
        f, r = find_image_file(retailer, client, rel)
        if f:
            media["image_url"] = f"/api/image/{retailer}/{client}/{r}"
    
    # Fallback: try CDN URL by filename
    if "image_url" not in media:
        cdn = ad.get("image_url")
        if isinstance(cdn, str) and cdn.strip():
            name = Path(cdn.split("?")[0]).name
            if name and not is_video_filename(name):
                f, r = find_image_file(retailer, client, name)
                if f:
                    media["image_url"] = f"/api/image/{retailer}/{client}/{r}"
    
    return media
```

#### 2. Video Endpoint

```python
@app.route("/api/video/<retailer>/<client>/<path:req_relpath>", methods=["GET"])
def api_video(retailer, client, req_relpath):
    """Serve video files with same robust resolution as images"""
    retailer = (retailer or "").lower().strip()
    client = (client or "").strip()
    if not retailer or not client or not req_relpath:
        abort(400, description="Missing retailer/client/path")

    fpath, rel = find_image_file(retailer, client, req_relpath)
    if not fpath or not fpath.is_file():
        abort(404, description=f"Video not found: {req_relpath}")

    ctype = "video/mp4" if str(fpath).lower().endswith(".mp4") else \
            (mimetypes.guess_type(str(fpath))[0] or "application/octet-stream")
    return send_file(str(fpath), mimetype=ctype, as_attachment=False, conditional=True)
```

#### 3. Cards Endpoint Update

```python
# In /api/ads/cards loop
media = build_media_urls_for_ad(retailer, client, ad)

# Only include cards with an image for the grid
image_api = media.get("image_url")
if not image_api:
    continue

# Build card
card = {
    "retailer": retailer,
    "client": client,
    "image_url": image_api,
    # ... other fields
}

# Attach optional video for modal
if media.get("video_url"):
    card["video_url"] = media["video_url"]
if media.get("poster_url"):
    card["poster_url"] = media["poster_url"]

all_cards.append(card)
```

---

## Frontend Implementation

### Vite Proxy (`neon-sanctuary/server/`)

#### 1. Video Proxy Route (`routes/video.ts`)

```typescript
import { RequestHandler } from "express";

const FLASK_BASE_URL = process.env.FLASK_BASE_URL || "http://localhost:5006";

export const handleVideoProxy: RequestHandler = async (req, res) => {
  const { retailer, client, filename } = req.params;

  if (!retailer || !client || !filename) {
    return res.status(400).json({ 
      error: "retailer, client, and filename are required" 
    });
  }

  let flaskUrl = `${FLASK_BASE_URL}/api/video/${retailer}/${client}/${filename}`;
  const queryString = new URLSearchParams(req.query as Record<string, string>).toString();
  if (queryString) {
    flaskUrl += `?${queryString}`;
  }

  try {
    const response = await fetch(flaskUrl, {
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "ngrok-skip-browser-warning": "true",
      },
    });

    if (!response.ok) {
      return res.status(response.status).json({ 
        error: `Failed to fetch video: ${response.statusText}` 
      });
    }

    const contentType = response.headers.get("content-type");
    if (!contentType || !contentType.startsWith("video/")) {
      return res.status(400).json({ error: "Response is not a video" });
    }

    res.set("Content-Type", contentType);
    res.set("Cache-Control", "public, max-age=86400");
    res.set("Access-Control-Allow-Origin", "*");
    res.set("Access-Control-Allow-Methods", "GET");

    const buffer = await response.arrayBuffer();
    res.send(Buffer.from(buffer));
  } catch (error) {
    res.status(500).json({ error: "Failed to proxy video from Flask backend" });
  }
};
```

#### 2. Register Route (`server/index.ts`)

```typescript
import { handleVideoProxy } from "./routes/video";

// In createServer():
app.get(/^\/api\/video\/([^/]+)\/([^/]+)\/(.+)$/, (req, res, next) => {
  req.params.retailer = req.params[0];
  req.params.client = req.params[1];
  req.params.filename = req.params[2];
  return handleVideoProxy(req, res, next);
});
```

---

## Builder.io Integration

### Grid Display (Images Only)

```javascript
const base = 'https://<your-ngrok>.ngrok-free.dev';

// Fetch cards
fetch(`${base}/api/ads/cards?retailer=walmart&client=${client}&page_size=24`, {
  headers: { 'ngrok-skip-browser-warning': 'true' }
})
  .then(r => r.json())
  .then(data => {
    state.adCards = data.cards;
  });

// In grid Image component
<img src={`${base}${card.image_url}`} alt={card.brand} />
```

### Modal/Detail View (Video Support)

```javascript
// In modal Custom Code block
const base = 'https://<your-ngrok>.ngrok-free.dev';

if (card.video_url) {
  // Show video with poster
  return (
    <video 
      controls 
      playsinline 
      preload="metadata"
      poster={base + (card.poster_url || card.image_url)}
      src={base + card.video_url}
      style="width:100%; border-radius: 12px;">
    </video>
  );
} else {
  // Fallback: show large image
  return (
    <img 
      src={base + card.image_url} 
      alt={card.brand}
      style="width:100%; border-radius: 12px;" 
    />
  );
}
```

---

## Testing

### 1. Test API Returns Media Fields

```bash
curl "http://localhost:5006/api/ads/cards?retailer=walmart&client=halo_top&page_size=10" | \
  jq '.cards[] | {brand, ad_type, image_url, video_url, poster_url}'
```

**Expected:**
- All cards have `image_url`
- SBV cards have `video_url` and `poster_url`
- SBA/Tile_Takeover cards have only `image_url`

### 2. Test Video Endpoint

```bash
# Get a video URL from cards response
VIDEO_URL=$(curl -s "http://localhost:5006/api/ads/cards?retailer=walmart&client=halo_top&page_size=10" | \
  jq -r '.cards[] | select(.video_url != null) | .video_url' | head -1)

# Test video endpoint
curl -I "http://localhost:5006${VIDEO_URL}"
```

**Expected:** `200 OK` with `Content-Type: video/mp4`

### 3. Test Vite Proxy

```bash
# Through Vite dev server
curl -I "http://localhost:3000${VIDEO_URL}"
```

**Expected:** `200 OK` with video streaming

### 4. Test in Builder.io

1. Load cards in Builder.io
2. Verify grid shows images (no broken `<img>` tags)
3. Click card to open modal
4. Verify video plays if `video_url` exists

---

## File Changes Summary

### Backend (Flask)
- `web/builder_server_v2.py`:
  - Added `is_video_filename()`
  - Added `find_poster_for_video()`
  - Added `build_media_urls_for_ad()`
  - Added `/api/video` endpoint
  - Updated `/api/ads/cards` to use `build_media_urls_for_ad()`

### Frontend (Vite)
- `neon-sanctuary/server/routes/video.ts`: **NEW** - Video proxy handler
- `neon-sanctuary/server/index.ts`: Added video proxy route registration

---

## Benefits

✅ **Grid never breaks** - Always displays images, never videos
✅ **Videos available** - Accessible in modal/detail view
✅ **Poster images** - Videos have thumbnails for better UX
✅ **Backward compatible** - Image-only ads still work
✅ **Robust resolution** - Uses same fuzzy matching as images

---

## Next Steps

1. **Restart servers:**
   ```bash
   ./restart_servers.sh
   ```

2. **Test API:**
   ```bash
   curl "http://localhost:5006/api/ads/cards?retailer=walmart&client=halo_top&page_size=10" | jq
   ```

3. **Update Builder.io:**
   - Add video support to modal
   - Test with SBV ads (Sponsored Brand Video)

---

**Last Updated:** 2025-10-27
**Status:** ✅ Ready for Testing
