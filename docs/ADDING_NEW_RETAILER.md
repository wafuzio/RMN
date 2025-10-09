# Adding a New Retailer to the Retail Ad Monitor

This guide walks through all the steps required to add a new retailer to the multi-retailer scraper application.

## Overview

Adding a new retailer involves:
1. Authentication setup
2. Creating the adapter structure
3. Implementing search and capture logic
4. Registering with the GUI
5. Configuring environment variables
6. Testing and documentation

---

## Step 1: Research & Requirements

### 1.1 Analyze the Retailer's Website
- [ ] Identify the search URL pattern
- [ ] Document ad types and their HTML selectors
- [ ] Determine if authentication is required
- [ ] Check if location/store selection is needed
- [ ] Test search behavior (wait strategies, dynamic content)

### 1.2 Create Documentation
Create a file: `docs/{retailer}_ad_html.md`

Document:
- Ad type names (as they appear on the site)
- CSS selectors for each ad type
- HTML examples of each ad type
- Any special requirements (store selection, etc.)

**Example**: See `docs/Instacart_ad_html.md`

---

## Step 2: Authentication Setup

### 2.1 Add Retailer to Auth Module
Edit `auth/retailer_auth.py`:

```python
RETAILERS = {
    'kroger': {...},
    'amazon': {...},
    'newretailer': {  # Add new retailer
        'name': 'NewRetailer',
        'login_url': 'https://www.newretailer.com/login',
        'success_indicators': ['text=/Account/i', 'button:has-text("Sign Out")'],
        'profile_env': 'NEWRETAILER_PROFILE_DIR'
    }
}
```

### 2.2 Create Setup Script
Create `scripts/setup_{retailer}_profile.sh`:

```bash
#!/bin/bash
PROFILE_DIR=~/Documents/Amazon_Scrape/profiles/newretailer
mkdir -p "$PROFILE_DIR"
python3 auth/retailer_auth.py --retailer newretailer --profile-dir "$PROFILE_DIR"

# Add to shell profile instructions
echo ""
echo "Add to ~/.zshrc or ~/.bash_profile:"
echo "export NEWRETAILER_PROFILE_DIR=$PROFILE_DIR"
```

Make it executable:
```bash
chmod +x scripts/setup_{retailer}_profile.sh
```

### 2.3 Test Authentication
```bash
./scripts/setup_{retailer}_profile.sh
```

Verify the profile was created and login persists.

---

## Step 3: Create Adapter Structure

### 3.1 Create Retailer Directory
```bash
mkdir -p retailers/{retailer}
```

### 3.2 Create `__init__.py`
File: `retailers/{retailer}/__init__.py`

```python
from .adapter import NewRetailerAdapter

__all__ = ['NewRetailerAdapter']
```

### 3.3 Create Search Script
File: `{retailer}_search_and_capture.py` (in project root)

