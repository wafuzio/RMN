# Complete PerimeterX Bypass Strategy for Walmart

## Overview

Walmart uses **PerimeterX** - one of the most sophisticated bot detection systems. It uses machine learning on multiple signals to calculate a trust score. This document details our comprehensive bypass strategy.

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

## Troubleshooting

### Still Getting CAPTCHA?

1. **Check GPU**: Must be consumer-grade (Intel Iris, AMD Radeon, NVIDIA GTX)
2. **Check Proxy**: Must be residential, not datacenter
3. **Check Timing**: Delays should be random (80-200ms keystrokes)
4. **Check Profile**: Must be authenticated with fresh cookies
5. **Check Pattern**: Should visit homepage, not direct search

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

## See Also

- `docs/WALMART_PROXY_SETUP.md` - Proxy configuration guide
- `docs/Walmart_ad_html.md` - Ad selectors
- `scripts/manual_walmart_setup.py` - Profile setup
- `walmart_search_and_capture.py` - Main implementation
