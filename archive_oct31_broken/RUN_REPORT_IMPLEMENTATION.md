# Run Report System - Implementation Guide

## ✅ What's Been Done

### 1. Report Writer Function Added (Lines 237-296)
- `_write_run_report(base_dir, report)` creates both JSON and Markdown reports
- JSON: `run_report.json` - machine-readable
- Markdown: `run_report.md` - human-readable

### 2. Metrics Buckets Added (Lines 1493-1501)
- `started_at` - ISO timestamp
- `timings` - to_home_ms, after_submit_px_ms, results_ready_ms
- `px_stats` - tries, cycles, cleared
- `net_counters` - req_failed, resp_doc, route_errors
- `env_info` - ua, webgl
- `cookies_info` - pre/post counts and names
- `artifacts` - paths to all saved files

## 🔧 Remaining Changes Needed

### A. Increment Network Counters in Listeners

**In `_req_failed` (around line 485):**
```python
def _req_failed(req):
    if CURRENT_SL:
        CURRENT_SL.log("req_failed",
                       url=req.url, method=req.method,
                       resource=req.resource_type, failure=str(req.failure))
    net_counters["req_failed"] += 1  # ADD THIS
```

**In `_resp_doc` (around line 491):**
```python
def _resp_doc(res):
    try:
        req = res.request
        if req.is_navigation_request() and req.resource_type == "document":
            if CURRENT_SL:
                CURRENT_SL.log("resp_doc",
                               url=res.url, status=res.status,
                               method=req.method, fromCache=res.from_service_worker)
            net_counters["resp_doc"] += 1  # ADD THIS
    except Exception as e:
        if CURRENT_SL:
            CURRENT_SL.log("resp_doc_error", err=str(e))
```

**In `_guard_nav` except block (around line 527):**
```python
except Exception as e:
    # Do not let route errors kill the run — log and best-effort continue
    if CURRENT_SL:
        CURRENT_SL.log("route_error", url=req.url, err=str(e))
    net_counters["route_errors"] += 1  # ADD THIS
    try:
        return route.continue_()
    except Exception:
        pass
```

### B. Fill Environment Info After Homepage

**After UA and WebGL logging (around line 1660):**
```python
# Log WebGL info (sanity check GPU isn't SwiftShader)
try:
    vendor = page.evaluate("""...""")
    renderer = page.evaluate("""...""")
    SL.log("webgl", vendor=vendor, renderer=renderer)
    print(f"[webgl] vendor={vendor}, renderer={renderer}")
    env_info["webgl"] = {"vendor": vendor, "renderer": renderer}  # ADD THIS
except Exception:
    pass

# Also after UA capture:
ua = page.evaluate("() => navigator.userAgent")
print(f"[ua] {ua}")
SL.log("user_agent", ua=ua)
env_info["ua"] = ua  # ADD THIS

# And timing to home:
timings["to_home_ms"] = int((time.time() - SL.t0) * 1000)  # ADD THIS
```

### C. Fill Cookies Info

**After pre_cookies (around line 1635):**
```python
pre_cookies = _cookie_names(ctx)
print(f"[cookies] pre-run walmart.com: {len(pre_cookies)} names={pre_cookies[:8]}")
SL.log("cookies_pre", count=len(pre_cookies), names=pre_cookies[:8])
cookies_info["pre_count"] = len(pre_cookies)  # ADD THIS
cookies_info["pre_names"] = pre_cookies[:12]  # ADD THIS
```

**In finally block after post_cookies (around line 2010):**
```python
post_cookies = _cookie_names(ctx)
print(f"[cookies] post-run walmart.com: {len(post_cookies)} names={post_cookies[:8]}")
SL.log("cookies_post", count=len(post_cookies), names=post_cookies[:8])
cookies_info["post_count"] = len(post_cookies)  # ADD THIS
cookies_info["post_names"] = post_cookies[:12]  # ADD THIS
```

### D. Fill Timings

**After submit (around line 1723):**
```python
px_now = _still_px_modal(page)
ms_since_submit = int((time.time() - (SUBMIT.get("t") or time.time())) * 1000)
cookies_now = sorted(set(c["name"] for c in page.context.cookies("https://www.walmart.com/")))
SL.log("after_submit", method=SUBMIT.get("method","?"), px_visible=bool(px_now),
       ms_since_submit=ms_since_submit, url=page.url, cookies=cookies_now[:6])
timings["after_submit_px_ms"] = ms_since_submit if px_now else None  # ADD THIS
```

**After results ready (around line 1870):**
```python
ready, which = _wait_for_search_results(page, timeout_ms=15000)
SL.log("results_ready", ready=ready, selector=which, url=page.url)
if ready:
    timings["results_ready_ms"] = int((time.time() - (SUBMIT.get("t") or time.time()))*1000)  # ADD THIS
    stable = _wait_results_stable(page)
    SL.log("results_stable", stable=stable)
```

### E. Track Artifacts

**After steps log path set:**
```python
artifacts["steps_log"] = SL.path  # ADD after first SL.log() call
```

