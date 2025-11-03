#!/usr/bin/env python3
"""
Instacart search and capture script.
Performs keyword search on Instacart and saves HTML + JSON results.
"""

import os
import sys
import json
import re
import base64
import time
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from brand_logo_database import BrandLogoDatabase

# Tunable: Sponsored text detection radius (px above carousel)
NEARBY_SPONSOR_PX = int(os.environ.get("IC_SPONSOR_RADIUS_PX", "650"))


def _wait_for_viewport_images(page, timeout_ms=1500):
    """
    Wait until all images currently intersecting the viewport are loaded (complete && naturalWidth > 0).
    Non-blocking fallback: returns when timeout reached.
    """
    try:
        page.wait_for_function(
            """
            () => {
              const vw = window.innerWidth;
              const vh = window.innerHeight;
              const inView = (el) => {
                const r = el.getBoundingClientRect();
                return r.bottom > 0 && r.right > 0 && r.top < vh && r.left < vw;
              };
              const imgs = Array.from(document.images).filter(inView);
              return imgs.every(img => img.complete && img.naturalWidth > 0);
            }
            """,
            timeout=timeout_ms
        )
    except Exception:
        # Non-fatal: if some ad uses canvas/video, images may not be the only load.
        pass


def _get_card_from_region(region):
    """
    From a region wrapper, go up to ancestor whose id ends with '-inner',
    then take its parent (that parent is the visual card).
    Fallback: nearest ancestor with any @id.
    """
    try:
        inner = region.locator('xpath=ancestor::div[substring(@id, string-length(@id)-5)="-inner"][1]')
        if inner.count() > 0:
            parent = inner.locator('xpath=..')
            if parent.count() > 0:
                return parent.first
        any_id = region.locator('xpath=ancestor::div[@id][1]')
        if any_id.count() > 0:
            return any_id.first
    except Exception:
        pass
    return region  # last-resort fallback


def _card_has_ad_signals(card):
    """
    Check if a card has ad signals (heading + sponsored, or brand link, or hero/video).
    """
    # heading
    has_heading = card.locator('h2, h3, [role="heading"]').count() > 0
    # sponsored (allow split spans: "Spons" + "ored")
    try:
        txt = card.inner_text()
    except Exception:
        txt = ""
    has_sponsored = bool(re.search(r'spons\s*ored', txt, re.I))
    # optional extra signals (brand link, hero/video)
    brand_link = card.locator('a[href*="/brands/"]').count() > 0
    has_hero_or_video = (
        card.locator('img[alt="Advertisement"]').count() > 0 or
        card.locator('video, source').count() > 0
    )
    return (has_heading and has_sponsored) or brand_link or has_hero_or_video


def _get_tight_card(region):
    """
    From the carousel region, find the container div that wraps
    both the header <a> tag AND the carousel div[id$="-inner"].
    Structure: region -> div[id$="-inner"] -> parent div[id] (the card)
    Uses structural patterns (not hashed class names) for stability.
    """
    try:
        # Find the div[id$="-inner"] that is a descendant of the region
        inner_div = region.locator('xpath=.//div[substring(@id, string-length(@id)-5)="-inner"][1]')
        if inner_div.count() > 0:
            # The parent of -inner is the card container (has an id, contains both <a> and -inner)
            card_container = inner_div.locator('xpath=..')
            if card_container.count() > 0:
                return card_container.first
            
    except Exception:
        pass
    
    # Last resort fallback
    return _get_card_from_region(region)


def _screenshot_card(card, out_path, pad=12):
    """
    Align the card's top into the viewport and grab the element.
    """
    try:
        card.scroll_into_view_if_needed()
        card.page.wait_for_timeout(80)
        card.page.evaluate(
            "(el, p) => { el.scrollIntoView({block:'start'}); window.scrollBy(0, -p); }",
            card.element_handle(), pad
        )
    except Exception:
        pass
    card.screenshot(path=out_path)
    return out_path


def _scroll_card_and_get_rect(locator, pad=12):
    """
    From an anchor inside the ad (carousel), find the bordered card container,
    scroll it so it fits in the viewport (top not negative, bottom not occluded),
    and return its viewport rect. Falls back to the anchor if no bordered container exists.
    """
    return locator.evaluate(
        """(node, pad) => {
            const vh = window.innerHeight, vw = window.innerWidth;
            const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi);
            const toNum = v => (v ? parseFloat(v) || 0 : 0);
            const rgb = s => {
              if (!s) return null;
              const m = s.replaceAll('/', ' ')
                         .match(/rgba?\\s*\\(\\s*(\\d+)\\s*[ ,]\\s*(\\d+)\\s*[ ,]\\s*(\\d+)/i);
              return m ? [parseInt(m[1],10), parseInt(m[2],10), parseInt(m[3],10)] : null;
            };
            const near = (a,b,t)=>Math.abs(a-b)<=t;

            // Try to find a bordered ancestor (or outline/1px box-shadow ring)
            const target = [232,233,235], tol = 4;
            function bordered(el){
              let e = el;
              for (let d=0; d<10 && e; d++){
                const cs = getComputedStyle(e);
                const sides = ['Top','Right','Bottom','Left'];
                let has = false;
                for (const s of sides){
                  const w = toNum(cs['border'+s+'Width']);
                  const st = (cs['border'+s+'Style']||'').toLowerCase();
                  const c = rgb(cs['border'+s+'Color']);
                  if (w>=1 && st && st!=='none' && c && near(c[0],target[0],tol) && near(c[1],target[1],tol) && near(c[2],target[2],tol)){
                    has = true; break;
                  }
                }
                if (!has){
                  const ow = toNum(cs.outlineWidth);
                  const os = (cs.outlineStyle||'').toLowerCase();
                  const oc = rgb(cs.outlineColor);
                  const bs = cs.boxShadow||'';
                  const boxRing = /0\\s+0\\s+0\\s+1px\\s+rgba?\\(/i.test(bs) && rgb(bs);
                  if ((ow>=1 && os && os!=='none' && oc && near(oc[0],target[0],tol) && near(oc[1],target[1],tol) && near(oc[2],target[2],tol))
                      || (boxRing && near(boxRing[0],target[0],tol) && near(boxRing[1],target[1],tol) && near(boxRing[2],target[2],tol))) {
                    has = true;
                  }
                }
                if (has) return e;
                e = e.parentElement;
              }
              return null;
            }

            let card = bordered(node) || node;
            let r = card.getBoundingClientRect();

            // If the card is shorter than viewport, try to scroll it fully into view
            if (r.height + 2*pad <= vh){
              // If top is above pad, nudge down; if bottom below, nudge up
              let dy = 0;
              if (r.top < pad)      dy = r.top - pad;
              else if (r.bottom > vh - pad) dy = r.bottom - (vh - pad);
              if (dy) window.scrollBy(0, dy);
              r = card.getBoundingClientRect();
            } else {
              // Too tall: align its top to pad so header is included
              card.scrollIntoView({ block: 'start', inline: 'nearest' });
              window.scrollBy(0, -pad);
              r = card.getBoundingClientRect();
            }

            // Build viewport-space clip rect
            let x = Math.floor(r.left - pad);
            let y = Math.floor(r.top  - pad);
            let w = Math.ceil(r.width  + 2*pad);
            let h = Math.ceil(r.height + 2*pad);

            // Clamp to viewport (page.screenshot clip is viewport-based)
            x = clamp(x, 0, Math.max(0, vw - 1));
            y = clamp(y, 0, Math.max(0, vh - 1));
            w = clamp(w, 1, vw - x);
            h = clamp(h, 1, vh - y);

            return { x, y, width: w, height: h };
        }""",
        pad
    )


def _has_nearby_sponsored(carousel_locator, max_px=650):
    """
    Check for 'Sponsored' text near (above) the carousel, allowing for sibling/ancestor splits.
    We scan previous siblings and a few ancestors within max_px vertical distance.
    """
    try:
        return carousel_locator.evaluate(
            """(node, maxDist) => {
                const carRect = node.getBoundingClientRect();
                const hasSponsored = (el) => {
                  if (!el) return false;
                  const text = (el.innerText || '').toLowerCase();
                  return /spons\\s*ored/.test(text);
                };

                // Walk up to 5 ancestors; at each level, scan previous siblings above the carousel
                let el = node;
                for (let depth = 0; depth < 5 && el; depth++) {
                  const parent = el.parentElement;
                  if (!parent) break;

                  // Previous siblings
                  let sib = el.previousElementSibling;
                  while (sib) {
                    const r = sib.getBoundingClientRect();
                    if (r.bottom <= carRect.top + 10 && (carRect.top - r.bottom) < maxDist) {
                      if (hasSponsored(sib)) return true;
                    }
                    // Stop if we're too far above
                    if (r.bottom < carRect.top - maxDist) break;
                    sib = sib.previousElementSibling;
                  }

                  // Parent might contain a sponsored badge that visually sits above this block
                  const pr = parent.getBoundingClientRect();
                  if (pr.bottom <= carRect.top + 10 && (carRect.top - pr.bottom) < maxDist && hasSponsored(parent)) {
                    return true;
                  }

                  el = parent;
                }
                return false;
            }""",
            max_px
        )
    except Exception:
        return False


