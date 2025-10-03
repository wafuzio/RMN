# Common Issues (and Fixes)

This document catalogs recurring problems across retailers and their proven solutions.

## Headless fails, headed works (Kroger)

**Cause:** CDN/anti-automation fingerprint blocks fetch/navigation in headless mode.

**Fix:**
- Use **headed-but-hidden policy** for this extractor
- Add minimization flags:
  ```python
  args=[
      "--start-minimized",
      "--window-position=0,0",
      "--window-size=10,10",
      "--disable-renderer-backgrounding",
      "--disable-backgrounding-occluded-windows",
  ]
  ```
- Use **nav-first capture** (page.goto → screenshot)
- Add **SRP element-screenshot fallback**

**Example:** Kroger extractor (see `retailers/kroger/adapter.py`)

---

## Images time out with context.request

**Cause:** No session cookies or missing Referer header.

**Fix:**
1. **Seed cookies from srp_url:**
   ```python
   seed_candidates = [
       srp_url,  # from JSON
       "https://www.<retailer>.com/search?query=milk",
       "https://www.<retailer>.com/",
   ]
   for seed in [u for u in seed_candidates if u]:
       page.goto(seed, wait_until="commit", timeout=60000)
       page.wait_for_timeout(1200)
       if len(context.cookies(domain)) > 0:
           break
   ```

2. **Set Referer + UA headers:**
   ```python
   context.set_extra_http_headers({
       "Referer": srp_url or "https://www.<retailer>.com/",
       "User-Agent": REAL_UA,
       "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
   })
   ```

3. **Bail quickly to nav-screenshot if !2xx:**
   ```python
   try:
       resp = context.request.get(image_url, timeout=5000)
       if not resp.ok:
           # Fall back to navigation immediately
           page.goto(image_url, wait_until="commit")
   except Exception:
       # Fall back to navigation
       page.goto(image_url, wait_until="commit")
   ```

**Log indicators:**
- `[fast] context.request failed or timed out`
- `[nav] Opening image URL in browser tab...`

---

## JSON missing source_url

**Cause:** Writer did not persist SRP URL when saving run results.

**Fix:** Write `"source_url": page.url` in run_results JSON:

```python
# In scraper (e.g., kroger_search_and_capture.py)
run_results = {
    "count": len(ads),
    "keyword": keyword,
    "search_term": search_term,
    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "source_file": html_path,
    "source_url": page.url,  # ← ADD THIS
    "results": results,
}
```

**Why it matters:**
- Extractor uses it for Referer header
- Extractor uses it for cookie seeding
- Without it, falls back to generic URLs

**Log indicator:**
- `[session] srp_url=<none>`

---

## "Two logs" for one scrape

**Cause:** Extractor returned 0 (no images saved) with exit code 0. Orchestrator retried silently.

**Fix:** Exit with code 1 when `saved_count == 0`:

```python
def process_images(...) -> int:
    saved_count = 0
    # ... extraction logic ...
    return saved_count

def main() -> int:
    saved = process_images(...)
    if saved == 0:
        print("❌ No images saved; exiting with failure for orchestrator.")
        return 1
    return 0
```

**Log indicators:**
- Multiple logs with same timestamp
- Empty log files (process hung)
- GUI shows retry attempts

---

## Directory gore (wrong subfolders under retailer)

**Cause:** Pre-create loop without per-retailer gating.

**Example of bad code:**
```python
# Wrong - creates Kroger folders for all retailers
for folder in ["TOA", "Skyscraper", "Carousel"]:
    os.makedirs(os.path.join(output_dir, folder), exist_ok=True)
```

**Fix:** Use `core/paths.ensure_subdir()` + `RETAILER_TAXONOMY`:

```python
# Correct
from core.paths import output_dir_for
output_dir = output_dir_for(base, retailer, client)
# Folders already created based on retailer taxonomy
```

**Cleanup:**
```bash
python scripts/maintenance/cleanup_taxonomy.py
```

**Validation:**
```bash
python scripts/docs/update_docs.py --check
```

**See:** `docs/ARTIFACT_TAXONOMY.md`

---

## Subprocess can't find Playwright browsers

