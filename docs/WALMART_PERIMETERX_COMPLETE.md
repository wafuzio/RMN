# Complete PerimeterX Bypass Strategy for Walmart

## ⚠️ Current Status: BLOCKED AT SEARCH SUBMISSION (0% Success Rate)

**Last Updated**: 2025-10-08 22:13

**Current Failure Mode**: We can successfully load walmart.com homepage with a fresh profile, but immediately trigger PX hard block when submitting search query. This indicates search submission behavior is the primary detection vector.

## Overview

Walmart uses **PerimeterX (PX)** + **Akamai Bot Manager** - two of the most sophisticated bot detection systems working in tandem. They use machine learning on multiple signals to calculate a trust score. This document details our current implementation and known issues.

## ⚠️ CRITICAL: The --no-sandbox Banner

**If you see "You are using an unsupported command-line flag: --no-sandbox" at the top of Chrome:**
- PerimeterX **INSTANTLY flags this as a bot**
- You will be redirected to `/blocked` immediately
- **FIX**: We force `chromium_sandbox=True` in launch options
- **VERIFY**: No `PW_CHROMIUM_NO_SANDBOX` or `CHROME_NO_SANDBOX` env vars set
- **RUN AS**: Non-root user (root forces --no-sandbox on Linux)

## PerimeterX Detection Vectors (What They Check)

### 1. Browser Fingerprint Consistency
- **What they check**:
  - User-Agent vs WebGL renderer mismatch
  - User-Agent vs Client Hints (sec-ch-ua) mismatch
  - JA3 TLS fingerprint vs declared browser
  - navigator.webdriver flag
  - Missing or unusual navigator properties
- **Our implementation**: 
  - ✅ Real Chrome via `channel='chrome'` (correct JA3)
  - ✅ GPU args: `--use-angle=metal`, `--enable-gpu-rasterization`, `--ignore-gpu-blocklist`
  - ✅ `ignore_default_args=['--enable-automation']` to prevent webdriver flag
  - ✅ UNMASKED WebGL logging for verification
  - ✅ Fingerprint guard: bails on SwiftShader, warns on WebKit masked
  - ✅ Navigator diagnostics logged (webdriver, plugins, hardwareConcurrency, etc.)

### 2. Request Routing & Network Behavior
- **What they check**:
  - Playwright routing fingerprints (touching PX/RUM/TAP endpoints)
  - Missing resource requests (images, fonts, CSS)
  - Request timing patterns
  - Header order and presence
- **Our implementation**:
  - ✅ Routing narrowed to Google-only (not `**/*`)
  - ✅ PX/RUM/TAP endpoints are listen-only (no route.continue() interference)
  - ✅ sec-ch-ua headers logged on first navigation
  - ✅ UA-CH missing warning
  - ⚠️  **CONCERN**: Search submission may have unusual request pattern

### 3. Profile & Cookie Reputation
- **What they check**:
  - Bot Manager cookies (adblocked, ak_bmsc, bm_mi, bm_sv, bm_sz, abck)
  - Cookie persistence and age
  - Profile history and trust score
- **Our implementation**:
  - ✅ Persistent Chrome profile required (enforced)
  - ✅ Suspicious cookie detection (6 Bot Manager flags)
  - ✅ Profile health logging (Cookies, Network Persistent State, Preferences)
  - ✅ Clean profile setup script
  - ⚠️  **ISSUE**: Old profiles had poisoned cookies - must use fresh profile

### 4. Playwright Stealth Detection
- **What they check**:
  - Stealth plugin mutations (navigator, permissions, plugins, fonts)
  - Common bot-kit flags (--disable-blink-features=AutomationControlled)
  - Playwright-specific signatures
- **Our implementation**:
  - ✅ Stealth DISABLED by default for Walmart (env var to enable)
  - ✅ No bot-kit flags (colleague confirmed --disable-blink-features is a red flag)
  - ✅ Real Chrome signals instead of spoofing
  - ✅ Stealth skip logged

### 5. Search Submission Behavior (PRIMARY DETECTION VECTOR)
- **What they check**:
  - Programmatic form submission vs Enter key
  - Timing between typing and submission
  - Mouse position during submission
  - Focus state of search box
- **Our implementation**:
  - ⚠️  **LIKELY ISSUE**: Using `search_box.press("Enter")` which may be detectable
  - ⚠️  **LIKELY ISSUE**: Programmatic navigation to `/search` URL after button click
  - ❌ **NOT IMPLEMENTED**: Natural Enter key with proper focus/blur events
  - ❌ **NOT IMPLEMENTED**: Mouse click on search button (more human-like)

### 6. Page Evaluation Timing
- **What they check**:
  - Immediate page.evaluate() calls after navigation
  - Evaluation context lifecycle
  - Timing of diagnostic checks
- **Our implementation**:
  - ✅ eval_safe wrapper prevents crashes
  - ✅ Bail-on-blocked check before evals
  - ✅ Logs eval_error with label, URL, error
  - ✅ No fatal "Page.evaluate:" crashes

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

### ✅ Comprehensive Diagnostics & Forensics
- **Run reports**: Every run produces run_report.json + run_report.md with diag section
- **Timings**: to_home_ms, after_submit_px_ms, results_ready_ms
- **Environment**: User-Agent, WebGL vendor/renderer, UNMASKED WebGL
- **Navigator diagnostics**: webdriver, plugins, hardwareConcurrency, deviceMemory, userAgentData
- **Nav headers**: sec-ch-ua, sec-ch-ua-mobile, sec-ch-ua-platform logged on first request
- **Cookies**: Pre/post counts and names (persistence check), suspicious cookie detection
- **PX stats**: Tries, cycles, cleared status
- **Network forensics**: req_failed, resp_doc, route_errors
- **Artifacts**: steps.jsonl, trace.zip, screenshots, HTML, meta.json
- **Diag summary in Markdown**: Quick human triage without opening JSON

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
- **eval_safe wrapper**: Prevents "Page.evaluate:" crashes, logs eval errors with context
- **Bail-on-blocked guard**: Stops execution immediately if /blocked detected after homepage