def compute_bordered_ancestor_clip(locator, pad=12, target_rgb=(232, 233, 235), min_px=1,
                                   choose="outermost", max_height=1800, max_depth=10, color_tol=4):
    """
    Walk up from `locator` and find an ancestor whose computed style has a visible border
      (~= 1px solid rgb(232,233,235)). Returns a page clip rect {x,y,width,height} with padding.
    - choose: "outermost" (furthest matching within max_depth but not huge) or "nearest"
    - color_tol: +/- tolerance per RGB channel to allow css/renderer rounding (e.g. rgba(...) or rgb(... / 1))
    """
    return locator.evaluate(
        """(node, opt) => {
          const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi);
          const toNum = (x) => (x ? parseFloat(x) || 0 : 0);

          const parseRGB = (s) => {
            if (!s) return null;
            // Accept "rgb(r, g, b)", "rgba(r, g, b, a)", "rgb(r g b / a)" formats
            const m = s.replaceAll('/', ' ').match(/rgba?\\s*\\(\\s*(\\d+)\\s*[ ,]\\s*(\\d+)\\s*[ ,]\\s*(\\d+)/i);
            if (!m) return null;
            return [parseInt(m[1],10), parseInt(m[2],10), parseInt(m[3],10)];
          };

          const nearly = (a, b, tol) => Math.abs(a - b) <= tol;

          const hasTargetBorder = (el) => {
            const cs = getComputedStyle(el);
            const styles = ['Top','Right','Bottom','Left'];

            let anySide = false, colorMatch = false, styleOk = false;
            let foundColor = null;

            for (const side of styles) {
              const w = toNum(cs['border' + side + 'Width']);
              const s = (cs['border' + side + 'Style'] || '').toLowerCase();
              const c = parseRGB(cs['border' + side + 'Color']);
              if (w >= opt.min_px && s && s !== 'none') {
                anySide = true;
                if (c) {
                  const match = nearly(c[0], opt.target_rgb[0], opt.color_tol)
                             && nearly(c[1], opt.target_rgb[1], opt.color_tol)
                             && nearly(c[2], opt.target_rgb[2], opt.color_tol);
                  if (match) colorMatch = true;
                  // remember one color for debugging
                  if (!foundColor) foundColor = c;
                }
                if (s === 'solid') styleOk = true;
              }
            }

            // ALSO support outline/box-shadow as a thin 1px ring if border not present
            if (!(anySide && (styleOk || colorMatch))) {
              const ow = toNum(cs.outlineWidth);
              const os = (cs.outlineStyle || '').toLowerCase();
              const oc = parseRGB(cs.outlineColor);
              if (ow >= opt.min_px && os && os !== 'none' && oc) {
                const om = nearly(oc[0], opt.target_rgb[0], opt.color_tol)
                        && nearly(oc[1], opt.target_rgb[1], opt.color_tol)
                        && nearly(oc[2], opt.target_rgb[2], opt.color_tol);
                if (om) { anySide = true; colorMatch = true; styleOk = true; }
              }

              // Very common pattern: box-shadow used as a 1px outline
              const bs = cs.boxShadow || '';
              // Look for "... 0 0 0 1px rgb(...)" or similar
              if (!styleOk && /0\\s+0\\s+0\\s+1px\\s+rgba?\\(/i.test(bs)) {
                const c = parseRGB(bs);
                if (c && nearly(c[0], opt.target_rgb[0], opt.color_tol)
                      && nearly(c[1], opt.target_rgb[1], opt.color_tol)
                      && nearly(c[2], opt.target_rgb[2], opt.color_tol)) {
                  anySide = true; colorMatch = true; styleOk = true;
                }
              }
            }

            return anySide && (styleOk || colorMatch);
          };

          const vw = window.innerWidth;
          const vh = window.innerHeight;

          const matches = [];
          let el = node;
          for (let depth = 0; depth < opt.max_depth && el; depth++) {
            const r = el.getBoundingClientRect();
            const areaOk = r.width > 200 && r.height > 120 && r.height < opt.max_height && r.width < vw; // guardrails
            if (areaOk && hasTargetBorder(el)) {
              matches.push(el);
            }
            el = el.parentElement;
          }

          if (!matches.length) return null;

          const pick = (opt.choose === 'outermost') ? matches[matches.length - 1] : matches[0];
          const r = pick.getBoundingClientRect();

          // Keep in viewport space (NO scroll offsets)
          let x = Math.floor(r.left - opt.pad);
          let y = Math.floor(r.top  - opt.pad);
          let w = Math.ceil(r.width  + 2 * opt.pad);
          let h = Math.ceil(r.height + 2 * opt.pad);

          // Clamp to viewport
          x = clamp(x, 0, Math.max(0, vw - 1));
          y = clamp(y, 0, Math.max(0, vh - 1));
          w = clamp(w, 1, vw - x);
          h = clamp(h, 1, vh - y);

          return { x, y, width: w, height: h };
        }""",
        {
          "pad": pad,
          "target_rgb": list(target_rgb),
          "min_px": min_px,
          "choose": choose,
          "max_height": max_height,
          "max_depth": max_depth,
          "color_tol": color_tol,
        }
    )


def compute_ad_union_clip(locator, padding=20):
    """
    Given a locator anchored somewhere in the ad region (your 'region_element' or the carousel),
    compute a screenshot clip rect that unions:
      - nearest ad header above (h2/h3/[role=heading]) within 500px
      - hero/video above or within the region
      - the carousel itself
    Returns a dict {x, y, width, height} in page coordinates with padding applied, clamped to document bounds.
    """
    # We do evaluation relative to the passed node so we can look up/down the DOM safely
    return locator.evaluate(
        """(node, padding) => {
          const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi);
          const within = (r) => !!r && r.width > 0 && r.height > 0;

          // Viewport dimensions (clip is relative to viewport)
          const vw = window.innerWidth;
          const vh = window.innerHeight;

          const rects = [];

          // 1) Carousel rect
          const carousel = node.closest('[data-testid="shoppable-list-sliding-carousel"]') || node;
          const carRect = carousel.getBoundingClientRect();
          if (within(carRect)) rects.push(carRect);

          // 2) Nearest heading ABOVE the carousel within ~500px
          let headerRect = null;
          {
            // Check current container and walk up a few ancestors to find a heading sibling
            let el = carousel;
            for (let depth = 0; depth < 6 && el; depth++) {
              const parent = el.parentElement;
              if (!parent) break;
              // headings in parent
              const candidates = parent.querySelectorAll('h2,h3,[role="heading"]');
              for (const h of candidates) {
                const r = h.getBoundingClientRect();
                if (within(r) && r.bottom <= carRect.top + 10 && (carRect.top - r.bottom) < 500) {
                  headerRect = r; break;
                }
              }
              if (headerRect) break;

              // try previous sibling with headings
              let sib = el.previousElementSibling;
              while (sib && !headerRect) {
                const heads = sib.querySelectorAll('h2,h3,[role="heading"]');
                for (const h of heads) {
                  const r = h.getBoundingClientRect();
                  if (within(r) && r.bottom <= carRect.top + 10 && (carRect.top - r.bottom) < 500) {
                    headerRect = r; break;
                  }
                }
                sib = sib.previousElementSibling;
              }
              if (headerRect) break;
              el = parent;
            }
          }
          if (headerRect) rects.push(headerRect);

          // 3) Hero/video within the same block (above or around carousel)
          let heroRect = null;
          {
            // Limit search to a reasonable ancestor
            let block = carousel;
            for (let i = 0; i < 4 && block && !block.hasAttribute('id'); i++) block = block.parentElement || block;
            const scope = block || carousel;
            const heroes = scope.querySelectorAll('img[alt="Advertisement"], video, [data-testid*="hero"]');
            for (const hero of heroes) {
              const r = hero.getBoundingClientRect();
              // Accept hero if it's near the carousel (above or overlapping, not miles away)
              const near = within(r) && Math.abs(r.top - carRect.top) < 800;
              if (near) { heroRect = r; break; }
            }
          }
          if (heroRect) rects.push(heroRect);

          // Union the rects
          let left = Infinity, top = Infinity, right = -Infinity, bottom = -Infinity;
          for (const r of rects) {
            left = Math.min(left, r.left);
            top = Math.min(top, r.top);
            right = Math.max(right, r.right);
            bottom = Math.max(bottom, r.bottom);
          }
          if (!isFinite(left) || !isFinite(top) || !isFinite(right) || !isFinite(bottom)) {
            // Fallback to carousel only
            left = carRect.left; top = carRect.top; right = carRect.right; bottom = carRect.bottom;
          }

          // Apply padding; keep coords in viewport space (NO scroll offsets)
          let x = Math.floor(left - padding);
          let y = Math.floor(top  - padding);
          let w = Math.ceil((right - left) + 2*padding);
          let h = Math.ceil((bottom - top) + 2*padding);

          // Clamp to viewport
          x = clamp(x, 0, Math.max(0, vw - 1));
          y = clamp(y, 0, Math.max(0, vh - 1));
          w = clamp(w, 1, vw - x);
          h = clamp(h, 1, vh - y);

          return { x, y, width: w, height: h };
        }""",
        padding
    )


