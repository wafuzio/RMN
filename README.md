Multi‑Retailer TOA Scraper
A macOS + Python automation platform for tracking and analyzing Targeted Onsite Ads (TOAs) across retailers (starting with Kroger). Includes a native GUI, optional web dashboard, conflict‑aware scheduler, and pluggable “retailer adapters” so you can add Walmart/Target/etc. without touching the UI.

Note: Kroger remains the default path. If you don’t choose another retailer, behavior is identical to the original Kroger tool.

TL;DR for future debugging
TOA/Skyscraper images come from retailer CDNs and require a valid logged‑in session (cookies).
The image extractor must reuse the same browser profile as the scraper. If not, expect timeouts/HTTP2 resets and “only Carousel.”
Kroger: export KROGER_PROFILE_DIR="/Users/<you>/ChromeProfiles/kroger_clean_profile"
Logs live in logs/<retailer>/..., and per‑run extractor logs are in logs/<retailer>/image_extract_*.log.
A 6‑minute watchdog prevents “Processing saved HTML files…” from hanging forever.
Jump to Session Persistence (CRITICAL) and Troubleshooting for precise fixes.

What's new
Retailer adapters: a tiny interface that wraps search, pair collection, and image extraction per retailer.
core/retailers.py: registry + base class.
retailers/kroger/adapter.py: Kroger implementation (uses your existing scripts).
retailers/amazon/adapter.py: Amazon implementation (captures Sponsored Brands, Products, and Display ads).
Retailer‑scoped paths and logs:
output///...

Supported Retailers
- **Kroger:** Captures TOA, Skyscraper, and Carousel ads
- **Instacart:** Captures Shoppable Display Ads, Shoppable Video Ads, and Display Ads
- **Amazon:** Captures Sponsored Brands (TOA), Sponsored Display (Skyscraper), and Sponsored Products (Carousel)

## Retailer Taxonomy (Auto-Generated)

> **Do not edit inside this block.** Run `python scripts/docs/update_docs.py` to regenerate from code.

<!-- TAXONOMY_START -->
| Retailer | Allowed subfolders |
|----------|-------------------|
| **Amazon** | `Carousel`, `Main`, `Skyscraper`, `TOA`, `runs` |
| **Instacart** | `Display_Ads`, `Main`, `Shoppable_Display_Ads`, `Shoppable_Video_Ads`, `runs` |
| **Kroger** | `Carousel`, `Display_Ads`, `Main`, `Skyscraper`, `TOA`, `runs` |
<!-- TAXONOMY_END -->

logs/<retailer>/...
Schedule files include a retailer field for conflict detection and back‑compat.
Overview
Native macOS app (py2app)
Tkinter GUI with high‑contrast ttk styles
Optional Flask web dashboard (Bootstrap)
Automated scheduling with conflict detection
Background daemon
Advanced ad extraction (TOA, Skyscraper, Carousel)
Multi‑tenant client data separation
Pluggable multi‑retailer architecture (adapters)
Architecture
Core runtime

GUI controller: keyword_input.py
Retailer registry: core/retailers.py
Run context (paths/profile per run): core/run_context.py
Retailer‑aware paths: core/paths.py
Retailer adapters

retailers/kroger/adapter.py (default, wraps your existing Kroger pipeline)
Add new ones via retailers//adapter.py
Web interface (optional)

builder_server.py (vendored Flask in libs/)
Bootstrap templates and static assets
Automation

