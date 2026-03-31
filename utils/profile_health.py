"""
Profile Health Monitor
======================
Centralized detection of blocked / stale browser profiles across all retailers.

Usage from any scraper:

    from utils.profile_health import check_page_blocked, record_outcome, should_bail, send_relogin_alert

    blocked, reason = check_page_blocked(html_content, retailer="kroger")
    record_outcome(retailer, keyword, blocked=blocked, reason=reason)
    if should_bail(retailer):
        send_relogin_alert(retailer)
        return False  # stop scraping

The health ledger is persisted to config/profile_health.json so the scheduler
and GUI can both read it.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
HEALTH_FILE = _PROJECT_ROOT / "config" / "profile_health.json"

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
CONSECUTIVE_FAIL_THRESHOLD = 3   # after N consecutive blocks → alert
ALERT_COOLDOWN_SEC = 3600        # don't re-alert within 1 hour

# ---------------------------------------------------------------------------
# Block-detection patterns per retailer
# ---------------------------------------------------------------------------
_BLOCK_PATTERNS: dict[str, list[dict]] = {
    # Each entry: {"pattern": <regex or literal>, "reason": str, "fixed": bool}
    "kroger": [
        {"pattern": "<title>Access Denied</title>", "reason": "akamai_access_denied", "fixed": True},
        {"pattern": "errors.edgesuite.net", "reason": "akamai_access_denied", "fixed": True},
        {"pattern": "You don't have permission to access", "reason": "akamai_access_denied", "fixed": True},
    ],
    "walmart": [
        {"pattern": "Robot or human?", "reason": "perimeterx_captcha", "fixed": True},
        {"pattern": "px-captcha", "reason": "perimeterx_captcha", "fixed": True},
        {"pattern": "<title>Access Denied</title>", "reason": "access_denied", "fixed": True},
        {"pattern": "walmart.com/blocked", "reason": "blocked_redirect", "fixed": True},
    ],
    "target": [
        {"pattern": "<title>Access Denied</title>", "reason": "access_denied", "fixed": True},
        {"pattern": "errors.edgesuite.net", "reason": "akamai_access_denied", "fixed": True},
    ],
    "instacart": [
        {"pattern": "verify you are human", "reason": "captcha", "fixed": True},
        {"pattern": "unusual activity", "reason": "unusual_activity", "fixed": True},
    ],
    "amazon": [
        {"pattern": "enter the characters you see below", "reason": "captcha", "fixed": True},
        {"pattern": "automated access", "reason": "bot_detection", "fixed": True},
    ],
    "tiktokshop": [
        {"pattern": "verify you are human", "reason": "captcha", "fixed": True},
        {"pattern": "access denied", "reason": "access_denied", "fixed": True},
    ],
}

# Universal patterns (apply to all retailers)
_UNIVERSAL_PATTERNS = [
    {"pattern": "<title>Access Denied</title>", "reason": "access_denied", "fixed": True},
    {"pattern": "too many requests", "reason": "rate_limit", "fixed": True},
]


def check_page_blocked(html: str, retailer: str = "") -> Tuple[bool, str]:
    """Check if HTML content indicates a blocked / stale session.

    Returns (is_blocked, reason).
    """
    if not html or len(html.strip()) == 0:
        return True, "empty_response"

    html_lower = html.lower()

    # Suspiciously small page (< 1KB) with no product-like content
    if len(html) < 1000:
        # Quick heuristic: if it has <title>Access Denied or similar, it's blocked
        if "access denied" in html_lower or "blocked" in html_lower:
            return True, "access_denied_small_page"

    # Retailer-specific patterns
    patterns = _BLOCK_PATTERNS.get(retailer.lower(), []) + _UNIVERSAL_PATTERNS
    for entry in patterns:
        needle = entry["pattern"]
        if entry.get("fixed"):
            if needle.lower() in html_lower:
                return True, entry["reason"]
        else:
            if re.search(needle, html, re.IGNORECASE):
                return True, entry["reason"]

    return False, ""


# ---------------------------------------------------------------------------
# Health Ledger (persistent JSON)
# ---------------------------------------------------------------------------

def _load_ledger() -> dict:
    """Load the health ledger from disk."""
    try:
        if HEALTH_FILE.exists():
            return json.loads(HEALTH_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_ledger(ledger: dict) -> None:
    """Save the health ledger to disk."""
    HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    HEALTH_FILE.write_text(json.dumps(ledger, indent=2, default=str), encoding="utf-8")


def record_outcome(
    retailer: str,
    keyword: str,
    *,
    blocked: bool,
    reason: str = "",
) -> dict:
    """Record a scrape outcome and return the updated retailer entry."""
    ledger = _load_ledger()
    key = retailer.lower()
    entry = ledger.setdefault(key, {
        "consecutive_failures": 0,
        "total_failures": 0,
        "total_successes": 0,
        "last_success": None,
        "last_failure": None,
        "last_failure_reason": None,
        "last_alert_sent": None,
        "status": "healthy",
    })

    now = datetime.now(timezone.utc).isoformat()

    if blocked:
        entry["consecutive_failures"] += 1
        entry["total_failures"] += 1
        entry["last_failure"] = now
        entry["last_failure_reason"] = reason
        entry["last_failure_keyword"] = keyword
        if entry["consecutive_failures"] >= CONSECUTIVE_FAIL_THRESHOLD:
            entry["status"] = "blocked"
        else:
            entry["status"] = "degraded"
    else:
        entry["consecutive_failures"] = 0
        entry["total_successes"] += 1
        entry["last_success"] = now
        entry["status"] = "healthy"

    ledger[key] = entry
    _save_ledger(ledger)
    return entry


def should_bail(retailer: str) -> bool:
    """Return True if the retailer has exceeded the failure threshold."""
    ledger = _load_ledger()
    entry = ledger.get(retailer.lower(), {})
    return entry.get("consecutive_failures", 0) >= CONSECUTIVE_FAIL_THRESHOLD


def get_status(retailer: str) -> dict:
    """Get the current health status for a retailer."""
    ledger = _load_ledger()
    return ledger.get(retailer.lower(), {
        "consecutive_failures": 0,
        "status": "healthy",
    })


def get_all_statuses() -> dict:
    """Get health status for all retailers."""
    return _load_ledger()


def reset_retailer(retailer: str) -> None:
    """Reset a retailer's health status (e.g. after manual re-login)."""
    ledger = _load_ledger()
    key = retailer.lower()
    if key in ledger:
        ledger[key]["consecutive_failures"] = 0
        ledger[key]["status"] = "healthy"
        ledger[key]["last_alert_sent"] = None
        _save_ledger(ledger)


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