```python
#!/usr/bin/env python3
"""
NewRetailer search and capture script.
Performs keyword search and saves HTML + JSON results.
"""

import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


def search_and_capture(keyword: str, output_dir: str, **kwargs) -> bool:
    """
    Search NewRetailer for a keyword and capture results.
    
    Args:
        keyword: Search term
        output_dir: Base output directory (e.g., output/newretailer/client_name)
        **kwargs: Additional retailer-specific parameters
    
    Returns:
        True if successful, False otherwise
    """
    
    # Get profile directory
    profile_dir = os.environ.get('NEWRETAILER_PROFILE_DIR')
    if not profile_dir or not os.path.isdir(profile_dir):
        print(f"❌ NEWRETAILER_PROFILE_DIR not set or invalid: {profile_dir}")
        print("Run: ./scripts/setup_newretailer_profile.sh")
        return False
    
    # Create runs directory
    runs_dir = os.path.join(output_dir, "runs")
    os.makedirs(runs_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    html_file = os.path.join(runs_dir, f"search_results_{timestamp}.html")
    json_file = os.path.join(runs_dir, f"run_results_{timestamp}.json")
    
    print(f"🔍 Searching NewRetailer for: '{keyword}'")
    print(f"   Profile: {profile_dir}")
    
    try:
        with sync_playwright() as p:
            # Launch with persistent context (authenticated session)
            context = p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=False,
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
            )
            
            page = context.pages[0] if context.pages else context.new_page()
            
            # Navigate to search page
            search_url = f'https://www.newretailer.com/search?q={keyword}'
            print(f"   URL: {search_url}")
            
            # Choose appropriate wait strategy
            page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
            
            # Wait for content to load (adjust as needed)
            time.sleep(5)
            
            # Check authentication
            # TODO: Add retailer-specific login check
            
            print("✅ Authenticated session active")
            
            # Get page content
            html_content = page.content()
            
            # Save HTML
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"💾 HTML saved: {html_file}")
            
            # Extract ad data for JSON
            ad_data = {
                "keyword": keyword,
                "timestamp": timestamp,
                "url": search_url,
                "ads": []
            }
            
            # Find all ad containers
            ad_selectors = {
                'Ad Type 1': 'div.ad-selector-1',
                'Ad Type 2': 'div.ad-selector-2',
            }
            
            for ad_type, selector in ad_selectors.items():
                elements = page.query_selector_all(selector)
                for i, elem in enumerate(elements):
                    try:
                        ad_id = elem.get_attribute('id') or f"{ad_type}_{i}"
                        bbox = elem.bounding_box()
                        
                        ad_info = {
                            "type": ad_type,
                            "selector": selector,
                            "id": ad_id,
                            "index": i,
                        }
                        
                        if bbox:
                            ad_info["bbox"] = {
                                "x": bbox['x'],
                                "y": bbox['y'],
                                "width": bbox['width'],
                                "height": bbox['height']
                            }
                        
                        # Extract title/brand if available
                        try:
                            title_elem = elem.query_selector('h2, [role="heading"]')
                            if title_elem:
                                ad_info["title"] = title_elem.inner_text()
                        except:
                            pass
                        
                        ad_data["ads"].append(ad_info)
                    except Exception as e:
                        print(f"⚠️  Could not extract data from {ad_type} #{i}: {e}")
            
            print(f"📊 Found {len(ad_data['ads'])} ad units")
            
            # Save JSON
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(ad_data, f, indent=2)
            print(f"💾 JSON saved: {json_file}")
            
            context.close()
            
            return True
            
    except PlaywrightTimeout as e:
        print(f"❌ Timeout: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Search NewRetailer and capture results')
    parser.add_argument('keyword', help='Search keyword')
    parser.add_argument('--output-dir', required=True, help='Output directory')
    
    args = parser.parse_args()
    
    success = search_and_capture(args.keyword, args.output_dir)
    sys.exit(0 if success else 1)
```

### 3.4 Create Adapter
File: `retailers/{retailer}/adapter.py`

