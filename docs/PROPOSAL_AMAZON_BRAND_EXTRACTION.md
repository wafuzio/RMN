# Proposal: Robust Amazon Brand Extraction via Iframe Piercing & Network Capture

## Executive Summary

The current "Unknown Brand" issue stems from Sponsored Display ads being rendered inside **iframes**. The current capture script (`amazon_search_and_capture.py`) scans the main page DOM, which cannot see inside these iframes. As a result, it misses the accessibility text and metadata that exists within the ad's protected document context.

The post-processing attempts (HTML matching) are fragile because they rely on guessing which "accessibility span" in the global HTML corresponds to which "unknown iframe" in the list.

**The Solution**: Move the extraction "left" — capture the data accurately during the scrape by "piercing" the iframes using Playwright's Frame API, and supplement this with Network Interception to grab raw ad data.

---

## Recommended Path Forward

### Phase 1: Direct Iframe Extraction (High Impact, Low Effort)

Playwright has native support for accessing content inside iframes (`frame.locator(...)`), but the current script treats iframes as black boxes.

**Technical Change:**
Modify `amazon_search_and_capture.py` to:
1. Identify when an ad container hosts an iframe.
2. Get the Playwright `Frame` object associated with that element.
3. Query the *internal* DOM of that frame for:
   - `a[href]` (Store links, Product links)
   - `img[alt]` (Brand logos)
   - `div[aria-label]` or `span` containing "Sponsored ad" text.

**Why this wins:**
- **Zero Ambiguity**: We extract metadata from the *exact* iframe we are screenshotting. No need to map lists later.
- **Access to Hidden Data**: The "accessibility text" mentioned in the issue (`Sponsored Ad.\nBrand logo...`) is often actually *inside* the iframe's DOM, which we are currently ignoring.

### Phase 2: Network Response Interception (Robustness)

Amazon populates these ads via dynamic XHR/Fetch requests (often to endpoints like `/s/s-ad-ajax` or external DSP domains). These responses contain the structured JSON data (Brand Name, ASIN, Image URLs) used to render the ad.

**Technical Change:**
Add a Playwright network listener:
```python
page.on("response", handle_response)
```
- Capture JSON responses associated with ad loading.
- Map them to ad slots via `data-uuid` or `cel_widget_id`.

**Why this wins:**
- **Source of Truth**: Bypasses the DOM rendering entirely.
- **Resilient**: Even if Amazon changes the DOM structure/classes, the data payload often remains stable.

---

## Implementation Plan

### Step 1: Proof of Concept (Iframe Piercing)
Create a test script (or modify `amazon_search_and_capture.py`) to:
1. Iterate over all `iframe` elements in `page.frames`.
2. Print their URL and title.
3. Try to locate `text="Sponsored"` or `a[href*="/stores/"]` inside them.

### Step 2: Integrate into Capture Loop
Update `amazon_search_and_capture.py`'s `_extract_brand_and_message` function:
- If the container contains an iframe, switch context to the frame.
- Run the existing brand regex extractors *inside* the frame context.

### Step 3: Deprecate Post-Processing
Once capture is accurate, the `batch_fix_unknown_brands_from_html.py` script becomes a safety net rather than a primary tool.

## Time Estimate
- **Phase 1 (Iframe Logic)**: ~1-2 hours coding & testing.
- **Phase 2 (Network)**: ~2-3 hours (requires analyzing traffic patterns first).

This approach will likely reduce "Unknown" brands by >90% without requiring constant maintenance of the HTML matching script.
