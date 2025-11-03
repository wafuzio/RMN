# Walmart Builder.io Readiness Checklist

**Get every Walmart ad rendering in Builder.io**

---

## Quick Start

Run the automated doctor to check readiness:

```bash
python3 tools/walmart_readiness_doctor.py
```

Or follow the manual steps below.

---

## Step 0: Preflight - Confirm Servers Running

### Check server status

```bash
./check_servers.sh
```

**Expected output:**
- ✅ Flask API running on port 5006
- ✅ Vite dev server running on port 3000 (or 3001)
- ✅ ngrok tunnel active

### Get your ngrok URL

```bash
curl http://localhost:4040/api/tunnels | jq -r '.tunnels[] | select(.proto=="https") | .public_url'
```

Copy the URL (e.g., `https://abc123.ngrok-free.dev`)

### Set CORS and restart

```bash
export ALLOWED_ORIGINS="https://builder.io,https://cdn.builder.io,https://<your-ngrok>.ngrok-free.dev"
./restart_servers.sh
```

---

## Step 1: Data - Ensure Every Ad Has image_path

### 1.1 Rebuild runs from orphan images

**Creates/repairs run JSONs and attaches ads to images**

**Dry run (see what would change):**
```bash
python3 tools/batch_rebuild_walmart_runs_from_images.py --client <client-name>
```

**Write with backups:**
```bash
python3 tools/batch_rebuild_walmart_runs_from_images.py --client <client-name> --write --backup
```

**All Walmart clients:**
```bash
python3 tools/batch_rebuild_walmart_runs_from_images.py --write --backup
```

### 1.2 Reconcile remaining ads

**Match ads to images by date token + type + brand/client/keyword**

**Dry run:**
```bash
python3 tools/reconcile_walmart_images_to_json.py --min-score 6
```

**Write:**
```bash
python3 tools/reconcile_walmart_images_to_json.py --write --backup --min-score 6
```

### 1.3 Audit coverage

```bash
python3 tools/audit_adtype_mapping.py
```

**Expected output:**
```
✅ walmart/SBA - JSON-type OK | Folder OK | Filename OK | Image exists
✅ walmart/SBV - JSON-type OK | Folder OK | Filename OK | Image exists
✅ walmart/Tile_Takeover - JSON-type OK | Folder OK | Filename OK | Image exists
```

**If you see many "Image MISSING":**
- Stop and share the audit output
- Don't proceed to Step 2

---

## Step 2: API - Make Backend Unbreakable

### 2.1 Verify API changes applied

**Check that `web/builder_server_v2.py` has these functions:**

```bash
grep -A 5 "def find_image_file" web/builder_server_v2.py
grep -A 5 "def build_image_url_for_ad" web/builder_server_v2.py
```

**Should show:**
- `find_image_file()` - Robust resolver for nested Walmart directories
- `build_image_url_for_ad()` - Builds image URLs with fallbacks

### 2.2 Test API endpoints

**Test /api/clients:**
```bash
curl "http://localhost:5006/api/clients?retailer=walmart" | jq
```

**Test /api/ads/cards:**
```bash
curl "http://localhost:5006/api/ads/cards?retailer=walmart&client=<client>&page_size=5" | jq '.cards | length'
```

**Test /api/image:**
```bash
# Get first card's image_url
IMAGE_URL=$(curl -s "http://localhost:5006/api/ads/cards?retailer=walmart&client=<client>&page_size=1" | jq -r '.cards[0].image_url')

# Test image endpoint
curl -I "http://localhost:5006${IMAGE_URL}"
```

**Expected:** `200 OK` with `Content-Type: image/png`

### 2.3 Run frontend doctor

```bash
python3 tools/doctor_walmart_frontend.py
```

**Or with ngrok:**
```bash
API_BASE=https://<your-ngrok>.ngrok-free.dev python3 tools/doctor_walmart_frontend.py
```

**Expected output:**
- ✅ Image path coverage ≥ 95%
- ✅ API resolvable ≥ 90%

---

## Step 3: Frontend - Verify Vite Proxy

### 3.1 Check proxy route exists

```bash
ls neon-sanctuary/server/routes/image.ts
```

### 3.2 Verify regex pattern

```bash
grep -A 10 "api/image" neon-sanctuary/server/routes/image.ts
```

