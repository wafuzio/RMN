#!/usr/bin/env python3
"""
Target search and capture script.

Performs a keyword search on Target.com using a persistent authenticated profile
and writes canonical run JSON + HTML for the Retail Ad Monitor.

This is intentionally minimal to get Target wired into the pipeline:
- Uses TARGET_PROFILE_DIR (or profiles/target under project root) for the
  Playwright persistent profile.
- Performs a basic search for the given keyword.
- Saves HTML and a canonical-but-empty ads[] array for now.

Later we can enrich ad extraction based on documented Target ad surfaces.
"""

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from filename_utils import generate_ad_filename
from utils.path_taxonomy import ensure_subdir
from core.brands import canonicalize, add_brand

try:
    from utils.time_utils import now_iso_z
except Exception:
    # Fallback if utils is not on path
    def now_iso_z(timespec: str = "seconds") -> str:
        return datetime.now().isoformat(timespec=timespec)


def build_run_id(dt: Optional[datetime] = None) -> str:
    """Generate 14-digit run ID: YYYYMMDDHHMMSS (local time)."""
    dt = dt or datetime.now()
    return dt.strftime("%Y%m%d%H%M%S")


def _resolve_profile_dir() -> Optional[str]:
    """Resolve Target profile directory using env var or project-local fallback."""
    # 1) Environment variable
    env_dir = os.environ.get("TARGET_PROFILE_DIR")
    if env_dir and os.path.isdir(env_dir):
        return env_dir

    # 2) Fallback to profiles/target under project root
    project_root = Path(__file__).resolve().parent
    # Walk up until we find a marker like config/launcher.env
    for _ in range(4):
        if (project_root / "config" / "launcher.env").exists():
            break
        project_root = project_root.parent
    fallback = project_root / "profiles" / "target"
    if fallback.is_dir():
        return str(fallback)

    return None


def _normalize_ad_href(raw_href: Optional[str]) -> Optional[str]:
    """Normalize ad click URLs to the underlying Target brand/product URL.

    For safeframe creatives we often see a DoubleClick URL like:
      https://adclick.g.doubleclick.net/pcs/click?...&adurl=https://www.target.com/p/...

    We prefer the inner adurl if present so downstream tooling sees the real
    Target URL instead of the ad server redirect.
    """
    if not raw_href:
        return None
    href = raw_href.strip()
    try:
        parsed = urlparse(href)
    except Exception:
        return href or None

    qs = parse_qs(parsed.query or "")
    adurl_vals = qs.get("adurl") or []
    if adurl_vals:
        target_url = adurl_vals[0]
        return target_url or href
    return href or None


def _resolve_brand_from_href(ctx, href: str, timeout_ms: int = 8000) -> Optional[str]:
    if not href:
        return None
    try:
        page = ctx.new_page()
    except Exception:
        return None
    try:
        page.goto(href, wait_until="domcontentloaded", timeout=timeout_ms)

        # Preferred: the explicit "Shop all <Brand>" link on the PDP.
        try:
            el = page.query_selector("a[data-test='shopAllBrandLink'] span")
        except Exception:
            el = None
        if el is not None:
            try:
                raw = el.inner_text() or ""
            except Exception:
                raw = ""
            text = " ".join(raw.split())  # collapse whitespace/newlines
            lower = text.lower()
            if lower.startswith("shop all"):
                text = text[len("shop all") :].strip()
            if text:
                # Canonicalize and add to lexicon if new
                canon = canonicalize(text)
                if canon:
                    return canon
                add_brand(text)
                return text

        # Fallback: page title element if present.
        h1 = page.query_selector("h1[data-test='page-title']")
        if not h1:
            return None
        text = h1.inner_text() or ""
        text = text.strip()
        if text:
            # Canonicalize and add to lexicon if new
            canon = canonicalize(text)
            if canon:
                return canon
            add_brand(text)
        return text or None
    except Exception:
        return None
    finally:
        try:
            page.close()
        except Exception:
            pass


