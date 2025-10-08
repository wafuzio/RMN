# Complete PerimeterX Bypass Strategy for Walmart

## ⚠️ Current Status: STILL BEING FLAGGED (0% Success Rate)

Despite implementing comprehensive evasion techniques, we are still being detected by PerimeterX. This document details what we've implemented and what we're debugging.

## Overview

Walmart uses **PerimeterX** - one of the most sophisticated bot detection systems. It uses machine learning on multiple signals to calculate a trust score. This document details our bypass strategy and current debugging efforts.

## ⚠️ CRITICAL: The --no-sandbox Banner

**If you see "You are using an unsupported command-line flag: --no-sandbox" at the top of Chrome:**
- PerimeterX **INSTANTLY flags this as a bot**
- You will be redirected to `/blocked` immediately
- **FIX**: We force `chromium_sandbox=True` in launch options
- **VERIFY**: No `PW_CHROMIUM_NO_SANDBOX` or `CHROME_NO_SANDBOX` env vars set
- **RUN AS**: Non-root user (root forces --no-sandbox on Linux)

## PerimeterX Detection Methods

### 0. Machine Learning (Behavior Analysis)
- **What they check**:
  - Page visit patterns (chaotic vs. linear)
  - Connection speed and rate (slow/random vs. fast/consistent)
  - Resource loading patterns
  - Trust score evolution over time
- **Our solution**: 
  - Randomized viewport (5 options)
  - Randomized timezone (4 options)
  - Variable wait strategies (networkidle/domcontentloaded/load)
  - Chaotic timing (1.5-4.5s reading time)
  - Non-obvious browsing (20% category visits)

### 1. IP Address Analysis
- **What they check**: IP reputation, datacenter detection, request patterns
- **Our solution**: Residential proxy support via environment variables

### 2. JavaScript Fingerprinting
- **What they check**: 
  - Browser properties (navigator, plugins, languages)
  - WebGL rendering (GPU vendor/renderer)
  - Canvas fingerprinting
  - Hardware specs (CPU cores, memory)
  - Battery API
  - Connection info
- **Our solution**: Comprehensive JavaScript patching (13+ properties spoofed)

### 3. User Input Tracking (Behavioral Biometrics)
- **What they check**:
  - Mouse movement patterns (curves, speed, acceleration)
  - Keystroke timing (delays between keys)
  - Hover events
  - Scroll behavior
- **Our solution**: Ghost-cursor implementation with Bezier curves, variable keystroke timing

### 4. Request Pattern Analysis
- **What they check**:
  - Direct navigation to search (suspicious)
  - No homepage visit (bot-like)
  - Perfect timing (too consistent)
- **Our solution**: Human-like browsing pattern (homepage → scroll → category → search)

### 5. TLS Fingerprinting (JA3)
- **What they check**: 
  - JA3 fingerprint (TLS handshake pattern)
  - Cipher suites negotiation
  - TLS version and extensions
  - HTTP/2 support
- **Critical**: Playwright's Chromium has **WRONG JA3** fingerprint
- **Our solution**: 
  - Use real Chrome (`channel='chrome'`) for correct JA3
  - Proper cipher suite configuration
  - HTTP/2 enabled
  - **NEVER use Chromium** - instant detection!

### 6. Cookie-Based Trust
- **What they check**: Session cookies, cookie age, cookie patterns
- **Our solution**: 24-hour cookie refresh cycle, persistent profile

## What We've Implemented (Still Being Flagged)

### ✅ Human Behavior Simulation
- **Variable keystroke delays**: 80-220ms per character with occasional pauses
- **Micro-mouse movements**: Subtle attention movements during typing (5-15 steps, ±10px jitter)
- **Drift reading**: Mouse drift during result scanning (2-3 seconds)
- **Back-scroll peek**: 35% chance of scrolling back up briefly
- **Random product hover**: Hover on random product tiles
- **Dwell times**: 600-1200ms pause after typing before submit, 2.2-3.5s before first scroll

### ✅ Auto CAPTCHA Solver
- **Press-and-hold detection**: Detects PX "Press and Hold" widget
- **Adaptive timing**: 6.8-10.2s hold duration (varies by widget readiness)
- **Focus click**: Initial click with 40-120ms delay
- **Steady hold**: Mouse down → wait → mouse up (no jitter)
- **Auto-transition detection**: Waits for PX beacon or modal vanish

