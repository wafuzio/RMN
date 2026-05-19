# Complete PerimeterX Bypass Strategy for Walmart

## Current Status: ✅ OPERATIONAL — PX Modal Eliminated (3-KW clean run confirmed)

**Last Updated**: 2026-05-19

**Current State**: Full PX bypass achieved. First clean 3-keyword run with no "Robot or human?" modal on any keyword — first time in months. Root causes identified and fixed through step-log forensic analysis.

**Latest test results** (2026-05-19, post-fix):
- KW1 (proactiv): ✅ Clean — no PX modal, all ad types captured
- KW2 (acne skin care): ✅ Clean — no PX modal, gallery cards captured
- KW3 (acne kit): ✅ Clean — no PX modal, full run complete

**What was actually causing the modal (in order of impact):**

1. **`_pxvid` cookie survived profile wipes** — PX stores the visitor ID in BOTH localStorage AND a cookie. We were only clearing localStorage. The flagged vid (`337ff3c0`) persisted in `ctx.cookies()` and was sent to `ift.px-cloud.net/ns?v=` within 7 seconds of page load — before any scroll happened. The challenge was predetermined at navigation time. **Fix**: delete `_pxvid` + `_pxde` from ctx cookies before every navigation (both fresh and reuse paths).

2. **JavaScript scrolls in capture code** — After fixing keyboard events and scroll_passes, PX was still triggering during the ad capture phase (SBV, gallery cards, full-page). `element.scroll_into_view_if_needed()` and `window.scrollTo()` are detectable as non-human. **Fix**: replaced all remaining JS scrolls with `page.mouse.wheel()` bursts via `_bring_into_view()` and `_scroll_like_human()`.

3. **`element.type()` for keyboard input** — fires only synthetic `InputEvent`, missing `KeyDown/KeyPress/KeyUp` chain. PX detects this. **Fix**: `page.keyboard.type(ch)` per character via `human_type(element, text, page=page)`.

4. **Contaminated browser profile** — profile accumulated flagged `_pxvid` history, `adblocked` cookies, and bot-associated fingerprints across sessions. **Fix**: wipe profile (preserve `_rmn_fingerprint/`), re-warm with `scripts/setup_walmart_fresh_profile.py`.

5. **Press-and-hold captcha solve** — old implementation used 10-step straight-line mouse move + separate pre-click + perfectly static cursor during hold + fixed timer. All detectable. **Fix**: Bezier approach, no pre-click, micro hand-tremor drift (±2.5px) during hold, release on completion signal.

**Step log confirmation**: look for `px_vid_cookie_cleared_fresh` on each KW — should show `['_pxvid', '_pxde']` being removed. No `px_trip` or `scroll_blocked` events = clean run.

## Overview

Walmart uses **PerimeterX (PX)** + **Akamai Bot Manager** — two of the most sophisticated bot detection systems working in tandem. They use machine learning on multiple signals to calculate a **cumulative trust/risk score** that persists across page loads via the `_px3` cookie. This document details our implementation, known triggers, and forensic methodology.

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
  - Typing method (`element.type()` vs real keyboard events)
  - Timing between typing and submission
  - Mouse position during submission
  - Focus state of search box
- **Our implementation** (updated 2026-03-24):
  - ✅ `page.keyboard.press()` per-character typing (dispatches real KeyDown/KeyPress/KeyUp events)
  - ✅ Variable keystroke delays (80-220ms) with occasional longer pauses
  - ✅ `page.keyboard.press("Enter")` for submit (not `element.press()`)
  - ✅ Search button click as primary submit, Enter as fallback
  - ✅ Dwell time (1.5-3.5s) between login check and search box interaction
  - ✅ Post-type dwell (0.6-1.2s) before submission
  - ✅ No programmatic `/search?q=` URL navigation — only organic form submission

### 6. Page Evaluation Timing (CDP Fingerprint)
- **What they check**:
  - Number and frequency of `Runtime.evaluate` CDP calls
  - Immediate page.evaluate() calls after navigation
  - Evaluation context lifecycle