def _extract_ads_from_html(
    html: str,
    run_id: str,
    keyword: str,
    log,
    safeframe_htmls: Optional[list[str]] = None,
    ctx=None,
) -> list[dict]:
    """Extract Target ad units from saved HTML using BeautifulSoup.

    We look for the companion markup that mirrors the safeframe:
    - ListingPageBannerAd: fluid-container.page-search + a[href*='adclick.g.doubleclick.net'] img
    - Sponsored_Logo: flex-container under a Sponsored logo wrapper.
    """
    ads: list[dict] = []
    soup = BeautifulSoup(html or "", "html.parser")

    # Listing page banners (top-level document)
    banner_idx = 0
    # Primary: Target's ListingPageBannerAd module wrapper
    banner_containers = list(soup.select("div[data-module-type='ListingPageBannerAd']"))
    # Fallback: older fluid-container.page-search wrapper if present
    if not banner_containers:
        banner_containers = list(soup.select("div.fluid-container.page-search"))
    log(f"[target] Banner containers detected: {len(banner_containers)}")

    for cont in banner_containers:
        try:
            # Prefer a DoubleClick href if present, otherwise any <a> that wraps an <img>
            a = cont.select_one("a[href*='adclick.g.doubleclick.net']")
            if not a:
                # fallback: any anchor with a descendant <img>
                for cand in cont.select("a"):
                    if cand.find("img"):
                        a = cand
                        break
            if not a:
                continue

            # Prefer heroImg, otherwise first img under the chosen anchor or container
            img = cont.select_one("img.heroImg") or a.find("img") or cont.find("img")
            if not img:
                continue

            src = img.get("src") or ""
            alt = img.get("alt") or ""
            raw_href = a.get("href") or ""
            href_norm = _normalize_ad_href(raw_href)
            brand = ""
            if ctx is not None and href_norm:
                try:
                    log(f"[target] Resolving banner brand from PDP: {href_norm[:160]}")
                    b = _resolve_brand_from_href(ctx, href_norm)
                    if b:
                        brand = b
                        log(f"[target] Banner brand resolved: {brand}")
                except Exception as e:
                    log(f"[target] Brand resolve failed for banner href: {e}")
            classes = cont.get("class") or []
            slot = None
            for token in classes:
                if isinstance(token, str) and token.startswith("position-"):
                    slot = token
                    break

            banner_idx += 1
            ad = {
                "id": f"target-{run_id}-banner-{banner_idx}",
                "type": "ListingPageBannerAd",
                "brand": brand,
                "title": None,
                "message": alt or None,
                "description": None,
                "cta": None,
                "href": href_norm,
                "image_url": src or None,
                "image_path": None,
                "products": [],
                "metadata": {
                    "slot": slot,
                    "keyword_token": keyword,
                    "source": "target",
                },
            }
            ads.append(ad)
        except Exception as e:
            log(f"[target] Failed to extract listing banner from HTML: {e}")
    log(f"[target] ListingPageBannerAd from HTML: {banner_idx}")

    # Sponsored logo blocks (top-level document)
    logo_idx = 0
    # Prefer the explicit Sponsored logo wrapper if present, otherwise any wrapper with sponsored-text
    wrappers = list(soup.select("div#adDesktopWrapperContainer"))
    if not wrappers:
        wrappers = list(soup.select("div:has(p[data-test='sponsored-text'])"))
    log(f"[target] Sponsored logo wrappers detected: {len(wrappers)}")

    for wrapper in wrappers:
        # In documented pages, the Sponsored Logo creative often lives in a
        # sibling flex-container immediately following the wrapper, not
        # strictly as a descendant. Try descendants first, then walk
        # forward siblings to find the first flex-container that actually
        # holds the ad creative.
        flex_blocks = list(wrapper.select("div.flex-container"))
        if not flex_blocks:
            sib = wrapper.find_next_sibling()
            steps = 0
            while sib is not None and steps < 4 and not flex_blocks:
                steps += 1
                classes = sib.get("class") or []
                if sib.name == "div" and any(
                    isinstance(c, str) and "flex-container" in c for c in classes
                ):
                    flex_blocks.append(sib)
                    break
                sib = sib.find_next_sibling()
        if not flex_blocks:
            flex_blocks = [wrapper]

        for flex in flex_blocks:
            try:
                # Prefer DoubleClick href if present, fallback to any anchor with an <img>
                a = flex.select_one("a[href*='adclick.g.doubleclick.net']")
                if not a:
                    for cand in flex.select("a"):
                        if cand.find("img"):
                            a = cand
                            break
                if not a:
                    continue

                img = a.find("img") or flex.find("img")
                if not img:
                    continue

                src = img.get("src") or ""
                alt = img.get("alt") or ""
                raw_href = a.get("href") or ""
                href_norm = _normalize_ad_href(raw_href)
                brand = ""
                if ctx is not None and href_norm:
                    try:
                        log(f"[target] Resolving logo brand from PDP: {href_norm[:160]}")
                        b = _resolve_brand_from_href(ctx, href_norm)
                        if b:
                            brand = b
                            log(f"[target] Logo brand resolved: {brand}")
                    except Exception as e:
                        log(f"[target] Brand resolve failed for logo href: {e}")
                logo_idx += 1
                ad = {
                    "id": f"target-{run_id}-logo-{logo_idx}",
                    "type": "Sponsored_Logo",
                    "brand": brand,
                    "title": None,
                    "message": alt or None,
                    "description": None,
                    "cta": None,
                    "href": href_norm,
                    "image_url": src or None,
                    "image_path": None,
                    "products": [],
                    "metadata": {
                        "slot": "adDesktopWrapperContainer",
                        "keyword_token": keyword,
                        "source": "target",
                    },
                }
                ads.append(ad)
            except Exception as e:
                log(f"[target] Failed to extract sponsored logo from HTML: {e}")
    log(f"[target] Sponsored_Logo from HTML: {logo_idx}")

    iframe_sel = "iframe[src*='safeframe.googlesyndication.com']"
    safeframes = list(soup.select(iframe_sel))
    log(f"[target] Safeframe iframes detected: {len(safeframes)}")

    if safeframe_htmls is not None:
        html_iter = list(safeframe_htmls)
    else:
        html_iter = []
        for idx_sf, iframe in enumerate(safeframes, 1):
            src = iframe.get("src") or ""
            if not src:
                continue
            try:
                log(f"[target] Fetching safeframe {idx_sf}: {src[:120]}...")
                resp = requests.get(src, timeout=10, headers={"User-Agent": "Mozilla/5.0 (compatible; TargetScraper/1.0)"})
                if resp.status_code != 200:
                    log(f"[target] Safeframe {idx_sf} HTTP {resp.status_code}")
                    continue
                html_iter.append(resp.text or "")
            except Exception as e:
                log(f"[target] Safeframe {idx_sf} fetch error: {e}")
                continue

    for idx_sf, sf_html in enumerate(html_iter, 1):
        try:
            sf_soup = BeautifulSoup(sf_html or "", "html.parser")
        except Exception as e:
            log(f"[target] Safeframe {idx_sf} parse error: {e}")
            continue

        # Checklist-style debug: even if our container selectors miss, report
        # what core ad elements exist so we can align selectors later.
        adclick_anchors = sf_soup.select("a[href*='adclick.g.doubleclick.net']")
        ad_link_anchors = sf_soup.select("a#ad-link")
        hero_imgs = sf_soup.select("img.heroImg")
        log(
            f"[target] Safeframe {idx_sf} checklist: "
            f"adclick anchors={len(adclick_anchors)}, "
            f"a#ad-link={len(ad_link_anchors)}, heroImg imgs={len(hero_imgs)}"
        )
        # Log short samples for the first couple of anchors/images
        for i, a_el in enumerate(adclick_anchors[:2], 1):
            href = (a_el.get("href") or "")[:160]
            log(f"[target] Safeframe {idx_sf} sample adclick[{i}]: {href}")
        for i, img_el in enumerate(hero_imgs[:2], 1):
            src_sample = (img_el.get("src") or "")[:160]
            alt_sample = (img_el.get("alt") or "")[:120]
            log(
                f"[target] Safeframe {idx_sf} sample heroImg[{i}]: "
                f"src={src_sample}, alt={alt_sample}"
            )

        # Safeframe banners use the fluid-container.page-search pattern
        sf_banner_containers = list(sf_soup.select("div.fluid-container.page-search"))
        log(f"[target] Safeframe {idx_sf} banner containers: {len(sf_banner_containers)}")
        for cont in sf_banner_containers:
            try:
                a = cont.select_one("a[href*='adclick.g.doubleclick.net']")
                if not a:
                    for cand in cont.select("a"):
                        if cand.find("img"):
                            a = cand
                            break
                if not a:
                    continue

                img = cont.select_one("img.heroImg") or a.find("img") or cont.find("img")
                if not img:
                    continue

                src_url = img.get("src") or ""
                alt = img.get("alt") or ""
                raw_href = a.get("href") or ""
                href_norm = _normalize_ad_href(raw_href)
                brand = ""
                if ctx is not None and href_norm:
                    try:
                        log(f"[target] Resolving safeframe banner brand from PDP: {href_norm[:160]}")
                        b = _resolve_brand_from_href(ctx, href_norm)
                        if b:
                            brand = b
                            log(f"[target] Safeframe banner brand resolved: {brand}")
                    except Exception as e:
                        log(f"[target] Brand resolve failed for safeframe banner href: {e}")
                classes = cont.get("class") or []
                slot = None
                for token in classes:
                    if isinstance(token, str) and token.startswith("position-"):
                        slot = token
                        break

                banner_idx += 1
                ad = {
                    "id": f"target-{run_id}-banner-{banner_idx}",
                    "type": "ListingPageBannerAd",
                    "brand": brand,
                    "title": None,
                    "message": alt or None,
                    "description": None,
                    "cta": None,
                    "href": href_norm,
                    "image_url": src_url or None,
                    "image_path": None,
                    "products": [],
                    "metadata": {
                        "slot": slot,
                        "keyword_token": keyword,
                        "source": "target",
                    },
                }
                ads.append(ad)
            except Exception as e:
                log(f"[target] Failed to extract listing banner from safeframe: {e}")

        sf_flex_blocks = sf_soup.select("div.flex-container")
        log(f"[target] Safeframe {idx_sf} flex containers: {len(sf_flex_blocks)}")
        for flex in sf_flex_blocks:
            try:
                a = flex.select_one("a#ad-link") or flex.select_one("a[href*='adclick.g.doubleclick.net']")
                if not a:
                    for cand in flex.select("a"):
                        if cand.find("img"):
                            a = cand
                            break
                if not a:
                    continue

                img = a.find("img") or flex.find("img")
                if not img:
                    continue

                src_url = img.get("src") or ""
                alt = img.get("alt") or ""
                raw_href = a.get("href") or ""
                href_norm = _normalize_ad_href(raw_href)
                brand = ""
                if ctx is not None and href_norm:
                    try:
                        b = _resolve_brand_from_href(ctx, href_norm)
                        if b:
                            brand = b
                    except Exception as e:
                        log(f"[target] Brand resolve failed for safeframe logo href: {e}")

                logo_idx += 1
                ad = {
                    "id": f"target-{run_id}-logo-{logo_idx}",
                    "type": "Sponsored_Logo",
                    "brand": brand,
                    "title": None,
                    "message": alt or None,
                    "description": None,
                    "cta": None,
                    "href": href_norm,
                    "image_url": src_url or None,
                    "image_path": None,
                    "products": [],
                    "metadata": {
                        "slot": "adDesktopWrapperContainer",
                        "keyword_token": keyword,
                        "source": "target",
                    },
                }
                ads.append(ad)
            except Exception as e:
                log(f"[target] Failed to extract sponsored logo from safeframe: {e}")

    log(f"[target] ListingPageBannerAd total (HTML + safeframe): {banner_idx}")
    log(f"[target] Sponsored_Logo total (HTML + safeframe): {logo_idx}")

    # Placement metadata should reflect banner ordering only, not logos.
    banner_ads = [ad for ad in ads if ad.get("type") == "ListingPageBannerAd"]
    total_banners = len(banner_ads)
    if total_banners:
        for idx, ad in enumerate(banner_ads, start=1):
            meta = ad.get("metadata") or {}
            meta["placement_index"] = idx
            meta["placement_total"] = total_banners
            ad["metadata"] = meta

    return ads


