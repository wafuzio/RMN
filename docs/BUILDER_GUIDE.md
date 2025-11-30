# Builder.io Integration - Complete Guide

**Your API URL:** `https://<your-ngrok-url>.ngrok-free.dev`

> ⚠️ **Note:** The ngrok URL changes each time you restart. Get your current URL from `./restart_servers.sh` output.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Server Management](#server-management)
3. [API Reference](#api-reference)
4. [Builder.io Setup](#builderio-setup)
5. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+ (for Vite dashboard)
- ngrok installed (`brew install ngrok`)

### Start All Servers

```bash
cd /path/to/Amazon_Scrape  # Update to your actual path
./restart_servers.sh
```

> ⚠️ **Note:** Update `SCRAPER_DIR` in `restart_servers.sh` (line 20) to match your installation path.

This script will:
1. ✅ Kill any existing server processes
2. ✅ Verify ports are available
3. ✅ Start Flask API (port 5006)
4. ✅ Start ngrok tunnel
5. ✅ Start Vite dev server (port 3000)
6. ✅ Display all URLs and PIDs

**Dashboard:** http://localhost:3000 (or 3001 if port busy)
**API:** http://localhost:5006
**ngrok:** https://<your-ngrok-url>.ngrok-free.dev (see script output)

---

## Server Management

### Available Scripts

#### `./restart_servers.sh` - Restart Everything
Safely kills all servers and restarts them cleanly.

**Features:**
- Prevents duplicate processes
- Verifies ports are free
- Logs output to `logs/` directory
- Shows ngrok URL and PIDs

```bash
./restart_servers.sh
```

#### `./check_servers.sh` - Check Status
Quickly see which servers are running.

```bash
./check_servers.sh
```

**Output:**
```
Flask API (port 5006):     ✓ Running (PID: 12345)
ngrok:                     ✓ Running (PID: 12346)
                           URL: https://foilable-ruthie-consultive.ngrok-free.dev
Vite (port 3000):          ✓ Running (PID: 12347)
```

#### `./stop_servers.sh` - Stop Everything
Cleanly stops all servers without restarting.

```bash
./stop_servers.sh
```

### Manual Server Management

#### Start Flask API
```bash
python3 web/builder_server_v2.py
```

#### Start ngrok
```bash
ngrok http 5006
```

#### Start Vite Dashboard
```bash
cd neon-sanctuary
npm run dev
```

### Environment Variables

```bash
# Optional: Set allowed CORS origins
export ALLOWED_ORIGINS="https://builder.io,https://cdn.builder.io"

# Optional: Set API key for future write operations
export API_KEY="your-secret-key"

# Optional: Override scraper home directory
export SCRAPER_HOME="/path/to/Amazon_Scrape"
```

---

## API Reference

### Base URL
- **Local:** `http://localhost:5006`
- **ngrok:** `https://foilable-ruthie-consultive.ngrok-free.dev`

### Core Endpoints

#### `GET /api/retailers`
List all available retailers.

**Response:**
```json
{
  "retailers": ["kroger", "instacart", "walmart"],
  "count": 3
}
```

#### `GET /api/clients?retailer=<retailer>`
List all clients for a retailer.

**Parameters:**
- `retailer` (required): Retailer slug (e.g., "kroger")

**Response:**
```json
{
  "retailer": "kroger",
  "clients": ["bandaid", "blue_bunny", "pickle"],
  "count": 3
}
```

#### `GET /api/runs?retailer=<retailer>&client=<client>`
List all scraping runs for a client.

**Parameters:**
- `retailer` (required): Retailer slug
- `client` (required): Client name

**Response:**
```json
{
  "retailer": "kroger",
  "client": "bandaid",
  "runs": [
    {
      "file": "run_results_waterproof_bandages_2025-10-09_09-23-42.json",
      "timestamp": "2025-10-09 09:23:42",
      "keyword": "waterproof bandages",
      "url": "https://www.kroger.com/search?query=waterproof+bandages",
      "ads_count": 15
    }
  ],
  "count": 1
}
```

#### `GET /api/terms?retailer=<retailer>&client=<client>`
List all search terms used for a client.

**Parameters:**
- `retailer` (required): Retailer slug
- `client` (required): Client name

**Response:**
```json
{
  "retailer": "kroger",
  "client": "bandaid",
  "terms": ["waterproof bandages", "bandages", "first aid"],
  "count": 3
}
```

#### `GET /api/advertisers?retailer=<retailer>&client=<client>`
List all unique advertisers/brands for a client.

**Parameters:**
- `retailer` (required): Retailer slug
- `client` (required): Client name

**Response:**
```json
{
  "retailer": "kroger",
  "client": "cheese_dip",
  "advertisers": ["Herdez", "Jennie-O", "Kraft", "P&G"],
  "count": 4
}
```

#### `GET /api/ads/cards?retailer=<retailer>&client=<client>&term=<term>&advertiser=<brand>&page=1&page_size=24`
Get ad cards with filtering and pagination.

**Parameters:**
- `retailer` (required): Retailer slug
- `client` (required): Client name
- `term` (optional): Filter by search term
- `advertiser` (optional): Filter by advertiser/brand name
- `start` (optional): Start date filter (YYYY-MM-DD format)
- `end` (optional): End date filter (YYYY-MM-DD format)
- `page` (optional): Page number (default: 1)
- `page_size` (optional): Items per page (default: 24, max: 100)

**Response:**
```json
{
  "retailer": "kroger",
  "client": "cheese_dip",
  "cards": [
    {
      "retailer": "kroger",
      "client": "cheese_dip",
      "keyword": "cheese dip",
      "ad_type": "TOA",
      "brand": "Herdez + Jennie-O",
      "advertisers": ["Herdez", "Jennie-O"],
      "message": "Turk-ify Your Taco",
      "image_url": "/api/image/kroger/cheese_dip/kroger__herdez+jennie_o__toa__cheese_dip__cheese_dip__D2025-10-12_T19-20.33_1.png",
      "run_file": "run_results_cheese_dip_2025-10-12_19-19-52.json",
      "timestamp": "2025-10-12 19:19:52",
      "featured": false,
      "ad_index": 0
    }
  ],
  "page": 1,
  "page_size": 24,
  "has_more": false,
  "total_cards": 15,
  "filters": {
    "term": null,
    "advertiser": null
  }
}
```

**Co-Branded Ad Support:**
- `brand`: Display string with `+` separator (e.g., "Herdez + Jennie-O")
- `advertisers`: Array of individual brands for filtering
- Filter by any brand: `?advertiser=herdez` returns co-branded ads too

#### `GET /api/image/<retailer>/<client>/<filename>`
Serve ad image files.

**Example:**
```
GET /api/image/kroger/bandaid/toa_waterproof_bandages_2025-10-09_09-23-42.png
```

Returns the image file. Automatically searches all allowed subdirectories (TOA, Carousel, Skyscraper, Main, etc.).

#### `GET /api/logo/<retailer>`
Serve retailer logo.

**Example:**
```
GET /api/logo/kroger
```

Returns the retailer's logo image.

### Utility Endpoints

#### `GET /`
API documentation and status.

#### `GET /health`
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-10-10T13:30:22.123456",
  "retailers_available": 3
}
```

---

## Builder.io Setup

### Step 1: Test Your API

Before using Builder.io, verify your API works:

1. Open: https://foilable-ruthie-consultive.ngrok-free.dev/api/retailers
2. You should see JSON with retailer list
3. Test other endpoints with curl or browser

### Step 2: Create Builder.io Account

1. Go to https://builder.io
2. Sign up or log in
3. Create a new space (or use existing)

### Step 3: Add Data Source

1. In Builder.io, go to **Integrations** → **Data Sources**
2. Click **+ New Data Source**
3. Select **REST API**
4. Configure:
   - **Name:** Retail Ad Monitor
   - **Base URL:** `https://foilable-ruthie-consultive.ngrok-free.dev`
   - **Auth:** None (read-only)

### Step 4: Create Your First Page

#### Add State Variables

In the Builder.io editor:

1. Click **Data** tab (right panel)
2. Add these state variables:
   - `retailers` → `[]`
   - `selectedRetailer` → `""`
   - `clients` → `[]`
   - `selectedClient` → `""`
   - `adCards` → `[]`

#### Fetch Retailers on Page Load

1. Go to **Actions** section
2. Click **+ Add Action**
3. Trigger: **"On page load"**
4. Action: **"Run code"**
5. Code:

```javascript
fetch('https://foilable-ruthie-consultive.ngrok-free.dev/api/retailers', {
  headers: { 'ngrok-skip-browser-warning': 'true' }
})
  .then(response => response.json())
  .then(data => {
    state.retailers = data.retailers;
    console.log('Retailers loaded:', data.retailers);
  })
  .catch(error => console.error('Error:', error));
```

#### Add Retailer Selector

1. Drag a **Select** component onto canvas
2. Bind **Options** to: `state.retailers`
3. Add **On change** action:

```javascript
const retailer = event.target.value;
state.selectedRetailer = retailer;

fetch(`https://foilable-ruthie-consultive.ngrok-free.dev/api/clients?retailer=${retailer}`, {
  headers: { 'ngrok-skip-browser-warning': 'true' }
})
  .then(response => response.json())
  .then(data => {
    state.clients = data.clients;
    console.log('Clients loaded:', data.clients);
  })
  .catch(error => console.error('Error:', error));