def _macos_notification(title: str, message: str) -> None:
    """Send a macOS notification via osascript."""
    try:
        script = f'display notification "{message}" with title "{title}" sound name "Glass"'
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass


def _send_email_alert(retailer: str, reason: str, consecutive: int) -> None:
    """Send an email alert using the config/notify.json SMTP settings."""
    try:
        notify_cfg_path = _PROJECT_ROOT / "config" / "notify.json"
        if not notify_cfg_path.exists():
            return
        cfg = json.loads(notify_cfg_path.read_text(encoding="utf-8"))
        email_cfg = cfg.get("email", {})
        if not email_cfg.get("enabled"):
            return

        import smtplib
        from email.mime.text import MIMEText

        reason_label = "not logged in" if "not_logged_in" in reason else "blocked"
        subject = f"{email_cfg.get('subject_prefix', '[RMN]')} {retailer.title()} profile {reason_label} — manual re-login needed"
        body = (
            f"The {retailer.title()} scraper profile is {reason_label}.\n\n"
            f"Reason: {reason}\n"
            f"Consecutive failures: {consecutive}\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"Action needed: Open the {retailer.title()} profile in a real Chrome window,\n"
            f"browse the site normally for a few minutes, and log in if needed.\n\n"
            f"The scheduler will automatically resume once the profile is healthy again."
        )

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = email_cfg["from_addr"]
        msg["To"] = ", ".join(email_cfg["to_addrs"])

        with smtplib.SMTP(email_cfg["smtp_host"], email_cfg["smtp_port"]) as server:
            server.starttls()
            server.login(email_cfg["smtp_user"], email_cfg["smtp_password"])
            server.send_message(msg)

        print(f"📧 Sent profile-blocked email alert for {retailer}")
    except Exception as e:
        print(f"⚠️ Failed to send email alert: {e}")


def send_relogin_alert(retailer: str, reason: str = "blocked") -> bool:
    """Send alert (macOS notification + email) if cooldown has elapsed.

    Returns True if an alert was actually sent.
    """
    ledger = _load_ledger()
    entry = ledger.get(retailer.lower(), {})
    consecutive = entry.get("consecutive_failures", 0)

    # Check cooldown
    last_alert = entry.get("last_alert_sent")
    if last_alert:
        try:
            last_ts = datetime.fromisoformat(last_alert).timestamp()
            if time.time() - last_ts < ALERT_COOLDOWN_SEC:
                return False  # still in cooldown
        except Exception:
            pass

    # macOS desktop notification
    _macos_notification(
        f"⚠️ {retailer.title()} Profile Blocked",
        f"{consecutive} consecutive failures ({reason}). Manual re-login needed.",
    )

    # Email alert
    _send_email_alert(retailer, reason, consecutive)

    # Update cooldown timestamp
    entry["last_alert_sent"] = datetime.now(timezone.utc).isoformat()
    ledger[retailer.lower()] = entry
    _save_ledger(ledger)

    return True


