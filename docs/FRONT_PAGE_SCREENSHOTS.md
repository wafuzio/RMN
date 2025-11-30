# Front Page Screenshot System

**Purpose:** Automated capture of retailer front pages (homepage) for competitive intelligence and UI/UX monitoring.

**Status:** 🚧 In Development (Nov 2025)

---

## Overview

This system captures full-page screenshots of retailer homepages on a scheduled basis, storing them in a timestamped archive for historical comparison and trend analysis.

**Use Cases:**
- Monitor homepage layout changes
- Track promotional banner rotations
- Analyze seasonal merchandising strategies
- Document UI/UX evolution over time
- Competitive intelligence on homepage real estate

---

## Architecture

### Storage Structure

```
output/screen_capture/
├── kroger/
│   └── front_pages/
│       ├── kroger__front_page__D2025-11-24_T18-30.00.png
│       ├── kroger__front_page__D2025-11-24_T22-30.00.png
│       └── kroger__front_page__D2025-11-25_T06-30.00.png
├── walmart/
│   └── front_pages/
│       └── walmart__front_page__D2025-11-24_T18-30.00.png
├── amazon/
│   └── front_pages/
├── instacart/
│   └── front_pages/
└── target/
    └── front_pages/
```

**Filename Pattern:**
```
<retailer>__front_page__DYYYY-MM-DD_THH-MM.SS.png
```

**Example:**
```
kroger__front_page__D2025-11-24_T18-30.00.png
```

### Retailer URLs

| Retailer   | Homepage URL                      | Profile Required |
|------------|-----------------------------------|------------------|
| Kroger     | https://www.kroger.com/           | Optional         |
| Walmart    | https://www.walmart.com/          | Optional         |
| Amazon     | https://www.amazon.com/           | Optional         |
| Instacart  | https://www.instacart.com/        | Recommended      |
| Target     | https://www.target.com/           | Optional         |

**Note:** Using persistent profiles ensures logged-in state for personalized homepage views.

---

## Components

### 1. Capture Script

**File:** `scripts/screenshot_front_page.py`

**Usage:**
```bash
# Capture single retailer
python scripts/screenshot_front_page.py --retailer kroger

# Capture all retailers
python scripts/screenshot_front_page.py --all

# Specify custom output root
python scripts/screenshot_front_page.py --retailer walmart --output-root /path/to/output

# Use specific profile
python scripts/screenshot_front_page.py --retailer instacart --profile-dir ~/ChromeProfiles/instacart
```

**Features:**
- Full-page screenshot (entire document height, not just viewport)
- Headed-but-hidden mode (avoids headless detection)
- Persistent profile support (maintains login state)
- Automatic retry on failure
- Timestamped filenames
- Logs to `logs/front_page_capture.log`

### 2. GUI Integration

**Location:** `keyword_input.py` → "Front Page Screenshots" section

**Features:**
- Retailer picker (multi-select)
- "Capture Now" button (runs captures in background thread)
- "Open Folder" button (opens output directory in Finder)
- Status display (success/failure per retailer)
- Base path display (shows resolved output directory)

**UI Layout:**
```
┌─────────────────────────────────────────────┐
│ Front Page Screenshots                      │
├─────────────────────────────────────────────┤
│ Select Retailers:                           │
│ ☑ Kroger    ☑ Walmart   ☑ Amazon           │
│ ☑ Instacart ☑ Target                        │
│                                             │
│ Output: output/screen_capture/              │
│                                             │
│ [Capture Now]  [Open Folder]                │
│                                             │
│ Status:                                     │
│ ✓ Kroger - Saved to kroger/front_pages/... │
│ ✓ Walmart - Saved to walmart/front_pages/..│
│ ✗ Amazon - Failed: timeout                 │
└─────────────────────────────────────────────┘
```

### 3. Scheduler Integration

The scheduler daemon (`scheduler_daemon.py`) automatically handles front page captures.

**Configuration:** `schedules/frontpage_capture.json`
```json
{
  "enabled": true,
  "days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
  "times": ["12:05"],
  "retailers": ["kroger", "walmart", "amazon", "instacart", "target"],
  "description": "Daily front page screenshot capture"
}
```

**Features:**
- **Once-per-day capture:** Only one capture per retailer per day
- **Catch-up logic:** If scheduled time is missed (system asleep), captures on next wake
- **Duplicate prevention:** Checks for existing files before catch-up runs
- **Parallel execution:** Runs alongside keyword scrapes without blocking

