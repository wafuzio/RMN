#!/usr/bin/env python3
"""
Profile Doctor — inspects and repairs browser profiles for all retailers.

Usage:
    python3 tools/profile_doctor.py                  # check all profiles
    python3 tools/profile_doctor.py --fix-corrupted  # remove corrupted backups
    python3 tools/profile_doctor.py --retailer kroger  # single retailer
    python3 tools/profile_doctor.py --login kroger   # open browser to re-login

Checks:
  - Profile directory exists
  - Corrupted/poisoned backup dirs present
  - Default/Cookies file exists and age
  - Default/Login Data file exists
  - Profile lock files (SingletonLock) that indicate browser crash
  - Basic profile file count sanity check
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SCRAPER_HOME = Path(os.environ.get("SCRAPER_HOME", str(ROOT)))

# ---------------------------------------------------------------------------
# Profile configuration
# ---------------------------------------------------------------------------

# ChromeProfiles base (where scrapers look by default)
_CHROME_PROFILES = Path.home() / "ChromeProfiles"

RETAILER_CONFIGS = {
    "amazon": {
        # amazon_search_and_capture.py: AMAZON_PROFILE_DIR env var OR ~/ChromeProfiles/amazon
        "env_vars": ["AMAZON_PROFILE_DIR", "AMZ_PROFILE_DIR"],
        "fallback": _CHROME_PROFILES / "amazon",
        "login_url": "https://www.amazon.com/ap/signin",
        "scraper_script": "amazon_search_and_capture.py",
        "requires_login": True,
    },
    "instacart": {
        # instacart_search_and_capture.py: INSTACART_PROFILE_DIR env var (required)
        "env_vars": ["INSTACART_PROFILE_DIR"],
        "fallback": _CHROME_PROFILES / "instacart",
        "login_url": "https://www.instacart.com/login",
        "scraper_script": "instacart_search_and_capture.py",
        "requires_login": True,
    },
    "kroger": {
        # kroger_search_and_capture.py: hardcoded to ~/ChromeProfiles/kroger_clean_profile
        # KROGER_PROFILE_DIR env var is NOT used by the scraper itself
        "env_vars": [],  # scraper doesn't read env var
        "fallback": _CHROME_PROFILES / "kroger_clean_profile",
        "login_url": "https://www.kroger.com/signin",
        "scraper_script": "kroger_search_and_capture.py",
        "requires_login": True,
    },
    "walmart": {
        # walmart_search_and_capture.py: WALMART_PROFILE_DIR env var (required)
        "env_vars": ["WALMART_PROFILE_DIR"],
        "fallback": _CHROME_PROFILES / "walmart",
        "login_url": "https://www.walmart.com/account/login",
        "scraper_script": "walmart_search_and_capture.py",
        "requires_login": False,  # Walmart uses PerimeterX bypass, not account login
    },
    "target": {
        # target_search_and_capture.py: TARGET_PROFILE_DIR env var OR profiles/target
        "env_vars": ["TARGET_PROFILE_DIR"],
        "fallback": ROOT / "profiles" / "target",
        "login_url": "https://www.target.com/account",
        "scraper_script": "target_search_and_capture.py",
        "requires_login": False,
    },
}

POISONED_MARKERS = ["corrupted", ".corrupted", "captcha", "blocked", "poisoned", "broken"]

# Singleton lock = Chrome crashed without cleanup
SINGLETON_LOCK_PATH = "SingletonLock"
COOKIE_STALE_DAYS = 60
COOKIE_WARN_DAYS = 30


# ---------------------------------------------------------------------------
# Core inspection
# ---------------------------------------------------------------------------

def resolve_profile_dir(retailer: str) -> Path:
    cfg = RETAILER_CONFIGS[retailer]
    for ev in cfg["env_vars"]:
        v = os.environ.get(ev)
        if v:
            return Path(v)
    return cfg["fallback"]


def inspect_profile(retailer: str) -> Dict:
    cfg = RETAILER_CONFIGS[retailer]
    profile_dir = resolve_profile_dir(retailer)

    result = {
        "retailer": retailer,
        "profile_dir": str(profile_dir),
        "exists": profile_dir.exists(),
        "cookies_exist": False,
        "cookies_age_days": None,
        "cookies_status": "UNKNOWN",
        "login_data_exists": False,
        "singleton_lock": False,
        "corrupted_backups": [],
        "issues": [],
        "overall": "UNKNOWN",
    }

    if not profile_dir.exists():
        result["overall"] = "MISSING"
        result["issues"].append(f"Profile directory missing: {profile_dir}")
        return result

    # Check for poisoned backups in the parent directory
    parent = profile_dir.parent
    if parent.exists():
        for d in parent.iterdir():
            if d.is_dir() and d != profile_dir:
                if any(m in d.name.lower() for m in POISONED_MARKERS):
                    result["corrupted_backups"].append(str(d))
                    result["issues"].append(f"Corrupted backup found: {d.name}")

    # Check for Singleton lock (indicates crashed browser)
    singleton = profile_dir / SINGLETON_LOCK_PATH
    if singleton.exists():
        result["singleton_lock"] = True
        result["issues"].append("SingletonLock exists — previous browser session may have crashed")

    # Check Default/Cookies
    cookies = profile_dir / "Default" / "Cookies"
    if cookies.exists():
        result["cookies_exist"] = True
        age_days = (time.time() - cookies.stat().st_mtime) / 86400
        result["cookies_age_days"] = round(age_days, 1)

        if age_days > COOKIE_STALE_DAYS:
            result["cookies_status"] = "STALE"
            result["issues"].append(f"Cookies are {int(age_days)} days old (>{COOKIE_STALE_DAYS}d) — likely expired, re-login needed")
        elif age_days > COOKIE_WARN_DAYS:
            result["cookies_status"] = "AGING"
            result["issues"].append(f"Cookies are {int(age_days)} days old (>{COOKIE_WARN_DAYS}d) — consider refreshing login")
        else:
            result["cookies_status"] = "FRESH"
    else:
        result["cookies_status"] = "MISSING"
        if cfg["requires_login"]:
            result["issues"].append("Default/Cookies missing — profile not logged in")
        else:
            result["issues"].append("Default/Cookies missing — profile may need setup")

    # Check Default/Login Data
    login_data = profile_dir / "Default" / "Login Data"
    result["login_data_exists"] = login_data.exists()

    # Check profile sanity (file count)
    default_dir = profile_dir / "Default"
    if default_dir.exists():
        file_count = sum(1 for _ in default_dir.iterdir())
        if file_count < 3:
            result["issues"].append(f"Default/ only has {file_count} item(s) — profile may be empty/incomplete")

    # Determine overall status
    if not result["exists"]:
        result["overall"] = "MISSING"
    elif result["singleton_lock"] or result["cookies_status"] in ("MISSING",):
        result["overall"] = "NOT_LOGGED_IN"
    elif result["cookies_status"] == "STALE":
        result["overall"] = "STALE"
    elif result["corrupted_backups"]:
        result["overall"] = "WARN"
    elif result["cookies_status"] == "AGING":
        result["overall"] = "WARN"
    elif result["issues"]:
        result["overall"] = "WARN"
    else:
        result["overall"] = "OK"

    return result


# ---------------------------------------------------------------------------
# Repair actions
# ---------------------------------------------------------------------------

def remove_singleton_lock(retailer: str) -> bool:
    profile_dir = resolve_profile_dir(retailer)
    lock = profile_dir / SINGLETON_LOCK_PATH
    if lock.exists():
        try:
            lock.unlink()
            print(f"  [✓] Removed SingletonLock for {retailer}: {lock}")
            return True
        except Exception as e:
            print(f"  [✗] Failed to remove SingletonLock for {retailer}: {e}")
    return False


def remove_corrupted_backups(retailer: str, dry_run: bool = False) -> List[str]:
    profile_dir = resolve_profile_dir(retailer)
    parent = profile_dir.parent
    removed = []

    if not parent.exists():
        return removed

    for d in parent.iterdir():
        if d.is_dir() and d != profile_dir:
            if any(m in d.name.lower() for m in POISONED_MARKERS):
                if dry_run:
                    print(f"  [DRY RUN] Would remove: {d}")
                    removed.append(str(d))
                else:
                    try:
                        shutil.rmtree(d)
                        print(f"  [✓] Removed corrupted backup: {d}")
                        removed.append(str(d))
                    except Exception as e:
                        print(f"  [✗] Failed to remove {d}: {e}")
    return removed


def open_browser_for_login(retailer: str):
    """Open a Playwright browser window with the retailer profile for manual re-login."""
    cfg = RETAILER_CONFIGS[retailer]
    profile_dir = resolve_profile_dir(retailer)
    login_url = cfg["login_url"]

    print(f"\n  Opening browser for {retailer} re-login...")
    print(f"  Profile: {profile_dir}")
    print(f"  URL: {login_url}")
    print()

    script = f"""
