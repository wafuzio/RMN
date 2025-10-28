#!/usr/bin/env python3
"""
Retailer Profiler

Fingerprints a new retailer site to detect:
- Auth requirements
- Bot defense mechanisms
- DOM patterns and selectors
- Lazy-loading behavior
- Ad surface types

Outputs a capability JSON for the Composer to use.
"""
import json, re, sys, time
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, Any, List
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

@dataclass
class RetailerCapabilities:
    retailer_hint: str
    base_url: str
    search_url_shape: str
    requires_auth: bool
    persistent_profile_required: bool
    store_selection_required: bool
    anti_bot_vendor: str
    anti_bot_level: str
    headless_allowed: bool
    data_testid_density: str
    hashed_class_density: str
    has_lazy_loading: bool
    spa_framework: str
    ad_hints: Dict[str, bool]
    notes: List[str]

def density(n: int) -> str:
    if n >= 200: return "high"
    if n >= 50: return "medium"
    return "low"

def sniff_anti_bot(html: str, scripts: List[str]) -> str:
    html_l = html.lower()
    for s in scripts:
        s = s.lower()
        if "perimeterx" in s or "px-captcha" in s or "px.js" in s: return "perimeterx"
        if "akamai" in s or "ak_bmsc" in html_l or "botman" in s: return "akamai"
        if "cloudflare" in s or "cf-chl" in html_l: return "cloudflare"
    return "none"

def detect_spa(html: str) -> str:
    if "__NEXT_DATA__" in html: return "nextjs"
    if "react" in html.lower(): return "react"
    if "vue" in html.lower(): return "vue"
    if "svelte" in html.lower(): return "svelte"
    return "unknown"

def sniff_search_shape(url: str) -> str:
    u = url.lower()
    if "?q=" in u: return "?q="
    if "?query=" in u: return "?query="
    if "/search?" in u or "/search/" in u: return "search_path"
    return "unknown"

