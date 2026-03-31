# Kroger Akamai Bypass: HAR Analysis & Code Changes

**Date:** March 7, 2026

---

## What the HAR File Revealed

Analysis of the captured HAR file (249 entries, ~9MB) from a successful Playwright session revealed that Kroger's Akamai implementation operates as a **three-layer detection system**, not the two-layer model described in the existing documentation.

### Layer 1: Akamai BMP Sensor

The primary bot detection layer communicates through obfuscated POST endpoints (the "CHOKAO-\*" URL pattern). The session contained 18 sensor POSTs across a 13-minute window, all returning 200-level status codes. Two distinct sub-endpoints were identified:

- **Path A (Token/CMP):** Sends an obfuscated "body" field as `application/json`. This is the Client-side Proof mechanism — a computational challenge response proving JavaScript executed correctly. Returns 202.

- **Path B (Sensor Telemetry):** Sends "sensor\_data" as `text/plain`. This is Akamai v2 behavioral telemetry (version field = 2), semicolon-delimited with 34–114 fields per post. Field 4 contains interaction counts: mouse events, key events, touch events, orientation events, focus events, and scroll events. Returns 201.

### Layer 2: Dynatrace RUM (mPulse/Boomerang)

Over 60 beacons were sent to `/rb_bf68771uzq` during the session. This is Akamai's Real User Monitoring system, reporting performance metrics, page load timing, browser tab instance IDs, and visibility state. While not directly part of bot detection, this data feeds into Akamai's overall risk scoring. The RUM script loads independently from the page's own JavaScript and fires naturally in a real browser, so no special handling is needed.

### Layer 3: Client-side Protection Config

A GET request to `/_sec/cpr/params` was observed at the 10-minute mark. This endpoint delivers Akamai's challenge configuration to the client. Its presence indicates the sensor script was running correctly and reached the point of requesting updated challenge parameters.

### Critical Timing Observation

In the successful session, the time from first sensor POST to first search API call was **12 seconds**. The first sensor payload (entry 1) reported **31 mouse events, 43 key events, and 32 scroll events** already collected before the search was even submitted. This means the sensor was continuously collecting telemetry from the moment the page loaded, and a real user generated significant interaction data during the browsing-to-search window.

---

## Problems Identified

### 1. navigator.webdriver Override Was Detectable

**Severity: HIGH**

The scraper was using `Object.defineProperty` to set `navigator.webdriver` to `undefined`. This is detectable by Akamai's sensor for two reasons:

1. **Wrong value:** Real Chrome 145 reports `navigator.webdriver` as `false` (a boolean data property), never `undefined`. The value `undefined` does not occur in any shipping browser build. Akamai's sensor encodes this into its fingerprint payload, creating an anomaly.

2. **Detectable override mechanism:** `Object.defineProperty` creates a getter function on the property. Akamai's sensor can detect this by calling `Object.getOwnPropertyDescriptor(navigator, 'webdriver')` and observing that the property has a "get" function rather than a "value" field. This is a known detection vector for property overrides.

**Why the override existed:** It was a workaround for Playwright setting `navigator.webdriver` to `true` via the `--enable-automation` flag. However, the scraper already uses `ignore_default_args=['--enable-automation']`, which prevents the flag from being added. With that flag excluded, real Chrome natively reports `webdriver` as `false` — no override is needed.

### 2. data:text/html Dummy Navigation Poisoned Session

**Severity: HIGH**

After launching the browser, the scraper navigated to `data:text/html,<html><body>Initializing...</body></html>` as a workaround to force the webdriver init script to take effect. This created multiple detection vectors:

- The `performance.navigation` API recorded an extra navigation entry with a `data:` URL — something no real user session would contain.
- The `document.referrer` chain contained a `data:` URL, which is a unique fingerprint.
- Akamai's Boomerang/RUM script (if loaded from cache) could log the `data:` page load event in its telemetry.

In the successful HAR session, the very first event was the sensor POST — the page loaded and the sensor fired immediately. The scraper's flow inserted a synthetic navigation gap before any real page load, creating a measurably different session structure.

### 3. Dead Time During Dwell Periods

**Severity: MEDIUM**

The scraper used bare `time.sleep()` and `random_delay()` calls during dwell periods — the 5-second homepage wait, the 3–6 second browsing simulation, and the 2–4 second pre-type pause. During these periods, Akamai's sensor was collecting telemetry continuously. A real user who pauses for 5 seconds still generates some mouse movement (drift, fidgeting) and possibly scroll events. The scraper generated **zero telemetry** during these windows — pure silence followed by a burst of activity, which is a recognizable bot pattern.

The HAR data confirmed this: sensor payloads from the successful session showed accumulated interaction counts that grew steadily across posts, indicating continuous low-level activity. The scraper's pattern of silence-burst-silence would produce sensor payloads with interaction counts that jump in discrete steps rather than growing smoothly.

---

## Changes Made

### Change 1: Removed navigator.webdriver Override

**File:** `kroger_search_and_capture.py`, lines 560–575 (old)

**What was removed:** The `ctx.add_init_script()` call that used `Object.defineProperty` to set `navigator.webdriver` to `undefined`.

