#!/usr/bin/env python3
"""Amazon Search and Capture Script (Modern Pattern)

Performs Amazon keyword search and captures assets during search:
- Main full-page screenshot
- Sponsored Brand Video (SBV) module screenshot (+ optional MP4)
- Sponsored Carousels (container-level screenshots)
- Sponsored Products aggregation with ASIN main image downloads

Outputs canonical JSON with flat ads[] array and saves HTML.
"""

import os
import json
import urllib.parse
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright
from browser_lock import single_browser_lock
import requests
import shutil
import hashlib
import re
import time
from core.brands import canonicalize

# Optional helpers with safe fallbacks
try:
    from retailers.amazon.helpers import (
        accept_amazon_cookies,
        ensure_amazon_logged_in,
        scroll_results,
        goto_with_retries,
    )
except Exception:
    def accept_amazon_cookies(page):
        try:
            page.click('input[name="accept"], button:has-text("Accept")', timeout=2000)
        except Exception:
            pass
    def ensure_amazon_logged_in(page):
        pass
    def scroll_results(page, max_loops=8, step_ratio=0.6, sleep_ms=300):
        for _ in range(max_loops):
            try:
                page.evaluate('window.scrollBy(0, window.innerHeight * 0.6)')
            except Exception:
                break
            try:
                time.sleep(max(0, float(sleep_ms) / 1000.0))
            except Exception:
                pass
    def goto_with_retries(page, url, attempts=3, wait_until="domcontentloaded", timeout_ms=45000):
        last_err = None
        for _ in range(attempts):
            try:
                page.goto(url, wait_until=wait_until, timeout=timeout_ms)
                return
            except Exception as e:
                last_err = e
                try:
                    time.sleep(1)
                except Exception:
                    pass
        if last_err:
            raise last_err

CAROUSEL_HEADINGS = [
    "Brands related to your search",
    "Shoppers also explored",
    "Trending now",
    "Popular products in this category",
    "Customers who viewed this item also viewed",
]