def run_profile(base_url: str, keyword: str, profile_dir: str, headed: bool = True) -> RetailerCapabilities:
    notes = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=not headed,
            viewport={"width": 1366, "height": 900},
            ignore_https_errors=True
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            # 1) Home
            page.goto(base_url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(2)

            # Auth/Store heuristics
            requires_auth = False
            persistent_profile_required = False
            store_selection_required = False
            try:
                if page.locator("text=Sign In").first.is_visible():
                    requires_auth = True
            except Exception: pass

            # If this retailer is known to gate ads without login (like Kroger)
            if requires_auth:
                persistent_profile_required = True

            # Store selection heuristic
            try:
                store_selection_required = bool(page.locator("text=Select Store").count())
            except Exception:
                pass

            # 2) Organic search (avoid direct goto when profiling)
            # Click in header input; fallback to direct URL if missing
            input_sel = "input[placeholder*='Search'], input[type='search']"
            did_search = False
            try:
                page.wait_for_selector(input_sel, timeout=5000)
                box = page.locator(input_sel).first
                box.click()
                box.fill(keyword)
                page.keyboard.press("Enter")
                page.wait_for_load_state("domcontentloaded", timeout=30000)
                did_search = True
            except Exception:
                # fallback
                search_url = f"{base_url.rstrip('/')}/search?q={keyword}"
                page.goto(search_url, wait_until="domcontentloaded", timeout=45000)

            time.sleep(3)

            url_after = page.url
            html = page.content()

            # 3) Scripts and signals
            scripts = [s.get_attribute("src") or "" for s in page.locator("script[src]").all()]

            anti = sniff_anti_bot(html, scripts)
            anti_bot_vendor = anti
            anti_bot_level = "low"
            if anti in {"perimeterx", "akamai", "cloudflare"}:
                anti_bot_level = "medium"

            # Headless probe (cheap heuristic): if we were headed and got content; try headless quickly
            headless_allowed = True
            try:
                # minimal headless check (no persistent context)
                hctx = p.chromium.launch(headless=True)
                hpage = hctx.new_page()
                hpage.goto(url_after, wait_until="domcontentloaded", timeout=15000)
                text = hpage.inner_text("body")
                if any(k in text.lower() for k in ["access denied", "captcha", "forbidden"]):
                    headless_allowed = False
                hctx.close()
            except Exception:
                headless_allowed = False

            # 4) DOM heuristics
            testid_count = page.eval_on_selector_all("[data-testid]", "els => els.length") or 0
            data_testid_density = density(testid_count)

            # hashed classes
            class_attrs = page.eval_on_selector_all("[class]", "els => els.map(e => e.className)")
            class_blob = " ".join(class_attrs) if class_attrs else ""
            hashed_hits = len(re.findall(r"\b(sc-[a-zA-Z0-9_-]+|css-[a-zA-Z0-9_-]+|k2-[a-zA-Z0-9_-]+)\b", class_blob))
            hashed_class_density = density(hashed_hits)

            # lazy-loading
            has_lazy_loading = False
            try:
                has_lazy_loading = page.evaluate("() => !!window.IntersectionObserver") or False
            except Exception:
                pass
            if not has_lazy_loading:
                try:
                    lazy_imgs = page.locator("img[loading='lazy']").count()
                    has_lazy_loading = lazy_imgs >= 5
                except Exception:
                    pass

            # SPA detection
            spa_framework = detect_spa(html)

            # 5) Ad surface hints (very rough)
            def has(sel: str, timeout=0):
                try:
                    return page.locator(sel).count() > 0
                except Exception:
                    return False

            ad_hints = {
                "sba_like": has("[data-testid*='sba']") or "sba" in html.lower(),
                "tile_takeover_like": has("[data-testid*='tile']") or "tile-take" in html.lower(),
                "video_in_grid_like": has("[data-testid*='video']") or "sbv" in html.lower(),
                "curated_carousel_like": has("div.CuratedCarousel") or "carousel" in html.lower(),
                "toa_like": has("div[data-testid='StandardTOA']") or "toa" in html.lower(),
                "skyscraper_like": has("div[data-testid*='skyscraper']") or "skyscraper" in html.lower(),
            }

            search_url_shape = sniff_search_shape(url_after)

            # Construct capability result
            caps = RetailerCapabilities(
                retailer_hint=base_url.split("//")[-1].split("/")[0].replace("www.", ""),
                base_url=base_url,
                search_url_shape=search_url_shape,
                requires_auth=requires_auth,
                persistent_profile_required=persistent_profile_required,
                store_selection_required=store_selection_required,
                anti_bot_vendor=anti_bot_vendor,
                anti_bot_level=anti_bot_level,
                headless_allowed=headless_allowed,
                data_testid_density=data_testid_density,
                hashed_class_density=hashed_class_density,
                has_lazy_loading=has_lazy_loading,
                spa_framework=spa_framework,
                ad_hints=ad_hints,
                notes=notes
            )
            ctx.close()
            return caps
        except PWTimeout as e:
            notes.append(f"timeout:{e}")
            ctx.close()
            return RetailerCapabilities(
                retailer_hint=base_url, base_url=base_url, search_url_shape="unknown",
                requires_auth=False, persistent_profile_required=False, store_selection_required=False,
                anti_bot_vendor="unknown", anti_bot_level="low", headless_allowed=True,
                data_testid_density="low", hashed_class_density="low", has_lazy_loading=False,
                spa_framework="unknown", ad_hints={}, notes=notes
            )

if __name__ == "__main__":
    import argparse, os
    ap = argparse.ArgumentParser(description="Profile a retailer site for scraper composition")
    ap.add_argument("--url", required=True, help="Retailer base URL, e.g., https://www.example.com")
    ap.add_argument("--keyword", default="milk", help="Test search keyword")
    ap.add_argument("--profile-dir", required=True, help="Persistent profile directory for auth")
    ap.add_argument("--out", default="profiles/newretailer_profile.json", help="Output JSON path")
    args = ap.parse_args()

    print(f"🔍 Profiling {args.url}...")
    caps = run_profile(args.url, args.keyword, args.profile_dir, headed=True)
    
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(asdict(caps), indent=2))
    
    print(f"\n✅ Profile saved to: {args.out}")
    print(f"\n📊 Capabilities detected:")
    print(f"   Auth required: {caps.requires_auth}")
    print(f"   Anti-bot: {caps.anti_bot_vendor} ({caps.anti_bot_level})")
    print(f"   Headless allowed: {caps.headless_allowed}")
    print(f"   Lazy loading: {caps.has_lazy_loading}")
    print(f"   Ad types detected: {', '.join([k for k, v in caps.ad_hints.items() if v])}")
