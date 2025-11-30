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

## Playwright locator misuse – `'Locator' object is not callable`

**Cause:** Playwright's sync API exposes `.first`, `.last`, and `.nth` as properties. Calling them like `.first()` or chaining `.first().locator(...).count()` calls the locator object, raising `'Locator' object is not callable`.

**Fix:**
- Call `.count()` / `.all()` on the parent locator *before* narrowing.
- Access the property handle via `locator.first` (no parentheses) and operate on that handle.
- Ensure event handlers also use properties (`m.type`, `m.text`, `r.method`, `r.url`).

```python
links = container.locator('a[aria-label]')
if links.count() > 0:
    link = links.first
    label = (link.get_attribute('aria-label') or '').strip()
```

**Logs:** `sbv: screenshot fail -> 'Locator' object is not callable`

---

## F-string backslash errors (`f-string expression part cannot include a backslash`)

**Cause:** Embedding escaped quotes/locators directly inside an f-string expression, e.g. `f"{page.locator('*[cel_widget_id^=\"VIDEO\"]').count()}"`.

**Fix:** Compute locator counts in variables first, then reference those variables in the f-string. Keeps code readable and avoids illegal backslashes.

```python
count = page.locator('*[cel_widget_id^="VIDEO_SINGLE_PRODUCT"]').count()
log(f"sbv markers -> VIDEO_SINGLE_PRODUCT: {count}")
```

---

## Unwanted "garbage" SBV MP4s

**Cause:** A global `page.on("response", ...)` hook dumped every MP4 response into `Sponsored_Brand_Video/`, including analytics beacons and unrelated ads.

**Fix:** Remove the interceptor and only save MP4s via the canonical SBV download path (where we already have the widget context and filename). This keeps output clean and canonically named.

---

## SBV detection misses wrappers/span nodes

**Symptoms:** Legit SBV modules (e.g., `<span data-component-type="sbv-video-single-product">`) never appear in JSON/screenshots.

**Fix:**
1. Broaden `sbv_selectors` to include `*[cel_widget_id*="sbv-video-single-product"]`, `sb-video-single-product`, `sbv-search-*`, `loom-desktop-*`, and `sb-video-product-collection` variants (no `div` restriction).
2. For each matched element, expand wrappers into inner SBV cards via `el.locator('[data-component-type="sbv-video-single-product"], *[cel_widget_id^="VIDEO_SINGLE_PRODUCT"], …')` before deduping.
3. Capture `data-index`, `data-uuid`, `cel_widget_id`, and `data-cel-widget` from both the slot wrapper and the inner widget; include them in `metadata` and dedupe sets (`seen_sbv_widget_uuids`).
4. Add marker logging (counts per selector family) to confirm what’s present on the page.

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

---

## Stale lock files blocking extraction

**Cause:** Process crashed/killed without cleaning up lock file.

**Symptoms:**
- Extraction hangs indefinitely
- Log shows "Waiting for lock..."
- No progress after 5+ minutes

**Fix:**
```bash
# Find and remove stale locks
find logs/<retailer>/locks/ -name "*.lock" -mmin +30 -delete

# Or manually:
rm logs/<retailer>/locks/*_image_extraction.lock
```

**Prevention:**
- Use proper signal handling in extractors
- Add timeout to lock acquisition (5 minutes max)
- Clean locks on startup

---

## Selector changes breaking extractors

**Cause:** Retailer updated their HTML structure or CSS classes.

**Symptoms:**
- Extractor returns 0 ads
- Log shows "No elements found for selector"
- Screenshots show page loaded but no ads captured

**Debug steps:**
1. Check saved HTML in `runs/` directory
2. Search for ad elements manually in HTML
3. Update selectors in extractor
4. Test with `--headed` flag to see what's actually on page

**Common patterns:**
- Class names change: `.ProductCard` → `.ProductCard-v2`
- Data attributes added: `div.ad` → `div[data-testid="ad"]`
- Structure changes: Direct child → nested deeper

**Prevention:**
- Use multiple selector fallbacks
- Prefer data attributes over classes when available
- Document selector rationale in comments

---

## Image URLs returning 403/404

**Cause:** CDN requires specific headers or cookies, or URL expired.

**Symptoms:**
- `context.request.get()` returns 403 or 404
- Images work in browser but not in extractor
- Works initially, fails on retry

**Fix:**
1. **Check if URL is time-limited:**
   - Look for tokens/signatures in URL
   - Extract fresh URLs from page instead of JSON

2. **Add required headers:**
   ```python
   context.set_extra_http_headers({
       "Referer": srp_url,
       "User-Agent": REAL_UA,
       "Accept": "image/*",
   })
   ```

3. **Seed cookies from SRP:**
   ```python
   page.goto(srp_url, wait_until="commit")
   page.wait_for_timeout(1000)
   # Now context has cookies
   ```

4. **Fall back to navigation:**
   ```python
   try:
       resp = context.request.get(url, timeout=5000)
       if not resp.ok:
           page.goto(url, wait_until="commit")
   except:
       page.goto(url, wait_until="commit")
   ```

---

## Process hangs during scrape

**Cause:** Waiting for element that never appears, or infinite retry loop.

**Symptoms:**
- No log output for 5+ minutes
- CPU usage near 0%
- Process doesn't respond to Ctrl+C

**Common causes:**
1. **Missing timeout on wait:**
   ```python
   # Wrong - waits forever
   page.wait_for_selector(".ad")
   
   # Correct - times out after 30s
   page.wait_for_selector(".ad", timeout=30000)
   ```

2. **Infinite retry without bail:**
   ```python
   # Wrong - retries forever
   while not success:
       success = try_scrape()
   
   # Correct - bail after N attempts
   for attempt in range(MAX_RETRIES):
       if try_scrape():
           break
   else:
       log("❌ Max retries exceeded")
       return False
   ```

3. **Deadlock on lock file:**
   - Check `logs/<retailer>/locks/` for stale locks
   - Add timeout to lock acquisition

**Debug:**
```bash
# Find hung process
ps aux | grep python | grep scrape

# Kill it
kill -9 <PID>

# Check what it was waiting for
tail -100 logs/<retailer>/keyword_input.log
```

---

## Screenshots desync from HTML/JSON data

**Cause:** Screenshots taken in separate page load from data extraction, causing mismatches due to dynamic content.

**Symptoms:**
- Ad screenshots show different content than JSON data
- Ad count mismatch between JSON and screenshot count
- Screenshots missing ads that appear in JSON
- Virtualized content differs between loads

**Fix:** Integrate screenshot capture directly into scraper during same page load:

```python
# In main scraper (e.g., instacart_search_and_capture.py)
for elem in ad_elements:
    # Extract data
    ad_info = extract_ad_data(elem)
    
    # Take screenshot IMMEDIATELY (same page load!)
    try:
        elem.scroll_into_view_if_needed()
        page.wait_for_timeout(250)
        elem.screenshot(path=screenshot_path)
        ad_info["screenshot"] = screenshot_path
    except Exception as e:
        print(f"Screenshot failed: {e}")
    
    # Add to results
    ad_data["ads"].append(ad_info)

# Save HTML/JSON after all extraction
html_content = page.content()
save_html(html_content)
save_json(ad_data)
```