def _slug(text: str) -> str:
    s = (text or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "unknown"


def _short_hash(s: str) -> str:
    try:
        return hashlib.md5((s or "").encode("utf-8")).hexdigest()[:8]
    except Exception:
        return "00000000"


def _first_nonempty(*vals):
    for v in vals:
        if v:
            return v
    return None


def _get_attr(locator, name: str):
    try:
        return locator.get_attribute(name)
    except Exception:
        return None


def _module_anchor(locator):
    # Prefer cel_widget_id then data-uuid then data-aid then data-cel-widget
    return _first_nonempty(
        _get_attr(locator, "cel_widget_id"),
        _get_attr(locator, "data-uuid"),
        _get_attr(locator, "data-aid"),
        _get_attr(locator, "data-cel-widget"),
    ) or "unknown"


def _extract_brand_and_message(container):
    brand = None
    message = None
    # Try aria-labels that include brand references
    try:
        al = container.locator('a[aria-label]')
        if al.count() > 0:
            label = (al.first.get_attribute('aria-label') or '').strip()
            # Common pattern: Sponsored ad from <Brand>.
            m = re.search(r"from\s+([^\.\"]+)", label, re.IGNORECASE)
            if m:
                brand = m.group(1).strip()
            if not message:
                message = label
    except Exception:
        pass
    # Try logo alt
    if not brand:
        try:
            logo = container.locator('img[alt]').first
            if logo.count() > 0:
                alt = (logo.get_attribute('alt') or '').strip()
                # Heuristic: short alts likely brand names
                if 1 <= len(alt.split()) <= 4:
                    brand = alt
        except Exception:
            pass
    # Try headline text as message/brand source
    try:
        head = container.locator('a[data-elementid="sb-headline"], h2').first
        if head.count() > 0:
            ht = (head.text_content() or '').strip()
            if ht:
                message = message or ht
                # Extract brand from "Shop <Brand>" pattern
                m2 = re.search(r"Shop\s+([^|\n\r]+)$", ht)
                if m2 and not brand:
                    brand = m2.group(1).strip()
    except Exception:
        pass
    # Canonicalize brand
    brand_canon = None
    try:
        if brand:
            brand_canon = canonicalize(brand)
    except Exception:
        brand_canon = None
    return brand, brand_canon, (message or "")


def _build_ids(retailer_type: str, subtype: str, brand_canon: str, anchor: str, run_id: str, pos: int = 0):
    sub = _slug(subtype)
    bc = _slug(brand_canon or "unknown")
    anch = _slug(anchor)
    module_id = f"amazon::{_slug(retailer_type)}::{sub}::{bc}::{anch}"
    eid = f"amazon::{run_id}::{_short_hash(module_id)}::{pos}"
    return module_id, eid


def _search_url(keyword: str, page: int = 1) -> str:
    base = "https://www.amazon.com/s"
    return f"{base}?{urllib.parse.urlencode({'k': keyword, 'page': page})}"


def _std_filename(retailer: str, advertiser: str, ad_type: str, client: str, keyword: str, run_id: str, index: int, ext: str) -> str:
    r = (retailer or "").strip().lower().replace(" ", "_")
    adv = (advertiser or "unknown").strip().lower().replace(" ", "_") or "unknown"
    typ = (ad_type or "").strip().replace(" ", "_")
    cli = (client or "").strip().lower().replace(" ", "_")
    kw = (keyword or "").strip().lower().replace(" ", "_")
    try:
        dt = datetime.strptime(run_id, "%Y%m%d%H%M%S")
    except Exception:
        dt = datetime.utcnow()
    d = dt.strftime("D%Y-%m-%d")
    tstr = dt.strftime("T%H-%M.%S")
    return f"{r}__{adv}__{typ}__{cli}__{kw}__{d}_{tstr}_{index}{ext}"


def search_and_capture(keyword: str, output_dir: str) -> bool:
    print("\n==================================================")
    print("AMAZON SEARCH AND CAPTURE")
    print("==================================================")
    print(f"Keyword: {keyword}")
    print(f"Output directory: {output_dir}")

    profile_dir = os.environ.get("AMAZON_PROFILE_DIR") or os.path.expanduser("~/ChromeProfiles/amazon")
    try:
        os.makedirs(profile_dir, exist_ok=True)
    except Exception as e:
        print(f"❌ Could not prepare profile dir {profile_dir}: {e}")
        return False
    print(f"Using profile: {profile_dir}")

    client = os.path.basename(output_dir.rstrip('/')) or "unknown"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = datetime.now().strftime("%Y%m%d%H%M%S")
    runs_dir = os.path.join(output_dir, "runs")
    os.makedirs(runs_dir, exist_ok=True)

    html_path = os.path.join(runs_dir, f"search_results_amazon_{client}_{ts}.html")
    json_path = os.path.join(runs_dir, f"run_results_amazon_{client}_{ts}.json")
    debug_log = os.path.join(runs_dir, f"capture_debug_{ts}.log")
    project_root = Path(__file__).resolve().parent
    central_asin_dir = project_root / "assets" / "amazon" / "ASIN_Images"
    try:
        central_asin_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    def log(msg: str):
        print(msg)
        try:
            with open(debug_log, 'a', encoding='utf-8') as f:
                f.write(f"{datetime.now().isoformat()} {msg}\n")
        except Exception:
            pass

    log("bootstrap: start")

    ads = []
    captured_modules = set()
    seen_anchors = set()
    success = False

    # Performance controls and time budget
    BUDGET_SEC = int(os.environ.get("AMAZON_BUDGET_SEC", "120"))
    MAX_SP = int(os.environ.get("AMAZON_MAX_SP", "12"))
    MAX_CAR = int(os.environ.get("AMAZON_MAX_CAR", "1"))
    MAX_LEFT_DISPLAY = int(os.environ.get("AMAZON_MAX_LEFT_DISPLAY", "2"))
    MAX_BOTTOM_DISPLAY = int(os.environ.get("AMAZON_MAX_BOTTOM_DISPLAY", "2"))
    deadline = time.time() + BUDGET_SEC
    def time_left():
        try:
            return max(0, deadline - time.time())
        except Exception:
            return 0

    with single_browser_lock(timeout=600):
        p = sync_playwright().start()
        bctx = None
        try:
            try:
                bctx = p.chromium.launch_persistent_context(
                    user_data_dir=profile_dir,
                    channel="chrome",
                    headless=False,
                    viewport={"width": 1400, "height": 900},
                    locale="en-US",
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-default-browser-check",
                        "--disable-features=IsolateOrigins,site-per-process",
                    ],
                )
            except Exception as e:
                log(f"launch: chrome channel failed -> {e}; retry with default chromium")
                bctx = p.chromium.launch_persistent_context(
                    user_data_dir=profile_dir,
                    headless=False,
                    viewport={"width": 1400, "height": 900},
                    locale="en-US",
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-default-browser-check",
                        "--disable-features=IsolateOrigins,site-per-process",
                    ],
                )
            page = bctx.new_page()

            # Wire minimal browser events (avoid noisy response logs)
            try:
                page.on("console", lambda m: log(f"[console:{m.type()}] {m.text()}"))
                page.on("pageerror", lambda e: log(f"[pageerror] {e}"))
                page.on("requestfailed", lambda r: log(f"[requestfailed] {r.method()} {r.url}"))
            except Exception:
                pass

            # Start tracing only if enabled
            try:
                if os.environ.get("AMAZON_TRACE") == "1":
                    bctx.tracing.start(screenshots=True, snapshots=True, sources=False)
            except Exception:
                pass

            url = _search_url(keyword)
            log(f"navigate: {url}")
            goto_with_retries(page, url, attempts=3, wait_until="domcontentloaded", timeout_ms=45000)

            log("cookies/login")
            accept_amazon_cookies(page)
            ensure_amazon_logged_in(page)

            # Wait readiness heuristics
            try:
                page.wait_for_selector('div[data-component-type="s-search-result"]', timeout=8000)
                log("ready: s-search-result present")
            except Exception as e:
                log(f"ready: timeout waiting for results -> {e}")
                try:
                    time.sleep(3)
                except Exception:
                    pass

            log("scrolling")
            try:
                page.evaluate("""
                  () => new Promise((resolve) => {
                    const sleep = (ms) => new Promise(r => setTimeout(r, ms));
                    (async () => {
                      let stable = 0; let last = 0;
                      for (let i=0; i<12 && stable<3; i++) {
                        const imgs = document.querySelectorAll('img');
                        const loaded = Array.from(imgs).filter(i => i.complete && i.naturalWidth > 10).length;
                        if (loaded === last) stable++; else stable = 0;
                        last = loaded; await sleep(600);
                      }
                      resolve(true);
                    })()
                  })
                """)
                log("scrolling: bottom images settled")
            except Exception as e:
                log(f"scrolling: settle error -> {e}")

            # Create output folders
            for folder in [
                "Main",
                "Sponsored_Brand_Video",
                "Sponsored_Brand",
                "Sponsored_Carousel",
                "Sponsored_Display",
                "ASIN_Images",
            ]:
                os.makedirs(os.path.join(output_dir, folder), exist_ok=True)

            # 1) Main full-page screenshot (hide sticky headers before capture)
            try:
                log("main: prepare (hide sticky headers, scroll top)")
                # Hide Amazon sticky headers/navs to avoid covering content (fast inline style injection)
                try:
                    page.evaluate(
                        """
                        (() => {
                          try {
                            const css = `#navbar,#nav-belt,#nav-main,#nav-progressive-subnav,header,[data-testid="header"],[class*="sticky" i],[data-sticky],[style*="position: sticky"],.sg-col-20-of-24 .s-desktop-width-max .s-desktop-toolbar,.s-desktop-toolbar .s-desktop-toolbar,.s-main-slot .s-no-outline .a-section.s-include-content-margin.s-border-bottom{display:none!important;visibility:hidden!important;}`;
                            const st = document.createElement('style');
                            st.type = 'text/css';
                            st.textContent = css;
                            document.head.appendChild(st);
                          } catch(e) {}
                          return true;
                        })()
                        """
                    )
                except Exception as css_err:
                    log(f"main: style inject error -> {css_err}")
                # Ensure we are at the very top for consistent full-page shot
                try:
                    page.evaluate("window.scrollTo(0, 0)")
                    try:
                        time.sleep(0.3)
                    except Exception:
                        pass
                except Exception:
                    pass
                log("main: screenshot")
                main_name = _std_filename("amazon", "unknown", "Main", client, keyword, run_id, 0, ".png")
                main_path = os.path.join(output_dir, "Main", main_name)
                page.screenshot(path=main_path, full_page=True)
                log(f"main: saved -> {main_path} exists={os.path.exists(main_path)} size={os.path.getsize(main_path) if os.path.exists(main_path) else 0}")
            except Exception as e:
                log(f"main: fail -> {e}")

            # 2) Sponsored Brand Video (SBV)
            try:
                log("sbv: detect")
                # SBV has cel_widget_id containing "VIDEO_SINGLE_PRODUCT"
                sbv_root = page.locator('div[cel_widget_id*="VIDEO_SINGLE_PRODUCT"]').first
                if sbv_root.count() > 0 and sbv_root.is_visible():
                    log(f"sbv: found VIDEO_SINGLE_PRODUCT widget")
                    # Brand and message
                    brand_txt, brand_canon, message = _extract_brand_and_message(sbv_root)
                    adv_for_name = brand_canon or "unknown"
                    fname = _std_filename("amazon", adv_for_name, "Sponsored_Brand_Video", client, keyword, run_id, 0, ".png")
                    fpath = os.path.join(output_dir, "Sponsored_Brand_Video", fname)
                    try:
                        # Hide sticky headers before SBV screenshot (same as main and other ad types)
                        try:
                            page.evaluate(
                                """
                                (() => {
                                  try {
                                    const css = `#navbar,#nav-belt,#nav-main,#nav-progressive-subnav,header,[data-testid="header"],[class*="sticky" i],[data-sticky],[style*="position: sticky"],.sg-col-20-of-24 .s-desktop-width-max .s-desktop-toolbar,.s-desktop-toolbar .s-desktop-toolbar,.s-main-slot .s-no-outline .a-section.s-include-content-margin.s-border-bottom{display:none!important;visibility:hidden!important;}`;
                                    const st = document.createElement('style');
                                    st.type = 'text/css';
                                    st.textContent = css;
                                    document.head.appendChild(st);
                                  } catch(e) {}
                                  return true;
                                })()
                                """
                            )
                        except Exception as css_err:
                            log(f"sbv: style inject error -> {css_err}")
                        # Scroll SBV into view and wait
                        try:
                            sbv_root.scroll_into_view_if_needed()
                            time.sleep(0.2)
                        except Exception:
                            pass
                        # Freeze animations (like other ad types)
                        try:
                            page.evaluate("""
                                () => {
                                    const style = document.createElement('style');
                                    style.textContent = '* { transition: none !important; animation: none !important; }';
                                    document.head.appendChild(style);
                                }
                            """)
                        except Exception:
                            pass
                        # Flush layout
                        try:
                            page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
                        except Exception:
                            pass
                        sbv_root.screenshot(path=fpath, timeout=5000)
                        log(f"sbv: saved -> {fpath} exists={os.path.exists(fpath)}")
                        video_rel = None
                        try:
                            sources = []
                            try:
                                sources += [s.get_attribute('src') for s in sbv_root.locator('video source').element_handles()]
                            except Exception:
                                pass
                            try:
                                v = sbv_root.locator('video').first
                                if v.count() > 0:
                                    s = v.get_attribute('src')
                                    if s:
                                        sources.append(s)
                            except Exception:
                                pass
                            try:
                                dv = sbv_root.get_attribute('data-video-url')
                                if dv:
                                    sources.append(dv)
                            except Exception:
                                pass
                            sources = [u for u in (sources or []) if u]
                            mp4 = next((u for u in sources if '.mp4' in u.lower()), None)
                            if mp4:
                                mp4_name = os.path.splitext(fname)[0] + ".mp4"
                                mp4_path = os.path.join(output_dir, "Sponsored_Brand_Video", mp4_name)
                                r = requests.get(mp4, timeout=10)
                                if r.ok:
                                    with open(mp4_path, "wb") as vf:
                                        vf.write(r.content)
                                    video_rel = f"Sponsored_Brand_Video/{mp4_name}"
                                    log(f"sbv: mp4 saved -> {mp4_path}")
                        except Exception as e:
                            log(f"sbv: mp4 error -> {e}")
                        # IDs
                        anchor = _module_anchor(sbv_root)
                        if anchor in seen_anchors:
                            log(f"sbv: duplicate anchor skipped -> {anchor}")
                        else:
                            seen_anchors.add(anchor)
                            module_id, eid = _build_ids("Sponsored_Brand_Video", "Video_Single_Product", brand_canon, anchor, run_id, 0)
                            ads.append({
                                "id": eid,
                                "module_id": module_id,
                                "type": "Sponsored_Brand_Video",
                                "subtype": "Video_Single_Product",
                                "brand": brand_txt or "Unknown",
                                "brand_canonical": brand_canon,
                                "advertisers": [brand_canon] if brand_canon else [],
                                "image_path": f"Sponsored_Brand_Video/{fname}",
                                "video_path": video_rel,
                                "message": message,
                                "metadata": {},
                            })
                        log(f"sbv: ad added {fname} module_id={module_id}")
                    except Exception as e:
                        log(f"sbv: screenshot fail -> {e}")
                else:
                    log("sbv: none")
            except Exception as e:
                log(f"sbv: detect error -> {e}")

            # 3) Carousels ("Brands related to your search")
            try:
                log("car: detect")
                car_idx = 0
                for heading in CAROUSEL_HEADINGS:
                    # Amazon uses span[role=heading] for these carousels, not h2
                    h = page.locator(f"span[role=heading]:has-text(\"{heading}\")").first
                    if h.count() == 0 or not h.is_visible():
                        # Fallback: try h2 variants
                        h = page.locator(f"h2:has-text(\"{heading}\")").first
                        if h.count() == 0 or not h.is_visible():
                            h = page.locator(f"h2 span:has-text(\"{heading}\")").first
                            if h.count() == 0 or not h.is_visible():
                                log(f"car: heading not found -> {heading}")
                                continue
                    # Budget check
                    if time_left() < 20:
                        log("car: budget low, break")
                        break
                    log(f"car: found heading -> {heading}")
                    container_el = None
                    try:
                        # Scroll heading into view first (Instacart pattern)
                        try:
                            h.scroll_into_view_if_needed()
                            time.sleep(0.1)
                        except Exception:
                            pass
                        
                        heading_el = h.element_handle()
                        handle = page.evaluate_handle(
                            """(el) => {
                                let n = el;
                                const enough = (node) => {
                                    try {
                                        const imgs = node.querySelectorAll('img.s-image').length;
                                        const cards = node.querySelectorAll('div[data-component-type=\"s-search-result\"]').length;
                                        return imgs >= 8 || cards >= 8;
                                    } catch(e) { return false; }
                                };
                                while (n && n.parentElement) {
                                    if (enough(n)) return n;
                                    n = n.parentElement;
                                }
                                return el;
                            }""",
                            heading_el,
                        )
                        container_el = handle.as_element()
                    except Exception:
                        container_el = None

                    # Products inside carousel
                    products = []
                    try:
                        # Define root element for product extraction
                        root_el = container_el if container_el else h.locator("xpath=ancestor::div[1]")
                        try:
                            root_el.scroll_into_view_if_needed()
                            time.sleep(0.2)
                        except Exception:
                            pass
                        try:
                            el_handle = root_el.element_handle()
                            page.evaluate(el_handle, """
                              (el) => new Promise((resolve) => {
                                const sleep = (ms) => new Promise(r => setTimeout(r, ms));
                                (async () => {
                                  let stable = 0; let last = 0;
                                  for (let i=0; i<6 && stable<2; i++) {
                                    const imgs = Array.from(el.querySelectorAll('img')).filter(i => i.complete && i.naturalWidth > 10).length;
                                    if (imgs === last) stable++; else stable = 0;
                                    last = imgs; await sleep(300);
                                  }
                                  resolve(true);
                                })()
                              })
                            """)
                        except Exception:
                            pass
                        cards = root_el.locator('div[data-asin]')
                        cnt = min(cards.count(), 24)
                        for i in range(cnt):
                            c = cards.nth(i)
                            asin = _get_attr(c, 'data-asin') or None
                            title = None
                            href = None
                            image_url = None
                            image_path = None
                            central_image_path = None
                            price_text = None
                            try:
                                a = c.locator('h2 a, a.a-link-normal').first
                                if a.count() > 0:
                                    href = a.get_attribute('href')
                                    if href and not href.startswith('http'):
                                        href = f"https://www.amazon.com{href}"
                            except Exception:
                                pass
                            try:
                                title = (c.locator('h2 a span').first.text_content() or '').strip()
                            except Exception:
                                pass
                            try:
                                img = c.locator('img.s-image').first
                                if img.count() > 0:
                                    src = img.get_attribute('src')
                                    if src and src.startswith('http'):
                                        image_url = src
                                        try:
                                            from urllib.parse import urlparse
                                            ext = os.path.splitext(urlparse(src).path)[1] or ".jpg"
                                        except Exception:
                                            ext = ".jpg"
                                        file_name = (asin or f"car_{car_idx}_{i}") + ext
                                        central_full = central_asin_dir / file_name
                                        try:
                                            r = requests.get(src, timeout=10)
                                            if r.ok:
                                                with open(central_full, 'wb') as fimg:
                                                    fimg.write(r.content)
                                                image_path = str(central_full.relative_to(project_root))
                                                try:
                                                    client_full = os.path.join(output_dir, "ASIN_Images", file_name)
                                                    if not os.path.exists(client_full):
                                                        shutil.copyfile(central_full, client_full)
                                                except Exception:
                                                    pass
                                        except Exception:
                                            pass
                            except Exception:
                                pass
                            try:
                                price_text = (c.locator('span.a-price .a-offscreen').first.text_content() or '').strip()
                            except Exception:
                                pass
                            if any([asin, title, href, image_url]):
                                products.append({
                                    "asin": asin,
                                    "href": href,
                                    "title": title,
                                    "image_url": image_url,
                                    "image_path": image_path,
                                    "central_image_path": image_path,
                                    "price": price_text,
                                })
                    except Exception as e:
                        log(f"car: products parse error -> {e}")

                    # Brand and message (if any) with classification & dedupe
                    root_loc = root_el if container_el else h.locator("xpath=ancestor::div[1]")
                    brand_txt, brand_canon, message = _extract_brand_and_message(root_loc)
                    anchor = _module_anchor(root_loc)
                    if anchor in seen_anchors:
                        log(f"car: duplicate anchor skipped -> {anchor}")
                        continue
                    seen_anchors.add(anchor)
                    is_sb = bool(re.match(r'^(sb|sponsoredb|sponsoredbrands)', (anchor or '').lower()))
                    adv_for_name = brand_canon or "unknown"
                    ad_type = "Sponsored_Brand" if is_sb else "Sponsored_Carousel"
                    folder = "Sponsored_Brand" if is_sb else "Sponsored_Carousel"
                    fname = _std_filename("amazon", adv_for_name, ad_type, client, keyword, run_id, car_idx, ".png")
                    fpath = os.path.join(output_dir, folder, fname)
                    try:
                        try:
                            root_loc.scroll_into_view_if_needed()
                            time.sleep(0.2)
                        except Exception:
                            pass
                        try:
                            el_handle = root_loc.element_handle()
                            page.evaluate(el_handle, """
                              (el) => new Promise((resolve) => {
                                const sleep = (ms) => new Promise(r => setTimeout(r, ms));
                                (async () => {
                                  let stable = 0; let last = 0;
                                  for (let i=0; i<6 && stable<2; i++) {
                                    const imgs = Array.from(el.querySelectorAll('img')).filter(img => img.complete && img.naturalWidth>10).length;
                                    if (imgs === last) stable++; else stable = 0;
                                    last = imgs; await sleep(300);
                                  }
                                  resolve(true);
                                })
                              })
                            """)
                        except Exception:
                            pass
                        try:
                            page.evaluate("""
                                () => {
                                    const style = document.createElement('style');
                                    style.textContent = '* { transition: none !important; animation: none !important; }';
                                    document.head.appendChild(style);
                                }
                            """)
                        except Exception:
                            pass
                        try:
                            page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
                        except Exception:
                            pass
                        root_loc.screenshot(path=fpath, timeout=4000)
                        module_id, eid = _build_ids(ad_type, heading, brand_canon, anchor, run_id, car_idx)
                        if module_id in captured_modules:
                            log(f"car: duplicate module skipped -> {module_id}")
                        else:
                            captured_modules.add(module_id)
                            ads.append({
                                "id": eid,
                                "module_id": module_id,
                                "type": ad_type,
                                "subtype": heading,
                                "brand": brand_txt or "Unknown",
                                "brand_canonical": brand_canon,
                                "advertisers": [brand_canon] if brand_canon else [],
                                "header": heading,
                                "products": products,
                                "capture_entire_carousel": True,
                                "position": car_idx + 1,
                                "image_path": f"{folder}/{fname}",
                                "video_path": None,
                                "message": message,
                                "metadata": {"subtype": heading, "count": len(products)},
                            })
                        log(f"car: saved -> {fpath} exists={os.path.exists(fpath)} module_id={module_id}")
                        car_idx += 1
                        if car_idx >= MAX_CAR:
                            log("car: reached MAX_CAR, stop")
                            break
                    except Exception as e:
                        log(f"car: screenshot fail -> {e}")
            except Exception as e:
                log(f"car: detect error -> {e}")

            # 3b) Sponsored Brand Themed Collections (direct detection)
            try:
                log("sb-themed: detect")
                themed = page.locator('div[cel_widget_id^="sb-themed-collection-"]')
                tcount = themed.count()
                for i in range(tcount):
                    if time_left() < 15:
                        log("sb-themed: budget low, break")
                        break
                    el = themed.nth(i)
                    if not el.is_visible():
                        continue
                    brand_txt, brand_canon, message = _extract_brand_and_message(el)
                    subtype = "Top" if "top-slot" in (_get_attr(el, 'cel_widget_id') or '') else "Inline"
                    adv_for_name = brand_canon or "unknown"
                    fname = _std_filename("amazon", adv_for_name, "Sponsored_Brand", client, keyword, run_id, i, ".png")
                    fpath = os.path.join(output_dir, "Sponsored_Brand", fname)
                    try:
                        try:
                            el.scroll_into_view_if_needed()
                            time.sleep(0.2)
                        except Exception:
                            pass
                        try:
                            el_handle = el.element_handle()
                            page.evaluate(el_handle, """
                              (el) => new Promise((resolve) => {
                                const sleep = (ms) => new Promise(r => setTimeout(r, ms));
                                (async () => {
                                  let stable = 0; let last = 0;
                                  for (let i=0; i<6 && stable<2; i++) {
                                    const imgs = Array.from(el.querySelectorAll('img')).filter(img => img.complete && img.naturalWidth>10).length;
                                    if (imgs === last) stable++; else stable = 0;
                                    last = imgs; await sleep(300);
                                  }
                                  resolve(true);
                                })
                              })
                            """)
                        except Exception:
                            pass
                        try:
                            page.evaluate("""
                                () => {
                                    const style = document.createElement('style');
                                    style.textContent = '* { transition: none !important; animation: none !important; }';
                                    document.head.appendChild(style);
                                }
                            """)
                        except Exception:
                            pass
                        try:
                            page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
                        except Exception:
                            pass
                        el.screenshot(path=fpath, timeout=4000)
                        anchor = _module_anchor(el)
                        if anchor in seen_anchors:
                            log(f"sb-themed: duplicate anchor skipped -> {anchor}")
                            continue
                        seen_anchors.add(anchor)
                        module_id, eid = _build_ids("Sponsored_Brand", f"Themed_Collection_{subtype}", brand_canon, anchor, run_id, i)
                        if module_id in captured_modules:
                            log(f"sb-themed: duplicate module skipped -> {module_id}")
                            continue
                        captured_modules.add(module_id)
                        # Products
                        products = []
                        cards = el.locator('div[data-asin]')
                        cnt = min(cards.count(), 24)
                        for j in range(cnt):
                            c = cards.nth(j)
                            asin = _get_attr(c, 'data-asin') or None
                            title = None
                            href = None
                            image_url = None
                            image_path = None
                            central_image_path = None
                            price_text = None
                            try:
                                a = c.locator('h2 a, a.a-link-normal').first
                                if a.count() > 0:
                                    href = a.get_attribute('href')
                                    if href and not href.startswith('http'):
                                        href = f"https://www.amazon.com{href}"
                            except Exception:
                                pass
                            try:
                                title = (c.locator('h2 a span').first.text_content() or '').strip()
                            except Exception:
                                pass
                            try:
                                img = c.locator('img.s-image').first
                                if img.count() > 0:
                                    src = img.get_attribute('src')
                                    if src and src.startswith('http'):
                                        image_url = src
                                        try:
                                            from urllib.parse import urlparse
                                            ext = os.path.splitext(urlparse(src).path)[1] or ".jpg"
                                        except Exception:
                                            ext = ".jpg"
                                        file_name = (asin or f"tc_{i}_{j}") + ext
                                        central_full = central_asin_dir / file_name
                                        try:
                                            r = requests.get(src, timeout=10)
                                            if r.ok:
                                                with open(central_full, 'wb') as fimg:
                                                    fimg.write(r.content)
                                                image_path = str(central_full.relative_to(project_root))
                                                try:
                                                    client_full = os.path.join(output_dir, "ASIN_Images", file_name)
                                                    if not os.path.exists(client_full):
                                                        shutil.copyfile(central_full, client_full)
                                                except Exception:
                                                    pass
                                        except Exception:
                                            pass
                            except Exception:
                                pass
                            try:
                                price_text = (c.locator('span.a-price .a-offscreen').first.text_content() or '').strip()
                            except Exception:
                                pass
                            if any([asin, title, href, image_url]):
                                products.append({
                                    "asin": asin,
                                    "href": href,
                                    "title": title,
                                    "image_url": image_url,
                                    "image_path": image_path,
                                    "central_image_path": central_image_path,
                                    "price": price_text,
                                })
                        ads.append({
                            "id": eid,
                            "module_id": module_id,
                            "type": "Sponsored_Brand",
                            "subtype": f"Themed_Collection_{subtype}",
                            "brand": brand_txt or "Unknown",
                            "brand_canonical": brand_canon,
                            "advertisers": [brand_canon] if brand_canon else [],
                            "header": message,
                            "products": products,
                            "capture_entire_carousel": True,
                            "position": i + 1,
                            "image_path": f"Sponsored_Brand/{fname}",
                            "video_path": None,
                            "message": message,
                            "metadata": {"count": len(products)},
                        })
                        log(f"sb-themed: saved -> {fpath} module_id={module_id}")
                    except Exception as e:
                        log(f"sb-themed: screenshot fail -> {e}")
            except Exception as e:
                log(f"sb-themed: detect error -> {e}")

            # 3c) Sponsored Display (Left rail / Bottom)
            # Left rail: .s-left-ads-item contains the outer wrapper, but the ad is .AdHolder inside it
            try:
                log("display: detect left rail")
                # Select the actual AdHolder inside left rail containers
                left_ads = page.locator('div.s-left-ads-item div.AdHolder')
                lcount = min(left_ads.count(), MAX_LEFT_DISPLAY)
                log(f"display: left rail found {lcount} ads")
                for i in range(lcount):
                    el = left_ads.nth(i)
                    if not el.is_visible():
                        continue
                    # Instacart-style scroll and freeze
                    try:
                        el.scroll_into_view_if_needed()
                        time.sleep(0.1)
                    except Exception:
                        pass
                    try:
                        el.evaluate("""
                          (el) => new Promise(async (resolve) => {
                            const sleep = (ms) => new Promise(r => setTimeout(r, ms));
                            let stable = 0, last = 0;
                            for (let i=0; i<8 && stable<3; i++) {
                              const imgs = Array.from(el.querySelectorAll('img')).filter(i => i.complete && i.naturalWidth > 10).length;
                              if (imgs === last) stable++; else stable = 0;
                              last = imgs; await sleep(300);
                            }
                            resolve(true);
                          })
                        """)
                    except Exception:
                        pass
                    try:
                        if left_ads.nth(i).locator('img').count() == 0:
                            log("display: left skipped (no images)")
                            continue
                    except Exception:
                        pass
                    brand_txt, brand_canon, message = _extract_brand_and_message(el)
                    adv_for_name = brand_canon or "unknown"
                    fname = _std_filename("amazon", adv_for_name, "Sponsored_Display", client, keyword, run_id, i, ".png")
                    fpath = os.path.join(output_dir, "Sponsored_Display", fname)
                    try:
                        # Freeze animations (Instacart pattern)
                        try:
                            page.evaluate("""
                                () => {
                                    const style = document.createElement('style');
                                    style.textContent = '* { transition: none !important; animation: none !important; }';
                                    document.head.appendChild(style);
                                }
                            """)
                        except Exception:
                            pass
                        # Flush layout
                        try:
                            page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
                        except Exception:
                            pass
                        el.screenshot(path=fpath, timeout=4000)
                        anchor = _module_anchor(el)
                        if re.match(r'^(sb|sponsoredb|sponsoredbrands)', (anchor or '').lower()):
                            log(f"display: skip sb-like anchor -> {anchor}")
                            continue
                        module_id, eid = _build_ids("Sponsored_Display", "Left_Rail_Display", brand_canon, anchor, run_id, i)
                        if anchor in seen_anchors:
                            log(f"display: left duplicate anchor skipped -> {anchor}")
                            continue
                        seen_anchors.add(anchor)
                        if module_id in captured_modules:
                            log(f"display: left duplicate module skipped -> {module_id}")
                            continue
                        captured_modules.add(module_id)
                        ads.append({
                            "id": eid,
                            "module_id": module_id,
                            "type": "Sponsored_Display",
                            "subtype": "Left_Rail_Display",
                            "brand": brand_txt or "Unknown",
                            "brand_canonical": brand_canon,
                            "advertisers": [brand_canon] if brand_canon else [],
                            "image_path": f"Sponsored_Display/{fname}",
                            "video_path": None,
                            "message": message,
                            "metadata": {},
                        })
                        log(f"display: left saved -> {fpath} module_id={module_id}")
                    except Exception as e:
                        log(f"display: left screenshot fail -> {e}")
            except Exception as e:
                log(f"display: left detect error -> {e}")

            try:
                log("display: detect bottom")
                # Bottom ads: AdHolder that is NOT inside .s-left-ads-item AND NOT a Sponsored Brand themed collection
                # Exclude: left rail, Sponsored Brand themed collections, in-grid sponsored products
                all_adholders = page.locator('div.AdHolder')
                bottom_ads = []
                for i in range(all_adholders.count()):
                    ad = all_adholders.nth(i)
                    # Skip if inside left rail
                    try:
                        parent_left = ad.locator('xpath=ancestor::div[contains(@class, "s-left-ads-item")]')
                        if parent_left.count() > 0:
                            continue
                    except Exception:
                        pass
                    # Skip if inside Sponsored Brand themed collection (has cel_widget_id with sb-themed)
                    try:
                        parent_sb = ad.locator('xpath=ancestor::div[contains(@cel_widget_id, "sb-themed-collection")]')
                        if parent_sb.count() > 0:
                            log(f"display: bottom skipped - inside SB themed collection")
                            continue
                    except Exception:
                        pass
                    # Skip if it's actually an in-grid search result (has data-component-type="s-search-result")
                    try:
                        parent_search = ad.locator('xpath=ancestor::div[@data-component-type="s-search-result"]')
                        if parent_search.count() > 0:
                            log(f"display: bottom skipped - in-grid search result")
                            continue
                    except Exception:
                        pass
                    bottom_ads.append(ad)
                    if len(bottom_ads) >= MAX_BOTTOM_DISPLAY:
                        break
                
                log(f"display: bottom found {len(bottom_ads)} ads (excluded left rail)")
                for i, el in enumerate(bottom_ads):
                    if not el.is_visible():
                        continue
                    # Instacart-style scroll and freeze
                    try:
                        el.scroll_into_view_if_needed()
                        time.sleep(0.1)
                    except Exception:
                        pass
                    try:
                        el.evaluate("""
                          (el) => new Promise(async (resolve) => {
                            const sleep = (ms) => new Promise(r => setTimeout(r, ms));
                            let stable = 0, last = 0;
                            for (let i=0; i<10 && stable<3; i++) {
                              const imgs = Array.from(el.querySelectorAll('img')).filter(i => i.complete && i.naturalWidth > 10).length;
                              if (imgs === last) stable++; else stable = 0;
                              last = imgs; await sleep(300);
                            }
                            resolve(true);
                          })
                        """)
                    except Exception:
                        pass
                    try:
                        if bottom_ads.nth(i).locator('img').count() == 0:
                            log("display: bottom skipped (no images)")
                            continue
                    except Exception:
                        pass
                    brand_txt, brand_canon, message = _extract_brand_and_message(el)
                    adv_for_name = brand_canon or "unknown"
                    fname = _std_filename("amazon", adv_for_name, "Sponsored_Display", client, keyword, run_id, i, ".png")
                    fpath = os.path.join(output_dir, "Sponsored_Display", fname)
                    try:
                        # Freeze animations (Instacart pattern)
                        try:
                            page.evaluate("""
                                () => {
                                    const style = document.createElement('style');
                                    style.textContent = '* { transition: none !important; animation: none !important; }';
                                    document.head.appendChild(style);
                                }
                            """)
                        except Exception:
                            pass
                        # Flush layout
                        try:
                            page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
                        except Exception:
                            pass
                        el.screenshot(path=fpath, timeout=4000)
                        anchor = _module_anchor(el)
                        if re.match(r'^(sb|sponsoredb|sponsoredbrands)', (anchor or '').lower()):
                            log(f"display: skip sb-like anchor -> {anchor}")
                            continue
                        module_id, eid = _build_ids("Sponsored_Display", "Bottom_Display", brand_canon, anchor, run_id, i)
                        if anchor in seen_anchors:
                            log(f"display: bottom duplicate anchor skipped -> {anchor}")
                            continue
                        seen_anchors.add(anchor)
                        if module_id in captured_modules:
                            log(f"display: bottom duplicate module skipped -> {module_id}")
                            continue
                        captured_modules.add(module_id)
                        ads.append({
                            "id": eid,
                            "module_id": module_id,
                            "type": "Sponsored_Display",
                            "subtype": "Bottom_Display",
                            "brand": brand_txt or "Unknown",
                            "brand_canonical": brand_canon,
                            "advertisers": [brand_canon] if brand_canon else [],
                            "image_path": f"Sponsored_Display/{fname}",
                            "video_path": None,
                            "message": message,
                            "metadata": {},
                        })
                        log(f"display: bottom saved -> {fpath} module_id={module_id}")
                    except Exception as e:
                        log(f"display: bottom screenshot fail -> {e}")
            except Exception as e:
                log(f"display: bottom detect error -> {e}")

            # 4) Sponsored Products (aggregate + ASIN images)
            try:
                log("sp: aggregate")
                items = page.locator('div[data-component-type=\"s-search-result\"]')
                n = items.count()
                sp_list = []
                page_num = 1
                try:
                    from urllib.parse import urlparse, parse_qs
                    qs = parse_qs(urlparse(page.url).query)
                    if qs.get("page"):
                        page_num = int(qs["page"][0])
                except Exception:
                    pass

                rank = 0
                for i in range(n):
                    item = items.nth(i)
                    is_sp = False
                    try:
                        lab = item.locator(":text('Sponsored')").first
                        if lab.count() > 0 and lab.is_visible():
                            is_sp = True
                    except Exception:
                        pass
                    if not is_sp:
                        continue
                    rank += 1
                    if len(sp_list) >= MAX_SP:
                        break

                    asin = None
                    try:
                        asin = item.get_attribute("data-asin")
                    except Exception:
                        pass

                    title = None
                    try:
                        title = (item.locator('h2 a span').first.text_content() or '').strip()
                    except Exception:
                        pass

                    brand_txt = None
                    for sel in ["span.a-size-base.a-color-secondary", "span.a-size-base-plus.a-color-base.a-text-normal", "h2 a span"]:
                        try:
                            loc = item.locator(sel).first
                            if loc.count() > 0:
                                t = (loc.text_content() or "").strip()
                                if t:
                                    brand_txt = t
                                    break
                        except Exception:
                            pass
                    brand_canon = None
                    try:
                        if brand_txt:
                            brand_canon = canonicalize(brand_txt)
                    except Exception:
                        brand_canon = None

                    img_url = None
                    img_path_rel = None
                    client_mirror_rel = None
                    try:
                        img = item.locator('img.s-image').first
                        if img.count() > 0:
                            src = img.get_attribute('src')
                            if src and src.startswith('http'):
                                img_url = src
                                try:
                                    from urllib.parse import urlparse
                                    ext = os.path.splitext(urlparse(src).path)[1] or ".jpg"
                                except Exception:
                                    ext = ".jpg"
                                file_name = (asin or f"rank_{rank}") + ext
                                central_full = central_asin_dir / file_name
                                try:
                                    # Skip download if already exists
                                    if not central_full.exists():
                                        r = requests.get(src, timeout=10)
                                        if r.ok:
                                            with open(central_full, 'wb') as fimg:
                                                fimg.write(r.content)
                                    # Set path regardless of whether we just downloaded
                                    if central_full.exists():
                                        img_path_rel = str(central_full.relative_to(project_root))
                                        try:
                                            client_full = os.path.join(output_dir, "ASIN_Images", file_name)
                                            if not os.path.exists(client_full):
                                                shutil.copyfile(central_full, client_full)
                                            client_mirror_rel = f"ASIN_Images/{file_name}"
                                        except Exception:
                                            pass
                                        log(f"sp: asin image -> {central_full} (cached={central_full.exists()})")
                                    else:
                                        log(f"sp: asin download failed for {asin}")
                                except Exception as e:
                                    log(f"sp: asin download fail -> {e}")
                    except Exception as e:
                        log(f"sp: image selector fail -> {e}")

                    price_text = None
                    try:
                        price_text = (item.locator('span.a-price .a-offscreen').first.text_content() or '').strip()
                    except Exception:
                        pass
                    rating = None
                    try:
                        rt = (item.locator('span.a-icon-alt').first.text_content() or '').strip()
                        if rt:
                            rating = float(rt.split()[0])
                    except Exception:
                        pass
                    reviews_count = None
                    try:
                        rc = (item.locator('span[aria-label$="ratings"], span[aria-label$="rating"]').first.text_content() or '').strip()
                        if rc:
                            reviews_count = int(''.join([c for c in rc if c.isdigit()]))
                    except Exception:
                        pass
                    prime = False
                    try:
                        prime = item.locator('i.a-icon.a-icon-prime, svg[aria-label="Prime"]').count() > 0
                    except Exception:
                        pass
                    badges = []
                    try:
                        for lab in ["Amazon's Choice", "Best Seller", "Sponsored"]:
                            try:
                                if item.locator(f'[aria-label="{lab}"]').count() > 0:
                                    badges.append(lab)
                            except Exception:
                                pass
                    except Exception:
                        pass
                    product_url = None
                    try:
                        href = item.locator('h2 a').first.get_attribute('href')
                        if href:
                            product_url = href if href.startswith('http') else f"https://www.amazon.com{href}"
                    except Exception:
                        pass

                    sp_list.append({
                        "asin": asin,
                        "rank": rank,
                        "page": page_num,
                        "brand": brand_txt or None,
                        "brand_canonical": brand_canon,
                        "title": title,
                        "image_url": img_url,
                        "image_path": img_path_rel,
                        "client_image_path": client_mirror_rel,
                        "price": price_text,
                        "rating": rating,
                        "reviews_count": reviews_count,
                        "prime": prime,
                        "badges": badges,
                        "product_url": product_url,
                    })

                if sp_list:
                    module_id, eid = _build_ids("Sponsored_Product_List", "List", None, f"page_{page_num}", run_id, 0)
                    ads.append({
                        "id": eid,
                        "module_id": module_id,
                        "type": "Sponsored_Product_List",
                        "subtype": "List",
                        "brand": None,
                        "brand_canonical": None,
                        "advertisers": [],
                        "image_path": None,
                        "video_path": None,
                        "message": "",
                        "metadata": {"page": page_num, "count": len(sp_list), "items": sp_list},
                    })
                    log(f"sp: items collected -> {len(sp_list)}")
                else:
                    log("sp: none found")
            except Exception as e:
                log(f"sp: aggregate error -> {e}")

            # Save HTML at the end
            try:
                log("html: save")
                html_content = page.content()
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                log(f"html: saved -> {html_path} exists={os.path.exists(html_path)} size={os.path.getsize(html_path) if os.path.exists(html_path) else 0}")
            except Exception as e:
                log(f"html: save error -> {e}")

            success = True
        except Exception as e:
            log(f"fatal: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Save tracing
            try:
                trace_path = os.path.join(runs_dir, f"trace_{ts}.zip")
                bctx.tracing.stop(path=trace_path)
                log(f"trace: saved -> {trace_path} exists={os.path.exists(trace_path)} size={os.path.getsize(trace_path) if os.path.exists(trace_path) else 0}")
            except Exception as e:
                log(f"trace: stop error -> {e}")
            try:
                if bctx:
                    bctx.close()
            except Exception:
                pass
            try:
                p.stop()
            except Exception:
                pass

    if success:
        log("json: save")
        run_data = {
            "retailer": "amazon",
            "client": client,
            "keyword": keyword,
            "search_url": _search_url(keyword),
            "ts": ts,
            "html": os.path.basename(html_path),
            "ads": ads,
            "timestamp": datetime.utcnow().isoformat(timespec="seconds").replace("+00:00", "Z"),
            "run_id": run_id,
        }
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(run_data, f, indent=2, ensure_ascii=False)
            log(f"json: saved -> {json_path} exists={os.path.exists(json_path)} size={os.path.getsize(json_path) if os.path.exists(json_path) else 0}")
        except Exception as e:
            log(f"json: save error -> {e}")

    return success


if __name__ == "__main__":
    import sys
    keyword = sys.argv[1] if len(sys.argv) > 1 else "waterproof bandage"
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "output/amazon/bandaid"

    success = search_and_capture(keyword, output_dir)
    if success:
        print("\n✅ AMAZON SEARCH AND CAPTURE COMPLETED SUCCESSFULLY")
    else:
        print("\n❌ AMAZON SEARCH AND CAPTURE FAILED")
        sys.exit(1)