# Context Seed — Multi‑Retailer TOA Scraper

USE MCP: wafuzio/RMN@insta_debug_login (read)

This is the canonical snapshot of how the tool is structured. Keep it short, current, and true.

## Objective
- One GUI + scheduler that runs "search capture → image extraction" across multiple retailers.
- Reuse a persistent browser profile per retailer so session‑gated CDN images (TOA/Skyscraper) render reliably.
- Keep Kroger fully working; add retailers without breaking existing behavior.

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
- `ad_extractors/toa_extractor.py` - TOA ads
- `ad_extractors/skyscraper_extractor.py` - Skyscraper ads
- `ad_extractors/carousel_extractor.py` - Carousel ads (Featured only)

**API & Frontend:**
- `web/builder_server_v2.py` - Flask API for Builder GUI
- `neon-sanctuary/` - React frontend (Builder GUI)

**Logs:**
- `logs/<retailer>/keyword_input.log` - GUI activity
- `logs/<retailer>/image_extract_*.log` - Extraction logs
- `logs/<retailer>/locks/*.lock` - Process locks (stale locks can hang extraction)

## Current Work
- [ ] **JSON Schema Standardization** - PARTIALLY COMPLETE
  - Many retailers now output consistent schema
  - Some retailer-specific fields remain
  - API has workarounds for legacy formats
  - See: `docs/ARTIFACT_TAXONOMY.md` → JSON Schema

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