# Kroger Akamai Detection & Bypass Documentation

This folder contains all documentation related to Kroger's Akamai anti-bot detection and bypass strategies.

---

## 📁 Documentation Index

### Core Analysis Documents

1. **[KROGER_AKAMAI_DETECTION.md](./KROGER_AKAMAI_DETECTION.md)**
   - Root cause analysis of Kroger blocking
   - Akamai detection vectors identified
   - Timeline of issues (January 2026 - March 2026)

2. **[WALMART_METHODOLOGY_FOR_KROGER.md](./WALMART_METHODOLOGY_FOR_KROGER.md)**
   - Behavioral simulation patterns ported from Walmart
   - Human-like interaction techniques
   - Proven anti-detection strategies

3. **[KROGER_DIAGNOSTIC_LOGGING.md](./KROGER_DIAGNOSTIC_LOGGING.md)**
   - Enhanced diagnostic system documentation
   - Network forensics counters
   - Timing analysis and cookie reputation tracking

---

### Testing & Validation

4. **[CURL_CFFI_TEST_RESULTS.md](./CURL_CFFI_TEST_RESULTS.md)**
   - curl_cffi bypass attempt results (FAILED)
   - Comparison: curl_cffi vs Playwright
   - Why Playwright is necessary for Akamai

5. **[KROGER_PREFLIGHT_CHECKLIST.md](./KROGER_PREFLIGHT_CHECKLIST.md)**
   - Pre-test verification checklist
   - All anti-detection measures verified
   - Test execution plan and success criteria

---

### API Documentation

6. **[kroger_api_endpoints.md](./kroger_api_endpoints.md)**
   - Kroger's two-step API architecture
   - Search API and Product Details API endpoints
   - Headers, parameters, and response structures

---

## 🎯 Quick Reference

### Current Status (March 7, 2026)

**Scraper Status:** ✅ Ready for testing  
**IP Status:** ✅ Clean (4 days since last rate limit)  
**Profile Status:** ✅ Valid (`kroger_clean_profile`)  
**Anti-Detection:** ✅ All measures in place

### Key Findings

1. **Akamai blocks at multiple layers:**
   - TLS fingerprinting
   - HTTP/2 behavior analysis
   - JavaScript execution patterns
   - Behavioral timing analysis

2. **curl_cffi cannot bypass Akamai:**
   - Blocked at network/TLS level
   - Even with valid cookies
   - Playwright is necessary

3. **Behavioral simulation is critical:**
   - Variable keystroke delays (80-220ms)
   - Natural scrolling patterns
   - Mouse micro-movements
   - Pre/post-action dwell times

### Critical Anti-Detection Measures

- ✅ `navigator.webdriver = undefined`
- ✅ Chrome 145 compatible launch args
- ✅ GPU acceleration enabled
- ✅ Behavioral simulation (Walmart-proven)
- ✅ Profile persistence
- ✅ Enhanced diagnostics
- ✅ Rate limiting protection

---

## 📊 Timeline

- **December 2025:** Last successful Kroger scrape
- **January 2026:** Akamai updated detection (behavioral focus)
- **March 3, 2026:** Chrome 145 compatibility fixes
- **March 5, 2026:** Behavioral simulation added
- **March 7, 2026:** curl_cffi testing (confirmed blocked)

---

## 🔗 Files in This Folder

### Scripts (Reference Copies)
- **[kroger_search_and_capture.py](./kroger_search_and_capture.py)** - Main scraper with all fixes (snapshot)
- **[kroger_diagnostics.py](./kroger_diagnostics.py)** - Enhanced diagnostic system (snapshot)
- **[kroger_curl_cffi_v2.py](./kroger_curl_cffi_v2.py)** - curl_cffi test script (blocked by Akamai)

**Note:** These are reference copies. The active versions are:
- `/kroger_search_and_capture.py` (main scraper)
- `/utils/kroger_diagnostics.py` (diagnostics)
- `/experiments/kroger_curl_cffi_v2.py` (curl_cffi test)

### Analysis Scripts (Located in /experiments/)
- `/experiments/analyze_har.py` - HAR file analyzer
- `/experiments/extract_search_api.py` - API endpoint extractor
- `/experiments/analyze_kroger_state.py` - window.__INITIAL_STATE__ parser

---

## 📝 Recommendations

### For Testing
1. Wait 5 minutes between scrapes
2. Use `kroger_clean_profile` only
3. Monitor diagnostic reports
4. Don't rapid-fire retry on failures

### For Maintenance
1. Keep Chrome updated (currently 145)
2. Review diagnostic logs regularly
3. Update behavioral patterns if new detection vectors emerge
4. Maintain profile health

---

## 🚨 Important Notes

- **DO NOT** use `--no-sandbox` flag (Akamai detection vector)
- **DO NOT** rapid-fire test (triggers IP rate limiter)
- **DO NOT** mix Chrome versions with same profile
- **DO** maintain 5-minute intervals between scrapes
- **DO** review diagnostics after each run

---

**Last Updated:** March 7, 2026  
**Status:** All documentation current and organized