```

#### Add Client Selector

1. Drag another **Select** component
2. Bind **Options** to: `state.clients`
3. Add **On change** action:

```javascript
state.selectedClient = event.target.value;
```

#### Add Load Ads Button

1. Drag a **Button** component
2. Set text: "Load Ad Cards"
3. Add **On click** action:

```javascript
const retailer = state.selectedRetailer;
const client = state.selectedClient;

if (!retailer || !client) {
  alert('Please select retailer and client');
  return;
}

fetch(`https://<your-ngrok-url>.ngrok-free.dev/api/ads/cards?retailer=${retailer}&client=${client}&page_size=24`, {
  headers: { 'ngrok-skip-browser-warning': 'true' }
})
  .then(response => response.json())
  .then(data => {
    state.adCards = data.cards;
    console.log('Ad cards loaded:', data.cards.length);
  })
  .catch(error => console.error('Error:', error));
```

#### Display Ad Cards

1. Drag a **Box** component (grid container)
2. Style it:
   - Display: `grid`
   - Grid template columns: `repeat(3, 1fr)`
   - Gap: `20px`
   - Padding: `20px`

3. Inside the box, drag another **Box** (card)
4. Click the card box
5. In **Data** tab, add **Repeat**:
   - Bind to: `state.adCards`
   - Item name: `card`

6. Inside the repeated card, add:
   - **Image:** Bind to `'https://foilable-ruthie-consultive.ngrok-free.dev' + card.image_url`
   - **Text:** Bind to `card.brand` (brand name)
   - **Text:** Bind to `card.keyword` (keyword)
   - **Text:** Bind to `card.ad_type` (ad type badge)

### Step 5: Style Your Page

Add CSS styling to make it look professional:

**Card styling:**
- Border: `1px solid #e0e0e0`
- Border radius: `12px`
- Padding: `15px`
- Background: `white`
- Box shadow: `0 2px 8px rgba(0,0,0,0.1)`