```python
# retailers/newretailer/adapter.py
from __future__ import annotations
import os, glob, time, subprocess
from datetime import datetime
from core.retailers import RetailerAdapter, register


class NewRetailerAdapter(RetailerAdapter):
    slug = "newretailer"
    display_name = "NewRetailer"
    profile_env = "NEWRETAILER_PROFILE_DIR"

    def search_and_capture(self, keyword: str, ctx) -> bool:
        """Execute NewRetailer search and capture HTML/JSON."""
        import sys
        # Add project root to path
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        sys.path.insert(0, project_root)
        
        # Import the search_and_capture function from root directory
        from newretailer_search_and_capture import search_and_capture
        
        return search_and_capture(keyword, ctx.output_dir)

    def collect_pairs_for_run(self, ctx, run_start_ts: float):
        """Collect JSON/HTML pairs from the most recent run."""
        runs = os.path.join(ctx.output_dir, "runs")
        jsons = sorted([p for p in glob.glob(os.path.join(runs, "run_results_*.json"))
                        if os.path.getmtime(p) >= run_start_ts - 2],
                       key=os.path.getmtime)
        pairs = []
        for j in jsons:
            h = j.replace("run_results_", "search_results_").replace(".json", ".html")
            if os.path.exists(h):
                pairs.append((j, h))
        return pairs

    def extract_images(self, json_path: str, html_path: str, ctx) -> dict:
        """Extract ad images using screenshot script."""
        ad_script = os.path.join(ctx.script_dir, "extractors/screenshot_ad_images.py")
        toa_script = os.path.join(ctx.script_dir, "extractors/screenshot_toa_image.py")
        script = ad_script if os.path.exists(ad_script) else toa_script

        cmd = [
            os.sys.executable, script,
            "--json", json_path,
            "--html", html_path,
            "--output", ctx.output_dir,
            "--headless",
            "--no-lock",
            "--time-window", "45",
            "--browser-lock-timeout", "600",
        ]
        
        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        
        if ctx.profile_dir and os.path.isdir(ctx.profile_dir):
            cmd += ["--profile-dir", ctx.profile_dir]
            env[self.profile_env] = ctx.profile_dir

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_dir = ctx.logs_dir
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, f"image_extract_{ts}.log")
        pair_start = time.time()

        with open(log_path, "w", encoding="utf-8") as lf:
            lf.write(f"=== START {datetime.now().isoformat()} ===\n")
            lf.write(f"CMD: {' '.join(cmd)}\nCWD: {ctx.script_dir}\n\n")
            proc = subprocess.Popen(
                cmd, env=env, cwd=ctx.script_dir,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
            )
            for line in iter(proc.stdout.readline, ""):
                lf.write(line)
            try:
                proc.wait(timeout=240)
            except subprocess.TimeoutExpired:
                proc.kill()
                lf.write("\n❌ Timeout: 240s\n")
            lf.write(f"Exit code: {proc.returncode}\n")
            lf.write(f"=== END {datetime.now().isoformat()} ===\n")

        def count(leaf: str) -> int:
            return len([p for p in glob.glob(os.path.join(ctx.output_dir, leaf, "*.png"))
                        if os.path.getmtime(p) >= pair_start - 1])

        return {"toa": count("TOA"), "sky": count("Skyscraper"), "car": count("Carousel"), "log": log_path}


# Register on import
register(NewRetailerAdapter())
```

---

## Step 4: Add to Path Taxonomy

### 4.1 Update `utils/path_taxonomy.py`
**⚠️ CRITICAL STEP - This is the #1 cause of "Start Scraping doesn't work"!**

Add your retailer to the `TAXONOMY` dictionary:

```python
TAXONOMY = {
    "kroger": {...},
    "instacart": {...},
    "amazon": {...},
    "newretailer": {  # Add your retailer here
        "Ad_Type_1",      # Based on your ad selectors
        "Ad_Type_2",
        "Main",           # Always include
        "runs",           # Always include
    },
}
```

**Example for Walmart:**
```python
"walmart": {
    "Top_Banner",      # For a.ad, a.adctr
    "SBA",             # For [data-testid="sba-container"]
    "Tile_Takeover",   # For [data-testid="tile-take-over"]
    "SBV",             # For [data-testid="search-video-in-grid"]
    "Main",
    "runs",
},
```

**Why this matters:**
- Without this, you'll get: `ValueError: Unknown retailer: 'newretailer'`
- The error happens when clicking "Start Scraping"
- The adapter is registered but path creation fails
- This is checked in `core/paths.py` → `output_dir_for()`

### 4.2 Verify Taxonomy
```bash
python3 -c "from utils.path_taxonomy import allowed_subdirs; print(allowed_subdirs('newretailer'))"
```

Should print your folder set without errors.

---

## Step 5: Register with GUI