# ---------------------------------------------------------------------------
# Convenience: one-call check for scrapers
# ---------------------------------------------------------------------------

def record_login_outcome(
    retailer: str,
    keyword: str,
    *,
    logged_in: bool,
    alert: bool = True,
) -> Tuple[bool, str]:
    """Record whether the scraper found a logged-in session.

    If *not* logged in, this counts as a failure with reason ``not_logged_in``.
    Returns (is_problem, reason) — True when the session is stale.
    """
    if logged_in:
        # Don't reset the counter here — a successful login is recorded
        # via check_and_record when the actual page content is verified.
        return False, ""

    reason = "not_logged_in"
    record_outcome(retailer, keyword, blocked=True, reason=reason)

    if alert and should_bail(retailer):
        send_relogin_alert(retailer, reason)

    return True, reason


def prompt_relogin(
    page,
    retailer: str,
    keyword: str,
    *,
    timeout_sec: int = 300,
    log_fn=None,
) -> bool:
    """Show an interactive dialog asking the user to log in via the open browser.

    Brings the Playwright *page* to the foreground and opens a tkinter
    message-box.  If the user clicks **Yes**, the function waits up to
    *timeout_sec* seconds for the user to complete login in that same
    browser window, then returns ``True``.  If they click **No** (or
    the dialog cannot be shown — e.g. headless / scheduler mode) the
    failure is recorded and the function returns ``False``.

    Returns ``True``  → caller should **continue** the scrape.
    Returns ``False`` → caller should **skip or bail**.
    """
    _log = log_fn or (lambda msg: print(msg))

    # Bring existing browser window to the front so user can interact
    try:
        page.bring_to_front()
    except Exception:
        pass

    # Show tkinter Yes/No dialog (non-blocking-safe: works even if a
    # Tk root already exists from keyword_input.py)
    user_said_yes = False
    try:
        import tkinter as tk
        from tkinter import messagebox

        # Reuse existing Tk root if one is alive, else create a hidden one
        try:
            _root = tk._default_root  # type: ignore[attr-defined]
            if _root is None or not _root.winfo_exists():
                raise RuntimeError("no root")
            own_root = False
        except Exception:
            _root = tk.Tk()
            _root.withdraw()
            own_root = True

        user_said_yes = messagebox.askyesno(
            f"{retailer.title()} — Not Logged In",
            f"The {retailer.title()} scraper detected that the browser is not "
            f"logged in.\n\n"
            f"Would you like to log in now?\n\n"
            f"Click Yes → log in in the browser window that just came to the "
            f"front, then come back here and the scrape will resume.\n\n"
            f"Click No → skip this keyword and record the failure.",
        )

        if own_root:
            _root.destroy()
    except Exception as e:
        _log(f"   ℹ️ Could not show login prompt ({e}) — recording failure")
        record_login_outcome(retailer, keyword, logged_in=False)
        return False

    if not user_said_yes:
        _log(f"   ℹ️ User declined re-login for {retailer.title()}")
        record_login_outcome(retailer, keyword, logged_in=False)
        return False

    # User clicked Yes — wait for them to complete login
    _log(f"   ⏳ Waiting up to {timeout_sec}s for {retailer.title()} login…")

    try:
        page.bring_to_front()
    except Exception:
        pass

    deadline = time.time() + timeout_sec
    last_report = 0.0
    while time.time() < deadline:
        remaining = int(deadline - time.time())
        now = time.time()
        if now - last_report >= 15:
            _log(f"   ⏳ Waiting for login… ({remaining}s remaining)")
            last_report = now
        # Use time.sleep instead of page.wait_for_timeout to avoid blocking
        # the Tkinter event loop when running from GUI
        time.sleep(2)

    # After timeout, show a final "Done?" confirmation
    try:
        import tkinter as tk
        from tkinter import messagebox

        try:
            _root = tk._default_root  # type: ignore[attr-defined]
            if _root is None or not _root.winfo_exists():
                raise RuntimeError("no root")
            own_root = False
        except Exception:
            _root = tk.Tk()
            _root.withdraw()
            own_root = True

        done = messagebox.askyesno(
            f"{retailer.title()} — Login Complete?",
            f"Have you finished logging in to {retailer.title()}?\n\n"
            f"Click Yes to continue the scrape.\n"
            f"Click No to abort this keyword.",
        )

        if own_root:
            _root.destroy()

        if done:
            _log(f"   ✅ User confirmed login — resuming scrape")
            return True
        else:
            _log(f"   ❌ User said login not complete — recording failure")
            record_login_outcome(retailer, keyword, logged_in=False)
            return False
    except Exception:
        # Can't show dialog; assume they logged in since they clicked Yes earlier
        _log(f"   ✅ Login wait complete — resuming scrape")
        return True


