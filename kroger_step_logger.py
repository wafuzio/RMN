import json
import os
import sys
import threading
import time
from contextlib import contextmanager
from typing import Optional


class StepLogger:
    def __init__(self, base_dir: str, keyword: str):
        self.base_dir = os.path.abspath(base_dir)
        self.keyword = keyword
        self.path: Optional[str] = None
        self.lock = threading.Lock()
        self.t0 = time.time()
        self.sensor_posts = 0
        self.rum_beacons = 0
        self.blocks = 0
        self._abck_history = []
        self.last_write_error: Optional[str] = None
        self._ensure_path()

    def _ensure_path(self):
        if self.path is None:
            safe_kw = "".join(c if c.isalnum() or c in "-_" else "_" for c in self.keyword)
            os.makedirs(self.base_dir, exist_ok=True)
            self.path = os.path.join(self.base_dir, f"kroger_{safe_kw}_steps.jsonl")

    def _coerce_jsonable(self, value):
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, dict):
            return {str(k): self._coerce_jsonable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._coerce_jsonable(v) for v in value]
        return str(value)

    def log(self, event: str, **data):
        self._ensure_path()
        rec = {
            "ts": time.time(),
            "t": round(time.time() - self.t0, 3),
            "event": event,
        }
        rec.update({k: self._coerce_jsonable(v) for k, v in data.items()})
        try:
            with self.lock:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            self.last_write_error = None
        except Exception as e:
            self.last_write_error = str(e)
            try:
                print(f"[kroger_step_logger] write failed for {self.path}: {e}", file=sys.stderr)
            except Exception:
                pass

    def snapshot_abck(self, context, label: str = ""):
        try:
            cookies = context.cookies("https://www.kroger.com/")
            abck = next((c for c in cookies if c["name"] == "_abck"), None)
            if abck:
                val = abck["value"]
                self._abck_history.append({
                    "t": round(time.time() - self.t0, 3),
                    "label": label,
                    "value": val[:80],
                    "length": len(val),
                })
                self.log(
                    "abck_snapshot",
                    label=label,
                    length=len(val),
                    prefix=val[:40],
                    suffix=val[-20:] if len(val) > 60 else "",
                )
        except Exception as e:
            self.log("abck_snapshot_error", label=label, error=str(e))


@contextmanager
def step(SL: StepLogger, name: str, **meta):
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
    def _on_request_failed(req):
        SL.log(
            "req_failed",
            url=req.url[:200],
            method=req.method,
            resource=req.resource_type,
            failure=str(req.failure),
        )

    def _on_response(res):
        url = res.url
        status = res.status
        method = res.request.method

        if res.request.resource_type == "document":
            SL.log("resp_doc", url=url[:200], status=status, method=method)

        if method == "POST" and status in (200, 201, 202):
            path = url.split("?")[0]
            segments = path.split("/")
            has_chokao = any(
                len(seg) >= 20 and seg.isalnum() and not seg.isdigit()
                for seg in segments
            )
            if has_chokao or "_sec/cpr" in url:
                SL.sensor_posts += 1
                SL.log(
                    "akamai_sensor",
                    url=url[:200],
                    status=status,
                    type="cpr_config" if "_sec/cpr" in url else (
                        "token_cmp" if status == 202 else "sensor_telemetry"
                    ),
                    count=SL.sensor_posts,
                )

        if "/rb_" in url or "mPulse" in url or "boomerang" in url.lower():
            SL.rum_beacons += 1
            SL.log("rum_beacon", url=url[:200], status=status, count=SL.rum_beacons)

    def _on_frame_navigated(frame):
        SL.log("nav", url=frame.url[:200] if frame.url else "<empty>", name=frame.name or "<main>")

    page.on("requestfailed", _on_request_failed)
    page.on("response", _on_response)
    page.on("framenavigated", _on_frame_navigated)
    SL.log("network_listeners_attached")


def log_navigator_diagnostics(page, SL: StepLogger, label: str = ""):
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
    SL.blocks += 1
    SL.log("akamai_trip", reason=reason, block_count=SL.blocks, **extra)
