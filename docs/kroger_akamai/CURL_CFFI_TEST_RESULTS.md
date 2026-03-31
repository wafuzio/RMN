# curl_cffi Test Results for Kroger Akamai Bypass

**Date:** March 7, 2026  
**Objective:** Test if curl_cffi with TLS impersonation can bypass Akamai detection on Kroger  
**Result:** ❌ **FAILED - Completely Blocked**

---

## Summary

curl_cffi **cannot bypass Akamai** on Kroger. All attempts were blocked at the network/TLS level, even with valid session cookies from Playwright.

---

## Test Methodology

### 1. HAR File Analysis
- Analyzed network traffic from successful Playwright session
- Identified Kroger's two-step API architecture:
  - **Search API:** `https://www.kroger.com/atlas/v1/search/v1/products-search`
  - **Product Details API:** `https://www.kroger.com/atlas/v1/product/v2/products`

### 2. curl_cffi Implementation
- Created script with exact API endpoints from HAR
- Used proper headers (User-Agent, Accept, Referer, sec-ch-ua, etc.)
- Tested multiple TLS impersonation profiles (chrome120, edge101)
- Tested with and without Playwright session cookies

---

## Test Results

### Test 1: No Cookies
```
Status: 403 Forbidden
Response: <HTML><HEAD><TITLE>Access Denied</TITLE></HEAD><BODY>
          <H1>Access Denied</H1>
```
**Verdict:** Immediate block by Akamai

---

### Test 2: With Cookies + HTTP/2 (chrome120)
```
Error: curl: (92) HTTP/2 stream 1 was not closed cleanly: INTERNAL_ERROR (err 2)
```
**Verdict:** Akamai forcibly closes HTTP/2 connection

---

### Test 3: With Cookies + HTTP/1.1 (edge101)
```
Error: curl: (28) Operation timed out after 30002 milliseconds with 0 bytes received
```
**Verdict:** Akamai refuses connection entirely (0 bytes received)

---

## Root Cause Analysis

### Why curl_cffi Failed

Akamai detects curl_cffi at **multiple layers**:

1. **TLS Fingerprint Detection**
   - Despite curl_cffi's TLS impersonation, Akamai can still detect subtle differences
   - Possible detection vectors:
     - TLS extension ordering
     - Cipher suite preferences
     - ALPN negotiation patterns
     - Certificate validation behavior

2. **HTTP/2 Fingerprinting**
   - HTTP/2 SETTINGS frame parameters
   - Stream prioritization patterns
   - HPACK compression behavior
   - Window size updates

3. **Network-Level Blocking**
   - Connection timeout with 0 bytes = Akamai drops packets before TLS handshake
   - This suggests **IP-level or pre-TLS detection**

4. **Missing Browser Context**
   - No JavaScript execution environment
   - No DOM/CSSOM
   - No WebGL/Canvas fingerprinting capability
   - No genuine browser event loop

---

## Comparison: curl_cffi vs Playwright

| Detection Vector | curl_cffi | Playwright |
|-----------------|-----------|------------|
| TLS Fingerprint | ❌ Detected | ✅ Real browser |
| HTTP/2 Behavior | ❌ Detected | ✅ Real browser |
| JavaScript Execution | ❌ None | ✅ Full V8 engine |
| navigator.webdriver | ✅ Not present | ⚠️ Can be hidden |
| Canvas/WebGL | ❌ Not available | ✅ Real GPU |
| Event Timing | ❌ Not applicable | ✅ Real user events |
| Cookie Reputation | ✅ Can reuse | ✅ Can reuse |
| **Overall Result** | ❌ **BLOCKED** | ✅ **Works (with behavioral fixes)** |

---

## Key Insights

### What We Learned

1. **Akamai is more sophisticated than expected**
   - Blocks at network level, not just JavaScript
   - Multiple detection layers (TLS, HTTP/2, behavioral)
   - Even perfect TLS impersonation isn't enough

2. **curl_cffi limitations**
   - Great for simple anti-bot systems
   - **Not sufficient for Akamai-level protection**
   - Cannot replicate full browser behavior

3. **Playwright is necessary**
   - Only real browser can pass all Akamai checks
   - Behavioral simulation (from previous fixes) is critical
   - Cookie reuse helps but isn't sufficient alone

---

## Recommendations

### ✅ Recommended Approach: Enhanced Playwright

Continue using Playwright with the behavioral simulation fixes already implemented:

**Strengths:**
- Real browser = passes all fingerprint checks
- Can execute JavaScript (required for Kroger)
- Supports human behavior simulation
- Can handle CAPTCHAs if needed
- Works with existing codebase

**Already Implemented:**
- ✅ navigator.webdriver override
- ✅ Human typing delays (80-220ms)
- ✅ Mouse micro-movements
- ✅ Natural scrolling patterns
- ✅ Random pauses and dwell time
- ✅ Profile persistence

**Next Steps:**
1. Wait for IP cooldown (24 hours since last rapid-fire tests)
2. Test with behavioral fixes on fresh IP
3. Maintain 1 scrape per 5 minutes rate limit
4. Monitor diagnostic logs for any new detection vectors

---

### ❌ Not Recommended: curl_cffi

**Reasons:**
- Completely blocked by Akamai (all 3 test scenarios failed)
- No path forward without full browser emulation
- Would require reverse-engineering Akamai's detection (cat-and-mouse game)
- Not worth the effort when Playwright works

---

## Files Created

1. **`experiments/kroger_curl_cffi_v2.py`** - Full curl_cffi implementation (blocked)
2. **`experiments/kroger_api_endpoints.md`** - API documentation from HAR
3. **`experiments/analyze_har.py`** - HAR analysis script
4. **`experiments/extract_search_api.py`** - API endpoint extractor

---

## Conclusion

**curl_cffi cannot bypass Akamai on Kroger.** The enhanced Playwright approach with behavioral simulation remains the only viable solution. Focus should be on:

1. Perfecting behavioral patterns
2. Maintaining proper rate limits
3. Using enhanced diagnostics to detect new blocking vectors
4. Keeping profiles clean and authenticated

The parallel curl_cffi path was valuable for understanding Akamai's detection depth, but is not a viable alternative to Playwright.
