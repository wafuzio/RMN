# Kroger Scraper Testing Plan - Clean IP Required

**Created:** March 7, 2026  
**Status:** Ready to Execute  
**Prerequisite:** Clean IP (not 136.62.204.180)

---

## Overview

This document outlines the testing procedure for the Kroger scraper after all HAR analysis fixes have been applied. The scraper is configured correctly but blocked due to IP reputation from repeated testing.

---

## Pre-Test Requirements

### 1. Clean IP Address

**Current Burned IP:** `136.62.204.180`

**Options for Clean IP:**

**Option A: VPN (Fastest)**
```bash
# Connect to VPN in different region
# Verify new IP:
curl -s https://api.ipify.org
```

**Option B: Different Network**
- Mobile hotspot
- Coffee shop WiFi
- Friend's network
- Office network (if different)

**Option C: Wait for Cooldown**
- Duration: 24-48 hours
- No Kroger testing from current IP during cooldown

**Option D: Residential Proxy**
- More sustainable for ongoing scraping
- Rotates IPs automatically

### 2. Profile Verification

**Profile Path:** `~/ChromeProfiles/kroger_playwright_profile`

**Verify Profile Exists:**
```bash
ls -la ~/ChromeProfiles/kroger_playwright_profile/Default/Cookies
```

**Expected:** Cookie file should exist with size > 0

**If Missing:** Re-run manual login:
```bash
/Users/dan.maguire/Library/Caches/ms-playwright/chromium-1208/chrome-mac-arm64/Google\ Chrome\ for\ Testing.app/Contents/MacOS/Google\ Chrome\ for\ Testing \
  --user-data-dir=/Users/dan.maguire/ChromeProfiles/kroger_playwright_profile \
  --no-first-run \
  --password-store=basic \
  https://www.kroger.com
```

Then:
1. Browse naturally for 30-60 seconds
2. Log in to Kroger account
3. Browse for another 20-30 seconds
4. Close browser

### 3. Environment Check

**Kill Any Running Chrome Processes:**
```bash
pkill -f "Chrome for Testing"
pkill -f "kroger_search_and_capture"
```

**Verify Python Environment:**
```bash
.venv/bin/python3 --version  # Should be 3.11+
.venv/bin/playwright --version  # Should be 1.58.0
```

---

## Test Procedure

### Test 1: Basic Homepage Load

**Purpose:** Verify no immediate IP-based blocking

**Command:**
```bash
.venv/bin/python3 -c "
from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir='/Users/dan.maguire/ChromeProfiles/kroger_playwright_profile',
        headless=False
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://www.kroger.com/')
    time.sleep(5)
    
    title = page.title()
    url = page.url
    
    print(f'Title: {title}')
    print(f'URL: {url}')
    
    if 'Access Denied' in title:
        print('❌ BLOCKED - IP still burned')
    elif 'kroger.com' in url.lower():
        print('✅ SUCCESS - Homepage loaded')
    else:
        print(f'⚠️ UNEXPECTED - Check manually')
    
    input('Press Enter to close...')
    ctx.close()
"
```

**Expected Result:**
- ✅ Homepage loads without "Access Denied"
- ✅ Title contains "Kroger" or similar
- ✅ URL is `https://www.kroger.com/`

**If Blocked:**
- IP is still burned or new detection issue
- Wait longer or try different IP

### Test 2: Full Scraper Run

**Purpose:** Test complete scrape with all fixes applied

**Command:**
```bash
.venv/bin/python3 kroger_search_and_capture.py --search "black forest ham"
```

**Monitor Output For:**
1. Browser launch (should be ~3-5 seconds)
2. Google.com pre-navigation
3. `webdriver=False` in diagnostics
4. Homepage load without "Access Denied"
5. Search execution
6. Product capture

**Expected Success Output:**
```
✅ Launched persistent context using profile: /Users/dan.maguire/ChromeProfiles/kroger_playwright_profile
[  ~3000ms] browser_launched: pages=1
[  ~5000ms] navigator_collected: checkpoint=before_navigation, webdriver=False
[  ~5500ms] homepage_loaded: url=https://www.kroger.com/
[  ~8000ms] No Akamai block detected
[  ~15000ms] search_submitted
[  ~20000ms] products_captured: count=XX
✅ SEARCH AND CAPTURE SUCCEEDED
```

**Expected Failure Indicators:**
```
❌ akamai_block_detected: reason=access_denied_title
❌ SEARCH AND CAPTURE FAILED
```

### Test 3: Diagnostic Review

**Location:** `output/diagnostics_YYYYMMDD_HHMMSS/`

**Check Files:**

**1. Diagnostic Report (`diagnostic_report.md`):**
```bash
cat output/diagnostics_*/diagnostic_report.md | grep -A 5 "Akamai"
```

**Expected:** No blocking signals

**2. Screenshots:**
```bash
ls -lh output/diagnostics_*/
```

**Expected:** 
- `main_screenshot.png` - Should show search results
- No `blocked_at_homepage_screenshot.png`

**3. HTML Captures:**
```bash
grep -l "Access Denied" output/diagnostics_*/*.html
```

**Expected:** No matches (no Access Denied pages)

---

## Success Criteria

### ✅ Complete Success
- [ ] Browser launches without errors
- [ ] Google.com pre-navigation completes
- [ ] `webdriver=False` in diagnostics
- [ ] Homepage loads without "Access Denied"
- [ ] Login detected (if logged in)
- [ ] Search executes successfully
- [ ] Products captured (ads array not empty)
- [ ] No blocking signals in diagnostic report

