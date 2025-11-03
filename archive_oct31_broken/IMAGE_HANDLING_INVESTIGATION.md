# Image Handling Architecture Investigation

## Executive Summary

Your image/video handling implementation is **mostly aligned** with the documented "before vs after" changes, but there are **3 misalignments** between the Flask API contract and the TypeScript type definitions that should be fixed, plus **critical environment configuration** that could cause "zero cards."

---

## What's Actually Implemented ✓

### 1. **Express Proxy Routes** (neon-sanctuary/server/index.ts)
```typescript
// Lines 48-59: Both routes correctly configured with regex to capture nested paths
app.get(/^\/api\/image\/([^/]+)\/([^/]+)\/(.+)$/, ...)  // ✓ Captures /retailer/client/path/to/file
app.get(/^\/api\/video\/([^/]+)\/([^/]+)\/(.+)$/, ...)  // ✓ Handles multi-level paths
```
**Status**: ✅ Correctly matches nested paths like `walmart/client/SBA/walmart__brand__sba__...png`

### 2. **Image/Video Proxy Handlers** (routes/image.ts, routes/video.ts)
- Forward requests to Flask at `http://localhost:5006`
- Validate response is correct MIME type (image/* or video/*)
- Set CORS headers appropriately
**Status**: ✅ Working correctly

### 3. **Flask Image Resolution** (web/builder_server_v2.py, lines 47-141)
```python
def resolve_image_path(ad: dict) -> str | None:
    # Canonical first, then legacy fallbacks
    p = ad.get("image_path") or ad.get("screenshot")  # ✓ New canonical
    # Then tries *_image_path, screenshot, etc.        # ✓ Legacy fallbacks
```
**Status**: ✅ Correctly implements canonical-first approach

### 4. **Media URL Builder** (web/builder_server_v2.py, lines 171-229)
```python
def build_media_urls_for_ad(retailer: str, client: str, ad: dict) -> dict:
    # Returns: {"image_url": "...", "video_url": "...", "poster_url": "..."}
```
**Status**: ✅ Building media URLs with fuzzy fallback for CDN filenames

### 5. **Strict Card Filtering** (web/builder_server_v2.py, lines 995-997)
```python
# Only include cards with an image for the grid (skip if no image available)
image_api = media.get("image_url")
if not image_api:
    continue  # ✓ Skip cards without resolvable images
```
**Status**: ✅ Correctly skipping cards without images

### 6. **Date Range Filtering** (web/builder_server_v2.py, lines 1077-1101)
```python
if start_date or end_date:
    filtered_cards = []
    for card in all_cards:
        timestamp = card.get("timestamp", "")
        card_date = timestamp.split()[0] if timestamp else ""
        # Correctly compares YYYY-MM-DD format
```
**Status**: ✅ Correctly extracting and comparing dates

### 7. **Image URL Resolution** (neon-sanctuary/client/utils/imageUrl.ts)
```typescript
export function toLocalImageUrl(u?: string) {
    // Ensures all relative paths start with /api
    if (!trimmed.startsWith('/api')) {
        return `/api${trimmed.startsWith('/') ? '' : '/'}${trimmed}`;
    }
    return trimmed;
}
```
**Status**: ✅ Correctly prepending `/api` for proxy routing

---

## ���� TYPE MISALIGNMENTS

### Issue 1: Missing video_url and poster_url in TypeScript Types

**What Flask Returns** (builder_server_v2.py, lines 1049-1060):
```python
card = {
    "image_url": image_api,
    "video_url": media["video_url"],      # ← Returned here
    "poster_url": media["poster_url"],    # ← Returned here
    # ... other fields
}
```

**What TypeScript Expects** (neon-sanctuary/shared/api.ts):
```typescript
export interface AdCardItem {
  retailer: string;
  client: string;
  keyword: string;
  ad_type: string;
  brand: string;
  message: string;
  image_url: string;
  timestamp: string;
  // ❌ MISSING: video_url, poster_url
}
```

**Impact**: 
- Frontend will ignore `video_url` and `poster_url` from API response
- No type safety when these fields are added to response
- These fields will still be in the actual JSON but ignored by TypeScript

**Recommendation**: Update interface:
```typescript
export interface AdCardItem {
  // ... existing fields ...
  image_url: string;
  video_url?: string;      // ← Add optional
  poster_url?: string;     // ← Add optional
  timestamp: string;
}
```

### Issue 2: Ad Interface Missing Optional Media Fields

**What's in AdCard.tsx** (line 195-198):
```typescript
export interface Ad {
  id: string;
  retailer: string; 
  client: string; 
  keyword: string; 
  ad_type: string; 
  brand: string; 
  message: string; 
  image_url: string; 
  timestamp: string;
  // ❌ MISSING: video_url, poster_url
}
```

**Recommendation**: Add optional fields:
```typescript
export interface Ad {
  id: string;
  retailer: string; 
  client: string; 
  keyword: string; 
  ad_type: string; 
  brand: string; 
  message: string; 
  image_url: string; 
  video_url?: string;    // ← Add optional
  poster_url?: string;   // ← Add optional
  timestamp: string;
}
```

### Issue 3: No Video Rendering in UI

The frontend has no video playback capability even though Flask is returning video URLs.

**Recommendation**: If video support is needed, add to AdModal.tsx:
```typescript
{media.get("video_url") && (
  <video 
    src={toLocalImageUrl(media.get("video_url"))} 
    poster={toLocalImageUrl(media.get("poster_url"))}
    controls
  />
)}
```

---

## 🟡 CRITICAL ENVIRONMENT CONFIGURATION

These issues can cause "zero cards" even if the API is correctly implemented:

### 1. **SCRAPER_HOME Mismatch**
**File**: web/builder_server_v2.py, line 37
```python
SCRAPER_HOME = os.environ.get("SCRAPER_HOME", project_root)
OUTPUT_ROOT = os.path.join(SCRAPER_HOME, "output")
```

**Problem**: If `SCRAPER_HOME` env var is not set or points to wrong path, Flask won't find any runs.

**Check**: 
```bash
echo $SCRAPER_HOME  # Should point to /absolute/path/to/Amazon_Scrape
# If not set, Flask defaults to project root which may not have output/
```

**Fix**: 
```bash
export SCRAPER_HOME=/absolute/path/to/Amazon_Scrape
# Then restart Flask server
```

### 2. **ALLOWED_ORIGINS Missing ngrok URL**
**File**: web/builder_server_v2.py, lines 40, 245-255
```python
ALLOWED_ORIGINS = set((os.environ.get("ALLOWED_ORIGINS") or "").split(",")) - {""}

def _is_allowed_origin(origin: str) -> bool:
    # localhost and ngrok are auto-allowed, but env list is checked if set
    if ALLOWED_ORIGINS:
        return origin in ALLOWED_ORIGINS  # ← Must be in env list
```

**Problem**: If `ALLOWED_ORIGINS` env var is set, only those origins work. If ngrok URL missing, CORS blocks all requests.

**Check**:
```bash
echo $ALLOWED_ORIGINS
# Should include: https://builder.io,https://cdn.builder.io,https://xxx.ngrok.io
```

**Fix**: If using ngrok:
```bash
export ALLOWED_ORIGINS="https://builder.io,https://cdn.builder.io,https://YOUR_NGROK_URL.ngrok.io"
```

### 3. **Flask Not Running on Port 5006**
**File**: neon-sanctuary/server/routes/image.ts, line 3
```typescript
const FLASK_BASE_URL = process.env.FLASK_BASE_URL || "http://localhost:5006";
```

**Problem**: If Flask isn't running, image/video proxies will fail silently, returning 500 errors.

**Check**:
```bash
curl http://localhost:5006/api/ping  # Should return {"ok": true, ...}
```

**Fix**: Start Flask server:
```bash
cd /path/to/project && python3 web/builder_server_v2.py
# Or set custom port: FLASK_PORT=5006 python3 web/builder_server_v2.py
```

---

## 🟠 POTENTIAL IMAGE RESOLUTION FAILURES

### Issue: Image Files Not Found on Disk

**Where it Fails**: web/builder_server_v2.py, lines 861-871 and 891-990

The API uses three strategies to find image files:
1. **Exact match** from `image_path` field in JSON
2. **Fallback search** in allowed ad-type folders (SBA, SBV, Tile_Takeover, Main, runs)
3. **Fuzzy match** by filename with timestamp/brand matching for Walmart

**Problem Indicators**:
```
⚠️  [walmart] Path in JSON doesn't exist: SBA/walmart__brand__sba__...
🔍 [walmart] Searching for image: ad_type=sba, leaf=SBA
⚠️  [walmart] No matching image found for keyword=...
```

These log messages mean images are being skipped, resulting in fewer/zero cards.

**Investigation Steps**:
1. Check if images exist in filesystem:
   ```bash
   ls -la output/walmart/[client]/SBA/ | head -5
   ```

2. Check JSON has valid image_path:
   ```bash
   python3 -c "
   import json
   with open('output/walmart/[client]/runs/[run_id]/run_results_*.json') as f:
       data = json.load(f)
       for ad in data.get('ads', [])[:3]:
           print(ad.get('image_path'), ad.get('screenshot'), ad.get('type'))
   "
   ```

3. Check if filenames match:
   ```bash
   # If JSON has image_path="SBA/walmart__brand__sba__...", file should exist at:
   output/walmart/[client]/SBA/walmart__brand__sba__...
   ```

---

## 🟢 RECOMMENDATIONS

### Immediate (Fix Misalignments):
1. ✏️ Update `AdCardItem` interface to include optional `video_url` and `poster_url`
2. ✏️ Update `Ad` interface to include optional media fields
3. 🧪 Test that API response matches TypeScript types

### Short-term (Prevent "Zero Cards"):
1. ✅ Verify `SCRAPER_HOME` env var is set to correct absolute path
2. ✅ Verify `ALLOWED_ORIGINS` includes current ngrok URL
3. ✅ Verify Flask is running on port 5006
4. ✅ Check filesystem for image files matching JSON references

### Long-term (Future Enhancement):
1. Add video playback support to AdModal if needed
2. Add poster image support for video cards
3. Create debug endpoint to show image resolution attempts
4. Add metrics logging for "cards skipped due to missing images"

---

## Summary of What's Aligned vs. Not

| Aspect | Status | Notes |
|--------|--------|-------|
| Canonical image_path resolution | ✅ | Correctly tries image_path first, then legacy fallbacks |
| Strict image requirement | ✅ | Cards without images are skipped |
| Date filtering | ✅ | Correctly implemented |
| Express proxy routes | ✅ | Regex patterns correctly capture nested paths |
| Flask media URL builder | ✅ | Using new build_media_urls_for_ad() |
| Frontend image URL handling | ✅ | toLocalImageUrl() correctly prepends /api |
| **TypeScript types** | ❌ | Missing video_url, poster_url fields |
| **Video/Poster UI** | ⚠️ | Not implemented, but not required for grid view |
| **Environment config** | ⚠️ | Could cause zero cards if not properly set |

