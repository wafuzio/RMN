# Repository Reorganization Summary

## Overview
This document summarizes the multi-retailer repository reorganization initiated on 2025-09-30, with path fixes completed on 2025-10-01.

## Changes Made

### 1. Directory Structure
Created new organized directory structure:
- **`core/`** - Core functionality (retailers.py, run_context.py, paths.py)
- **`retailers/`** - Retailer-specific adapters
  - `retailers/kroger/` - Kroger adapter
  - `retailers/amazon/` - Amazon adapter
- **`auth/`** - Authentication modules (retailer_auth.py, gui_helper.py)
- **`extractors/`** - Image extraction scripts
  - `screenshot_ad_images.py` (preferred)
  - `screenshot_toa_image.py` (legacy)
- **`web/`** - Web interface
  - `builder_server.py` - Main server
  - `templates/` - Jinja2 templates
  - `static/` - CSS/JS assets
  - `libs/` - Vendored Flask/dependencies
- **`assets/`** - Static assets
  - `icons/` - Application icons
- **`archived/`** - Legacy code (kept for backward compatibility)
  - `kroger_ad_core.py` (HTML parsing and ad extraction)
  - Old scripts and documentation
- **Root directory** - Active scripts
  - `kroger_search_and_capture.py` (main Kroger scraper)
  - `process_saved_html.py` (processes HTML, creates JSON)

### 2. Updated Imports and Paths
- Updated all references to moved files
- Fixed imports in `retailers/kroger/adapter.py` to import kroger_search_and_capture from root directory
- Updated `scheduler_daemon.py` to reference archived scripts
- Updated `keyword_input.py` to use new extractor paths
- Updated `process_saved_html.py` to import from `archived.kroger_ad_core`
- Added project root to sys.path in extractor scripts for `browser_lock` import

### 3. Launcher Improvements
Created robust launcher system with:
- **`launcher.py`** - Python launcher with SCRAPER_HOME support
- **`start_app.sh`** - Shell wrapper with PYTHON_EXEC support
- Environment variable resolution:
  - `SCRAPER_HOME` - Project root directory
  - `PYTHON_EXEC` - Python interpreter to use (supports venv)
  - `KROGER_PROFILE_DIR` - Kroger browser profile
  - `AMZ_PROFILE_DIR` - Amazon browser profile

### 4. Build System
Updated `setup.py` for py2app with:
- Anchored resource paths to prevent permission errors
- Minimal alias build for development
- Proper package inclusion (core, retailers, auth)
- Launcher-based entry point

### 5. .gitignore Updates
Added comprehensive ignore patterns:
- Python artifacts (`__pycache__/`, `*.pyc`, `*.pyo`, `*.pyd`)
- Build artifacts (`build/`, `dist/`, `*.spec`, `*.app/`)
- Runtime files (`logs/`, `output/`, `profiles/`)
- Specific log files (`file_list.log`, `debug.log`, etc.)

### 6. UI Improvements
Added theme persistence and menu system:
- Theme selection menu (View > Theme)
- Palette selection menu (View > Palette - Light/Dark)
- Preferences saved to `config/ui.json`
- Updated window title to "Retail Ad Monitor"
- Inline View menu fallback when native menubar disabled (prevents Tk/Cocoa crashes)

### 7. Post-Reorganization Fixes (2025-10-01)
- Fixed import paths after file moves:
  - `process_saved_html.py` now imports from `archived.kroger_ad_core`
  - `retailers/kroger/adapter.py` imports kroger_search_and_capture from root
  - Extractor scripts add project root to sys.path for `browser_lock` import
- Fixed duplicate output directories (output/client vs output/kroger/client):
  - Updated all path functions to use `output_dir_for()` for retailer-scoped paths
  - Fixed `compute_runs_root()` to handle both old and new path structures
  - Backward compatibility: old paths still read, new saves go to output/kroger/client
- macOS app launcher improvements:
  - In-process execution (single dock icon, no separate Python process)
  - Inline View menu to avoid Tk/Cocoa menubar crashes (RAM_NO_NATIVE_MENUBAR guard)
  - Added boot logging: logs/app_launcher_boot.log, logs/gui_boot.log
  - Launcher reads config/launcher.env for environment variables

## Environment Setup

Add these to your shell profile (`~/.zshrc` or `~/.bash_profile`):

```bash
export SCRAPER_HOME="/Users/dan.maguire/Documents/Amazon_Scrape"
export KROGER_PROFILE_DIR="/Users/dan.maguire/ChromeProfiles/kroger_clean_profile"
export AMZ_PROFILE_DIR="/Users/dan.maguire/Documents/Amazon_Scrape/profiles/amazon"

# Optional: Use a specific Python interpreter (e.g., venv)
# export PYTHON_EXEC="/Users/dan.maguire/venvs/ram/bin/python"
```

## Building the App

### Development (Alias) Build
Runs live source code, updates automatically:
```bash
rm -rf dist build
python3 setup.py py2app -A
open "dist/Retail Ad Monitor.app"
```

### Production (Frozen) Build
Creates standalone app:
```bash
rm -rf dist build
python3 setup.py py2app
open "dist/Retail Ad Monitor.app"
```

## Running the Application

### From Source
```bash
cd ~/Documents/Amazon_Scrape
python3 keyword_input.py
```

### From App Bundle
```bash
open "dist/Retail Ad Monitor.app"
```

### Using Shell Wrapper
```bash
./start_app.sh
```

## Verification Checklist

- [x] Core modules import correctly
- [x] Retailer adapters load properly
- [x] Extractors accessible from new paths
- [x] Web server runs from web/ directory
- [x] Archived scripts accessible for backward compatibility
- [x] Launcher resolves SCRAPER_HOME correctly
- [x] App bundle builds without errors
- [x] Theme persistence works
- [x] Menu system functional
- [x] Import paths fixed (archived/, extractors/, retailers/)
- [x] Output directories consolidated (output/kroger/client)
- [x] Browser lock imports working in extractors
- [x] In-process launcher working (single dock icon)
- [x] JSON files being created correctly

## Next Steps

1. **Test GUI** - Run Kroger scrape with 1 keyword
2. **Test Amazon** - Run Amazon scrape with 1 keyword
3. **Test Scheduler** - Verify scheduler daemon works
4. **Run Tests** - Execute test suite if available
5. **Commit Changes** - Commit with descriptive message
6. **Documentation** - Update README with new structure

## Files to Commit

```bash
git add -A
git commit -m "chore: repo reorg for multi-retailer; move extractors/, web/, archive legacy; add .gitignore; update paths"
git push
```

## Notes

- The `archived/` directory contains legacy code (kroger_ad_core.py) that is still actively used
- The `kroger_search_and_capture.py` script (in root directory) is used by the Kroger adapter
- Web libraries are vendored in `web/libs/` for offline operation
- All paths now use the centralized `output_dir_for()` and `logs_dir_for()` functions from `core/paths.py`
- The app uses py2app (not PyInstaller) for macOS bundling
- Alias mode (`-A` flag) allows live code updates without rebuilding
