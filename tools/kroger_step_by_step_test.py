#!/usr/bin/env python3
"""
Kroger Step-by-Step Bot Detection Isolation Test

Similar to Walmart's PerimeterX debugging methodology, this script tests
each action in isolation to pinpoint exactly what triggers Akamai.

Usage:
    .venv/bin/python3 tools/kroger_step_by_step_test.py --step homepage
    .venv/bin/python3 tools/kroger_step_by_step_test.py --step search_box
    .venv/bin/python3 tools/kroger_step_by_step_test.py --step type_search
    .venv/bin/python3 tools/kroger_step_by_step_test.py --step submit
    .venv/bin/python3 tools/kroger_step_by_step_test.py --step all

Each step builds on the previous one, allowing you to isolate the exact trigger.
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from browser_lock import single_browser_lock

# Profile path
USER_DATA_DIR = os.path.expanduser("~/ChromeProfiles/kroger_clean_profile")
OUTPUT_DIR = PROJECT_ROOT / "debug_output" / "kroger_step_tests"

class StepLogger:
    """Logs each step with microsecond precision for forensic analysis"""
    def __init__(self, output_dir):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.steps = []
        self.start_time = time.time()
        
    def log(self, event, **kwargs):
        """Log an event with timestamp and metadata"""
        entry = {
            "ts": time.time(),
            "elapsed_ms": int((time.time() - self.start_time) * 1000),
            "event": event,
            **kwargs
        }
        self.steps.append(entry)
        print(f"[{entry['elapsed_ms']:6d}ms] {event}: {kwargs}")
        
    def save(self, filename="steps.jsonl"):
        """Save steps to JSONL file"""
        path = self.output_dir / filename
        with open(path, "w") as f:
            for step in self.steps:
                f.write(json.dumps(step) + "\n")
        print(f"\n✅ Steps saved to: {path}")


def check_akamai_block(page, logger):
    """
    Check if Akamai has blocked us.
    Returns (is_blocked, reason, details)
    """
    try:
        content = page.content()
        url = page.url
        
        # Akamai Access Denied patterns
        if "<title>Access Denied</title>" in content:
            logger.log("akamai_block_detected", reason="access_denied_title", url=url)
            return True, "access_denied", "Title: Access Denied"
        
        if "errors.edgesuite.net" in content:
            logger.log("akamai_block_detected", reason="edgesuite_error", url=url)
            return True, "edgesuite_error", "Akamai CDN error page"
        
        if "You don't have permission to access" in content:
            logger.log("akamai_block_detected", reason="permission_denied", url=url)
            return True, "permission_denied", "Permission denied message"
        
        if "Reference #" in content and "blocked" in content.lower():
            logger.log("akamai_block_detected", reason="reference_block", url=url)
            return True, "reference_block", "Akamai reference number block"
        
        # Check for suspiciously small page (< 1KB with no real content)
        if len(content) < 1000 and "kroger" not in content.lower():
            logger.log("akamai_block_suspected", reason="small_page", size=len(content), url=url)
            return True, "small_page", f"Page only {len(content)} bytes"
        
        logger.log("no_block_detected", url=url, content_size=len(content))
        return False, "", ""
        
    except Exception as e:
        logger.log("block_check_error", error=str(e))
        return False, "", f"Check error: {e}"


def get_diagnostics(page, context, logger):
    """
    Collect comprehensive diagnostics similar to Walmart's system.
    Returns dict with all diagnostic info.
    """
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
        logger.log("navigator_diag", **nav)
        
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
        logger.log("webgl_diag", **webgl)
        
        # Cookies
        cookies = context.cookies()
        cookie_names = [c["name"] for c in cookies]
        diag["cookies"] = {
            "count": len(cookies),
            "names": cookie_names[:20],  # First 20 cookie names
        }
        logger.log("cookies_diag", count=len(cookies), names=cookie_names[:10])
        
        # Check for suspicious Akamai cookies
        akamai_cookies = [n for n in cookie_names if any(x in n.lower() for x in ["ak_", "bm_", "abck"])]
        if akamai_cookies:
            diag["akamai_cookies"] = akamai_cookies
            logger.log("akamai_cookies_found", cookies=akamai_cookies)
        
        # Viewport
        viewport = page.viewport_size
        diag["viewport"] = viewport
        logger.log("viewport_diag", **viewport)
        
        # URL and title
        diag["url"] = page.url
        diag["title"] = page.title()
        logger.log("page_info", url=page.url, title=page.title())
        
    except Exception as e:
        logger.log("diagnostics_error", error=str(e))
        diag["error"] = str(e)
    
    return diag


def save_forensics(page, output_dir, step_name, logger):
    """Save HTML and screenshot for forensic analysis"""
    try:
        # Screenshot
        screenshot_path = output_dir / f"{step_name}_screenshot.png"
        page.screenshot(path=str(screenshot_path))
        logger.log("screenshot_saved", path=str(screenshot_path))
        
        # HTML
        html_path = output_dir / f"{step_name}_page.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(page.content())
        logger.log("html_saved", path=str(html_path), size=len(page.content()))
        
        return True
    except Exception as e:
        logger.log("forensics_save_error", error=str(e))
        return False


def human_type_with_logging(element, text: str, logger):
    """Type with human-like delays and log each keystroke (Walmart methodology)."""
    for i, ch in enumerate(text):
        delay_ms = random.uniform(80, 220)
        logger.log("keystroke", char=ch, index=i, delay_ms=int(delay_ms))
        element.type(ch, delay=delay_ms)
        
        # Random micro-pause (10% chance)
        if random.random() < 0.10:
            pause_ms = random.uniform(50, 150)
            logger.log("keystroke_pause", index=i, pause_ms=int(pause_ms))
            time.sleep(pause_ms / 1000)
    
    # Longer pause for longer text (60% chance)
    if len(text) >= 10 and random.random() < 0.6:
        final_pause_ms = random.uniform(200, 450)
        logger.log("typing_complete_pause", pause_ms=int(final_pause_ms))
        time.sleep(final_pause_ms / 1000)


def run_step_test(step_name, headless=False):
    """
    Run a specific step test.
    
    Steps:
    - homepage: Just load kroger.com homepage
    - search_box: Load homepage + click search box
    - type_search: Load homepage + click search box + type keyword
    - submit: Full flow including search submission
    - all: Run all steps sequentially
    """
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = OUTPUT_DIR / f"{step_name}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    
    logger = StepLogger(run_dir)
    logger.log("test_start", step=step_name, headless=headless, profile=USER_DATA_DIR)
    
    report = {
        "step": step_name,
        "timestamp": timestamp,
        "profile": USER_DATA_DIR,
        "outcome": "unknown",
        "blocked": False,
        "block_reason": "",
        "diagnostics": {},
        "timings": {},
    }
    
    with single_browser_lock(timeout=600):
        with sync_playwright() as p:
            try:
                # Launch Chrome with minimal args (post-Chrome 145 compatible)
                args = [
                    # NOTE: --no-sandbox REMOVED - conflicts with chromium_sandbox=True and triggers Akamai
                    '--disable-dev-shm-usage',
                    '--disable-infobars',
                    '--no-first-run',
                    '--disable-default-apps',
                    '--disable-backgrounding-occluded-windows',
                    '--window-size=1280,720',
                    '--disable-notifications',
                    '--disable-quic',
                    '--noerrdialogs',
                    # GPU acceleration args (CRITICAL: Prevents SwiftShader software rendering)
                    '--use-angle=metal',  # Force ANGLE→Metal backend on macOS
                    '--enable-gpu-rasterization',  # Prefer GPU raster
                    '--ignore-gpu-blocklist',  # Don't let Chrome silently disable GPU
                ]
                
                logger.log("browser_launch", args=args)
                start_launch = time.time()
                
                context = p.chromium.launch_persistent_context(
                    user_data_dir=USER_DATA_DIR,
                    headless=False,  # Always headed for Kroger
                    channel='chrome',  # Use real Chrome for correct fingerprint
                    args=args,
                    ignore_default_args=['--enable-automation'],  # CRITICAL: Prevents navigator.webdriver=true
                    chromium_sandbox=True,  # CRITICAL: Enables sandbox (no --no-sandbox banner)
                )
                
                # CRITICAL: Force navigator.webdriver to undefined (ignore_default_args doesn't always work with persistent context)
                context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """)
                
                report["timings"]["launch_ms"] = int((time.time() - start_launch) * 1000)
                logger.log("browser_launched", elapsed_ms=report["timings"]["launch_ms"])
                
                page = context.pages[0] if context.pages else context.new_page()
                
                # Get initial diagnostics
                logger.log("collecting_initial_diagnostics")
                report["diagnostics"]["initial"] = get_diagnostics(page, context, logger)
                
                # STEP 1: Homepage (all tests start here)
                logger.log("step_1_homepage_start")
                start_homepage = time.time()
                
                page.goto("https://www.kroger.com/", wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(3000)
                
                report["timings"]["homepage_ms"] = int((time.time() - start_homepage) * 1000)
                logger.log("step_1_homepage_complete", elapsed_ms=report["timings"]["homepage_ms"])
                
                # Check navigator.webdriver on the actual Kroger page (after init script should be applied)
                try:
                    webdriver_on_page = page.evaluate("() => navigator.webdriver")
                    logger.log("kroger_page_webdriver_check", webdriver=webdriver_on_page, url=page.url)
                except Exception as e:
                    logger.log("webdriver_check_error", error=str(e))
                
                # Check for block after homepage
                is_blocked, reason, details = check_akamai_block(page, logger)
                if is_blocked:
                    report["blocked"] = True
                    report["block_reason"] = reason
                    report["block_details"] = details
                    report["outcome"] = "blocked_at_homepage"
                    logger.log("test_failed", reason="blocked_at_homepage", details=details)
                    save_forensics(page, run_dir, "blocked_homepage", logger)
                    return report
                
                save_forensics(page, run_dir, "step1_homepage", logger)
                
                if step_name == "homepage":
                    report["outcome"] = "success"
                    logger.log("test_complete", step="homepage", result="no_block")
                    return report
                
                # STEP 2: Click search box
                if step_name in ["search_box", "type_search", "submit", "all"]:
                    logger.log("step_2_search_box_start")
                    start_search_box = time.time()
                    
                    try:
                        # Try multiple search box selectors
                        search_selectors = [
                            'input[placeholder*="Search"]',
                            'input[type="search"]',
                            'input[aria-label*="Search"]',
                            '#SearchBar-input',
                        ]
                        
                        search_box = None
                        for selector in search_selectors:
                            try:
                                if page.locator(selector).count() > 0:
                                    search_box = page.locator(selector).first
                                    logger.log("search_box_found", selector=selector)
                                    break
                            except:
                                continue
                        
                        if not search_box:
                            logger.log("search_box_not_found", tried=search_selectors)
                            report["outcome"] = "error_no_search_box"
                            return report
                        
                        search_box.click()
                        page.wait_for_timeout(500)
                        
                        report["timings"]["search_box_click_ms"] = int((time.time() - start_search_box) * 1000)
                        logger.log("step_2_search_box_complete", elapsed_ms=report["timings"]["search_box_click_ms"])
                        
                        # Check for block after clicking search box
                        is_blocked, reason, details = check_akamai_block(page, logger)
                        if is_blocked:
                            report["blocked"] = True
                            report["block_reason"] = reason
                            report["block_details"] = details
                            report["outcome"] = "blocked_at_search_box_click"
                            logger.log("test_failed", reason="blocked_at_search_box_click", details=details)
                            save_forensics(page, run_dir, "blocked_search_box", logger)
                            return report
                        
                        save_forensics(page, run_dir, "step2_search_box", logger)
                        
                        if step_name == "search_box":
                            report["outcome"] = "success"
                            logger.log("test_complete", step="search_box", result="no_block")
                            return report
                        
                    except Exception as e:
                        logger.log("search_box_error", error=str(e))
                        report["outcome"] = f"error_search_box: {e}"
                        return report
                
                # STEP 3: Type search keyword
                if step_name in ["type_search", "submit", "all"]:
                    logger.log("step_3_type_search_start")
                    start_typing = time.time()
                    
                    try:
                        keyword = "black forest ham"
                        logger.log("typing_keyword_start", keyword=keyword, length=len(keyword))
                        
                        # Type with per-keystroke logging (Walmart methodology)
                        human_type_with_logging(search_box, keyword, logger)
                        
                        page.wait_for_timeout(1000)
                        
                        report["timings"]["typing_ms"] = int((time.time() - start_typing) * 1000)
                        logger.log("step_3_type_search_complete", elapsed_ms=report["timings"]["typing_ms"])
                        
                        # Check for block after typing
                        is_blocked, reason, details = check_akamai_block(page, logger)
                        if is_blocked:
                            report["blocked"] = True
                            report["block_reason"] = reason
                            report["block_details"] = details
                            report["outcome"] = "blocked_at_typing"
                            logger.log("test_failed", reason="blocked_at_typing", details=details)
                            save_forensics(page, run_dir, "blocked_typing", logger)
                            return report
                        
                        save_forensics(page, run_dir, "step3_typing", logger)
                        
                        if step_name == "type_search":
                            report["outcome"] = "success"
                            logger.log("test_complete", step="type_search", result="no_block")
                            return report
                        
                    except Exception as e:
                        logger.log("typing_error", error=str(e))
                        report["outcome"] = f"error_typing: {e}"
                        return report
                
                # STEP 4: Submit search
                if step_name in ["submit", "all"]:
                    logger.log("step_4_submit_start")
                    start_submit = time.time()
                    
                    try:
                        # Press Enter to submit
                        page.keyboard.press("Enter")
                        logger.log("enter_pressed")
                        
                        # Wait for navigation
                        page.wait_for_load_state("domcontentloaded", timeout=30000)
                        page.wait_for_timeout(3000)
                        
                        report["timings"]["submit_ms"] = int((time.time() - start_submit) * 1000)
                        logger.log("step_4_submit_complete", elapsed_ms=report["timings"]["submit_ms"])
                        
                        # Check for block after submission
                        is_blocked, reason, details = check_akamai_block(page, logger)
                        if is_blocked:
                            report["blocked"] = True
                            report["block_reason"] = reason
                            report["block_details"] = details
                            report["outcome"] = "blocked_at_submit"
                            logger.log("test_failed", reason="blocked_at_submit", details=details)
                            save_forensics(page, run_dir, "blocked_submit", logger)
                            return report
                        
                        save_forensics(page, run_dir, "step4_submit", logger)
                        
                        # Get final diagnostics
                        logger.log("collecting_final_diagnostics")
                        report["diagnostics"]["final"] = get_diagnostics(page, context, logger)
                        
                        report["outcome"] = "success"
                        logger.log("test_complete", step="submit", result="no_block")
                        return report
                        
                    except Exception as e:
                        logger.log("submit_error", error=str(e))
                        report["outcome"] = f"error_submit: {e}"
                        return report
                
            except Exception as e:
                logger.log("test_error", error=str(e))
                report["outcome"] = f"error: {e}"
                return report
            
            finally:
                try:
                    context.close()
                except:
                    pass
                
                # Save logger steps
                logger.save()
                
                # Save report
                report_path = run_dir / "report.json"
                with open(report_path, "w") as f:
                    json.dump(report, f, indent=2)
                
                # Save markdown report
                md_path = run_dir / "report.md"
                with open(md_path, "w") as f:
                    f.write(f"# Kroger Step Test: {step_name}\n\n")
                    f.write(f"**Timestamp**: {timestamp}\n")
                    f.write(f"**Outcome**: {report['outcome']}\n")
                    f.write(f"**Blocked**: {report['blocked']}\n")
                    if report['blocked']:
                        f.write(f"**Block Reason**: {report['block_reason']}\n")
                        f.write(f"**Block Details**: {report.get('block_details', 'N/A')}\n")
                    f.write(f"\n## Timings\n\n")
                    for k, v in report.get("timings", {}).items():
                        f.write(f"- {k}: {v}ms\n")
                    f.write(f"\n## Diagnostics\n\n")
                    if "initial" in report.get("diagnostics", {}):
                        nav = report["diagnostics"]["initial"].get("navigator", {})
                        f.write(f"### Navigator\n")
                        f.write(f"- webdriver: {nav.get('webdriver')}\n")
                        f.write(f"- userAgent: {nav.get('userAgent', 'N/A')[:80]}...\n")
                        f.write(f"- platform: {nav.get('platform')}\n")
                        f.write(f"- hardwareConcurrency: {nav.get('hardwareConcurrency')}\n")
                        f.write(f"- deviceMemory: {nav.get('deviceMemory')}\n")
                        f.write(f"- pluginsLength: {nav.get('pluginsLength')}\n")
                        f.write(f"\n### WebGL\n")
                        webgl = report["diagnostics"]["initial"].get("webgl", {})
                        f.write(f"- vendor: {webgl.get('vendor')}\n")
                        f.write(f"- renderer: {webgl.get('renderer')}\n")
                        f.write(f"- unmaskedVendor: {webgl.get('unmaskedVendor')}\n")
                        f.write(f"- unmaskedRenderer: {webgl.get('unmaskedRenderer')}\n")
                        f.write(f"\n### Cookies\n")
                        cookies = report["diagnostics"]["initial"].get("cookies", {})
                        f.write(f"- count: {cookies.get('count')}\n")
                        f.write(f"- names: {', '.join(cookies.get('names', [])[:10])}\n")
                        if "akamai_cookies" in report["diagnostics"]["initial"]:
                            f.write(f"- akamai_cookies: {', '.join(report['diagnostics']['initial']['akamai_cookies'])}\n")
                
                print(f"\n{'='*60}")
                print(f"Test Complete: {step_name}")
                print(f"Outcome: {report['outcome']}")
                print(f"Blocked: {report['blocked']}")
                if report['blocked']:
                    print(f"Block Reason: {report['block_reason']}")
                print(f"\nResults saved to: {run_dir}")
                print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Kroger Step-by-Step Bot Detection Isolation Test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Steps:
  homepage    - Just load kroger.com homepage
  search_box  - Load homepage + click search box
  type_search - Load homepage + click search box + type keyword
  submit      - Full flow including search submission
  all         - Run all steps sequentially

Examples:
  .venv/bin/python3 tools/kroger_step_by_step_test.py --step homepage
  .venv/bin/python3 tools/kroger_step_by_step_test.py --step submit
        """
    )
    
    parser.add_argument(
        "--step",
        required=True,
        choices=["homepage", "search_box", "type_search", "submit", "all"],
        help="Which step to test"
    )
    
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run in headless mode (not recommended for Kroger)"
    )
    
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="Custom profile directory (default: ~/ChromeProfiles/kroger_clean_profile)"
    )
    
    args = parser.parse_args()
    
    # Override USER_DATA_DIR if custom profile specified
    global USER_DATA_DIR
    if args.profile:
        USER_DATA_DIR = os.path.expanduser(args.profile)
    
    print(f"\n{'='*60}")
    print(f"Kroger Step-by-Step Bot Detection Test")
    print(f"Step: {args.step}")
    print(f"Profile: {USER_DATA_DIR}")
    print(f"Output: {OUTPUT_DIR}")
    print(f"{'='*60}\n")
    
    if args.step == "all":
        for step in ["homepage", "search_box", "type_search", "submit"]:
            print(f"\n>>> Running step: {step}\n")
            report = run_step_test(step, headless=args.headless)
            if report["blocked"]:
                print(f"\n⚠️  BLOCKED at step '{step}' - stopping here")
                print(f"Block reason: {report['block_reason']}")
                break
            time.sleep(5)  # Wait between steps
    else:
        run_step_test(args.step, headless=args.headless)


if __name__ == "__main__":
    main()
