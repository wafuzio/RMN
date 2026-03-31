"""
Kroger Step Logger — Granular JSONL telemetry for Akamai debugging.

Ported from the Walmart StepLogger system that successfully identified PerimeterX
trigger points. Adapted for Akamai's three-layer detection (BMP sensor, Dynatrace
RUM, Client-side Protection).

Produces kroger_<keyword>_steps.jsonl with one JSON object per line.
Each event has: ts (absolute), t (relative seconds), event name, context data.

Usage:
    from kroger_step_logger import StepLogger, step, attach_network_listeners

    SL = StepLogger(base_dir="output", keyword="black_forest_ham")
    SL.log("home_goto_start", url="https://www.kroger.com/")

    with step(SL, "homepage_load"):
        page.goto("https://www.kroger.com/")

    attach_network_listeners(page, SL)  # Wire up request/response/akamai tracking
"""

import json
import os
import threading
import time
from contextlib import contextmanager
from typing import Optional


class StepLogger:
    """JSONL logger for detailed run telemetry."""

    def __init__(self, base_dir: str, keyword: str):
        self.base_dir = base_dir
        self.keyword = keyword
        self.path: Optional[str] = None
        self.lock = threading.Lock()
        self.t0 = time.time()

        # Akamai-specific counters
        self.sensor_posts = 0
        self.rum_beacons = 0
        self.blocks = 0
        self._abck_history = []  # Track _abck cookie evolution

    def _ensure_path(self):
        if self.path is None:
            safe_kw = "".join(c if c.isalnum() or c in "-_" else "_" for c in self.keyword)
            os.makedirs(self.base_dir, exist_ok=True)
            self.path = os.path.join(self.base_dir, f"kroger_{safe_kw}_steps.jsonl")

    def log(self, event: str, **data):
        """Log a single event to the JSONL file."""
        self._ensure_path()
        rec = {
            "ts": time.time(),
            "t": round(time.time() - self.t0, 3),
            "event": event,
        }
        rec.update(data)
        with self.lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def snapshot_abck(self, context, label: str = ""):
        """Capture current _abck cookie value for bot-score tracking."""
        try:
            cookies = context.cookies("https://www.kroger.com/")
            abck = next((c for c in cookies if c["name"] == "_abck"), None)
            if abck:
                val = abck["value"]
                self._abck_history.append({
                    "t": round(time.time() - self.t0, 3),
                    "label": label,
                    "value": val[:80],  # Truncate for readability
                    "length": len(val),
                })
                self.log("abck_snapshot", label=label, length=len(val),
                         prefix=val[:40], suffix=val[-20:] if len(val) > 60 else "")
        except Exception as e:
            self.log("abck_snapshot_error", label=label, error=str(e))


@contextmanager
def step(SL: StepLogger, name: str, **meta):
    """Context manager that logs step_start/step_end with duration."""
    SL.log("step_start", name=name, **meta)
    t0 = time.time()
    try:
        yield
    except Exception as e:
        SL.log("step_error", name=name, dur=round(time.time() - t0, 3), error=str(e))
        raise
    else:
        SL.log("step_end", name=name, dur=round(time.time() - t0, 3))


def attach_network_listeners(page, SL: StepLogger):
    """
    Wire Playwright event handlers to log every network event relevant to Akamai.

    Tracks:
    - Request failures (connection errors, timeouts)
    - Document responses (page navigations, redirects)
    - Akamai sensor POSTs (CHOKAO endpoints)
    - Dynatrace RUM / mPulse beacons
    - _sec/cpr/params (Client-side Protection config)
    - Frame navigations
    """

    def _on_request_failed(req):
        SL.log("req_failed",
               url=req.url[:200],
               method=req.method,
               resource=req.resource_type,
               failure=str(req.failure))

    def _on_response(res):
        url = res.url
        status = res.status
        method = res.request.method

        # Log all document responses (navigations)
        if res.request.resource_type == "document":
            SL.log("resp_doc",
                   url=url[:200],
                   status=status,
                   method=method)

        # --- Akamai sensor POSTs ---
        # CHOKAO-style obfuscated endpoint: long alphanumeric path segment
        # Two flavors: body field (202) = token/CMP, sensor_data field (201) = telemetry
        if method == "POST" and status in (200, 201, 202):
            # Heuristic: Akamai sensor endpoints have long random-looking paths
            # and are POST requests returning 201/202
            path = url.split("?")[0]
            segments = path.split("/")
            # Look for path segments that are 20+ chars of mixed alphanumeric (CHOKAO pattern)
            has_chokao = any(
                len(seg) >= 20 and seg.isalnum() and not seg.isdigit()
                for seg in segments
            )
            if has_chokao or "_sec/cpr" in url:
                SL.sensor_posts += 1
                SL.log("akamai_sensor",
                       url=url[:200],
                       status=status,
                       type="cpr_config" if "_sec/cpr" in url else (
                           "token_cmp" if status == 202 else "sensor_telemetry"
                       ),
                       count=SL.sensor_posts)

        # --- Dynatrace RUM / mPulse / Boomerang beacons ---
        if "/rb_" in url or "mPulse" in url or "boomerang" in url.lower():
            SL.rum_beacons += 1
            SL.log("rum_beacon",
                   url=url[:200],
                   status=status,
                   count=SL.rum_beacons)

    def _on_frame_navigated(frame):
        SL.log("nav",
               url=frame.url[:200] if frame.url else "<empty>",
               name=frame.name or "<main>")

    # Attach handlers
    page.on("requestfailed", _on_request_failed)
    page.on("response", _on_response)
    page.on("framenavigated", _on_frame_navigated)

    SL.log("network_listeners_attached")


def log_navigator_diagnostics(page, SL: StepLogger, label: str = ""):
    """Log full navigator fingerprint diagnostics."""
    try:
        diag = page.evaluate("""() => ({
            webdriver: navigator.webdriver,
            userAgent: navigator.userAgent,
            platform: navigator.platform,
            language: navigator.language,
            languages: navigator.languages,
            hardwareConcurrency: navigator.hardwareConcurrency,
            deviceMemory: navigator.deviceMemory,
            plugins: navigator.plugins.length,
            vendor: navigator.vendor,
            maxTouchPoints: navigator.maxTouchPoints,
            pdfViewerEnabled: navigator.pdfViewerEnabled,
            cookieEnabled: navigator.cookieEnabled,
        })""")
        SL.log("navigator_diag", label=label, **diag)
    except Exception as e:
        SL.log("navigator_diag_error", label=label, error=str(e))


def log_webgl_diagnostics(page, SL: StepLogger, label: str = ""):
    """Log WebGL fingerprint (both masked and unmasked)."""
    try:
        webgl = page.evaluate("""() => {
            const canvas = document.createElement('canvas');
            const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
            if (!gl) return {error: 'WebGL not available'};
            const ext = gl.getExtension('WEBGL_debug_renderer_info');
            return {
                vendor: gl.getParameter(gl.VENDOR),
                renderer: gl.getParameter(gl.RENDERER),
                unmaskedVendor: ext ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : 'N/A',
                unmaskedRenderer: ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : 'N/A',
                version: gl.getParameter(gl.VERSION),
            };
        }""")
        SL.log("webgl", label=label, **webgl)
    except Exception as e:
        SL.log("webgl_error", label=label, error=str(e))


def log_akamai_trip(SL: StepLogger, reason: str, **extra):
    """Log the exact moment Akamai detection is triggered."""
    SL.blocks += 1
    SL.log("akamai_trip", reason=reason, block_count=SL.blocks, **extra)