**Why it matters:**
- Ensures perfect synchronization between data and visuals
- Prevents virtualization/lazy-loading mismatches
- Critical for dynamic SPAs like Instacart

**See:** `docs/INSTACART_INTEGRATION.md` → Synchronized Screenshot Capture

---

## Full-page screenshot causes DOM reflow

**Cause:** `page.screenshot(full_page=True)` resizes viewport, triggering virtualization to remount/unmount content.

**Symptoms:**
- Ads disappear from full-page screenshot
- Different ad layout in full-page vs individual screenshots
- Sticky headers repeat throughout screenshot
- Tile seams visible in stitched screenshots

**Fix:** Use CDP's `Page.captureScreenshot` with `captureBeyondViewport=true`:

```python
def capture_fullpage_static_no_resize(context, page, out_path):
    """Capture entire page without viewport resize using CDP"""
    client = context.new_cdp_session(page)
    
    # Disable animations for clean capture
    page.add_style_tag(content="""
      * { animation: none !important; transition: none !important; }
      html { scroll-behavior: auto !important; }
    """)
    
    # Single-pass capture (no viewport resize)
    shot = client.send("Page.captureScreenshot", {
        "format": "png",
        "fromSurface": True,
        "captureBeyondViewport": True
    })
    
    data = base64.b64decode(shot["data"])
    with open(out_path, "wb") as f:
        f.write(data)
    return out_path

# Before capture, warm up lazy content
vh = page.evaluate("() => window.innerHeight")
doc_h = page.evaluate("() => document.body.scrollHeight")
step = int(vh * 0.85)
y = 0
while y < doc_h - vh:
    page.evaluate(f"window.scrollTo(0, {y})")
    page.wait_for_timeout(250)
    y += step

# Return to top and capture
page.evaluate("window.scrollTo(0, 0)")
capture_fullpage_static_no_resize(context, page, output_path)
```

**Benefits:**
- No viewport resize = no DOM reflow
- Single compositor pass = no seams
- Sticky headers handled automatically
- Faster than tile stitching

**See:** `docs/INSTACART_INTEGRATION.md` → CDP Static Full-Page Screenshots

---

## Full-page screenshot has inconsistent width (header/footer wider than body)

**Cause:** Large viewport (e.g., 1920x1080) causes responsive layouts to render header/footer at full width while body content uses a narrower max-width container.

**Symptoms:**
- Header and footer extend to full viewport width
- Body content is narrower, creating visible margins
- Screenshot looks unprofessional with inconsistent widths
- Gray/white margins visible on sides of body content

**Fix:** Use the same viewport size as the main scraper (1280x720):

```python
# Browser args - match main scraper viewport
browser_args = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--window-size=1280,720",  # ← Critical: match viewport
    # ... other args
]

# Launch with matching viewport
context = p.chromium.launch_persistent_context(
    user_data_dir=profile_dir,
    headless=False,
    viewport={"width": 1280, "height": 720},  # ← Must match window-size
    device_scale_factor=1.0,
    args=browser_args,
)
```

**Why it works:**
- 1280px is a common breakpoint where most sites render body at full width
- Header/footer/body all render at same width
- Matches what main scraper uses for search results pages
- Consistent screenshots across all retailers

**Applied to:** `scripts/screenshot_front_page.py` for front page captures

---

## Ads don't load (viewability gates)

**Cause:** Ad creative requires dwell time in viewport (600-1000ms) before mounting.

**Symptoms:**
- Screenshots show blank ad containers
- Video ads show loading spinner
- Ad count correct but screenshots empty
- Works with manual browsing, fails in automation

**Fix:** Wait for ad creative to load before screenshot:

```python
def _wait_for_ad_creative_loaded(page, el, timeout_ms=1200):
    """Wait for images/video inside ad element to load"""
    try:
        page.wait_for_function(
            """(e) => {
               const vw = window.innerWidth, vh = window.innerHeight;
               const r = e.getBoundingClientRect();
               const inView = (r.bottom > 0 && r.right > 0 && r.top < vh && r.left < vw);
               if (!inView) return false;
               const imgs = Array.from(e.querySelectorAll('img'));
               const okImg = imgs.length === 0 || imgs.every(i => i.complete && i.naturalWidth > 0);
               const vid = e.querySelector('video');
               const okVid = !vid || (vid.readyState >= 2);
               return okImg && okVid;
            }""",
            el,
            timeout=timeout_ms
        )
    except Exception:
        pass  # Non-fatal

# Use before screenshot
elem.scroll_into_view_if_needed()
page.wait_for_timeout(250)
_wait_for_ad_creative_loaded(page, elem, timeout_ms=1200)  # ← Add this
elem.screenshot(path=screenshot_path)
```

**Additional fixes:**
- Force eager loading: `img[loading="lazy"]` → `img[loading="eager"]`
- Increase dwell time for video ads (1200ms minimum)
- Scroll element into view before waiting

**See:** `docs/INSTACART_INTEGRATION.md` → Anti-Detection & Ad Loading

---

## Automation detected / ads suppressed

**Cause:** Ad systems detect Playwright and degrade/suppress creative serving.

**Symptoms:**
- Fewer ads in automation than manual browsing
- Blank ad containers
- Generic placeholder images instead of real creative
- Works in headed mode, fails in headless

**Fix:** Anti-detection measures:

```python
# 1. Use mainstream User-Agent (not Playwright default)
context = p.chromium.launch_persistent_context(
    user_data_dir=profile_dir,
    headless=False,
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    args=[
        '--disable-blink-features=AutomationControlled',
        '--no-sandbox',
    ]
)

# 2. Dismiss consent banners (can block ads)
consent_selectors = [
    "[id*='onetrust-accept']",
    "button:has-text('Accept')",
    "button:has-text('I agree')",
]
for cta in consent_selectors:
    try:
        if page.locator(cta).first.is_visible(timeout=1000):
            page.locator(cta).first.click(timeout=1000)
            break
    except:
        pass

# 3. Emulate human behavior on direct navigation
page.goto(url, wait_until="domcontentloaded")
page.wait_for_timeout(1200)  # Dwell
page.evaluate("window.scrollTo(0, 200)")  # Scroll
page.wait_for_timeout(400)
page.evaluate("window.scrollTo(0, 0)")  # Back to top
```

**Additional measures:**
- Use persistent profile (not incognito)
- Disable "block third-party cookies" in profile
- Turn off Do-Not-Track
- Check for ad-blocking extensions

**See:** `docs/INSTACART_INTEGRATION.md` → Anti-Detection & Ad Loading

---

## Duplicate brand logos with different hashes

**Cause:** Logo filenames hashed by URL instead of image content.

**Symptoms:**
- `boiron_40a07122.png` and `boiron_58d48a91.png` are identical
- Multiple files for same brand logo
- Database has duplicate entries

**Fix:** Use content-based hashing in `brand_logo_database.py`:

```python
# OLD: Hash the URL
url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
filename = f"{brand_key}_{url_hash}.{ext}"

# NEW: Hash the actual image content
response = requests.get(url)
content_hash = hashlib.md5(response.content).hexdigest()

# Check if identical image already exists
existing_files = list(logos_dir.glob(f"{brand_key}*.{ext}"))
for existing_file in existing_files:
    existing_hash = hashlib.md5(existing_file.read_bytes()).hexdigest()
    if existing_hash == content_hash:
        return f"brand_logos/{existing_file.name}"  # Reuse existing

# New unique image - use clean numbered naming
logo_number = find_next_logo_number(brand_key, ext)
filename = f"{brand_key}.{ext}" if logo_number == 1 else f"{brand_key}_{logo_number}.{ext}"
```

**Cleanup existing duplicates:**
```bash
python3 scripts/deduplicate_brand_logos.py
```

**Result:**
- `boiron.png` (single file for identical images)
- `boiron_2.png` (if brand has second unique logo)
- Clean, human-readable filenames

**See:** `docs/ARTIFACT_TAXONOMY.md` → Brand Logos

---

## Brand logo not in JSON output

**Cause:** Logo path not enriched into ad data after extraction.

**Symptoms:**
- Brand logos downloaded and saved
- JSON has `brand` field but no `brand_logo` field
- Frontend can't display logos

**Fix:** Add logo path enrichment before appending to results:

```python
# In scraper after extracting ad data
ad_info = {
    "type": ad_type,
    "brand": advertiser,
    "title": title,
    # ... other fields ...
}

# Enrich with brand logo path from database
if advertiser and logo_db:
    logo_path = logo_db.get_logo_path(advertiser)
    if logo_path:
        ad_info["brand_logo"] = logo_path  # ← Add this

ad_data["ads"].append(ad_info)
```

**JSON output:**
```json
{
  "type": "Shoppable Display Ad",
  "brand": "Boiron",
  "brand_logo": "brand_logos/boiron.png",
  "screenshot": "output/instacart/client/Shoppable_Display_Ads/..."
}
```

**See:** `docs/ARTIFACT_TAXONOMY.md` → JSON Schema Standardization

---

---

## Kroger image paths missing despite files existing

**Cause:** Screenshot extraction succeeded but failed to update JSON with `image_path` / `toa_image_path` / `skyscraper_image_path`.

**Symptoms:**
- PNG files exist in TOA/, Skyscraper/, Carousel/ folders
- JSON ads have `image_url` but no `image_path`
- Dashboard shows "No image" or placeholder
- Aggregated JSONs missing image references
- Per-run JSONs may have paths but aggregated files don't

**Root Causes:**
1. **Extractor path-wiring bug** - `update_json_with_image_paths()` in `extractors/screenshot_ad_image.py` failed to match ads
2. **URL mismatch** - Extractor tried to match absolute Kroger CDN URLs (`https://www.kroger.com/content/...`) but JSON had relative URLs (`/content/...`)
3. **JSON structure mismatch** - Extractor expected flat `ads[]` array, but Kroger uses nested `results[].ads[]`
4. **Aggregation loss** - Per-run JSONs had paths, but aggregation process didn't preserve them

**Context (Nov 2025):**
- Discovered during Kroger MilkPEP/magic_spoon/Proactiv client review
- Hundreds of TOA/Skyscraper PNGs existed but weren't referenced in JSON
- Manual intervention unacceptable per user requirement
- Created automated repair tools to fix existing data and prevent future occurrences

**Fix:**
Use repair tools to backfill missing paths:

```bash
# 1. Backfill image_path where PNGs exist (matches by filename metadata)
python tools/repair_kroger_image_paths.py

# 2. Regenerate missing images from archived HTML (offline extraction)
python tools/rebuild_kroger_images_from_archive.py

# 3. Fix specific brand mislabelings from rebuild
python tools/fix_bluey_rebuild_labels.py  # Blue Buffalo → Bluey
python tools/repair_blue_bunny_sweet_pairings.py  # Unknown → Blue Bunny

# 4. Rebuild brand index to reflect changes
python tools/build_brand_index.py
```

**How repair tools work:**

1. **repair_kroger_image_paths.py:**
   - Scans all Kroger client directories for orphaned PNGs
   - Parses filename metadata (retailer, advertiser, ad_type, client, keyword, timestamp)
   - Matches PNGs to JSON ads by ad_type + client + keyword + timestamp proximity
   - Backfills `image_path` / `toa_image_path` / `skyscraper_image_path` fields
   - Handles both per-run and aggregated JSON structures

2. **rebuild_kroger_images_from_archive.py:**
   - Scans for run JSONs with `image_url` but no `image_path`
   - Finds corresponding archived HTML file
   - Re-runs screenshot extraction offline (headed-but-hidden mode)
   - Wires new image paths back into JSON
   - Skips runs that already have images

**Prevention:**
- Fixed `extractors/screenshot_ad_image.py` to handle both aggregated and per-run JSON shapes
- Match ads by both absolute CDN URLs and relative `/content/...` URLs
- Update both top-level `ads[]` and nested `results[].ads[]` structures
- Ensure aggregation process preserves `image_path` fields

**Verification:**
```bash
# Check if image_path exists in JSON
cat output/kroger/<client>/runs/run_results_*.json | jq '.ads[] | select(.image_path)'

# Check if PNG files exist
find output/kroger/<client> -name "*.png" -type f

# Count orphaned images (PNGs without JSON references)
python tools/repair_kroger_image_paths.py --dry-run
```

**See:** `tools/rebuild_kroger_images_from_archive.py`, `tools/repair_kroger_image_paths.py`, `extractors/screenshot_ad_image.py`

---

## Brand canonicalization misclassifies similar names

**Cause:** Fuzzy token matching on short generic words (e.g., "blue") incorrectly matches distinct brands.

**Symptoms:**
- "Blue Pet Foods" → "Bluey" (should be "Blue Buffalo")
- "Blue Bunny" ads showing as "Unknown"
- Generic words like "blue", "red", "new" causing collisions
- Different brands with similar words getting merged

**Root Cause:**
- Fuzzy matching (`difflib.get_close_matches`) operates on individual tokens
- Short tokens (≤4 chars) like "blue" match multiple brands with high similarity scores
- No distinction between generic words and brand-specific terms
- Example: "blue" in "Blue Pet Foods" matches "Bluey" (4 chars, 75% similarity)

**Context (Nov 2025):**
- Discovered during Kroger Proactiv client review
- Blue Buffalo ads were mislabeled as "Bluey" during Nov 24 image rebuild
- Blue Bunny "Serve Up Sweet Pairings" TOA ads showed as "Unknown"
- User explicitly stated: "no hardcoding generic words" - need robust solution

**Fix Applied:**

1. **Ignore short tokens in fuzzy matching:**
   ```python
   # In core/brands.py, canonicalize() function
   for token in tokens:
       if len(token) <= 4:  # Skip short tokens to prevent collisions
           continue
       matches = difflib.get_close_matches(token, all_brand_tokens, n=1, cutoff=0.85)
   ```

