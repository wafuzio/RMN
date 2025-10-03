# Playwright Bootstrap Guide

This document explains how Playwright browsers are installed and managed across different execution contexts (app bundle vs terminal).

## Overview

The RMN app uses Playwright for browser automation. Playwright requires browser binaries (Chromium/Chrome) to be installed in a specific location. This guide covers:
- Where browsers are installed
- How the app bootstrap works
- Environment variables
- Profile management
- Troubleshooting

## Browser Installation Paths

### User-Writable Path (Recommended)
```bash
~/Library/Application Support/RMN/playwright-browsers/
```

This path is:
- ✅ User-writable (no sudo required)
- ✅ Persistent across app updates
- ✅ Shared between app and terminal
- ✅ Backed up with Time Machine

### Environment Variable
```bash
export PLAYWRIGHT_BROWSERS_PATH="$HOME/Library/Application Support/RMN/playwright-browsers"
```

## App Bundle Bootstrap

When the app launches, `bootstrap.py` runs before the GUI:

### Bootstrap Sequence
1. **Set environment variables:**
   ```python
   os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browsers_path
   os.environ["RMN_PROFILES_DIR"] = profiles_path
   ```

2. **Install Chromium if missing:**
   ```python
   if not chromium_exists():
       subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"])
   ```

3. **Launch GUI:**
   ```python
   import keyword_input
   keyword_input.main()
   ```

### Bootstrap Logs
Check `logs/app_launcher_boot.log` for bootstrap status:
```
Bootstrap: Playwright browsers path: /Users/.../playwright-browsers
Bootstrap: Checking Chromium installation...
Bootstrap: Chromium found at: .../chromium-1234/chrome-mac/Chromium.app
```

## Subprocess Environment

When the GUI spawns extractor subprocesses, environment variables must be explicitly passed:

### Adapter Pattern
```python
# In retailers/<retailer>/adapter.py
env = os.environ.copy()
env.setdefault("PYTHONUNBUFFERED", "1")
env.setdefault("PYTHONIOENCODING", "utf-8")

# Explicitly pass Playwright path
if "PLAYWRIGHT_BROWSERS_PATH" in os.environ:
    env["PLAYWRIGHT_BROWSERS_PATH"] = os.environ["PLAYWRIGHT_BROWSERS_PATH"]

proc = subprocess.Popen(cmd, env=env, ...)
```

**Why explicit passing is needed:**
- Subprocesses don't automatically inherit all environment variables
- macOS app bundles have isolated environments
- System Python vs venv Python may have different environments

## Profile Management

### Profile Directory Structure
```
~/Library/Application Support/RMN/profiles/
├── kroger/
│   ├── Default/
│   │   ├── Cookies
│   │   ├── Local Storage/
│   │   └── Session Storage/
│   └── SingletonLock
├── instacart/
│   └── Default/
└── amazon/
    └── Default/
```

### Profile Usage
```python
# Launch persistent context with profile
context = playwright.chromium.launch_persistent_context(
    user_data_dir="~/Library/Application Support/RMN/profiles/kroger",
    headless=False,
    viewport={"width": 1440, "height": 900},
)
```

### Profile Benefits
- ✅ Cookies persist between runs
- ✅ Login sessions maintained
- ✅ Faster subsequent runs (no re-authentication)
- ✅ Per-retailer isolation

## Terminal vs App Execution

### Terminal (venv)
```bash
# Activate venv
source .venv/bin/activate

# Set environment (if not in shell profile)
export PLAYWRIGHT_BROWSERS_PATH="$HOME/Library/Application Support/RMN/playwright-browsers"

# Run extractor
python3 extractors/screenshot_ad_image.py --json ... --profile-dir profiles/kroger
```

**Environment:**
- Uses venv Python
- Inherits shell environment variables
- Direct access to Playwright browsers

### App Bundle
```bash
# Launch app
open "Retail Ad Monitor.app"
```

**Environment:**
- Uses system Python (from app bundle)
- Bootstrap sets environment variables
- Subprocesses need explicit env passing

## Troubleshooting

### Problem: "Executable doesn't exist" Error

**Symptoms:**
- Empty log files
- Process hangs
- Error: `Executable doesn't exist at /path/to/chromium`