### ✅ Comprehensive Forensics
- **Run reports**: Every run produces run_report.json + run_report.md
- **Timings**: to_home_ms, after_submit_px_ms, results_ready_ms
- **Environment**: User-Agent, WebGL vendor/renderer
- **Cookies**: Pre/post counts and names (persistence check)
- **PX stats**: Tries, cycles, cleared status
- **Network forensics**: req_failed, resp_doc, route_errors
- **Artifacts**: steps.jsonl, trace.zip, screenshots, HTML, meta.json

### ✅ Bail System
- **Non-retryable detection**: Stops blind retries on px_locked, hard_block, fatal
- **Adapter returns**: `{'ok': bool, 'bail': bool, 'reason': str}`
- **GUI integration**: Stops retrying immediately when bail=True

### ✅ Resilient Navigation
- **3-tier fallback**: domcontentloaded (30s) → commit+search (15s) → networkidle (10s)
- **Forensics on timeout**: Saves HTML/PNG if homepage times out
- **Search box detection**: Treats page as ready when search input visible

### ✅ Debug Tools
- **Break on PX modal**: GUI checkbox to pause execution when PX appears
- **Break on /blocked**: GUI checkbox to pause on redirect to blocked page
- **Line trace**: Microsecond-precision event logging
- **Playwright trace**: trace.zip with screenshots and network activity
- **steps.jsonl**: Complete event log with timestamps
- **run_report.md**: Quick diagnosis (timings, PX stats, network errors)

## Implementation Details

### ✅ 1. Fingerprint Rotation

**Headers (Exact Chrome Match with CORRECT ORDER)**:
```python
from collections import OrderedDict

# CRITICAL: Header ORDER matters! PerimeterX checks this
REAL_CHROME_HEADERS = OrderedDict([
    ("sec-ch-ua", '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"'),
    ("sec-ch-ua-mobile", "?0"),
    ("sec-ch-ua-platform", '"macOS"'),
    ("Upgrade-Insecure-Requests", "1"),
    ("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)..."),
    ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9..."),
    ("Sec-Fetch-Site", "none"),
    ("Sec-Fetch-Mode", "navigate"),
    ("Sec-Fetch-User", "?1"),
    ("Sec-Fetch-Dest", "document"),
    ("Accept-Encoding", "gzip, deflate, br, zstd"),
    ("Accept-Language", "en-US,en;q=0.9"),
])
```

**Why Order Matters**:
- Chrome sends headers in specific order
- PerimeterX compares header order against known browsers
- Wrong order = instant bot detection
- Python's `dict` doesn't preserve order in older versions
- Use `OrderedDict` or Python 3.7+ dict (preserves insertion order)

**GPU Spoofing (Consumer-Grade)**:
```javascript
// CRITICAL: Use consumer GPU, NOT professional (Quadro, FirePro)
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel Iris Plus Graphics 640';  // MacBook GPU
    // ...
}
```

### ✅ 2. Behavioral Simulation

**Ghost Cursor (Bezier Curves)**:
```python
def ghost_cursor_move(page, start_x, start_y, end_x, end_y):
    # Cubic Bezier curve with control points
    # Variable timing: slower at edges, faster in middle
    # 15-25 steps for smooth movement
```

**Keystroke Timing**:
```python
for char in keyword:
    search_box.type(char, delay=random.uniform(80, 200))  # 80-200ms per key
```

**Hover Events**:
```python
products[0].hover()  # Hover over first product
time.sleep(random.uniform(0.5, 1.0))
```

### ✅ 3. Proxy Rotation

**Environment Variables**:
```bash
export WALMART_PROXY_SERVER="http://proxy.example.com:8080"
export WALMART_PROXY_USERNAME="username"
export WALMART_PROXY_PASSWORD="password"
```

**Residential Proxies Recommended**:
- Bright Data (premium)
- Smartproxy (good balance)
- Oxylabs (enterprise)

### ✅ 4. JavaScript Execution

**Playwright with Stealth**:
- Persistent Chrome (channel='chrome')
- 30+ anti-detection flags
- 13+ JavaScript property patches
- WebGL spoofing
- Battery API patching

### ✅ 5. CAPTCHA Handling

**Manual Solving (Headed Mode)**:
```python
if block_reason == "perimeterx_captcha":
    if not headless:
        # Wait 60 seconds for user to solve
        for i in range(30):
            time.sleep(2)
            if CAPTCHA_solved:
                break
```

**Automatic Detection**:
- Detects `#px-captcha` element
- Detects "Robot or human?" text
- Logs block reason
- Provides actionable feedback

### ✅ 6. TLS Fingerprinting Resistance (JA3)

**CRITICAL: Real Chrome Required**:
```python
# MUST use channel='chrome' for correct JA3 fingerprint
launch_options['channel'] = 'chrome'
ctx = playwright.chromium.launch_persistent_context(**launch_options)
```

