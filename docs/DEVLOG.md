# Dev Log

Append-only notes by retailer/division. Keep each bullet to ~2 lines and link the PR.

Repo: wafuzio/RMN
Branch/ref: insta_debug_login
Scope: summarize all .md files, paste nothing unless asked
OK to fetch and read file contents: yes I will:
Enumerate .md with a repo tree/list call.
Fetch file contents via file API.
Return a concise map + summaries. I’ll only paste full content if you ask.
Option B — If tools seem blocked (private repo or session without GitHub wiring) Use raw links I can read without auth:

Example: https://raw.githubusercontent.com/wafuzio/RMN/insta_debug_login/docs/INSTACART_INTEGRATION.md https://raw.githubusercontent.com/wafuzio/RMN/insta_debug_login/README.md Tell me “Summarize all” or name specific files to paste.
Option C — One-line local list + paste back Run locally and paste the output:

git fetch origin insta_debug_login && git checkout insta_debug_login
git ls-tree -r --name-only HEAD | grep -Ei '.md$' Then say “Summarize all of these,” and I’ll ask for any I need to fetch via raw links.

## Kroger

**2025-10-02:** Headless timeouts in packaged app; headed ok. Adopted nav-first capture, headed-but-hidden mode, SRP fallback, exit 1 on zero saves. Require `source_url` in JSON. Added minimization flags to hide browser window. (PR #TBD)

## Instacart

**2025-09-??:** Location pin via zip; login modal guard; headless ok. Element screenshot from SRP (no direct image URLs). (PR #118)

## Walmart

**2025-10-06 (Final):** Production-ready PerimeterX bypass with comprehensive telemetry. Removed heavy anti-fingerprinting (playwright-stealth only), removed homepage scrolling (major trigger), added dwell time after typing (400-1100ms), prefer button click over Enter, micro caret movement, immediate retry controller (3 quick retries for same widget), longer steady holds (6.8-10.2s adaptive), off-domain guard (nav-only), JSONL step logger with millisecond-precision telemetry. Successfully bypasses PX challenges with detailed diagnostics. (PR #TBD)

**2025-10-06 (Initial):** Complete PerimeterX bypass implementation. Native wheel scrolling (replaced JS scrollTo), auto press-and-hold solver (3.1-3.6s), PX cookie verification (_px3/_pxvid), modal + /blocked detection, off-domain guard rails (blocks Google), telemetry (tracing/video/crash hooks), stable per-profile fingerprint, playwright-stealth integration, empty Chrome args (no banners), chromium_sandbox=True. Successfully captures all ad units through PX challenges. (PR #TBD)

**2025-10-05:** Initial integration complete. Selector-based ad detection (Top_Banner, SBA, Tile_Takeover, SBV). Added anti-bot stealth mode: disabled AutomationControlled, injected navigator.webdriver override, homepage-first navigation pattern with random delays. Path taxonomy added (critical for GUI integration). (PR #TBD)

## Internal

**2025-10-02:** README taxonomy now auto-generated from `utils/path_taxonomy.py`; added `scripts/docs/update_docs.py` and CI check. Created comprehensive onboarding docs: RETAILER_ONBOARDING_CHECKLIST.md, PLAYWRIGHT_BOOTSTRAP.md, ARTIFACT_TAXONOMY.md, COMMON_ISSUES.md. (PR #TBD)

---

## Archive (Reverse-chronological)

## 2025‑10‑01
- Repository reorganization and path fixes
  - Fixed all import paths after moving files to archived/, extractors/, retailers/
  - kroger_search_and_capture.py stays in root; kroger_ad_core.py moved to archived/
  - Updated process_saved_html.py to import from archived.kroger_ad_core
  - Fixed retailers/kroger/adapter.py to import from root, not archived
  - Added project root to sys.path in extractor scripts for browser_lock import

- Output directory consolidation
  - Fixed duplicate output paths (output/client vs output/kroger/client)
  - Updated all functions to use output_dir_for() for retailer-scoped paths
  - Fixed compute_runs_root() to handle both old and new path structures
  - Backward compatibility: old paths still read, new saves go to output/kroger/client

- macOS app launcher improvements
  - Renamed app to "Retail Ad Monitor" (py2app)
  - In-process launcher runs live source code from SCRAPER_HOME (no rebuild needed)
  - Added PYTHON_EXEC support for custom interpreter (e.g., venv)
  - Fixed Tk/Cocoa menubar crash with inline View menu (RAM_NO_NATIVE_MENUBAR guard)
  - Added boot logging: logs/app_launcher_boot.log, logs/gui_boot.log
  - Launcher reads config/launcher.env for environment variables

- Theme system hardening
  - Added _safe_ttk_themes() to filter out aqua on macOS (prevents menubar crash)
  - Theme and palette persistence to config/ui.json
  - Inline menubutton fallback when native menubar disabled

- Documentation updates
  - Updated README.md with correct app name, py2app commands, environment variables
  - Updated CONTEXT_SEED.md with current architecture and completed tasks
  - Fixed all placeholder paths in documentation

## 2025‑09‑30
- Multi‑retailer seam introduced
  - core/retailers.py: RetailerAdapter + registry
  - core/run_context.py: RunContext dataclass
  - core/paths.py: retailer‑aware output/logs helpers
  - retailers/kroger/adapter.py: wraps existing Kroger pipeline
  - retailers/amazon/adapter.py: initial implementation (persistent profile, search capture, basic selectors); maps Amazon placements to TOA/Sky/Carousel
  - keyword_input.py: Retailer dropdown wired to adapter registry; schedules saved with "retailer"
  - README updated to reflect new structure and session persistence

- Auth helper
  - auth/retailer_auth.py: one‑time Playwright login; saves persistent Chrome user_data_dir per retailer

- Scheduler UX hardening
  - Filters minute options to only allowed slots (cross‑client conflicts)
  - Disables Save on conflicts; optional auto‑fix on save (apply next available time)

- GUI usability
  - Client dropdown cleaned: "<choose from menu>" no longer creates folders
  - “New…” moved to button; clients alphabetized
  - High‑contrast ttk styles added (Primary/Secondary/Danger buttons), with aqua→clam fallback

- Stability
  - UTF‑8 enforced for logging + subprocess streaming (PYTHONIOENCODING, encoding="utf‑8", errors="replace")
  - Extractor passed --profile-dir where present; default profile fallback for Kroger

## 2025‑09‑28
- Post‑processing watchdog: 6‑minute wall clock cap on image extraction
- Success criteria updated: Carousel alone does not count as success; warn after retry
- Stale lock cleanup command documented

## 2025‑09‑26
- Dropdown placeholder and folder creation bug fixed
- Added conflict indicator labels and suggestion handler

(Older entries pruned; see git history)
