# ✅ Implementation Checklist

## Amazon Integration

- [x] **Authentication Setup**
  - [x] Amazon profile created at `~/Documents/Amazon_Scrape/profiles/amazon`
  - [x] `AMAZON_PROFILE_DIR` added to `config/launcher.env`
  - [x] Setup script available: `scripts/setup_amazon_profile.sh`

- [x] **Adapter Configuration**
  - [x] Updated `profile_env` to `AMAZON_PROFILE_DIR`
  - [x] Implemented correct ad type selectors
  - [x] Updated extraction logic for 4 ad types

- [x] **Path Taxonomy**
  - [x] Removed legacy folders (TOA, Skyscraper, Carousel)
  - [x] Added correct folders:
    - [x] Sponsored_Brand_Video
    - [x] Sponsored_Product
    - [x] Featured_Brand
    - [x] Sponsored_Carousel

- [x] **Registration**
  - [x] Adapter imported in `keyword_input.py`
  - [x] Verified registration in adapter list

- [ ] **Testing**
  - [ ] Run test search via Tkinter GUI
  - [ ] Verify images saved to correct folders
  - [ ] Check JSON metadata is correct

---

## Builder.io API

- [x] **Server Implementation**
  - [x] Created `web/builder_server_v2.py`
  - [x] Implemented all core endpoints
  - [x] Added retailer-aware path resolution
  - [x] Added taxonomy support
  - [x] Added CORS configuration
  - [x] Added pagination support
  - [x] Fixed "runs" appearing in retailer list

- [x] **Documentation**
  - [x] Created `docs/BUILDER_API.md` (full reference)
  - [x] Created `docs/BUILDER_QUICKSTART.md` (quick start)
  - [x] Created `docs/SESSION_SUMMARY.md` (session notes)

- [x] **Supporting Files**
  - [x] Created `scripts/start_api_server.sh`
  - [x] Created `web/test_api.html`
  - [x] Updated `builder.config.json`

- [ ] **Testing**
  - [ ] Restart server with fix
  - [ ] Test all endpoints with curl
  - [ ] Test with test_api.html page
  - [ ] Verify images load correctly

- [ ] **Deployment**
  - [ ] Install ngrok: `brew install ngrok`
  - [ ] Start ngrok tunnel: `ngrok http 5006`
  - [ ] Set ALLOWED_ORIGINS with ngrok URL
  - [ ] Test CORS from Builder.io

---

## Builder.io Integration

- [ ] **Data Source Setup**
  - [ ] Add REST API data source in Builder.io
  - [ ] Configure base URL (ngrok)
  - [ ] Test connection

- [ ] **Data Models**
  - [ ] Create Retailer List query
  - [ ] Create Client List query
  - [ ] Create Terms List query
  - [ ] Create Ad Cards query
  - [ ] Test all queries

- [ ] **Page Building**
  - [ ] Create homepage with retailer selector
  - [ ] Create client selector dropdown
  - [ ] Create term filter dropdown
  - [ ] Create ad cards grid
  - [ ] Add pagination controls
  - [ ] Add loading states
  - [ ] Add error handling

- [ ] **Components**
  - [ ] Create AdCard component
  - [ ] Create RetailerSelector component
  - [ ] Create FilterBar component
  - [ ] Style with brand colors

---

## Next Steps (Priority Order)

### 🔴 High Priority (Do Today)
1. [ ] Restart API server to apply "runs" filter fix
2. [ ] Test Amazon scraper with real search
3. [ ] Verify API endpoints work correctly
4. [ ] Test with test_api.html page

### 🟡 Medium Priority (This Week)
1. [ ] Set up ngrok tunnel
2. [ ] Configure Builder.io data source
3. [ ] Build first Builder.io page
4. [ ] Test end-to-end flow

### 🟢 Low Priority (Future)
1. [ ] Add Server-Sent Events for live updates
2. [ ] Add POST endpoints for triggering scrapes
3. [ ] Add analytics dashboard
4. [ ] Add export functionality (CSV, PDF)
5. [ ] Add user authentication
6. [ ] Deploy to production server

---

## Quick Commands

### Start API Server
```bash
cd /Users/dan.maguire/Documents/Amazon_Scrape
python3 web/builder_server_v2.py
```

### Test API
```bash
# List retailers
curl http://localhost:5006/api/retailers

# List clients
curl "http://localhost:5006/api/clients?retailer=kroger"

# Get ad cards
curl "http://localhost:5006/api/ads/cards?retailer=kroger&client=bandaid&page=1&page_size=24"
```

### Start ngrok
```bash
ngrok http 5006
```

### Set Environment
```bash
export ALLOWED_ORIGINS="https://builder.io,https://YOUR-NGROK-URL"
export API_KEY="your-secret-key"
```

### Test Amazon Scraper
```bash
python3 keyword_input.py
# Select Amazon, enter search term, run
```

---

## Files to Review

- `web/builder_server_v2.py` - Main API server
- `docs/BUILDER_API.md` - API documentation
- `docs/BUILDER_QUICKSTART.md` - Quick start guide
- `docs/SESSION_SUMMARY.md` - Session notes
- `web/test_api.html` - Test page
- `retailers/amazon/adapter.py` - Amazon adapter
- `utils/path_taxonomy.py` - Taxonomy definitions

---

## Known Issues

1. ✅ **FIXED:** "runs" appearing in retailer list
2. ⚠️ **TODO:** Test Amazon scraper with real data
3. ⚠️ **TODO:** Verify all image paths resolve correctly
4. ⚠️ **TODO:** Add rate limiting to API (optional)

---

**Status:** Ready for testing and Builder.io integration! 🚀