async def prompt_relogin_async(
    page,
    retailer: str,
    keyword: str,
    *,
    timeout_sec: int = 300,
    log_fn=None,
) -> bool:
    """Async version of :func:`prompt_relogin` for async scrapers (TikTok Shop).

    Same interface and return semantics.
    """
    import asyncio

    _log = log_fn or (lambda msg: print(msg))

    try:
        await page.bring_to_front()
    except Exception:
        pass

    # Show tkinter dialog (tkinter is sync — run in executor)
    user_said_yes = False
    try:
        loop = asyncio.get_event_loop()
        user_said_yes = await loop.run_in_executor(None, _sync_ask_relogin, retailer)
    except Exception as e:
        _log(f"   ℹ️ Could not show login prompt ({e}) — recording failure")
        record_login_outcome(retailer, keyword, logged_in=False)
        return False

    if not user_said_yes:
        _log(f"   ℹ️ User declined re-login for {retailer.title()}")
        record_login_outcome(retailer, keyword, logged_in=False)
        return False

    _log(f"   ⏳ Waiting up to {timeout_sec}s for {retailer.title()} login…")
    try:
        await page.bring_to_front()
    except Exception:
        pass

    deadline = time.time() + timeout_sec
    last_report = 0.0
    while time.time() < deadline:
        remaining = int(deadline - time.time())
        now = time.time()
        if now - last_report >= 15:
            _log(f"   ⏳ Waiting for login… ({remaining}s remaining)")
            last_report = now
        await asyncio.sleep(2)

    # Final confirmation
    try:
        loop = asyncio.get_event_loop()
        done = await loop.run_in_executor(None, _sync_ask_login_done, retailer)
        if done:
            _log(f"   ✅ User confirmed login — resuming scrape")
            return True
        else:
            _log(f"   ❌ User said login not complete — recording failure")
            record_login_outcome(retailer, keyword, logged_in=False)
            return False
    except Exception:
        _log(f"   ✅ Login wait complete — resuming scrape")
        return True


def _sync_ask_relogin(retailer: str) -> bool:
    """Tkinter messagebox helper — called from executor for async path."""
    import tkinter as tk
    from tkinter import messagebox

    try:
        _root = tk._default_root  # type: ignore[attr-defined]
        if _root is None or not _root.winfo_exists():
            raise RuntimeError("no root")
        own_root = False
    except Exception:
        _root = tk.Tk()
        _root.withdraw()
        own_root = True

    result = messagebox.askyesno(
        f"{retailer.title()} — Not Logged In",
        f"The {retailer.title()} scraper detected that the browser is not "
        f"logged in.\n\n"
        f"Would you like to log in now?\n\n"
        f"Click Yes → log in in the browser window, then wait for the "
        f"confirmation dialog.\n\n"
        f"Click No → skip this keyword and record the failure.",
    )

    if own_root:
        _root.destroy()
    return result


def _sync_ask_login_done(retailer: str) -> bool:
    """Tkinter messagebox helper — called from executor for async path."""
    import tkinter as tk
    from tkinter import messagebox

    try:
        _root = tk._default_root  # type: ignore[attr-defined]
        if _root is None or not _root.winfo_exists():
            raise RuntimeError("no root")
        own_root = False
    except Exception:
        _root = tk.Tk()
        _root.withdraw()
        own_root = True

    result = messagebox.askyesno(
        f"{retailer.title()} — Login Complete?",
        f"Have you finished logging in to {retailer.title()}?\n\n"
        f"Click Yes to continue the scrape.\n"
        f"Click No to abort this keyword.",
    )

    if own_root:
        _root.destroy()
    return result


def check_and_record(
    html: str,
    retailer: str,
    keyword: str,
    *,
    alert: bool = True,
) -> Tuple[bool, str]:
    """All-in-one: check page, record outcome, alert if needed.

    Returns (is_blocked, reason).
    Use this from scrapers right after saving HTML.
    """
    blocked, reason = check_page_blocked(html, retailer)
    record_outcome(retailer, keyword, blocked=blocked, reason=reason)

    if blocked and alert and should_bail(retailer):
        send_relogin_alert(retailer, reason)

    return blocked, reason
