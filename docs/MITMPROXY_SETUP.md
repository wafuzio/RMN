# mitmproxy Setup Guide for Retailer Scraping

## What is mitmproxy?

**mitmproxy** is an interactive HTTPS proxy that lets you intercept, inspect, modify, and replay web traffic. It's invaluable for debugging retailer bot detection by showing you:

- **Exact HTTP requests/responses** - Headers, cookies, POST data
- **TLS fingerprints** - What the server sees from your browser
- **Blocked requests** - Which requests trigger anti-bot systems
- **Cookie evolution** - How PerimeterX/Akamai cookies change
- **API calls** - Hidden XHR/fetch requests to bot detection endpoints

## Why Use It?

When a scraper gets blocked, mitmproxy helps you:
1. **See the block signal** - Is it a redirect? A 403? A CAPTCHA page?
2. **Identify detection vectors** - Which request triggered the block?
3. **Compare good vs bad sessions** - What changed between working and blocked?
4. **Debug TLS fingerprints** - Does your browser match the User-Agent?
5. **Analyze bot detection APIs** - PerimeterX, Akamai, DataDome endpoints

---

## Installation

### Option 1: Homebrew (macOS)
```bash
brew install mitmproxy
```

### Option 2: pip (All platforms)
```bash
.venv/bin/pip install mitmproxy
```

### Verify Installation
```bash
mitmproxy --version
# Should show: Mitmproxy 10.x.x
```

---

## Basic Usage

### 1. Start mitmproxy
```bash
mitmproxy -p 8080
```

This starts an interactive proxy on port 8080. You'll see a terminal UI.

### 2. Configure Your Scraper to Use the Proxy

Add proxy configuration to your scraper's Playwright launch options:

```python
# Example: walmart_search_and_capture.py
browser = p.chromium.launch(
    channel="chrome",
    headless=False,
    proxy={
        "server": "http://127.0.0.1:8080"  # mitmproxy
    }
)
```

### 3. Install mitmproxy Certificate

**First time only:** Install mitmproxy's CA certificate so it can intercept HTTPS.

1. Start mitmproxy: `mitmproxy -p 8080`
2. Configure browser to use proxy (see step 2)
3. Navigate to: `http://mitm.it`
4. Download and install the certificate for your OS
5. **macOS**: Open Keychain Access → System → Find "mitmproxy" → Trust → Always Trust

### 4. Run Your Scraper
```bash
.venv/bin/python3 walmart_search_and_capture.py --search "coffee"
```

All traffic will flow through mitmproxy and appear in the terminal UI.

---

## mitmproxy Interface

