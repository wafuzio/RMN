# Opensteer Integration Plan
# walmart_search_and_capture.py — session 2026-04-12

## The problem this solves

The existing flow bails at two hard-block points:
- `:2919` — blocked on first navigation to homepage
- `:3296` — blocked immediately after search submit

Both currently `return CaptureResult(html_saved=0, ...)` and stop. The opensteer
session proved that a human driving a headed Chromium browser with a real Chrome
profile can navigate through Akamai and get clean search results. The integration
is: when a hard block fires, instead of bailing, hand control to the user via
opensteer, extract the resulting warm session state, inject it back into the
existing Playwright context, and resume the normal flow.

---

## Integration architecture

### New function: `_opensteer_warm_session(profile_dir, target_url) -> dict`

This is the only new piece of code. Everything else is wiring into existing hooks.

What it does:
1. Clones the scraper's `WALMART_PROFILE_DIR` into an opensteer workspace so the
   human session starts with the same cookies/fingerprint the scraper already has
2. Opens that workspace headed so the user sees a browser window
3. Prompts the user (CLI or GUI callback) to navigate through the block manually
4. Once the user signals clear, exports cookies and localStorage from the warm session
5. Returns them as a dict the caller can inject into the Playwright context

Sketch:
```python
import subprocess, json

def _opensteer_warm_session(profile_dir: str, target_url: str, say=None) -> dict:
    """
    Launch an opensteer headed browser pre-seeded with the scraper profile.
    Let the user navigate past Akamai/PX manually.
    Return session state (cookies + localStorage) to inject into Playwright ctx.
    """
    WS = "walmart-warm"

    # 1. Clone scraper profile into opensteer workspace
    if say: say("info", "[opensteer] Cloning scraper profile into warm session...")
    subprocess.run([
        "opensteer", "browser", "clone", "--workspace", WS,
        "--source-user-data-dir", profile_dir,
        "--source-profile-directory", "Default"
    ], capture_output=True)

    # 2. Open target URL headed (user will see the window)
    if say: say("info", "[opensteer] Opening browser headed — navigate past the block, then return here")
    subprocess.run([
        "opensteer", "open", target_url,
        "--workspace", WS,
        "--headless", "false"
    ], capture_output=True)

    # 3. Wait for user to confirm clear
    if say: say("warn", "[opensteer] ⚠️  Browser window is open. Navigate to search results, then press Enter here.")
    input("[opensteer] Press Enter when Walmart search results are visible...")

    # 4. Export cookies from warm session
    cookies_raw = subprocess.run([
        "opensteer", "exec",
        "return await this.cookies('walmart.com')",
        "--workspace", WS
    ], capture_output=True, text=True)

    storage_raw = subprocess.run([
        "opensteer", "exec",
        "return await this.storage('walmart.com', 'local')",
        "--workspace", WS
    ], capture_output=True, text=True)

    # 5. Clean up headed browser (keep workspace for forensics)
    subprocess.run(["opensteer", "browser", "delete", "--workspace", WS], capture_output=True)

    try:
        cookies = json.loads(cookies_raw.stdout)
    except Exception:
        cookies = []
    try:
        local_storage = json.loads(storage_raw.stdout)
    except Exception:
        local_storage = {}

    return {"cookies": cookies, "local_storage": local_storage}
```

---

### New function: `_inject_warm_session(ctx, page, session: dict, SL=None)`

Takes the dict from `_opensteer_warm_session` and loads it into the existing
Playwright context. Must be called before any navigation retry.

```python
def _inject_warm_session(ctx, page, session: dict, SL=None):
    """Inject opensteer warm session state into the existing Playwright context."""
    cookies = session.get("cookies", [])
    local_storage = session.get("local_storage", {})

    if cookies:
        # Playwright accepts cookies in this format directly
        try:
            ctx.add_cookies(cookies)
            if SL: SL.log("warm_session_cookies_injected", count=len(cookies))
        except Exception as e:
            if SL: SL.log("warm_session_cookie_error", error=str(e))

    if local_storage and isinstance(local_storage, dict):
        try:
            page.evaluate(f"Object.assign(localStorage, {json.dumps(local_storage)})")
            if SL: SL.log("warm_session_storage_injected", keys=list(local_storage.keys())[:8])
        except Exception as e:
            if SL: SL.log("warm_session_storage_error", error=str(e))
```

---

## Insertion points in the existing flow

### Point 1: Hard block on first navigation (`:2919`)