def search_and_capture(keyword: str, output_dir: str, *, headless: bool = False) -> bool:
    """Search Target for a keyword and capture results.

    Creates canonical run JSON and HTML under:
      {output_dir}/runs/
        search_results_<run_id>.html
        run_results_<run_id>.json

    Returns True on success, False otherwise.
    """
    profile_dir = _resolve_profile_dir()
    if not profile_dir:
        print("❌ TARGET_PROFILE_DIR not set and no profiles/target directory found")
        print("   Run scripts/setup_target_profile.sh first.")
        return False

    # Clean up stale Chromium lock file if present (mirrors Instacart pattern)
    # Use lexists() instead of exists() to catch broken symlinks
    lock_file = os.path.join(profile_dir, "SingletonLock")
    if os.path.lexists(lock_file):
        try:
            os.remove(lock_file)
            print(f"   Removed stale lock file: {lock_file}")
        except Exception as e:
            print(f"   Warning: Could not remove lock file: {e}")

    runs_dir = os.path.join(output_dir, "runs")
    os.makedirs(runs_dir, exist_ok=True)
    output_root = Path(output_dir)

    run_id = build_run_id()
    timestamp_iso = now_iso_z()

    html_file = os.path.join(runs_dir, f"search_results_{run_id}.html")
    json_file = os.path.join(runs_dir, f"run_results_{run_id}.json")
    debug_log = os.path.join(runs_dir, f"capture_debug_target_{run_id}.log")

    def log(msg: str) -> None:
        print(msg)
        try:
            with open(debug_log, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().isoformat()} {msg}\n")
        except Exception:
            pass

    client = os.path.basename(output_dir.rstrip("/")) or "unknown_client"

    log(f"🔍 Searching Target for: '{keyword}'")
    log(f"   Profile: {profile_dir}")
    log(f"   Output:  {output_dir}")

    # Handle Chromium lock files before launching.
    # SingletonLock is a symlink whose target encodes the holding PID.
    # If the PID is alive → profile is in use; wait up to 60s for it to release.
    # If the PID is dead (stale lock) → safe to remove.
    if profile_dir:
        singleton = Path(profile_dir) / "SingletonLock"
        wait_deadline = time.time() + 60
        while singleton.exists() or singleton.is_symlink():
            holding_pid = None
            try:
                target = os.readlink(str(singleton))
                # Chromium encodes "hostname-PID" or just "PID" in the symlink target
                holding_pid = int(target.split("-")[-1])
            except Exception:
                pass
            if holding_pid:
                try:
                    os.kill(holding_pid, 0)  # 0 = check existence only
                    # PID is alive — profile is in active use
                    if time.time() > wait_deadline:
                        log(f"   ⚠️ Profile still locked by PID {holding_pid} after 60s — aborting to avoid crash")
                        return False
                    log(f"   Profile locked by PID {holding_pid}, waiting...")
                    time.sleep(5)
                    continue
                except (ProcessLookupError, PermissionError):
                    pass  # PID is dead — stale lock, safe to remove
            # Lock exists but no live PID — remove stale locks
            for lock_name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
                lock_path = Path(profile_dir) / lock_name
                if lock_path.exists() or lock_path.is_symlink():
                    try:
                        lock_path.unlink()
                        log(f"   Removed stale lock: {lock_name}")
                    except Exception:
                        pass
            break

    try:
        with sync_playwright() as p:
            log("   Launching persistent Chromium context for Target")
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=headless,
                viewport={"width": 1366, "height": 900},
                ignore_https_errors=True,
                locale="en-US",
            )

            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            base_url = "https://www.target.com"
            search_box_sel = "input[placeholder*='Search'], input[type='search']"

            log(f"   Navigating to {base_url}...")
            page.goto(base_url, wait_until="domcontentloaded", timeout=45000)
            # Wait for React header to hydrate (domcontentloaded fires too early)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass  # timeout is fine — just best-effort
            time.sleep(3)

            # Login state check — missing login means fewer ad types captured
            # NOTE: Target's #account-sign-in element and aria-label="Account, sign in"
            # persist in the DOM even when logged in (SSR pre-render placeholder that
            # React doesn't always replace in Playwright). DOM checks are unreliable.
            # Use auth cookies as the ground truth instead.
            try:
                _tgt_logged_in = False
                cookies = ctx.cookies()
                tgt_auth = [c for c in cookies
                            if c['name'] in ('accessToken', 'idToken', 'refreshToken')
                            and 'target' in c.get('domain', '')]
                if len(tgt_auth) >= 2:
                    _tgt_logged_in = True
                    log(f"   ✅ Logged-in session detected ({len(tgt_auth)} auth cookies)")
                else:
                    log(f"   ⚠️ Not logged in — only {len(tgt_auth)} auth cookie(s) found")
                    try:
                        from utils.profile_health import prompt_relogin
                        _relogged = prompt_relogin(page, "target", keyword, log_fn=log)
                        if not _relogged:
                            from utils.profile_health import record_login_outcome
                            record_login_outcome("target", keyword, logged_in=False)
                    except Exception:
                        pass
            except Exception:
                pass

            used_search_box = False
            try:
                page.wait_for_selector(search_box_sel, timeout=5000)
                box = page.locator(search_box_sel).first
                box.click()
                box.fill(keyword)
                page.keyboard.press("Enter")
                page.wait_for_load_state("domcontentloaded", timeout=30000)
                used_search_box = True
                log("   Used on-page search box")
            except Exception as e:
                log(f"⚠️  Search box interaction failed: {type(e).__name__}: {e}")
                fallback_url = f"{base_url.rstrip('/')}/s?searchTerm={keyword}"
                log(f"   Falling back to direct search URL: {fallback_url}")
                page.goto(fallback_url, wait_until="domcontentloaded", timeout=45000)

            # Allow initial content to settle
            time.sleep(3)

            # Trigger lazy-loaded ad modules by scrolling through the page once
            try:
                log("   Performing scroll pass to trigger lazy-loaded modules")
                # Measure scroll behavior from Python so we can log each step
                start_scroll = time.time()
                viewport_h = page.evaluate("() => window.innerHeight || 800")
                scroll_h = page.evaluate("() => document.body && document.body.scrollHeight || 0")
                step = max(int(viewport_h * 0.8), 600)
                log(f"   Scroll metrics: viewport_h={viewport_h}, scroll_h={scroll_h}, step={step}")
                y = 0
                step_idx = 0
                while y < scroll_h and step > 0:
                    page.evaluate("y => window.scrollTo(0, y)", y)
                    step_idx += 1
                    log(f"   Scroll step {step_idx}: y={y}/{scroll_h}")
                    # Give Target's Roundel / safeframe modules a bit more
                    # time to hydrate at each scroll position.
                    page.wait_for_timeout(750)
                    y += step
                # Return to top
                page.evaluate("() => window.scrollTo(0, 0)")
                page.wait_for_timeout(300)
                dur = time.time() - start_scroll
                log(f"   Scroll pass complete, steps={step_idx}, duration={dur:.2f}s; back at top")
            except Exception as e:
                log(f"[target] Scroll pass failed (continuing anyway): {e}")

            # Collect iframe HTML documents directly from the live DOM via
            # Playwright's content_frame(). This lets us see not only the
            # classic safeframe banner markup but also any 300x250 "sponsored
            # logo" creatives that live in non-standard iframes.
            safeframe_htmls: list[str] = []
            try:
                iframe_handles = page.query_selector_all("iframe")
                log(f"   Iframes in live DOM: {len(iframe_handles)}")
                captured = 0
                for idx_sf, iframe in enumerate(iframe_handles, 1):
                    try:
                        src = iframe.get_attribute("src") or ""
                    except Exception as e:
                        log(f"   [sf] Failed to read src for iframe {idx_sf}: {e}")
                        src = ""

                    try:
                        frame = iframe.content_frame()
                        if frame is None:
                            continue
                        log(
                            f"   [sf] Capturing iframe {idx_sf} DOM (src={src[:80]})..."
                        )
                        sf_html = frame.content()
                        if not sf_html:
                            continue
                        captured += 1
                        safeframe_htmls.append(sf_html)
                        sf_path = os.path.join(runs_dir, f"safeframe_{run_id}_{captured}.html")
                        try:
                            with open(sf_path, "w", encoding="utf-8") as f:
                                f.write(sf_html)
                            log(f"   [sf] Saved safeframe {captured} HTML -> {sf_path}")
                        except Exception as e:
                            log(f"   [sf] Failed to write safeframe {captured} HTML: {e}")
                    except Exception as e:
                        log(f"   [sf] Error capturing safeframe {idx_sf} DOM: {e}")
            except Exception as e:
                log(f"   [sf] Unexpected error while collecting safeframes: {e}")

            html_content = page.content()
            with open(html_file, "w", encoding="utf-8") as f:
                f.write(html_content)
            log(f"💾 HTML saved: {html_file}")

            # Track profile health (block detection + persistent ledger)
            try:
                from utils.profile_health import check_and_record
                blk, blk_reason = check_and_record(html_content, "target", keyword, alert=True)
                if blk:
                    log(f"❌ Target page blocked: {blk_reason}")
                    log("   Profile needs manual re-login in a real Chrome window.")
                    return False
            except Exception:
                pass

            # Take a full-page SRP screenshot after HTML capture so the PNG
            # reflects the same hydrated DOM we just wrote to disk.
            try:
                main_dir = ensure_subdir("target", output_root, "Main")
                fullpage_filename = generate_ad_filename(
                    retailer="target",
                    ad_type="main",
                    client=client,
                    search_term=keyword,
                    timestamp=run_id,
                    index=1,
                    extension="png",
                    advertiser=None,
                )
                fullpage_path = main_dir / fullpage_filename
                # Hide sticky/fixed headers before full-page screenshot to prevent
                # duplicate content at Playwright's viewport-stitch boundaries.
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(300)
                page.evaluate("""() => {
                    document.querySelectorAll('header, nav, [class*="sticky"], [class*="Sticky"]')
                        .forEach(el => {
                            const style = window.getComputedStyle(el);
                            if (style.position === 'fixed' || style.position === 'sticky') {
                                el.dataset._origPosition = style.position;
                                el.style.position = 'absolute';
                            }
                        });
                }""")
                page.screenshot(path=str(fullpage_path), full_page=True)
                # Restore sticky headers
                page.evaluate("""() => {
                    document.querySelectorAll('[data-_orig-position]')
                        .forEach(el => {
                            el.style.position = el.dataset._origPosition;
                            delete el.dataset._origPosition;
                        });
                }""")
                log(f"   Full-page screenshot saved: {fullpage_path}")
            except Exception as e:
                log(f"[target] Full-page screenshot failed (continuing anyway): {e}")

            # Screenshot individual ad elements from the live page before
            # extracting metadata from HTML. This gives us actual ad images.
            _ad_screenshots = {"banner": [], "logo": []}
            try:
                # Restore sticky headers for accurate ad positioning
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(500)

                # ListingPageBannerAd modules
                banner_els = page.locator("div[data-module-type='ListingPageBannerAd']")
                banner_count = banner_els.count()
                if banner_count:
                    banner_dir = ensure_subdir("target", output_root, "ListingPageBannerAd")
                    for bi in range(banner_count):
                        try:
                            container = banner_els.nth(bi)
                            container.scroll_into_view_if_needed(timeout=3000)
                            time.sleep(0.3)
                            
                            # Screenshot the actual ad content (anchor/image) instead of the container
                            # to avoid capturing empty space or incorrect dimensions
                            shot_el = container
                            try:
                                # Try to find the actual ad anchor with image
                                anchor = container.locator("a[href*='adclick.g.doubleclick.net']").first
                                if anchor.count() > 0:
                                    shot_el = anchor
                                    log(f"   [target] Banner {bi+1}: targeting anchor element")
                                else:
                                    # Fallback: try any anchor with an image
                                    anchor_with_img = container.locator("a:has(img)").first
                                    if anchor_with_img.count() > 0:
                                        shot_el = anchor_with_img
                                        log(f"   [target] Banner {bi+1}: targeting anchor with image")
                                    else:
                                        # Last resort: screenshot the image directly
                                        img = container.locator("img.heroImg, img").first
                                        if img.count() > 0:
                                            shot_el = img
                                            log(f"   [target] Banner {bi+1}: targeting image element")
                            except Exception as e:
                                log(f"   [target] Banner {bi+1}: element targeting failed, using container: {e}")
                            
                            # Wait for ad images to load (Target uses lazy loading)
                            try:
                                img_locator = shot_el.locator("img").first
                                if img_locator.count() > 0:
                                    img_locator.wait_for(state="visible", timeout=3000)
                                    time.sleep(0.5)
                            except Exception:
                                pass
                            
                            fname = generate_ad_filename(
                                retailer="target", ad_type="listingpagebannerad",
                                client=client, search_term=keyword,
                                timestamp=run_id, index=bi + 1,
                                extension="png", advertiser=None,
                            )
                            fpath = banner_dir / fname
                            shot_el.screenshot(path=str(fpath))
                            
                            # Verify screenshot isn't blank
                            try:
                                from PIL import Image as PILImage
                                with PILImage.open(fpath) as img:
                                    pixels = img.load()
                                    width, height = img.size
                                    white_count = 0
                                    total = 0
                                    for x in range(0, width, max(1, width//20)):
                                        for y in range(0, height, max(1, height//20)):
                                            r, g, b = pixels[x, y]
                                            if r > 240 and g > 240 and b > 240:
                                                white_count += 1
                                            total += 1
                                    white_pct = 100 * white_count / total if total > 0 else 100
                                    
                                    if white_pct > 95:
                                        log(f"   ⚠️ Banner ad {bi+1} is blank ({white_pct:.0f}% white), skipping")
                                        fpath.unlink()
                                        _ad_screenshots["banner"].append(None)
                                    else:
                                        _ad_screenshots["banner"].append(str(fpath))
                                        log(f"   📸 Banner ad {bi+1} saved: {fpath.name}")
                            except Exception as e:
                                _ad_screenshots["banner"].append(str(fpath))
                                log(f"   📸 Banner ad {bi+1} saved: {fpath.name} (verification skipped: {e})")
                        except Exception as e:
                            log(f"   [target] Banner ad {bi+1} screenshot failed: {e}")
                            _ad_screenshots["banner"].append(None)

                # Sponsored Logo (adDesktopWrapperContainer)
                # The ad creative lives inside an iframe within the wrapper.
                # Screenshotting the wrapper clips the creative, so we pierce
                # the iframe and screenshot its body for the full uncropped image.
                logo_els = page.locator("div#adDesktopWrapperContainer")
                logo_count = logo_els.count()
                if logo_count:
                    logo_dir = ensure_subdir("target", output_root, "Sponsored_Logo")
                    for li in range(logo_count):
                        try:
                            el = logo_els.nth(li)
                            el.scroll_into_view_if_needed(timeout=3000)
                            time.sleep(0.5)
                            fname = generate_ad_filename(
                                retailer="target", ad_type="sponsored_logo",
                                client=client, search_term=keyword,
                                timestamp=run_id, index=li + 1,
                                extension="png", advertiser=None,
                            )
                            fpath = logo_dir / fname
                            # Try to screenshot the iframe content for a full uncropped capture
                            _logo_captured = False
                            try:
                                iframe_handle = el.locator("iframe").first
                                if iframe_handle.count() > 0:
                                    frame = iframe_handle.content_frame()
                                    if frame:
                                        frame_body = frame.locator("body")
                                        if frame_body.count() > 0:
                                            frame_body.screenshot(path=str(fpath))
                                            _logo_captured = True
                                            log(f"   📸 Sponsored logo {li+1} saved (iframe): {fpath.name}")
                            except Exception as e_iframe:
                                log(f"   [target] Sponsored logo {li+1} iframe screenshot failed, falling back to wrapper: {e_iframe}")
                            # Fallback: screenshot the wrapper element directly
                            if not _logo_captured:
                                el.screenshot(path=str(fpath))
                                log(f"   📸 Sponsored logo {li+1} saved (wrapper): {fpath.name}")
                            _ad_screenshots["logo"].append(str(fpath))
                        except Exception as e:
                            log(f"   [target] Sponsored logo {li+1} screenshot failed: {e}")
                            _ad_screenshots["logo"].append(None)

                log(f"   Ad screenshots: {len(_ad_screenshots['banner'])} banners, {len(_ad_screenshots['logo'])} logos")
            except Exception as e:
                log(f"   [target] Ad screenshot pass failed (continuing): {e}")

            # Extract ads from the saved HTML using BeautifulSoup (iframe-safe).
            # Pass the live Playwright context so we can resolve brands from the
            # PDP "Shop all <Brand>" link when needed.
            log("   Extracting Target ads from saved HTML...")
            ads: list[dict] = _extract_ads_from_html(
                html_content,
                run_id,
                keyword,
                log,
                safeframe_htmls or None,
                ctx,
            )
            log(f"   Extracted {len(ads)} Target ad units from HTML")

            # Match ad screenshots to extracted ad objects by type + index
            _banner_idx = 0
            _logo_idx = 0
            for ad in ads:
                img_path = None
                if ad["type"] == "ListingPageBannerAd":
                    if _banner_idx < len(_ad_screenshots["banner"]):
                        img_path = _ad_screenshots["banner"][_banner_idx]
                    _banner_idx += 1
                elif ad["type"] == "Sponsored_Logo":
                    if _logo_idx < len(_ad_screenshots["logo"]):
                        img_path = _ad_screenshots["logo"][_logo_idx]
                    _logo_idx += 1
                if img_path:
                    ad["image_path"] = str(Path(img_path).relative_to(output_root))

            # CDN fallback: download image_url for any ad still missing image_path
            # (e.g. safeframe-only ads that had no live DOM element to screenshot)
            _cdn_downloaded = 0
            for idx, ad in enumerate(ads, start=1):
                if ad.get("image_path") or not ad.get("image_url"):
                    continue
                ad_type = ad.get("type", "ListingPageBannerAd")
                folder = "ListingPageBannerAd" if ad_type == "ListingPageBannerAd" else (
                    "Sponsored_Logo" if ad_type == "Sponsored_Logo" else "Main")
                try:
                    target_dir = ensure_subdir("target", output_root, folder)
                    brand_tag = (ad.get("brand") or "unknown").strip() or "unknown"
                    fname = generate_ad_filename(
                        retailer="target", ad_type=ad_type.lower(),
                        client=client, search_term=keyword,
                        timestamp=run_id, index=idx,
                        extension="png", advertiser=brand_tag,
                    )
                    dest = target_dir / fname
                    req = urllib.request.Request(
                        ad["image_url"],
                        headers={
                            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                            "Referer": page.url,
                            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                        },
                    )
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        with open(dest, "wb") as f:
                            f.write(resp.read())
                    ad["image_path"] = str(dest.relative_to(output_root))
                    _cdn_downloaded += 1
                    log(f"   📥 CDN fallback: ad #{idx} ({ad_type}) -> {dest.name}")
                except Exception as e:
                    log(f"   [target] CDN fallback failed for ad #{idx}: {e}")
            if _cdn_downloaded:
                log(f"   CDN fallback downloaded {_cdn_downloaded} additional ad image(s)")

            run_payload = {
                "retailer": "target",
                "client": client,
                "keyword": keyword,
                "timestamp": timestamp_iso,
                "run_id": run_id,
                "url_after": page.url,
                "ads": ads,
            }

            # Extract product listings from saved HTML
            try:
                from tools.extract_product_listings import extract_product_listings
                product_listings = extract_product_listings("target", html_content)
                run_payload["product_listings"] = product_listings
                sp_count = sum(1 for p in product_listings if p.get("is_sponsored"))
                log(f"   Extracted {len(product_listings)} product listings ({sp_count} sponsored)")
            except Exception as pl_err:
                log(f"   Product listing extraction failed: {pl_err}")

            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(run_payload, f, indent=2)
            log(f"💾 JSON saved: {json_file}")

            ctx.close()
            log("✅ Target search_and_capture completed")
            return True

    except PlaywrightTimeout as e:
        log(f"❌ Timeout during Target search: {e}")
        return False
    except Exception as e:
        log(f"❌ Error during Target search: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Search Target and capture results")
    ap.add_argument("keyword", help="Search keyword")
    ap.add_argument("--output-dir", required=True, help="Output directory (e.g. output/target/client)")
    ap.add_argument("--headless", action="store_true", help="Run browser in headless mode")

    args = ap.parse_args()
    ok = search_and_capture(args.keyword, args.output_dir, headless=args.headless)
    sys.exit(0 if ok else 1)