### Navigation
- **↑/↓** - Navigate through requests
- **Enter** - View request/response details
- **Tab** - Switch between Request/Response/Detail tabs
- **q** - Back/Quit
- **/** - Search/filter

### Useful Filters
```bash
# Only show walmart.com requests
~d walmart.com

# Only show blocked/error responses
~c 4xx | ~c 5xx

# Show POST requests (form submissions, API calls)
~m POST

# Show requests to PerimeterX/Akamai
~d perimeterx | ~d akamai

# Combine filters
~d walmart.com & ~c 4xx
```

### Keyboard Shortcuts
- **e** - Edit request (before replay)
- **r** - Replay request
- **f** - Set filter
- **z** - Clear current flow
- **E** - Export flow to file

---

## Common Debugging Workflows

### 1. Identify Block Signal

**Scenario:** Scraper gets blocked, you want to see what happened.

```bash
# Start mitmproxy
mitmproxy -p 8080

# In scraper code, add proxy
browser = p.chromium.launch(
    channel="chrome",
    proxy={"server": "http://127.0.0.1:8080"}
)

# Run scraper
.venv/bin/python3 walmart_search_and_capture.py --search "coffee"
```

**In mitmproxy:**
1. Filter for walmart: `~d walmart.com`
2. Look for:
   - **302 redirects** to `/blocked` or `/robot_check`
   - **403 Forbidden** responses
   - **HTML with "Access Denied"** or "Unusual Activity"
   - **CAPTCHA pages** (look for "px-captcha" or "challenge")

### 2. Compare Working vs Blocked Sessions

**Scenario:** Scraper worked yesterday, blocked today. What changed?

```bash
# Capture working session (if you have one)
mitmproxy -p 8080 --save-stream-file working.mitm

# Capture blocked session
mitmproxy -p 8080 --save-stream-file blocked.mitm

# Compare offline
mitmweb -r working.mitm   # Opens in browser
mitmweb -r blocked.mitm
```

**Look for differences in:**
- Request headers (User-Agent, sec-ch-ua, Accept-Language)
- Cookie values (especially `_pxvid`, `_px3`, `ak_bmsc`, `bm_sz`)
- Request timing (too fast = bot)
- Missing requests (images, fonts, CSS not loading)

### 3. Analyze PerimeterX/Akamai Cookies

**Scenario:** Want to see how bot detection cookies evolve.

```bash
# Start with filter for cookie-setting responses
mitmproxy -p 8080

# In UI, filter for Set-Cookie headers
~h Set-Cookie
```

**Watch for:**
- **PerimeterX cookies**: `_pxvid`, `_px3`, `_px2`, `pxcts`
- **Akamai Bot Manager**: `ak_bmsc`, `bm_mi`, `bm_sv`, `bm_sz`, `abck`
- **Poisoned cookies**: Look for `adblocked`, `captcha`, `challenge` in values

**Example of a blocked cookie:**
```
Set-Cookie: _px3=abc123...; Path=/; Domain=.walmart.com
```
If `_px3` value changes on every request, you're being fingerprinted.

### 4. Debug TLS Fingerprint Mismatch

**Scenario:** Using Chrome User-Agent but server detects Chromium.

```bash
# Start mitmproxy with TLS logging
mitmproxy -p 8080 --set tls_version_client_min=TLS1_2

# In UI, look at first request to walmart.com
# Press Enter → Detail tab → Look for TLS info
```

**Check:**
- **JA3 fingerprint** - Should match real Chrome
- **TLS version** - Should be TLS 1.3 for modern Chrome
- **Cipher suites** - Should match Chrome's order

**If mismatched:**
- You're using Chromium instead of Chrome (`channel='chrome'` missing)
- Or using old Chrome version (update Chrome)

### 5. Find Hidden Bot Detection Endpoints

**Scenario:** Want to see what bot detection APIs are being called.

```bash
# Filter for common bot detection domains
~d perimeterx | ~d akamai | ~d datadome | ~d px-cloud
```

**Common endpoints:**
- `collector-*.perimeterx.net` - PerimeterX telemetry
- `*.akstat.io` - Akamai RUM (Real User Monitoring)
- `tap-nexus.walmart.com` - Walmart's analytics
- `/api/px/xhr` - PerimeterX challenge API

**What to look for:**
- **POST to collector** - Sends browser fingerprint, behavior data
- **Response with `uuid`** - PerimeterX session ID
- **Response with `block`** - You've been flagged

---

## Advanced: Scripting with mitmproxy

### Auto-Save Blocked Requests

Create `~/.mitmproxy/save_blocks.py`:

```python
from mitmproxy import http

def response(flow: http.HTTPFlow) -> None:
    """Save all 403/blocked responses to file"""
    if flow.response.status_code in [403, 429]:
        with open("blocked_responses.txt", "a") as f:
            f.write(f"\n=== {flow.request.url} ===\n")
            f.write(f"Status: {flow.response.status_code}\n")
            f.write(f"Headers: {flow.response.headers}\n")
            f.write(f"Body: {flow.response.text[:500]}\n")
```

Run with:
```bash
mitmproxy -p 8080 -s ~/.mitmproxy/save_blocks.py
```

### Extract All Cookies

```python
from mitmproxy import http

def response(flow: http.HTTPFlow) -> None:
    """Log all Set-Cookie headers"""
    if "Set-Cookie" in flow.response.headers:
        with open("cookies.log", "a") as f:
            for cookie in flow.response.headers.get_all("Set-Cookie"):
                f.write(f"{flow.request.host}: {cookie}\n")
```

---

## Integration with Scrapers

### Walmart Example

```python
# walmart_search_and_capture.py

# Add at top
import os

# In main() or launch section
USE_MITM = os.getenv("USE_MITM_PROXY", "false").lower() == "true"

launch_options = {
    "channel": "chrome",
    "headless": False,
    "args": [...],
}

if USE_MITM:
    launch_options["proxy"] = {"server": "http://127.0.0.1:8080"}
    print("🔍 Using mitmproxy for traffic inspection")

browser = p.chromium.launch(**launch_options)
```

**Usage:**
```bash
# Normal run (no proxy)
.venv/bin/python3 walmart_search_and_capture.py --search "coffee"

# With mitmproxy
USE_MITM_PROXY=true .venv/bin/python3 walmart_search_and_capture.py --search "coffee"
```

### Kroger Example

```python
# kroger_search_and_capture.py

# Same pattern as Walmart
USE_MITM = os.getenv("USE_MITM_PROXY", "false").lower() == "true"

if USE_MITM:
    launch_options["proxy"] = {"server": "http://127.0.0.1:8080"}
```

---

## Troubleshooting

### Certificate Errors

**Problem:** Browser shows "Your connection is not private" or "NET::ERR_CERT_AUTHORITY_INVALID"

**Solution:**
1. Navigate to `http://mitm.it` (not https)
2. Download certificate for your OS
3. Install and trust the certificate
4. Restart browser

### Proxy Connection Refused

**Problem:** Scraper can't connect to proxy

**Solution:**
```bash
# Check if mitmproxy is running
lsof -i :8080

# If not, start it
mitmproxy -p 8080
```

### No Traffic Showing

**Problem:** mitmproxy running but no requests appear

**Solution:**
1. Verify proxy is configured in scraper
2. Check port number matches (8080)
3. Ensure certificate is installed for HTTPS
4. Try HTTP-only site first: `http://example.com`

### Playwright Hangs with Proxy

**Problem:** Browser opens but hangs on navigation

**Solution:**
- mitmproxy certificate not trusted → Install cert
- Firewall blocking localhost:8080 → Check firewall
- Wrong proxy format → Use `http://127.0.0.1:8080` not `localhost:8080`

---

## Real-World Examples

### Example 1: Walmart PerimeterX Block

**Observation in mitmproxy:**
```
POST https://collector-pxu6b0qd2s.perimeterx.net/api/v2/collector
Status: 200 OK
Response: {"uuid":"abc-123","vid":"def-456","action":"c"}
```

**What this means:**
- `action: "c"` = Challenge (CAPTCHA required)
- Your browser fingerprint was flagged
- Check request payload for what data was sent

### Example 2: Kroger Akamai Block

**Observation:**
```
GET https://www.kroger.com/search?query=coffee
Status: 403 Forbidden
Body: Reference #18.7eeb2d17.1234567890.abcdef
```

**What this means:**
- Akamai edge network blocked the request
- Reference number is for Kroger's support (useless for us)
- Check previous requests for what triggered it

### Example 3: TLS Fingerprint Mismatch

**Observation in mitmproxy Detail tab:**
```
TLS Version: TLS 1.2
Cipher: TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256
JA3: 771,4865-4866-4867-49195...
```

**Compare to real Chrome JA3:**
```
JA3: 771,4865-4866-4867-49196...  (different!)
```

**Fix:** Use `channel='chrome'` instead of default Chromium.

---

## Best Practices

1. **Start mitmproxy before running scraper** - Obvious but easy to forget
2. **Use filters liberally** - `~d walmart.com` to reduce noise
3. **Save important sessions** - `--save-stream-file session.mitm`
4. **Compare before/after** - Capture working session as baseline
5. **Watch for cookie changes** - PerimeterX cookies evolve during session
6. **Check timing** - Requests too fast = bot detection
7. **Look for missing resources** - Real browsers load images/CSS/fonts
8. **Export for analysis** - Press `E` to save individual requests

---

## Alternative Tools

### mitmweb (Web UI)
```bash
mitmweb -p 8080
# Opens browser UI at http://127.0.0.1:8081
```

**Pros:** Easier to navigate, better for screenshots  
**Cons:** Higher resource usage

### mitmdump (Command-line)
```bash
mitmdump -p 8080 -w traffic.mitm
# Non-interactive, saves to file
```

**Pros:** Good for automation, CI/CD  
**Cons:** No real-time inspection

### Charles Proxy (Commercial)
- GUI-based, easier for beginners
- $50 one-time purchase
- Better for mobile app debugging

---

## Summary

**mitmproxy is essential for:**
- ✅ Debugging bot detection blocks
- ✅ Analyzing HTTP traffic in detail
- ✅ Comparing working vs broken sessions
- ✅ Understanding PerimeterX/Akamai behavior
- ✅ Validating TLS fingerprints

**Quick start:**
```bash
# Terminal 1: Start proxy
mitmproxy -p 8080

# Terminal 2: Run scraper with proxy
USE_MITM_PROXY=true .venv/bin/python3 walmart_search_and_capture.py --search "test"
```

**Key insight:** The traffic you see in mitmproxy is exactly what the server sees. If it looks robotic to you, it looks robotic to PerimeterX.
