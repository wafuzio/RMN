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
1. **Seed cookies from srp_url (retailer-aware):**
   ```python
   # Load SRP URL from JSON
   srp_url = load_srp_url(json_path)
   retailer = infer_retailer_from_output(output_dir)
   
   # Build seed candidates (NO hardcoded URLs!)
   seed_candidates = [srp_url] if srp_url else []
   seed_candidates.append(retailer_homepage(retailer))
   
   for seed in seed_candidates:
       page.goto(seed, wait_until="commit", timeout=60000)
       page.wait_for_timeout(1200)
       if len(context.cookies(domain)) > 0:
           break
   ```
   
   **⚠️ NEVER hardcode fallback URLs** - use retailer-aware helpers instead.

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

## JSON missing source_url / url / retailer

**Cause:** Writer did not persist SRP URL and retailer when saving run results.

**Fix:** Write `url`, `srp_url`, and `retailer` in run_results JSON:

```python
# In scraper (e.g., kroger_search_and_capture.py, instacart_search_and_capture.py)
search_url = page.url  # Get final URL after navigation

run_results = {
    "count": len(ads),
    "keyword": keyword,
    "search_term": search_term,
    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "source_file": html_path,
    "retailer": "kroger",      # ← ADD THIS (for downstream tools)
    "url": search_url,         # ← ADD THIS (primary for extractors)
    "srp_url": search_url,     # ← ADD THIS (alias for compatibility)
    "results": results,
}
```

**Why it matters:**
- Extractor uses `url`/`srp_url` for Referer header
- Extractor uses it for cookie seeding
- `retailer` enables retailer-aware fallbacks
- Without these, extractor falls back to generic homepage

**Log indicators:**
- `[session] srp_url=<none>`
- `⚠️ No SRP URL found in JSON; seeding cookies with retailer homepage`

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

## Profile not passed from adapter to scraper

**Cause:** When app launched from Finder, environment variables aren't inherited. Search phase runs without cookies.

**Symptoms:**
- Login prompts appear even after authentication
- Search works from terminal, fails from app
- Different sessions for search vs extraction

**Fix:** Inject `ctx.profile_dir` into environment in adapter's `search_and_capture()`:

```python
# In retailers/<retailer>/adapter.py
def search_and_capture(self, keyword: str, ctx) -> bool:
    from retailer_search_and_capture import search_and_capture
    
    # CRITICAL: Inject profile dir so scraper uses same session
    if ctx.profile_dir and os.path.isdir(ctx.profile_dir):
        os.environ["RETAILER_PROFILE_DIR"] = ctx.profile_dir
        print(f"Injected RETAILER_PROFILE_DIR into env: {ctx.profile_dir}")
    else:
        print("⚠️ ctx.profile_dir missing; scraper may run without cookies")
    
    return search_and_capture(keyword, ctx.output_dir)
```

**Why it matters:**
- Ensures both search and extraction use same cookie jar
- Prevents HTTP/2 resets and CDN rejections
- Critical for app bundle launches

**See:** `docs/ADDING_NEW_RETAILER.md` → Profile Handoff

---

## Organic search fails, direct navigation used

**Cause:** Search input selector too narrow or page not ready.

**Symptoms:**
- Logs show "Search box interaction failed"
- "Falling back to direct navigation"
- May trigger bot detection or login modals

**Fix:** Use broad selectors and wait for page readiness:

```python
# 1. Wait for page to be ready
page.goto(homepage_url, wait_until='domcontentloaded')
page.wait_for_load_state("load")  # More conservative

# 2. Use broad selector union
search_selector = (
    "[data-testid='search-bar-input'], "
    "input[type='search'], "
    "input[placeholder*='Search'], "
    "input[aria-label*='Search'], "
    "[role='search'] input"
)
search_input = page.locator(search_selector).first

# 3. Wait for visibility
search_input.wait_for(state="visible", timeout=6000)

# 4. Click, fill, submit
search_input.click()
search_input.fill(keyword)
page.keyboard.press("Enter")

# 5. Wait for navigation
page.wait_for_url('**/s?k=**', timeout=12000)
```

