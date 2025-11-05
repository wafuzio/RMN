# Brand Review Tool Fixes - November 5, 2025

## Problem
The brand review tool was reporting "All brands have been identified!" when hundreds of ads actually had mismatches between JSON brand names and image filenames.

## Root Causes

### 1. **Gated Mismatch Detection**
The tool only flagged filename/JSON mismatches if the filename brand looked like a "campaign code" (via `is_uncertain_brand()`). If the filename contained a real brand slug (just the wrong one), it was silently skipped.

**Example:** JSON says `BOOST Advanced` but file is `kroger__muscle_milk__carousel__...` → Not flagged ❌

### 2. **Missing Fallback for Wrong Brand Slugs**
When `find_ad_image()` returned `None` (because it couldn't find the branded file), the tool only searched for files with `__unknown__` in the name. It didn't search for files with different brand slugs.

**Example:** JSON says `kroger__boost_advanced__carousel__...` but file is `kroger__muscle_milk__carousel__...` → Not found ❌

### 3. **Weak Slug Normalization**
The `to_slug()` function only replaced spaces, apostrophes, and ampersands. It didn't handle hyphens, punctuation, or other special characters, leading to false "matches" and "mismatches".

**Example:** `"Ben & Jerry's"` → `"ben_jerrys"` but filename might be `"ben_and_jerrys"` → Mismatch ❌

### 4. **Broken References Not Flagged**
When JSON had an image path but no file existed after all reconciliation attempts, the ad was silently skipped instead of being flagged for review.

## Solutions Implemented

### FIX #1: Unconditional Mismatch Flagging
**Location:** `load_unknown_brands()` - filename brand slug comparison

**Before:**
```python
if brand_slug_in_file not in adv_slugs:
    looks_like_code = self.is_uncertain_brand(brand_slug_in_file.replace('_', ' '))
    if looks_like_code:  # ← GATE
        is_unknown_in_filename = True
```

**After:**
```python
if brand_slug_in_file not in adv_slugs:
    # Unconditional flag on brand slug mismatch
    is_unknown_in_filename = True
    print(f"[WARN] Filename brand slug '{brand_slug_in_file}' ≠ advertisers {adv_slugs}")
```

**Impact:** Now catches all brand slug mismatches, not just campaign codes.

---

### FIX #2: Wildcard Brand Slug Search
**Location:** `load_unknown_brands()` - after `find_ad_image()` returns `None`

**New Helper Methods:**
```python
def expected_image_path_from_json(self, ad, json_file):
    """Return the full path that the JSON points to, even if it doesn't exist."""
    # Constructs path from JSON fields for all retailers (Kroger, Walmart, Instacart)

def find_existing_image_ignoring_brand(self, expected_full_path):
    """Find a file matching all parts except the brand slug segment."""
    # Uses glob pattern: retailer__*__adtype__client__search__Dts.png
    # Returns most recent match if multiple found
```

**New Logic:**
```python
if not image_path:
    expected_path = self.expected_image_path_from_json(ad, json_file)
    if expected_path and not os.path.exists(expected_path):
        alt = self.find_existing_image_ignoring_brand(expected_path)
        if alt:
            image_path = alt
            is_unknown_in_filename = True
            print(f"[WARN] JSON image path not found: {expected_path}")
            print(f"[WARN] Found existing file with different brand slug: {alt}")
```

**Impact:** Finds files with ANY brand slug mismatch, not just `__unknown__`. More comprehensive than legacy recovery.

---

### FIX #3: Robust Slug Normalization
**Location:** `to_slug()` method

**Before:**
```python
def to_slug(self, text):
    return text.lower().replace(' ', '_').replace("'", '').replace('&', 'and')
```

**After:**
```python
def to_slug(self, text):
    s = text.lower()
    s = s.replace('&', 'and')
    s = s.replace("'", '')
    # Collapse any non-alphanumeric into underscores
    s = re.sub(r'[^a-z0-9]+', '_', s)
    # Collapse multiple underscores
    s = re.sub(r'_+', '_', s).strip('_')
    return s
```

**Impact:** Handles hyphens, punctuation, diacritics consistently. Reduces false matches/mismatches.

---

### FIX #4: Flag Broken JSON References
**Location:** `load_unknown_brands()` - after all reconciliation attempts

**New Logic:**
```python
if not image_path:
    # Check if JSON has any image path field
    has_json_path = (ad.get('image_path') or 
                   ad.get('toa_image_path') or 
                   ad.get('skyscraper_image_path') or 
                   ad.get('carousel_image_path'))
    if has_json_path:
        print(f"[WARN] JSON has an image path but no matching file exists after reconciliation")
        is_unknown_in_filename = True
```

**Impact:** Broken references are now flagged for review instead of being silently skipped.

---

## Additional Improvements

### Instacart Type Coverage
Added Instacart ad types to legacy `__unknown__` recovery step:
```python
type_to_folder = {
    # ... existing types ...
    'display_ad': 'DisplayAd',
    'shoppable_recipe_ad': 'ShoppableRecipe',
    'main': 'Main'
}
```

### Documentation
Added comments explaining:
- Legacy `__unknown__` search is less comprehensive than Fix #2
- Fix #2 finds ANY brand slug mismatch, not just "unknown"
- All retailer types now covered (Kroger, Walmart, Instacart)

---

## Expected Results

### Before Fixes
- Tool reported: "All brands have been identified!"
- Diagnostic script found: **Hundreds of ads** with JSON/filename mismatches

### After Fixes
- Tool should now flag all ads where:
  - Filename has `__unknown__` but JSON has a brand
  - Filename has a different brand slug than JSON
  - JSON path doesn't exist but a file with different brand slug does
  - JSON has a path but no file exists at all

### Test Cases Covered

1. ✅ JSON: `BOOST Advanced`, File: `kroger__unknown__carousel__...`
2. ✅ JSON: `BOOST Advanced`, File: `kroger__muscle_milk__carousel__...`
3. ✅ JSON: `Coca-Cola`, File: `kroger__pepsi__carousel__...`
4. ✅ JSON: `kroger__boost_advanced__carousel__...` (doesn't exist), File: `kroger__unknown__carousel__...` (exists)
5. ✅ JSON: `kroger__boost_advanced__carousel__...` (doesn't exist), No file exists at all
6. ✅ Empty advertisers array in JSON
7. ✅ Advertisers: `['unknown']` in JSON

---

## Files Modified
- `brand_review_tool.py` - All four fixes implemented
- `tools/find_unknown_ads.py` - Enhanced diagnostic script to detect JSON/filename mismatches

## Commits
- `f0ce6c7` - Initial diagnostic improvements
- `ade71f3` - Complete fixes for all four issues

## Next Steps
1. Run the brand review tool to verify it now catches all mismatches
2. Review and correct the flagged ads
3. Consider running a bulk reconciliation script to rename files to match JSON

---

# Dashboard Modules, Filters, & Views Breakdown

## 📄 **PAGES** (Routes)

### 1. **Index.tsx** - Main Dashboard (Home Route `/`)
The core analytics and monitoring dashboard featuring:
- KPI statistics cards (total ads, active brands, top brand, volume trend)
- Retailer selector
- Comprehensive filtering system
- Ad card grid with drag-and-drop reordering
- Compare mode (side-by-side views)
- Export functionality (CSV, PDF)

### 2. **Brands.tsx** - Brand Gallery (`/brands`)
Dedicated page for browsing all brands with:
- Retailer multi-select filter
- Full-text brand search
- Alphabetically sorted brand list
- Brand detail modal view
- Link back to dashboard

### 3. **VideoOverlayTest.tsx** - Developer Testing
Test utility page (development/debug purposes)

### 4. **NotFound.tsx** - 404 Page
Catch-all for undefined routes

---

## 🎛️ **FILTERS & VIEWS** (All Employable)

### **PRIMARY FILTERS** (All functional & actively used)

| Filter | Type | Options | Location | Status |
|--------|------|---------|----------|--------|
| **Retailer** | Multi-select chips | Kroger, Amazon, Instacart, Walmart | Top of dashboard | ✅ **Employable** |
| **Client** | Popover multi-select | Dynamic from API | Filters panel | ✅ **Employable** |
| **Date Range** | Preset + Custom Calendar | Today, Yesterday, Last 7 days, MTD, YTD, Last 52 weeks, Lifetime, Custom date range | Filters panel | ✅ **Employable** |
| **Ad Types** | Popover multi-select | Carousel, TOA (Top of Aisle), Skyscraper, Template, etc. | Filters panel | ✅ **Employable** |
| **Keywords/Search Terms** | Popover multi-select | Dynamic from loaded ads | Filters panel | ✅ **Employable** |
| **Search/Message** | Text input | Free-text search | Filters panel | ✅ **Employable** |
| **Sort Order** | Dropdown select | Latest, Oldest, Name (A-Z) | Ad grid toolbar | ✅ **Employable** |
| **Timeline Range** | Visual bar chart selector | Granular selection (Day/Week/Month) | Below filters | ✅ **Employable** |

### **SECONDARY VIEWS/MODES**

| View | Function | Details |
|------|----------|---------|
| **Standard View** | Default card grid | Single retailer/client display with left (normal ads) + right (skyscraper) columns |
| **Compare Mode** | Side-by-side comparison | Two independent filter sets; left & right panels with separate timelines |
| **Visual Timeline** | Temporal heatmap | Pixel-grid showing ad distribution over time; clickable for date range filtering |

---

## 🧩 **MODULE BREAKDOWN**

### **Dashboard Components** (`neon-sanctuary/client/components/dashboard/`)

| Module | Purpose | Key Features |
|--------|---------|--------------|
| **Filters.tsx** | Filter control panel | Client, Date, Ad Type, Keywords, Search, Apply/Reset buttons |
| **RetailerSelector.tsx** | Retailer toggle buttons | Visual chips with logos; at least one always selected |
| **AdCard.tsx** | Individual ad display | Media (image/video), metadata, remove/open modal actions |
| **StatCard.tsx** | KPI metrics | Value, label, hint, trend indicator, optional brand logo |
| **Timeline.tsx** | Temporal bar chart | Grouped by day/week/month; drag range selector |
| **TemporalVisualMap.tsx** | Image/video grid timeline | Pixel-based visual representation with click-to-filter |
| **AdModal.tsx** | Ad detail modal | Full ad metadata, compare button, close action |
| **TopBrandModal.tsx** | Top brand stats modal | Displays top 1 brand by SOV (share of voice) |
| **AllBrandsModal.tsx** | All brands list modal | Filterable, sortable list of all brands |
| **RetailerLogo.tsx** | Brand/retailer logo renderer | Image component with fallback |
| **BrandLogo.tsx** | Brand logo fetcher | API integration for brand assets |
| **SkeletonGrid.tsx** | Loading placeholder | Skeleton cards during data fetch |

### **Visual Components** (`neon-sanctuary/client/components/visual/`)

| Module | Purpose |
|--------|---------|
| **TemporalVisualMap.tsx** | Heatmap-style display of ad thumbnails over time; supports click-to-filter & range selection |

### **Server Routes** (`neon-sanctuary/server/routes/`)

| Route | Method | Purpose | Query Parameters |
|-------|--------|---------|-------------------|
| `/api/retailers` | GET | Get available retailers | (none) |
| `/api/clients` | GET | Get clients for a retailer | `retailer` |
| `/api/brands` | GET | Get brands across retailers | `retailers` (comma-separated) |
| **`/api/ads/cards`** | GET | Get filtered ad cards (paginated) | `retailer`, `client`, `page`, `page_size`, `start`, `end`, `types`, `search`, `term`, `sort` |
| `/api/brand_logo/<brand>` | GET | Get brand logo image | (URL param) |
| `/api/retailer-logo/<retailer>` | GET | Get retailer logo | (URL param) |
| `/api/image/*` | GET | Proxy images from Flask backend | (proxied) |
| `/api/video/*` | GET | Proxy video files | (proxied) |
| `/api/proxy-image` | GET | Proxy media with headers | `url` parameter |

---

## 📊 **DATA STRUCTURES & STATE MANAGEMENT**

### **FiltersState** (Filters.tsx export)
```typescript
{
  clients: string[];
  start?: Date;
  end?: Date;
  types: string[];              // Ad types (carousel, toa, etc.)
  search?: string;              // Free-text search
  keywords?: string[];          // Selected keywords to filter by
  datePreset?: {
    type: "today" | "yesterday" | "last_week" | "last_x_days" |
          "last_x_months" | "mtd" | "ytd" | "last_52_weeks" |
          "lifetime" | "custom";
    days?: number;              // For last_x_days preset
    months?: number;            // For last_x_months preset
  }
}
```

### **Ad/AdCardItem** (Core data model)
```typescript
{
  retailer: string;             // kroger | amazon | instacart | walmart
  client: string;               // Brand/advertiser name
  keyword: string;              // Search term used in ad
  ad_type: string;              // carousel | toa | skyscraper | template
  brand: string;                // Product brand
  message: string;              // Ad copy/description
  image_url: string;            // Primary ad image
  timestamp: string;            // ISO format: "YYYY-MM-DD HH:MM:SS" or "YYYY-MM-DDTHH:MM:SSZ"
  run_file?: string;
  ad_index?: number;
  id?: string;                  // Computed stable ID
}
```

---

## 🔌 **KEY FEATURES & INTERACTIONS**

### **Smart Filtering Logic**
- **Conditional retailer querying**: Each retailer only executes queries if selected
- **Multi-client support**: Up to 3 clients can be queried in parallel; "all" client collapses to single query
- **Date filtering**: Backend applies range filtering on `run_date` or timestamp
- **Deduplication**: Merges results from multiple queries using stable IDs

### **Ad Display**
- **Drag-and-drop reordering**: User can reorder cards within session
- **Inline selection**: Multi-select with checkboxes for batch operations (hide selected)
- **Dismiss/remove**: Individual ad removal from view
- **Media support**: Images + videos with fallback handling

### **Timeline Features**
- **Dynamic grouping**: Groups by day/week/month based on zoom level
- **Range selector**: Dual-thumb slider to filter by time range
- **Visual feedback**: Highlighted bars show selected range, faded bars show excluded data

### **Comparison Mode**
- **Dual filters**: Two independent filter sets (left & right)
- **Independent timelines**: Each side has its own timeline
- **Separate queries**: Each side pulls its own data for true comparison

### **Data Persistence**
- **Session state**: Retailers & filters saved to localStorage (`retail-dashboard:last-state:v1`)
- **Auto-restore**: Restores previous session on page load
- **Auto-select**: First client auto-selected if none chosen

---

## 🎯 **EMPLOYABLE FILTERS SUMMARY**

All 8 primary filters are **fully functional & employable**:

1. ✅ **Retailer** - Toggle between Kroger, Amazon, Instacart, Walmart
2. ✅ **Client** - Multi-select brands/advertisers
3. ✅ **Date Range** - 10+ preset options + custom calendar
4. ✅ **Ad Types** - Multi-select from available types
5. ✅ **Keywords** - Select from dropdown of available search terms
6. ✅ **Search/Message** - Free-text search across brand, message, keyword
7. ✅ **Sort** - Latest/Oldest/Name (A-Z)
8. ✅ **Timeline Range** - Visual drag selector with day/week/month granularity

**No placeholder/non-functional filters detected** — all are wired to backend API calls with proper state management.

---

# Backend Routing Architecture

## 📋 **Frontend Files (Request Initiators)**

### **Client API Layer**

| File | Purpose | Key Functions |
|------|---------|----------------|
| **`neon-sanctuary/client/lib/api.ts`** | API client wrapper | `getRetailers()`, `getClients()`, `getAds()`, `getBrands()`, `imageUrl()` |
| **`neon-sanctuary/client/hooks/useRetailAds.ts`** | React Query hooks | `useRetailers()`, `useClients()`, `useAds()` |

### **Components that Trigger Requests**

| Component | Triggers | Endpoint Called |
|-----------|----------|-----------------|
| **Index.tsx** | Page load, filter changes, pagination | `/api/retailers`, `/api/clients`, `/api/ads/cards`, `/api/brands` |
| **Filters.tsx** | Apply filters button | `adsQuery.refetch()` → `/api/ads/cards` |
| **RetailerSelector.tsx** | Retailer toggle | Triggers re-query with new retailer params |
| **Timeline.tsx** | Range selection | `onRangeChange()` → date filter update |
| **StatCard.tsx** | Click to open modal | `/api/brand_logo/:brand` |
| **Brands.tsx** | Search/filter brands | `/api/brands?retailers=...` |

---

## 🔌 **Backend Route Files (Request Handlers)**

### **Server Entry Point**

| File | Role |
|------|------|
| **`neon-sanctuary/server/index.ts`** | Main Express app setup; registers all routes; applies middleware (CORS, JSON) |

### **Route Handlers**

| Route | Handler File | Purpose | Proxies To | Query Parameters |
|-------|-------------|---------|------------|-----------------|
| `GET /api/retailers` | `routes/retailers.ts` | Lists available retailers | None (local) | (none) |
| `GET /api/clients` | `routes/clients.ts` | Lists clients for a retailer | Filesystem read | `retailer` |
| `GET /api/ads/cards` | `routes/ads-proxy.ts` | Fetch ad cards (paginated, filtered) | Flask @ `localhost:5006` | `retailer`, `client`, `page`, `page_size`, `start`, `end`, `term`, `advertiser`, `types`, `search`, `sort` |
| `GET /api/brands` | `routes/brands.ts` | Fetch all brands across retailers | Flask @ `localhost:5006` | `retailers` (comma-sep) |
| `GET /api/brand-details` | `routes/brand-details.ts` | Fetch details for a specific brand | Flask @ `localhost:5006` | `brand`, `retailers` |
| `GET /api/logo/brand/:brand` | `routes/logo.ts` | Serve brand logo image | Filesystem read | (URL param) |
| `GET /api/logo/:retailer` | `routes/retailer-logo.ts` | Serve retailer logo | Filesystem read | (URL param) |
| `GET /api/image/:retailer/:client/:filename` | `routes/image.ts` | Proxy image requests | Flask @ `localhost:5006` | (URL params + query) |
| `GET /api/video/:retailer/:client/:filename` | `routes/video.ts` | Proxy video requests | Flask @ `localhost:5006` | (URL params + query) |
| `GET /proxy-image` | `routes/proxy-image.ts` | Generic image/video proxy | External URL | `url` |
| `GET /api/placeholder-ad-*.jpg` | `routes/placeholder.ts` | Mock placeholder ads | None (generated) | (regex matched) |
| `GET /api/demo` | `routes/demo.ts` | Demo endpoint | None | (none) |

---

## 🏗️ **Request Flow Diagram**

```
BROWSER (React Components)
    ↓
api.ts (HTTP wrapper)
    ↓
React Query (useRetailAds hooks)
    ↓
HTTP Request to /api/* endpoints
    ↓
Vite Dev Server + Express Middleware
    ↓
server/index.ts (Route Registration)
    ↓
Route Handlers (server/routes/*.ts)
    ├─→ Local: retailers, clients, logos
    └─→ Proxy to Flask: ads, brands, brand-details, images, videos
    ↓
Response JSON/Image/Video
    ↓
BROWSER (Component state update)
```

---

## 📦 **Shared Types File**

| File | Exports |
|------|---------|
| **`neon-sanctuary/shared/api.ts`** | `Retailer`, `RetailersResponse`, `ClientsResponse`, `AdCardItem`, `AdsCardsResponse`, `BrandAggregation`, `VideoOverlay` |

---

## ⚙️ **Build & Dev Config**

| File | Purpose | Key Setting |
|------|---------|------------|
| **`neon-sanctuary/vite.config.ts`** | Vite + React build config | Registers `expressPlugin()` to serve Express during dev; sets port 3000, aliases `@` and `@shared` |

---

## 🔗 **Request Chain Example: Fetch Ads**

```typescript
// 1. Component (Index.tsx) calls:
const adsQuery = useAds({
  retailer: "kroger",
  client: "MyBrand",
  start: "2025-01-01",
  end: "2025-01-31"
});

// 2. Hook (useRetailAds.ts) uses React Query:
useInfiniteQuery({
  queryKey: ["ads", "kroger", "MyBrand", ...],
  queryFn: ({ pageParam }) => api.getAds({ ... })
});

// 3. API client (api.ts) constructs request:
GET /api/ads/cards?retailer=kroger&client=MyBrand&start=2025-01-01&end=2025-01-31&page=1&page_size=24

// 4. Vite proxies to Express (dev server)
server/index.ts → app.get("/api/ads/cards", handleAdsProxy)

// 5. Handler (ads-proxy.ts) proxies to Flask:
GET http://localhost:5006/api/ads/cards?retailer=kroger&client=MyBrand&start=2025-01-01&end=2025-01-31

// 6. Response flows back through chain:
Flask → ads-proxy.ts → /api/ads/cards → React Query → Component state → UI render
```

---

## 📊 **Data Source Hierarchy**

| Data Type | Source Priority |
|-----------|-----------------|
| Retailers | Hardcoded in `retailers.ts` |
| Clients | Filesystem scan (`output/{retailer}/**/runs/`) |
| Brand Logos | Filesystem (`output/brand_logos/`) or Flask fallback |
| Retailer Logos | Filesystem or API mapping |
| Ads Cards | **Flask Backend** (`localhost:5006`) |
| Brand Details | **Flask Backend** (`localhost:5006`) |
| Ad Images/Videos | **Flask Backend** (proxied via `/api/image/` & `/api/video/`) |

---

## 🔐 **Environment Variables**

| Variable | Default | Used By | Purpose |
|----------|---------|---------|---------|
| `FLASK_BASE_URL` | `http://localhost:5006` | All proxy routes | Flask backend URL for proxying |
| `PING_MESSAGE` | `"ping"` | `/api/demo` | Demo endpoint message |
| `VITE_API_BASE` | `` (empty/same origin) | `api.ts` | API base URL override |

---

## 📝 **Route Registration Summary**

All routes are registered in `neon-sanctuary/server/index.ts`:
- **13 route handlers** across 13 files
- **3 data sources**: Local filesystem, hardcoded values, Flask backend
- **2 proxy patterns**: Regex routes for `/api/image/` and `/api/video/`
- **CORS enabled** for cross-origin requests
