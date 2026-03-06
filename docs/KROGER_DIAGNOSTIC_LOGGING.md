# Kroger Diagnostic Logging System

## Overview

Comprehensive step-by-step diagnostic logging is now integrated into **all** Kroger scraping operations to help debug Akamai bot detection issues until the behavioral simulation fixes are proven stable.

## What Gets Logged

Every Kroger scrape now automatically generates detailed forensic artifacts:

### 1. **steps.jsonl** - Event Timeline
Microsecond-precision log of every action:
- Browser launch
- Homepage navigation
- Login checks
- Search box interactions (click, typing, submission)
- Page loads and transitions
- Scrolling and mouse movements
- Akamai block detection checks

### 2. **report.json** - Structured Summary
- Run metadata (ID, duration, timestamps)
- Total steps executed
- Blocks detected (count and details)
- Diagnostic checkpoints with full fingerprint data
- Output directory paths

### 3. **report.md** - Human-Readable Report
Markdown-formatted summary with:
- Run statistics
- Block detection details
- Navigator diagnostics (webdriver, platform, etc.)
- WebGL fingerprint (GPU vendor/renderer)
- Cookie counts and Akamai-specific cookies

### 4. **Forensic Screenshots & HTML**
Automatic capture at critical points:
- `blocked_at_homepage_screenshot.png` + HTML
- `blocked_at_search_results_screenshot.png` + HTML
- `blocked_at_direct_navigation_screenshot.png` + HTML
- `final_page_screenshot.png` + HTML (successful runs)

## Diagnostic Checkpoints

Fingerprint diagnostics collected at:
1. **before_navigation** - Initial browser state
2. **after_homepage_load** - After Kroger homepage loads
3. **after_search_results** - After search submission
4. **final_state** - Before browser closes (successful runs)

Each checkpoint captures:
- `navigator.webdriver` value
- User agent and platform
- Hardware concurrency
- WebGL vendor and renderer (unmasked)
- Cookie count and Akamai cookies (`_abck`, `bm_*`, `ak_*`)
- Viewport dimensions
- Current URL and page title

## Output Location

Diagnostics are saved to:
```
output/<client>/diagnostics_<timestamp>/
├── steps.jsonl
├── report.json
├── report.md
├── blocked_at_homepage_screenshot.png (if blocked)
├── blocked_at_homepage_page.html (if blocked)
├── final_page_screenshot.png (if successful)
└── final_page_page.html (if successful)
```

## How to Use

### Main Scraper
Diagnostic logging is **automatic** - just run the scraper normally:

```bash
.venv/bin/python3 kroger_search_and_capture.py --search "black forest ham"
```

Every run will generate diagnostics in the output directory.

### Step-by-Step Test Script
For isolated testing:

```bash
# Test specific step
.venv/bin/python3 tools/kroger_step_by_step_test.py --step homepage

# Test all steps
.venv/bin/python3 tools/kroger_step_by_step_test.py --step all

# Test with custom profile
.venv/bin/python3 tools/kroger_step_by_step_test.py --step all --profile ~/ChromeProfiles/kroger_test
```

## Interpreting Results

### Success Indicators
✅ **No blocks detected**
```json
{"event": "no_block_detected", "url": "https://www.kroger.com/search?query=..."}
```

✅ **Clean fingerprint**
```json
{"event": "navigator_collected", "webdriver": null}
{"event": "webgl_collected", "renderer": "ANGLE (Apple, ANGLE Metal Renderer: Apple M1 Pro...)"}
```

### Block Indicators
❌ **Akamai block detected**
```json
{"event": "akamai_block_detected", "reason": "access_denied_title"}
```

❌ **Suspicious fingerprint**
```json
{"event": "navigator_collected", "webdriver": true}  // BAD
{"event": "webgl_collected", "renderer": "SwiftShader"}  // BAD
```

## Console Output

Real-time diagnostic logging appears in console:
```
[     0ms] diagnostic_session_start: run_id=20260305223000, output_dir=output/kroger/client
[   823ms] browser_launched: pages=1
[  1234ms] collecting_diagnostics: checkpoint=before_navigation
[  1250ms] navigator_collected: checkpoint=before_navigation, webdriver=None
[  1265ms] webgl_collected: checkpoint=before_navigation, renderer=ANGLE (Apple, ANGLE Metal Renderer: Apple M1 Pro...)
[  2100ms] homepage_navigation_start: url=https://www.kroger.com/
[  6500ms] homepage_loaded: url=https://www.kroger.com/
[  6520ms] collecting_diagnostics: checkpoint=after_homepage_load
[  6550ms] no_block_detected: url=https://www.kroger.com/, content_size=125643
```

## When to Review Diagnostics

### Always Review If:
1. **Scraper returns False** - Check for Akamai blocks
2. **Empty ads array** - Verify page loaded correctly
3. **Consecutive failures** - Look for fingerprint issues
4. **Testing new behavioral changes** - Confirm they're working

### Key Files to Check:
1. **steps.jsonl** - Full event timeline
2. **report.md** - Quick summary
3. **Screenshots** - Visual confirmation of blocks

## Diagnostic Module API

For custom scripts:

```python
from utils.kroger_diagnostics import KrogerDiagnostics

# Initialize
diag = KrogerDiagnostics(output_dir="output/kroger/client", run_id="custom_test")

# Log events
diag.log("custom_event", key="value", data=123)

# Collect fingerprint diagnostics
diag.collect_diagnostics(page, context, "my_checkpoint")

# Check for Akamai blocks
is_blocked, reason, details = diag.check_akamai_block(page)

# Save forensic artifacts
diag.save_forensics(page, "custom_label")

# Finalize (saves steps.jsonl, report.json, report.md)
report = diag.finalize()
```

## Disabling Diagnostics

Diagnostics are lightweight but if you need to disable them:

1. Comment out the `KrogerDiagnostics` initialization in `kroger_search_and_capture.py`
2. Comment out all `diag.log()`, `diag.collect_diagnostics()`, and `diag.check_akamai_block()` calls

**Note**: Keep diagnostics enabled until Kroger is proven stable (multiple successful runs without blocks).

## Comparison with Test Script

| Feature | Main Scraper | Test Script |
|---------|-------------|-------------|
| Diagnostic logging | ✅ Full | ✅ Full |
| Behavioral simulation | ✅ Yes | ❌ No (minimal) |
| Login handling | ✅ Yes | ❌ No |
| Ad capture | ✅ Yes | ❌ No |
| Post-processing | ✅ Yes | ❌ No |
| Use case | Production scraping | Isolation testing |

## Next Steps

1. **After 24h IP cooldown**, run a test scrape
2. **Review diagnostics** in `output/<client>/diagnostics_*/`
3. **Check for blocks** in `report.md`
4. **Verify fingerprint** in `steps.jsonl` (webdriver should be `null`)
5. **If successful**, monitor for 3-5 runs to confirm stability
6. **If blocked**, review screenshots and fingerprint data to identify new detection vectors

## Related Documentation

- `docs/KROGER_AKAMAI_DETECTION.md` - Akamai detection guide
- `tools/kroger_step_by_step_test.py` - Isolation testing script
- `utils/kroger_diagnostics.py` - Diagnostic module source