### 5.1 Import Adapter in GUI
Edit `keyword_input.py`:

```python
# ensure retailer adapters are registered
import retailers.kroger.adapter  # noqa: F401
import retailers.amazon.adapter  # noqa: F401
import retailers.instacart.adapter  # noqa: F401
import retailers.newretailer.adapter  # noqa: F401  # ADD THIS LINE
```

### 4.2 Verify Registration
```bash
python3 -c "
import retailers.kroger.adapter
import retailers.amazon.adapter
import retailers.instacart.adapter
import retailers.newretailer.adapter
from core.retailers import list_adapters
print('Registered adapters:')
[print(f'  - {a.display_name} ({a.slug})') for a in sorted(list_adapters(), key=lambda x: x.display_name)]
"
```

---

## Step 6: Configure Environment Variables

### 6.1 Update `config/launcher.env`
**⚠️ CRITICAL STEP - App won't work without this!**

Edit `config/launcher.env`:

```bash
SCRAPER_HOME=/Users/dan.maguire/Documents/Amazon_Scrape
PYTHON_EXEC=/Users/dan.maguire/Documents/Amazon_Scrape/.venv/bin/python
KROGER_PROFILE_DIR=/Users/dan.maguire/Documents/Amazon_Scrape/profiles/kroger
INSTACART_PROFILE_DIR=/Users/dan.maguire/Documents/Amazon_Scrape/profiles/instacart
INSTACART_STORE=publix
NEWRETAILER_PROFILE_DIR=/Users/dan.maguire/Documents/Amazon_Scrape/profiles/newretailer  # ADD THIS
```

### 5.2 Update Shell Profile (for CLI usage)
Add to `~/.zshrc` or `~/.bash_profile`:

```bash
export NEWRETAILER_PROFILE_DIR=~/Documents/Amazon_Scrape/profiles/newretailer
```

Then reload:
```bash
source ~/.zshrc
```

---

## Step 7: Testing

### 7.1 Create Test Script
File: `scripts/test_{retailer}_adapter.py`

```python
#!/usr/bin/env python3
"""Test the NewRetailer adapter end-to-end."""

import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from retailers.newretailer.adapter import NewRetailerAdapter
from core.run_context import RunContext

def test_newretailer_adapter():
    profile_dir = os.environ.get('NEWRETAILER_PROFILE_DIR')
    if not profile_dir or not os.path.isdir(profile_dir):
        print(f"❌ NEWRETAILER_PROFILE_DIR not set or invalid: {profile_dir}")
        return False
    
    print("=" * 60)
    print("NewRetailer Adapter Test")
    print("=" * 60)
    print(f"Profile: {profile_dir}")
    print()
    
    test_client = "adapter_test"
    base_dir = str(project_root)
    output_dir = str(project_root / "output" / "newretailer" / test_client)
    runs_dir = str(project_root / "output" / "newretailer" / test_client / "runs")
    logs_dir = str(project_root / "logs" / "newretailer")
    
    ctx = RunContext(
        retailer="newretailer",
        client=test_client,
        base_dir=base_dir,
        output_dir=output_dir,
        runs_dir=runs_dir,
        logs_dir=logs_dir,
        profile_dir=profile_dir,
        script_dir=base_dir
    )
    
    os.makedirs(ctx.output_dir, exist_ok=True)
    
    adapter = NewRetailerAdapter()
    
    print(f"Testing adapter: {adapter.display_name} ({adapter.slug})")
    print(f"Output directory: {ctx.output_dir}")
    print()
    
    keyword = "test product"
    print(f"Running search_and_capture for keyword: '{keyword}'")
    print("-" * 60)
    
    success = adapter.search_and_capture(keyword, ctx)
    
    print("-" * 60)
    if success:
        print("✅ search_and_capture completed successfully")
        
        runs_dir = Path(ctx.output_dir) / "runs"
        if runs_dir.exists():
            html_files = list(runs_dir.glob("search_results_*.html"))
            json_files = list(runs_dir.glob("run_results_*.json"))
            
            print(f"\nOutput files:")
            print(f"  HTML files: {len(html_files)}")
            print(f"  JSON files: {len(json_files)}")
            
            if json_files:
                import json
                with open(json_files[-1]) as f:
                    data = json.load(f)
                print(f"\n  Ads found: {len(data.get('ads', []))}")
        
        return True
    else:
        print("❌ search_and_capture failed")
        return False


if __name__ == "__main__":
    success = test_newretailer_adapter()
    sys.exit(0 if success else 1)
```

