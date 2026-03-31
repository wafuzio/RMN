# Kroger Playwright Pre-Flight Checklist

**Date:** March 7, 2026  
**Status:** ✅ READY FOR TESTING

---

## Critical Anti-Detection Measures

### ✅ 1. navigator.webdriver Override
**Location:** `kroger_search_and_capture.py:561-565`

```python
ctx.add_init_script("""
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined
    });
""")
```

**Status:** ✅ Implemented with dummy page workaround (lines 571-575)
- Forces `navigator.webdriver = undefined` (not `false`)
- Dummy page navigation ensures init script applies to all pages
- Critical for Akamai fingerprint bypass

---

### ✅ 2. Chrome Launch Args (Chrome 145 Compatible)
**Location:** `kroger_search_and_capture.py:541-558`

**Removed 9 crashing args:**
- ❌ `--disable-blink-features=AutomationControlled` (unsupported in Chrome 145)
- ❌ `--disable-web-security` (triggers Akamai)
- ❌ `--disable-popup-blocking` (crashes Chrome 145)
- ❌ `--disable-translate` (crashes Chrome 145)
- ❌ `--disable-background-timer-throttling` (crashes Chrome 145)
- ❌ `--disable-renderer-backgrounding` (crashes Chrome 145)
- ❌ `--disable-restore-session-state` (crashes Chrome 145)
- ❌ `--disable-ipc-flooding-protection` (crashes Chrome 145)
- ❌ `--disable-focus-on-load` (crashes Chrome 145)

**Current safe args:**
```python
args=[
    "--disable-dev-shm-usage",
    "--disable-infobars",
    "--no-first-run",
    "--disable-default-apps",
    "--disable-backgrounding-occluded-windows",
    "--window-size=1280,720",
    "--disable-notifications",
    "--disable-quic",
    "--noerrdialogs",
    # GPU acceleration (prevents SwiftShader)
    "--use-angle=metal",
    "--enable-gpu-rasterization",
    "--ignore-gpu-blocklist",
]
```

**Status:** ✅ Chrome 145 compatible
- No `--no-sandbox` (conflicts with `chromium_sandbox=True`)
- GPU acceleration enabled (prevents software rendering detection)

---

### ✅ 3. Behavioral Simulation (Ported from Walmart)
**Location:** `kroger_search_and_capture.py:48-106`

**Implemented functions:**
- ✅ `human_type()` - Variable keystroke delays (80-220ms) with pauses
- ✅ `micro_mouse_attention()` - Subtle mouse micro-movements
- ✅ `random_delay()` - Variable pauses between actions
- ✅ `scroll_like_human()` - Natural wheel scrolling with bursts
- ✅ `drift_reading()` - Simulate reading with pauses
- ✅ `backscroll_peek()` - Scroll up then down (curiosity behavior)

**Status:** ✅ All behavioral patterns implemented

---

### ✅ 4. Profile Persistence
**Location:** `kroger_search_and_capture.py:44, 528-529`

```python
USER_DATA_DIR = "~/ChromeProfiles/kroger_clean_profile"
candidates = [
    {"user_data_dir": USER_DATA_DIR, "channel": "chrome"},
]
```

**Status:** ✅ Using `kroger_clean_profile` (last successful run: Dec 2025)
- Profile NOT burned (confirmed March 3, 2026)
- Session persistence enabled
- Cookies maintained across runs

---

### ✅ 5. Enhanced Diagnostics
**Location:** `kroger_search_and_capture.py:632, 672, 692-698`

**Tracking:**
- ✅ Network forensics counters
- ✅ Timing analysis (to_home_ms, to_search_ms, etc.)
- ✅ Cookie reputation (pre/post tracking)
- ✅ Environment info (User-Agent, webdriver status)
- ✅ Playwright trace capability

**Status:** ✅ Full diagnostic logging enabled

---

### ✅ 6. Rate Limiting Protection
**Location:** `utils/profile_health.py` (should_bail check)

```python
if should_bail("kroger"):
    print("⚠️ Kroger profile is blocked (consecutive failures). Skipping scrape.")
    return False
```

**Status:** ✅ Bail system prevents rapid-fire retries
- Checks for consecutive failures before launching browser
- Prevents IP rate limit triggers

---

## Potential Issues to Watch

### ⚠️ 1. Duplicate Behavioral Functions
**Issue:** Found duplicate function definitions
- Lines 48-106: First set of behavioral functions
- Lines 169-233: Second set with underscore prefix (`_human_type`, etc.)