**After trace saved (in finally block, around line 2015):**
```python
trace_path = os.path.join(base_dir, safe_filename(f"{SLUG}_{keyword}_trace.zip"))
ctx.tracing.stop(path=trace_path)
print(f"[trace] saved → {trace_path}")
artifacts["trace_zip"] = trace_path  # ADD THIS
```

**After no_results dump (around line 1880):**
```python
if not ready:
    say("warn", f"[{retailer}] No results detected - saving forensics")
    _dump_html_png(page, base_dir, f"{SLUG}_{keyword}_no_results")
    artifacts["no_results_html"] = os.path.join(base_dir, safe_filename(f"{SLUG}_{keyword}_no_results.html"))  # ADD
    artifacts["no_results_png"] = os.path.join(base_dir, safe_filename(f"{SLUG}_{keyword}_no_results.png"))  # ADD
```

**After HTML saved (around line 1935):**
```python
html_path = os.path.join(base_dir, safe_filename(f"{SLUG}_{keyword}_search.html"))
try:
    content = page.content()
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(content)
    html_saved = 1
    artifacts["saved_html"] = html_path  # ADD THIS
    say("info", f"[{retailer}] HTML captured (1/1)")
except Exception as e:
    say("warn", f"[{retailer}] HTML save failed: {e}")
```

**After meta.json saved (around line 1990):**
```python
try:
    meta_path = os.path.join(base_dir, safe_filename(f"{SLUG}_{keyword}_meta.json"))
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    assets.append(meta_path)
    artifacts["meta_json"] = meta_path  # ADD THIS
except Exception:
    pass
```

### F. Write Report on All Exit Paths

**On bail returns (add before each early return):**
```python
# Example for px_locked on home:
say("error", f"[{retailer}] Failed to clear PX after max attempts")
SL.log("px_result", where="home", ok=False)
bail_reason = "px_locked"
meta["bail"] = bail_reason
meta["steps_log"] = SL.path

# ADD THIS BLOCK:
report = {
    "keyword": keyword,
    "outcome": "bail",
    "bail_reason": bail_reason,
    "started_at": started_at,
    "timings": timings,
    "env": env_info,
    "cookies": cookies_info,
    "px": px_stats,
    "network": net_counters,
    "artifacts": {**artifacts, "steps_log": SL.path},
}
_write_run_report(base_dir, report)

return CaptureResult(html_saved=0, shots=[], assets=[], meta=meta)
```

**On normal return (at the very end, around line 2000):**
```python
# Add step log path to meta
meta["steps_log"] = SL.path if SL.path else None

# ADD THIS BLOCK:
outcome = "success" if html_saved > 0 else "fail"
report = {
    "keyword": keyword,
    "outcome": outcome,
    "bail_reason": None,
    "started_at": started_at,
    "timings": timings,
    "env": env_info,
    "cookies": cookies_info,
    "px": px_stats,
    "network": net_counters,
    "artifacts": {**artifacts, "steps_log": SL.path},
}
paths = _write_run_report(base_dir, report)
if paths:
    SL.log("run_report_paths", **paths)

SL.log("run_complete", html_saved=html_saved, shots_count=len(shots), assets_count=len(assets))
```

## 📝 Quick Implementation Checklist

- [ ] Add `net_counters["req_failed"] += 1` in `_req_failed`
- [ ] Add `net_counters["resp_doc"] += 1` in `_resp_doc`
- [ ] Add `net_counters["route_errors"] += 1` in `_guard_nav` except
- [ ] Fill `env_info["ua"]` and `env_info["webgl"]` after homepage
- [ ] Fill `timings["to_home_ms"]` after homepage load
- [ ] Fill `cookies_info` pre/post
- [ ] Fill `timings["after_submit_px_ms"]` after submit
- [ ] Fill `timings["results_ready_ms"]` when results ready
- [ ] Track all artifact paths as they're created
- [ ] Write report on all bail returns (6 locations)
- [ ] Write report on normal return (1 location)

## 🎯 Result

After implementation, every run will produce:
- `run_report.json` - Full machine-readable report
- `run_report.md` - Human-readable summary

Example `run_report.md`:
```markdown
# Walmart Run Report — pickle spears
- started: 2025-10-08T14:30:00
- outcome: bail  
- bail_reason: px_locked

## Timings
- to_home_ms: 1234
- after_submit_px_ms: 234
- results_ready_ms: None

## Environment
- user_agent: Mozilla/5.0 ... Chrome/131.0.0.0 ...
- webgl_vendor: Google Inc.  
- webgl_renderer: ANGLE (Apple, ANGLE Metal Renderer: Apple M1, Unspecified Version)

## Cookies
- pre_count: 8  pre_names: ['_pxvid', '_px3', ...]
- post_count: 8 post_names: ['_pxvid', '_px3', ...]

## PX
- tries: 3
- cycles: 1
- cleared: False

## Network Forensics
- req_failed: 2
- resp_doc: 5
- route_errors: 0

## Artifacts
- steps_log: /path/to/walmart_pickle_spears_steps.jsonl
- trace_zip: /path/to/walmart_pickle_spears_trace.zip
- no_results_html: /path/to/walmart_pickle_spears_no_results.html
```

This gives you a complete dossier you can skim in seconds!