**Why This Matters**:
- Playwright's Chromium: **Wrong JA3** = Instant detection
- Real Chrome: **Correct JA3** = Passes PerimeterX
- JA3 is the TLS handshake fingerprint
- PerimeterX compares it against known browser JA3s

**Verify Your JA3**:
1. Visit: https://ja3er.com/json
2. Check if JA3 matches real Chrome
3. Real Chrome JA3: `771,4865-4866-4867-49195-49199-49196-49200-52393-52392-49171-49172-156-157-47-53,0-23-65281-10-11-35-16-5-13-18-51-45-43-27-17513,29-23-24,0`

**Chrome Args**:
```python
'--cipher-suite-blacklist=0x0004,0x0005,0xc011,0xc007',
'--enable-features=NetworkService,NetworkServiceInProcess',
'--disable-features=EnableTLS13EarlyData',
```

**HTTP/2 Support**: Enabled by default in Chrome

**Install Real Chrome**:
```bash
brew install --cask google-chrome
```

## Human-Like Browsing Pattern

### Flow:
1. **Homepage Visit** (2-4s)
   - `page.goto("https://www.walmart.com/")`
   - Wait for networkidle
   - Simulate reading

2. **Scroll Homepage** (0.8-1.5s)
   - Smooth scroll to 400px
   - Random delay

3. **Ghost Cursor Movement** (0.5-1s)
   - Bezier curve path
   - Variable speed (slower at edges)
   - 15-25 steps

4. **Maybe Browse Category** (20% chance)
   - Navigate to random department
   - Scroll and pause
   - Non-obvious pattern

5. **Search Input** (3-6s)
   - Click search box
   - Type with 80-200ms delays per character
   - Press Enter

6. **Read Results** (1.5-3s)
   - Hover over products
   - Scroll smoothly
   - Mouse movements

## Cookie Refresh Strategy

**24-Hour Cycle**:
```python
def _should_refresh_cookies(profile_dir):
    # Check .cookie_refresh_time marker
    # Refresh if > 24 hours old
    
def _mark_cookies_refreshed(profile_dir):
    # Write current timestamp
```

**Files Cleared**:
- `Cookies`
- `Cookies-journal`
- `Network Persistent State`

## Block Detection

**Signals Detected**:
- `perimeterx_captcha` - CAPTCHA challenge
- `access_denied` - IP blocked
- `rate_limit` - Too many requests
- `unusual_activity` - Behavioral flags
- `empty_response` - No products (suspicious)

**Actions**:
- Log block reason
- Suggest proxy rotation
- Suggest profile change
- Return error (no data)

## Success Metrics

**Trust Score Factors**:
1. ✅ Consumer GPU (not professional)
2. ✅ Exact Chrome headers
3. ✅ Human-like mouse curves
4. ✅ Variable keystroke timing
5. ✅ Hover events
6. ✅ Non-obvious browsing pattern
7. ✅ Residential IP (if proxy configured)
8. ✅ Fresh cookies (24hr cycle)
9. ✅ TLS fingerprint matches Chrome
10. ✅ HTTP/2 support

## Usage

### Setup:
```bash
# 1. Create profile
python3 scripts/manual_walmart_setup.py

# 2. Configure proxy (optional but recommended)
export WALMART_PROXY_SERVER="http://residential-proxy.com:8080"
export WALMART_PROXY_USERNAME="user"
export WALMART_PROXY_PASSWORD="pass"

# 3. Set profile
export WALMART_PROFILE_DIR="$HOME/Documents/Amazon_Scrape/profiles/walmart"
```

### Run:
```bash
python3 keyword_input.py
# Select Walmart
# Enter keyword
# Click "Start Scraping"
```

### Expected Behavior:
1. Browser opens (headed mode)
2. Visits homepage
3. Scrolls and moves mouse naturally
4. Types search with delays
5. Hovers over products
6. **If CAPTCHA appears**: Solve it manually (60s window)
7. Captures HTML and screenshots
8. Marks cookies as refreshed

## Limitations

**What We CANNOT Bypass**:
- PerimeterX machine learning (it learns patterns)
- Repeated same-IP requests (need proxy rotation)
- Identical behavioral patterns (need randomization)
- Professional GPU detection (need consumer hardware)

**What Helps**:
- ✅ Residential proxies (mandatory for production)
- ✅ Profile rotation (multiple authenticated profiles)
- ✅ Time delays between runs (30-60 seconds minimum)
- ✅ Off-peak hours (less detection)
- ✅ CAPTCHA solving service (for full automation)

## Troubleshooting & Debugging

