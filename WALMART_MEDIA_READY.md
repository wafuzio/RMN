# ✅ Walmart Media-Aware Cards - READY!

## What Was Implemented

### Problem Solved
Video files (`.mp4`) were appearing in `image_url` fields, causing Builder.io to fail when trying to render them in `<img>` tags.

### Solution
**Media-aware card system** that separates images and videos:
- **Grid:** Always displays images (never videos)
- **Modal:** Shows videos when available, with poster images
- **Backward compatible:** Image-only ads still work perfectly

---

## Changes Made

### 🔧 Backend (Flask API)

**File:** `web/builder_server_v2.py`

**New Functions:**
1. `is_video_filename(name)` - Detects video files by extension
2. `find_poster_for_video(retailer, client, video_path)` - Finds matching poster image
3. `build_media_urls_for_ad(retailer, client, ad)` - Returns `{image_url, video_url, poster_url}`

**New Endpoint:**
- `GET /api/video/<retailer>/<client>/<path>` - Serves video files with robust resolution

**Updated Endpoint:**
- `GET /api/ads/cards` - Now returns `video_url` and `poster_url` when available

### 🌐 Frontend (Vite Proxy)

**New File:** `neon-sanctuary/server/routes/video.ts`
- Video proxy handler (mirrors image proxy)

**Updated File:** `neon-sanctuary/server/index.ts`
- Added video proxy route: `/api/video/:retailer/:client/*`

---

## Card Structure

### Before (Broken)
```json
{
  "image_url": "/api/image/walmart/client/SBV/video.mp4",  // ❌ Breaks <img> tag
  "brand": "Halo Top"
}
```

### After (Fixed)
```json
{
  "image_url": "/api/image/walmart/client/SBV/poster.png",  // ✅ Grid displays image
  "video_url": "/api/video/walmart/client/SBV/video.mp4",   // ✅ Modal plays video
  "poster_url": "/api/image/walmart/client/SBV/poster.png", // ✅ Video thumbnail
  "brand": "Halo Top",
  "ad_type": "SBV"
}
```

---

## Testing

### 1. Restart Servers

```bash
./restart_servers.sh
```

### 2. Run Media Test

```bash
./test_media_cards.sh
```

**Expected Output:**
```
✅ API returned 10 cards
✅ All 10 cards have image_url
✅ Found 5 cards with video_url
✅ All 5 video cards have poster_url
✅ Video endpoint working (HTTP 200)
✅ Image endpoint working (HTTP 200)
```

### 3. Manual API Test

```bash
# Get cards with media fields
curl "http://localhost:5006/api/ads/cards?retailer=walmart&client=halo_top&page_size=10" | \
  jq '.cards[] | {brand, ad_type, image_url, video_url, poster_url}'
```

### 4. Test Specific Endpoints

```bash
# Test image endpoint
curl -I "http://localhost:5006/api/image/walmart/halo_top/SBA/test.png"

# Test video endpoint
curl -I "http://localhost:5006/api/video/walmart/halo_top/SBV/test.mp4"
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
```

**In Image Component:**
```html
<img src="${base}${card.image_url}" alt="${card.brand}" />
```

### Modal/Detail View (Video Support)

**Add to modal Custom Code block:**

```javascript
const base = 'https://<your-ngrok>.ngrok-free.dev';

if (card.video_url) {
  // Show video with poster
  return `
    <video 
      controls 
      playsinline 
      preload="metadata"
      poster="${base}${card.poster_url || card.image_url}"
      src="${base}${card.video_url}"
      style="width:100%; border-radius: 12px;">
    </video>
  `;
} else {
  // Fallback: show large image
  return `
    <img 
      src="${base}${card.image_url}" 
      alt="${card.brand}"
      style="width:100%; border-radius: 12px;" 
    />
  `;
}
```

---

## How It Works

### 1. Ad Has Video File

**JSON:** `ad.image_path = "SBV/walmart__yasso__sbv__client__kw__D2025-10-24_T14-13.00_1.mp4"`

**API Processing:**
1. Detects `.mp4` extension → It's a video
2. Sets `video_url = "/api/video/walmart/client/SBV/...mp4"`
3. Searches for poster: `SBV/walmart__yasso__sbv__client__kw__D2025-10-24_T14-13.00_1.png`
4. Sets `image_url = "/api/image/walmart/client/SBV/...png"` (for grid)
5. Sets `poster_url = "/api/image/walmart/client/SBV/...png"` (for video tag)