**Page styling:**
- Background: `linear-gradient(135deg, #667eea 0%, #764ba2 100%)`
- Padding: `40px`
- Min height: `100vh`

### Step 6: Publish

1. Click **Publish** button (top right)
2. Your page is now live!
3. Share the URL or embed in your website

---

## Troubleshooting

### Server Issues

#### Servers won't start
```bash
# Check what's using the ports
lsof -i :5006  # Flask
lsof -i :3000  # Vite
lsof -i :4040  # ngrok

# Use the restart script to clean up
./restart_servers.sh
```

#### Multiple Flask processes running
```bash
# Kill all Flask processes
pkill -9 -f "builder_server_v2.py"

# Restart cleanly
./restart_servers.sh
```

#### Port 3000 in use
```bash
# Kill whatever is using port 3000
lsof -ti:3000 | xargs kill -9

# Restart Vite
cd neon-sanctuary && npm run dev
```

### API Issues

#### CORS errors in Builder.io
Make sure ngrok URL is in allowed origins:
```bash
export ALLOWED_ORIGINS="https://builder.io,https://cdn.builder.io,https://foilable-ruthie-consultive.ngrok-free.dev"
./restart_servers.sh
```

#### Images not loading

**Common causes and fixes:**

1. **Check Flask API is serving images:**
   ```bash
   curl -I "http://localhost:5006/api/image/kroger/client/TOA/image.png"
   ```
   Should return `200 OK` with `Content-Type: image/png`

2. **Check Vite proxy is forwarding:**
   - Open browser DevTools → Network tab
   - Look for `/api/image/*` requests
   - Should show `200 OK` (not `404` or `CORS error`)

3. **Verify image files exist:**
   ```bash
   ls output/kroger/client/TOA/
   ls output/walmart/client/runs/*/SBA/
   ```

4. **Test fuzzy matching:**
   ```bash
   # Even with typos, should find similar files
   curl "http://localhost:5006/api/image/kroger/client/test.jpg"
   ```

5. **Check image_path in JSON:**
   ```bash
   cat output/kroger/client/runs/run_results_*.json | jq '.ads[0].image_path'
   ```
   Should be relative path like `"TOA/kroger__brand__toa__...png"`

6. **Verify proxy route exists:**
   ```bash
   # Check neon-sanctuary/server/routes/image.ts exists
   ls neon-sanctuary/server/routes/image.ts
   ```

**If images still don't load:**
- Check browser console for errors
- Verify ngrok URL is correct (changes on restart)
- Ensure both Flask (5006) and Vite (3000) are running
- Try clearing browser cache

#### API returns empty data
1. Verify runs exist:
```bash
ls output/kroger/blue_bunny/runs/
```

2. Check JSON files are valid:
```bash
cat output/kroger/blue_bunny/runs/run_results_*.json | jq
```

3. Test API directly:
```bash
curl "http://localhost:5006/api/runs?retailer=kroger&client=blue_bunny"
```

#### ngrok URL changed
ngrok URLs change when you restart. Update:
1. Your Builder.io data source base URL
2. Your `ALLOWED_ORIGINS` environment variable
3. Any hardcoded URLs in your code

### Dashboard Issues