### 6.2 Run Tests

**Test 1: Adapter Registration**
```bash
python3 -c "from retailers.newretailer.adapter import NewRetailerAdapter; print('✅ Adapter loads')"
```

**Test 2: End-to-End**
```bash
NEWRETAILER_PROFILE_DIR=~/Documents/Amazon_Scrape/profiles/newretailer \
python3 scripts/test_newretailer_adapter.py
```

**Test 3: GUI**
```bash
python3 keyword_input.py
# Select "NewRetailer" from dropdown
# Enter a keyword
# Click "Run Scraper"
```

**Test 4: macOS App**
```bash
# Clear Python cache
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete 2>/dev/null

# Launch app
open "dist/Retail Ad Monitor.app"
# Select "NewRetailer" from dropdown
# Enter a keyword
# Click "Run Scraper"
```

---

## Step 8: Documentation

### 8.1 Create Retailer README
File: `retailers/{retailer}/README.md`

Include:
- Setup instructions
- Ad type mapping (TOA, Skyscraper, Carousel)
- Environment variables
- URL patterns
- Troubleshooting

**Example**: See `retailers/instacart/README.md`

### 7.2 Update CONTEXT_SEED.md
Edit `docs/CONTEXT_SEED.md`:

```markdown
## Current Adapters
- kroger (stable)
- amazon (WIP)
- instacart (new)
- newretailer (new)  # ADD THIS
  - Persistent profile via NEWRETAILER_PROFILE_DIR.
  - URL pattern: https://www.newretailer.com/search?q={keyword}
  - Ad types: [list ad types and selectors]
  - Verified: [number] ads detected with authenticated session.
```

### 7.3 Create Integration Summary
File: `docs/{RETAILER}_INTEGRATION.md`

Document:
- What was built
- Technical details
- Verification results
- Usage instructions

**Example**: See `docs/INSTACART_INTEGRATION.md`

---

## Step 9: Rebuild App (if needed)

If the app was built in full mode (not alias mode), rebuild it:

```bash
python3 setup.py py2app -A
```

Clear Python cache:
```bash
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete 2>/dev/null
```

---

## Checklist Summary

Use this checklist when adding a new retailer:

- [ ] Research website and document ad types
- [ ] Add retailer to `auth/retailer_auth.py`
- [ ] Create setup script `scripts/setup_{retailer}_profile.sh`
- [ ] Run setup script and verify authentication
- [ ] Create `retailers/{retailer}/` directory structure
- [ ] Create `{retailer}_search_and_capture.py` in project root
- [ ] Create `retailers/{retailer}/adapter.py`
- [ ] Create `retailers/{retailer}/__init__.py`
- [ ] **Add retailer to `utils/path_taxonomy.py` TAXONOMY** ⚠️ CRITICAL #1
- [ ] Import adapter in `keyword_input.py`
- [ ] **Add environment variables to `config/launcher.env`** ⚠️ CRITICAL #2
- [ ] Add environment variables to `~/.zshrc` (for CLI)
- [ ] Create test script `scripts/test_{retailer}_adapter.py`
- [ ] Test adapter registration
- [ ] Test end-to-end with test script
- [ ] Test in GUI (`python3 keyword_input.py`)
- [ ] Clear Python cache
- [ ] Test in macOS app
- [ ] Create `retailers/{retailer}/README.md`
- [ ] Update `docs/CONTEXT_SEED.md`
- [ ] Create `docs/{RETAILER}_INTEGRATION.md`
- [ ] Commit all changes to git

