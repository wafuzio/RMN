# Applying Walmart PerimeterX Methodology to Kroger Akamai Detection

## Overview

The Walmart PerimeterX step-by-step detection methodology is directly applicable to Kroger's Akamai bot detection, even though they use different systems. Both use behavioral analysis and machine learning to detect bots.

## Key Walmart Techniques Now Applied to Kroger

### 1. **Per-Keystroke Logging** ✅ IMPLEMENTED

**Walmart Approach:**
- Log every single character typed with timing
- Track delay between each keystroke (80-220ms variable)
- Log micro-pauses (10% chance, 50-150ms)
- Log final pause after typing complete (200-450ms)

**Why It Matters:**
- Identifies exact keystroke that triggers detection
- Reveals if consistent timing patterns are flagged
- Shows if specific characters or character sequences trigger blocks

**Kroger Implementation:**
```python
def human_type_with_logging(element, text: str, logger):
    """Type with human-like delays and log each keystroke (Walmart methodology)."""
    for i, ch in enumerate(text):
        delay_ms = random.uniform(80, 220)
        logger.log("keystroke", char=ch, index=i, delay_ms=int(delay_ms))
        element.type(ch, delay=delay_ms)
        
        # Random micro-pause (10% chance)
        if random.random() < 0.10:
            pause_ms = random.uniform(50, 150)
            logger.log("keystroke_pause", index=i, pause_ms=int(pause_ms))
            time.sleep(pause_ms / 1000)
```

**Diagnostic Output:**
```json
{"event": "keystroke", "char": "b", "index": 0, "delay_ms": 156}
{"event": "keystroke", "char": "l", "index": 1, "delay_ms": 203}
{"event": "keystroke", "char": "a", "index": 2, "delay_ms": 89}
{"event": "keystroke_pause", "index": 2, "pause_ms": 127}
{"event": "keystroke", "char": "c", "index": 3, "delay_ms": 178}
...
```

If blocked at keystroke index 7, you know character 'f' triggered it.

### 2. **Incremental Step Testing** ✅ IMPLEMENTED

**Walmart Approach:**
- Test homepage load only
- Test homepage + search box click
- Test homepage + search box + typing
- Test homepage + search box + typing + submission
- Isolate exact action that triggers block

**Kroger Implementation:**
```bash
# Test each step independently
.venv/bin/python3 tools/kroger_step_by_step_test.py --step homepage
.venv/bin/python3 tools/kroger_step_by_step_test.py --step search_box
.venv/bin/python3 tools/kroger_step_by_step_test.py --step type_search
.venv/bin/python3 tools/kroger_step_by_step_test.py --step submit
```

**Why It Matters:**
- Pinpoints exact trigger point
- Avoids wasting time on wrong assumptions
- Enables targeted fixes

### 3. **Comprehensive Forensics** ✅ IMPLEMENTED

**Walmart Artifacts:**
- `steps.jsonl` - Microsecond-precision event log
- `run_report.json` - Structured summary
- `run_report.md` - Human-readable report
- Screenshots at each step
- HTML snapshots at each step
- Playwright trace.zip

**Kroger Artifacts (Now Matching):**
- `steps.jsonl` - Complete event timeline
- `report.json` - Structured data
- `report.md` - Quick summary
- Screenshots at block points
- HTML at block points
- Diagnostic checkpoints with full fingerprint

### 4. **Fingerprint Diagnostics** ✅ IMPLEMENTED

**Walmart Checks:**
- `navigator.webdriver` (should be `false`)
- WebGL vendor/renderer (should be real GPU)
- Hardware concurrency
- Device memory
- Plugins count
- User agent consistency

**Kroger Checks (Now Matching):**
- All of the above
- Plus Akamai-specific cookies (`_abck`, `bm_*`)
- Cookie counts and persistence
- Viewport dimensions

### 5. **Variable Behavioral Timing** ✅ IMPLEMENTED

**Walmart Timing Patterns:**
- Keystroke delays: 80-220ms (variable)
- Post-typing pause: 600-1200ms
- Pre-scroll idle: 2200-3500ms
- Scroll burst pauses: 250-900ms
- Drift reading: 1800-3000ms

**Kroger Timing (Now Matching):**
- Same variable ranges
- Same pause patterns
- Same behavioral simulation

## Walmart-Specific Techniques Not Yet in Kroger

### 1. **Mouse Movement to Search Button**

**Walmart:**
```python
# Move mouse to button naturally before clicking
bbox = button.bounding_box()
mx = bbox["x"] + bbox["width"] * random.uniform(0.3, 0.7)
my = bbox["y"] + bbox["height"] * random.uniform(0.3, 0.7)
page.mouse.move(mx, my, steps=random.randint(6, 12))
random_delay(0.05, 0.12)
button.click()
```

**Status in Kroger:** ✅ Already implemented in main scraper

### 2. **Focus State Management**

**Walmart:**
```python
# Ensure proper focus before Enter key
search_box.focus()
time.sleep(random.uniform(0.1, 0.3))
page.keyboard.press("Enter")
```

