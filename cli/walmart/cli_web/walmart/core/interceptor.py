"""Response interceptor for ad intelligence capture.

Attaches to a Playwright page *before* navigation and captures every
ad-relevant network response: GraphQL ad payloads, creative asset URLs,
video manifests, and VAST tags.

Usage::

    interceptor = AdInterceptor()
    page = ctx.new_page()
    interceptor.attach(page)
    page.goto(url, ...)
    # ... scroll passes ...
    results = interceptor.harvest()
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


# URL patterns that carry ad data
_ORCHESTRA_RE = re.compile(r"/orchestra/(home|pdp|api)/graphql")
_SWAG_RE = re.compile(r"/swag/graphql")
_VIDEO_RE = re.compile(r"\.(mp4|m3u8|mpd|webm|mov)(\?|$)", re.I)
_VAST_RE = re.compile(r"(vast|vpaid|adtag|adsystem)", re.I)
_AD_IMAGE_RE = re.compile(r"(creative|banner|ad[_-]image|sponsoredAsset)", re.I)


@dataclass
class RawAdResponse:
    url: str
    source: str          # "orchestra" | "swag" | "video" | "vast" | "asset"
    body: Any = None     # parsed JSON or raw text
    error: str = ""


@dataclass
class InterceptorResults:
    orchestra_payloads: list[dict] = field(default_factory=list)
    swag_payloads: list[dict] = field(default_factory=list)
    video_urls: list[str] = field(default_factory=list)
    vast_urls: list[str] = field(default_factory=list)
    asset_urls: list[str] = field(default_factory=list)
    raw: list[RawAdResponse] = field(default_factory=list)

    # Parsed ad structures (populated by harvest())
    sponsored_shelf_ads: list[dict] = field(default_factory=list)   # AdV3
    display_banner_ads: list[dict] = field(default_factory=list)    # AdV2DisplayDSP
    lazy_items: list[dict] = field(default_factory=list)            # post-scroll items


class AdInterceptor:
    """Attaches to a Playwright page and silently captures ad network calls."""

    def __init__(self):
        self._results = InterceptorResults()

    def attach(self, page) -> None:
        """Register response handler. MUST be called before page.goto()."""
        page.on("response", self._on_response)

    def _on_response(self, response) -> None:
        url = response.url
        try:
            if _ORCHESTRA_RE.search(url):
                self._capture_json(url, "orchestra", response)
            elif _SWAG_RE.search(url):
                self._capture_json(url, "swag", response)
            elif _VIDEO_RE.search(url):
                self._results.video_urls.append(url)
                self._results.raw.append(RawAdResponse(url=url, source="video"))
            elif _VAST_RE.search(url):
                self._results.vast_urls.append(url)
                self._results.raw.append(RawAdResponse(url=url, source="vast"))
            elif _AD_IMAGE_RE.search(url):
                self._results.asset_urls.append(url)
        except Exception:
            pass

    def _capture_json(self, url: str, source: str, response) -> None:
        try:
            # Only capture responses that look like JSON
            ct = response.headers.get("content-type", "")
            if "json" not in ct and "graphql" not in url:
                return
            body = response.json()
            raw = RawAdResponse(url=url, source=source, body=body)
            self._results.raw.append(raw)
            if source == "orchestra":
                self._results.orchestra_payloads.append({"url": url, "body": body})
            else:
                self._results.swag_payloads.append({"url": url, "body": body})
        except Exception as e:
            self._results.raw.append(RawAdResponse(url=url, source=source, error=str(e)))

    def harvest(self) -> InterceptorResults:
        """Parse all captured payloads into structured ad objects. Call after scrolling."""
        r = self._results

        for entry in r.orchestra_payloads:
            body = entry.get("body", {})
            self._parse_orchestra(body, r)

        for entry in r.swag_payloads:
            body = entry.get("body", {})
            self._parse_swag(body, r)

        return r

    # ── Parsers ───────────────────────────────────────────────────────────────

    def _parse_orchestra(self, body: dict, r: InterceptorResults) -> None:
        """Extract sponsored shelf ads and lazy-loaded item stacks from orchestra GraphQL."""
        data = body.get("data") or {}

        # Walk the full response tree looking for known structures
        self._walk_for_sponsored(data, r)
        self._walk_for_item_stacks(data, r)

    def _walk_for_sponsored(self, node: Any, r: InterceptorResults, depth: int = 0) -> None:
        """Recursively find sponsoredProducts / adV3 / sponsoredShelf nodes."""
        if depth > 8 or not isinstance(node, dict):
            return
        for key, val in node.items():
            if key in ("sponsoredProducts", "adV3", "sponsoredShelf", "sponsoredAds"):
                ads = val if isinstance(val, list) else val.get("ads", []) if isinstance(val, dict) else []
                for ad in ads:
                    if isinstance(ad, dict):
                        r.sponsored_shelf_ads.append(ad)
                        # Collect any video/asset URLs embedded in the ad
                        self._collect_media_from_ad(ad, r)
            elif isinstance(val, dict):
                self._walk_for_sponsored(val, r, depth + 1)
            elif isinstance(val, list):
                for item in val:
                    self._walk_for_sponsored(item, r, depth + 1)

    def _walk_for_item_stacks(self, node: Any, r: InterceptorResults, depth: int = 0) -> None:
        """Find itemStacks from lazy-loaded search responses (post-scroll XHR)."""
        if depth > 6 or not isinstance(node, dict):
            return
        for key, val in node.items():
            if key == "itemStacks" and isinstance(val, list):
                for stack in val:
                    for item in (stack.get("items", []) if isinstance(stack, dict) else []):
                        if isinstance(item, dict) and item.get("name"):
                            r.lazy_items.append(item)
            elif isinstance(val, dict):
                self._walk_for_item_stacks(val, r, depth + 1)

    def _parse_swag(self, body: dict, r: InterceptorResults) -> None:
        """Extract display/DSP banner ads from swag GraphQL."""
        data = body.get("data") or {}
        self._walk_for_display_ads(data, r)

    def _walk_for_display_ads(self, node: Any, r: InterceptorResults, depth: int = 0) -> None:
        """Find AdV2DisplayDSP / displayAd / bannerAd nodes."""
        if depth > 8 or not isinstance(node, dict):
            return
        for key, val in node.items():
            if key in ("adV2DisplayDSP", "multiImpDspAd", "displayAdDSP",
                       "displayAd", "bannerAd", "dspAd"):
                ads = val if isinstance(val, list) else [val] if isinstance(val, dict) else []
                for ad in ads:
                    if isinstance(ad, dict):
                        r.display_banner_ads.append(ad)
                        self._collect_media_from_ad(ad, r)
            elif isinstance(val, dict):
                self._walk_for_display_ads(val, r, depth + 1)
            elif isinstance(val, list):
                for item in val:
                    self._walk_for_display_ads(item, r, depth + 1)

    def _collect_media_from_ad(self, ad: dict, r: InterceptorResults) -> None:
        """Pull video/image asset URLs out of any ad object."""
        ad_str = json.dumps(ad)

        # Video URLs embedded in ad payload
        for match in _VIDEO_RE.finditer(ad_str):
            # Extract the full URL from surrounding context
            start = max(0, match.start() - 200)
            chunk = ad_str[start:match.end() + 50]
            url_match = re.search(r'https?://[^\s"\'\\]+' + re.escape(match.group(0).split("?")[0]), chunk)
            if url_match:
                url = url_match.group(0).rstrip('",\\')
                if url not in r.video_urls:
                    r.video_urls.append(url)

        # VAST tag URLs
        for match in re.finditer(r'https?://[^\s"\'\\]*(?:vast|vpaid|adtag)[^\s"\'\\]*', ad_str, re.I):
            url = match.group(0).rstrip('",\\')
            if url not in r.vast_urls:
                r.vast_urls.append(url)

        # Creative image URLs
        assets = ad.get("assets") or ad.get("creative") or {}
        if isinstance(assets, dict):
            for field_name in ("imageUrl", "image", "thumbnailUrl", "creativeUrl"):
                if url := assets.get(field_name):
                    if isinstance(url, str) and url.startswith("http"):
                        r.asset_urls.append(url)
                    elif isinstance(url, dict) and (u := url.get("url")):
                        r.asset_urls.append(u)