**Solutions:**
1. **Check browser installation:**
   ```bash
   ls -la "$HOME/Library/Application Support/RMN/playwright-browsers/chromium-"*
   ```

2. **Reinstall browsers:**
   ```bash
   export PLAYWRIGHT_BROWSERS_PATH="$HOME/Library/Application Support/RMN/playwright-browsers"
   python3 -m playwright install chromium
   ```

3. **Verify environment variable:**
   ```bash
   echo $PLAYWRIGHT_BROWSERS_PATH
   ```

4. **Check bootstrap log:**
   ```bash
   cat logs/app_launcher_boot.log
   ```

### Problem: Subprocess Can't Find Browsers

**Symptoms:**
- Works in terminal, fails in GUI
- Empty subprocess logs
- Process hangs on browser launch

**Solution:**
Add explicit environment passing in adapter:
```python
if "PLAYWRIGHT_BROWSERS_PATH" in os.environ:
    env["PLAYWRIGHT_BROWSERS_PATH"] = os.environ["PLAYWRIGHT_BROWSERS_PATH"]
```

### Problem: Profile Locked

**Symptoms:**
- Error: `Failed to create/open lock file`
- Multiple instances trying to use same profile

**Solutions:**
1. **Close other instances:**
   ```bash
   ps aux | grep "screenshot_"
   kill <PID>
   ```

2. **Remove lock file:**
   ```bash
   rm ~/Library/Application\ Support/RMN/profiles/kroger/SingletonLock
   ```

3. **Use `--no-lock` flag** (for testing only)

### Problem: Cookies Not Persisting

**Symptoms:**
- Login required every run
- Zero cookies after seeding

**Solutions:**
1. **Verify profile directory exists:**
   ```bash
   ls -la ~/Library/Application\ Support/RMN/profiles/kroger/
   ```

2. **Check profile permissions:**
   ```bash
   chmod -R u+rw ~/Library/Application\ Support/RMN/profiles/
   ```

3. **Use persistent context:**
   ```python
   # Correct
   context = p.chromium.launch_persistent_context(user_data_dir=profile_dir)
   
   # Wrong (cookies won't persist)
   browser = p.chromium.launch()
   context = browser.new_context()
   ```

## Best Practices

### 1. Always Use Persistent Context for Retailers
```python
context = p.chromium.launch_persistent_context(
    user_data_dir=profile_dir,
    headless=headless,
    viewport={"width": 1440, "height": 900},
    user_agent=REAL_UA,
)
```

### 2. Seed Cookies on First Run
```python
if len(context.cookies(domain)) == 0:
    # Visit homepage to seed cookies
    page.goto(seed_url, wait_until="commit", timeout=60000)
    page.wait_for_timeout(1200)
```

### 3. Log Cookie Count
```python
cookies = context.cookies("https://www.kroger.com")
print(f"[cookies] kroger.com={len(cookies)} -> {[c['name'] for c in cookies[:6]]}")
```

### 4. Close Context in Finally Block
```python
try:
    # ... extraction logic ...
finally:
    try:
        if context:
            context.close()
    except Exception:
        pass
```

### 5. Pass Environment to Subprocesses
```python
env = os.environ.copy()
if "PLAYWRIGHT_BROWSERS_PATH" in os.environ:
    env["PLAYWRIGHT_BROWSERS_PATH"] = os.environ["PLAYWRIGHT_BROWSERS_PATH"]
subprocess.Popen(cmd, env=env, ...)
```

## Verification Commands

### Check Browser Installation
```bash
python3 -c "
import os
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = os.path.expanduser('~/Library/Application Support/RMN/playwright-browsers')
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch()
    print('✅ Chromium launched successfully')
    browser.close()
"
```

### Check Profile Cookies
```bash
python3 -c "
import os, json
from playwright.sync_api import sync_playwright
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = os.path.expanduser('~/Library/Application Support/RMN/playwright-browsers')
profile = os.path.expanduser('~/Library/Application Support/RMN/profiles/kroger')
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(profile, headless=True)
    cookies = ctx.cookies('https://www.kroger.com')
    print(f'Cookies: {len(cookies)}')
    ctx.close()
"
```

## References

- [Playwright Python Documentation](https://playwright.dev/python/docs/intro)
- [Browser Installation](https://playwright.dev/python/docs/browsers)
- [Persistent Context](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-persistent-context)