## 🔴 Known Issues & Current Blockers

### Issue #1: Search Submission Triggers Immediate Block
**Status**: BLOCKING - 100% failure rate  
**Symptom**: Homepage loads successfully, but search submission triggers instant 307 → /blocked  
**Evidence**:
- `resp_doc: 307` on search URL
- `hard_block` logged immediately after search
- No PX challenge modal - straight to blocked page

**Likely Causes**:
1. **Programmatic form submission** - Using `search_box.press("Enter")` may be detectable
2. **Programmatic navigation fallback** - Code navigates to `/search?q=...` URL if button click fails
3. **Missing human signals** - No mouse position, focus/blur events during submission
4. **Timing pattern** - Consistent timing between typing and submission

**Next Steps to Try**:
- [ ] Use keyboard.press("Enter") instead of element.press("Enter")
- [ ] Add mouse movement to search button before Enter
- [ ] Ensure proper focus state before submission
- [ ] Add variable delay (1-3s) after last keystroke
- [ ] Remove programmatic navigation fallback
- [ ] Test with manual Enter key in headed mode

### Issue #2: webdriver=True in Navigator Diagnostics
**Status**: INVESTIGATING  
**Symptom**: `navigator.webdriver=True` logged in some runs  
**Evidence**: `[diag] {'webdriver': True, ...}` in console output

**Expected**: Should be `False` with `ignore_default_args=['--enable-automation']`

**Possible Causes**:
1. `ignore_default_args` not being applied correctly
2. Playwright version issue
3. Chrome channel launch failure (falling back to Chromium)

**Next Steps**:
- [ ] Verify Chrome channel launch success ("✅ Using real Chrome" in logs)
- [ ] Test with fresh Playwright installation
- [ ] Check if persistent context applies ignore_default_args correctly

### Issue #3: Profile Environment Variable Not Respected by GUI
**Status**: CONFIRMED  
**Symptom**: GUI uses old profile path despite `WALMART_PROFILE_DIR` env var  
**Evidence**: 
```
export WALMART_PROFILE_DIR="/Users/dan.maguire/ChromeProfiles/walmart_clean2"
# But logs show:
[profile] WALMART_PROFILE_DIR='/Users/dan.maguire/ChromeProfiles/walmart'
```

**Impact**: Cannot test with clean profile via GUI

**Next Steps**:
- [ ] Verify GUI reads environment variables on startup
- [ ] Test with command-line adapter directly
- [ ] Add profile path selector to GUI

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

### Current Status (As of 2025-10-08 22:13)

**We can load homepage but are blocked at search submission (100% failure rate).** This indicates the search submission behavior is the primary detection vector, not the initial fingerprint.

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

## Next Steps to Try (Priority Order)

### 🔴 Priority 1: Fix Search Submission Behavior
**Current blocker** - This is why we're getting blocked:

1. **Replace programmatic Enter with natural keyboard event**:
   - Change from `search_box.press("Enter")` to `page.keyboard.press("Enter")`
   - Ensure search box has focus before pressing Enter
   - Add proper focus/blur event sequence

2. **Remove programmatic navigation fallback**:
   - Delete the `page.goto(search_url)` fallback after button click
   - This is a clear bot signal

3. **Add human-like submission delay**:
   - Variable 1-3s delay after last keystroke before submission
   - Random chance (30%) to pause and re-read query before submitting

4. **Test with manual Enter in headed mode**:
   - Verify that manual Enter key works without block
   - If manual works, confirms our submission method is the issue

### 🟡 Priority 2: Verify Fingerprint is Clean

1. **Test with fresh profile** (walmart_clean2):
   - Run `./scripts/setup_clean_walmart_profile.sh walmart_clean2`
   - Manually age profile (2-3 minutes browsing)
   - Verify no suspicious cookies in pre-run

2. **Confirm webdriver=False**:
   - Check navigator_diag in run_report.md
   - Should show `webdriver: False`
   - If True, investigate ignore_default_args

3. **Verify UNMASKED WebGL shows ANGLE/Metal**:
   - Check webgl_unmasked in run_report.md
   - Should NOT show SwiftShader
   - Should show ANGLE or Metal renderer

### 🟢 Priority 3: Consider Additional Mitigations

1. **Residential Proxies** (if not using):
   - Bright Data, Smartproxy, Oxylabs
   - Datacenter IPs may be flagged
   - Cost: $5-15/GB

2. **Longer Dwell Times**:
   - Increase pre-submit dwell to 2-3 seconds
   - Increase homepage idle to 5-10 seconds
   - More random product interactions

3. **Profile Aging**:
   - Let profile sit for 24-48 hours between runs
   - Manual browsing sessions to build trust
   - Multiple authenticated profiles

## See Also

- `docs/WALMART_PROXY_SETUP.md` - Proxy configuration guide
- `docs/reference/Walmart_ad_html.md` - Ad selectors
- `scripts/manual_walmart_setup.py` - Profile setup
- `walmart_search_and_capture.py` - Main implementation
- `view_debug_logs.py` - Analyze steps.jsonl files