2. **Add full-phrase synonyms to brands.json:**
   ```json
   {
     "name": "Blue Buffalo",
     "synonyms": [
       "MSG:Save on Blue Pet Foods. Feed delicious recipes, made with real meat first.",
       "Save on Blue Pet Foods. Feed delicious recipes, made with real meat first.",
       "Blue Food"
     ]
   },
   {
     "name": "Blue Bunny",
     "synonyms": [
       "BlueBunny",
       "Blue-Bunny",
       "MSG:Serve Up Sweet Pairings. Top holiday treats with deliciously soft scoops. Shop Now."
     ]
   },
   {
     "name": "Bluey",
     "synonyms": [
       "MSG:Bluey Makes Snack Time Fun. Shop Bluey grocery, toys & more. Shop Now."
     ]
   }
   ```

3. **Three-tier matching strategy (in order):**
   - **Exact match:** Direct lookup in canonical brand names
   - **Phrase match:** Multi-word substring matching against full synonyms
   - **Fuzzy token match:** Individual word matching (now skips short tokens)

**Repair existing mislabelings:**
```bash
# Fix Blue Buffalo ads mislabeled as Bluey (from Nov 24 rebuild)
python tools/fix_bluey_rebuild_labels.py

# Fix Blue Bunny ads showing as Unknown
python tools/repair_blue_bunny_sweet_pairings.py

# Rebuild brand index to reflect changes
python tools/build_brand_index.py
```

**How repair scripts work:**

1. **fix_bluey_rebuild_labels.py:**
   - Scoped to specific run date: `D2025-11-24_T15-3*` (the rebuild timestamp)
   - Finds ads with `advertisers: ["Bluey"]` OR `image_path` containing `__bluey__`
   - Changes `advertisers` and `brand` to "Blue Buffalo"
   - Renames PNG files from `__bluey__` to `__blue_buffalo__`
   - Updates `image_path` fields to match new filenames

2. **repair_blue_bunny_sweet_pairings.py:**
   - Scoped to specific message: "Serve Up Sweet Pairings. Top holiday treats..."
   - Finds TOA ads with this exact message
   - Sets `advertisers: ["Blue Bunny"]` and `brand: "Blue Bunny"`
   - Renames PNG files from `__unknown__` to `__blue_bunny__`
   - Updates `image_path` fields to match

**Prevention:**
- Use full-phrase synonyms for brands with generic words
- Add campaign-specific messages as synonyms (prefix with `MSG:`)
- Fuzzy matching now skips tokens ≤4 chars automatically
- Brand Review Tool available for manual corrections

**Testing brand canonicalization:**
```python
from core.brands import canonicalize

# Should return "Blue Buffalo"
print(canonicalize("Save on Blue Pet Foods"))

# Should return "Blue Bunny"  
print(canonicalize("Serve Up Sweet Pairings"))

# Should return "Bluey"
print(canonicalize("Bluey Makes Snack Time Fun"))
```

**See:** `core/brands.py`, `config/brands.json`, `tools/fix_bluey_rebuild_labels.py`, `tools/repair_blue_bunny_sweet_pairings.py`

---

## References

- **Onboarding:** `docs/RETAILER_ONBOARDING_CHECKLIST.md`
- **Taxonomy:** `docs/ARTIFACT_TAXONOMY.md`
- **Playwright:** `docs/PLAYWRIGHT_BOOTSTRAP.md`
- **Builder GUI:** `docs/BUILDER_GUIDE.md`


## Instacart ad screenshots cropped incorrectly / showing only carousel

**Status:** ✅ SOLVED

**Symptoms:**
- Ad screenshots showing only the product carousel (not full ad card)
- Missing logo/brand header at top
- Missing hero image section
- Missing "Sponsored" label
- Screenshots are correct width (1580-1793px) but wrong height (233-467px vs expected 400-600px)
- Element bounding box shows correct dimensions but screenshot captures wrong content

**Root Causes Identified and Fixed:**

1. **Viewport scaling from wrong Chrome profile** ✅ FIXED
   - GUI was passing Walmart profile (`~/ChromeProfiles/walmart`) to Instacart scraper
   - Walmart profile had saved window dimensions of 2133x1200 with DPR 0.9
   - CDP viewport control commands couldn't override persistent profile preferences
   - Caused all screenshots to be scaled incorrectly
   
   **Solution:** 
   - Created dedicated Instacart profile (`~/ChromeProfiles/instacart`)
   - Adapter now detects wrong profile and auto-switches to correct one
   - Fresh profile has no saved dimensions, allows 1920x1080 DPR 1.0 to work
   - Added to `auth/profiles.json` for future use

2. **Coordinate space mismatch in CDP screenshot** ✅ FIXED - THE ACTUAL BUG
   - `element.bounding_box()` returns **viewport coordinates** (relative to scroll position)
   - CDP `Page.captureScreenshot` expects **page coordinates** (absolute document position)
   - When scrolled, element at viewport y=423 is actually at page y=1675 (423 + scrollY 1252)
   - Was passing viewport coords (y=423) when CDP needed page coords (y=1675)
   - Result: CDP captured wrong region of page (1252px too high)
   
   **Debug Evidence of Bug:**
   ```
   Found ad container: y=1675.4 (before scroll)
   Element rect: top=423.4, scrollY=1252.0 (after scroll into view)
   Clip: y=415.4 (WRONG - missing scrollY offset!)
   Expected: y = 423.4 + 1252.0 = 1675.4
   ```
   
   **Solution:**
   ```python
   # Compute rect in PAGE coordinates (viewport + scroll offset)
   rect = page.evaluate(
       """([el, pad]) => {
           const r = el.getBoundingClientRect();
           const sx = window.scrollX || window.pageXOffset || 0;
           const sy = window.scrollY || window.pageYOffset || 0;
           const x = Math.max(0, Math.floor(r.left + sx - pad));
           const y = Math.max(0, Math.floor(r.top + sy - pad));
           const w = Math.ceil(r.width + 2*pad);
           const h = Math.ceil(r.height + 2*pad);
           return { x, y, width: w, height: h };
       }""",
       [handle, pad]
   )
   
   # Now clip uses page coordinates
   clip = {'x': rect['x'], 'y': rect['y'], 'width': rect['width'], 'height': rect['height']}
   ```

3. **Hash class instability** ✅ HANDLED
   - Border container class changes between runs: `e-onstcn`, `e-1cjjmkc`, `e-s7m7s6`
   - Cannot rely on direct class selectors
   - Use structural navigation (UUID + `-inner` child + carousel presence)

**Complete Solution Stack:**
1. ✅ Dedicated Instacart Chrome profile (no saved window dimensions)
2. ✅ CDP viewport control: `Browser.setWindowBounds` + `Emulation.setDeviceMetricsOverride`
3. ✅ Force DPR=1: `device_scale_factor=1` + `--force-device-scale-factor=1`
4. ✅ Page coordinate calculation: `rect.top + window.scrollY` for CDP clip
5. ✅ CDP screenshot with `captureBeyondViewport: true`
6. ✅ Single browser session (no separate extraction phase)

