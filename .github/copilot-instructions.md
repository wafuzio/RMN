# Copilot Instructions

## Project Overview

Multi-retailer ad scraping platform for tracking Targeted Onsite Ads (TOAs) across retailers (Kroger, Instacart, Amazon, Walmart, Target, TikTok Shop). Built on Playwright with a Tkinter GUI, optional Flask web dashboard, and a conflict-aware background scheduler.

## Commands

Always activate the venv first: `source .venv/bin/activate`

```bash
# Run the GUI
python keyword_input.py

# Start the background scheduler daemon
./start_scheduler.sh

# Start the optional web dashboard (port 5006)
python3 web/builder_server_v2.py

# Update auto-generated README taxonomy table from code
make docs

# Verify README taxonomy is in sync with code (also runs in CI)
make docs-check

# Clean Python cache
make clean

# Run an individual test
python tests/test_amazon_adapter.py
python scripts/test_walmart_adapter.py
```

There is no single test runner — test scripts live in `tests/` and `scripts/test_*.py` and are run directly.

## Architecture

### Core Layer (`core/`)

- **`core/retailers.py`** — `RetailerAdapter` base class + simple `_REG` dict registry. `register()` adds an adapter; `get(slug)` retrieves it; `list_adapters()` returns all.
- **`core/run_context.py`** — `RunContext` dataclass passed through every scrape run: holds `retailer`, `client`, `output_dir`, `runs_dir`, `logs_dir`, `profile_dir`, `script_dir`.
- **`core/paths.py`** — helpers that create output and log directories using the taxonomy.

### Retailer Adapters (`retailers/<slug>/adapter.py`)

Each retailer is a subclass of `RetailerAdapter` with three hooks:

```python
def search_and_capture(self, keyword: str, ctx: RunContext) -> bool: ...
def collect_pairs_for_run(self, ctx, run_start_ts: float) -> list[tuple[str, str]]: ...
def extract_images(self, json_path: str, html_path: str, ctx) -> dict: ...
```

The GUI discovers adapters automatically via the registry — no UI changes needed when adding a new retailer.

### Path Taxonomy (`utils/path_taxonomy.py`)

**Single source of truth** for allowed output folders per retailer. `ALLOWED_FOLDERS` dict and `WALMART_LABEL_TO_FOLDER` dict drive both directory creation and validation. The README taxonomy table is auto-generated from this file — **never edit the `<!-- TAXONOMY_START -->…<!-- TAXONOMY_END -->` block in README.md by hand**; run `make docs` instead.

### Output Structure

```
output/<retailer>/<client>/
  runs/           # run_results_*.json + search_results_*.html
  TOA/            # (retailer-specific ad type folders per taxonomy)
  Skyscraper/
  ...
logs/<retailer>/
  keyword_input.log
  image_extract_<timestamp>.log
  locks/*_image_extraction.lock
```

### Scheduler

`scheduler_daemon.py` manages conflict-aware scheduling (5-minute windows, per-retailer). Lock files live at `logs/<retailer>/locks/*_image_extraction.lock`. A 6-minute watchdog prevents post-processing from hanging.

## Key Conventions

### Session Persistence (Critical)

Extractors **must** use the same persistent Playwright browser profile as the scraper. Without it, CDN image requests fail with `net::ERR_HTTP2_PROTOCOL_ERROR` and only Carousel (page-captured) images are saved. Each retailer has a `profile_env` attribute naming the env var that points to its profile directory:

| Retailer | Env var |
|---|---|
| Kroger | `KROGER_PROFILE_DIR` |
| Amazon | `AMZ_PROFILE_DIR` / `AMAZON_PROFILE_DIR` |
| Walmart | `WALMART_PROFILE_DIR` |
| Target | `TARGET_PROFILE_DIR` |
| TikTok Shop | `TIKTOKSHOP_PROFILE_DIR` |

### Adding a New Retailer

1. Create `retailers/<slug>/adapter.py` implementing the three `RetailerAdapter` hooks and calling `register(MyAdapter())`.
2. Add the retailer's allowed folders to `ALLOWED_FOLDERS` in `utils/path_taxonomy.py`.
3. Run `make docs` to regenerate the README taxonomy table.
4. Add a profile setup script in `scripts/` if needed.

### Folder Names from Code