scheduler_daemon.py
Conflict‑aware scheduler (5‑minute windows)
Per‑retailer logs and locks
Directory Structure
├── core/
│   ├── retailers.py          # base adapter + registry
│   ├── run_context.py        # RunContext dataclass
│   └── paths.py              # retailer-aware path helpers
├── auth/
│   ├── retailer_auth.py      # Authentication helper for retailers
│   ├── gui_helper.py         # GUI integration for auth
│   └── profiles.json         # Profile configuration
├── retailers/
│   ├── kroger/
│   │   └── adapter.py        # Kroger adapter (uses existing scripts)
│   └── amazon/
│       └── adapter.py        # Amazon adapter (captures Sponsored ads)
├── dist/
│   └── Retail Ad Monitor.app/
├── libs/                     # Vendored Flask deps
├── static/                   # CSS/JS for web UI
├── templates/                # Flask templates
├── output/
│   └── <retailer>/
│       └── <client>/
│           ├── runs/                 # run_results_*.json + search_results_*.html
│           ├── TOA/ Skyscraper/ Carousel/
│           ├── schedule_config.json  # includes retailer + client
│           └── scheduler.log
├── logs/
│   └── <retailer>/
│       ├── keyword_input.log
│       ├── image_extract_*.log
│       └── locks/*_image_extraction.lock
└── (existing extractor/scraper scripts)
Back‑compat: old Kroger‑only schedules under output//schedule_config.json are still read; new saves go to output/kroger//.

Key Components
GUI: keyword_input.py (Tkinter ttk)
Retailer registry: core/retailers.py
Run context: core/run_context.py
Paths: core/paths.py
Authentication: auth/retailer_auth.py, auth/gui_helper.py
Kroger adapter: retailers/kroger/adapter.py
Amazon adapter: retailers/amazon/adapter.py
Scraper: kroger_search_and_capture.py (root directory, Playwright, persistent profile)
Image Extractors: extractors/screenshot_ad_images.py (preferred), extractors/screenshot_toa_image.py (legacy)
Scheduler: scheduler_daemon.py
Web API/UI: web/builder_server.py, web/templates, web/static
Requirements
macOS 10.14+
Python 3.8+ (Tkinter included on macOS)
Playwright installed with browsers
4 GB RAM+ recommended
~2 GB disk for outputs/caches
Python deps:

playwright, beautifulsoup4, pillow, flask, numpy
Flask is vendored under libs for deploys
Installation
Quick Start (macOS)

CLI Python:
pip install playwright
playwright install
If you use the app‑bundle Python:
APP_PY="/Users/<you>/Documents/Amazon_Scrape/dist/Retail Ad Monitor.app/Contents/MacOS/python"
"$APP_PY" -m pip install playwright
"$APP_PY" -m playwright install chromium

### Environment Variables (Optional)

For best results, set these in your shell profile (`~/.zshrc` or `~/.bash_profile`):

```bash
export SCRAPER_HOME="/Users/<you>/Documents/Amazon_Scrape"
export KROGER_PROFILE_DIR="/Users/<you>/ChromeProfiles/kroger_clean_profile"
export AMZ_PROFILE_DIR="/Users/<you>/Documents/Amazon_Scrape/profiles/amazon"

# Optional: Use a specific Python interpreter (e.g., venv)
# export PYTHON_EXEC="/Users/<you>/Documents/Amazon_Scrape/.venv/bin/python"
```

The launcher will use these to find your source code and browser profiles.

### macOS App Launcher

The app uses an in-process launcher that:
- Runs live source code from `SCRAPER_HOME` (no rebuild needed for code changes)
- Uses inline View menu to avoid Tk/Cocoa menubar crashes on macOS
- Supports custom Python interpreter via `PYTHON_EXEC` environment variable
- Reads configuration from `config/launcher.env` if present

Boot logs: `~/Documents/Amazon_Scrape/logs/app_launcher_boot.log`
GUI logs: `~/Documents/Amazon_Scrape/logs/gui_boot.log`

Launch
Double‑click the .app, or:
python keyword_input.py
Development Setup

git clone https://github.com/wafuzio/RMN.git
cd Amazon_Scrape
pip install -r requirements.txt
playwright install
Bundle (optional)

```bash
# Build alias app (runs live source code, updates automatically)
python3 setup.py py2app -A

# Build standalone app (frozen, doesn't update with code changes)
python3 setup.py py2app
```
Usage (GUI)
Select Retailer (defaults to Kroger)
Choose Client or click New…
Paste keywords (one per line)
Start Scraping
Save Schedule (optional)
Outputs are written to output///...

Session Persistence (CRITICAL)
Most retailer CDN images require a valid session. If the extractor runs with a fresh browser context:

Page.goto timeouts / net::ERR_HTTP2_PROTOCOL_ERROR
Only Carousel images (page capture), no TOA/Sky
GUI appears stuck on “Processing saved HTML files…”
Fix: run the extractor with the SAME persistent profile as the scraper.

Per‑retailer profiles

Kroger: export KROGER_PROFILE_DIR="/Users/<you>/ChromeProfiles/kroger_clean_profile"
Amazon: export AMZ_PROFILE_DIR="/Users/<you>/Documents/Amazon_Scrape/profiles/amazon"
For additional retailers, each adapter declares its profile env var (e.g., WMT_PROFILE_DIR for Walmart).

Setting up retailer profiles:

```bash
# For Amazon
./scripts/setup_amazon_profile.sh
# Or manually:
# python3 auth/retailer_auth.py --retailer amazon --profile-dir ~/Documents/Amazon_Scrape/profiles/amazon
```
The GUI passes --profile-dir automatically if the env var exists or a default profile path is found. Extractor logic uses:

python
p.chromium.launch_persistent_context(
  user_data_dir=args.profile_dir, channel="chrome", headless=...
)
Manual verification Run the last command printed in the GUI log and add --profile-dir:

APP_PY="/Users/<you>/Documents/Amazon_Scrape/dist/Retail Ad Monitor.app/Contents/MacOS/python"
JSON="/Users/<you>/Documents/Amazon_Scrape/output/<retailer>/<client>/runs/run_results_...json"
HTML="/Users/<you>/Documents/Amazon_Scrape/output/<retailer>/<client>/runs/search_results_...html"
PROFILE="/Users/<you>/ChromeProfiles/kroger_clean_profile"

"$APP_PY" ./extractors/screenshot_toa_image.py \
  --json "$JSON" --html "$HTML" \
  --output "/Users/<you>/Documents/Amazon_Scrape/output/<retailer>/<client>" \
  --headless --time-window 45 --browser-lock-timeout 600 \
  --profile-dir "$PROFILE"
Logs & Live Visibility
GUI log:
~/Documents/Amazon_Scrape/logs/<retailer>/keyword_input.log
tail -f ~/Documents/Amazon_Scrape/logs/<retailer>/keyword_input.log
Extractor logs:
~/Documents/Amazon_Scrape/logs/<retailer>/image_extract_YYYYMMDD_HHMMSS.log
EX=$(ls -t ~/Documents/Amazon_Scrape/logs/<retailer>/image_extract_*.log | head -n1); tail -f "$EX"
Locks:
~/Documents/Amazon_Scrape/logs/<retailer>/locks/*_image_extraction.lock
find ~/Documents/Amazon_Scrape/logs/<retailer>/locks -name "*_image_extraction.lock" -print -delete
Success rule:
“Success” requires at least one TOA or Skyscraper (Carousel alone triggers retry/warn).
Watchdog:
6‑minute post‑processing cap to avoid indefinite “Processing saved HTML files…”
Scheduling & Daemon
Start daemon:

./start_scheduler.sh
Check status:

ps aux | grep scheduler_daemon
tail -f output/<retailer>/<client>/scheduler.log
Conflict handling:

Schedules are retailer‑aware and conflict‑aware (5‑minute windows). The GUI filters/disables unavailable minute values and disables Save if conflicts exist.
Troubleshooting
“Processing saved HTML files…” hangs

Stale lock: delete *_image_extraction.lock (see above).
Cookie‑less extractor: missing --profile-dir (see Session Persistence).
CDN timeouts: without cookies the JPGs won’t stream.
Check quickly:

tail -f ~/Documents/Amazon_Scrape/logs/<retailer>/keyword_input.log
EX=$(ls -t ~/Documents/Amazon_Scrape/logs/<retailer>/image_extract_*.log | head -n1); tail -f "$EX"
Only Carousel images

Carousel is page‑side; TOA/Sky require CDN JPGs. Pass the profile and retry.
“Page.goto: net::ERR_HTTP2_PROTOCOL_ERROR”

CDN refusing streams; use persistent context with cookies.
App‑bundle Python doesn’t have browsers

APP_PY="/Users/<you>/Documents/Amazon_Scrape/dist/Retail Ad Monitor.app/Contents/MacOS/python"
"$APP_PY" -m pip install playwright
"$APP_PY" -m playwright install chromium
Finder doesn’t pass env

Apps launched from Finder don’t inherit your shell. The GUI tries a default profile; safer during debugging:
export KROGER_PROFILE_DIR=... then run python keyword_input.py, or add a launcher wrapper that sets env.
Verify cookies

Print cookie count in the extractor (optional): Cookies for : N (should be >0)
Extending to a new retailer (adapter)
Add a file retailers//adapter.py implementing three hooks and register it.

Example skeleton:

python
# retailers/walmart/adapter.py
from core.retailers import RetailerAdapter, register

class WalmartAdapter(RetailerAdapter):
    slug = "walmart"
    display_name = "Walmart"
    profile_env = "WMT_PROFILE_DIR"

    def search_and_capture(self, keyword, ctx) -> bool:
        # implement Playwright flow (or wrap an existing script)
        ...

    def collect_pairs_for_run(self, ctx, run_start_ts: float):
        # return list[(json_path, html_path)]
        ...

    def extract_images(self, json_path, html_path, ctx) -> dict:
        # run screenshot scripts, pass --profile-dir, return counts
        ...

register(WalmartAdapter())
The GUI picks up the new retailer automatically via the registry. You can allow multi‑select and iterate adapters per run.

Backward Compatibility & Migration
Old schedules (output/<client>/schedule_config.json) are still read and treated as retailer="kroger".
New saves write output/<retailer>/<client>/schedule_config.json with "retailer" included.
Extractor and scraper scripts remain unchanged; the Kroger adapter wraps them.
Web Interface & API (optional)
Start:

python web/builder_server.py
# http://localhost:5006
Endpoints:

GET / – scheduler UI
GET /api/ads
GET /api/ads/
GET /api/nfl-grid/
GET /api/images//
GET /api/toa//
CORS enabled for Builder.io.

Known Issues
In some runs TOA/Sky can over‑collect. Recommended mitigations:
Deduplicate by creative ID/viewport region
Reduce concurrency; debounce per keyword
Planned: stricter creative hashing
License
Proprietary – Internal use only

Appendix: Handy Commands
Tail GUI log

tail -f ~/Documents/Amazon_Scrape/logs/<retailer>/keyword_input.log
Tail latest extractor log

EX=$(ls -t ~/Documents/Amazon_Scrape/logs/<retailer>/image_extract_*.log | head -n1); tail -f "$EX"
Clear stale image locks

find ~/Documents/Amazon_Scrape/logs/<retailer>/locks -name "*_image_extraction.lock" -print -delete
Run extractor manually with profile

APP_PY="/Users/<you>/Documents/Amazon_Scrape/dist/Retail Ad Monitor.app/Contents/MacOS/python"
"$APP_PY" ./extractors/screenshot_toa_image.py --json <JSON> --html <HTML> --output <OUT> \
  --headless --time-window 45 --browser-lock-timeout 600 \
  --profile-dir "/Users/<you>/ChromeProfiles/kroger_clean_profile"