**How it works:**
1. Scheduler checks `frontpage_capture.json` every minute
2. If scheduled time matches (within 2-minute window), triggers capture
3. If scheduled time was missed, checks if captures already exist for today
4. Only runs catch-up if no captures exist for the current date
5. Looks for files matching `<retailer>__front_page__D<YYYY-MM-DD>_*.png`

**Manual Cron Alternative:**
```bash
# Capture all retailers at 8am daily
0 8 * * * cd /path/to/Amazon_Scrape && python scripts/screenshot_front_page.py --all
```

---

## Technical Details

### Screenshot Method

**Approach:** Scroll-triggered lazy loading + full-page screenshot

The script scrolls through the page to trigger lazy-loaded content, then captures using Playwright's `full_page=True` option.

### Browser Configuration (PerimeterX Evasion)

**CRITICAL:** Walmart and Target use PerimeterX bot detection. The front page capture script uses the same evasion techniques as the main Walmart scraper.

**Launch Options:**
```python
launch_options = {
    'user_data_dir': profile_dir,
    'headless': False,  # ALWAYS headed - retailers block headless
    'viewport': {"width": 1280, "height": 720},
    'locale': 'en-US',
    'args': [
        '--use-angle=metal',  # Real GPU (not SwiftShader)
        '--enable-gpu-rasterization',
        '--ignore-gpu-blocklist',
        '--no-startup-window',
        '--silent-launch',
        # NOTE: Do NOT use --no-sandbox - instant bot flag
    ],
    'ignore_default_args': ['--enable-automation'],  # navigator.webdriver=false
    'chromium_sandbox': True,  # Removes --no-sandbox banner
    'channel': 'chrome',  # Real Chrome for correct JA3 fingerprint
}
```

**Key Evasion Techniques:**
- **Real Chrome** (`channel='chrome'`) - Correct JA3 TLS fingerprint
- **GPU acceleration** (`--use-angle=metal`) - Real WebGL renderer, not SwiftShader
- **No automation flag** (`ignore_default_args=['--enable-automation']`) - `navigator.webdriver=undefined`
- **Sandbox enabled** (`chromium_sandbox=True`) - Removes "--no-sandbox" banner
- **Persistent profile** - Cookie reputation and session persistence

**Why these matter:**
- PerimeterX checks JA3 TLS fingerprint - Playwright's Chromium has wrong fingerprint
- SwiftShader WebGL = instant bot detection
- `navigator.webdriver=true` = instant bot detection
- "--no-sandbox" banner = instant bot detection

**See:** `docs/WALMART_PERIMETERX_COMPLETE.md` for full details

### Error Handling

**Common Failures:**
1. **Navigation timeout** - Retry with longer timeout
2. **Profile locked** - Skip if another process is using profile
3. **Network error** - Retry up to 3 times
4. **Screenshot failed** - Log error and continue to next retailer

**Retry Strategy:**
```python
max_retries = 3
for attempt in range(max_retries):
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=10000)
        break
    except Exception as e:
        if attempt == max_retries - 1:
            raise
        time.sleep(2 ** attempt)  # Exponential backoff
```

---

## Configuration

### Environment Variables

```bash
# Optional: Override output root
export FRONT_PAGE_OUTPUT_ROOT="$HOME/Documents/RetailerFrontPages"

# Optional: Retailer-specific profiles
export KROGER_PROFILE_DIR="$HOME/ChromeProfiles/kroger"
export WALMART_PROFILE_DIR="$HOME/ChromeProfiles/walmart"
export AMAZON_PROFILE_DIR="$HOME/ChromeProfiles/amazon"
export INSTACART_PROFILE_DIR="$HOME/ChromeProfiles/instacart"
export TARGET_PROFILE_DIR="$HOME/ChromeProfiles/target"
```

### Default Paths

**Output Root (priority order):**
1. `$FRONT_PAGE_OUTPUT_ROOT` (if set)
2. `$SCRAPER_HOME/output/screen_capture` (if SCRAPER_HOME set)
3. `~/Documents/Amazon_Scrape/output/screen_capture` (fallback)

**Profile Directories (priority order):**
1. `--profile-dir` CLI argument
2. `<RETAILER>_PROFILE_DIR` environment variable
3. `$SCRAPER_HOME/profiles/<retailer>` (if exists)
4. No profile (incognito mode)

---

## Usage Examples

### Capture Single Retailer
```bash
python scripts/screenshot_front_page.py --retailer kroger
```