---

## Common Pitfalls

### ❌ #1 MOST COMMON: Forgot to add to path taxonomy
**Symptom**: `ValueError: Unknown retailer: 'newretailer'` when clicking "Start Scraping"
**Error location**: `utils/path_taxonomy.py`, line 39
**Fix**: Add retailer to `TAXONOMY` dictionary in `utils/path_taxonomy.py`
**Why it happens**: Adapter is registered but path creation fails

### ❌ Forgot to add environment variables to `config/launcher.env`
**Symptom**: App fails with "PROFILE_DIR not set or invalid"
**Fix**: Add `{RETAILER}_PROFILE_DIR` to `config/launcher.env`

### ❌ Forgot to import adapter in `keyword_input.py`
**Symptom**: Retailer doesn't appear in GUI dropdown
**Fix**: Add `import retailers.{retailer}.adapter` to `keyword_input.py`

### ❌ Python cache not cleared
**Symptom**: App runs old code even after changes
**Fix**: Run `find . -type d -name __pycache__ -exec rm -rf {} +`

### ❌ Profile directory doesn't exist
**Symptom**: "PROFILE_DIR not set or invalid"
**Fix**: Run `./scripts/setup_{retailer}_profile.sh`

### ❌ Wrong wait strategy
**Symptom**: Page loads but no ads found
**Fix**: Adjust wait strategy (`networkidle` vs `domcontentloaded` + sleep)

### ❌ Incorrect ad selectors
**Symptom**: No ads found in JSON
**Fix**: Inspect page HTML and update selectors in search script

---

## Example: Instacart Integration

For a complete working example, see the Instacart integration:

- `auth/retailer_auth.py` - Instacart auth config
- `scripts/setup_instacart_profile.sh` - Setup script
- `instacart_search_and_capture.py` - Search script
- `retailers/instacart/adapter.py` - Adapter
- `config/launcher.env` - Environment variables
- `docs/INSTACART_INTEGRATION.md` - Full documentation

---

## Questions?

If you encounter issues:
1. Check logs in `logs/{retailer}/`
2. Verify environment variables are set
3. Test each component individually
4. Review the Instacart integration as a reference

---

## Best Practices & Lessons Learned

### Profile Handoff: Ensure Both Phases Use Same Session

**Problem**: Search phase and image extraction phase may use different browser sessions, causing authentication failures or CDN rejections.

**Solution**: Inject `ctx.profile_dir` into environment variables in your adapter's `search_and_capture()` method:

```python
def search_and_capture(self, keyword: str, ctx) -> bool:
    # Import the scraper function
    from newretailer_search_and_capture import search_and_capture
    
    # CRITICAL: Inject profile dir into environment so scraper uses same session
    if ctx.profile_dir and os.path.isdir(ctx.profile_dir):
        os.environ["NEWRETAILER_PROFILE_DIR"] = ctx.profile_dir
        print(f"Injected NEWRETAILER_PROFILE_DIR into env: {ctx.profile_dir}")
    else:
        print("⚠️ ctx.profile_dir missing or invalid; scraper may run without cookies")
    
    # Call scraper
    return search_and_capture(keyword, ctx.output_dir)
```

**Why this matters**:
- When app is launched from Finder, shell environment variables aren't inherited
- Without this, search phase runs without cookies but extractor has them
- Results in login prompts, HTTP/2 resets, or incomplete ad assets

### Organic Search vs Direct Navigation

**Problem**: Direct URL navigation (`page.goto(search_url)`) can trigger bot detection or break session state.

**Solution**: Use organic search interaction when possible:

