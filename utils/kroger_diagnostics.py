"""
Kroger Diagnostic Logging System

Provides comprehensive step-by-step logging, fingerprint diagnostics, and forensic
artifact collection for debugging Akamai bot detection issues.

Usage:
    from utils.kroger_diagnostics import KrogerDiagnostics
    
    diag = KrogerDiagnostics(output_dir="output/kroger/client/runs")
    diag.log("homepage_load_start", url="https://www.kroger.com/")
    diag.collect_diagnostics(page, context, "after_homepage_load")
    diag.check_akamai_block(page)
    diag.save_forensics(page, "homepage_loaded")
    diag.finalize()  # Saves steps.jsonl and report.json
"""

import os
import time
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, Tuple


class KrogerDiagnostics:
    """Comprehensive diagnostic logging for Kroger scraping operations."""
    
    def __init__(self, output_dir: str, run_id: Optional[str] = None):
        """
        Initialize diagnostic logger.
        
        Args:
            output_dir: Directory where diagnostic files will be saved
            run_id: Optional run identifier (defaults to timestamp)
        """
        self.output_dir = Path(output_dir)
        self.run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.start_time = time.time()
        self.steps = []
        self.diagnostics = {}
        self.blocks_detected = []
        
        # Network forensics counters (from Walmart system)
        self.net_counters = {
            "req_failed": 0,
            "resp_doc": 0,
            "route_errors": 0,
        }
        
        # Timing tracking
        self.timings = {
            "to_home_ms": None,
            "after_search_ms": None,
            "results_ready_ms": None,
        }
        
        # Cookie tracking
        self.cookies_info = {
            "pre_count": 0,
            "pre_names": [],
            "post_count": 0,
            "post_names": [],
        }
        
        # Environment info
        self.env_info = {
            "ua": None,
            "webgl": None,
        }
        
        # Artifacts tracking
        self.artifacts = {
            "steps_log": None,
            "trace_zip": None,
            "screenshots": [],
            "html_files": [],
        }
        
        # Create diagnostics subdirectory
        self.diag_dir = self.output_dir / f"diagnostics_{self.run_id}"
        self.diag_dir.mkdir(parents=True, exist_ok=True)
        
        # Initial log
        self.log("diagnostic_session_start", run_id=self.run_id, output_dir=str(self.output_dir))
    
    def log(self, event: str, **kwargs):
        """
        Log an event with microsecond-precision timestamp.
        
        Args:
            event: Event name/type
            **kwargs: Additional event metadata
        """
        entry = {
            "ts": time.time(),
            "elapsed_ms": int((time.time() - self.start_time) * 1000),
            "event": event,
            **kwargs
        }
        self.steps.append(entry)
        
        # Also print to console for real-time monitoring
        metadata = ", ".join(f"{k}={v}" for k, v in kwargs.items() if k not in ["html", "content"])
        print(f"[{entry['elapsed_ms']:6d}ms] {event}: {metadata}")
    
    def collect_diagnostics(self, page, context, checkpoint: str):
        """
        Collect comprehensive browser diagnostics.
        
        Args:
            page: Playwright page object
            context: Playwright browser context
            checkpoint: Name of this diagnostic checkpoint
        """
        self.log("collecting_diagnostics", checkpoint=checkpoint)
        
        diag = {}
        
        try:
            # Navigator properties
            nav = page.evaluate("""() => ({
                webdriver: navigator.webdriver,
                userAgent: navigator.userAgent,
                platform: navigator.platform,
                language: navigator.language,
                languages: navigator.languages,
                hardwareConcurrency: navigator.hardwareConcurrency,
                deviceMemory: navigator.deviceMemory,
                pluginsLength: navigator.plugins.length,
                vendor: navigator.vendor,
                vendorSub: navigator.vendorSub,
                productSub: navigator.productSub,
                maxTouchPoints: navigator.maxTouchPoints,
            })""")
            diag["navigator"] = nav
            self.log("navigator_collected", checkpoint=checkpoint, webdriver=nav.get("webdriver"))
            
            # WebGL fingerprint
            webgl = page.evaluate("""() => {
                const canvas = document.createElement('canvas');
                const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
                if (!gl) return {error: 'WebGL not available'};
                
                const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
                return {
                    vendor: gl.getParameter(gl.VENDOR),
                    renderer: gl.getParameter(gl.RENDERER),
                    unmaskedVendor: debugInfo ? gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL) : 'N/A',
                    unmaskedRenderer: debugInfo ? gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) : 'N/A',
                    version: gl.getParameter(gl.VERSION),
                    shadingLanguageVersion: gl.getParameter(gl.SHADING_LANGUAGE_VERSION),
                };
            }""")
            diag["webgl"] = webgl
            self.log("webgl_collected", checkpoint=checkpoint, renderer=webgl.get("unmaskedRenderer", "N/A")[:50])
            
            # Cookies
            cookies = context.cookies()
            cookie_names = [c["name"] for c in cookies]
            diag["cookies"] = {
                "count": len(cookies),
                "names": cookie_names[:20],
            }
            
            # Check for Akamai-specific cookies
            akamai_cookies = [n for n in cookie_names if any(x in n.lower() for x in ["ak_", "bm_", "abck"])]
            if akamai_cookies:
                diag["akamai_cookies"] = akamai_cookies
                self.log("akamai_cookies_found", checkpoint=checkpoint, cookies=akamai_cookies)
            
            # Viewport
            viewport = page.viewport_size
            diag["viewport"] = viewport
            
            # URL and title
            diag["url"] = page.url
            diag["title"] = page.title()
            
            self.log("diagnostics_collected", checkpoint=checkpoint, url=page.url)
            
        except Exception as e:
            self.log("diagnostics_error", checkpoint=checkpoint, error=str(e))
            diag["error"] = str(e)
        
        self.diagnostics[checkpoint] = diag
        return diag
    
    def check_akamai_block(self, page) -> Tuple[bool, str, str]:
        """
        Check if Akamai has blocked the page.
        
        Args:
            page: Playwright page object
            
        Returns:
            Tuple of (is_blocked, reason, details)
        """
        try:
            content = page.content()
            url = page.url
            
            # Akamai Access Denied patterns
            if "<title>Access Denied</title>" in content:
                self.log("akamai_block_detected", reason="access_denied_title", url=url)
                self.blocks_detected.append({
                    "ts": time.time(),
                    "reason": "access_denied_title",
                    "url": url,
                })
                return True, "access_denied", "Title: Access Denied"
            
            if "errors.edgesuite.net" in content:
                self.log("akamai_block_detected", reason="edgesuite_error", url=url)
                self.blocks_detected.append({
                    "ts": time.time(),
                    "reason": "edgesuite_error",
                    "url": url,
                })
                return True, "edgesuite_error", "Akamai CDN error page"
            
            if "You don't have permission to access" in content:
                self.log("akamai_block_detected", reason="permission_denied", url=url)
                self.blocks_detected.append({
                    "ts": time.time(),
                    "reason": "permission_denied",
                    "url": url,
                })
                return True, "permission_denied", "Permission denied message"
            
            if "Reference #" in content and "blocked" in content.lower():
                self.log("akamai_block_detected", reason="reference_block", url=url)
                self.blocks_detected.append({
                    "ts": time.time(),
                    "reason": "reference_block",
                    "url": url,
                })
                return True, "reference_block", "Akamai reference number block"
            
            # Check for suspiciously small page
            if len(content) < 1000 and "kroger" not in content.lower():
                self.log("akamai_block_suspected", reason="small_page", size=len(content), url=url)
                self.blocks_detected.append({
                    "ts": time.time(),
                    "reason": "small_page_suspected",
                    "url": url,
                    "size": len(content),
                })
                return True, "small_page", f"Page only {len(content)} bytes"
            
            self.log("no_block_detected", url=url, content_size=len(content))
            return False, "", ""
            
        except Exception as e:
            self.log("block_check_error", error=str(e))
            return False, "", f"Check error: {e}"
    
    def save_forensics(self, page, label: str) -> bool:
        """
        Save screenshot and HTML for forensic analysis.
        
        Args:
            page: Playwright page object
            label: Label for this forensic snapshot
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Screenshot
            screenshot_path = self.diag_dir / f"{label}_screenshot.png"
            page.screenshot(path=str(screenshot_path))
            self.log("screenshot_saved", label=label, path=str(screenshot_path))
            
            # HTML
            html_path = self.diag_dir / f"{label}_page.html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(page.content())
            self.log("html_saved", label=label, path=str(html_path), size=len(page.content()))
            
            return True
        except Exception as e:
            self.log("forensics_save_error", label=label, error=str(e))
            return False
    
    def track_cookies(self, context, checkpoint: str):
        """
        Track cookie state for reputation analysis.
        
        Args:
            context: Playwright browser context
            checkpoint: 'pre' or 'post' run
        """
        try:
            cookies = context.cookies("https://www.kroger.com/")
            cookie_names = sorted([c["name"] for c in cookies])
            
            if checkpoint == "pre":
                self.cookies_info["pre_count"] = len(cookie_names)
                self.cookies_info["pre_names"] = cookie_names[:12]
                self.log("cookies_pre", count=len(cookie_names), names=cookie_names[:8])
            elif checkpoint == "post":
                self.cookies_info["post_count"] = len(cookie_names)
                self.cookies_info["post_names"] = cookie_names[:12]
                self.log("cookies_post", count=len(cookie_names), names=cookie_names[:8])
        except Exception as e:
            self.log("cookie_tracking_error", checkpoint=checkpoint, error=str(e))
    
    def track_timing(self, checkpoint: str, value_ms: Optional[int] = None):
        """
        Track timing metrics.
        
        Args:
            checkpoint: Timing checkpoint name
            value_ms: Optional explicit value, otherwise calculates from start_time
        """
        if value_ms is not None:
            self.timings[checkpoint] = value_ms
        else:
            self.timings[checkpoint] = int((time.time() - self.start_time) * 1000)
        self.log(f"timing_{checkpoint}", ms=self.timings[checkpoint])
    
    def track_artifact(self, artifact_type: str, path: str):
        """
        Track artifact file paths.
        
        Args:
            artifact_type: Type of artifact (screenshot, html, trace, etc.)
            path: File path
        """
        if artifact_type in ["screenshot", "html"]:
            self.artifacts[f"{artifact_type}s"].append(path)
        else:
            self.artifacts[artifact_type] = path
        self.log(f"artifact_tracked", type=artifact_type, path=path)
    
    def finalize(self) -> Dict[str, Any]:
        """
        Finalize diagnostic session and save all artifacts.
        
        Returns:
            Summary report dictionary
        """
        self.log("diagnostic_session_end", total_steps=len(self.steps))
        
        # Save steps.jsonl
        steps_path = self.diag_dir / "steps.jsonl"
        with open(steps_path, "w") as f:
            for step in self.steps:
                f.write(json.dumps(step) + "\n")
        
        self.artifacts["steps_log"] = str(steps_path)
        
        # Create summary report with enhanced metrics
        report = {
            "run_id": self.run_id,
            "start_time": self.start_time,
            "end_time": time.time(),
            "duration_seconds": time.time() - self.start_time,
            "total_steps": len(self.steps),
            "blocks_detected": len(self.blocks_detected),
            "block_details": self.blocks_detected,
            "diagnostics": self.diagnostics,
            "timings": self.timings,
            "network": self.net_counters,
            "cookies": self.cookies_info,
            "environment": self.env_info,
            "artifacts": self.artifacts,
            "output_dir": str(self.diag_dir),
        }
        
        # Save report.json
        report_path = self.diag_dir / "report.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        
        # Save report.md
        md_path = self.diag_dir / "report.md"
        with open(md_path, "w") as f:
            f.write(f"# Kroger Diagnostic Report\n\n")
            f.write(f"**Run ID**: {self.run_id}\n")
            f.write(f"**Duration**: {report['duration_seconds']:.2f} seconds\n")
            f.write(f"**Total Steps**: {report['total_steps']}\n")
            f.write(f"**Blocks Detected**: {report['blocks_detected']}\n\n")
            
            # Timings section
            f.write(f"## Timings\n\n")
            for key, value in self.timings.items():
                f.write(f"- **{key}**: {value if value is not None else 'N/A'}\n")
            f.write(f"\n")
            
            # Network forensics section
            f.write(f"## Network Forensics\n\n")
            f.write(f"- **req_failed**: {self.net_counters['req_failed']}\n")
            f.write(f"- **resp_doc**: {self.net_counters['resp_doc']}\n")
            f.write(f"- **route_errors**: {self.net_counters['route_errors']}\n\n")
            
            # Environment section
            if self.env_info.get('ua') or self.env_info.get('webgl'):
                f.write(f"## Environment\n\n")
                if self.env_info.get('ua'):
                    f.write(f"- **User-Agent**: {self.env_info['ua']}\n")
                if self.env_info.get('webgl'):
                    webgl = self.env_info['webgl']
                    f.write(f"- **WebGL Vendor**: {webgl.get('vendor')}\n")
                    f.write(f"- **WebGL Renderer**: {webgl.get('renderer')}\n")
                f.write(f"\n")
            
            # Cookies section
            if self.cookies_info['pre_count'] > 0 or self.cookies_info['post_count'] > 0:
                f.write(f"## Cookies\n\n")
                f.write(f"- **Pre-run**: {self.cookies_info['pre_count']} cookies\n")
                if self.cookies_info['pre_names']:
                    f.write(f"  - Names: {', '.join(self.cookies_info['pre_names'][:8])}\n")
                f.write(f"- **Post-run**: {self.cookies_info['post_count']} cookies\n")
                if self.cookies_info['post_names']:
                    f.write(f"  - Names: {', '.join(self.cookies_info['post_names'][:8])}\n")
                f.write(f"\n")
            
            # Blocks section
            if self.blocks_detected:
                f.write(f"## Blocks Detected\n\n")
                for block in self.blocks_detected:
                    f.write(f"- **{block['reason']}** at {block['url']}\n")
                f.write(f"\n")
            
            # Diagnostics checkpoints section
            f.write(f"## Diagnostics Checkpoints\n\n")
            for checkpoint, diag in self.diagnostics.items():
                f.write(f"### {checkpoint}\n\n")
                if "navigator" in diag:
                    nav = diag["navigator"]
                    f.write(f"**Navigator**:\n")
                    f.write(f"- webdriver: `{nav.get('webdriver')}`\n")
                    f.write(f"- platform: {nav.get('platform')}\n")
                    f.write(f"- hardwareConcurrency: {nav.get('hardwareConcurrency')}\n")
                    f.write(f"- deviceMemory: {nav.get('deviceMemory')}\n\n")
                
                if "webgl" in diag:
                    webgl = diag["webgl"]
                    f.write(f"**WebGL**:\n")
                    f.write(f"- vendor: {webgl.get('vendor')}\n")
                    f.write(f"- unmaskedRenderer: {webgl.get('unmaskedRenderer')}\n\n")
                
                if "cookies" in diag:
                    cookies = diag["cookies"]
                    f.write(f"**Cookies**: {cookies.get('count')} total\n\n")
                    if "akamai_cookies" in diag:
                        f.write(f"**Akamai Cookies**: {', '.join(diag['akamai_cookies'])}\n\n")
            
            # Artifacts section
            if any(self.artifacts.values()):
                f.write(f"## Artifacts\n\n")
                for key, value in self.artifacts.items():
                    if value:
                        if isinstance(value, list):
                            f.write(f"- **{key}**: {len(value)} files\n")
                        else:
                            f.write(f"- **{key}**: `{value}`\n")
                f.write(f"\n")
        
        print(f"\n{'='*60}")
        print(f"Kroger Diagnostics Complete")
        print(f"Run ID: {self.run_id}")
        print(f"Duration: {report['duration_seconds']:.2f}s")
        print(f"Blocks: {report['blocks_detected']}")
        print(f"Output: {self.diag_dir}")
        print(f"{'='*60}\n")
        
        return report