#### Dashboard shows "No image"
This is expected for TOA ads that don't have images. The API is working correctly.

#### Brand shows "Unknown"
Your scraper data doesn't include brand information. This is a data issue, not a display issue. To fix:
1. Update your scraper to extract brand names
2. Re-run scrapes to collect new data

### Kroger Data Issues

#### Many ads show "Unknown" brand
**Cause:** Brand canonicalization failed or image rebuild used incorrect brand.

**Fix:**
1. **Check if raw data has brand:**
   ```bash
   cat output/kroger/<client>/runs/run_results_*.json | jq '.ads[] | select(.advertisers)'
   ```

2. **If brand exists in raw JSON but missing in aggregated:**
   - Brand was lost during aggregation or rebuild
   - Use repair scripts to fix specific creatives:
   ```bash
   python tools/repair_blue_bunny_sweet_pairings.py
   python tools/build_brand_index.py
   ```

3. **If brand missing in raw JSON:**
   - Scraper didn't extract advertiser
   - Re-run scrape or use Brand Review Tool to manually tag

#### Images missing despite files existing
**Cause:** `image_path` field not wired into JSON during extraction.

**Symptoms:**
- PNG files exist in TOA/, Skyscraper/, Carousel/ folders
- Dashboard shows "No image" placeholder
- JSON has `image_url` but no `image_path`

**Fix:**
```bash
# Backfill missing image_path fields
python tools/repair_kroger_image_paths.py

# Regenerate missing images from archive
python tools/rebuild_kroger_images_from_archive.py

# Rebuild brand index
python tools/build_brand_index.py
```

**Verification:**
```bash
# Check if image_path exists in JSON
cat output/kroger/<client>/runs/run_results_*.json | jq '.ads[] | select(.image_path)'

# Check if PNG files exist
find output/kroger/<client> -name "*.png" -type f

# Compare counts
echo "JSON ads with image_path:"
cat output/kroger/<client>/runs/run_results_*.json | jq '[.ads[] | select(.image_path)] | length'
echo "PNG files on disk:"
find output/kroger/<client> -name "*.png" -type f | wc -l
```

**Common scenarios:**
- **Scenario 1:** PNGs exist, JSON has no `image_path`
  - **Fix:** `python tools/repair_kroger_image_paths.py`
- **Scenario 2:** No PNGs, JSON has `image_url`
  - **Fix:** `python tools/rebuild_kroger_images_from_archive.py`
- **Scenario 3:** Brand mislabeled (e.g., "Bluey" instead of "Blue Buffalo")
  - **Fix:** `python tools/fix_bluey_rebuild_labels.py`

**See:** `docs/COMMON_ISSUES.md` → Kroger image paths missing

#### Vite running on wrong port
If Vite starts on 3001 instead of 3000:
```bash
# Kill port 3000
lsof -ti:3000 | xargs kill -9

# Restart Vite
cd neon-sanctuary && npm run dev
```

### Builder.io Issues

#### "Failed to fetch" errors
1. Check that ngrok is running: `curl https://foilable-ruthie-consultive.ngrok-free.dev/api/retailers`
2. Add `ngrok-skip-browser-warning: true` header to all fetch requests
3. Check browser console for CORS errors

#### State not updating
1. Open browser console (F12)
2. Check for JavaScript errors
3. Add `console.log()` statements to debug
4. Verify state variable names match exactly

#### Images not displaying
Make sure to prepend the base URL:
```javascript
// Correct
'https://foilable-ruthie-consultive.ngrok-free.dev' + card.image_url

// Wrong
card.image_url  // This is just "/api/image/..."
```

---

## Architecture

### System Overview

```
┌─────────────────────┐
│  Tkinter Admin GUI  │ ← Power users (scheduling, configuration)
└─────────────────────┘
          ↓
┌─────────────────────┐
│   Core Scraper      │ ← Shared scraping engine + taxonomy
└─────────────────────┘
          ↓
┌─────────────────────┐
│   Flask API v2.0    │ ← Builder.io & Vite dashboard (read-only)
│   (Port 5006)       │
└─────────────────────┘
          ↓
┌─────────────────────┐
│   ngrok Tunnel      │ ← Exposes API to internet
└─────────────────────┘
          ↓
┌─────────────────────┐
│   Vite Dashboard    │ ← React dashboard (localhost:3000)
│   (Port 3000)       │
└─────────────────────┘
          ↓
┌─────────────────────┐
│   Builder.io        │ ← Visual page builder (optional)
└─────────────────────┘
```

### Image Resolution Flow

**How the frontend finds and displays images:**