```python
# BAD: Direct navigation (can trigger bot detection)
search_url = f'https://www.retailer.com/search?q={keyword}'
page.goto(search_url)

# GOOD: Organic search (mimics human behavior)
# 1. Go to homepage first
page.goto('https://www.retailer.com/store/{store}')

# 2. Wait for page to be ready
page.wait_for_load_state("load")
page.wait_for_selector("[data-testid='search-bar-input']", timeout=5000)

# 3. Click search input
search_input = page.locator('input[placeholder*="Search"]').first
search_input.click()

# 4. Type keyword with human-like delays
search_input.fill(keyword)  # or .type(keyword, delay=100)

# 5. Press Enter
page.keyboard.press("Enter")

# 6. Wait for navigation
page.wait_for_url('**/s?k=**', timeout=10000)
```

**Key points**:
- Use `.fill()` for speed or `.type(keyword, delay=100)` for human-like typing
- Wait for actual UI elements, not just `domcontentloaded`
- Handle cookie banners and search toggles if present
- Always have a fallback to direct navigation if organic search fails

### Cookie Seeding for Image Extraction

**Problem**: Image extractor needs cookies to download ad assets, but may not have access to search URL.

**Solution**: Always include `url` and `retailer` fields in your run_results JSON:

```python
# In your search_and_capture script, when building ad_data:
search_url = page.url  # Get final URL after navigation

ad_data = {
    "keyword": keyword,
    "timestamp": timestamp,
    "retailer": "newretailer",  # For downstream tools
    "url": search_url,          # Primary URL for extractors
    "srp_url": search_url,      # Alias for compatibility
    "ads": []
}
```

**In your extractor** (if using custom extractor):
```python
def load_srp_url(json_path: str) -> str:
    """Load SRP URL from JSON for cookie seeding."""
    try:
        data = json.loads(Path(json_path).read_text())
        # Try common field names (prioritize explicit url fields)
        for k in ("url", "srp_url", "source_url", "page_url"):
            val = data.get(k)
            if isinstance(val, str) and val.strip():
                return val
    except Exception as e:
        print(f"[warn] Could not load SRP URL from JSON: {e}")
    return ""

# Use retailer-aware fallback
def retailer_homepage(retailer: str) -> str:
    return {
        "kroger": "https://www.kroger.com/",
        "amazon": "https://www.amazon.com/",
        "instacart": "https://www.instacart.com/",
        "walmart": "https://www.walmart.com/",
        "newretailer": "https://www.newretailer.com/",
    }.get(retailer, "about:blank")

# Seed cookies
srp_url = load_srp_url(json_path)
retailer = infer_retailer_from_output(output_dir)

seed_candidates = [srp_url] if srp_url else []
seed_candidates.append(retailer_homepage(retailer))

for seed in seed_candidates:
    page.goto(seed, wait_until="commit", timeout=60000)
    # Check if cookies were set
    if len(context.cookies(retailer_domain)) > 0:
        break
```

**Never hardcode fallback URLs** - use retailer-aware helpers instead.

### Robust Image Counting

**Problem**: Image extraction may save files to different folders or timing edge cases cause zero counts.

**Solution**: Use forgiving time windows and check multiple folder names:

```python
def extract_images(self, json_path: str, html_path: str, ctx) -> dict:
    import glob
    from datetime import datetime
    
    # ... run extractor subprocess ...
    
    # Count images with a forgiving window (5 min back)
    slack_seconds = 300
    horizon = pair_start - slack_seconds
    
    def recent_pngs(leaf: str) -> list:
        d = os.path.join(ctx.output_dir, leaf)
        return [
            p for p in glob.glob(os.path.join(d, "*.png"))
            if os.path.getmtime(p) >= horizon
        ]
    
    # Check multiple folder names (retailer-specific + legacy)
    toa_files = []
    toa_files += recent_pngs("Ad_Type_1")
    toa_files += recent_pngs("TOA")  # Legacy fallback
    toa_files += recent_pngs("Main")  # Some extractors use this
    
    sky_files = []
    sky_files += recent_pngs("Ad_Type_2")
    sky_files += recent_pngs("Skyscraper")  # Legacy fallback
    
    # Log what we counted for debugging
    with open(log_path, 'a') as lf:
        lf.write(f"\nCounted files (since {datetime.fromtimestamp(horizon).isoformat()}):\n")
        lf.write(f"  TOA-like: {len(toa_files)}\n")
        for p in sorted(toa_files)[:10]:
            lf.write(f"    - {p}\n")
        lf.write(f"  Skyscraper-like: {len(sky_files)}\n")
        for p in sorted(sky_files)[:10]:
            lf.write(f"    - {p}\n")
    
    return {
        "toa": len(toa_files),
        "sky": len(sky_files),
        "car": 0,
        "log": log_path,
    }
```

**Key points**:
- Use 5-minute slack window (300 seconds) instead of 1-2 seconds
- Check multiple folder names (retailer-specific + legacy + Main)
- Log counted files to extractor log for debugging
- Return counts even if zero (don't raise exceptions)

### Interactive Login Handling

**Problem**: Session may expire during scraping, requiring user to log in again.

**Solution**: Detect login modals and pause for interactive login:

```python
def _is_login_modal_visible(page):
    """Check if login modal is visible."""
    login_selectors = [
        ".login-modal",
        "[data-testid='authModal']",
        "div:has-text('Sign In')",
    ]
    try:
        for sel in login_selectors:
            el = page.query_selector(sel)
            if el and el.is_visible():
                return True
        return False
    except Exception:
        return False

def _prompt_user_login(page, log, max_wait_sec=300):
    """Bring browser to front and wait for user to complete login."""
    try:
        page.bring_to_front()
    except Exception:
        pass
    
    log("⚠️ Login required: Please complete login in the visible browser window.")
    log(f"Timeout in {max_wait_sec} seconds.")
    
    deadline = time.time() + max_wait_sec
    last_report = 0
    while time.time() < deadline:
        if not _is_login_modal_visible(page):
            log("✅ Login modal no longer visible — continuing.")
            return True
        
        now = time.time()
        if now - last_report >= 10:
            remaining = int(deadline - now)
            log(f"Waiting for login to complete... ({remaining}s remaining)")
            last_report = now
        page.wait_for_timeout(1000)
    
    log("❌ Login prompt timeout")
    return False

# Use in your search script:
if _is_login_modal_visible(page):
    if not _prompt_user_login(page, log):
        return False
```

**Benefits**:
- Graceful handling of expired sessions
- User can complete 2FA or CAPTCHA
- Script auto-resumes after login
- Clear progress updates every 10 seconds

### Deterministic Wait Strategies

**Problem**: `domcontentloaded` fires too early, causing scripts to proceed before page is ready.

**Solution**: Wait for specific UI elements or load states:

```python
def _wait_until_page_ready(page, log, timeout_ms=15000):
    """Wait for page to be fully loaded and ready."""
    # 1. Wait for full load event
    try:
        page.wait_for_load_state("load", timeout=timeout_ms)
        log("Page: load state reached")
    except Exception as e:
        log(f"Page: load state wait failed: {e}")
    
    # 2. Wait for specific UI elements
    selectors = [
        "[data-testid='main-content']",
        "input[type='search']",
        "header",
    ]
    for sel in selectors:
        try:
            page.wait_for_selector(sel, timeout=4000)
            log(f"Page: ready selector found: {sel}")
            return
        except Exception:
            pass
    
    # 3. Fallback: short settle delay
    page.wait_for_timeout(3000)
    log("Page: fallback settle delay used")
```

**Key points**:
- Prefer `"load"` over `"domcontentloaded"`
- Wait for actual UI elements, not just DOM ready
- Have a fallback settle delay
- Log each step for debugging

---

**Last Updated**: 2025-10-09
