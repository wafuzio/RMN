# Kroger Akamai Bot Detection - Diagnostic Guide

## Overview

Kroger uses **Akamai Bot Manager** for bot detection. This is different from Walmart's PerimeterX system and requires different debugging strategies.

**Key Difference**: Akamai is more focused on rate limiting and IP reputation, while PerimeterX focuses on behavioral fingerprinting.

## Current Status

Based on memory from Mar 3, 2026:
- ✅ Kroger was working fine with `kroger_clean_profile`
- ❌ Chrome 145 update broke 9 launch args causing immediate crashes
- ⚠️ Rapid-fire testing (~15 launches in 1 hour) triggered Akamai rate limiter
- ✅ Profile is NOT burned - still valid after 30-60 minute cooldown
- ✅ Launch args fixed to Chrome 145-compatible set

## Akamai Detection Vectors

### 1. Rate Limiting (PRIMARY)
**What they check**:
- Requests per minute from same IP
- Requests per hour from same IP
- Pattern of identical requests
- Time between requests

**Our observations**:
- ~15 rapid launches in 1 hour = rate limit triggered
- Rate limits clear in 30-60 minutes
- Profile cookies remain valid (not burned)

**Mitigation**:
- Wait 2-3 minutes between scrape attempts
- Use residential proxies for production
- Don't rapid-fire test in development

### 2. Browser Fingerprint
**What they check**:
- User-Agent consistency
- WebGL renderer (consumer vs professional GPU)
- navigator.webdriver flag
- Chrome args that indicate automation

**Our implementation**:
- ✅ Real Chrome via executable path
- ✅ Persistent profile (user_data_dir)
- ✅ Chrome 145-compatible args only
- ✅ No automation flags

**Chrome 145 Compatible Args** (CRITICAL):
```python
args = [
    '--no-sandbox',
    '--disable-dev-shm-usage',
    '--disable-infobars',
    '--no-first-run',
    '--disable-default-apps',
    '--disable-backgrounding-occluded-windows',
    '--window-size=1280,720',
    '--disable-notifications',
    '--disable-quic',
    '--noerrdialogs',
]
```

**REMOVED Args** (Chrome 145 crashes with these):
```python
# DO NOT USE - Chrome 145 incompatible
'--disable-blink-features=AutomationControlled',  # Crashes
'--disable-web-security',                          # Crashes
'--disable-popup-blocking',                        # Crashes
'--disable-translate',                             # Crashes
'--disable-background-timer-throttling',           # Crashes
'--disable-renderer-backgrounding',                # Crashes
'--disable-restore-session-state',                 # Crashes
'--disable-ipc-flooding-protection',               # Crashes
'--disable-focus-on-load',                         # Crashes
```

### 3. Profile & Cookie Reputation
**What they check**:
- Akamai Bot Manager cookies (ak_bmsc, bm_mi, bm_sv, bm_sz)
- Cookie age and persistence
- Login session validity

**Our implementation**:
- ✅ Persistent profile at `~/ChromeProfiles/kroger_clean_profile`
- ✅ Cookies saved via `Kroger_login.py`
- ✅ Session persists across runs

**Profile Health**:
- Check for Akamai cookies: `ak_bmsc`, `bm_mi`, `bm_sv`, `bm_sz`
- These are normal - Akamai uses them for tracking
- Only concern if they contain "blocked" or "denied" values

### 4. Behavioral Patterns
**What they check**:
- Immediate search after page load (bot-like)
- No mouse movement
- Consistent timing patterns
- Missing human-like delays

**Our implementation**:
- ✅ Human-like typing delays (per-character)
- ✅ Random delays between actions
- ✅ Popup dismissal (looks human)
- ⚠️ Could improve: mouse movement, scroll patterns

## Block Detection Patterns

### Akamai Access Denied
```html
<title>Access Denied</title>
```

### Akamai CDN Error
```
errors.edgesuite.net
```

### Permission Denied
```
You don't have permission to access
```

### Reference Number Block
```
Reference #18.xxxxxxxx.xxxxxxxxx.xxxxxxxx
```

## Step-by-Step Isolation Testing

Use the diagnostic script to isolate exactly where Akamai triggers:

```bash
# Test just homepage load
.venv/bin/python3 tools/kroger_step_by_step_test.py --step homepage

# Test homepage + search box click
.venv/bin/python3 tools/kroger_step_by_step_test.py --step search_box

# Test homepage + search box + typing
.venv/bin/python3 tools/kroger_step_by_step_test.py --step type_search

# Test full flow including submission
.venv/bin/python3 tools/kroger_step_by_step_test.py --step submit

# Run all steps sequentially (stops at first block)
.venv/bin/python3 tools/kroger_step_by_step_test.py --step all
```

### What Each Step Tests

1. **homepage**: Just loads kroger.com
   - Tests: IP reputation, basic fingerprint
   - If blocked here: IP is flagged or profile is burned

2. **search_box**: Clicks search box
   - Tests: DOM interaction, focus events
   - If blocked here: Click pattern is suspicious

3. **type_search**: Types keyword
   - Tests: Keystroke timing, input events
   - If blocked here: Typing pattern is robotic

4. **submit**: Submits search
   - Tests: Form submission, navigation
   - If blocked here: Submission method is detectable

### Diagnostic Output