- **Our implementation** (updated 2026-03-24):
  - ✅ **Consolidated diagnostics**: 5 separate `page.evaluate()` calls merged into 1 (UA, WebGL vendor, WebGL unmasked, navigator diag, WebGL renderer — all in single eval)
  - ✅ eval_safe wrapper prevents crashes
  - ✅ Bail-on-blocked check before evals
  - ✅ Post-transition settle pause (0.8-1.5s) before any DOM/cookie queries
  - ✅ No fatal "Page.evaluate:" crashes

## What We've Implemented (Still Being Flagged)

### ✅ Human Behavior Simulation (Updated 2026-03-24)
- **Realistic typing**: `page.keyboard.press()` per-character (real KeyDown/KeyPress/KeyUp events, not synthetic `element.type()`)
- **Variable keystroke delays**: 80-220ms per character with occasional longer pauses
- **Micro-mouse movements**: Subtle attention movements during typing (5-15 steps, ±10px jitter)
- **Drift reading**: Mouse drift during result scanning (2-3 seconds)
- **Back-scroll peek**: 35% chance of scrolling back up briefly
- **Random product hover**: Hover on random product tiles
- **Pre-search dwell**: 1.5-3.5s pause between login check and search box click
- **Post-type dwell**: 600-1200ms pause after typing before submit
- **Post-transition settle**: 0.8-1.5s pause after search navigation before any DOM queries
- **Homepage idle**: 2.0-4.0s idle after homepage load before any interaction
- **Consolidated CDP calls**: 5 diagnostic `page.evaluate()` calls merged into 1 to reduce `Runtime.evaluate` events

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

### ✅ Bail System (Two-Tier with PX Escalation Awareness)
- **Non-retryable detection**: Stops blind retries on px_locked, hard_block, fatal
- **Adapter returns**: `{'ok': bool, 'bail': bool, 'reason': str}`
- **GUI integration**: Stops retrying immediately when bail=True
- **PX escalation bail**: If `main.min.js` or `bundle` POST detected in network traffic, bail immediately before scroll — PX has already decided to challenge server-side
- **Escalation flag reset after homepage solve**: If PX modal appears on the homepage and is successfully solved, escalation flags are cleared so they don’t false-positive during the search phase (bug fix 2026-03-24)
- **Two-tier empty results bail**:
  - **Tier 1**: `results_ready=false` + PX escalation signals → immediate bail (`px_blocked_no_results`)
  - **Tier 2**: `results_ready=false` + no PX signals → extend wait +10s for slow load, then bail (`no_results_timeout`)
- **Pre-scroll gate**: If PX escalation detected after results loaded, bail before unlocking scroll (`px_escalation_pre_scroll`)
- **Search transition**: URL-only detection (`/search` in URL). DOM-based detection was removed because `[data-item-id]` matched homepage product tiles, causing false-positive transitions (bug fix 2026-03-24)
- **Bail reasons**: `px_locked`, `hard_block`, `px_blocked_no_results`, `no_results_timeout`, `px_escalation_pre_scroll`, `px_escalation_after_submit`, `search_submit_no_nav`, `px_on_home_after_recovery`

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

## 🔴 Known Issues & Current Findings

### Finding #1: Cumulative Velocity Scoring (PRIMARY TRIGGER)
**Status**: CONFIRMED via forensic audit (2026-03-24)  
**Symptom**: Sequential searches from the same profile can trigger PX CAPTCHA due to accumulated risk  
**Evidence** (from Garan client runs):

**Morning run** (old profile, pre-behavioral-fixes):

| Run | Keyword | Gap from 1st | `_px3` Cookie | PX Escalation | Result |
|-----|---------|-------------|---------------|---------------|--------|
| 1 | Garanimals | — | Not present | None | ✅ Success |
| 2 | toddler clothes | 81s | Present | None | ✅ Success |
| 3 | kids clothes | 167s | Present (updated) | `main.min.js` + `bundle` POST + iframe | ❌ CAPTCHA |
| 4 | community coffee | 462s (scheduler) | Present | None | ✅ Success |