**Key Learnings:**
- **Persistent browser contexts save window state** - need fresh profile or CDP override
- **CDP coordinate spaces are different** - viewport coords ≠ page coords
- **Always add scroll offsets** when using CDP `captureScreenshot` with scrolled content
- **Playwright's `element.bounding_box()`** returns viewport coords, not page coords
- **`page.evaluate()` in Python** takes single arg, use array: `page.evaluate(expr, [arg1, arg2])`

**Files Modified:**
- `instacart_search_and_capture.py`: Added CDP viewport control and page coordinate calculation
- `retailers/instacart/adapter.py`: Auto-switch to Instacart profile
- `auth/profiles.json`: Added Instacart profile entry
- Created: `~/ChromeProfiles/instacart` directory

**Verification:**
```bash
# Check screenshots show full ad cards
ls -lh output/instacart/*/Shoppable_Display_Ads/*.png

# Verify viewport in logs
grep "Viewport verified" output/instacart/*/debug_search.log
# Should show: 1920x1080, DPR: 1

# Verify page coordinates used
grep "Clip (page coords)" output/instacart/*/debug_search.log
# Should show: y ≈ (viewport top + scrollY)
```

**See:** `retailers/instacart/README.md` → Technical Details → Screenshot Capture

---

## Frontend showing duplicate images for different ads

**Status:** ✅ SOLVED

**Symptoms:**
- Web dashboard displays same image for multiple different ads
- Siggi's ad card shows Danone image
- JSON has correct screenshot paths but frontend uses wrong image URL
- Browser dev tools show wrong image URL in `<img src>`

**Root Cause:**
Backend image path resolution was not checking the `screenshot` field that Instacart scraper uses. It only checked for `screenshot_path`, `image_path`, etc. When the field wasn't found, it fell back to searching by brand name, which could match the wrong file.

**Solution:**
Add `"screenshot"` to the list of path fields checked in `web/builder_server_v2.py`:

```python
# Try various path fields first (these point to actual saved files)
for path_field in ["skyscraper_image_path", "carousel_image_path", "main_image_path",
                   "image_path", "screenshot_path", "screenshot", "filename"]:
    p = ad.get(path_field)
    if not p:
        continue
    # ... rest of logic
```

**Why it matters:**
- Different retailers use different field names in their JSON output
- Instacart: `screenshot`
- Kroger: `screenshot_path` or `image_path`
- Walmart: `main_image_path` or `carousel_image_path`
- Backend must check all common field names to find the correct image path

**Additional fix:** Frontend ID generation now includes brand and ad_type to ensure uniqueness:
```typescript
// In neon-sanctuary/client/pages/Index.tsx
const brand = (c.brand || 'unknown').replace(/[|]/g, '-');
const adType = (c.ad_type || 'unknown').replace(/[|]/g, '-');
return `${c.retailer}|${c.client}|${runId}|${idx}|${brand}|${adType}|${tsMs}`;
```

**Files Modified:**
- `web/builder_server_v2.py`: Added `"screenshot"` to path field list
- `neon-sanctuary/client/pages/Index.tsx`: Updated `buildAdId()` to include brand/ad_type

**Verification:**
```bash
# Restart web server
cd neon-sanctuary && pnpm dev

# Check API returns correct image URLs
curl -s "http://localhost:48752/api/ads/cards?retailer=instacart&client=magic_spoon" | \
  jq '.cards[] | {brand, image_url}'

# Each brand should have unique image URL matching their screenshot filename
```

---

## Taxonomy Fix checklist

### Instacart

html saves to runs
json saves but is empty

no ads save, no main screengrab saves

all of these were previously working

folders are created correctly

### Walmart

EVERYTHING saves in the runs folder

SBA image is extracted but in runs folder

json only seems to include the SBA

no screengrab is saved

folders are created correctly

### Kroger

Folders are created correctly

screengrab is working correctly

skyscraper ad is captured

html and json are in the right place

none of the other ads are patured

---

## Kroger scraper hangs indefinitely / deadlock

**Status:** ✅ SOLVED (Oct 2025)

**Symptoms:**
- Kroger scrapes start but never complete (hang for 8+ minutes)
- Browser closes but process still running
- Lock files remain, blocking subsequent runs
- Logs show "START" but never "SUCCESS" or "TIMEOUT"
- Screenshot extraction process waiting indefinitely
- Other retailers (Walmart, Instacart) complete successfully in same run

**Root Cause:**
**Deadlock in browser lock acquisition.** The main Kroger scraper (`kroger_search_and_capture.py`) was calling post-processing (which spawns the screenshot extraction script) **while still holding the global browser lock**. The screenshot script then tried to acquire the same lock, causing a deadlock:

1. Parent (main scraper) acquires `single_browser_lock()`
2. Parent completes scraping and saves HTML/JSON
3. Parent calls `process_specific_html_files()` **inside the lock**
4. Post-processing spawns screenshot script as child process
5. Child tries to acquire `single_browser_lock()`
6. **DEADLOCK** - child waits for parent's lock, parent waits for child to finish

**Debug Evidence:**
```bash
# Main scraper still running after 5+ minutes
ps aux | grep kroger_search_and_capture
# PID 38324 - running since 23:13, now 23:18

# Screenshot script also running, waiting for lock
ps aux | grep screenshot_toa_image
# PID 38486 - child of 38324, stuck

# Lock file exists
cat logs/locks/sour_cream_image_extraction.lock
# 38486

# Files created but processing never completes
ls -lth output/kroger/sour_cream/runs/
# HTML/JSON created at 23:13, but no images extracted
```

**Solution:**
Move post-processing **outside** the browser lock in `kroger_search_and_capture.py`:

```python
# BEFORE (deadlock):
with single_browser_lock(timeout=600):
    with sync_playwright() as p:
        # ... browser work ...
        save_html(html_path)
        
        # ❌ DEADLOCK: Post-processing inside lock
        from process_saved_html import process_specific_html_files
        process_specific_html_files([html_path], output_dir=output_dir, force_images=True)

# AFTER (fixed):
saved_html_path = None

with single_browser_lock(timeout=600):
    with sync_playwright() as p:
        # ... browser work ...
        save_html(html_path)
        
        # Save path for later processing
        saved_html_path = html_path
        print("✅ Browser work complete - will do post-processing after releasing lock")

# Lock is released here ↑

# ✅ Post-processing after lock released
if saved_html_path:
    print("\n🔍 Starting post-processing (browser lock released)...")
    from process_saved_html import process_specific_html_files
    process_specific_html_files([saved_html_path], output_dir=output_dir, force_images=True)
```

**Additional Fixes Applied:**