def _wait_for_ad_creative_loaded(page, el, timeout_ms=1200):
    """
    Wait for ad creative (images/video) inside an element to be fully loaded.
    Critical for ads with viewability gates that require dwell time.
    """
    try:
        page.wait_for_function(
            """(e) => {
               const vw = window.innerWidth, vh = window.innerHeight;
               const r = e.getBoundingClientRect();
               const inView = (r.bottom > 0 && r.right > 0 && r.top < vh && r.left < vw);
               if (!inView) return false;
               const imgs = Array.from(e.querySelectorAll('img'));
               const okImg = imgs.length === 0 || imgs.every(i => i.complete && i.naturalWidth > 0);
               const vid = e.querySelector('video');
               const okVid = !vid || (vid.readyState >= 2);
               return okImg && okVid;
            }""",
            el,
            timeout=timeout_ms
        )
    except Exception:
        # Non-fatal: some ads are canvas/iframe; still proceed
        pass


def capture_fullpage_static_no_resize(context, page, out_path):
    """
    Capture the entire page without changing the viewport using CDP.
    - Uses Page.captureScreenshot with captureBeyondViewport=true
    - Requires Chromium (works with Playwright's Chromium)
    - No viewport resize = no reflow/virtualization churn
    """
    client = context.new_cdp_session(page)
    
    # Ensure we are at a stable state (optional – keeps animations from flickering)
    try:
        page.add_style_tag(content="""
          * { animation: none !important; transition: none !important; }
          html { scroll-behavior: auto !important; }
        """)
    except Exception:
        pass

    # Ask Chrome for a beyond-viewport screenshot in a single raster pass
    shot = client.send("Page.captureScreenshot", {
        "format": "png",
        "fromSurface": True,
        "captureBeyondViewport": True
    })
    data = base64.b64decode(shot["data"])
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(data)
    return out_path


def _wait_until_home_ready(page, log, timeout_ms=15000):
    """Wait for homepage to be fully loaded and ready."""
    try:
        page.wait_for_load_state("load", timeout=timeout_ms)
        log("Home: load state reached")
    except Exception as e:
        log(f"Home: load state wait skipped/failed: {e}")
    
    selectors = [
        "[data-testid='search-bar-input']",
        "input[placeholder*='Search']",
        "[role='search'] input",
        "header",
    ]
    for sel in selectors:
        try:
            page.wait_for_selector(sel, timeout=4000)
            log(f"Home: ready selector found: {sel}")
            return
        except Exception:
            pass
    
    page.wait_for_timeout(3000)
    log("Home: fallback settle delay used")


def _is_login_modal_visible(page):
    """Check if Instacart login modal is visible."""
    # Known auth modal selectors seen on Instacart
    SELS = [
        ".ReactModalPortal .AuthModal__Overlay",
        "[data-testid='authModalWrapper']",
    ]
    try:
        for sel in SELS:
            el = page.query_selector(sel)
            if el and el.is_visible():
                return True
        return False
    except Exception:
        return False


def _prompt_user_login(page, log, max_wait_sec=300):
    """
    When a login modal is present, bring the browser to the foreground,
    instruct the user to complete login, and wait until the modal disappears.
    Returns True if login modal disappears, False on timeout.
    """
    try:
        page.bring_to_front()
    except Exception:
        pass
    
    log("⚠️ Login required: A login modal is visible.")
    log("Please complete the Instacart login in the visible browser window.")
    log("After you finish, the scraper will continue automatically.")
    log(f"Timeout in {max_wait_sec} seconds.")
    
    deadline = time.time() + max_wait_sec
    last_report = 0
    while time.time() < deadline:
        if not _is_login_modal_visible(page):
            log("✅ Login modal no longer visible — continuing.")
            return True
        # Report every ~10 seconds so logs show progress
        now = time.time()
        if now - last_report >= 10:
            remaining = int(deadline - now)
            log(f"Waiting for login to complete... ({remaining}s remaining)")
            last_report = now
        page.wait_for_timeout(1000)
    
    log("❌ Login prompt timeout — no change detected. You may need to re-run auth:")
    log("   ./scripts/setup_instacart_profile.sh")
    return False


def _handle_login_if_needed(page, log, max_wait_sec=300):
    """Check for login modal and prompt user if visible. Returns True if OK to continue."""
    try:
        if _is_login_modal_visible(page):
            return _prompt_user_login(page, log, max_wait_sec=max_wait_sec)
        return True
    except Exception as e:
        log(f"Login check failed: {e}")
        return False