**Afternoon run** (fresh profile, pre-behavioral-fixes — GUI hadn't restarted to pick up new code):

| Run | Keyword | Gap from 1st | PX on Homepage | PX on Search | Result | Notes |
|-----|---------|-------------|----------------|--------------|--------|-------|
| 1 | Garanimals | — | ✅ Solved | Stale flags → false bail | ❌ BAIL | **Bug: escalation flags not reset after homepage solve** |
| 2 | toddler clothes | 87s | None | None | ✅ Success | 2 ads, 47 listings |
| 3 | kids clothes | 219s | None | None | ✅ Success | 1 ad, 52 listings |
| 4 | toddler clothes clearance | 352s | None | Escalated immediately | ❌ BAIL | PX escalated on search nav; also hit DOM false-positive bug |

**Root Cause**: PX maintains a server-side risk score correlated with the `_px3` cookie. Each search from the same profile increments the score. PX's decision to challenge is made **server-side during the search navigation** — before any scroll, before any DOM interaction.

**Key Insight**: The scroll did NOT trigger the CAPTCHA. PX had already decided to challenge when `main.min.js` loaded. Results were withheld, then code proceeded to scroll, giving PX a DOM event to attach the modal to.

**Mitigations Implemented**:
- [x] Inter-keyword cooldown (45s minimum between keywords in GUI)
- [x] PX escalation detection (`main.min.js` / `bundle` POST network signals)
- [x] Two-tier bail on empty results with PX awareness
- [x] Pre-scroll PX escalation gate (bail before unlocking scroll)
- [x] Module state reset between GUI keyword runs
- [x] Escalation flag reset after successful homepage CAPTCHA solve (2026-03-24 fix)

### Finding #2: PX Escalation Signals (Early Warning System)
**Status**: IMPLEMENTED (2026-03-24)  
**Discovery**: PX uses a two-phase approach:
1. **Standard telemetry** (every page): `collector-pxu6b0qd2s.px-cloud.net` POST — behavioral data collection. Present on ALL pages, even successful ones.
2. **Challenge enforcement** (only when challenging): `client.px-cloud.net/.../main.min.js` GET + `collector .../assets/js/bundle` POST + `px-iframe` injection. Only appears when PX has **already decided** to challenge.

If you see `main.min.js` load after search navigation → PX has decided to challenge. Results will be withheld. CAPTCHA modal is queued. **Bail immediately — no action will prevent the challenge.**

### Finding #3: Scheduler vs GUI Structural Difference
**Status**: UNDERSTOOD  
**Why scheduler succeeds after GUI gets CAPTCHA'd**:

The scheduler runs each keyword as a **separate subprocess** (`subprocess.Popen`). This means:
- Fresh Python process → fresh module globals, fresh PX state
- New TCP connections → new source port range, new TLS sessions
- New PX collector session → PX sees a "returning user," not a "bot hammering"
- Natural time gap between keywords (process startup overhead)

The GUI runs keywords **sequentially in the same process**:
- Same module state carried across keywords (now fixed with `_reset_run_state()`)
- Same OS network state, same TCP port range
- Minimal gap between keywords (now fixed with 45s cooldown)

### Finding #4: `_px3` Cookie — PX Risk Score Carrier
**Status**: MONITORED  
The `_px3` cookie carries PX's cumulative risk score across page loads and sessions. It persists in the Chrome profile on disk.
- **Absent** on first-ever visit → PX evaluates fresh (low risk)
- **Present** after first visit → PX starts from accumulated score
- **Updated** after each interaction → risk score can increase or decrease
- **High-entropy value** (long string) suggests accumulated evaluation data

We now log `_px3` presence, value length, and expiry at the start of every run for forensic visibility.

### Finding #5: Stale PX Escalation Flags After Homepage Solve (BUG FOUND & FIXED)
**Status**: FIXED (2026-03-24 afternoon)  
**Symptom**: KW1 (Garanimals) bailed on search even though the homepage CAPTCHA was successfully solved  
**Root Cause**: When PX challenged on the homepage, the network listener set `main_js_seen=True` and `bundle_post_seen=True`. After solving the CAPTCHA successfully, those flags were **never reset**. When the search was submitted and `_wait_for_search_results` polled, it saw the stale flags and exited early with `px_escalation_early_exit` — a **false positive bail**.  
**Fix**: Reset `PX_ESCALATION` flags (`main_js_seen`, `bundle_post_seen`, `escalation_ts`) immediately after `_solve_px_until_clear` returns True on the homepage. Added `px_escalation_reset` log event for forensic visibility.  
**File**: `walmart_search_and_capture.py` ~line 3036-3043  
**Timeline from step log**:
```
t=9.6s   PX modal on homepage
t=10.0s  main.min.js + bundle_post flags set    ← escalation flags
t=11.8s  Press-and-hold solve (7.95s)
t=26.1s  ✅ "Unblocked on homepage"               ← flags NOT reset (bug)
t=36.7s  Submit → nav to /search?q=Garanimals
t=36.8s  _wait_for_search_results → sees stale flags → EARLY EXIT
t=37.2s  BAIL: px_blocked_no_results              ← FALSE POSITIVE
```

### Finding #6: DOM False-Positive in Search Transition Detection (BUG FOUND & FIXED)
**Status**: FIXED (2026-03-24 afternoon)  
**Symptom**: KW4 (toddler clothes clearance) returned `button:dom` transition while still on homepage URL  
**Root Cause**: `_wait_for_search_transition()` checked `RESULT_READY_SELECTORS` as a fallback alongside URL matching. The selector `[data-item-id]` matches **homepage product recommendation tiles** — not just search results. After clicking the search button, the function found `[data-item-id]` on the homepage and returned `"dom"` before the SPA had actually navigated to `/search`. The code then thought it was on the search results page but was still on the homepage.  
**Fix**: Removed DOM selector fallback entirely from `_wait_for_search_transition()`. Now it only waits for `/search` to appear in the URL, which is the reliable signal for SPA navigation.  
**File**: `walmart_search_and_capture.py` ~line 2067-2085  
**Impact**: Without this fix, the scraper entered the wrong post-submit path ("Post-PX recovery: idling on home"), wasted time, and then hit PX escalation when the delayed search navigation finally occurred.

### Issue #7 (RESOLVED): Search Submission Triggers Immediate Block
**Status**: RESOLVED (was blocking in Oct 2025, fixed by Nov 2025)  
**Root Cause Was**: `search_box.press("Enter")` → replaced with `page.keyboard.press("Enter")` + proper focus/blur + mouse movement to search button + variable dwell times.
**Current State**: Search submission works reliably. The remaining trigger is velocity scoring (Finding #1), not submission mechanics.

### Issue #8 (RESOLVED): webdriver=True
**Status**: RESOLVED  
**Fix**: `ignore_default_args=['--enable-automation']` + `channel='chrome'` (real Chrome). Verified via `navigator_diag` in step logs.

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

**Keystroke Timing** (updated 2026-03-24 — uses real keyboard events):
```python
# Per-character page.keyboard.press() dispatches real KeyDown/KeyPress/KeyUp
# Unlike element.type(), this is indistinguishable from physical keypresses
for char in keyword:
    page.keyboard.press(char)
    time.sleep(random.uniform(0.08, 0.22))  # 80-220ms per key
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

## Fresh Profile: Complete Walkthrough

### Why a fresh profile matters

PX tracks trust/risk via the `_px3` cookie and other state stored in the Chrome profile. A profile that has accumulated PX challenges, failed CAPTCHAs, or suspicious cookies starts every new run at a **higher risk score**. A fresh profile begins with a clean slate.

### How the profile flows through the system

```
~/.zshrc                          # WALMART_PROFILE_DIR env var (persists across shells)
  └─> keyword_input.py (GUI)      # reads env var at startup → ctx.profile_dir
       └─> walmart/adapter.py     # passes ctx.profile_dir to core scraper
            └─> walmart_search_and_capture.py  # _launch() opens Chrome with user_data_dir=profile_dir
```

**Key implication**: The GUI reads `WALMART_PROFILE_DIR` **once at startup**. If you change the env var or the profile, you must **restart the GUI** for the change to take effect.

The scraper's `_launch()` function also creates a `_rmn_fingerprint/` subdirectory inside the profile to store a stable viewport size and timezone. These are generated on the first scrape run and reused on subsequent runs so PX sees a consistent fingerprint.

### Step-by-step: Create and activate a fresh profile

#### Step 1: Run the setup script

```bash
.venv/bin/python3 scripts/setup_walmart_fresh_profile.py
```

**What the script automates:**
1. Creates a timestamped profile directory: `~/ChromeProfiles/walmart_fresh_YYYYMMDD_HHMMSS`
2. Launches Chrome with **identical** args to the main scraper (`--use-angle=metal`, `chromium_sandbox=True`, `channel='chrome'`, `ignore_default_args=['--enable-automation']`, `navigator.webdriver=undefined`)
3. Navigates to walmart.com — prompts you to solve CAPTCHA if PX challenges
4. Performs organic browsing: homepage scroll, 1-2 product searches with clicks, back navigation
5. Prompts for manual login (recommended — enables SBA/SBV ad capture)
6. Verifies profile on disk (Cookies, Preferences, Network Persistent State)
7. **Automatically updates `~/.zshrc`** — removes old `WALMART_PROFILE_DIR` entries, writes the new one
8. Sets `WALMART_PROFILE_DIR` in the current process (for any child processes)

You can also pass a custom name:
```bash
.venv/bin/python3 scripts/setup_walmart_fresh_profile.py walmart_march_clean
```

#### Step 2: Source your shell (required)

The setup script updates `~/.zshrc` but your **current terminal session** still has the old value. Apply it:

```bash
source ~/.zshrc
```

Verify it took effect:
```bash
echo $WALMART_PROFILE_DIR
# Should print: /Users/<you>/ChromeProfiles/walmart_fresh_YYYYMMDD_HHMMSS
```

#### Step 3: Restart the GUI (required)

The GUI loads Python modules and reads env vars **at startup**. A running GUI will not pick up the new profile or any code changes.

```bash
# Close the existing keyword_input.py window, then:
.venv/bin/python3 keyword_input.py
```

#### Step 4: Run a test scrape

Pick any Walmart client keyword and run a single keyword scrape. Check the step log for:
- `profile_dir` should show the fresh path
- `px_escalation` events (should be absent on a fresh profile)
- `results_ready: true` with product listings

### Verify an existing profile

To check the health of the currently configured profile without creating a new one:

```bash
.venv/bin/python3 scripts/setup_walmart_fresh_profile.py --verify
```

This checks:
- `WALMART_PROFILE_DIR` env var is set
- Profile directory exists on disk
- Cookies, Preferences, Network Persistent State files present and non-empty
- `~/.zshrc` value matches the current env var
- `_rmn_fingerprint/` viewport and timezone files (created on first scrape run)

### When to create a fresh profile

- **Profile is getting PX challenged on every keyword** → accumulated risk, time for a fresh start
- **Login expired** → re-login via the scraper's built-in `prompt_relogin` is easier, but if it fails, create a fresh profile and log in during setup
- **After major code changes to launch args** → fingerprint consistency requires the profile to be warmed up with the same Chrome args the scraper uses
- **New machine or team member** → each machine needs its own profile

### Common pitfalls

| Symptom | Cause | Fix |
|---------|-------|-----|
| Scraper uses old profile path | GUI wasn't restarted | Close and relaunch `keyword_input.py` |
| `echo $WALMART_PROFILE_DIR` shows old path | Shell not sourced | `source ~/.zshrc` |
| Profile dir "not found" error | Env var points to deleted dir | Run setup script again |
| PX challenges on first keyword with fresh profile | CAPTCHA wasn't solved during setup | Re-run setup, solve the CAPTCHA when prompted |
| `--no-sandbox` banner visible | `chromium_sandbox` not set | Already fixed in setup script; verify you're using the latest version |
| WebGL shows SwiftShader | GPU args missing | Already fixed in setup script; verify `--use-angle=metal` in launch |

### Configure proxy (optional)

```bash
export WALMART_PROXY_SERVER="http://residential-proxy.com:8080"
export WALMART_PROXY_USERNAME="user"
export WALMART_PROXY_PASSWORD="pass"
```

### Run a scrape

```bash
.venv/bin/python3 keyword_input.py
# Select Walmart retailer
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

### Current Status (As of 2026-03-24)

**Scraper is operational.** Homepage loads reliably, search submission works, and results are captured successfully on most keywords. The primary remaining risk is **cumulative velocity scoring** — PX challenges after rapid sequential searches from the same profile. Two critical bugs (stale escalation flags, DOM false-positive transition) were fixed on 2026-03-24 and await testing with a GUI restart.

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
# Check current profile health
.venv/bin/python3 scripts/setup_walmart_fresh_profile.py --verify

# Create a fresh profile (preferred — builds organic browsing history)
.venv/bin/python3 scripts/setup_walmart_fresh_profile.py

# After setup, apply to current shell + restart GUI:
source ~/.zshrc
# Close keyword_input.py, then relaunch
```

See the **"Fresh Profile: Complete Walkthrough"** section above for full details.

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

## Current Priorities (as of 2026-03-24 afternoon)

### 🔴 Priority 1: Restart GUI and Test with All Fixes
- **All code changes from today require a GUI restart** to take effect
- The last 4-keyword test run used **stale code** (GUI was already running when fixes were saved)
- Fixes pending validation:
  - Stale PX escalation flag reset after homepage solve (Finding #5)
  - DOM false-positive transition fix (Finding #6)
  - Consolidated `page.evaluate()` (5→1 call)
  - `page.keyboard.press()` per-character typing
  - Pre-search dwell time (1.5-3.5s)
  - Post-transition settle pause (0.8-1.5s)
- Fresh profile is ready: `$WALMART_PROFILE_DIR` points to `~/ChromeProfiles/walmart_fresh_*`
- **Test command**: Restart `keyword_input.py`, run Garan client (4 keywords)

### 🟡 Priority 2: Build Walmart Step-by-Step Isolation Test
- Port `tools/kroger_step_by_step_test.py` to Walmart-specific version
- Test each step independently: homepage → search_box → type → submit → results
- Include PX escalation detection at each step
- Include `_px3` cookie logging between steps
- Use to re-validate after any scraper changes

### 🟠 Priority 3: Tune Inter-Keyword Cooldown
- Currently set to 45s minimum between keywords in GUI mode
- May need increase to 60-90s if PX continues to challenge on 3rd keyword
- Monitor `px_escalation` events in step logs to calibrate
- Scheduler subprocess isolation naturally provides longer gaps

### 🟠 Priority 4: Profile Rotation / Multi-Profile Support
- Single profile accumulates `_px3` risk across all runs
- Multiple authenticated profiles would distribute risk
- Consider profile-per-client or profile-per-keyword-group
- Manual login required per profile (PX detects automated login flows)

### 🟢 Priority 5: `_px3` Cookie Management
- Monitor `_px3` value length growth across runs (correlates with risk)
- Consider clearing `_px3` between runs if risk consistently exceeds threshold
- Test: does deleting `_px3` between runs reduce CAPTCHA rate?
- Risk: PX may treat missing `_px3` as suspicious (new session on established profile)

### ✅ RESOLVED: Behavioral Hardening (March 24, 2026)
- Switched typing from `element.type()` to `page.keyboard.press()` (real keyboard events)
- Consolidated 5 diagnostic `page.evaluate()` calls into 1 (reduces CDP fingerprint)
- Added dwell times between login check and search box interaction
- Added post-transition settle pauses before DOM queries
- Fixed homepage PX escalation flag leak (Finding #5)
- Fixed DOM false-positive in search transition (Finding #6)

### ✅ RESOLVED: Search Submission (was Priority 1 in Oct 2025)
- Fixed by switching to `page.keyboard.press("Enter")` with proper focus/blur
- Added mouse movement to search button, variable dwell times
- Removed programmatic `/search?q=` navigation fallback

## Forensic Methodology: Analyzing PX Triggers

When a CAPTCHA or bail occurs, use this process to determine the root cause:

### 1. Locate the step log
```bash
# Find latest run's step log
ls -lt output/walmart/*/runs/*/walmart_*_steps.jsonl | head -5
```

### 2. Check for PX escalation signals
```bash
# Look for main.min.js (challenge enforcement script)
grep "main.min.js" <steps.jsonl>

# Look for bundle POST (challenge telemetry)
grep "bundle" <steps.jsonl>

# Look for px-iframe injection
grep "px-iframe" <steps.jsonl>
```

**If these appear**: PX decided to challenge server-side. The trigger is cumulative velocity, not any specific action. Check timing between this run and previous runs.

**If these are absent**: The run was not challenged by PX. Any bail was due to slow load or hard block, not CAPTCHA.

### 3. Check `_px3` cookie state
```bash
# Look for px3_cookie log entry
grep "px3_cookie" <steps.jsonl>
```
- `present: true` with high `value_len` → accumulated risk from prior runs
- `present: false` → fresh session, low risk

### 4. Compare PX network events across runs
For each run, extract the PX response timeline:
```bash
grep "px_resp\|px_escalation\|results_ready" <steps.jsonl> | jq -r '[.elapsed_ms, .event, .url // .ready // ""] | @tsv'
```

**Successful run pattern**: Only `collector` POSTs → `results_ready: true`
**Failed run pattern**: `collector` POSTs → `main.min.js` GET → `bundle` POST → `px-iframe` → `results_ready: false`

### 5. Check bail reason in run report
```bash
cat output/walmart/*/runs/*/run_report.json | jq '.outcome, .bail_reason'
```

Bail reasons and their meanings:
- `px_locked` — PX modal appeared, solver failed after max attempts
- `hard_block` — Redirected to /blocked
- `px_blocked_no_results` — PX escalation detected + no results loaded
- `no_results_timeout` — No PX signals but results never loaded (slow/error)
- `px_escalation_pre_scroll` — PX escalation detected before scroll unlock
- `px_escalation_after_submit` — PX modal + escalation signals after search submit
- `px_on_home_after_recovery` — Still on homepage after PX recovery attempt
- `search_submit_no_nav` — No navigation after button click / Enter

### Key files in the codebase
| File | Purpose |
|------|---------|
| `walmart_search_and_capture.py` | Core scraper, PX detection, bail logic, scroll gating |
| `keyword_input.py` | GUI runner, inter-keyword cooldown |
| `scheduler_daemon.py` | Scheduler (subprocess per keyword) |
| `retailers/walmart/adapter.py` | Adapter wrapping core scraper for GUI/scheduler |
| `scripts/setup_walmart_fresh_profile.py` | Fresh profile creator (organic browsing + login prompt) |
| `tools/kroger_step_by_step_test.py` | Step isolation test (port to Walmart pending) |
| `debug_walmart_preflight.py` | Preflight check tester |
| `view_debug_logs.py` | Step log analyzer |
| `tools/scrape_monitor.py` | Coverage and health monitor |

## See Also

- `docs/WALMART_PROXY_SETUP.md` - Proxy configuration guide
- `docs/reference/Walmart_ad_html.md` - Ad selectors
- `scripts/manual_walmart_setup.py` - Legacy profile setup
- `scripts/setup_walmart_fresh_profile.py` - Fresh profile setup (preferred)
- `walmart_search_and_capture.py` - Main implementation
- `view_debug_logs.py` - Analyze steps.jsonl files
- `tools/kroger_step_by_step_test.py` - Step isolation test (Kroger, template for Walmart port)