1. **Screenshot download timeout reduction** (`extractors/screenshot_ad_image.py`):
   - Reduced timeout from 45s to 15s per attempt
   - Added detailed logging for each download attempt
   - Fail fast on HTTP errors (don't retry 404s, 403s)
   - Fixed delay instead of exponential backoff

2. **Cookie seeding optimization** (`extractors/screenshot_ad_image.py`):
   - Check for existing cookies in persistent profile BEFORE navigation
   - Skip cookie seeding if cookies already exist (from main scraper)
   - Only navigate to seed cookies if profile is empty

**Files Modified:**
- `kroger_search_and_capture.py`: Moved post-processing outside browser lock (lines 472-816)
- `extractors/screenshot_ad_image.py`: Reduced timeouts, added logging, skip cookie seeding if cookies exist

**Result:**
- Kroger scrapes complete in ~1 minute (down from 8+ minute hangs)
- TOA and Skyscraper images extract successfully
- No more deadlocks or stale lock files
- Detailed logging shows exactly what's happening during downloads

**Prevention:**
- Always release browser locks before spawning child processes that need the same lock
- Use `--no-lock` flag when calling screenshot scripts from within locked context (adapter already does this)
- Add timeouts to all lock acquisitions
- Log lock acquisition/release for debugging

**Verification:**
```bash
# Check Kroger runs complete quickly
tail -f logs/scheduler_daemon.log | grep kroger

# Should see:
# [kroger] START keyword 'ice cream bar' for blue bunny
# [kroger] SUCCESS keyword 'ice cream bar' for blue bunny  (< 1 minute later)
# [kroger] Waiting 120s before HTML processing
# [kroger] Successfully processed HTML files for blue bunny
# [kroger] Completed scheduled scrape for blue bunny: 1/1 keywords successful

# Check for extracted images
ls -lth output/kroger/*/TOA/*.png output/kroger/*/Skyscraper/*.png | head -10
```

**See:** `docs/SCHEDULER_PERFORMANCE_FIXES.md` → Browser Lock Management

---

## Frontend: Content box not spanning full width of card container

**Symptoms:**
- Text/content box constrained to image width instead of card width
- Content box right edge aligns with image right edge, not card edge
- Styling properties on content element don't work (width, alignment, etc.)
- Issue appears for specific ad types (e.g., Skyscraper) but not others

**Root Cause:**
The **parent container** (button wrapper) is not full-width, constraining all children. The content box styling is correct, but it's inside a narrow parent.

**How to Debug Faster:**

❌ **Don't say:** "For skyscraper ads, this is not applying"
- Too vague - doesn't identify which element or boundary is wrong

✅ **Do say:**
- "The text box is constrained to the image width instead of extending to the card's full width"
- "The content box's right edge aligns with the image's right edge, but it should extend to the card's edge"  
- "The button wrapper isn't expanding full width for skyscraper ads"

**Key Insight:**
Describe **which elements are constrained** and **what boundaries they're incorrectly snapping to**, rather than just which ad type isn't working. This immediately points to the parent/container problem instead of the child styling.

**Common Fix:**
```tsx
// Wrong - button wrapper not full width
<button className="relative">
  <img src={...} />
  <div className="content-frame w-full">Text</div>
</button>

// Correct - button wrapper is full width
<button className="relative w-full">
  <img src={...} />
  <div className="content-frame w-full">Text</div>
</button>
```

**Analogy:**
You were rearranging furniture in a room without realizing the room's walls were too narrow. The furniture (content box) was fine - the room (button wrapper) needed to be bigger.

**See:** Frontend component debugging, Tailwind layout issues

---

## Images failing to load in Vite dashboard (dual-backend architecture)

**Status:** ✅ SOLVED

**Problem & Root Cause:**

Your application has two backends:
- **Flask API (port 5006)** - serves real ad images from your filesystem
- **Express/Node.js (port 3000)** - the Vite dev server and API layer

When the frontend requested images from `/api/image/retailer/client/path/filename.png`, the Express server had no route to handle these requests. They failed silently, showing `[AdImage] Failed to load image` errors.

**Solution: Image Proxy Route**

Created a bridge between the two backends:

**What Was Added:**

1. **New file: `neon-sanctuary/server/routes/image.ts`**
   - Intercepts requests to `/api/image/*`
   - Proxies them to Flask at `http://localhost:5006`
   - Returns the image with proper CORS headers

2. **Updated: `neon-sanctuary/server/index.ts`**
   - Registered a regex route pattern to capture image requests
   - Uses: `^\/api\/image\/([^/]+)\/([^/]+)\/(.+)$` to extract:
     - `retailer` (e.g., instacart)
     - `client` (e.g., MilkPEP)
     - `filename` with nested paths (e.g., `Shoppable_Display_Ads/instacart__nature_s_truth__...png?v=123`)

3. **Enhanced: `neon-sanctuary/client/utils/imageUrl.ts`**
   - Better type checking and validation
   - Improved error logging

**Key Watchouts for Future Building:**

✅ **When you have multiple backend services** (Flask + Express), ensure the "main" backend (Express/Vite) knows how to route to or proxy requests for resources that live in other backends

✅ **Regex route patterns matter** - Simple wildcard patterns like `/api/image/:retailer/:client/*` don't capture nested subdirectories properly. The regex `^\/api\/image\/([^/]+)\/([^/]+)\/(.+)$` correctly captures multi-level paths

✅ **Preserve query strings** - When proxying, forward query parameters (`?ngrok-skip-browser-warning=true&v=123`) to the upstream service

✅ **Cross-origin headers** - Set proper CORS headers (`Access-Control-Allow-Origin: *`) when proxying cross-origin requests

**Files Involved:**
- `neon-sanctuary/server/routes/image.ts` - Flask image proxy
- `neon-sanctuary/server/routes/proxy-image.ts` - External URL proxy
- `neon-sanctuary/server/index.ts` - Route registration
- `neon-sanctuary/client/utils/imageUrl.ts` - Client-side URL routing

**Verification:**
```bash
# Check Express is proxying to Flask
curl -I "http://localhost:3000/api/image/instacart/client/Shoppable_Display_Ads/test.png"
# Should return 200 or 404 (not 404 from Express routing)

# Check Flask is serving images
curl -I "http://localhost:5006/api/image/instacart/client/Shoppable_Display_Ads/test.png"
# Should return image content-type

# Check frontend logs
# Should NOT see "[AdImage] Failed to load image" errors
```

**See:** `docs/BUILDER_GUIDE.md` → Architecture Overview

---

## Kroger Ad Dashboard - Multi-Backend Integration Issues & Fixes

**Status:** ✅ SOLVED

### Issue 1: Image Loading Errors - `[AdImage] Failed to load image: [object Object]`

**Symptom:**
- Ad images failed to load with console errors showing stringified objects

**Root Cause:**
- Console logging passed objects directly: `console.error('[AdImage] Failed to load image:', { src, ... })`
- Browsers stringify objects to `[object Object]` in certain contexts

**Solution:**

File: `neon-sanctuary/client/components/dashboard/AdCard.tsx`
- Use `JSON.stringify()` for object logging: `console.error('[AdImage] Failed to load image: ' + JSON.stringify(errorDetails))`

File: `neon-sanctuary/client/utils/imageUrl.ts`
- Added type checking for image URLs
- Better error messages with explicit JSON formatting
- Trim whitespace and handle undefined inputs

---

### Issue 2: Real Images Not Loading (Using Mock Data Instead)

**Symptom:**
- Placeholder images from Express served instead of real ad images from Flask backend

**Root Cause:**
- Flask backend at `localhost:5006` had real ad images
- Express at port 3000 was using mock data with hardcoded `/api/placeholder-ad-N.jpg` URLs
- Frontend couldn't reach Flask's `/api/image/*` endpoints

**Solution:**
Create image proxy route to bridge backends:

**Files Created/Modified:**

1. **Created:** `neon-sanctuary/server/routes/image.ts`
   - Proxies `/api/image/:retailer/:client/*` requests to Flask
   - Uses regex pattern: `^\/api\/image\/([^/]+)\/([^/]+)\/(.+)$` to capture nested subdirectories
   - Preserves query strings (`?ngrok-skip-browser-warning=true&v=123`)
   - Sets CORS headers for image response

2. **Modified:** `neon-sanctuary/server/index.ts`
   - Added image proxy route that extracts retailer/client/filename from URL pattern
   - Routes all image requests through Flask backend

**Key Pattern:**
```typescript
app.get(/^\/api\/image\/([^/]+)\/([^/]+)\/(.+)$/, (req, res, next) => {
  req.params.retailer = req.params[0];
  req.params.client = req.params[1];
  req.params.filename = req.params[2];  // Captures nested paths like "Shoppable_Display_Ads/filename.png"
  return handleImageProxy(req, res, next);
});
```

---

### Issue 3: Retailer Logos Missing (Amazon & Walmart Showing Alt Text)

**Symptom:**
- Kroger and Instacart logos displayed (hardcoded CDN URLs)
- Amazon and Walmart showed text "AMAZON"/"WALMART" instead of logos
- Component tried `/api/logo/amazon` which didn't exist

**Root Cause:**
- `RetailerLogo.tsx` had hardcoded CDN URLs for only 2 retailers
- Fallback to `/api/logo/retailer` route didn't exist on Express
- Express only had `/api/logo/brand/:brand` (for brand logos like BOOST Advanced)

**Solution:**
Create retailer logo serving route:

**File Created:** `neon-sanctuary/server/routes/retailer-logo.ts`
- Maps retailer names to actual files in `web/assets/logos/`:
  - `amazon` → `AMZ.png`
  - `walmart` → `WMT.png`
  - `kroger` → `Kroger.png`
  - `instacart` → `Instacart Long.png`

**File Modified:** `neon-sanctuary/server/index.ts`
- Added route: `app.get("/api/logo/:retailer", handleRetailerLogo);`
- **Note:** Place before `/api/logo/brand/:brand` to prevent route conflicts

---

### Issue 4: Retailer Filters Not Working

**Symptom:**
- Changing retailer selection didn't update results
- All retailers' data loading simultaneously regardless of selection
- Ad counts didn't change when toggling retailers

**Root Cause:**
- All 12 queries (4 retailers × 3 clients) executed unconditionally
- Code filtered results during render but didn't stop queries from running
- Wasted API calls and state synchronization issues

**Solution:**
Add conditional `enabled` logic to queries:

**File Modified:** `neon-sanctuary/client/pages/Index.tsx` (lines 166-269)

**Pattern Applied to All 4 Retailers:**
```typescript
// Before: Query always runs
const krogerQuery1 = useAds({
  retailer: "kroger",  // Always queries
  client: client1,
  ...
});

// After: Query only runs when retailer is selected
const isKrogerSelected = retailers.includes("kroger");
const krogerQuery1 = useAds({
  retailer: isKrogerSelected ? "kroger" : undefined,  // Disables query when not selected
  client: client1,
  ...
});
```

**How it works:**
- `useAds` hook checks: `const enabled = Boolean(retailer && client);`
- When `retailer` is `undefined`, the query disables and stops fetching
- Reduces backend load by only querying selected retailers

---

### Issue 5: Date Filters Not Working

**Status:** ✅ FIXED - Now working fundamentally

**Symptom:**
- Selecting date ranges ("Yesterday", "Last 7 days") didn't filter results
- Ad counts stayed the same regardless of date selection
- Date parameters were being sent but ignored

**Root Causes:**
- Express proxy was forwarding dates correctly but...
- Flask backend wasn't implementing date filter logic at all
- Flask accepted `start` and `end` parameters but never used them

**Solution:**
Implement date filtering in Flask:

**File Modified:** `web/builder_server_v2.py` (`api_ads_cards` function)

**Step 1:** Extract date parameters (line 544-545)
```python
start_date = (request.args.get("start") or "").strip()  # YYYY-MM-DD
end_date = (request.args.get("end") or "").strip()      # YYYY-MM-DD
```

**Step 2:** Filter cards by date (after advertiser filtering)
```python
if start_date or end_date:
    filtered_cards = []
    for card in all_cards:
        # Extract card date from timestamp: "2025-10-24 15:30:00" → "2025-10-24"
        timestamp = card.get("timestamp", "")
        card_date = timestamp.split()[0] if timestamp else ""
        
        if not card_date:
            continue  # Skip cards with no date
        
        if start_date and card_date < start_date:
            continue  # Before range start
        
        if end_date and card_date > end_date:
            continue  # After range end
        
        filtered_cards.append(card)
    
    all_cards = filtered_cards
```

**Key Points:**
- Date format: `YYYY-MM-DD` (lexicographically sortable)
- Timestamps in cards are Central Time (matching backend)
- String comparison works because `YYYY-MM-DD` is naturally sortable
- Frontend sends dates via `formatLocalDate()` function

---

### Data Flow Reference

```
Frontend (React)
  ↓ formatLocalDate(date) → "2025-10-25"
  ↓ useAds({ start: "2025-10-25", end: "2025-10-25" })
  ↓
Express Server (port 3000)
  ↓ /api/ads/cards?start=2025-10-25&end=2025-10-25
  ↓ (ads-proxy route)
  ↓
Flask Backend (port 5006)
  ↓ api_ads_cards() - extracts and filters by date
  ↓ Returns: { cards: [...filtered...], has_more: bool, total_cards: int }
  ↓
Express (passes through)
  ↓
Frontend (renders filtered results)
```

---

### Common Watchouts for Future Building

✅ **Multi-Backend Architecture:**
- When you have multiple services (Flask + Express), ensure the primary service can proxy/route to others
- Use environment variables for backend URLs: `const FLASK_BASE_URL = process.env.FLASK_BASE_URL || "http://localhost:5006"`

✅ **Regex Route Patterns:**
- Simple wildcards like `/api/image/:retailer/:client/*` don't capture nested paths properly
- Use regex for complex paths: `^\/api\/image\/([^/]+)\/([^/]+)\/(.+)$`

✅ **Query Parameter Forwarding:**
- Always forward query strings when proxying: `new URLSearchParams(req.query as Record<string, string>)`

✅ **React Query Conditional Execution:**
- Use boolean `enabled` parameter to conditionally disable queries
- Prevents unnecessary API calls and state synchronization issues

✅ **Timezone Consistency:**
- If backend stores timestamps in Central Time, ensure frontend formats dates accordingly
- Use local date formatting: `getFullYear()`, `getMonth() + 1`, `getDate()` (not UTC methods)

✅ **Console Logging Objects:**
- Always stringify objects for logs: `JSON.stringify(obj)` instead of passing object directly
- Some contexts will stringify to `[object Object]` automatically

---

### Files Modified Summary

**Created:**
- `neon-sanctuary/server/routes/image.ts`
- `neon-sanctuary/server/routes/retailer-logo.ts`
- `neon-sanctuary/server/routes/ads-proxy.ts`

**Modified:**
- `neon-sanctuary/server/index.ts` (routes registered)
- `neon-sanctuary/client/pages/Index.tsx` (retailer query conditions)
- `neon-sanctuary/client/components/dashboard/AdCard.tsx` (logging fix)
- `neon-sanctuary/client/utils/imageUrl.ts` (URL validation)
- `web/builder_server_v2.py` (date filter implementation)

---

## Brand Logo Endpoints Confusion (Dual Backend)

**Status:** ✅ SOLVED

**Problem:**
Brand logos not displaying in frontend modals. Confusion between two different logo endpoints serving different purposes.

**Root Cause:**
The system has TWO logo endpoints across two different backends:

1. **`/api/brand_logo/<filename>`** - Flask backend (port 5006)
   - Direct file serving by exact filename
   - Input: `cerave.png`, `tide.png`
   - Use case: When you already know the exact logo filename

2. **`/api/logo/brand/<brandname>`** - Express backend (port 3000/8080)
   - Smart brand name lookup with normalization
   - Input: `CeraVe`, `Blue Buffalo`, `Tide`
   - Use case: When you have brand names from ad data

**The Confusion:**
Frontend components have **brand names** from ad data (e.g., "CeraVe", "Blue Buffalo"), not filenames. Using the Flask endpoint requires knowing the exact filename, which the frontend doesn't have.

**Solution:**
Use the Express endpoint `/api/logo/brand/<brandname>` which:
1. Takes brand name: `"CeraVe"`
2. Normalizes it: `"cerave"` (lowercase, removes spaces/special chars)
3. Searches `output/brand_logos/` for matching files
4. Finds: `cerave.png`
5. Serves the image with proper content-type

**Implementation:**

```typescript
// ✅ CORRECT - Use Express endpoint with brand names
const response = await fetch(`/api/logo/brand/${encodeURIComponent(brandName)}`);

// ❌ WRONG - Flask endpoint expects filenames, not brand names
const response = await fetch(`/api/brand_logo/${encodeURIComponent(brandName)}`);
```

**Express Handler (`server/routes/logo.ts`):**
```typescript
export const handleBrandLogo: RequestHandler = async (req, res) => {
  const { brand } = req.params;
  
  // Normalize: "CeraVe" → "cerave"
  const normalizedBrand = brand
    .toLowerCase()
    .replace(/\s+/g, "_")
    .replace(/[^a-z0-9_-]/g, "");
  
  // Find matching file (cerave.png, cerave.jpg, etc.)
  const logoFile = files.find(f => {
    const normalized = f.replace(/\.(png|jpg|jpeg)$/i, "")
      .toLowerCase()
      .replace(/[^a-z0-9_-]/g, "");
    return normalized === normalizedBrand;
  });
  
  // Serve with proper content-type
  res.set("Content-Type", mimeTypes[ext]);
  res.send(fileContent);
};
```

**Components Fixed:**
- `TopBrandModal.tsx` - Uses `/api/logo/brand/`
- `AllBrandsModal.tsx` - Uses `BrandLogo` component → `/api/logo/brand/`
- `BrandLogo.tsx` - Uses `/api/logo/brand/`

**Fallback Behavior:**
When logo not found (404), components display colored initials:
- "CeraVe" → "CE" in blue circle
- "Blue Buffalo" → "BB" in purple circle
- Uses consistent color mapping based on first character

**Key Insight:**
In a dual-backend architecture, use the backend that provides the most convenient interface for your data. The Express endpoint handles the brand name → filename translation, while Flask just serves files directly.

**See Also:**
- Multi-backend architecture patterns
- API endpoint design
- Brand logo database integration

---

## Video URLs not returned when client=all

**Status:** ✅ SOLVED

**Symptoms:**
- Videos display correctly in Builder.io preview
- Videos don't appear in dashboard when filtering to "All" clients
- Console shows `Ad has video_url? false undefined`
- API returns `video_url: null` even though video files exist
- Debug logs show searching in `/output/walmart/all/SBV` instead of actual client folder

**Root Cause:**
When querying with `client=all`, the backend correctly identifies each ad's actual client (e.g., `blue_bunny`, `halo_top`) from the file path and stores it as `file_client`. However, the path existence check and fallback search were using the query parameter `client` (which is `"all"`) instead of `file_client` when building file paths.

**The Bug:**
```python
# Line 1317 - WRONG: Uses query param 'client' instead of actual client
full_path = os.path.join(OUTPUT_ROOT, retailer, client, filename)

# Line 1353 - WRONG: Fallback search looks in wrong directory
search_dir = os.path.join(OUTPUT_ROOT, retailer, client, leaf)
```

This caused the backend to look for files in `/output/walmart/all/SBV/` (which doesn't exist) instead of `/output/walmart/blue_bunny/SBV/` (which does exist).

**The Fix:**
```python
# Line 1317 - CORRECT: Use file_client (actual client from file path)
full_path = os.path.join(OUTPUT_ROOT, retailer, file_client, filename)

# Line 1353 - CORRECT: Search in actual client directory
search_dir = os.path.join(OUTPUT_ROOT, retailer, file_client, leaf)
```

**Why It Matters:**
- The `client` parameter is the user's filter selection (`"all"`, `"blue_bunny"`, etc.)
- The `file_client` variable is the actual client folder where the ad's files are stored
- When `client="all"`, the code iterates through all client folders and sets `file_client` correctly for each ad
- File path operations must use `file_client`, not `client`

**Affected Code:**
- `web/builder_server_v2.py` lines 1317, 1323, 1350, 1353, 1354

**Debug Evidence:**
```
[build_media_urls_for_ad] walmart/blue_bunny: Found path: SBV/walmart__breyers__sbv__blue_bunny__chocolate_ice_cream__D2025-10-14_T23-02.11_1.png
⚠️  [walmart] Path in JSON doesn't exist: SBV/walmart__breyers__sbv__blue_bunny__chocolate_ice_cream__D2025-10-14_T23-02.11_1.png
🔍 [walmart] Search dir: /Users/.../output/walmart/all/SBV, exists=False
```

After fix:
```
[build_media_urls_for_ad] walmart/blue_bunny: Found path: SBV/walmart__breyers__sbv__blue_bunny__chocolate_ice_cream__D2025-10-14_T23-02.11_1.png
✓ File found at: /Users/.../output/walmart/blue_bunny/SBV/walmart__breyers__sbv__blue_bunny__chocolate_ice_cream__D2025-10-14_T23-02.11_1.png
```

**Key Insight:**
In multi-client queries, always distinguish between:
1. **Query parameter** (`client`) - User's filter selection
2. **File context** (`file_client`) - Actual location of ad's files

File operations must use `file_client` to access the correct directory structure.

**See Also:**
- Video overlay alignment in `AdModal.tsx`
- Media URL building in `build_media_urls_for_ad()`
- Client filtering in `/api/ads/cards` endpoint

---