import sys
sys.path.insert(0, '{ROOT}')
from playwright.sync_api import sync_playwright
import time

profile = '{profile_dir}'

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        profile,
        headless=False,
        channel='chrome',
        args=['--no-first-run', '--no-default-browser-check'],
        slow_mo=50,
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('{login_url}')
    print("\\nBrowser open. Log in manually, then press Enter here to close...")
    input()
    ctx.close()
    print("Profile saved. Browser closed.")
"""
    try:
        venv_python = ROOT / ".venv" / "bin" / "python3"
        python = str(venv_python) if venv_python.exists() else sys.executable
        subprocess.run([python, "-c", script], cwd=str(ROOT))
    except KeyboardInterrupt:
        print("\n  Cancelled.")
    except Exception as e:
        print(f"  Error: {e}")


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

STATUS_ICONS = {
    "OK": "✅",
    "WARN": "⚠️ ",
    "STALE": "🕐",
    "NOT_LOGGED_IN": "🔑",
    "MISSING": "❌",
    "UNKNOWN": "❓",
}

STATUS_COLORS = {
    "OK": "\033[32m",
    "WARN": "\033[33m",
    "STALE": "\033[33m",
    "NOT_LOGGED_IN": "\033[31m",
    "MISSING": "\033[31m",
    "UNKNOWN": "\033[90m",
}
RESET = "\033[0m"


def _c(text: str, status: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"{STATUS_COLORS.get(status, '')}{text}{RESET}"


def print_profile_report(profiles: List[Dict], verbose: bool = False):
    print(f"\n{'='*65}")
    print(f"  BROWSER PROFILE HEALTH  —  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*65}")

    all_ok = all(p["overall"] == "OK" for p in profiles)

    for p in profiles:
        status = p["overall"]
        icon = STATUS_ICONS.get(status, "?")
        cookie_info = ""
        if p["cookies_age_days"] is not None:
            cookie_info = f"  cookies: {p['cookies_age_days']}d old"
        elif p["cookies_status"] == "MISSING":
            cookie_info = "  cookies: MISSING"

        print(f"\n  {icon} {_c(p['retailer'].upper(), status):<20}  [{_c(status, status)}]{cookie_info}")
        print(f"     Path: {p['profile_dir']}")

        if p["issues"] or verbose:
            for issue in p["issues"]:
                print(f"     → {issue}")
        if p["corrupted_backups"]:
            print(f"     → {len(p['corrupted_backups'])} corrupted backup(s) found")
            for b in p["corrupted_backups"]:
                print(f"       - {Path(b).name}")

    print()
    if all_ok:
        print(f"  {_c('All profiles healthy.', 'OK')}\n")
    else:
        issues = [p for p in profiles if p["overall"] != "OK"]
        print(f"  {len(issues)} profile(s) need attention:")
        for p in issues:
            status = p["overall"]
            if status == "MISSING":
                print(f"    {p['retailer']}: Profile directory not found — run setup script")
            elif status == "NOT_LOGGED_IN":
                print(f"    {p['retailer']}: Not logged in — run: python3 tools/profile_doctor.py --login {p['retailer']}")
            elif status == "STALE":
                print(f"    {p['retailer']}: Session expired — run: python3 tools/profile_doctor.py --login {p['retailer']}")
            elif status == "WARN":
                print(f"    {p['retailer']}: {'; '.join(p['issues'][:2])}")
            if p["corrupted_backups"]:
                print(f"    {p['retailer']}: Run: python3 tools/profile_doctor.py --fix-corrupted --retailer {p['retailer']}")
        print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Browser profile health checker and repair tool")
    ap.add_argument("--retailer", help="Single retailer to check (default: all)")
    ap.add_argument("--fix-corrupted", action="store_true", help="Remove corrupted/poisoned backup profile directories")
    ap.add_argument("--fix-locks", action="store_true", help="Remove SingletonLock files from profiles")
    ap.add_argument("--login", metavar="RETAILER", help="Open browser for manual re-login for a retailer")
    ap.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    ap.add_argument("--verbose", "-v", action="store_true", help="Show all issues even for OK profiles")
    args = ap.parse_args()

    retailers = list(RETAILER_CONFIGS.keys())
    if args.retailer:
        if args.retailer.lower() not in RETAILER_CONFIGS:
            print(f"Unknown retailer: {args.retailer}. Choose from: {', '.join(retailers)}")
            sys.exit(1)
        retailers = [args.retailer.lower()]

    # Login mode
    if args.login:
        r = args.login.lower()
        if r not in RETAILER_CONFIGS:
            print(f"Unknown retailer: {r}")
            sys.exit(1)
        open_browser_for_login(r)
        return

    # Inspect all profiles
    profiles = [inspect_profile(r) for r in retailers]
    print_profile_report(profiles, verbose=args.verbose)

    # Fix actions
    if args.fix_corrupted:
        print(f"{'='*65}")
        print("  REMOVING CORRUPTED BACKUP PROFILES")
        print(f"{'='*65}")
        total_removed = 0
        for r in retailers:
            removed = remove_corrupted_backups(r, dry_run=args.dry_run)
            total_removed += len(removed)
        if total_removed == 0:
            print("  No corrupted backups found.")
        else:
            verb = "Would remove" if args.dry_run else "Removed"
            print(f"\n  {verb} {total_removed} directory(ies).")
        print()

    if args.fix_locks:
        print(f"{'='*65}")
        print("  REMOVING SINGLETON LOCKS")
        print(f"{'='*65}")
        any_removed = False
        for r in retailers:
            profile_dir = resolve_profile_dir(r)
            lock = profile_dir / SINGLETON_LOCK_PATH
            if lock.exists():
                if args.dry_run:
                    print(f"  [DRY RUN] Would remove: {lock}")
                else:
                    removed = remove_singleton_lock(r)
                    if removed:
                        any_removed = True
        if not any_removed and not args.dry_run:
            print("  No SingletonLock files found.")
        print()


if __name__ == "__main__":
    main()