**Should show:**
```typescript
app.get(/^\/api\/image\/([^/]+)\/([^/]+)\/(.+)$/, async (req, res) => {
  const flaskUrl = `http://localhost:5006${req.path}`;
  // ...
});
```

**Why regex?** Captures multi-level paths like `/api/image/walmart/client/SBA/subfolder/image.png`

### 3.3 Test proxy in browser

1. Open http://localhost:3000
2. Open DevTools → Network tab
3. Load a Walmart client
4. Look for `/api/image/*` requests
5. Should show `200 OK` (not `404` or `CORS error`)

---

## Step 4: Builder.io Integration

### 4.1 Update Builder.io code

**Load ad cards:**
```javascript
const base = 'https://<your-ngrok>.ngrok-free.dev';

fetch(`${base}/api/ads/cards?retailer=walmart&client=${state.selectedClient}&page_size=24`, {
  headers: { 'ngrok-skip-browser-warning': 'true' }
})
  .then(r => r.json())
  .then(data => {
    state.adCards = data.cards;
    console.log('Loaded cards:', data.cards.length);
  })
  .catch(console.error);
```

**Display images:**
```javascript
// In your Image component
<img src={`${base}${card.image_url}`} alt={card.brand} />
```

**⚠️ Critical:** Always prepend `base` to `card.image_url`

### 4.2 Test in Builder.io

1. Open Builder.io
2. Create new page
3. Add Custom Code block
4. Paste fetch code
5. Add state binding for `adCards`
6. Add repeater for cards
7. Bind image src to `${base}${card.image_url}`

**Expected:** Cards render with images

---

## Common Pitfalls Checklist

### ❌ Data Issues

- [ ] **image_path missing in JSON**
  - Fix: Run rebuild + reconcile scripts
  
- [ ] **Images in wrong folders**
  - Fix: Check taxonomy compliance with audit tool
  
- [ ] **Orphaned JSON entries**
  - Fix: Delete or re-run scraper

### ❌ API Issues

- [ ] **Flask not running**
  - Fix: `./restart_servers.sh`
  
- [ ] **Image endpoint returns 404**
  - Fix: Check `find_image_file()` function exists
  
- [ ] **Cards have no image_url**
  - Fix: Check `build_image_url_for_ad()` is called

### ❌ Frontend Issues

- [ ] **Vite proxy missing**
  - Fix: Check `neon-sanctuary/server/routes/image.ts` exists
  
- [ ] **Regex pattern wrong**
  - Fix: Use `^\/api\/image\/([^/]+)\/([^/]+)\/(.+)$`
  
- [ ] **Not prepending base URL**
  - Fix: Always use `${base}${card.image_url}`

### ❌ CORS Issues

- [ ] **ALLOWED_ORIGINS missing ngrok**
  - Fix: Export and restart servers
  
- [ ] **Builder.io not in ALLOWED_ORIGINS**
  - Fix: Add `https://builder.io,https://cdn.builder.io`

---

## Verification Commands

### Quick health check

```bash
# 1. Servers running?
curl http://localhost:5006/health
curl http://localhost:3000

# 2. Walmart clients exist?
curl "http://localhost:5006/api/clients?retailer=walmart" | jq

# 3. Cards have images?
curl "http://localhost:5006/api/ads/cards?retailer=walmart&client=<client>&page_size=5" | \
  jq '.cards[] | {brand, image_url}'

# 4. Image endpoint works?
curl -I "http://localhost:5006/api/image/walmart/<client>/SBA/test.png"
```

### Full diagnostic

```bash
# Run all checks
python3 tools/walmart_readiness_doctor.py

# Or manual checks
python3 tools/audit_adtype_mapping.py
python3 tools/doctor_walmart_frontend.py
```

---

## Success Criteria

✅ **Data Layer**
- Image path coverage ≥ 95%
- All images exist on disk
- Taxonomy compliance 100%

✅ **API Layer**
- `/api/ads/cards` returns cards with `image_url`
- `/api/image/*` resolves images (exact + fuzzy)
- Handles nested Walmart directories

✅ **Frontend Layer**
- Vite proxy forwards to Flask
- Images load in browser
- No CORS errors

✅ **Builder.io**
- Cards render with images
- No "no image" placeholders
- Filtering works

---

## Troubleshooting

### "No Walmart ads found"

**Cause:** No run JSONs in `output/walmart/*/runs/`

**Fix:**
```bash
# Run a scrape
python3 walmart_search_and_capture.py 'test' --output-dir output/walmart/test_client
```

### "Image path coverage < 95%"

**Cause:** JSONs missing `image_path` field

**Fix:**
```bash
python3 tools/batch_rebuild_walmart_runs_from_images.py --write --backup
python3 tools/reconcile_walmart_images_to_json.py --write --backup --min-score 6
```

### "API can't resolve images"

**Cause:** `find_image_file()` not finding files

**Fix:**
1. Check files exist: `ls output/walmart/client/SBA/`
2. Check Flask has new code: `grep find_image_file web/builder_server_v2.py`
3. Restart: `./restart_servers.sh`

### "Images don't load in Builder.io"

**Cause:** Not prepending base URL or CORS issue

**Fix:**
1. Check: `src={base + card.image_url}` (not just `card.image_url`)
2. Check CORS: `export ALLOWED_ORIGINS="..."`
3. Check ngrok URL is current

---

## Files Modified

### Backend (Flask)
- `web/builder_server_v2.py`
  - `resolve_image_path()` - Enhanced with legacy fallbacks
  - `find_image_file()` - NEW: Robust resolver for nested dirs
  - `build_image_url_for_ad()` - NEW: Build URLs with fallbacks
  - `/api/image` endpoint - Uses new resolver
  - `/api/ads/cards` endpoint - Skips cards without images

### Frontend (Vite)
- `neon-sanctuary/server/routes/image.ts`
  - Regex pattern for multi-level paths
  - Proxies to Flask on port 5006

### Tools
- `tools/walmart_readiness_doctor.py` - NEW: Comprehensive health check
- `tools/doctor_walmart_frontend.py` - NEW: API probe + coverage check
- `tools/batch_rebuild_walmart_runs_from_images.py` - Existing
- `tools/reconcile_walmart_images_to_json.py` - Existing
- `tools/audit_adtype_mapping.py` - Existing

---

## Next Steps After Success

1. **Test with real Builder.io page**
   - Create production page
   - Add filtering by brand/term
   - Add pagination

2. **Monitor performance**
   - Check API response times
   - Optimize image serving if needed
   - Add caching headers

3. **Expand to other retailers**
   - Apply same pattern to Kroger
   - Apply to Instacart
   - Generalize resolver for all retailers

---

**Last Updated:** 2025-10-27
**Status:** ✅ Production Ready