### ⚠️ Partial Success
- [ ] Homepage loads but search fails → Behavioral detection
- [ ] Products load but no ads → Ad detection issue
- [ ] Slow performance but works → Optimization needed

### ❌ Failure
- [ ] "Access Denied" on homepage → IP still burned or new detection
- [ ] Browser crashes → Chrome args incompatibility
- [ ] `webdriver=True` in diagnostics → Init script failed
- [ ] Empty results → Complete blocking

---

## Troubleshooting Guide

### Issue: "Access Denied" on Homepage

**Possible Causes:**
1. IP still burned (most likely)
2. Profile flagged
3. New detection vector

**Actions:**
1. Verify IP is different: `curl -s https://api.ipify.org`
2. Try from completely different network
3. Create fresh profile and re-login
4. Check if manual browsing works from same IP

### Issue: webdriver=True in Diagnostics

**Possible Causes:**
1. Google.com pre-navigation failed
2. Init script not executing

**Actions:**
1. Check browser launch logs for errors
2. Verify google.com navigation in output
3. Add longer wait after google.com load

### Issue: Search Fails But Homepage Loads

**Possible Causes:**
1. Behavioral detection during search
2. Search box selector changed
3. Timing issue

**Actions:**
1. Review diagnostic screenshots
2. Check search box detection in logs
3. Increase dwell times

### Issue: Products Load But No Ads

**Possible Causes:**
1. Ad detection working differently
2. No ads for search term
3. Ad extraction logic issue

**Actions:**
1. Try different search term
2. Check HTML capture for ad elements
3. Review ad extraction selectors

---

## Rollback Plan

If testing reveals new issues, rollback to known configuration:

### Revert to System Chrome (If Needed)

**File:** `kroger_search_and_capture.py`

**Change:**
```python
# Line ~530
candidates = [
    {"user_data_dir": USER_DATA_DIR, "channel": "chrome"},  # Use system Chrome
]
```

**Note:** This may reintroduce CDP protocol issues with Chrome 145

### Revert to Old Profile (If Needed)

**File:** `kroger_search_and_capture.py`

**Change:**
```python
# Line ~44
USER_DATA_DIR = os.path.expanduser("~/ChromeProfiles/kroger_clean_profile")
```

**Note:** Old profile has cookies from system Chrome 145.0.7632.160

---

## Data Collection

### Successful Test Data to Capture

**1. Diagnostic Report:**
```bash
cp output/diagnostics_*/diagnostic_report.md docs/kroger_akamai/SUCCESSFUL_RUN_DIAGNOSTICS.md
```

**2. Configuration Snapshot:**
```bash
# Save exact configuration that worked
git log -1 --oneline > docs/kroger_akamai/WORKING_CONFIG_COMMIT.txt
```

**3. IP Address:**
```bash
echo "Working IP: $(curl -s https://api.ipify.org)" >> docs/kroger_akamai/WORKING_CONFIG.txt
```

**4. Browser Flags:**
```bash
# During test, capture actual flags:
ps aux | grep "Chrome for Testing" | grep -v grep > docs/kroger_akamai/WORKING_CHROME_FLAGS.txt
```

---

## Post-Success Actions

### 1. Document Working Configuration

Create `docs/kroger_akamai/WORKING_CONFIGURATION.md` with:
- IP address (or IP range if using proxy)
- Profile path and age
- Browser version
- All launch args
- Timing parameters
- Success rate

### 2. Establish Baseline

Run 5 consecutive successful scrapes to establish:
- Average runtime
- Consistency of results
- Ad capture rate
- Any intermittent issues

### 3. Schedule Regular Testing

**Frequency:** Once every 5 minutes (existing schedule)

**Monitor:**
- Success rate over 24 hours
- Any new blocking patterns
- Performance degradation

### 4. Update Memory

Create memory with:
- Working configuration
- IP requirements
- Profile maintenance needs
- Known issues and solutions

---

## Alternative Approaches (If Still Blocked)

### Option 1: Selenium with Undetected ChromeDriver

**Pros:**
- Different automation framework
- May have different fingerprint

**Cons:**
- Major code rewrite
- May have same issues

### Option 2: Puppeteer (Node.js)

**Pros:**
- Native Chrome DevTools Protocol
- Potentially cleaner fingerprint

**Cons:**
- Different language
- Code migration required

### Option 3: Manual Capture + Processing

**Pros:**
- Guaranteed to work
- No automation detection

**Cons:**
- Not scalable
- Labor intensive

### Option 4: API Reverse Engineering

**Pros:**
- No browser needed
- Faster and more reliable

**Cons:**
- Requires extensive analysis
- May need to solve CAPTCHA
- APIs may be protected

---

## Contact Points

**If Testing Succeeds:**
- Document configuration in `WORKING_CONFIGURATION.md`
- Update `EXECUTIVE_SUMMARY.md` with success
- Resume scheduled scraping

**If Testing Fails:**
- Capture diagnostic output
- Document failure mode
- Consider alternative approaches
- May need to wait longer for IP cooldown

---

## Timeline Estimate

**Minimum Time:** 15 minutes
- 5 min: Setup and verification
- 5 min: Test execution
- 5 min: Result analysis

**Maximum Time:** 48 hours
- If IP cooldown needed
- Plus setup and testing time

**Recommended:** Test immediately from different IP if available, otherwise wait 24 hours.