**Additional checks:**
- Dismiss cookie banners first
- Click search toggle if input is gated
- Scroll input into view if needed
- Always have fallback to direct navigation

**See:** `docs/ADDING_NEW_RETAILER.md` → Organic Search vs Direct Navigation

---

## Image extraction reports zero counts

**Cause:** Time window too strict or checking wrong folder names.

**Symptoms:**
- "Extraction incomplete: No TOA/Skyscraper produced"
- Images exist in filesystem but adapter reports 0
- Works sometimes, fails other times (timing issue)

**Fix:** Use forgiving time window and check multiple folders:

```python
def extract_images(self, json_path: str, html_path: str, ctx) -> dict:
    # ... run extractor subprocess ...
    
    # Use 5-minute slack window (not 1-2 seconds!)
    slack_seconds = 300
    horizon = pair_start - slack_seconds
    
    def recent_pngs(leaf: str) -> list:
        d = os.path.join(ctx.output_dir, leaf)
        return [
            p for p in glob.glob(os.path.join(d, "*.png"))
            if os.path.getmtime(p) >= horizon
        ]
    
    # Check multiple folder names (retailer-specific + legacy + Main)
    toa_files = []
    toa_files += recent_pngs("Shoppable_Display_Ads")  # Instacart
    toa_files += recent_pngs("Top_Banner")             # Walmart
    toa_files += recent_pngs("TOA")                    # Kroger/legacy
    toa_files += recent_pngs("Main")                   # Some extractors
    
    # Log what we counted for debugging
    with open(log_path, 'a') as lf:
        lf.write(f"\nCounted files (since {datetime.fromtimestamp(horizon).isoformat()}):\n")
        lf.write(f"  TOA-like: {len(toa_files)}\n")
        for p in sorted(toa_files)[:10]:
            lf.write(f"    - {p}\n")
    
    return {"toa": len(toa_files), "sky": len(sky_files), "car": 0, "log": log_path}
```

**Debug:**
```bash
# Check what files actually exist
find output/<retailer>/<client> -name "*.png" -mtime -1 -ls

# Check extractor log for counted files
tail -50 logs/<retailer>/image_extract_*.log
```

**See:** `docs/ADDING_NEW_RETAILER.md` → Robust Image Counting

---

## Login modal appears after authentication

**Cause:** Direct URL navigation breaks session state or triggers bot detection.

**Symptoms:**
- Login modal on search results page
- Works with manual browsing, fails in automation
- Session cookies present but modal still appears

**Fix:** Use organic search instead of direct navigation (see "Organic search fails" above).

**Alternative:** Add interactive login handling:

```python
def _is_login_modal_visible(page):
    login_selectors = [".login-modal", "[data-testid='authModal']"]
    for sel in login_selectors:
        el = page.query_selector(sel)
        if el and el.is_visible():
            return True
    return False

def _prompt_user_login(page, log, max_wait_sec=300):
    page.bring_to_front()
    log("⚠️ Login required: Please complete login in the browser window.")
    
    deadline = time.time() + max_wait_sec
    while time.time() < deadline:
        if not _is_login_modal_visible(page):
            log("✅ Login completed — continuing.")
            return True
        page.wait_for_timeout(1000)
    
    log("❌ Login timeout")
    return False

# Use after navigation
if _is_login_modal_visible(page):
    if not _prompt_user_login(page, log):
        return False
```

**See:** `docs/ADDING_NEW_RETAILER.md` → Interactive Login Handling

---

## References

- **Onboarding:** `docs/RETAILER_ONBOARDING_CHECKLIST.md`
- **Taxonomy:** `docs/ARTIFACT_TAXONOMY.md`
- **Playwright:** `docs/PLAYWRIGHT_BOOTSTRAP.md`
- **Devlog:** `docs/DEVLOG.md`