def search_and_capture(keyword: str, output_dir: str, store: str = None) -> bool:
    """
    Search Instacart for a keyword and capture the results.
    
    Args:
        keyword: Search term
        output_dir: Directory to save results
        store: Store slug (e.g., 'publix', 'kroger'). Defaults to INSTACART_STORE env var or 'publix'
    
    Returns:
        True if successful, False otherwise
    """
    
    # Set up debug logging
    debug_log = os.path.join(output_dir, "debug_search.log")
    os.makedirs(output_dir, exist_ok=True)
    
    def log(msg):
        """Log to both stdout and debug file"""
        print(msg)
        try:
            with open(debug_log, 'a', encoding='utf-8') as f:
                f.write(f"{datetime.now().isoformat()} {msg}\n")
        except:
            pass
    
    log(f"=== SEARCH START: {keyword} ===")
    
    # Get store from parameter or environment
    if store is None:
        store = os.environ.get('INSTACART_STORE', 'publix')
    log(f"Store: {store}")
    
    # Get profile directory
    profile_dir = os.environ.get('INSTACART_PROFILE_DIR')
    log(f"Profile dir: {profile_dir}")
    if not profile_dir or not os.path.isdir(profile_dir):
        log(f"❌ INSTACART_PROFILE_DIR not set or invalid: {profile_dir}")
        log("Run: ./scripts/setup_instacart_profile.sh")
        return False
    log(f"✅ Profile directory valid")
    
    # Initialize brand logo database
    try:
        # Get project root (2 levels up from output_dir)
        project_root = Path(output_dir).parent.parent
        logo_db = BrandLogoDatabase(base_dir=str(project_root))
        log("Brand logo database initialized")
    except Exception as e:
        log(f"Warning: Could not initialize brand logo database: {e}")
        logo_db = None
    
    # Clean up stale lock file if it exists
    lock_file = os.path.join(profile_dir, 'SingletonLock')
    if os.path.exists(lock_file):
        try:
            os.remove(lock_file)
            print(f"   Removed stale lock file: {lock_file}")
        except Exception as e:
            print(f"   Warning: Could not remove lock file: {e}")
    
    # Create runs directory
    runs_dir = os.path.join(output_dir, "runs")
    os.makedirs(runs_dir, exist_ok=True)
    log(f"Runs directory: {runs_dir}")
    
    # Timestamp for filenames (readable with dashes/colons)
    timestamp_for_file = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    # ISO 8601 timestamp for JSON (taxonomy compliance)
    timestamp_iso = datetime.now().isoformat(timespec="seconds")
    
    # Sanitize keyword for filename (like Kroger does)
    safe_keyword = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in keyword.lower())
    
    # Include keyword in filename (like Kroger format)
    html_file = os.path.join(runs_dir, f"search_results_{safe_keyword}_{timestamp_for_file}.html")
    json_file = os.path.join(runs_dir, f"run_results_{safe_keyword}_{timestamp_for_file}.json")
    
    log(f"🔍 Searching Instacart for: '{keyword}'")
    log(f"   Store: {store}")
    log(f"   Profile: {profile_dir}")
    
    # Use Playwright with persistent context (authenticated session)
    log("Starting Playwright...")
    try:
        with sync_playwright() as p:
            # Launch with persistent context (authenticated session)
            # Use stable mainstream UA to avoid automation fingerprinting
            context = p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=False,
                viewport={'width': 1920, 'height': 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
                locale='en-US',
                args=[
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--no-first-run',
                    '--no-default-browser-check',
                    '--disable-session-crashed-bubble',  # Suppress "Restore pages?" prompt
                ],
            )
            
            page = context.pages[0] if context.pages else context.new_page()
            
            # Visit homepage (organic navigation)
            log("Loading homepage...")
            page.goto(f'https://www.instacart.com/store/{store}', wait_until='domcontentloaded', timeout=15000)
            
            # Don't rush off the home page
            _wait_until_home_ready(page, log, timeout_ms=15000)
            
            # If a login modal is present on home, pause for interactive login
            if not _handle_login_if_needed(page, log, max_wait_sec=300):
                context.close()
                return False
            
            # Organic search interaction (robust version)
            log(f"Searching for: {keyword}")
            try:
                # 0) Cookie banner can block the header — dismiss if present (best-effort)
                cookie_ctas = [
                    "button:has-text('Accept')",
                    "button:has-text('Agree')",
                    "[data-testid*='accept']",
                    "button[aria-label*='Accept']",
                ]
                for cta in cookie_ctas:
                    try:
                        loc = page.locator(cta).first
                        if loc.is_visible():
                            log(f"   Dismissing cookie banner via {cta}")
                            loc.click(timeout=1000)
                            page.wait_for_timeout(300)
                            break
                    except Exception:
                        pass
                
                # 1) Some variants gate the input behind a search-toggle button
                toggle_selectors = [
                    "button[aria-label*='Search']",
                    "[data-testid='search-bar-button']",
                    "[data-testid='search-input-toggle']",
                    "button:has(svg[aria-label='Search'])",
                ]
                for tsel in toggle_selectors:
                    try:
                        loc = page.locator(tsel).first
                        if loc.is_visible():
                            log(f"   Clicking search toggle: {tsel}")
                            loc.click(timeout=1500)
                            page.wait_for_timeout(300)
                            break
                    except Exception:
                        pass
                
                # 2) Broad input/combobox selector (covers most site variants)
                search_selector = (
                    "[data-testid='search-bar-input'], "
                    "input[type='search'], "
                    "input[placeholder*='Search'], "
                    "input[aria-label*='Search'], "
                    "[role='search'] input, "
                    "[contenteditable='true'][role='combobox']"
                )
                search_input = page.locator(search_selector).filter(
                    has_not=page.locator("[aria-hidden='true']")
                ).first
                
                log("   Looking for search input...")
                search_input.wait_for(state="visible", timeout=6000)
                log("   Search input found and visible")
                
                # 3) Ensure it's interactable
                try:
                    search_input.scroll_into_view_if_needed(timeout=1500)
                except Exception:
                    pass
                search_input.click(timeout=2000)
                log("   Clicked search input")
                
                # 4) Type/fill and submit
                try:
                    search_input.fill("")  # clear if anything prefilled
                except Exception:
                    pass
                search_input.fill(keyword)
                log(f"   Filled keyword: {keyword}")
                page.wait_for_timeout(200)
                search_input.press("Enter")
                log("   Pressed Enter on input")
                
                # 5) Wait for results URL
                page.wait_for_url("**/s?k=**", timeout=12000)
                log("   ✅ Navigated to search results via organic search")
                
            except Exception as e:
                log(f"   ❌ Search box interaction failed: {type(e).__name__}: {e}")
                try:
                    # Drop a screenshot so we can see what blocked us
                    shot = os.path.join(runs_dir, "home_before_fallback.png")
                    page.screenshot(path=shot, full_page=False)
                    log(f"   Saved debug screenshot: {shot}")
                except Exception:
                    pass
                log("   Falling back to direct navigation...")
                search_url = f"https://www.instacart.com/store/{store}/s?k={keyword}"
                page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                log("   Direct navigation completed")
                
                # Emulate human arrival after direct navigation
                page.wait_for_timeout(1200)
                page.evaluate("window.scrollTo(0, 200)")
                page.wait_for_timeout(400)
                page.evaluate("window.scrollTo(0, 0)")
                log("   Synthetic dwell + scroll completed")
            
            # Some flows can trigger the auth modal on the results page — handle again
            if not _handle_login_if_needed(page, log, max_wait_sec=300):
                context.close()
                return False
            
            # On results page, attempt consent dismissal again (broader selectors)
            log("   Checking for consent banner on results page...")
            consent_selectors = [
                "[id*='onetrust-accept']",
                "button:has-text('Accept')",
                "button:has-text('I agree')",
                "[data-testid*='accept']",
                "[aria-label*='Accept']",
            ]
            for cta in consent_selectors:
                try:
                    loc = page.locator(cta).first
                    # Wait for element to be visible with timeout
                    loc.wait_for(state="visible", timeout=1000)
                    log(f"   Accepting consent via {cta}")
                    loc.click(timeout=1000)
                    page.wait_for_timeout(300)
                    break
                except Exception:
                    pass
            
            # Prefer to see ad containers; fallback to a short settle delay
            try:
                page.wait_for_selector("div.e-1qzz7bi, div.e-1hv1sre", timeout=8000)
                log("Search: ad containers detected")
            except Exception:
                log("Search: ad containers not detected within 8s; using short settle delay")
                page.wait_for_timeout(3000)
            
            search_url = page.url
            log("✅ Authenticated session active")
            
            # Extract ad data for JSON (matching Kroger structure)
            # NOTE: We'll save HTML AFTER extraction to ensure it matches what we extracted
            ad_data = {
                "keyword": keyword,
                "search_term": keyword,
                "store": store,
                "timestamp": timestamp_iso,
                "retailer": "instacart",
                "url": search_url,
                "source_file": html_file,
                "results": [{"ads": []}]  # Nested structure like Kroger
            }
            
            # Create output directories for screenshots
            shoppable_display_dir = os.path.join(output_dir, "Shoppable_Display_Ads")
            shoppable_video_dir = os.path.join(output_dir, "Shoppable_Video_Ads")
            display_ad_dir = os.path.join(output_dir, "Display_Ads")
            shoppable_recipe_dir = os.path.join(output_dir, "Shoppable_Recipe_Ads")
            main_dir = os.path.join(output_dir, "Main")
            
            for d in [shoppable_display_dir, shoppable_video_dir, display_ad_dir, shoppable_recipe_dir, main_dir]:
                os.makedirs(d, exist_ok=True)
            
            # Extract client name from output_dir
            client_name = os.path.basename(output_dir)
            
            # CRITICAL: Scroll page to load ALL lazy-loaded ads BEFORE extraction
            # This ensures ads that appear lower on the page are in the DOM when we extract
            print("\n📜 Pre-loading lazy content (scrolling to load all ads)...")
            try:
                # Nudge lazy images without mutating overflow/virtual scrollers
                page.evaluate("""
                  document.querySelectorAll('img[loading="lazy"]').forEach(img => { img.loading = 'eager'; });
                  document.querySelectorAll('img[data-src]').forEach(img => { if (!img.src) img.src = img.dataset.src; });
                """)
                page.wait_for_timeout(300)

                vh = page.evaluate("() => window.innerHeight")
                doc_h = page.evaluate("() => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)")

                # Scroll in 50% viewport steps down and back up to keep items rendered
                step = int(max(1, vh * 0.5))
                y = 0
                positions = []
                while y < doc_h - vh:
                    positions.append(y)
                    y += step

                for pos in positions:
                    page.evaluate(f"window.scrollTo({{top: {pos}, behavior: 'auto'}})")
                    page.wait_for_timeout(350)

                for pos in reversed(positions):
                    page.evaluate(f"window.scrollTo({{top: {pos}, behavior: 'auto'}})")
                    page.wait_for_timeout(250)

                page.evaluate("window.scrollTo({top: 0, behavior: 'auto'})")
                page.wait_for_timeout(400)
                print('✅ Page fully loaded with all lazy content')
            except Exception as e:
                print(f'⚠️  Lazy load warning: {e}')
            
            # NEW RESILIENT EXTRACTION: Use Playwright locators with semantic selectors
            # Ignores hashed CSS classes entirely - keys off stable attributes
            print("\n🔍 Extracting Instacart ads using resilient selectors...")
            
            sponsor_regex = re.compile(r"Spons\s*ored", re.I)
            extracted_ads = []
            seen_carousel_ids = set()  # Track unique carousels to avoid duplicates
            
            try:
                # Find carousel regions (the wrapper above the carousel div)
                # This is the correct anchor point that contains header + hero + carousel
                regions = page.locator('[role="region"][aria-label="item carousel"]').filter(
                    has=page.locator('[data-testid="shoppable-list-sliding-carousel"]')
                )
                region_count = regions.count()
                log(f"🧭 Found {region_count} carousel regions")
                
                for c_idx in range(region_count):
                    region = regions.nth(c_idx)
                    log(f"\n🔍 Processing region {c_idx + 1}/{region_count}")
                    
                    # Get carousel within region for ID tracking
                    carousel = region.locator('[data-testid="shoppable-list-sliding-carousel"]').first
                    try:
                        carousel_id = carousel.get_attribute('id') or f"carousel_{c_idx}"
                        if carousel_id in seen_carousel_ids:
                            log(f"   ⏭️  Skipping duplicate carousel: {carousel_id}")
                            continue
                        seen_carousel_ids.add(carousel_id)
                    except:
                        carousel_id = f"carousel_{c_idx}"
                    
                    # We already have the region from the role="region" selector
                    # Get the ad container structurally (no hashed classes):
                    # Anchor on carousel, walk up to -inner, then up to border container
                    try:
                        # Anchor on the carousel inside the region
                        carousel = region.locator('[data-testid="shoppable-list-sliding-carousel"]').first
                        
                        # Go up to nearest -inner ancestor, then up one more to the border container
                        card = carousel.locator(
                            'xpath=ancestor::div[substring(@id, string-length(@id)-5)="-inner"][1]/..'
                        ).first
                        
                        # Fallback: if for any reason the carousel anchor isn't found, try from region
                        if card.count() == 0:
                            card = region.locator(
                                'xpath=ancestor::div[substring(@id, string-length(@id)-5)="-inner"][1]/..'
                            ).first
                        
                        # Last resort: use region (don't "walk up" to generic ancestors with id)
                        if card.count() == 0:
                            card = region
                    except Exception:
                        card = region
                    
                    # Optional: gate to avoid false positives
                    if not _card_has_ad_signals(card):
                        log("   ⏭️  No ad signals in card; skipping")
                        continue
                    
                    # Debug logging and size guard
                    try:
                        elem_bbox = card.bounding_box()
                        region_bbox = region.bounding_box()
                        
                        # Guard against obviously-too-small "cards" (likely wrong element)
                        if elem_bbox and (elem_bbox['height'] < 140 or elem_bbox['width'] < 240):
                            log(f"   ⚠️ Card too small (w={elem_bbox['width']}, h={elem_bbox['height']}), skipping")
                            continue
                        log(f"   ↳ region bbox: {region_bbox}")
                        log(f"   ↳ card   bbox: {elem_bbox}")
                        # Log card element info
                        try:
                            card_id = card.get_attribute('id') or 'no-id'
                            card_tag = card.evaluate("el => el.tagName.toLowerCase()")
                            log(f"   ↳ card element: <{card_tag} id='{card_id}'>")
                        except Exception:
                            pass
                    except Exception as e:
                        log(f"   ⚠️  Bbox logging failed: {e}")
                    
                    elem = card  # Use card as elem for rest of the code
                    
                    # Ad signals: Check for multiple indicators
                    # Advertisement image
                    has_ad_img = region.locator('img[alt="Advertisement"]').count() > 0
                    
                    # Sponsored text in region
                    has_sponsor_text = False
                    try:
                        if region.get_by_text(sponsor_regex).count() > 0:
                            has_sponsor_text = True
                        else:
                            region_text = region.inner_text()
                            if re.search(r'spons\s*ored', region_text, re.I):
                                has_sponsor_text = True
                    except Exception:
                        pass
                    
                    # Additional, robust signals:
                    has_brand_link_close = region.locator('a[href*="/brands/"]').count() > 0
                    has_video_hint = (
                        region.locator('video').count() > 0
                        or region.get_by_role('button', name=re.compile(r'Advertisement\s*Play\s*Video|Play\s*Video', re.I)).count() > 0
                        or region.locator('button[aria-label*="Play"][aria-label*="Video"]').count() > 0
                    )
                    
                    # Sponsored might be above/adjacent, not inside region: check near the carousel anchor
                    has_sponsor_nearby = False
                    try:
                        has_sponsor_nearby = _has_nearby_sponsored(carousel, max_px=NEARBY_SPONSOR_PX)
                    except Exception:
                        pass
                    
                    has_signal = (has_ad_img or has_sponsor_text or has_sponsor_nearby or has_brand_link_close or has_video_hint)
                    
                    if not has_signal:
                        print(f"   ⏭️  Skipping - no ad signals found (ad_img={has_ad_img}, sponsor_in_region={has_sponsor_text}, sponsor_nearby={has_sponsor_nearby}, brand_link={has_brand_link_close}, video_hint={has_video_hint})")
                        continue
                    
                    print(f"   ✅ Ad signals detected (ad_img={has_ad_img}, sponsor_in_region={has_sponsor_text}, sponsor_nearby={has_sponsor_nearby}, brand_link={has_brand_link_close}, video_hint={has_video_hint})")
                    
                    # Video signals: video element or play video button
                    has_video = (
                        region.locator('video').count() > 0
                        or region.get_by_role('button', name=re.compile(r'Advertisement\s*Play\s*Video', re.I)).count() > 0
                        or region.get_by_role('button', name=re.compile(r'Play\s*Video', re.I)).count() > 0
                        or region.locator('button[aria-label*="Play"][aria-label*="Video"]').count() > 0
                    )
                    
                    # Header text (brand headline)
                    header_text = ""
                    try:
                        header_loc = region.locator('h2, h3, [class*="header"], [class*="title"]').first
                        if header_loc.is_visible():
                            header_text = (header_loc.inner_text() or "").strip()
                    except Exception:
                        pass
                    
                    # Brand landing link (/store/.../brands/...)
                    brand_link = ""
                    try:
                        brand_link_loc = region.locator('a[href*="/store/"][href*="/brands/"]').first
                        if brand_link_loc.is_visible():
                            brand_link = brand_link_loc.get_attribute('href') or ""
                    except Exception:
                        pass
                    
                    # Optional ad hero images
                    # Look for large images in the ad region (hero/banner images)
                    hero_imgs = []
                    try:
                        # Try Advertisement alt first (most common)
                        hero_imgs = [
                            el.get_attribute("src") or ""
                            for el in region.locator('a img[alt="Advertisement"], img[alt="Advertisement"]').all()
                        ]
                        
                        # If no Advertisement images, look for any large images in the ad container
                        # (before the carousel) that are likely hero images
                        if not hero_imgs:
                            # Get all images in the region
                            all_imgs = region.locator('img').all()
                            carousel_in_region = region.locator('[data-testid="shoppable-list-sliding-carousel"]').first
                            
                            for img in all_imgs:
                                try:
                                    # Skip if image is inside the carousel (product images)
                                    if carousel_in_region.locator('xpath=..').locator(f'img[src="{img.get_attribute("src")}"]').count() > 0:
                                        continue
                                    
                                    # Check if image is large enough to be a hero (not an icon)
                                    bbox = img.bounding_box()
                                    if bbox and bbox['width'] > 100 and bbox['height'] > 100:
                                        src = img.get_attribute("src") or ""
                                        if src and 'display.instacart.com' in src:
                                            hero_imgs.append(src)
                                except:
                                    pass
                        
                        hero_imgs = [u for u in hero_imgs if u]
                    except Exception:
                        pass
                    
                    # Extract shoppable products (first N)
                    products = []
                    try:
                        slider = region.locator('[data-testid="shoppable-list-sliding-carousel"]')
                        li_cards = slider.locator('li[data-testid^="item_list_item_"]')
                        li_count = min(li_cards.count(), 10)
                        for i in range(li_count):
                            card = li_cards.nth(i)
                            href = ""
                            title = ""
                            try:
                                link = card.locator('a[href]').first
                                if link.is_visible():
                                    href = link.get_attribute('href') or ""
                            except Exception:
                                pass
                            try:
                                # role heading is stable; e.g. [role="heading"][aria-level="4"]
                                title_el = card.locator('[role="heading"][aria-level="4"]').first
                                if title_el.is_visible():
                                    title = (title_el.inner_text() or "").strip()
                            except Exception:
                                pass
                            if title or href:
                                products.append({"href": href, "title": title})
                    except Exception as e:
                        print(f"⚠️ Shoppable slider parse error: {e}")
                    
                    # If it's a shoppable ad, we should have some products
                    if not products:
                        continue
                    
                    # If video, capture video metadata
                    video_info = None
                    if has_video:
                        try:
                            v = region.locator('video').first
                            if v.is_visible() or v.count() > 0:
                                src = v.get_attribute('src') or ''
                                poster = v.get_attribute('poster') or ''
                                # Some players embed <source> children
                                if not src:
                                    try:
                                        src = v.locator('source').first.get_attribute('src') or ''
                                    except:
                                        pass
                                video_info = {"src": src, "poster": poster}
                        except Exception:
                            pass
                    
                    ad_type = "Shoppable Video Ad" if has_video else "Shoppable Display Ad"
                    
                    extracted_ads.append({
                        "type": ad_type,
                        "header": header_text,
                        "brand_link": brand_link,
                        "hero_images": hero_imgs,
                        "sponsored": bool(has_sponsor_text or has_ad_img),
                        "video": video_info,  # null for display; dict for video
                        "products": products,
                        "region_element": region,  # Keep reference for screenshot/brand extraction
                        "carousel_element": carousel,  # Exact carousel we iterated
                        "carousel_id": carousel_id or ""  # ID for fallback lookup
                    })
            
            except Exception as e:
                print(f"⚠️ Shoppable unit extraction error: {e}")
            
            print(f"✅ Instacart shoppable units extracted: {len(extracted_ads)}")
            
            # Separate counters for display vs video ads
            display_ad_counter = 0
            video_ad_counter = 0
            
            # Now process each extracted ad with brand matching logic
            for i, ad_raw in enumerate(extracted_ads):
                # Rebuild the region and get the ad container structurally
                region = ad_raw["region_element"]
                try:
                    carousel = region.locator('[data-testid="shoppable-list-sliding-carousel"]').first
                    card = carousel.locator(
                        'xpath=ancestor::div[substring(@id, string-length(@id)-5)="-inner"][1]/..'
                    ).first
                    
                    if card.count() == 0:
                        card = region.locator(
                            'xpath=ancestor::div[substring(@id, string-length(@id)-5)="-inner"][1]/..'
                        ).first
                    
                    if card.count() == 0:
                        card = region
                except Exception:
                    card = region
                
                elem = card  # from here on, 'elem' refers to the card element
                actual_ad_type = ad_raw["type"]
                
                # Increment appropriate counter
                if actual_ad_type == "Shoppable Video Ad":
                    video_ad_counter += 1
                    ad_index = video_ad_counter
                else:
                    display_ad_counter += 1
                    ad_index = display_ad_counter
                
                try:
                    # Get bounding box for screenshot coordinates
                    bbox = elem.bounding_box()
                    
                    ad_info = {
                        "type": actual_ad_type,
                        "index": i,
                        "header": ad_raw["header"],
                        "brand_link": ad_raw["brand_link"],
                        "hero_images": ad_raw["hero_images"],
                        "sponsored": ad_raw["sponsored"],
                        "video": ad_raw["video"],
                        "products": ad_raw["products"]
                    }
                    
                    if bbox:
                        ad_info["bbox"] = {
                            "x": bbox['x'],
                            "y": bbox['y'],
                            "width": bbox['width'],
                            "height": bbox['height']
                        }
                    
                    # Try to extract brand/advertiser
                    advertiser = None
                    logo_img = None
                    
                    # FIRST: Try to extract from brand_link (most reliable for shoppable ads)
                    if ad_raw["brand_link"]:
                        try:
                            brand_match = re.search(r'/brands/([^/?]+)', ad_raw["brand_link"])
                            if brand_match:
                                brand_slug = brand_match.group(1)
                                # Clean up brand slug - remove company prefixes like "dgic-"
                                # Common patterns: "dgic-outshine" -> "outshine", "mondelez-oreo" -> "oreo"
                                if '-' in brand_slug:
                                    parts = brand_slug.split('-')
                                    # If first part is short (likely a company code), use the rest
                                    if len(parts) > 1 and len(parts[0]) <= 4:
                                        brand_slug = '-'.join(parts[1:])
                                
                                # Convert slug to title case (e.g., "goodpop" -> "Goodpop")
                                advertiser = brand_slug.replace('-', ' ').title()
                                print(f"   📌 Advertiser from brand_link: {advertiser}")
                        except:
                            pass
                    
                    # FALLBACK: Extract from first product title if no brand_link
                    if not advertiser and ad_raw["products"]:
                        try:
                            first_product = ad_raw["products"][0]["title"]
                            # Extract first 1-2 capitalized words as brand
                            words = first_product.split()
                            brand_words = []
                            for word in words[:3]:
                                if word and word[0].isupper():
                                    brand_words.append(word)
                                    if len(brand_words) >= 2:
                                        break
                                else:
                                    break
                            if brand_words:
                                advertiser = ' '.join(brand_words)
                                print(f"   📌 Advertiser from product: {advertiser}")
                        except:
                            pass
                    
                    # Add advertiser to ad_info if we found one
                    if advertiser:
                        ad_info["advertisers"] = [advertiser]
                        ad_info["brand"] = advertiser
                    
                    # ADDITIONAL: Try logo alt text (for display ads - may override above)
                    logo_img_loc = None
                    try:
                        # Strategy 0: Extract from advertiser logo alt text (MOST RELIABLE for Display Ads)
                        # Display ads have a logo with alt text like <img alt="Stonyfield Organic">
                        logo_img_loc = elem.locator('img[alt]:not([alt=""])').first
                        if logo_img_loc.count() > 0:
                            alt_text = logo_img_loc.get_attribute('alt')
                            if alt_text and alt_text.strip() and len(alt_text) > 2:
                                # Check if it's purely generic (single word like "logo", "image")
                                generic_alts = ['logo', 'image', 'ad', 'banner', 'sponsored', 'advertisement']
                                
                                # If alt text is a single generic word, skip it
                                if alt_text.lower() in generic_alts:
                                    pass  # Skip purely generic alt text
                                # If alt text contains descriptive words (e.g., "New York Bakery Logo"), extract the brand
                                elif any(generic in alt_text.lower() for generic in ['logo', 'brand', 'image']):
                                    # Remove generic descriptive words and extract brand
                                    cleaned = alt_text
                                    for word in ['Logo', 'logo', 'Brand', 'brand', 'Image', 'image']:
                                        cleaned = cleaned.replace(word, '').strip()
                                    
                                    if cleaned and len(cleaned) > 2:
                                        alt_text = cleaned  # Use cleaned version
                                        # Continue with normal extraction logic below
                                
                                # Now process the (possibly cleaned) alt text
                                if alt_text and alt_text.lower() not in generic_alts:
                                    # If alt text is short and clean, use it directly
                                    if len(alt_text) < 30 and '&' not in alt_text:
                                        advertiser = alt_text.strip()
                                    else:
                                        # For longer descriptive alt text, try multiple strategies:
                                        # 1. Look for brand after " - " separator (e.g., "Frighteningly Delicious Treats - Sour Patch Kids")
                                        # 2. Look for brand at the beginning (e.g., "Sour Patch Kids & Swedish Fish candies")
                                        
                                        brand_candidate = None
                                        
                                        # Strategy: Check for " - " separator (brand often comes after)
                                        if ' - ' in alt_text:
                                            parts = alt_text.split(' - ')
                                            # Brand is usually after the dash
                                            if len(parts) > 1:
                                                brand_part = parts[-1].strip()  # Take last part after dash
                                                # Extract first 1-3 capitalized words from this part
                                                words = brand_part.split()
                                                brand_words = []
                                                for word in words[:3]:
                                                    if word and word[0].isupper():
                                                        brand_words.append(word)
                                                    else:
                                                        break
                                                if brand_words:
                                                    brand_candidate = ' '.join(brand_words)
                                        
                                        # Fallback: Extract from beginning (before '&' or descriptive words)
                                        if not brand_candidate:
                                            words = alt_text.split()
                                            descriptive_words = {'in', 'on', 'with', 'and', 'or', 'the', 'a', 'an', 'for', 'at', 
                                                               'candies', 'candy', 'products', 'product', 'items', 'item',
                                                               'costumes', 'costume', 'packages', 'package', 'bottles', 'bottle',
                                                               'treats', 'treat', 'delicious', 'frighteningly'}
                                            brand_words = []
                                            for word in words[:5]:  # Look at first 5 words
                                                # Stop at '&' or descriptive words
                                                if word in ['&', 'and', '-'] or word.lower() in descriptive_words:
                                                    break
                                                # Collect capitalized words
                                                if word and word[0].isupper():
                                                    brand_words.append(word)
                                                    if len(brand_words) >= 3:  # Max 3 words for brand
                                                        break
                                            
                                            if brand_words:
                                                brand_candidate = ' '.join(brand_words)
                                        
                                        if brand_candidate:
                                            advertiser = brand_candidate
                        
                        # Validate/refine brand by checking against product carousel
                        # If we extracted a brand from alt text, verify it appears in the products
                        if advertiser:
                            products_loc = region.locator('[data-testid^="item_list_item"]')
                            if products_loc.count() > 0:
                                # Get all product text to search for brand mentions
                                carousel_text = ' '.join([products_loc.nth(i).inner_text() for i in range(min(3, products_loc.count()))])  # Check first 3 products
                                
                                # Normalize for fuzzy matching (handle &/and, case, punctuation)
                                def normalize_for_comparison(text):
                                    """Normalize for matching only (lowercase)"""
                                    return text.lower().replace('&', 'and').replace("'", "").replace(".", "").strip()
                                
                                def normalize_brand_name(text):
                                    """Normalize and return in Title Case"""
                                    normalized = text.replace('&', 'and').replace("'", "").replace(".", "").strip()
                                    return normalized.title()
                                
                                normalized_advertiser = normalize_for_comparison(advertiser)
                                normalized_carousel = normalize_for_comparison(carousel_text)
                                
                                # Check if extracted brand appears in carousel (fuzzy match)
                                # Also check if individual words from brand appear (e.g., "Sour Patch" in "SOUR PATCH KIDS")
                                brand_words = normalized_advertiser.split()
                                words_found = sum(1 for word in brand_words if len(word) > 2 and word in normalized_carousel)
                                match_ratio = words_found / len(brand_words) if brand_words else 0
                                
                                # If brand validated (≥50% match), normalize to Title Case
                                if match_ratio >= 0.5:
                                    advertiser = normalize_brand_name(advertiser)
                                # If less than 50% of brand words found, extract from carousel instead
                                elif match_ratio < 0.5:
                                    # Brand not found in carousel, try to extract from product names instead
                                    for i in range(min(3, products_loc.count())):
                                        product = products_loc.nth(i)
                                        product_text = product.inner_text()
                                        # Look for product heading
                                        heading = product.locator('[role="heading"], h4').first
                                        if heading.count() > 0:
                                            heading_text = heading.inner_text()
                                            # Extract brand from product name (first 1-3 capitalized words)
                                            words = heading_text.split()
                                            brand_words = []
                                            for word in words[:4]:
                                                if word and word[0].isupper() and word.upper() == word:
                                                    # All caps word (like "SOUR", "PATCH", "KIDS")
                                                    brand_words.append(word.title())  # Convert to title case
                                                elif word and word[0].isupper():
                                                    brand_words.append(word)
                                                else:
                                                    break
                                                if len(brand_words) >= 3:
                                                    break
                                            
                                            if brand_words:
                                                advertiser = ' '.join(brand_words)
                                                break
                        
                        # Strategy 1: Extract from first product in carousel (for Shoppable ads without logo)
                        # This matches the screenshot script's successful approach
                        if not advertiser:
                            products_loc2 = region.locator('[data-testid^="item_list_item"]')
                            if products_loc2.count() > 0:
                                first_product = products_loc2.first
                                product_text = first_product.inner_text()
                                lines = [line.strip() for line in product_text.split('\n') if line.strip()]
                                
                                # Find the product name line (longer, contains product info)
                                # Skip promotional text, prices, ratings, and generic UI elements
                                for line in lines:
                                    if (len(line) > 15 and  # Product names are usually longer
                                        not line.startswith('$') and 
                                        not line.startswith('★') and
                                        not line.startswith('(') and
                                        not 'Current price' in line and
                                        not 'Spend' in line and
                                        not line.endswith('oz') and
                                        not line == 'Add' and
                                        not 'save' in line.lower() and
                                        not 'See eligible' in line):
                                        
                                        # Extract brand from product name (first 1-2 capitalized words)
                                        words = line.split()
                                        if words and len(words) >= 2:
                                            descriptive_words = {'Fresh', 'Cut', 'Pure', 'Premium', 'Original', 'Classic', 
                                                                'Natural', 'Organic', 'Whole', 'Sliced', 'Diced', 'Chopped'}
                                            brand_words = []
                                            for word in words[:3]:
                                                if word and word[0].isupper() and word not in descriptive_words:
                                                    brand_words.append(word)
                                                    if len(brand_words) == 2:
                                                        break
                                                elif word in descriptive_words:
                                                    break
                                            
                                            if brand_words:
                                                advertiser = ' '.join(brand_words)
                                                break
                        
                        # Strategy 2: Look for brand link
                        if not advertiser:
                            brand_link = elem.locator('a[href*="/brands/"]').first
                            if brand_link.count() > 0:
                                href = brand_link.get_attribute('href') or ''
                                brand_match = re.search(r'/brands/([^/?]+)', href)
                                if brand_match:
                                    brand_slug = brand_match.group(1)
                                    advertiser = brand_slug.replace('-', ' ').title()
                        
                        # Strategy 3: Look for heading with brand name
                        if not advertiser:
                            heading = elem.locator('h2, h3').first
                            if heading.count() > 0:
                                heading_text = heading.inner_text()
                                brand_match = re.search(r'(?:Stock Up On|Shop|Discover|Try|from)\s+([A-Z][a-zA-Z\s&\'\.]+?)(?:\s*$|\s+Products|\s+Items)', heading_text, re.IGNORECASE)
                                if brand_match:
                                    advertiser = brand_match.group(1).strip()
                        
                        if advertiser:
                            ad_info["advertisers"] = [advertiser]
                            ad_info["brand"] = advertiser  # Also set brand field for consistency
                            
                            # Save brand logo to database if we have a logo image
                            try:
                                if logo_db and logo_img_loc and logo_img_loc.count() > 0:
                                    logo_src = logo_img_loc.get_attribute('src')
                                    if logo_src:
                                        logo_db.add_brand_logo(
                                            brand=advertiser,
                                            logo_url=logo_src,
                                            retailer="instacart",
                                            metadata={
                                                "ad_type": actual_ad_type,
                                                "keyword": keyword,
                                                "timestamp": timestamp_iso
                                            }
                                        )
                            except Exception as logo_err:
                                print(f"   Warning: Could not save brand logo: {logo_err}")
                    except Exception:
                        pass  # If brand extraction fails, continue without brand
                    
                    # Take screenshot of this ad (same page load as extraction!)
                    try:
                        # Hide floating header to avoid it covering ads
                        try:
                            page.evaluate("""
                                () => {
                                    const header = document.querySelector('header[class*="sticky"], header[style*="position: fixed"], header[style*="position:fixed"]');
                                    if (header) {
                                        header.style.display = 'none';
                                    }
                                }
                            """)
                        except:
                            pass
                        
                        # Scroll ad into view and wait for creative to load (viewability gates)
                        elem.scroll_into_view_if_needed()
                        page.wait_for_timeout(250)
                        _wait_for_ad_creative_loaded(page, elem, timeout_ms=1200)
                        
                        # Determine output folder based on ad type
                        if actual_ad_type == 'Shoppable Video Ad':
                            output_folder = shoppable_video_dir
                            ad_type_slug = 'shoppable_video_ad'
                        elif actual_ad_type == 'Shoppable Display Ad':
                            output_folder = shoppable_display_dir
                            ad_type_slug = 'shoppable_display_ad'
                        else:  # Display Ad
                            output_folder = display_ad_dir
                            ad_type_slug = 'display_ad'
                        
                        # Generate filename using correct index
                        from filename_utils import generate_ad_filename
                        screenshot_filename = generate_ad_filename(
                            retailer='instacart',
                            ad_type=ad_type_slug,
                            client=client_name,
                            search_term=keyword,
                            timestamp=timestamp_for_file,
                            index=ad_index,
                            extension='png',
                            advertiser=advertiser
                        )
                        screenshot_path = os.path.join(output_folder, screenshot_filename)
                        
                        # Take screenshot: Oct 15 method - simple element screenshot
                        try:
                            # Scroll element into view to ensure it's fully visible
                            card.scroll_into_view_if_needed()
                            page.wait_for_timeout(500)  # Let it settle
                            
                            # Direct element screenshot - exactly like Oct 15
                            card.screenshot(path=screenshot_path)
                            log(f"   📸 Screenshot: {os.path.basename(screenshot_path)}")

                        except Exception as e:
                            log(f"   ⚠️  Screenshot failed: {e}, skipping ad")
                            continue  # skip this ad gracefully
                        
                        # Store relative path (taxonomy compliance)
                        rel_screenshot_path = os.path.relpath(screenshot_path, output_dir)
                        ad_info["screenshot"] = rel_screenshot_path
                        print(f"   📸 Screenshot: {os.path.basename(screenshot_path)}")
                        
                        # For video ads, download or record the video file
                        if actual_ad_type == 'Shoppable Video Ad' and ad_raw["video"] and ad_raw["video"].get("src"):
                            try:
                                video_src = ad_raw["video"]["src"]
                                video_filename = screenshot_filename.replace('.png', '.mp4')
                                video_path = os.path.join(output_folder, video_filename)
                                
                                # Check if it's HLS (.m3u8) or direct video
                                if video_src.endswith('.m3u8'):
                                    # HLS stream - try to download with ffmpeg if available
                                    print(f"   🎥 Video is HLS stream (.m3u8)")
                                    try:
                                        import subprocess
                                        result = subprocess.run(
                                            ['ffmpeg', '-i', video_src, '-c', 'copy', '-bsf:a', 'aac_adtstoasc', video_path],
                                            capture_output=True,
                                            timeout=30
                                        )
                                        if result.returncode == 0:
                                            ad_info["video_file"] = video_path
                                            print(f"   ✅ HLS video downloaded: {os.path.basename(video_path)}")
                                        else:
                                            # Store URL instead
                                            ad_info["video_url"] = video_src
                                            print(f"   ℹ️  HLS video URL saved (ffmpeg failed)")
                                    except (FileNotFoundError, subprocess.TimeoutExpired):
                                        # ffmpeg not available or timeout
                                        ad_info["video_url"] = video_src
                                        print(f"   ℹ️  HLS video URL saved (ffmpeg not available)")
                                else:
                                    # Direct video file - download it
                                    import urllib.request
                                    urllib.request.urlretrieve(video_src, video_path)
                                    ad_info["video_file"] = video_path
                                    print(f"   ✅ Video downloaded: {os.path.basename(video_path)}")
                            except Exception as video_err:
                                print(f"   ⚠️  Could not download video: {video_err}")
                                # At minimum, save the URL
                                if video_src:
                                    ad_info["video_url"] = video_src
                        
                    except Exception as screenshot_err:
                        print(f"   ⚠️  Could not capture screenshot: {screenshot_err}")
                    
                        # Enrich with brand logo path from database
                    if advertiser and logo_db:
                        logo_path = logo_db.get_logo_path(advertiser)
                        if logo_path:
                            ad_info["brand_logo"] = logo_path
                    
                    ad_data["results"][0]["ads"].append(ad_info)
                except Exception as e:
                    print(f"⚠️  Could not extract data from ad #{i}: {e}")
            
            # Handle Shoppable Recipe ads (different structure - using old selectors for now)
            # TODO: Update recipe ads to use resilient selectors
            try:
                # Look for "Related recipe" heading with "Sponsored" label
                recipe_containers = page.query_selector_all('div.e-1yrpusx')
                for i, container in enumerate(recipe_containers):
                    try:
                        # Check if this container has "Related recipe" and "Sponsored"
                        heading = container.query_selector('h2.e-5ieped')
                        sponsored = container.query_selector('span.e-yrjvxu')
                        
                        if heading and sponsored:
                            heading_text = heading.inner_text()
                            sponsored_text = sponsored.inner_text()
                            
                            if 'Related recipe' in heading_text and 'Sponsored' in sponsored_text:
                                # This is a Shoppable Recipe ad
                                ad_id = container.get_attribute('id') or f"recipe_{i}"
                                bbox = container.bounding_box()
                                
                                ad_info = {
                                    "type": "Shoppable Recipe Ad",
                                    "selector": "div.e-1yrpusx (Related recipe)",
                                    "id": ad_id,
                                    "index": i,
                                }
                                
                                if bbox:
                                    ad_info["bbox"] = {
                                        "x": bbox['x'],
                                        "y": bbox['y'],
                                        "width": bbox['width'],
                                        "height": bbox['height']
                                    }
                                
                                # Extract recipe details (URL, title, brand)
                                advertiser = None
                                recipe_url = None
                                recipe_title = None
                                
                                try:
                                    # Look for recipe link (contains URL, brand image, and title)
                                    recipe_link = container.query_selector('a[href*="/recipes/"]')
                                    if recipe_link:
                                        # Extract recipe URL
                                        href = recipe_link.get_attribute('href')
                                        if href:
                                            recipe_url = href
                                            ad_info["recipe_url"] = recipe_url
                                        
                                        # Extract brand from image alt text within the link
                                        recipe_img = recipe_link.query_selector('img[alt]')
                                        if recipe_img:
                                            alt_text = recipe_img.get_attribute('alt')
                                            if alt_text and alt_text.strip():
                                                # Filter out generic alt texts
                                                generic_alts = ['logo', 'image', 'ad', 'banner', 'sponsored', 'advertisement']
                                                if alt_text.lower() not in generic_alts:
                                                    advertiser = alt_text.strip()
                                        
                                        # Extract recipe title from h2
                                        title_elem = recipe_link.query_selector('h2')
                                        if title_elem:
                                            recipe_title = title_elem.inner_text().strip()
                                            ad_info["recipe_title"] = recipe_title
                                    
                                    # Fallback: look for brand link
                                    if not advertiser:
                                        brand_link = container.query_selector('a[href*="/brands/"]')
                                        if brand_link:
                                            href = brand_link.get_attribute('href') or ''
                                            brand_match = re.search(r'/brands/([^/?]+)', href)
                                            if brand_match:
                                                brand_slug = brand_match.group(1)
                                                advertiser = brand_slug.replace('-', ' ').title()
                                    
                                    if advertiser:
                                        ad_info["advertisers"] = [advertiser]
                                        ad_info["brand"] = advertiser
                                except:
                                    pass
                                
                                # Take screenshot of recipe ad
                                try:
                                    container.scroll_into_view_if_needed()
                                    page.wait_for_timeout(250)
                                    _wait_for_ad_creative_loaded(page, container, timeout_ms=1200)
                                    
                                    from filename_utils import generate_ad_filename
                                    screenshot_filename = generate_ad_filename(
                                        retailer='instacart',
                                        ad_type='shoppable_recipe_ad',
                                        client=client_name,
                                        search_term=keyword,
                                        timestamp=timestamp_for_file,
                                        index=i+1,
                                        extension='png',
                                        advertiser=advertiser
                                    )
                                    screenshot_path = os.path.join(shoppable_recipe_dir, screenshot_filename)
                                    container.screenshot(path=screenshot_path)
                                    # Store relative path (taxonomy compliance)
                                    rel_screenshot_path = os.path.relpath(screenshot_path, output_dir)
                                    ad_info["screenshot"] = rel_screenshot_path
                                    print(f"   📸 Screenshot: {os.path.basename(screenshot_path)}")
                                except Exception as screenshot_err:
                                    print(f"   ⚠️  Could not capture recipe screenshot: {screenshot_err}")
                                
                                # Enrich with brand logo path from database
                                if advertiser and logo_db:
                                    logo_path = logo_db.get_logo_path(advertiser)
                                    if logo_path:
                                        ad_info["brand_logo"] = logo_path
                                
                                ad_data["results"][0]["ads"].append(ad_info)
                                print(f"✅ Found Shoppable Recipe ad: {advertiser or 'unknown'}")
                    except Exception as e:
                        print(f"⚠️  Could not extract Shoppable Recipe #{i}: {e}")
            except Exception as e:
                print(f"⚠️  Error processing Shoppable Recipe ads: {e}")
            
            ad_count = len(ad_data['results'][0]['ads'])
            ad_data['count'] = ad_count
            print(f"📊 Found {ad_count} ad units")
            
            # Save HTML/JSON immediately after extraction so they match ad_data and ad crops
            html_content = page.content()
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"💾 HTML saved: {html_file}")
            
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(ad_data, f, indent=2)
            print(f"💾 JSON saved: {json_file}")
            
            # Take full-page screenshot using CDP (no viewport resize, single raster pass)
            print("\n📸 Taking full-page screenshot (CDP static capture)...")
            try:
                from filename_utils import generate_ad_filename
                fullpage_filename = generate_ad_filename(
                    retailer='instacart',
                    ad_type='main',
                    client=client_name,
                    search_term=keyword,
                    timestamp=timestamp_for_file,
                    index=1,
                    extension='png',
                    advertiser=None
                )
                fullpage_path = os.path.join(main_dir, fullpage_filename)

                # For screenshot: Need bidirectional scroll to keep virtual scroll items in DOM
                # The pre-extraction scroll loaded ads, but virtual scroll may have removed grid items
                try:
                    vh = page.evaluate("() => window.innerHeight")
                    doc_h = page.evaluate("() => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)")
                    
                    # Smaller steps with more overlap to ensure virtual scroll items stay rendered
                    step = int(max(1, vh * 0.5))  # 50% viewport height
                    y = 0
                    scroll_positions = []
                    
                    # Collect all scroll positions first
                    while y < doc_h - vh:
                        scroll_positions.append(y)
                        y += step
                    
                    # Scroll down slowly to load content
                    for pos in scroll_positions:
                        page.evaluate(f"window.scrollTo({{top: {pos}, behavior: 'smooth'}})")
                        page.wait_for_timeout(400)  # Longer wait for virtual scroll to render
                    
                    # Scroll back up slowly to keep items in DOM
                    for pos in reversed(scroll_positions):
                        page.evaluate(f"window.scrollTo({{top: {pos}, behavior: 'smooth'}})")
                        page.wait_for_timeout(300)
                    
                    # Return to top for final screenshot
                    page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
                    page.wait_for_timeout(500)
                    
                    # Wait for any remaining lazy images to load
                    _wait_for_viewport_images(page, timeout_ms=2000)
                except Exception as e:
                    print(f"   ⚠️  Screenshot prep issue: {e}")

                # Use CDP to capture entire page in one pass (no viewport resize)
                capture_fullpage_static_no_resize(context, page, fullpage_path)
                print(f"✅ Full page (static, no resize): {fullpage_filename}")
            except Exception as e:
                print(f"⚠️  Could not capture full page: {e}")
            
            context.close()
            
            return True
            
    except PlaywrightTimeout as e:
        log(f"❌ Timeout: {e}")
        return False
    except Exception as e:
        error_msg = str(e)
        log(f"❌ EXCEPTION: {type(e).__name__}: {error_msg}")
        
        # Don't print full traceback for known errors
        if "ProcessSingleton" in error_msg or "SingletonLock" in error_msg:
            log("   Profile is locked by another browser instance.")
            log("   Close all Chromium windows and try again.")
        elif "Target page, context or browser has been closed" in error_msg:
            log("   Browser was closed unexpectedly.")
        else:
            # Print traceback for unexpected errors
            import traceback
            tb = traceback.format_exc()
            log(f"TRACEBACK:\n{tb}")
        
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Search Instacart and capture results')
    parser.add_argument('keyword', help='Search keyword')
    parser.add_argument('--output-dir', required=True, help='Output directory')
    parser.add_argument('--store', help='Store slug (default: publix or INSTACART_STORE env var)')
    
    args = parser.parse_args()
    
    success = search_and_capture(args.keyword, args.output_dir, args.store)
    sys.exit(0 if success else 1)
