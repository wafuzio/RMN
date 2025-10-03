# New Retailer Onboarding Checklist

Use this for every new retailer. Keep PRs small and tick each box.

## Environment and paths

- [ ] Python 3.11.x
- [ ] `PLAYWRIGHT_BROWSERS_PATH` is set and user-writable  
  e.g., `~/Library/Application Support/RMN/playwright-browsers`
- [ ] Persistent profile at `~/Library/Application Support/RMN/profiles/<retailer>/`
- [ ] Return codes respected:  
  - `0` = success (≥1 artifacts)
  - `1` = extraction failure (0 artifacts)
  - `2` = bad args
  - `3` = no candidates found
- [ ] Subprocess env (when adapter spawns extractor) passes:  
  `PLAYWRIGHT_BROWSERS_PATH`, `<RETAILER>_PROFILE_DIR`, `PYTHONDONTWRITEBYTECODE=1`

## Taxonomy and output

- [ ] Add/extend `utils/path_taxonomy.TAXONOMY` for this retailer
- [ ] Create dirs only via `ensure_subdir(retailer, run_root, subdir)` (asserts invalid)
- [ ] README taxonomy updated from code: `python scripts/docs/update_docs.py`  
  (Run `scripts/docs/update_docs.py --check` in CI)

## Run JSON contract

- [ ] Include: `schema_version` ("1.0"), `retailer` ("<name>"), `count`, `keyword`, `search_term`, `timestamp`
- [ ] `source_file`: absolute path to saved HTML
- [ ] `source_url`: exact page URL (SRP) ← **required** (used for Referer and cookie seed)
- [ ] `results[].ads[]` include: `type`, `image_url` (absolute; normalize `/` and `//` and srcset), `href`, `message`, `description`, `cta`

## Browser + session bootstrap

- [ ] Choose policy and record decision in `docs/DEVLOG.md`:  
  **headed-but-hidden** OR **hardened headless**
- [ ] Seed cookies from `srp_url`; fallback seeds: `/search?query=milk` → `/`
- [ ] Log `[session] srp_url=...` and `[cookies] <domain>=N -> [cookie names]`
- [ ] Set context extra headers: Referer (srp_url or root), Accept, Accept-Language, User-Agent
- [ ] Optional health probe (helps debug):  
  `r = context.request.get("https://www.<retailer>.com/robots.txt", timeout=20000)`

## Extraction behavior

- [ ] **nav-first** for image docs (`page.goto(image, wait_until="commit")` → screenshot)
- [ ] `context.request` is best-effort fast path (one short attempt; log `[ctx] status`; bail quickly on !2xx)
- [ ] SRP element-screenshot fallback: find `img[src*="<filename>"]` across frames, ensure complete, `element.screenshot`
- [ ] Hard timeouts (waits 10–15s; nav 20–30s). Always close context in `finally`.
- [ ] `process_images` returns `saved_count`; `main` exits `1` when `saved_count==0`, `0` otherwise; exit `3` when no candidates

## Smoke proof in PR

- [ ] Log snippet shows: `[session] srp_url`, `[cookies] ... > 0`, and either `[ctx] status 2xx` or "Fallback screenshot saved..."
- [ ] Output tree under `output/<retailer>/<client>/<subdir>/...` with at least one artifact
- [ ] No cross-retailer folders (taxonomy guard held)
- [ ] README taxonomy block is up-to-date (generator ran)

---

## Quick Reference

### Headed-but-hidden args (recommended for CDN-sensitive sites like Kroger)

```python
args = [
    "--disable-dev-shm-usage", "--no-sandbox",
    "--no-first-run", "--no-default-browser-check",
    "--disable-session-crashed-bubble",
    "--start-minimized", "--window-position=0,0", "--window-size=10,10",
    "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows",
]
```

### Cookie seeding pattern

```python
seed_candidates = [
    srp_url,  # from JSON
    "https://www.<retailer>.com/search?query=milk",
    "https://www.<retailer>.com/",
]
cookies_ok = False
for seed in [u for u in seed_candidates if u]:
    page.goto(seed, wait_until="commit", timeout=60000)
    page.wait_for_timeout(1200)
    cookies = context.cookies("https://www.<retailer>.com")
    print(f"[cookies] <retailer>={len(cookies)} -> {[c['name'] for c in cookies[:6]]}")
    if len(cookies) > 0:
        cookies_ok = True
        break

context.set_extra_http_headers({
    "Referer": srp_url or "https://www.<retailer>.com/",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": REAL_UA,
})
```

### Navigation screenshot (primary)

```python
page.goto(image_url, wait_until="commit", timeout=30000)
page.wait_for_timeout(300)
page.screenshot(path=output_path, full_page=False)
```

### context.request fast path (optional)

```python
try:
    resp = context.request.get(image_url, timeout=5000, fail_on_status=False)
    print(f"[ctx] status {resp.status} for {image_url}")
    if 200 <= resp.status < 300:
        out.write_bytes(resp.body())
        saved_count += 1
        continue
except Exception as e:
    print(f"[ctx] request failed: {e}")
```

### SRP element-screenshot fallback (match by filename across frames)

```python
from urllib.parse import urlparse
basename = urlparse(image_url).path.split("/")[-1]
loc = page.locator(f'img[src*="{basename}"]').first
if not loc or not loc.count():
    for f in page.frames:
        cand = f.locator(f'img[src*="{basename}"]').first
        if cand and cand.count():
            loc = cand
            break
loc.wait_for(state="visible", timeout=10000)
page.wait_for_function(
    "el => { const i = el.tagName==='IMG'?el:el.querySelector('img'); return i && i.complete && i.naturalWidth>0; }",
    arg=loc, timeout=8000
)
loc.screenshot(path=output_path)
saved_count += 1
```

### Exit code pattern

```python
def process_images(...) -> int:
    saved_count = 0
    # ... extraction ...
    return saved_count

def main() -> int:
    saved = process_images(...)
    if saved == 0:
        return 1  # Failure (zero artifacts)
    return 0      # Success
```

### Subprocess env when launching extractor (from adapter)

```python
env = os.environ.copy()
env.setdefault("PLAYWRIGHT_BROWSERS_PATH",
               os.path.expanduser("~/Library/Application Support/RMN/playwright-browsers"))
env.setdefault("<RETAILER>_PROFILE_DIR",
               os.path.abspath("profiles/<retailer>"))
env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
subprocess.run(cmd, env=env, check=True, ...)
```

---

## Notes by retailer (examples to carry forward)

**Instacart:**
- Persistent profile required; location pin via zip; login modal guard; headless OK.
- SRP element screenshots are sufficient (no direct image fetch).

**Kroger:**
- Headed-but-hidden recommended; nav-first capture.
- Requires `source_url` in JSON; fallback seed to `/search?query=milk`.
- Exit 1 when `saved_count==0` to prevent GUI silent retries.

_(Record the choice in `docs/DEVLOG.md` when you onboard each retailer.)_

---

## See Also

- **README taxonomy** (auto-generated) — run: `python scripts/docs/update_docs.py`
- **docs/COMMON_ISSUES.md** (frequent failures and fixes)
- **docs/DEVLOG.md** (history by retailer/division; append a one-liner per decision)