**Output:**
```
[front_page] Starting capture for kroger
[front_page] Using profile: /Users/dan/ChromeProfiles/kroger
[front_page] Navigating to https://www.kroger.com/
[front_page] Waiting for page load...
[front_page] Capturing full-page screenshot...
[front_page] ✓ Saved: output/screen_capture/kroger/front_pages/kroger__front_page__D2025-11-24_T18-30.00.png
[front_page] Screenshot size: 1920x8450 (4.2 MB)
```

### Capture All Retailers
```bash
python scripts/screenshot_front_page.py --all
```

**Output:**
```
[front_page] Capturing front pages for 5 retailers...
[front_page] [1/5] kroger - ✓ Success (3.2s)
[front_page] [2/5] walmart - ✓ Success (4.1s)
[front_page] [3/5] amazon - ✗ Failed: Navigation timeout
[front_page] [4/5] instacart - ✓ Success (2.8s)
[front_page] [5/5] target - ✓ Success (3.5s)
[front_page] Summary: 4/5 successful
```

### GUI Capture
1. Open `keyword_input.py`
2. Scroll to "Front Page Screenshots" section
3. Select retailers (Kroger, Walmart, etc.)
4. Click "Capture Now"
5. Watch status updates in real-time
6. Click "Open Folder" to view screenshots

---

## Troubleshooting

### Screenshot is blank/white
**Cause:** Page didn't finish loading before screenshot.

**Fix:**
```python
# Add longer wait
page.wait_for_load_state("networkidle", timeout=15000)
page.wait_for_timeout(2000)  # Additional grace period
```

### Screenshot cuts off at viewport height
**Cause:** Using `page.screenshot()` instead of CDP.

**Fix:** Ensure using CDP `Page.captureScreenshot` with `captureBeyondViewport=true`.

### Profile locked error
**Cause:** Another process is using the same profile.

**Fix:**
```bash
# Find and kill hung processes
ps aux | grep screenshot_front_page
kill <PID>

# Remove lock file
rm ~/ChromeProfiles/<retailer>/SingletonLock
```

### Different content than manual browsing
**Cause:** Not using persistent profile (logged out state).

**Fix:** Specify profile directory:
```bash
python scripts/screenshot_front_page.py --retailer instacart --profile-dir ~/ChromeProfiles/instacart
```

### Navigation timeout
**Cause:** Slow network or page load issues.

**Fix:**
```bash
# Increase timeout
python scripts/screenshot_front_page.py --retailer walmart --timeout 60
```

---

## File Organization

```
Amazon_Scrape/
├── scripts/
│   └── screenshot_front_page.py          # Main capture script
├── keyword_input.py                      # GUI integration
├── output/
│   └── screen_capture/                   # Screenshot storage
│       ├── kroger/front_pages/
│       ├── walmart/front_pages/
│       ├── amazon/front_pages/
│       ├── instacart/front_pages/
│       └── target/front_pages/
├── logs/
│   └── front_page_capture.log            # Capture logs
└── docs/
    └── FRONT_PAGE_SCREENSHOTS.md         # This file
```

---

## Future Enhancements

### Planned Features
- [ ] **Comparison View** - Side-by-side diff of screenshots over time
- [ ] **Change Detection** - Automated alerts when homepage changes significantly
- [ ] **Scheduled Captures** - Integration with scheduler_daemon.py
- [ ] **Mobile Screenshots** - Capture mobile viewport versions
- [ ] **Video Recording** - Record 30-second homepage interaction
- [ ] **Metadata Extraction** - Parse hero banners, promo text, featured products
- [ ] **API Integration** - Serve screenshots via Flask API for Builder.io

### Advanced Options
- **Custom viewport sizes** - Desktop, tablet, mobile
- **Scroll-through capture** - Capture after scrolling to trigger lazy-loaded content
- **Interactive wait** - Wait for specific elements before capturing
- **Multi-region** - Capture different geographic variants (requires VPN/proxy)

---

## Related Documentation

- **Main Context:** `docs/CONTEXT_SEED.md`
- **Troubleshooting:** `docs/COMMON_ISSUES.md`
- **Playwright Setup:** `docs/PLAYWRIGHT_BOOTSTRAP.md`
- **GUI Guide:** `keyword_input.py` source code

---

## Changelog

### Nov 2025 - Initial Implementation
- Created capture script with CDP full-page screenshots
- Added GUI integration to keyword_input.py
- Documented storage structure and usage
- Configured for all 5 retailers (Kroger, Walmart, Amazon, Instacart, Target)
