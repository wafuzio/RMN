#!/usr/bin/env python3
"""
Walmart search and capture with selector-based ad detection.
"""
from __future__ import annotations
import os
import time
import json
import urllib.parse as ul
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Callable

import requests
from playwright.sync_api import sync_playwright

SLUG = "walmart"
DISPLAY_NAME = "Walmart"
PROFILE_ENV = "WALMART_PROFILE_DIR"

HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# Ad modules we'll detect and screenshot
SELECTORS = {
    "top_banner": "a.ad, a.adctr",  # programmatic banners (top/bottom)
    "sba": '[data-testid="sba-container"]',  # Sponsored Brand module
    "tile_takeover": '[data-testid="tile-take-over"]',  # Tile takeover
    "sbv": '[data-testid="search-video-in-grid"]',  # Sponsored Brand Video
}


@dataclass
class CaptureResult:
    html_saved: int
    shots: List[str]
    assets: List[str]
    meta: Dict


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def safe_filename(name: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in name)


def _parse_walmart_redirect(href: str) -> str:
    """
    Walmart redirectors:
    - https://www.walmart.com/sp/track?...&rd=
    - https://www.walmart.com/dad/trk/... (encrypted)
    Prefer rd= when present; otherwise leave as-is.
    """
    try:
        u = ul.urlparse(href)
        qs = ul.parse_qs(u.query)
        if "rd" in qs and qs["rd"]:
            return ul.unquote(qs["rd"][0])
        return href
    except Exception:
        return href


def _download(url: str, out_path: str, timeout: int = 25) -> bool:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        with open(out_path, "wb") as f:
            f.write(r.content)
        return True
    except Exception:
        return False


def _launch(playwright, profile_dir: Optional[str], headless: bool = True):
    """
    Returns (browser_or_None, context, page, is_persistent)
    Uses persistent context when profile_dir is provided.
    """
    if profile_dir:
        ctx = playwright.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=headless,
            viewport={"width": 1300, "height": 1100},
            user_agent=HEADERS["user-agent"],
            locale="en-US",
        )
        page = ctx.new_page()
        return None, ctx, page, True
    
    browser = playwright.chromium.launch(headless=headless)
    ctx = browser.new_context(
        viewport={"width": 1300, "height": 1100},
        user_agent=HEADERS["user-agent"],
        locale="en-US",
    )
    page = ctx.new_page()
    return browser, ctx, page, False


def _capture_elements(page, base_dir: str, keyword: str, label: str, css: str, meta: Dict) -> Tuple[int, List[str]]:
    shots: List[str] = []
    loc = page.locator(css)
    count = loc.count()
    for i in range(count):
        item = loc.nth(i)
        try:
            item.scroll_into_view_if_needed()
            time.sleep(0.2)
            out = os.path.join(base_dir, safe_filename(f"{SLUG}_{keyword}_{label}_{i+1}.png"))
            item.screenshot(path=out)
            shots.append(out)
            # attempt to store a landing URL
            try:
                ahref = item.locator("a[href]").first
                if ahref.count() > 0:
                    href = ahref.get_attribute("href") or ""
                    if href:
                        meta.setdefault("links", []).append(_parse_walmart_redirect(href))
            except Exception:
                pass
        except Exception:
            continue
    return count, shots


def _search_url(keyword: str) -> str:
    q = ul.quote_plus(keyword.strip())
    return f"https://www.walmart.com/search?q={q}"


def search_and_capture(
    root_logger,
    activity_cb: Optional[Callable[[str, str], None]],
    base_dir: str,
    keyword: str,
    profile_dir: Optional[str],
    headless: bool = True,
) -> CaptureResult:
    """
    GUI calls this function.
    activity_cb(kind, msg) — kind in {'info','warn','error','success'}
    """
    def say(kind: str, msg: str):
        try:
            if activity_cb:
                activity_cb(kind, msg)
            elif root_logger:
                (root_logger.info if kind != "error" else root_logger.error)(msg)
            else:
                print(f"{kind.upper()}: {msg}")
        except Exception:
            pass
    
    retailer = DISPLAY_NAME
    shots: List[str] = []
    assets: List[str] = []
    meta: Dict = {"links": [], "videos": []}
    html_saved = 0
    
    _ensure_dir(base_dir)
    url = _search_url(keyword)
    
    with sync_playwright() as p:
        browser, ctx, page, persistent = _launch(p, profile_dir, headless=headless)
        try:
            page.set_default_timeout(15000)  # 15s
            say("info", f"[{retailer}] Navigating")
            page.goto(url, wait_until="domcontentloaded")
            
            # Save HTML
            html_path = os.path.join(base_dir, safe_filename(f"{SLUG}_{keyword}_search.html"))
            try:
                content = page.content()
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(content)
                html_saved = 1
                say("info", f"[{retailer}] HTML captured (1/1)")
            except Exception as e:
                say("warn", f"[{retailer}] HTML save failed: {e}")
            
            # 1) Programmatic banners
            n, s = _capture_elements(page, base_dir, keyword, "top_banner", SELECTORS["top_banner"], meta)
            shots.extend(s)
            if n:
                say("info", f"[{retailer}] Top banner found ({n})")
            
            # 2) SBA
            n, s = _capture_elements(page, base_dir, keyword, "sba", SELECTORS["sba"], meta)
            shots.extend(s)
            if n:
                say("info", f"[{retailer}] SBA found ({n})")
            
            # 3) Tile takeover
            n, s = _capture_elements(page, base_dir, keyword, "tile_takeover", SELECTORS["tile_takeover"], meta)
            shots.extend(s)
            if n:
                say("info", f"[{retailer}] Tile takeover found ({n})")
            
            # 4) SBV (screenshot module + attempt mp4 download)
            sbv_mod = page.locator(SELECTORS["sbv"])
            vcount = sbv_mod.count()
            vids_saved = 0
            for i in range(vcount):
                mod = sbv_mod.nth(i)
                try:
                    mod.scroll_into_view_if_needed()
                    time.sleep(0.2)
                    out = os.path.join(base_dir, safe_filename(f"{SLUG}_{keyword}_sbv_{i+1}.png"))
                    mod.screenshot(path=out)
                    shots.append(out)
                    v = mod.locator("video").first
                    if v.count() > 0:
                        src = v.get_attribute("src") or ""
                        if src and src.startswith(("http://", "https://")):
                            vpath = os.path.join(base_dir, safe_filename(f"{SLUG}_{keyword}_sbv_{i+1}.mp4"))
                            if _download(src, vpath):
                                vids_saved += 1
                                assets.append(vpath)
                                meta["videos"].append(vpath)
                except Exception:
                    continue
            if vcount:
                say("info", f"[{retailer}] SBV found (videos {vids_saved})")
            
            # Save meta.json (links/videos)
            try:
                meta_path = os.path.join(base_dir, safe_filename(f"{SLUG}_{keyword}_meta.json"))
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2)
                assets.append(meta_path)
            except Exception:
                pass
        
        finally:
            try:
                ctx.close()
            except Exception:
                pass
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
    
    return CaptureResult(html_saved=html_saved, shots=shots, assets=assets, meta=meta)