Current code bails here:
```python
if _on_blocked(page.url):
    SL.log("hard_block", where="initial_home", ...)
    ...
    return CaptureResult(html_saved=0, ...)
```

Replace the bail with a warm-session recovery attempt:
```python
if _on_blocked(page.url):
    SL.log("hard_block", where="initial_home", url=page.url)
    say("warn", f"[{retailer}] Hard blocked on first nav — attempting warm session recovery")

    session = _opensteer_warm_session(profile_dir, "https://www.walmart.com", say=say)
    _inject_warm_session(ctx, page, session, SL=SL)
    SL.log("warm_session_injected", cookies=len(session.get("cookies", [])))

    # Retry homepage
    phase = _goto_home(page, SL)
    SL.log("home_goto_phase_after_warm", phase=phase)

    if _on_blocked(page.url):
        # Still blocked after human assist — genuine bail
        SL.log("hard_block_after_warm", where="initial_home")
        say("error", f"[{retailer}] Still blocked after warm session — bailing")
        bail_reason = "hard_block_after_warm"
        meta["bail"] = bail_reason
        report = _build_report(keyword, "bail", bail_reason, started_at, timings,
                               env_info, cookies_info, px_stats, net_counters, artifacts, SL)
        _write_run_report(base_dir, report)
        return CaptureResult(html_saved=0, shots=[], assets=[], meta=meta)
```

### Point 2: Hard block after search submit (`:3296`)

Current code bails here:
```python
if _on_blocked(page.url) and (time.time() - LAST_NAV_DONE_TS["t"] < 5.0):
    SL.log("hard_block", where="after_submit", ...)
    ...
    return CaptureResult(html_saved=0, ...)
```

Replace with the same pattern — warm session, inject, retry search navigation.
The retry here should navigate directly to `url` (the search URL) rather than
going back through the homepage warmup, since we just came from the homepage.

```python
if _on_blocked(page.url) and (time.time() - LAST_NAV_DONE_TS["t"] < 5.0):
    SL.log("hard_block", where="after_submit", url=page.url)
    say("warn", f"[{retailer}] Hard blocked after submit — warm session recovery")

    session = _opensteer_warm_session(profile_dir, url, say=say)  # url = search URL
    _inject_warm_session(ctx, page, session, SL=SL)

    # Navigate directly to search URL with warm cookies
    page.goto(url, wait_until="domcontentloaded")
    _nav_mark_done(SL=SL)

    if _on_blocked(page.url):
        bail_reason = "hard_block_after_warm"
        meta["bail"] = bail_reason
        report = _build_report(keyword, "bail", bail_reason, started_at, timings,
                               env_info, cookies_info, px_stats, net_counters, artifacts, SL)
        _write_run_report(base_dir, report)
        return CaptureResult(html_saved=0, shots=shots, assets=assets, meta=meta)
    # Fall through to existing results-ready / PX check flow
```

---

## One caveat to verify before shipping

Akamai's `ak_bmsc` and `bm_sz` cookies contain encrypted session signatures that may
be tied to browser fingerprint (UA, TLS fingerprint, header order). Injecting them
from the opensteer Chromium into the Playwright Chromium context might get rejected if
the fingerprints diverge.

Two ways to check:
1. Run the warm-session integration once and watch the `cookie_suspicious` log at `:2835`.
   If `ak_bmsc` survives the injection and the scraper gets past the block, it worked.
2. If cookies are rejected, fall back to writing the opensteer user-data-dir back to
   `WALMART_PROFILE_DIR` directly (file copy), then relaunching the Playwright context
   fresh. That's heavier but fingerprint-exact.

Start with cookie injection (simpler). Only move to the file-copy fallback if the
suspicious cookie check fires after warm session injection.

---

## What doesn't change

The existing PX solver (`_solve_px_until_clear` :2392), homepage warmup
(`_homepage_warmup` :1856), scroll behavior, ad extraction, screenshot logic,
report writing — none of that is touched. Warm session recovery is purely an
escape hatch at the two hard-block bailout points. Everything downstream of those
points runs exactly as before.

---

## Files from this session (for reference)

```
opensteer intel/
  summary.json          API endpoint map, hydration findings
  products.json         124 products, 20 sponsored (proactiv search)
  ads.json              27 ad unit bounding boxes + text + image URLs
  ad-screenshots/       27 cropped ad tiles (visual reference for selector validation)
  fullpage.png          Full-page stitch (reference only)
  video-assets/         Empty — no video on this keyword
```