**Impact:** Minor - both sets are identical, just naming difference
**Action:** Non-critical, but could be cleaned up later

---

### ⚠️ 2. Search Flow Timing
**Location:** Search execution flow

**Current timing:**
1. Homepage load → 5s wait
2. Dismiss popups
3. **Pre-type dwell:** 2-4 seconds ✅
4. Human typing with delays ✅
5. **Post-type dwell:** 0.6-1.2 seconds ✅
6. Mouse movement to button ✅
7. Click search
8. **Pre-scroll idle:** 2.2-3.5 seconds ✅
9. Multiple scroll bursts with reading pauses ✅

**Status:** ✅ All timing patterns implemented correctly

---

### ✅ 3. Cookie Tracking
**Location:** `kroger_search_and_capture.py:672, 1342-1355`

```python
# Pre-run
diag.track_cookies(context, "pre")

# Post-run (in finally block)
diag.track_cookies(context, "post")
```

**Status:** ✅ Cookie reputation tracking enabled
- Captures cookies before and after run
- Helps identify cookie-based detection

---

## Pre-Test Verification

### System Checks

**✅ IP Cooldown Status:**
- Last rapid-fire test: March 3, 2026
- Time elapsed: 4 days
- curl_cffi tests: Blocked at network level (no session established)
- **Verdict:** IP should be clean

**✅ Profile Status:**
- Profile: `kroger_clean_profile`
- Last successful run: December 2025 (land_o_frost/honey_ham)
- Profile NOT burned (confirmed)
- **Verdict:** Profile is valid

**✅ Chrome Version:**
- Chrome 145 compatible args only
- No crashing flags
- **Verdict:** Launch should succeed

**✅ Behavioral Simulation:**
- All Walmart-proven patterns ported
- Human-like timing throughout flow
- **Verdict:** Should pass behavioral detection

---

## Test Execution Plan

### Recommended First Test

```bash
.venv/bin/python3 kroger_search_and_capture.py --search "black forest ham"
```

**Expected behavior:**
1. Browser launches with `kroger_clean_profile`
2. Navigates to homepage (5s wait)
3. Dismisses popups
4. Pre-type dwell (2-4s)
5. Types search term with human delays
6. Post-type dwell (0.6-1.2s)
7. Moves mouse to search button
8. Clicks search
9. Pre-scroll idle (2.2-3.5s)
10. Scrolls with natural bursts
11. Captures results

**Success criteria:**
- ✅ No 403 errors
- ✅ No "Access Denied" pages
- ✅ Search results load
- ✅ Products captured (not empty `ads: []`)
- ✅ Diagnostic report shows no blocking

**Failure indicators:**
- ❌ 403 Forbidden
- ❌ Akamai challenge page
- ❌ Empty results
- ❌ Connection timeout

---

## Post-Test Actions

### If Successful:
1. ✅ Review diagnostic report for any warnings
2. ✅ Verify product data captured
3. ✅ Wait 5 minutes before next test
4. ✅ Continue with scheduled scraping

### If Blocked:
1. ❌ Review diagnostic logs
2. ❌ Check for new detection vectors
3. ❌ Wait 24 hours for IP cooldown
4. ❌ Consider additional behavioral patterns

---

## Critical Reminders

### DO:
- ✅ Maintain 5-minute intervals between scrapes
- ✅ Use `kroger_clean_profile` (not `kroger_fresh_profile`)
- ✅ Review diagnostic reports after each run
- ✅ Monitor for new Akamai detection patterns

### DON'T:
- ❌ Run rapid-fire tests (triggers rate limiter)
- ❌ Use `--no-sandbox` flag (Akamai detection vector)
- ❌ Disable behavioral simulation
- ❌ Mix different Chrome versions with same profile

---

## Conclusion

**All critical anti-detection measures are in place:**
- ✅ navigator.webdriver override
- ✅ Chrome 145 compatible args
- ✅ Behavioral simulation (Walmart-proven)
- ✅ Profile persistence
- ✅ Enhanced diagnostics
- ✅ Rate limiting protection

**System is ready for testing.**

The Kroger scraper is properly configured with all lessons learned from:
- March 3, 2026 Chrome 145 compatibility fixes
- March 5, 2026 behavioral simulation additions
- March 7, 2026 curl_cffi testing (confirmed Playwright is necessary)

**Recommendation:** Proceed with single test run and monitor diagnostics closely.
