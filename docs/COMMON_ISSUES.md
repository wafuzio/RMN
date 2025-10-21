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