Use `utils/path_taxonomy.py` functions — never hardcode folder strings:
- `allowed_subdirs(retailer)` — returns the allowed folder set
- `ensure_subdir(retailer, root, subdir)` — creates a folder only if valid, raises `ValueError` otherwise
- `folder_for_adtype(retailer, ad_type)` — maps JSON `ad.type` to folder name (handles exceptions like Kroger's `CuratedCarousel` → `Carousel`)

### Run Artifacts

Each scrape run produces a pair written to `<output_dir>/runs/`:
- `run_results_<timestamp>.json` — structured ad data
- `search_results_<timestamp>.html` — raw captured HTML

`collect_pairs_for_run` matches these by `run_start_ts` file mtime (with a 2-second grace).

### Success Criteria

A run is only "successful" if at least one TOA or Skyscraper image is captured. Carousel-only results trigger a retry/warning.

### Stale Lock Cleanup

```bash
find logs/<retailer>/locks -name "*_image_extraction.lock" -print -delete
```

### App Launcher

The `.app` bundle runs **live source code** from `SCRAPER_HOME` (no rebuild needed for code changes). Set `SCRAPER_HOME` and per-retailer profile env vars in `~/.zshrc`. Boot logs: `logs/app_launcher_boot.log`; GUI logs: `logs/gui_boot.log`.

---

## Dashboard & Web Layer

### Services

Three processes serve the dashboard:

| Process | Start | Port | Purpose |
|---|---|---|---|
| Flask API | `python3 web/builder_server_v2.py` | 5006 | Ad data API + image serving |
| ngrok tunnel | `ngrok http 5006` | — | Exposes Flask to Builder.io |
| Vite dev server | `cd neon-sanctuary && pnpm dev` | 3000 | React dashboard UI |

**Start/stop all three at once:**
```bash
./restart_servers.sh   # kills existing, starts fresh, prints ngrok URL + PIDs
./check_servers.sh     # shows running status and current ngrok URL
./stop_servers.sh      # clean shutdown
```

⚠️ The ngrok URL changes on every restart. Update `VITE_API_BASE` in `neon-sanctuary/.env` and the Builder.io data source if you restart ngrok.

### neon-sanctuary (React Dashboard)

Located in `neon-sanctuary/`. Stack: React 18 + React Router 6 SPA + TypeScript + Vite + TailwindCSS 3 + Radix UI. Backend is a lightweight Express server (`neon-sanctuary/server/index.ts`) that proxies to the Flask API.

```bash
cd neon-sanctuary
pnpm dev          # dev server (port 3000)
pnpm build        # production build
pnpm typecheck    # TypeScript check
pnpm test         # Vitest
```

- Pages: `neon-sanctuary/client/pages/`
- Routes defined in `neon-sanctuary/client/App.tsx`
- Shared types between client and server: `neon-sanctuary/shared/api.ts`
- Add new Express endpoints in `neon-sanctuary/server/routes/`, register in `server/index.ts`, prefix with `/api/`
- Use the `cn()` utility (`clsx` + `tailwind-merge`) for conditional Tailwind classes
- `VITE_API_BASE` in `neon-sanctuary/.env` sets the Flask API URL for the frontend

### Flask API Endpoints (port 5006)

```
GET /api/retailers                               → list retailer slugs
GET /api/clients?retailer=<r>                    → list clients
GET /api/runs?retailer=<r>&client=<c>            → list run files with metadata
GET /api/terms?retailer=<r>&client=<c>           → list search terms used
GET /api/advertisers?retailer=<r>&client=<c>     → list unique brands
GET /api/ads/cards?retailer=<r>&client=<c>       → paginated ad cards (page, page_size, term, advertiser, start, end)
GET /api/image/<retailer>/<client>/<filename>    → serve ad image (searches all taxonomy folders)
GET /api/logo/<retailer>                         → serve retailer logo
GET /health                                      → health check
```

Co-branded ads: `brand` field uses `+` separator (e.g. `"Herdez + Jennie-O"`); `advertisers` array contains each brand individually for filtering.

All Builder.io fetch calls must include `'ngrok-skip-browser-warning': 'true'` header.

### Builder.io Connection

Builder.io connects to the Flask API via the ngrok tunnel as a REST data source. The public API key is stored in `neon-sanctuary/.env` as `VITE_PUBLIC_BUILDER_KEY`. CORS for Builder.io:

```bash
export ALLOWED_ORIGINS="https://builder.io,https://cdn.builder.io,<your-ngrok-url>"
./restart_servers.sh
```

---

## Run Manifest & Database

### Run Manifest (`cache/run_manifest.json`)

A flat JSON index of all scrape runs — enables fast counting and pagination without opening individual JSON files. Structure:

```json
{
  "built_at": "...",
  "runs": [{"retailer","client","keyword","run_id","timestamp","day","ad_count","json_path",...}],
  "daily_totals": {"kroger": {"blue_bunny": {"2025-11-07": 24}}},
  "brands": {},
  "brands_by_client": {}
}
```

**Rebuild after scraping new data or on server restart:**
```bash
python3 tools/build_run_manifest.py           # incremental (default, fast ~30s)
python3 tools/build_run_manifest.py --full    # full rebuild from scratch (slow, ~10min with 50k+ files)
```

`web/manifest_store.py` loads the manifest lazily with mtime-based cache invalidation — no restart needed after rebuilding.

### Supabase (Local PostgreSQL, port 54322)

The database is the preferred data source when available; `web/db_store.py` falls back to `manifest_store.py` automatically if the DB is unreachable.

Connection string: `postgresql://postgres:postgres@127.0.0.1:54322/postgres` (also read from `DATABASE_URL` env var).

**Schema** (defined in `supabase/migrations/20260212200000_initial_schema.sql`):
- `brands` — canonical brand names + `name_lower` generated column
- `brand_synonyms` — alternate spellings keyed to `brand_id`
- `brand_logos` — logo file metadata; actual files stay on disk
- `runs` — one row per scrape run; `day` auto-populated by trigger from `timestamp`
- `ad_brands`, `ads` — ad-level records

**Populate / re-populate from JSON files on disk:**
```bash
python3 tools/populate_database.py --all       # brands + logos + schedules + runs
python3 tools/populate_database.py --runs      # runs only (faster, post-scrape)
python3 tools/populate_database.py --brands    # brands + synonyms only
```

**Add new migrations** in `supabase/migrations/` following the `YYYYMMDDHHMMSS_description.sql` naming convention.

---

## Common Issues

> Always activate the venv first: `source .venv/bin/activate`

**Headless fails, headed works** — CDN fingerprint blocks headless. Use headed-but-minimized: `args=["--start-minimized","--window-position=0,0","--window-size=10,10"]`.

**`'Locator' object is not callable`** — `.first`, `.last`, `.nth` are *properties* in Playwright's sync API, not methods. Use `locator.first` (no parens), call `.count()` on the parent before narrowing.

**Images time out / 403** — Extractor running without session cookies. Always seed via `page.goto(srp_url, wait_until="commit")` before fetching images. Use `wait_until="commit"` (not `"domcontentloaded"`) for direct image URLs. Never hardcode fallback URLs — use `retailer_homepage(retailer)` helper.

**`url`/`srp_url`/`retailer` missing from JSON** — Scraper didn't persist them. Add all three fields to the `run_results` dict in the scraper script; extractors need them for Referer headers and cookie seeding.

**Subprocess can't find Playwright browsers** — Pass `PLAYWRIGHT_BROWSERS_PATH` explicitly in adapter: `env = os.environ.copy()` then `subprocess.Popen(cmd, env=env)`.

**Profile locked (`SingletonLock`)** — Multiple processes sharing same profile. Kill extras (`ps aux | grep screenshot_`), then `rm ~/Library/Application\ Support/RMN/profiles/<retailer>/SingletonLock`.

**Profile not passed from Finder-launched app** — Finder doesn't inherit shell env. In adapter's `search_and_capture()`, inject: `os.environ["RETAILER_PROFILE_DIR"] = ctx.profile_dir`.

**Wrong subfolders created** — Never pre-create folders manually. Use `output_dir_for(base, retailer, client)` from `core/paths.py`; it reads the taxonomy. Clean up with `python scripts/maintenance/cleanup_taxonomy.py`.

**Two log files for one scrape** — Extractor returned 0 with exit code 0, triggering retry. Fix: `return 1` from `main()` when `saved_count == 0`.

**Image extraction reports zero counts** — Use a 5-minute slack window (`horizon = pair_start - 300`) when globbing for recent PNGs, not the default 2-second grace period.

**Process hangs** — Always set `timeout=` on `page.wait_for_selector()`. Check for stale locks: `find logs/<retailer>/locks/ -name "*.lock" -mmin +30 -delete`.
