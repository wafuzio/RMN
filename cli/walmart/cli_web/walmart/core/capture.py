"""Full-page ad intelligence capture engine.

Orchestrates:
  1. Response interception (attaches before page.goto)
  2. Page navigation with scroll passes
  3. __NEXT_DATA__ extraction (organic + in-grid sponsored)
  4. GraphQL ad payload parsing (AdV3 shelf + AdV2DisplayDSP banners)
  5. Creative screenshot capture (banner iframes)
  6. Video/asset download (MP4, HLS, VAST chains)
  7. Raw JSON dump for offline inspection

Usage::

    session = CaptureSession.run_search("coffee", output_dir=Path("./captures"))
    print(session.summary())
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

from .client import BASE_URL, PROFILE_DIR, _get_context
from .exceptions import NetworkError, WalmartError
from .interceptor import AdInterceptor, InterceptorResults
from .models import ProductDetail, SearchItem, SearchResults
from .runs import RunRecord, RunStore, make_run_id
from .video import download_creative, download_image, follow_vast_chain


# ── Session result ─────────────────────────────────────────────────────────────

@dataclass
class AdAsset:
    """A downloaded or URL-captured creative asset."""
    url: str
    local_path: Optional[str] = None   # relative to output_dir
    asset_type: str = "image"          # image | video | hls | vast_chain | screenshot
    size_bytes: int = 0

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "local_path": self.local_path,
            "asset_type": self.asset_type,
            "size_bytes": self.size_bytes,
        }


@dataclass
class BannerAd:
    """A rendered banner/display ad with screenshot + creative assets."""
    slot_name: str = ""              # e.g. "skyline1", "midpage2"
    ad_type: str = "banner"          # banner | video_banner | sbv
    template_id: str = ""
    variant_id: str = ""
    click_url: str = ""
    impression_urls: list[str] = field(default_factory=list)
    assets: list[AdAsset] = field(default_factory=list)
    screenshot_path: Optional[str] = None
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "slot_name": self.slot_name,
            "ad_type": self.ad_type,
            "template_id": self.template_id,
            "variant_id": self.variant_id,
            "click_url": self.click_url,
            "impression_urls": self.impression_urls,
            "assets": [a.to_dict() for a in self.assets],
            "screenshot_path": self.screenshot_path,
        }


@dataclass
class SponsoredAd:
    """A sponsored product ad (in-grid or shelf)."""
    ad_uuid: str = ""
    item_id: str = ""
    offer_id: str = ""
    template_id: str = ""
    name: str = ""
    price: str = ""
    ad_type: str = "sponsored_product"   # sponsored_product | shelf
    assets: list[AdAsset] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "ad_uuid": self.ad_uuid,
            "item_id": self.item_id,
            "offer_id": self.offer_id,
            "template_id": self.template_id,
            "name": self.name,
            "price": self.price,
            "ad_type": self.ad_type,
            "assets": [a.to_dict() for a in self.assets],
        }


@dataclass
class CaptureResult:
    """Full result of one capture session."""
    run_id: str
    query: str
    url: str
    page: int
    timestamp: str
    output_dir: str

    # Organic items (all, incl. lazy-loaded)
    organic_items: list[dict] = field(default_factory=list)

    # In-grid sponsored items (from __NEXT_DATA__)
    sponsored_items: list[dict] = field(default_factory=list)

    # Shelf/AdV3 sponsored ads (from orchestra GraphQL)
    sponsored_ads: list[SponsoredAd] = field(default_factory=list)

    # Display/DSP banner ads (from swag GraphQL)
    banner_ads: list[BannerAd] = field(default_factory=list)

    # All video URLs found (before download)
    video_urls: list[str] = field(default_factory=list)

    # VAST chains resolved
    vast_chains: list[dict] = field(default_factory=list)   # {vast_url, media_urls}

    # Raw interceptor dump path (for debugging)
    raw_dump_path: Optional[str] = None

    errors: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "run_id": self.run_id,
            "query": self.query,
            "url": self.url,
            "page": self.page,
            "timestamp": self.timestamp,
            "organic_item_count": len(self.organic_items),
            "sponsored_item_count": len(self.sponsored_items),
            "sponsored_ad_count": len(self.sponsored_ads),
            "banner_ad_count": len(self.banner_ads),
            "video_url_count": len(self.video_urls),
            "vast_chain_count": len(self.vast_chains),
            "errors": self.errors,
        }

    def to_dict(self) -> dict:
        return {
            **self.summary(),
            "organic_items": self.organic_items,
            "sponsored_items": self.sponsored_items,
            "sponsored_ads": [a.to_dict() for a in self.sponsored_ads],
            "banner_ads": [a.to_dict() for a in self.banner_ads],
            "video_urls": self.video_urls,
            "vast_chains": self.vast_chains,
        }


# ── Main capture function ─────────────────────────────────────────────────────

def run_capture(
    url: str,
    query: str,
    page: int = 1,
    output_dir: Optional[Path] = None,
    download_videos: bool = True,
    download_images: bool = True,
    screenshot_banners: bool = True,
    scroll_passes: int = 3,
    scroll_pause_ms: int = 2000,
    run_id: Optional[str] = None,
    store: Optional[RunStore] = None,
) -> CaptureResult:
    """Execute a full-page ad intelligence capture.

    Args:
        url: Full Walmart page URL.
        query: Human-readable label (search query or category path).
        page: Page number (for metadata).
        output_dir: Where to save assets. Created if needed.
        download_videos: Fetch and save video MP4/HLS files.
        download_images: Fetch and save creative image files.
        screenshot_banners: Screenshot rendered banner ad elements.
        scroll_passes: Number of scroll-to-bottom passes (each triggers lazy loads).
        scroll_pause_ms: Milliseconds to wait between scroll passes.
        run_id: Override auto-generated run ID.
        store: RunStore instance (created if not provided).

    Returns:
        CaptureResult with all extracted data and asset paths.
    """
    if run_id is None:
        run_id = make_run_id(query)

    timestamp = datetime.now(timezone.utc).isoformat()

    if output_dir is None:
        output_dir = Path.cwd() / "captures" / run_id
    else:
        output_dir = Path(output_dir) / run_id

    output_dir.mkdir(parents=True, exist_ok=True)

    result = CaptureResult(
        run_id=run_id,
        query=query,
        url=url,
        page=page,
        timestamp=timestamp,
        output_dir=str(output_dir),
    )

    ctx = _get_context()
    pw_page = ctx.new_page()

    interceptor = AdInterceptor()
    interceptor.attach(pw_page)

    try:
        # ── Navigate ───────────────────────────────────────────────────────────
        try:
            pw_page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            if "timeout" not in str(e).lower():
                raise NetworkError(f"Navigation failed: {e}") from e

        # Block check
        current_url = pw_page.url
        if "blocked" in current_url or "captcha" in current_url.lower():
            raise WalmartError("Walmart blocked this request.")

        # ── Extract __NEXT_DATA__ ──────────────────────────────────────────────
        raw_nd = pw_page.evaluate(
            "() => { const el = document.getElementById('__NEXT_DATA__'); "
            "return el ? el.textContent : null; }"
        )
        if raw_nd:
            nd = json.loads(raw_nd)
            _extract_next_data(nd, result)

        # ── Scroll passes ──────────────────────────────────────────────────────
        for i in range(scroll_passes):
            _scroll_pass(pw_page, i, scroll_passes, scroll_pause_ms)

        # Final networkidle wait (cap at 5s)
        try:
            pw_page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

        # ── Harvest interceptor ────────────────────────────────────────────────
        intercepted = interceptor.harvest()

        # Merge lazy-loaded items
        for item in intercepted.lazy_items:
            item_id = str(item.get("usItemId", ""))
            existing_ids = {i.get("item_id") for i in result.organic_items}
            if item_id and item_id not in existing_ids:
                si = SearchItem.from_dict(item)
                result.organic_items.append(si.to_dict())

        # Parse shelf sponsored ads
        for raw_ad in intercepted.sponsored_shelf_ads:
            result.sponsored_ads.append(_parse_sponsored_ad(raw_ad))

        # Parse display/DSP banners
        for raw_ad in intercepted.display_banner_ads:
            result.banner_ads.append(_parse_banner_ad(raw_ad))

        # Collect video URLs
        result.video_urls = list(dict.fromkeys(intercepted.video_urls))  # dedupe

        # ── Screenshot banners ─────────────────────────────────────────────────
        if screenshot_banners:
            _screenshot_banners(pw_page, result, output_dir)

        # ── Save raw dump ──────────────────────────────────────────────────────
        raw_path = output_dir / "raw_interceptor.json"
        _save_raw(intercepted, raw_path)
        result.raw_dump_path = str(raw_path)

    finally:
        pw_page.close()

    # ── Download assets (outside playwright page) ──────────────────────────────
    if download_videos and result.video_urls:
        _download_videos(result, output_dir)

    if download_videos and intercepted.vast_urls:
        _resolve_vast_chains(intercepted.vast_urls, result, output_dir)

    if download_images:
        _download_creative_images(intercepted.asset_urls, result, output_dir)

    # ── Persist run record ─────────────────────────────────────────────────────
    _save_session_json(result, output_dir)

    if store is None:
        store = RunStore()

    run_rec = RunRecord(
        run_id=run_id,
        query=query,
        url=url,
        page=page,
        timestamp=timestamp,
        output_dir=str(output_dir),
        item_count=len(result.organic_items) + len(result.sponsored_items),
        ad_count=len(result.sponsored_ads) + len(result.sponsored_items),
        banner_count=len(result.banner_ads),
    )
    store.save_run(run_rec)

    all_ads = [ad.raw for ad in result.sponsored_ads] + [ad.raw for ad in result.banner_ads]
    if all_ads:
        store.save_fingerprints(run_id, all_ads, "ad")

    return result


# ── Scroll helper ─────────────────────────────────────────────────────────────

def _scroll_pass(page, pass_num: int, total_passes: int, pause_ms: int) -> None:
    """Execute one scroll pass: mid-page → bottom, with pause."""
    try:
        if pass_num == 0:
            # First pass: scroll to 50% to trigger mid-page ad loads
            page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.5)")
            page.wait_for_timeout(pause_ms // 2)

        # Scroll to bottom
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(pause_ms)

        # Last pass: scroll back to top (some lazy loaders need this)
        if pass_num == total_passes - 1:
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(500)
    except Exception:
        pass


# ── __NEXT_DATA__ extraction ──────────────────────────────────────────────────

def _extract_next_data(nd: dict, result: CaptureResult) -> None:
    """Pull organic and sponsored items from __NEXT_DATA__."""
    try:
        props = nd.get("props", {}).get("pageProps", {})
        initial = props.get("initialData", {})

        # Search / browse results
        sr = initial.get("searchResult", {})
        stacks = sr.get("itemStacks", [])
        for stack in stacks:
            for item in stack.get("items", []):
                if not isinstance(item, dict) or not item.get("name"):
                    continue
                si = SearchItem.from_dict(item)
                d = si.to_dict()
                if si.is_sponsored:
                    result.sponsored_items.append(d)
                else:
                    result.organic_items.append(d)

        # Product detail page
        product = initial.get("data", {}).get("product")
        if product and isinstance(product, dict):
            pd = ProductDetail.from_dict(product)
            result.organic_items.append(pd.to_dict())

    except Exception as e:
        result.errors.append(f"__NEXT_DATA__ parse error: {e}")


# ── Ad parsers ────────────────────────────────────────────────────────────────

def _parse_sponsored_ad(raw: dict) -> SponsoredAd:
    """Build a SponsoredAd from a raw AdV3 payload dict."""
    # AdV3 may nest items in an 'items' list or expose fields directly
    items = raw.get("items", [raw])
    first = items[0] if items else raw

    price_info = first.get("priceInfo") or {}
    price = (
        price_info.get("linePrice") or
        (price_info.get("currentPrice") or {}).get("priceString") or ""
    )

    ad = SponsoredAd(
        ad_uuid=raw.get("adUuid", ""),
        item_id=str(first.get("usItemId", "")),
        offer_id=first.get("offerId", ""),
        template_id=raw.get("templateId", ""),
        name=first.get("name", ""),
        price=price,
        ad_type="shelf",
        raw=raw,
    )

    # Collect image assets from adExpInfo or product image
    exp = raw.get("adExpInfo") or {}
    for field_name in ("creativeUrl", "imageUrl", "thumbnailUrl"):
        if url := exp.get(field_name) or first.get("imageInfo", {}).get("thumbnailUrl"):
            if url and url.startswith("http"):
                ad.assets.append(AdAsset(url=url, asset_type="image"))
                break

    return ad


def _parse_banner_ad(raw: dict) -> BannerAd:
    """Build a BannerAd from a raw AdV2DisplayDSP payload dict."""
    assets_raw = raw.get("assets") or raw.get("creative") or {}
    event_trackers = raw.get("eventTrackers") or []

    banner = BannerAd(
        slot_name=raw.get("slotName") or raw.get("placement") or raw.get("moduleType") or "",
        ad_type="banner",
        template_id=raw.get("templateId", ""),
        variant_id=raw.get("variantId", ""),
        click_url=raw.get("link") or raw.get("clickUrl") or "",
        impression_urls=event_trackers if isinstance(event_trackers, list) else [],
        raw=raw,
    )

    # Image asset
    if isinstance(assets_raw, dict):
        for field_name in ("imageUrl", "image", "creativeUrl", "thumbnailUrl"):
            img = assets_raw.get(field_name)
            if isinstance(img, str) and img.startswith("http"):
                banner.assets.append(AdAsset(url=img, asset_type="image"))
                break
            elif isinstance(img, dict) and (u := img.get("url")):
                banner.assets.append(AdAsset(url=u, asset_type="image"))
                break

        # Video asset
        for field_name in ("videoUrl", "video", "mediaUrl"):
            vid = assets_raw.get(field_name)
            if isinstance(vid, str) and vid.startswith("http"):
                banner.assets.append(AdAsset(url=vid, asset_type="video"))
                break
            elif isinstance(vid, dict) and (u := vid.get("url")):
                banner.assets.append(AdAsset(url=u, asset_type="video"))
                break

    return banner


# ── Screenshot banners ────────────────────────────────────────────────────────

def _screenshot_banners(page, result: CaptureResult, output_dir: Path) -> None:
    """Screenshot all banner ad containers and ad iframes on the page."""
    screenshot_dir = output_dir / "assets" / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    captured = 0

    # 1. Try known banner container selectors
    banner_selectors = [
        '[data-testid*="sponsored-display"]',
        '[data-testid*="banner"]',
        '[class*="sponsored-banner"]',
        '[class*="display-ad"]',
        '[class*="banner-ad"]',
        '[data-ad-slot]',
        '.ad-container',
        '[id*="banner"]',
    ]

    for selector in banner_selectors:
        try:
            elements = page.locator(selector).all()
            for i, el in enumerate(elements[:10]):  # cap at 10 per selector
                try:
                    box = el.bounding_box()
                    if not box or box["width"] < 50 or box["height"] < 20:
                        continue
                    slug = selector.replace("[", "").replace("]", "").replace("*=", "_").replace('"', "")[:20]
                    fname = f"banner_{captured:03d}_{slug}.png"
                    path = screenshot_dir / fname
                    el.screenshot(path=str(path))
                    captured += 1

                    # Find which banner_ad this screenshot belongs to (by position)
                    if result.banner_ads and captured <= len(result.banner_ads):
                        result.banner_ads[captured - 1].screenshot_path = str(
                            path.relative_to(output_dir)
                        )
                except Exception:
                    continue
        except Exception:
            continue

    # 2. Screenshot ad iframes (catches Google DFP / DoubleClick banners)
    try:
        frames = page.frames
        if callable(frames):
            frames = frames()
        for i, frame in enumerate(frames):
            try:
                frame_url = frame.url
                if not frame_url or frame_url in ("about:blank", ""):
                    continue
                if any(domain in frame_url for domain in
                       ("doubleclick", "googlesyndication", "walmart.com/ads",
                        "advertising", "adsystem", "adnxs")):
                    fname = f"iframe_ad_{i:03d}.png"
                    path = screenshot_dir / fname

                    # Screenshot the frame's root element
                    frame.locator("body").screenshot(path=str(path))
                    captured += 1

                    # Attach to a banner_ad if we have unmatched ones
                    for banner in result.banner_ads:
                        if banner.screenshot_path is None:
                            banner.screenshot_path = str(path.relative_to(output_dir))
                            break
            except Exception:
                continue
    except Exception:
        pass

    # 3. Full-page screenshot as fallback reference
    try:
        ref_path = screenshot_dir / "full_page.png"
        page.screenshot(path=str(ref_path), full_page=True)
    except Exception:
        pass


# ── Asset downloads ───────────────────────────────────────────────────────────

def _download_videos(result: CaptureResult, output_dir: Path) -> None:
    """Download all captured video URLs."""
    video_dir = output_dir / "assets" / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)

    for url in result.video_urls:
        try:
            path = download_creative(url, video_dir)
            if path:
                asset = AdAsset(
                    url=url,
                    local_path=str(path.relative_to(output_dir)),
                    asset_type="video",
                    size_bytes=path.stat().st_size,
                )
                # Attach to the matching banner or sponsored ad
                _attach_asset(asset, result)
        except Exception as e:
            result.errors.append(f"Video download failed for {url}: {e}")


def _resolve_vast_chains(vast_urls: list[str], result: CaptureResult, output_dir: Path) -> None:
    """Follow VAST redirect chains and download final video media."""
    video_dir = output_dir / "assets" / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)

    seen = set()
    for vast_url in vast_urls:
        if vast_url in seen:
            continue
        seen.add(vast_url)
        try:
            media_urls = follow_vast_chain(vast_url)
            chain_record = {"vast_url": vast_url, "media_urls": media_urls}
            result.vast_chains.append(chain_record)

            # Download first (best quality) media URL
            if media_urls:
                path = download_creative(media_urls[0], video_dir, prefix="vast_")
                if path:
                    asset = AdAsset(
                        url=media_urls[0],
                        local_path=str(path.relative_to(output_dir)),
                        asset_type="video",
                        size_bytes=path.stat().st_size,
                    )
                    _attach_asset(asset, result)
        except Exception as e:
            result.errors.append(f"VAST chain failed for {vast_url}: {e}")


def _download_creative_images(asset_urls: list[str], result: CaptureResult, output_dir: Path) -> None:
    """Download creative image assets from CDN."""
    img_dir = output_dir / "assets" / "images"
    img_dir.mkdir(parents=True, exist_ok=True)

    seen = set()
    for url in asset_urls:
        if url in seen:
            continue
        seen.add(url)
        try:
            path = download_image(url, img_dir)
            if path:
                asset = AdAsset(
                    url=url,
                    local_path=str(path.relative_to(output_dir)),
                    asset_type="image",
                    size_bytes=path.stat().st_size,
                )
                _attach_asset(asset, result)
        except Exception:
            pass


def _attach_asset(asset: AdAsset, result: CaptureResult) -> None:
    """Attach a downloaded asset to the best-matching ad in result."""
    url = asset.url
    # Try to match by URL fragment to a known ad
    for banner in result.banner_ads:
        for existing in banner.assets:
            if existing.url == url:
                existing.local_path = asset.local_path
                existing.size_bytes = asset.size_bytes
                return
    for ad in result.sponsored_ads:
        for existing in ad.assets:
            if existing.url == url:
                existing.local_path = asset.local_path
                existing.size_bytes = asset.size_bytes
                return


# ── Save helpers ──────────────────────────────────────────────────────────────

def _save_session_json(result: CaptureResult, output_dir: Path) -> None:
    """Write per-section JSON files for easy inspection."""
    files = {
        "session.json": result.summary(),
        "organic.json": {"items": result.organic_items},
        "sponsored.json": {
            "in_grid": result.sponsored_items,
            "shelf_ads": [a.to_dict() for a in result.sponsored_ads],
        },
        "banners.json": {"ads": [a.to_dict() for a in result.banner_ads]},
        "videos.json": {
            "direct_urls": result.video_urls,
            "vast_chains": result.vast_chains,
        },
    }
    for fname, data in files.items():
        path = output_dir / fname
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def _save_raw(intercepted: InterceptorResults, path: Path) -> None:
    """Dump raw interceptor payloads for offline schema inspection."""
    raw = {
        "orchestra_payloads": [
            {"url": e["url"], "body": e["body"]} for e in intercepted.orchestra_payloads
        ],
        "swag_payloads": [
            {"url": e["url"], "body": e["body"]} for e in intercepted.swag_payloads
        ],
        "video_urls": intercepted.video_urls,
        "vast_urls": intercepted.vast_urls,
        "asset_urls": intercepted.asset_urls,
    }
    path.write_text(json.dumps(raw, indent=2, ensure_ascii=False, default=str))