### Current Issues (As of 2025-10-08)

**We are still being flagged by PerimeterX despite all evasion techniques.** Here's what to check:

### Analyze Run Reports

Every run produces diagnostic files in `output/walmart/<keyword>/runs/<timestamp>/`:

1. **run_report.md** - Quick diagnosis:
   ```bash
   cat output/walmart/*/runs/*/run_report.md
   ```
   - Check `outcome`: success/fail/bail
   - Check `bail_reason`: px_locked/hard_block/fatal
   - Check `timings.after_submit_px_ms`: How fast PX appeared
   - Check `network.route_errors`: Should be 0 (was causing timeouts)

2. **steps.jsonl** - Detailed event log:
   ```bash
   python3 view_debug_logs.py
   ```
   - Look for `px_trip` events (when PX first detected)
   - Check `after_submit` timing (instant PX = reputation issue)
   - Check `route_error` events (should be 0 now)

3. **trace.zip** - Playwright trace viewer:
   ```bash
   playwright show-trace output/walmart/*/runs/*/walmart_*_trace.zip
   ```
   - Visual timeline of all actions
   - Network requests and responses
   - Screenshots at each step

### Still Getting CAPTCHA/Blocked?

1. **Check GPU**: Must be consumer-grade (Intel Iris, AMD Radeon, NVIDIA GTX)
   - Look in run_report.md → Environment → webgl_renderer
   - Should NOT be SwiftShader or professional GPU

2. **Check Proxy**: Must be residential, not datacenter
   - Datacenter IPs are instantly flagged
   - Test: `curl -x $WALMART_PROXY_SERVER https://www.walmart.com/`

3. **Check Timing**: 
   - Look at `timings.after_submit_px_ms` in run_report.md
   - < 500ms = Reputation issue (IP/profile flagged)
   - > 2000ms = Behavior issue (detected during interaction)

4. **Check Profile**: Must be authenticated with fresh cookies
   - Look at `cookies.pre_count` in run_report.md
   - Should have 15-20 cookies from previous runs
   - 0 cookies = Profile not persisting

5. **Check Pattern**: Should visit homepage, not direct search
   - Look for `home_goto_phase_final` in steps.jsonl
   - Should be "domcontentloaded" or "commit+search"

### Proxy Not Working?

```bash
# Test proxy
curl -x $WALMART_PROXY_SERVER \
  -U $WALMART_PROXY_USERNAME:$WALMART_PROXY_PASSWORD \
  https://www.walmart.com/
```

### Profile Issues?

```bash
# Clear and recreate
rm -rf ~/Documents/Amazon_Scrape/profiles/walmart
python3 scripts/manual_walmart_setup.py
```

## Cost Estimates

**Residential Proxies**:
- $5-15 per GB
- ~1000-2000 searches per GB
- Budget: $10-30/month

**CAPTCHA Solving** (if needed):
- $1-3 per 1000 CAPTCHAs
- Budget: $5-20/month

**Total**: $15-50/month for moderate use

## References

- PerimeterX Documentation: https://www.perimeterx.com/
- Ghost Cursor: https://npmjs.com/package/ghost-cursor
- Playwright Stealth: https://github.com/berstend/puppeteer-extra/tree/master/packages/puppeteer-extra-plugin-stealth
- WebGL Fingerprinting: https://browserleaks.com/webgl

## Next Steps to Try

Based on run_report.md analysis, consider:

1. **Residential Proxies** (if not using):
   - Bright Data, Smartproxy, Oxylabs
   - Datacenter IPs are instantly flagged
   - Cost: $5-15/GB

2. **Longer Dwell Times**:
   - Increase pre-submit dwell to 2-3 seconds
   - Increase homepage idle to 5-10 seconds
   - More random product interactions

3. **Profile Aging**:
   - Let profile sit for 24-48 hours between runs
   - Manual browsing sessions to build trust
   - Multiple authenticated profiles

4. **Request Pattern Analysis**:
   - Check trace.zip for suspicious patterns
   - Look for missing requests (images, fonts, etc.)
   - Verify all sec-ch-ua headers match

5. **Consider CAPTCHA Solving Service**:
   - 2Captcha, Anti-Captcha, CapSolver
   - $1-3 per 1000 CAPTCHAs
   - Integrate with auto-solver

## See Also

- `docs/WALMART_PROXY_SETUP.md` - Proxy configuration guide
- `docs/reference/Walmart_ad_html.md` - Ad selectors
- `scripts/manual_walmart_setup.py` - Profile setup
- `walmart_search_and_capture.py` - Main implementation
- `view_debug_logs.py` - Analyze steps.jsonl files
