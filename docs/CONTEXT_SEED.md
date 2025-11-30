# Multi-Retailer Ad Scraper

**What it does:** Automated tool for capturing and analyzing retail media ads (TOA, Skyscraper, Display Ads, etc.) from Kroger, Walmart, Instacart, and Amazon.

**Use case:** Competitive intelligence, ad monitoring, and retail media analysis for brands and agencies.

---

## Quick Start

### 1. Prerequisites
- Python 3.9+
- Playwright (for browser automation)
- Node.js 18+ (for Builder GUI frontend)

### 2. Installation
```bash
# Install Python dependencies
pip install -r requirements.txt
playwright install chromium

# Install frontend dependencies (optional - for Builder GUI)
cd neon-sanctuary && pnpm install
```

### 3. First Run
```bash
# Set up authentication (one-time per retailer)
python3 auth/retailer_auth.py --retailer kroger

# Launch GUI
python3 keyword_input.py
```

Select a retailer, enter a keyword (e.g., "ice cream"), and click "Start Scraping". Results appear in `output/<retailer>/<client>/`.

---

## Project Overview

**Objective:**
- One GUI + scheduler that runs "search capture → image extraction" across multiple retailers
- Reuse persistent browser profiles so session-gated CDN images render reliably
- Extensible architecture - add retailers without breaking existing ones

## Architecture (seam-first)

- RetailerAdapter (core/retailers.py)
  - Hooks every adapter must implement:
    - search_and_capture(keyword, ctx) -> dict {'ok': bool, 'bail': bool, 'reason': str|None, 'result': CaptureResult}
    - collect_pairs_for_run(ctx, run_start_ts) -> list[(json_path, html_path)]
    - extract_images(json_path, html_path, ctx) -> {"toa": int, "sky": int, "car": int, "log": path}
  - Registry: register(adapter); GUI pulls display names from registry.

- Run context (core/run_context.py)
  - RunContext fields:
    - retailer, client, base_dir, output_dir, runs_dir, logs_dir
    - profile_dir (persistent Chrome user data dir)
    - script_dir (where screenshot_* live)

- Paths (core/paths.py)
  - output/<retailer>/<client>/{runs, TOA, Skyscraper, Carousel}
  - logs/<retailer>/{keyword_input.log, image_extract_*.log, locks/…}
  - Back‑compat: old schedules in output/<client>/schedule_config.json still read as retailer="kroger"; new saves go to output/kroger/<client>/schedule_config.json and include "retailer".

- Import paths (post-reorg):
  - kroger_search_and_capture.py → root directory
  - kroger_ad_core.py → archived/ directory
  - Extractors add project root to sys.path for browser_lock import