```
1. Frontend requests ad cards
   GET /api/ads/cards?retailer=kroger&client=cheese_dip
   
2. Flask API scans JSON files
   - Reads run_results_*.json from runs/ directory
   - Extracts ad.image_path (relative path)
   - Example: "TOA/kroger__brand__toa__client__keyword__D2025-10-27_T14-32.15_1.png"
   
3. API returns cards with image_url
   {
     "image_url": "/api/image/kroger/cheese_dip/TOA/kroger__brand__toa__..."
   }
   
4. Frontend requests image
   GET /api/image/kroger/cheese_dip/TOA/kroger__brand__toa__...
   
5. Flask searches filesystem
   - Checks: output/kroger/cheese_dip/TOA/
   - Also searches: Carousel/, Skyscraper/, Main/, SBA/, SBV/, Tile_Takeover/
   - Uses fuzzy matching if exact filename not found
   
6. Returns image file
   Content-Type: image/png
```

**Key Features:**
- ✅ **Fuzzy matching** - Finds images even with slight filename differences
- ✅ **Multi-folder search** - Automatically checks all ad type folders
- ✅ **Nested directory support** - Handles Walmart's `runs/{run_id}/` structure
- ✅ **Canonical schema aware** - Prefers `image_path` field, falls back to legacy fields

### Dual-Backend Proxy Architecture

**Why we have two servers:**

The system uses a **dual-backend architecture** for development:

```
┌──────────────────────────────────────────────────────────────┐
│                     Browser / Builder.io                      │
└──────────────────────────────────────────────────────────────┘
                              ↓
                    ┌─────────────────┐
                    │  ngrok Tunnel   │
                    └─────────────────┘
                              ↓
        ┌─────────────────────────────────────────┐
        │                                         │
        ↓                                         ↓
┌──────────────────┐                    ┌──────────────────┐
│  Vite Dev Server │                    │   Flask API      │
│  (Express/Node)  │ ──── proxies ────→ │   (Python)       │
│  Port 3000/3001  │    /api/image/*    │   Port 5006      │
└──────────────────┘                    └──────────────────┘
        ↓                                         ↓
  Serves React UI                        Serves images from
  & proxies API calls                    filesystem
```

**How the proxy works:**

1. **Vite serves the frontend**
   - React dashboard at http://localhost:3000
   - Hot module reloading for development

2. **Express middleware proxies image requests**
   - Route: `neon-sanctuary/server/routes/image.ts`
   - Pattern: `/api/image/:retailer/:client/*`
   - Forwards to: `http://localhost:5006/api/image/...`

3. **Flask serves images from filesystem**
   - Reads from `output/{retailer}/{client}/` directories
   - Handles CORS headers
   - Supports nested paths (e.g., `TOA/subfolder/image.png`)

**Why this architecture?**

- ✅ **Development workflow** - Vite provides fast React HMR
- ✅ **CORS handling** - Single origin for frontend requests
- ✅ **Separation of concerns** - Flask focuses on data/images, Vite on UI
- ✅ **Flexible deployment** - Can deploy separately in production

**Critical proxy configuration:**