**Cause:** `PLAYWRIGHT_BROWSERS_PATH` not passed to subprocess environment.

**Symptoms:**
- Works in terminal, fails in GUI
- Empty subprocess logs
- Process hangs on browser launch

**Fix:** Explicitly pass environment variable in adapter:

```python
# In retailers/<retailer>/adapter.py
env = os.environ.copy()
if "PLAYWRIGHT_BROWSERS_PATH" in os.environ:
    env["PLAYWRIGHT_BROWSERS_PATH"] = os.environ["PLAYWRIGHT_BROWSERS_PATH"]

proc = subprocess.Popen(cmd, env=env, ...)
```

**Verification:**
```bash
# Check bootstrap log
cat logs/app_launcher_boot.log

# Check browser installation
ls -la "$HOME/Library/Application Support/RMN/playwright-browsers/chromium-"*
```

**See:** `docs/PLAYWRIGHT_BOOTSTRAP.md`

---

## Profile locked (multiple instances)

**Cause:** Multiple processes trying to use same profile simultaneously.

**Symptoms:**
- Error: `Failed to create/open lock file`
- `SingletonLock` file exists

**Fix:**
1. **Close other instances:**
   ```bash
   ps aux | grep "screenshot_"
   kill <PID>
   ```

2. **Remove lock file:**
   ```bash
   rm ~/Library/Application\ Support/RMN/profiles/<retailer>/SingletonLock
   ```

3. **Use conflict detection** (scheduler prevents overlaps)

**Prevention:**
- Use scheduler's 5-minute conflict window
- Don't run manual extractions during scheduled runs
- Use `--no-lock` only for debugging

---

## Cookies not persisting

**Cause:** Not using persistent context or profile permissions issue.

**Symptoms:**
- Login required every run
- Zero cookies after seeding
- `[cookies] <domain>=0`

**Fix:**
1. **Use persistent context:**
   ```python
   # Correct
   context = p.chromium.launch_persistent_context(
       user_data_dir=profile_dir,
       ...
   )
   
   # Wrong (cookies won't persist)
   browser = p.chromium.launch()
   context = browser.new_context()
   ```

2. **Check profile permissions:**
   ```bash
   chmod -R u+rw ~/Library/Application\ Support/RMN/profiles/
   ```

3. **Verify profile directory exists:**
   ```bash
   ls -la ~/Library/Application\ Support/RMN/profiles/<retailer>/
   ```

**See:** `docs/PLAYWRIGHT_BOOTSTRAP.md` → Profile Management

---

## Navigation to image times out

**Cause:** Using `wait_until="domcontentloaded"` on image documents.

**Symptoms:**
- Timeout after 20-30 seconds
- Works for HTML pages, fails for direct image URLs

**Fix:** Use `wait_until="commit"` for image documents:

```python
# Correct for images
page.goto(image_url, wait_until="commit", timeout=30000)
page.wait_for_timeout(300)  # Brief grace period
page.screenshot(path=output_path)

# Wrong (will timeout)
page.goto(image_url, wait_until="domcontentloaded", timeout=30000)
```

**Why:** Image documents don't fire `DOMContentLoaded` event. The `commit` event fires when the response is received.

---

## Empty log files

**Cause:** Process hangs before writing any output.

**Common reasons:**
1. Import error (syntax error in code)
2. Playwright browser not found
3. Profile lock
4. Missing environment variable

**Debug steps:**
1. **Test import:**
   ```bash
   python3 -c "from extractors.screenshot_ad_image import main; print('OK')"
   ```

2. **Run manually (headed):**
   ```bash
   python3 extractors/screenshot_ad_image.py --json ... --profile-dir profiles/<retailer>
   ```

3. **Check for hung processes:**
   ```bash
   ps aux | grep screenshot_
   ```

4. **Check bootstrap log:**
   ```bash
   cat logs/app_launcher_boot.log
   ```

---

## References

- **Onboarding:** `docs/RETAILER_ONBOARDING_CHECKLIST.md`
- **Taxonomy:** `docs/ARTIFACT_TAXONOMY.md`
- **Playwright:** `docs/PLAYWRIGHT_BOOTSTRAP.md`
- **Devlog:** `docs/DEVLOG.md`
