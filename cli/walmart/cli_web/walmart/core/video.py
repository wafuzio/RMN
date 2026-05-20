"""Video and creative asset downloader for ad intelligence capture.

Handles three video delivery formats:
- Direct MP4/WebM URLs → simple HTTP download
- HLS (.m3u8) playlists → parse manifest, download segments, concatenate
- VAST/VPAID XML tags → follow redirect chain → extract MediaFile → download

VAST chains can be nested up to 5 levels deep (VAST wrapper → VAST wrapper → inline).
We follow the chain and collect every MediaFile URL found.
"""
from __future__ import annotations

import hashlib
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx

from .exceptions import NetworkError


# ── Constants ─────────────────────────────────────────────────────────────────

MAX_VAST_DEPTH = 5
DOWNLOAD_TIMEOUT = 30          # seconds per file
SEGMENT_TIMEOUT = 10           # seconds per HLS segment
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}


# ── Public API ────────────────────────────────────────────────────────────────

def download_creative(url: str, dest_dir: Path, prefix: str = "") -> Optional[Path]:
    """Download a creative asset (image or video) to dest_dir.

    Detects format from URL/Content-Type and routes to the right downloader.
    Returns the saved file path, or None if download fails.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    if _is_hls(url):
        return _download_hls(url, dest_dir, prefix)
    elif _is_vast(url):
        mp4_urls = follow_vast_chain(url)
        if mp4_urls:
            return _download_mp4(mp4_urls[0], dest_dir, prefix)
        return None
    else:
        return _download_mp4(url, dest_dir, prefix)


def follow_vast_chain(vast_url: str, depth: int = 0) -> list[str]:
    """Follow a VAST/VPAID redirect chain and return all MediaFile URLs found.

    Recursively follows VASTAdTagURI wrappers. Collects MediaFile URLs from
    every level (some wrappers also include inline media).

    Args:
        vast_url: URL returning VAST XML.
        depth: Current recursion depth (stops at MAX_VAST_DEPTH).

    Returns:
        List of direct media file URLs, best quality first.
    """
    if depth >= MAX_VAST_DEPTH:
        return []

    try:
        with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=10) as client:
            resp = client.get(vast_url)
            if resp.status_code != 200:
                return []
            content = resp.text.strip()
    except Exception:
        return []

    if not content or not content.startswith("<"):
        return []

    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return []

    media_urls: list[str] = []

    # Collect MediaFile URLs from this level
    for media_file in root.iter("MediaFile"):
        url = (media_file.text or "").strip()
        if url and url.startswith("http"):
            delivery = media_file.get("delivery", "").lower()
            mime = media_file.get("type", "").lower()
            # Prefer progressive MP4 over streaming; skip Flash
            if "javascript" not in mime and "flash" not in mime.lower():
                media_urls.append(url)

    # Follow wrapper chain
    for wrapper_tag in root.iter("VASTAdTagURI"):
        wrapper_url = (wrapper_tag.text or "").strip()
        if wrapper_url and wrapper_url.startswith("http"):
            media_urls.extend(follow_vast_chain(wrapper_url, depth + 1))

    # Sort: prefer MP4 progressive delivery
    media_urls.sort(key=lambda u: (
        0 if ".mp4" in u.lower() else
        1 if ".webm" in u.lower() else
        2
    ))

    return media_urls


def download_image(url: str, dest_dir: Path, prefix: str = "") -> Optional[Path]:
    """Download a creative image asset."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=DOWNLOAD_TIMEOUT) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return None
            ext = _ext_from_response(resp, url, default=".jpg")
            slug = _url_slug(url)
            fname = f"{prefix}{slug}{ext}" if prefix else f"{slug}{ext}"
            dest = dest_dir / fname
            dest.write_bytes(resp.content)
            return dest
    except Exception:
        return None


# ── Internal helpers ──────────────────────────────────────────────────────────

