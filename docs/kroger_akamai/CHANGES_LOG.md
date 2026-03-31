# Kroger Scraper Changes Log - March 7, 2026 (Evening Sessions)

**Based on:** HAR Analysis and Fixes by colleague  
**Date:** March 7, 2026, 7:00 PM - 9:54 PM  
**Status:** ✅ All fixes implemented, ready to test with clean IP

---

## Files Modified

### 1. kroger_search_and_capture.py

**Location:** `/Users/dan.maguire/Documents/Amazon_Scrape/kroger_search_and_capture.py`  
**Backup:** `docs/kroger_akamai/kroger_search_and_capture.py` (updated copy)

#### Change 1: Removed navigator.webdriver Override
**Lines:** 560-565 (old)  
**Severity:** HIGH

**Before:**
```python
# CRITICAL: Force navigator.webdriver to undefined (ignore_default_args doesn't always work with persistent context)
ctx.add_init_script("""
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined
    });
""")
```

**After:**
```python
# NOTE: navigator.webdriver override removed per HAR analysis
# With ignore_default_args=['--enable-automation'], Chrome natively reports webdriver=false
# Previous override to undefined was detectable (wrong value + getter function)
```

**Rationale:**
- Setting to `undefined` is wrong (real Chrome reports `false`)
- `Object.defineProperty` creates detectable getter function
- With `ignore_default_args=['--enable-automation']`, override is unnecessary
- Chrome natively reports `webdriver=false` as a boolean data property

---

#### Change 2: Removed data:text/html Dummy Navigation
**Lines:** 567-575 (old)  
**Severity:** HIGH

**Before:**
```python
# WORKAROUND: Navigate to dummy page first to ensure init script takes effect
# The init script only applies to pages created AFTER it's called
# Initial about:blank page has webdriver=true, so we navigate away and back
try:
    dummy_page = ctx.pages[0] if ctx.pages else ctx.new_page()
    dummy_page.goto("data:text/html,<html><body>Initializing...</body></html>", wait_until="domcontentloaded", timeout=5000)
    dummy_page.wait_for_timeout(500)  # Let override settle
except Exception:
    pass  # Non-fatal if dummy navigation fails
```

**After:**
```python
# (Removed entirely)
```

**Rationale:**
- Only existed to support the (now removed) webdriver override
- Created detectable artifacts:
  - Abnormal navigation history with `data:` URL
  - Polluted `document.referrer` chain
  - RUM telemetry logged synthetic navigation
- Browser now launches and navigates directly to kroger.com

---

#### Change 3: Homepage Load Wait - Active Dwell
**Lines:** 675-676  
**Severity:** MEDIUM

**Before:**
```python
page.wait_for_timeout(5000)
diag.log("homepage_loaded", url=page.url)
```

**After:**
```python
page.wait_for_timeout(2000)  # Initial DOM settle
drift_reading(page, seconds=random.uniform(2.0, 3.5))  # Generate mouse telemetry during dwell
diag.log("homepage_loaded", url=page.url)
```

**Rationale:**
- Dead sleep generates zero telemetry
- Real users generate mouse drift during idle periods
- Akamai sensor collects telemetry continuously
- `drift_reading()` fills gap with authentic low-level activity

---

#### Change 4: Browsing Simulation - Active Dwell
**Lines:** 786, 792  
**Severity:** MEDIUM

**Before:**
```python
random_delay(3.0, 6.0)  # Humans browse before searching
# ...
random_delay(1.0, 2.0)
```

**After:**
```python
drift_reading(page, seconds=random.uniform(3.0, 6.0))  # Generate mouse telemetry during browsing
# ...
drift_reading(page, seconds=random.uniform(1.0, 2.0))  # Active dwell after scroll
```

**Rationale:**
- Fills 3-6 second browsing window with mouse activity
- Matches HAR data showing continuous interaction counts
- Avoids silence-burst-silence pattern

---

#### Change 5: Pre-Type Dwell - Active Thinking
**Lines:** 855  
**Severity:** MEDIUM

**Before:**
```python
# 2) Pre-type dwell (adds entropy — avoids "home → submit in ~4s")
time.sleep(random.uniform(2.0, 4.0))
```

**After:**
```python
# 2) Pre-type dwell (adds entropy — avoids "home → submit in ~4s")
drift_reading(page, seconds=random.uniform(2.0, 4.0))  # Mouse drift while user thinks
```

**Rationale:**
- Simulates user thinking about what to type
- Mouse naturally drifts during cognitive pauses
- Generates telemetry that Akamai sensor expects

---

#### Change 6: Pre-Scroll Idle - Active Scanning
**Lines:** 1064  
**Severity:** MEDIUM

**Before:**
```python
# Pre-scroll idle (humans don't scroll instantly)
diag.log("pre_scroll_idle_start")
random_delay(2.2, 3.5)
```