Each test creates a timestamped directory in `debug_output/kroger_step_tests/` with:

- **steps.jsonl**: Microsecond-precision event log
- **report.json**: Structured diagnostic data
- **report.md**: Human-readable summary
- **step1_homepage_screenshot.png**: Visual state at each step
- **step1_homepage_page.html**: HTML at each step
- **blocked_*.png/html**: Forensics if block detected

### Reading the Reports

**report.md** contains:
- Outcome (success/blocked/error)
- Block reason if detected
- Timing metrics for each step
- Navigator diagnostics (webdriver, platform, etc.)
- WebGL fingerprint (vendor, renderer)
- Cookie count and names
- Akamai-specific cookies if present

**steps.jsonl** contains:
- Every action with microsecond timestamp
- Elapsed time from test start
- Event metadata (URLs, selectors, errors)

## Comparison: Akamai vs PerimeterX

| Aspect | Akamai (Kroger) | PerimeterX (Walmart) |
|--------|-----------------|----------------------|
| **Primary Detection** | Rate limiting, IP reputation | Behavioral fingerprinting |
| **Block Speed** | Immediate on rate limit | Can be delayed (trust score) |
| **Profile Burn** | Rare (IP-based) | Common (behavioral) |
| **Cooldown** | 30-60 minutes | Hours to days |
| **CAPTCHA** | Rare | Common (Press & Hold) |
| **Best Defense** | Slow down, use proxies | Perfect fingerprint, human behavior |

## Troubleshooting

### Issue: "Browser window not found" or Chrome crashes immediately

**Cause**: Using Chrome 145-incompatible launch args

**Solution**: 
1. Check `kroger_search_and_capture.py` launch args
2. Remove any args from the "REMOVED Args" list above
3. Use only the "Chrome 145 Compatible Args"

### Issue: "Access Denied" on homepage

**Cause**: IP rate limited or flagged

**Solution**:
1. Wait 30-60 minutes
2. Use different IP (VPN/proxy)
3. Check if rapid testing triggered rate limit

### Issue: Works manually but fails in script

**Cause**: Behavioral detection (timing, mouse, etc.)

**Solution**:
1. Run step-by-step test to isolate trigger point
2. Add more human-like delays
3. Add mouse movement between actions
4. Randomize timing patterns

### Issue: Profile seems burned

**Cause**: Unlikely with Akamai (IP-based, not profile-based)

**Solution**:
1. Check if it's actually IP rate limit (wait 1 hour)
2. Try same profile with different IP
3. If truly burned, create fresh profile with `Kroger_login.py`

## Best Practices

### Development
- ✅ Wait 2-3 minutes between test runs
- ✅ Use step-by-step test to isolate issues
- ✅ Check diagnostics before assuming profile is burned
- ❌ Don't rapid-fire test (triggers rate limit)
- ❌ Don't apply Walmart PerimeterX strategies to Kroger

### Production
- ✅ Use residential proxies
- ✅ Rotate IPs between runs
- ✅ Wait 5-10 minutes between searches
- ✅ Monitor for rate limit patterns
- ❌ Don't use datacenter IPs (flagged)
- ❌ Don't scrape same keyword repeatedly

## Diagnostic Workflow

When Kroger scraping fails:

1. **Check recent activity**
   - Did you run 10+ tests in the last hour?
   - If yes: Wait 1 hour, try again

2. **Run step-by-step test**
   ```bash
   .venv/bin/python3 tools/kroger_step_by_step_test.py --step all
   ```

3. **Review diagnostics**
   - Check `report.md` for block reason
   - Check `steps.jsonl` for timing patterns
   - Look for Akamai cookies in diagnostics

4. **Identify trigger point**
   - If blocked at homepage: IP issue
   - If blocked at search_box: Click detection
   - If blocked at type_search: Keystroke detection
   - If blocked at submit: Form submission detection

5. **Apply targeted fix**
   - IP issue: Wait or change IP
   - Behavioral issue: Add delays, randomization
   - Fingerprint issue: Check Chrome args, WebGL

## Key Differences from Walmart

**DO NOT** apply these Walmart strategies to Kroger:
- ❌ PerimeterX-specific CAPTCHA solving
- ❌ Press & Hold detection
- ❌ PX beacon monitoring
- ❌ Stealth plugins (Akamai detects them differently)

**DO** apply these universal strategies:
- ✅ Real Chrome (not Chromium)
- ✅ Persistent profile
- ✅ Human-like timing
- ✅ Consumer GPU (not professional)
- ✅ Residential proxies

## Files

- `kroger_search_and_capture.py` - Main scraper
- `Kroger_login.py` - Profile setup and cookie management
- `tools/kroger_step_by_step_test.py` - Diagnostic testing script
- `utils/profile_health.py` - Profile health monitoring (shared)

## Next Steps

If you're experiencing Kroger bot detection issues:

1. Run the step-by-step test to isolate the trigger
2. Review the diagnostic reports
3. Check if it's rate limiting (most common)
4. Wait appropriate cooldown period
5. Apply targeted fixes based on diagnostics

## See Also

- `docs/WALMART_PERIMETERX_COMPLETE.md` - Walmart's different system
- `utils/profile_health.py` - Shared health monitoring
- Memory: Chrome 145 arg fixes (Mar 3, 2026)
