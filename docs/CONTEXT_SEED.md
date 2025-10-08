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

### instacart (new)
- Persistent profile via INSTACART_PROFILE_DIR.
- Store selection via INSTACART_STORE env var (default: publix).
- URL pattern: https://www.instacart.com/store/{store}/s?k={keyword}
- Ad types: Shoppable Display Ad, Shoppable Video Ad (div.e-1qzz7bi), Display Ad (div.e-1hv1sre), Sponsored Label (div.e-cwus85).
- Verified: 8+ ads detected with authenticated session.

### walmart (WIP - PerimeterX challenges)
- Persistent profile via WALMART_PROFILE_DIR
- URL: https://www.walmart.com/search?q={keyword}
- Ad types: programmatic banner (a.ad, a.adctr), SBA ([data-testid="sba-container"]), tile takeover ([data-testid="tile-take-over"]), SBV ([data-testid="search-video-in-grid"])
- Meta: stores outbound links (sp/track rd=…) and video assets if available
- **Status**: Still being flagged by PerimeterX bot detection - no successful scrapes yet
- **PerimeterX Evasion (implemented)**: Human-like typing, micro-mouse movements, drift reading, back-scroll peeks, auto press-and-hold CAPTCHA solver
- **Forensics**: Comprehensive run reports (run_report.json + run_report.md) with timings, network stats, PX solver stats, WebGL info, cookie persistence
- **Bail System**: Stops retrying on non-retryable failures (px_locked, hard_block, fatal)
- **Resilient Navigation**: 3-tier fallback (domcontentloaded → commit+search → networkidle)
- **Debug Tools**: 
  - Break on PX modal appearance (GUI checkbox)
  - Break on /blocked redirect (GUI checkbox)
  - Line-by-line trace logging
  - Playwright trace viewer (trace.zip saved per run)
  - steps.jsonl with microsecond timestamps for all events
  - run_report.md for quick diagnosis (timings, PX stats, network errors)

## Auth & Profiles
- One-time human login to each retailer using Playwright and a persistent user_data_dir.
- Helper: auth/retailer_auth.py
  - Example: python3 auth/retailer_auth.py --retailer amazon --profile-dir ~/Documents/Amazon_Scrape/profiles/amazon
  - SCRAPER_HOME → base dir (default: ~/Documents/Amazon_Scrape); launcher uses this first
  - PYTHON_EXEC → optional custom Python interpreter path (e.g., .venv/bin/python)
  - KROGER_PROFILE_DIR → Kroger profile path
  - AMZ_PROFILE_DIR → Amazon profile path
  - INSTACART_PROFILE_DIR → Instacart profile path
  - INSTACART_STORE → Instacart store slug (default: publix)
  - WALMART_PROFILE_DIR → Walmart profile path

## macOS App Bundle
- Native app: "Retail Ad Monitor.app" (built with py2app)
- In-process launcher runs live source code from SCRAPER_HOME
- No rebuild needed for code changes (alias mode: `python3 setup.py py2app -A`)
- Uses inline View menu to avoid Tk/Cocoa menubar crashes
- Boot logs: logs/app_launcher_boot.log, logs/gui_boot.log
- Supports PYTHON_EXEC env var for custom interpreter (e.g., venv)

## Success Rule
- A run is "successful" if at least one TOA or Skyscraper image is produced (Carousel alone ≠ success).
- GUI shows Success dialog only under that condition; otherwise warns after retry.

## Key Files & Locations
- GUI: keyword_input.py (Tkinter, retailer-aware)
- Launcher: launcher.py (in-process runner for .app bundle)
- Kroger scraper: kroger_search_and_capture.py (root directory)
- Walmart scraper: walmart_search_and_capture.py (root directory)
- Ad extraction: archived/kroger_ad_core.py (HTML → JSON)
- Image extractors: extractors/screenshot_ad_image.py (main), extractors/screenshot_toa_image.py (shim)
- Process HTML: process_saved_html.py (calls kroger_ad_core, creates run_results_*.json)

- GUI log: logs/<retailer>/keyword_input.log
- Extractor logs: logs/<retailer>/image_extract_YYYYMMDD_HHMMSS.log
- Locks: logs/<retailer>/locks/*_image_extraction.lock (stale locks can hang post‑processing)

## Walmart Run Reports
Every Walmart run produces:
- **run_report.json** - Machine-readable metrics
- **run_report.md** - Human-readable summary
- **Contents**: Outcome (success/fail/bail), timings (to_home_ms, after_submit_px_ms, results_ready_ms), environment (UA, WebGL), cookies (pre/post counts), PX stats (tries, cycles, cleared), network forensics (req_failed, resp_doc, route_errors), artifact paths (steps_log, trace_zip, screenshots, HTML, meta)

## Open Worklist
- [x] Fixed path imports after repo reorg (archived/, extractors/, retailers/)
- [x] Fixed duplicate output directories (output/client vs output/kroger/client)
- [x] Fixed browser_lock import in extractors
- [x] macOS app launcher with in-process execution (single dock icon)
- [x] Bail system to stop blind retries on non-retryable failures
- [x] Run report system for Walmart (JSON + Markdown)
- [x] Comprehensive forensics and debug tools for Walmart
- [ ] **CRITICAL: Solve Walmart PerimeterX detection** - Currently 0% success rate
  - Implemented: Human behavior, CAPTCHA solver, forensics
  - Still flagged: Need to analyze trace.zip, steps.jsonl, run_report.md patterns
  - Consider: Residential proxies, longer dwell times, profile aging
- [ ] Tighten Amazon selectors for SB/SBV/SP and right‑rail SD
- [ ] GUI "Manage Login…" button → launches auth/retailer_auth.py for selected retailer
- [ ] Back‑compat scan to migrate old schedules into output/kroger/<client>/ (optional move or symlink)
- [ ] Unit tests for scheduler_utils allowed_minutes/has_conflict

## Quick Test Checklist
- export KROGER_PROFILE_DIR=~/ChromeProfiles/kroger
- export AMZ_PROFILE_DIR=~/ChromeProfiles/amazon
- export INSTACART_PROFILE_DIR=~/ChromeProfiles/instacart
- export INSTACART_STORE=publix
- export WALMART_PROFILE_DIR=~/ChromeProfiles/walmart
- python3 keyword_input.py → Retailer=Kroger → run 1 keyword → expect TOA/Sky PNGs
- Switch to Amazon → run 1 keyword → expect runs/*.html + TOA fallback PNG (until selectors are tuned)
- Switch to Instacart → run 1 keyword → expect 8+ ads (3 shoppable, 1 banner, 4 sponsored)
- Switch to Walmart → run 1 keyword → expect run_report.md with populated metrics
- tail -f logs/<retailer>/keyword_input.log and the newest logs/<retailer>/image_extract_*.log

## Docs Organization
- **docs/** - Active documentation
  - CONTEXT_SEED.md - This file (canonical snapshot)
  - DEVLOG.md - Development log
  - COMMON_ISSUES.md - Troubleshooting guide
  - ADDING_NEW_RETAILER.md - How to add a new retailer
  - ARTIFACT_TAXONOMY.md - Output file structure
  - INSTACART_INTEGRATION.md - Instacart-specific notes
  - WALMART_PERIMETERX_COMPLETE.md - Walmart PX evasion guide
  - WALMART_PROXY_SETUP.md - Walmart proxy configuration
- **docs/reference/** - Large HTML samples and reference materials
- **docs/archive/** - Completed/old documentation