- GUI (keyword_input.py)
  - Retailer dropdown (defaults to Kroger), Client dropdown + New…, keyword box.
  - Start Scraping = two‑phase:
    1) adapter.search_and_capture → saves runs/*.html + runs/*.json
    2) collect_pairs_for_run → extract_images per pair → write PNGs
  - Scheduler: conflict‑aware, filters unavailable minute options, disables Save on conflicts.
  - Bail system: GUI stops retrying when adapter returns bail=True (px_locked, hard_block, fatal)

## Current Adapters

### kroger (stable)
- Persistent profile via KROGER_PROFILE_DIR (or default path).
- Produces PNGs in TOA/Skyscraper/Carousel; success = (TOA or Skyscraper) ≥ 1.

### amazon (WIP)
- Persistent profile via AMZ_PROFILE_DIR.
- Mirrors Kroger's outputs; initial selectors for SB/SBV/SP; refine with samples.

### instacart (stable)
- Persistent profile via INSTACART_PROFILE_DIR.
- Store selection via INSTACART_STORE env var (default: publix).
- URL pattern: https://www.instacart.com/store/{store}/s?k={keyword}
- Uses semantic selectors (data-testid, alt, role) not hashed CSS classes
- Ad types: Shoppable Display Ad, Shoppable Video Ad (with video download/HLS URL capture)
- Screenshot capture: CDP with page coordinates (not viewport coords) for accurate cropping
- See: `retailers/instacart/README.md`, `docs/COMMON_ISSUES.md` → Instacart ad screenshots

### walmart (functional - security bypassed)
- Persistent profile via WALMART_PROFILE_DIR
- URL: https://www.walmart.com/search?q={keyword}
- Ad types: programmatic banner, SBA, tile takeover, SBV
- **Status**: PerimeterX security bypassed - scraper functional
- Evasion: Human-like behavior, CAPTCHA solver, forensics
- Outputs: run_report.md + images in ad-type folders
- See: `docs/WALMART_PERIMETERX_COMPLETE.md`

## Authentication & Browser Profiles
Each retailer requires a one-time human login using Playwright with persistent browser profiles.

**Setup:**
```bash
python3 auth/retailer_auth.py --retailer kroger --profile-dir ~/ChromeProfiles/kroger
```

**Environment Variables:**
- `KROGER_PROFILE_DIR` - Kroger browser profile path
- `AMZ_PROFILE_DIR` - Amazon browser profile path
- `INSTACART_PROFILE_DIR` - Instacart browser profile path
- `INSTACART_STORE` - Instacart store slug (default: publix)
- `WALMART_PROFILE_DIR` - Walmart browser profile path

## macOS App Bundle (Kroger TOA Scraper)
- **App:** "Kroger TOA Scraper.app" (built with py2app)
- **Launcher:** Runs live source code from project directory (no rebuild needed for code changes)
- **Logs:** `logs/app_launcher_boot.log`, `logs/gui_boot.log`
- **Environment:** Supports `PYTHON_EXEC` for custom interpreter (e.g., venv)

## Key Files

**Scrapers:**
- `kroger_search_and_capture.py` - Kroger scraper
- `walmart_search_and_capture.py` - Walmart scraper (with PX evasion)
- `keyword_input.py` - GUI (Tkinter, multi-retailer)
- `launcher.py` - App bundle launcher

**Extractors:**
- `extractors/screenshot_ad_image.py` - Universal ad image extractor (Kroger, Instacart)
- `extractors/screenshot_toa_image.py` - Legacy TOA-specific extractor
- `ad_extractors/toa_extractor.py` - TOA ads (legacy)
- `ad_extractors/skyscraper_extractor.py` - Skyscraper ads (legacy)
- `ad_extractors/carousel_extractor.py` - Carousel ads (Featured only, legacy)

**API & Frontend:**
- `web/builder_server_v2.py` - Flask API for Builder GUI
- `neon-sanctuary/` - React frontend (Builder GUI)

**Repair Tools:**
- `tools/rebuild_kroger_images_from_archive.py` - Regenerate missing images from archived HTML/JSON pairs
- `tools/repair_kroger_image_paths.py` - Backfill missing image paths where files exist
- `tools/fix_bluey_rebuild_labels.py` - Fix specific brand mislabeling from rebuilds
- `tools/repair_blue_bunny_sweet_pairings.py` - Fix Unknown brand ads with known creative
- `tools/build_brand_index.py` - Rebuild brand index from all run JSONs

**Logs:**
- `logs/<retailer>/keyword_input.log` - GUI activity
- `logs/<retailer>/image_extract_*.log` - Extraction logs
- `logs/<retailer>/locks/*.lock` - Process locks (stale locks can hang extraction)

## Canonical Schema Migration

**Status:** Walmart ✅ COMPLETE | Kroger ⏳ TODO | Instacart ⏳ TODO | Amazon ⏳ TODO

### Walmart Migration (Completed)
Successfully migrated all Walmart data to canonical schema with 100% image coverage:

**Process:**
1. **Legacy Migration** (`tools/migrate_walmart_legacy_to_canonical.py`)
   - Migrated 19 nested `results[].ads[]` JSONs → flat `ads[]` format
   - Converted timestamps to ISO 8601 with Z
   - Normalized ad types: `sba` → `SBA`, `sbv` → `SBV`, `tile_takeover` → `Tile_Takeover`

2. **Cross-Contamination Fix**
   - Fixed 58 JSONs with wrong `retailer: "kroger"` → `retailer: "walmart"`
   - Deleted 61 malformed flat JSONs (wrong URLs, empty ads)

3. **Orphaned Image Recovery** (`tools/create_json_for_orphaned_images.py`)
   - Created 17 canonical JSONs for orphaned images matched by timestamp

4. **Batch Rebuild** (`tools/batch_rebuild_walmart_runs_from_images.py`)
   - Rebuilt 246 canonical run JSONs from image filenames
   - Used filename metadata: retailer, brand, ad_type, client, keyword, timestamp
   - Achieved 100% image coverage (283/283 images referenced)

**Final Results:**
- 354 ads in canonical format (161 SBA, 139 SBV, 54 Tile_Takeover)
- 297 images properly linked
- 0 orphaned images
- All JSONs: `{retailer, client, keyword, timestamp (ISO Z), run_id, ads[]}`
- All ads: `{id, type, brand, brand_logo, image_path, metadata}`

**Tools Created:**
- `tools/migrate_walmart_legacy_to_canonical.py` - Migrate legacy nested JSONs
- `tools/create_json_for_orphaned_images.py` - Recover orphaned images by timestamp
- `tools/batch_rebuild_walmart_runs_from_images.py` - Rebuild runs from image filenames
- `tools/audit_adtype_mapping.py` - Audit JSON/image compliance

**Next:** Apply same process to Kroger and Instacart (both use legacy `results[].ads[]` format)

---

## Current Work
- [x] **Walmart JSON Schema** - ✅ COMPLETE (100% canonical)
- [ ] **Kroger JSON Schema** - TODO (legacy `results[].ads[]` format)
- [ ] **Instacart JSON Schema** - TODO (legacy `results[].ads[]` format)
- [ ] **Amazon JSON Schema** - TODO (not yet implemented)
- [x] **Brand Lexicon Integration** - ✅ COMPLETE
  - All retailers use `core/brands.py` for canonicalization
  - Fuzzy matching improved to ignore short tokens (≤4 chars)
  - Full-phrase synonyms prevent generic word collisions

- [x] **Kroger Image Rebuild Tools** - ✅ COMPLETE (Nov 2025)
  - `tools/rebuild_kroger_images_from_archive.py` - Offline image regeneration from archived HTML
  - `tools/repair_kroger_image_paths.py` - Backfill missing image_path fields where PNGs exist
  - `tools/fix_bluey_rebuild_labels.py` - Fix mislabeled Blue Buffalo ads from 2025-11-24 rebuild
  - `tools/repair_blue_bunny_sweet_pairings.py` - Fix Blue Bunny TOA ads showing as Unknown
  - **Context:** Kroger runs had missing `image_path` fields despite PNGs existing on disk
  - **Root cause:** Screenshot extractor failed to wire paths back into JSON (URL mismatch + structure mismatch)
  - **Solution:** Repair tools backfill paths and regenerate missing images from archived HTML/JSON pairs

- [x] **Brand Canonicalization Improvements** - ✅ COMPLETE (Nov 2025)
  - Removed hardcoded 'blue' skip from fuzzy matching
  - Ignore short tokens (≤4 chars) in fuzzy matching to prevent generic word collisions
  - Added full-phrase synonyms for Blue Buffalo, Blue Bunny, Bluey, Birds Eye, Bertolli, Annie Chun, P.F. Chang's
  - **Context:** "Blue Pet Foods" was incorrectly canonicalized to "Bluey" instead of "Blue Buffalo"
  - **Root cause:** Fuzzy token matching on "blue" matched short brand name "Bluey"
  - **Solution:** Skip short tokens in fuzzy matching; use exact/phrase matching first
  - Prevents brand collisions while preserving distinct brands

- [ ] **Amazon selectors refinement**
  - Tighten selectors for SB/SBV/SP and right-rail SD
  - Verify ad type names

- [ ] **GUI enhancements**
  - "Manage Login…" button → launches auth/retailer_auth.py
  - Schedule migration tool for old configs

## Quick Test Commands

**Setup environment:**
```bash
export KROGER_PROFILE_DIR=~/ChromeProfiles/kroger
export AMZ_PROFILE_DIR=~/ChromeProfiles/amazon
export INSTACART_PROFILE_DIR=~/ChromeProfiles/instacart
export INSTACART_STORE=publix
export WALMART_PROFILE_DIR=~/ChromeProfiles/walmart
```

**Run scrapers:**
```bash
python3 keyword_input.py
# Select retailer → run keyword → check output/
```

**Expected outputs:**
- Kroger: `TOA/`, `Skyscraper/`, `Carousel/` images + JSON in `runs/`
- Walmart: `run_report.md` + images in ad-type folders + JSON in `runs/`
- Instacart: Images in `Shoppable_Display_Ads/`, `Shoppable_Video_Ads/`, `Main/` + JSON/HTML in `runs/`
- Amazon: Images in ad-type folders + JSON in `runs/`

**Monitor logs:**
```bash
tail -f logs/<retailer>/keyword_input.log
tail -f logs/<retailer>/image_extract_*.log
```

**Test Builder GUI:**
```bash
cd neon-sanctuary && pnpm dev  # Frontend on :48752
python3 web/builder_server_v2.py  # API on :5006
```

## Documentation

**Main Docs:**
- `CONTEXT_SEED.md` - This file (project overview)
- `ARTIFACT_TAXONOMY.md` - Directory structure, file naming, JSON schema
- `BUILDER_GUIDE.md` - Builder GUI usage and architecture
- `WALMART_PERIMETERX_COMPLETE.md` - Walmart PX evasion strategies
- `COMMON_ISSUES.md` - Troubleshooting guide

**Reference:**
- `docs/reference/` - HTML samples and reference materials
- **docs/archive/** - Completed/old documentation