**After:**
```python
# Pre-scroll idle (humans don't scroll instantly)
diag.log("pre_scroll_idle_start")
drift_reading(page, seconds=random.uniform(2.2, 3.5))  # Scan results with mouse drift
```

**Rationale:**
- Simulates user scanning search results before scrolling
- Real users move mouse while reading
- Fills 2.2-3.5 second gap with authentic activity

---

### 2. KROGER_AKAMAI_DETECTION.md

**Location:** `docs/kroger_akamai/KROGER_AKAMAI_DETECTION.md`  
**Severity:** Documentation Drift Fix

#### Change: Fixed Chrome Args List
**Lines:** 52-70

**Before:**
```python
args = [
    '--no-sandbox',  # ← INCORRECT
    '--disable-dev-shm-usage',
    # ... other args
]
```

**After:**
```python
args = [
    '--disable-dev-shm-usage',
    '--disable-infobars',
    '--no-first-run',
    '--disable-default-apps',
    '--disable-backgrounding-occluded-windows',
    '--window-size=1280,720',
    '--disable-notifications',
    '--disable-quic',
    '--noerrdialogs',
    # GPU acceleration (CRITICAL: Prevents SwiftShader software rendering)
    '--use-angle=metal',
    '--enable-gpu-rasterization',
    '--ignore-gpu-blocklist',
]

# NOTE: chromium_sandbox=True is used instead of --no-sandbox flag
# The --no-sandbox flag is a detection vector for Akamai
```

**Rationale:**
- Documentation was out of sync with actual code
- `--no-sandbox` was removed but still listed in docs
- GPU acceleration args were missing from docs
- Added clarifying note about `chromium_sandbox=True`

---

### 3. EXECUTIVE_SUMMARY.md

**Location:** `docs/kroger_akamai/EXECUTIVE_SUMMARY.md`  
**Severity:** Documentation Update

#### Changes Made:
1. Added March 7, 2026 (Evening) timeline entry
2. Updated "What We've Fixed" section with HAR findings
3. Added new Section 4: Session Pollution
4. Enhanced Section 3: Behavioral Patterns with telemetry gap explanation
5. Updated Section 1: Browser Fingerprint Issues with override removal

**Key Additions:**
- Three-layer Akamai detection system documented
- Telemetry gap problem explained
- Session pollution issue documented
- All fixes cross-referenced with HAR analysis

---

## Summary of Impact

### Detection Vectors Removed
1. ✅ **navigator.webdriver = undefined** (wrong value + detectable getter)
2. ✅ **data:text/html navigation** (abnormal history + referrer pollution)
3. ✅ **Telemetry gaps** (5 locations now generate continuous mouse activity)

### Fingerprint Improvements
- **More authentic:** Native `webdriver=false` instead of override
- **Cleaner session:** Direct navigation to kroger.com (no synthetic steps)
- **Continuous telemetry:** Mouse drift during all dwell periods

### Documentation Accuracy
- ✅ Args list corrected (removed --no-sandbox)
- ✅ GPU acceleration args added
- ✅ HAR findings documented
- ✅ Timeline updated

---

## Testing Recommendations

### Before Testing
1. **Clean Akamai cookies** from `kroger_clean_profile`:
   - `_abck` (bot score cookie)
   - `ak_bmsc`, `bm_mi`, `bm_sv`, `bm_sz` (related cookies)
   - Or manually browse kroger.com for 30 seconds to warm fresh cookies

2. **Verify changes applied:**
   ```bash
   grep -n "navigator.webdriver" kroger_search_and_capture.py
   # Should show only comment on line 561, no add_init_script
   
   grep -n "data:text/html" kroger_search_and_capture.py
   # Should return no results
   
   grep -n "drift_reading" kroger_search_and_capture.py
   # Should show 5+ occurrences
   ```

### Expected Improvements
- ✅ No detectable webdriver override
- ✅ Clean navigation history
- ✅ Continuous Akamai sensor telemetry
- ✅ More authentic browser fingerprint

### Success Metrics
- No 403 Forbidden responses
- Search results load successfully
- Products captured (not empty)
- Diagnostic report shows no Akamai blocking signals

---

## Files in This Folder

**Reference Copies (Updated):**
- `kroger_search_and_capture.py` - Main scraper with HAR fixes applied
- `kroger_diagnostics.py` - Diagnostic system (unchanged)
- `kroger_curl_cffi_v2.py` - curl_cffi test (unchanged)

**Documentation:**
- `AKAMAI_HAR_ANALYSIS_AND_FIXES.md` - Colleague's analysis
- `EXECUTIVE_SUMMARY.md` - Updated with HAR findings
- `KROGER_AKAMAI_DETECTION.md` - Args list corrected
- `CHANGES_LOG.md` - This file

**Data:**
- `kroger_html.md` - Sample HTML
- `www.kroger.com.har` - HAR file analyzed

---

**Last Updated:** March 7, 2026, 7:30 PM  
**Status:** All fixes implemented and documented