def _download_mp4(url: str, dest_dir: Path, prefix: str = "") -> Optional[Path]:
    """Download a direct video file (MP4/WebM/etc.) with streaming."""
    try:
        slug = _url_slug(url)
        ext = _ext_from_url(url, ".mp4")
        fname = f"{prefix}{slug}{ext}" if prefix else f"{slug}{ext}"
        dest = dest_dir / fname

        with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=DOWNLOAD_TIMEOUT) as client:
            with client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    return None
                with open(dest, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=65536):
                        f.write(chunk)
        return dest
    except Exception:
        return None


def _download_hls(m3u8_url: str, dest_dir: Path, prefix: str = "") -> Optional[Path]:
    """Download an HLS stream: parse master → find best variant → download segments → concat.

    Falls back to saving the playlist URL if segment download fails.
    """
    try:
        with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=10) as client:
            resp = client.get(m3u8_url)
            if resp.status_code != 200:
                return None
            playlist = resp.text

        base_url = m3u8_url.rsplit("/", 1)[0] + "/"

        # If this is a master playlist, find the best variant (highest bandwidth)
        if "#EXT-X-STREAM-INF" in playlist:
            variant_url = _best_variant(playlist, base_url)
            if not variant_url:
                return None
            return _download_hls(variant_url, dest_dir, prefix)

        # Media playlist — download segments
        segment_urls = _parse_segments(playlist, base_url)
        if not segment_urls:
            return None

        slug = _url_slug(m3u8_url)
        dest = dest_dir / f"{prefix}{slug}.ts"

        with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=SEGMENT_TIMEOUT) as client:
            with open(dest, "wb") as f:
                for seg_url in segment_urls:
                    try:
                        seg_resp = client.get(seg_url)
                        if seg_resp.status_code == 200:
                            f.write(seg_resp.content)
                    except Exception:
                        continue  # skip failed segments

        return dest if dest.stat().st_size > 0 else None

    except Exception:
        return None


def _best_variant(master_playlist: str, base_url: str) -> Optional[str]:
    """Find the highest-bandwidth variant stream in a master HLS playlist."""
    best_url = None
    best_bw = -1
    lines = master_playlist.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF"):
            bw_match = re.search(r"BANDWIDTH=(\d+)", line)
            bw = int(bw_match.group(1)) if bw_match else 0
            if bw > best_bw and i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and not next_line.startswith("#"):
                    best_bw = bw
                    best_url = urljoin(base_url, next_line)
    return best_url


def _parse_segments(media_playlist: str, base_url: str) -> list[str]:
    """Extract segment URLs from a media HLS playlist."""
    segments = []
    for line in media_playlist.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            segments.append(urljoin(base_url, line))
    return segments


def _is_hls(url: str) -> bool:
    return ".m3u8" in url.lower() or "hls" in url.lower()


def _is_vast(url: str) -> bool:
    return bool(re.search(r"(vast|vpaid|adtag|adsystem)", url, re.I))


def _url_slug(url: str) -> str:
    """Generate a short stable filename-safe slug from a URL."""
    parsed = urlparse(url)
    path_part = parsed.path.rsplit("/", 1)[-1].split("?")[0]
    # If path has a clean filename, use it (max 40 chars)
    if path_part and "." in path_part:
        clean = re.sub(r"[^\w\-.]", "_", path_part)[:40]
        return clean
    # Fallback: hash of full URL
    return hashlib.md5(url.encode()).hexdigest()[:12]


def _ext_from_url(url: str, default: str = ".bin") -> str:
    """Extract file extension from URL path."""
    path = urlparse(url).path
    if "." in path:
        ext = "." + path.rsplit(".", 1)[-1].split("?")[0].lower()
        if len(ext) <= 5:
            return ext
    return default


def _ext_from_response(resp, url: str, default: str = ".bin") -> str:
    """Determine file extension from Content-Type header or URL."""
    ct = resp.headers.get("content-type", "").split(";")[0].strip().lower()
    mime_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/svg+xml": ".svg",
        "video/mp4": ".mp4",
        "video/webm": ".webm",
        "application/x-mpegurl": ".m3u8",
        "application/vnd.apple.mpegurl": ".m3u8",
    }
    return mime_map.get(ct) or _ext_from_url(url, default)