**Status in Kroger:** ✅ Already implemented

### 3. **Bezier Curve Mouse Movement**

**Walmart:**
- Uses ghost-cursor library for natural mouse paths
- Bezier curves instead of linear movement
- Variable speed along path

**Status in Kroger:** ❌ Not implemented (could add if needed)

### 4. **Auto CAPTCHA Solver**

**Walmart:**
- Detects PerimeterX "Press and Hold" widget
- Adaptive timing (6.8-10.2s hold)
- Auto-transition detection

**Status in Kroger:** ❌ Not applicable (Akamai uses different CAPTCHA)

## How to Use Walmart Methodology for Kroger Debugging

### Step 1: Run Incremental Tests

```bash
# Start with homepage only
.venv/bin/python3 tools/kroger_step_by_step_test.py --step homepage

# If successful, add search box click
.venv/bin/python3 tools/kroger_step_by_step_test.py --step search_box

# If successful, add typing
.venv/bin/python3 tools/kroger_step_by_step_test.py --step type_search

# If successful, add submission
.venv/bin/python3 tools/kroger_step_by_step_test.py --step submit
```

### Step 2: Analyze Per-Keystroke Logs

If blocked during typing, check `steps.jsonl`:

```bash
# Find the last keystroke before block
grep "keystroke" debug_output/kroger_step_tests/*/steps.jsonl | tail -5
```

Example output:
```json
{"event": "keystroke", "char": "f", "index": 6, "delay_ms": 145}
{"event": "keystroke", "char": "o", "index": 7, "delay_ms": 198}
{"event": "akamai_block_detected", "reason": "access_denied"}
```

**Conclusion:** Character 'o' at index 7 triggered the block.

### Step 3: Check Fingerprint at Block Point

Review diagnostics in `report.md`:

```markdown
## Diagnostics: after_typing

**Navigator:**
- webdriver: `null` ✅
- platform: MacIntel
- hardwareConcurrency: 10

**WebGL:**
- vendor: WebKit
- unmaskedRenderer: ANGLE (Apple, ANGLE Metal Renderer: Apple M1 Pro...) ✅
```

If fingerprint is clean but still blocked → behavioral pattern issue.

### Step 4: Compare Timing Patterns

Check if timing is too consistent:

```bash
# Extract all keystroke delays
grep "keystroke" steps.jsonl | jq .delay_ms

# Should see variable delays like: 156, 203, 89, 178, 145, 198
# NOT consistent like: 100, 100, 100, 100, 100
```

### Step 5: Test on Fresh IP

If all above checks pass but still blocked:

```bash
# Test with mobile hotspot or VPN
.venv/bin/python3 tools/kroger_step_by_step_test.py --step all
```

## Key Differences: PerimeterX vs Akamai

| Aspect | PerimeterX (Walmart) | Akamai (Kroger) |
|--------|---------------------|-----------------|
| **Primary Focus** | Search submission behavior | Behavioral patterns + IP reputation |
| **CAPTCHA Type** | Press-and-hold widget | Standard image CAPTCHA |
| **Detection Speed** | Instant on submit | Can be delayed/gradual |
| **Cookie Names** | `_px*`, `_pxvid` | `_abck`, `bm_*`, `ak_*` |
| **Block Page** | `/blocked` redirect | "Access Denied" error page |
| **Bypass Strategy** | Perfect submission timing | Natural browsing behavior |

## Lessons from Walmart Applied to Kroger

### 1. **Never Assume - Always Test**
Walmart taught us that even "obvious" fixes can fail. Test incrementally.

### 2. **Log Everything**
Per-keystroke logging revealed that specific characters triggered PerimeterX. Same principle applies to Akamai.

### 3. **Timing Variance is Critical**
Consistent timing = instant bot flag. Variable delays (80-220ms) are essential.

### 4. **IP Reputation Matters**
Both systems track IP behavior. Fresh IP = fresh start.

### 5. **Profile Cookies Can Be Poisoned**
Old profiles accumulate "bot scores" in cookies. Fresh profile often solves issues.

## Current Kroger Status with Walmart Methodology

✅ **Implemented:**
- Per-keystroke logging
- Incremental step testing
- Comprehensive forensics
- Fingerprint diagnostics
- Variable behavioral timing
- Human behavior simulation

⏳ **Pending:**
- 24-hour IP cooldown
- Test with fresh IP
- Verify behavioral fixes work

🎯 **Expected Outcome:**
With Walmart's proven methodology now applied to Kroger, we should be able to:
1. Identify exact trigger point if still blocked
2. Isolate fingerprint vs behavioral issues
3. Apply targeted fixes based on data
4. Restore "trusted" status for 5-minute interval scraping

## References

- `docs/WALMART_PERIMETERX_COMPLETE.md` - Full PerimeterX strategy
- `walmart_search_and_capture.py` - Working implementation
- `tools/kroger_step_by_step_test.py` - Kroger test script with Walmart methodology
- `utils/kroger_diagnostics.py` - Diagnostic logging module