**Result:** Grid shows poster image, modal plays video

### 2. Ad Has Image File

**JSON:** `ad.image_path = "SBA/walmart__outshine__sba__client__kw__D2025-10-24_T14-14.21_1.png"`

**API Processing:**
1. Detects `.png` extension → It's an image
2. Sets `image_url = "/api/image/walmart/client/SBA/...png"`
3. No `video_url` or `poster_url`

**Result:** Grid shows image, modal shows large image

### 3. Ad Has No image_path

**JSON:** `ad.image_path = null` (but image file exists on disk)

**API Processing:**
1. Tries fuzzy matching by filename
2. Finds image in filesystem
3. Sets `image_url` if found
4. Skips card if no image found

**Result:** Card renders thanks to fuzzy matching

---

## Benefits

✅ **Grid never breaks** - Always displays images, never videos
✅ **Videos available** - Accessible in modal/detail view  
✅ **Poster images** - Videos have thumbnails for better UX
✅ **Backward compatible** - Image-only ads still work
✅ **Robust resolution** - Uses same fuzzy matching as images
✅ **No .mp4 in <img>** - Prevents Builder.io rendering errors

---

## Ad Type Coverage

### Walmart Ad Types

| Ad Type | Has Video? | Grid Display | Modal Display |
|---------|-----------|--------------|---------------|
| **SBA** (Sponsored Brand Ads) | ❌ No | Image | Large Image |
| **SBV** (Sponsored Brand Video) | ✅ Yes | Poster Image | Video Player |
| **Tile_Takeover** | ❌ No | Image | Large Image |

---

## Files Created/Modified

### Created
- ✅ `neon-sanctuary/server/routes/video.ts` - Video proxy handler
- ✅ `docs/MEDIA_AWARE_CARDS.md` - Technical documentation
- ✅ `test_media_cards.sh` - Automated test script
- ✅ `WALMART_MEDIA_READY.md` - This file

### Modified
- ✅ `web/builder_server_v2.py` - Added media-aware functions + video endpoint
- ✅ `neon-sanctuary/server/index.ts` - Registered video proxy route

---

## Verification Checklist

- [ ] Servers restarted: `./restart_servers.sh`
- [ ] Test script passes: `./test_media_cards.sh`
- [ ] API returns cards with `image_url`: `curl localhost:5006/api/ads/cards?retailer=walmart&client=halo_top`
- [ ] Video cards have `video_url` and `poster_url`
- [ ] Image endpoint works: `curl -I localhost:5006/api/image/...`
- [ ] Video endpoint works: `curl -I localhost:5006/api/video/...`
- [ ] Builder.io grid displays images (no broken `<img>` tags)
- [ ] Builder.io modal plays videos for SBV ads
- [ ] Builder.io modal shows large images for SBA/Tile_Takeover ads

---

## Next Steps

1. **Restart servers:**
   ```bash
   ./restart_servers.sh
   ```

2. **Run tests:**
   ```bash
   ./test_media_cards.sh
   ```

3. **Update Builder.io:**
   - Add video support to modal (see code above)
   - Test with Walmart SBV ads

4. **Monitor:**
   - Check Flask logs: `tail -f logs/flask.log`
   - Check Vite logs: `tail -f logs/vite.log`

---

## Troubleshooting

### "No video_url in cards"
- **Cause:** Client has no SBV ads or videos not saved
- **Fix:** Run scraper for client with video ads, or test with `halo_top` client

### "Video endpoint returns 404"
- **Cause:** Video file not found on disk
- **Fix:** Check file exists: `ls output/walmart/client/SBV/*.mp4`

### "Poster not found"
- **Cause:** No matching `.png` for `.mp4` file
- **Fix:** Scraper should save both video and poster; check scraper output

### "Grid shows broken images"
- **Cause:** `image_url` points to video file
- **Fix:** Restart servers to load new `build_media_urls_for_ad()` code

---

**Status:** ✅ READY FOR TESTING
**Last Updated:** 2025-10-27
**Tested:** Pending restart + test script