```typescript
// neon-sanctuary/server/routes/image.ts
app.get(/^\/api\/image\/([^/]+)\/([^/]+)\/(.+)$/, async (req, res) => {
  const flaskUrl = `http://localhost:5006${req.path}`;
  // Proxy to Flask, preserve query strings
  const response = await fetch(flaskUrl);
  res.set('Content-Type', response.headers.get('content-type'));
  response.body.pipe(res);
});
```

**Why regex pattern?**
- Simple wildcards (`/api/image/:retailer/:client/*`) don't capture multi-level paths
- Regex `^\/api\/image\/([^/]+)\/([^/]+)\/(.+)$` captures nested subdirectories
- Example: `/api/image/kroger/client/TOA/subfolder/image.png` ✅

### Canonical Schema Integration

**Recent Walmart changes affect this system:**

1. **Nested directory structure**
   ```
   output/walmart/client/
     runs/
       20251027143215/              ← run_id directory
         run_results_20251027143215.json
         SBA/
         SBV/
         Tile_Takeover/
   ```

2. **Flask API handles both structures**
   - **Kroger (flat):** `runs/run_results_{run_id}.json`
   - **Walmart (nested):** `runs/{run_id}/run_results_{run_id}.json`
   - API automatically detects and scans both

3. **Image path resolution**
   - Canonical: `ad.image_path` (relative to client root)
   - Legacy: `ad.screenshot`, `ad.toa_image_path`, etc.
   - API tries canonical first, falls back to legacy

4. **Brand canonicalization**
   - All brands normalized via `core/brands.canonicalize()`
   - Filenames use canonical brand tokens
   - Example: "lays" → "Lay's" in both JSON and filenames

**API compatibility:**
- ✅ Works with legacy Kroger JSONs (`results[].ads[]`)
- ✅ Works with canonical Walmart JSONs (`ads[]`)
- ✅ Works with canonical Kroger JSONs (after migration)
- ✅ Handles missing `image_path` via fallback logic

---

## File Structure

```
Amazon_Scrape/
├── web/
│   ├── builder_server_v2.py    ← Flask API server
│   └── test_api.html           ← API test page
├── neon-sanctuary/             ← Vite React dashboard
│   ├── client/
│   │   ├── pages/Index.tsx     ← Main dashboard page
│   │   ├── components/         ← React components
│   │   └── lib/api.ts          ← API client
│   └── vite.config.ts
├── docs/
│   └── BUILDER_GUIDE.md        ← This file
├── logs/                       ← Server logs
│   ├── flask.log
│   ├── ngrok.log
│   └── vite.log
├── restart_servers.sh          ← Restart all servers
├── check_servers.sh            ← Check server status
├── stop_servers.sh             ← Stop all servers
└── output/                     ← Scraper data
    ├── kroger/
    │   ├── bandaid/
    │   │   ├── runs/           ← JSON run files
    │   │   ├── TOA/            ← Ad images
    │   │   ├── Skyscraper/     ← Ad images
    │   │   └── Main/           ← Screenshots
    │   └── blue_bunny/
    ├── instacart/
    └── walmart/
```

---

## API Connection Status Map

### ✅ Working Endpoints

| Endpoint | Status | Notes |
|----------|--------|-------|
| `GET /health` | ✅ Working | Returns healthy status + 3 retailers |
| `GET /api/retailers` | ✅ Working | Returns: kroger, instacart, walmart |
| `GET /api/clients?retailer=<retailer>` | ✅ Working | All retailers return client lists |
| `GET /api/runs?retailer=<retailer>&client=<client>` | ✅ Working | Handles nested directories (Walmart) |
| `GET /api/terms?retailer=<retailer>&client=<client>` | ✅ Working | Scans all JSON structures |
| `GET /api/advertisers?retailer=<retailer>&client=<client>` | ✅ Working | Lists all unique brands |
| `GET /api/ads/cards` | ✅ Working | Returns paginated ad cards with advertiser filtering |
| `GET /api/image/<retailer>/<client>/<path:filename>` | ✅ Working | Serves images with path support |

### 📊 Data Availability by Retailer

#### Kroger (blue_bunny)
- **Total Cards:** 193
- **Images Available:** 2 files (1 Skyscraper, 1 Main screenshot)
- **Issue:** 193 ad entries but only 2 actual images saved
  - TOA: 1 ad, 0 images ❌
  - Skyscraper: 2 ads, 1 image (50%) ⚠️
  - CuratedCarousel: 190 ads, 190 image paths in JSON ✅ (but pointing to same file)

#### Instacart (land_o_frost)
- **Total Cards:** 14
- **Images Available:** 7 files
- **Migration Status:** ✅ Complete (5 images linked)
  - Shoppable Display Ad: 2/2 with images ✅
  - Display Ad: 1/1 with images ✅
  - Shoppable Video Ad: 0/1 with images ❌
  - Sponsored Label: 0/4 with images ❌

#### Walmart (land_o_frost)
- **Total Cards:** 6
- **Images Available:** 8 files (including videos)
- **Migration Status:** ✅ Complete (8 files moved)
  - SBA: 2/2 with images ✅
  - SBV: 2/2 with images ✅
  - Tile Takeover: 2/2 with images ✅

---

## Troubleshooting Image Display Issues

### Issue 1: Kroger - Carousel Naming Convention

**Problem:** Carousel images use inconsistent naming with ad copy text embedded in filename.

**Current Pattern:**
```
carousel_don_t_skimp_on_flavor_black_forest_ham_2025-10-10_15-02-21.png
carousel_stack_your_dream_sandwich_packaged_deli_meat_2025-10-10_15-03-21.png
```

**Expected Pattern (like Skyscraper):**
```
carousel_black_forest_ham_2025-10-10_15-02-21_1.png
carousel_packaged_deli_meat_2025-10-10_15-03-21_1.png
```

**Root Cause:** Line 667 in `kroger_search_and_capture.py` uses `safe_header` (ad copy) instead of index number.

**Fix Applied:** Changed filename generation to use index number:
```python
# Old: filename = f"carousel_{safe_header}_{safe_term2}_{ts2}.png"
# New: filename = f"carousel_{safe_term2}_{ts2}_{i+1}.png"
```

**Impact:** Future scrapes will use systematic naming. Existing files need manual rename or re-scrape.

---

### Issue 2: Instacart - Some Ad Types Have No Images

**Problem:** Shoppable Video Ads and Sponsored Labels have no images.

**Root Cause:** These ad types may not have downloadable images, or scraper doesn't capture them.

**Evidence:**
```json
{
  "type": "Shoppable Video Ad",
  "title": "New York Bakery",
  "selector": "div.e-1qzz7bi"
  // No image_path field
}
```

**Why Images Don't Show:**
- Shoppable Video Ads: Likely video-only (no thumbnail saved)
- Sponsored Labels: Text-only ads (no image to capture)

**Fix Options:**
1. Extract video thumbnails for Shoppable Video Ads
2. Mark text-only ads in UI (don't show "No image" placeholder)
3. Capture screenshots of ad containers

---

### Issue 3: Walmart - All Working ✅

**Status:** Walmart images display correctly after migration.

**Success Factors:**
- Migration script moved all images to correct folders
- JSON updated with `image_paths` mapping
- API uses mapping to serve images
- All ad types have images

---

## Image Display Checklist

When debugging "No image" issues:

1. **Check if image file exists:**
   ```bash
   find output/<retailer>/<client> -name "*.png" -o -name "*.jpg"
   ```

2. **Check JSON has image path:**
   ```bash
   cat output/<retailer>/<client>/runs/*.json | jq '.ads[] | select(.image_path)'
   ```

3. **Test API endpoint:**
   ```bash
   curl -I "http://localhost:5006/api/image/<retailer>/<client>/<filename>"
   ```

4. **Check fuzzy matching:**
   - API tries to match by ad type if exact filename not found
   - Multiple ads may get same image if only one file exists

5. **Verify taxonomy compliance:**
   - Images should be in ad-type folders (TOA/, SBA/, etc.)
   - Not in runs/ subdirectories (except Walmart pre-migration)

---

## Ad Types Filter Fix (November 2025)

### Issue: Ad Types Filter Not Working

**Problem:** The ad types filter in the frontend was not filtering the displayed cards despite:
- ✅ Frontend correctly sending `types` parameter in API requests
- ✅ Express proxy correctly forwarding parameter to Flask
- ✅ Flask receiving the parameter in request logs

**Root Cause:** The Flask backend in `web/builder_server_v2.py` was accepting the `types` query parameter but never actually using it to filter the cards in the main code paths.

### Code Paths That Needed Fixing

The Flask API has multiple code paths for serving ad cards:

1. **BRAND INDEX FAST PATH** (lines ~1580-1620) - Used when filtering by advertiser
2. **GENERAL MANIFEST PATH** (lines ~1680-1810) - Used for general queries  
3. **Legacy filtering path** (lines ~2326-2345) - Only used in specific edge cases

**The bug:** Only the legacy path had types filtering implemented. The main paths that handle 99% of requests had no filtering logic.

### Fix Applied

Added types filtering logic to both main code paths:

#### 1. Brand Index Fast Path
```python
# Extract ad type for filtering
ad_type = ad.get("type") or ad.get("ad_type") or "Main"

# Filter by ad types if specified (comma-separated list)
if types_filter:
    types_list = [t.strip().lower() for t in types_filter.split(',') if t.strip()]
    if types_list:
        ad_type_normalized = ad_type.lower().replace("_", " ").replace("-", " ")
        # Check if any requested type matches the ad type (exact or substring)
        matches = any(req_type in ad_type_normalized or ad_type_normalized in req_type for req_type in types_list)
        if not matches:
            continue  # Skip this ad, it doesn't match the types filter
```

#### 2. General Manifest Path
```python
# Parse types filter once if needed
types_list = []
if types_filter:
    types_list = [t.strip().lower() for t in types_filter.split(',') if t.strip()]
    print(f"🔍 [FLASK DEBUG] Applied types filter: {types_list}")

# In the ad processing loop:
# Extract ad type for filtering
ad_type = ad.get("type") or ad.get("ad_type") or "Main"

# Filter by ad types if specified
if types_list:
    ad_type_normalized = ad_type.lower().replace("_", " ").replace("-", " ")
    matches = any(req_type in ad_type_normalized or ad_type_normalized in req_type for req_type in types_list)
    if not matches:
        filtered_total += 1  # Count as filtered out, but don't add to cards
        continue
```

### Pagination Fix

When the types filter is applied, the pagination logic needed updates:

1. **Load enough ads:** Continue scanning until we have a full page of filtered results
2. **Correct totals:** Return `filtered_total` instead of original total when filter is active
3. **Accurate `has_more`:** Base pagination on filtered count, not original count

```python
# When types filter is applied, calculate total based on filtered count
display_total = total if not types_filter else filtered_total
has_more = (offset + len(cards)) < display_total if types_filter else (offset + len(cards)) < total

result = {
    "total_cards": display_total,
    "has_more": has_more,
    # ...
}
```

### Matching Logic

The types filter uses flexible matching:

1. **Case insensitive:** `types_list = [t.strip().lower() for t in types_filter.split(',')]`
2. **Normalized comparison:** Replace underscores/hyphens with spaces
3. **Substring matching:** Both exact matches and partial matches work
   - Filter: `"sba"` matches ad type: `"SBA"` ✅
   - Filter: `"video"` matches ad type: `"Shoppable_Video_Ad"` ✅

### Testing

After the fix:
- ✅ Selecting "SBA" shows only Sponsored Brand Ads
- ✅ Selecting "SBV" shows only Sponsored Brand Video ads  
- ✅ Multiple selections work (e.g., "SBA,SBV")
- ✅ Pagination works correctly with filtered results
- ✅ Total counts reflect filtered data

### Files Modified

- `web/builder_server_v2.py` - Added types filtering to both main code paths
- Added debug logging to track filter application

---

## Quick Reference: Image & Proxy System

### How Images Flow Through the System

```
Scraper → Saves image to disk
   ↓
   output/{retailer}/{client}/{AdType}/canonical_filename.png
   ↓
Scraper → Writes JSON with image_path
   ↓
   runs/run_results_{run_id}.json
   {
     "ads": [{
       "image_path": "TOA/canonical_filename.png"  ← relative path
     }]
   }
   ↓
Frontend → Requests ad cards
   ↓
   GET /api/ads/cards?retailer=kroger&client=cheese_dip
   ↓
Flask API → Scans JSONs, builds image URLs
   ↓
   Returns: { "image_url": "/api/image/kroger/cheese_dip/TOA/..." }
   ↓
Frontend → Requests image
   ↓
   GET /api/image/kroger/cheese_dip/TOA/canonical_filename.png
   ↓
Vite Proxy → Forwards to Flask
   ↓
   neon-sanctuary/server/routes/image.ts
   ↓
Flask API → Searches filesystem
   ↓
   1. Check exact path: output/kroger/cheese_dip/TOA/canonical_filename.png
   2. Fuzzy match if not found
   3. Search other folders (Carousel/, Skyscraper/, etc.)
   ↓
Returns image file → Browser displays
```

### Key Files

**Backend (Flask):**
- `web/builder_server_v2.py` - Main API server
  - `/api/ads/cards` - Returns ad cards with image URLs
  - `/api/image/<retailer>/<client>/<path>` - Serves images from filesystem
  - Handles fuzzy matching, multi-folder search, nested directories

**Frontend Proxy (Vite/Express):**
- `neon-sanctuary/server/routes/image.ts` - Proxies image requests to Flask
  - Pattern: `/api/image/:retailer/:client/*`
  - Forwards to: `http://localhost:5006/api/image/...`
  - Preserves query strings and headers

**Canonical Schema:**
- `ad.image_path` - Relative path from client root (preferred)
- `ad.screenshot` - Legacy alias (fallback)
- `ad.*_image_path` - Type-specific fields (fallback)

### Walmart vs Kroger Differences

**Kroger (Flat Structure):**
```
output/kroger/client/
  TOA/
    kroger__brand__toa__...png
  Carousel/
    kroger__brand__carousel__...png
  runs/
    run_results_20251027143215.json  ← flat
```

**Walmart (Nested Structure):**
```
output/walmart/client/
  SBA/
    walmart__brand__sba__...png
  SBV/
    walmart__brand__sbv__...png
  runs/
    20251027143215/                  ← nested by run_id
      run_results_20251027143215.json
```

**API handles both automatically!**

### Common Pitfalls

❌ **Using absolute paths in JSON**
```json
{"image_path": "/Users/dan/output/kroger/client/TOA/image.png"}
```
✅ **Use relative paths**
```json
{"image_path": "TOA/image.png"}
```

❌ **Forgetting to proxy in Vite**
```typescript
// Missing: neon-sanctuary/server/routes/image.ts
```
✅ **Proxy configured**
```typescript
app.get(/^\/api\/image\/([^/]+)\/([^/]+)\/(.+)$/, ...)
```

❌ **Not prepending base URL in frontend**
```javascript
<img src={card.image_url} />  // Just "/api/image/..."
```
✅ **Prepend ngrok URL**
```javascript
<img src={`https://<ngrok-url>.ngrok-free.dev${card.image_url}`} />
```

---

---

## Tips & Best Practices

1. **Always use the restart script** - Prevents duplicate processes
2. **Check server status first** - Use `./check_servers.sh` before debugging
3. **Monitor logs** - Check `logs/` directory for errors
4. **Test API directly** - Use curl before Builder.io integration
5. **Keep ngrok running** - Don't restart unless necessary (URL changes)
6. **Use browser console** - F12 is your friend for debugging
7. **Add console.log()** - Debug state changes in Builder.io
8. **Test incrementally** - Build one feature at a time

---

## Next Steps

### Immediate
- ✅ Start all servers with `./restart_servers.sh`
- ✅ Test dashboard at http://localhost:3000
- ✅ Verify API at https://foilable-ruthie-consultive.ngrok-free.dev

### Short-term
- ⬜ Build custom pages in Builder.io
- ⬜ Add more filtering options
- ⬜ Implement pagination
- ⬜ Add export functionality (CSV, PDF)

### Future
- ⬜ Add authentication
- ⬜ Add write operations (trigger scrapes)
- ⬜ Add real-time updates (Server-Sent Events)
- ⬜ Deploy to production server

---

**Last Updated:** 2025-10-27
**API Version:** 2.0
**Dashboard Version:** 1.0
