# Dev Log

Append-only notes by retailer/division. Keep each bullet to ~2 lines and link the PR.

## Kroger

**2025-10-02:** Headless timeouts in packaged app; headed ok. Adopted nav-first capture, headed-but-hidden mode, SRP fallback, exit 1 on zero saves. Require `source_url` in JSON. Added minimization flags to hide browser window. (PR #TBD)

## Instacart

**2025-09-??:** Location pin via zip; login modal guard; headless ok. Element screenshot from SRP (no direct image URLs). (PR #118)

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