**Why:** The `ignore_default_args=['--enable-automation']` parameter already prevents Playwright from adding the `--enable-automation` flag. Without that flag, real Chrome reports `navigator.webdriver` as `false` natively (a boolean data property). The override was setting it to `undefined` (via a getter function), which is both the wrong value and a detectable override mechanism. Removing it produces a more authentic fingerprint.

### Change 2: Removed data:text/html Dummy Navigation

**File:** `kroger_search_and_capture.py`, lines 567–575 (old)

**What was removed:** The try block that navigated to `data:text/html,<html><body>Initializing...</body></html>` with a 500ms wait.

**Why:** This workaround was only needed to force the init script (now removed) to take effect. The `data:` URL created detectable artifacts in navigation history, referrer chains, and RUM telemetry. With the init script removed, there is no reason for this navigation step. The browser now launches and navigates directly to kroger.com, matching the session flow observed in the successful HAR capture.

### Change 3: Replaced Dead Dwell Time with Active Behaviors

**File:** `kroger_search_and_capture.py`, five locations

**What changed:** Replaced bare `time.sleep()` and `random_delay()` calls during significant dwell periods (1+ seconds) with `drift_reading()` calls. The `drift_reading()` function generates subtle mouse micro-movements and small pauses that simulate a user scanning the page, producing continuous low-level telemetry for Akamai's sensor.

**Locations changed:**

1. **Homepage load wait** (~line 681): Changed from `page.wait_for_timeout(5000)` to a 2-second wait followed by `drift_reading()` for 2–3.5 seconds. Total dwell time is similar but now generates mouse telemetry.

2. **Browsing simulation** (~line 791): Changed from `random_delay(3.0, 6.0)` to `drift_reading(page, seconds=random.uniform(3.0, 6.0))`. Fills the pre-search browsing window with mouse drift instead of dead silence.

3. **Post-scroll pause on homepage** (~line 797): Changed from `random_delay(1.0, 2.0)` to `drift_reading()` for the same duration.

4. **Pre-type dwell** (~line 860): Changed from `time.sleep(random.uniform(2.0, 4.0))` to `drift_reading()`. Simulates the user's mouse moving while they decide what to type.

5. **Pre-scroll idle on search results** (~line 1076): Changed from `random_delay(2.2, 3.5)` to `drift_reading()`. Simulates the user scanning search results before scrolling.

**Why:** Akamai's sensor collects telemetry continuously. In the successful HAR session, sensor payloads showed steadily growing interaction counts, indicating real users generate low-level activity even during "idle" periods. The scraper's pattern of absolute silence (zero events) followed by activity bursts is a distinguishable bot signature. `drift_reading()` fills these gaps with the same kind of low-level mouse drift that a real user produces while scanning a page.

---

## Summary

| Change | Severity | Rationale |
|--------|----------|-----------|
| Removed webdriver override | **High** | `undefined` is wrong value; getter is detectable |
| Removed `data:` URL navigation | **High** | Pollutes navigation history, referrer chain, RUM telemetry |
| Active dwell behaviors | **Medium** | Fills telemetry gaps; matches real user interaction patterns from HAR |

The fundamental architecture (Playwright with persistent profile, behavioral simulation) is correct. The curl\_cffi test confirmed that only a real browser can pass Akamai's detection. These changes address specific tells that a real Chrome session would not produce, reducing the gap between the scraper's fingerprint and a genuine user's.

---

## Additional Recommendations (Not Yet Implemented)

### Clean Stale Akamai Cookies Before Testing

The `kroger_clean_profile` was last successfully used in December 2025. Akamai's bot score cookie (`_abck`) and related cookies (`ak_bmsc`, `bm_mi`, `bm_sv`, `bm_sz`) may be stale or contain a "bad" score from a previously blocked session. Before the next test run, manually delete these cookies from the Chrome profile, or browse kroger.com manually in the profile for 30 seconds to warm fresh cookies. This forces Akamai's sensor to generate fresh scoring rather than relying on potentially poisoned state.

### Add Sensor Health Monitoring to Diagnostics

The current `check_akamai_block()` function only examines page HTML for block patterns (Access Denied, edgesuite errors). It does not verify whether Akamai's sensor script actually loaded and posted successfully. A failed or corrupted sensor results in a bad `_abck` cookie, which causes the next API request (the search) to fail — but this failure mode is invisible to the current diagnostics. Adding network request interception to verify CHOKAO endpoint responses (expecting 201/202) would provide early warning of sensor-level issues before they manifest as search failures.

### Document Drift: Inconsistent Args List

`KROGER_AKAMAI_DETECTION.md` lists `--no-sandbox` in the "Chrome 145 Compatible Args" section (line 52), but the actual code and executive summary confirm it was removed. This kind of documentation drift is dangerous for a project where a single wrong flag can trigger detection. A cleanup pass across all docs is recommended to ensure they reflect the current state of the code.

### The --disable-quic Flag

The scraper disables QUIC (HTTP/3), forcing all connections to use HTTP/2. In the successful HAR session, the connection used HTTP/2 with TLS 1.3, which is consistent. However, stock Chrome 145 would typically negotiate QUIC/HTTP/3 with Akamai edges that support it. Disabling QUIC is one more fingerprint data point that distinguishes the browser from stock. This is low-risk on its own but worth noting as a cumulative factor in Akamai's scoring.
