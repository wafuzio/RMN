"""
Run manifest loader with auto-reload on file change.

Provides fast access to run metadata without scanning filesystem.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = PROJECT_ROOT / "cache" / "run_manifest.json"

_cache: Dict[str, Any] = {}
_mtime: float = 0.0


def _load() -> Dict[str, Any]:
    """Load manifest with mtime-based cache invalidation."""
    global _cache, _mtime
    
    if not MANIFEST.exists():
        return {"runs": [], "daily_totals": {}, "built_at": None}
    
    st = MANIFEST.stat().st_mtime
    if st != _mtime:
        _cache = json.loads(MANIFEST.read_text(encoding="utf-8"))
        _mtime = st
        print(f"✅ Manifest loaded: {len(_cache.get('runs', []))} runs")
    
    return _cache


def runs() -> List[Dict[str, Any]]:
    """Get all run metadata (sorted newest first)."""
    return _load().get("runs", [])


def daily_totals() -> Dict[str, Any]:
    """Get daily totals by retailer/client/day."""
    return _load().get("daily_totals", {})


def brands() -> Dict[str, List[Dict[str, Any]]]:
    """Get pre-computed brand counts by retailer.
    
    Returns: {retailer: [{brand, count, percentage}, ...], ...}
    """
    return _load().get("brands", {})


def brands_by_client() -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    """Get pre-computed brand counts by retailer and client.
    
    Returns: {retailer: {client: [{brand, count, percentage}, ...], ...}, ...}
    """
    return _load().get("brands_by_client", {})


def unknown_ad_counts() -> Dict[str, int]:
    """Get count of unknown-brand ads by retailer.

    These are ads where the scraper could not identify the advertiser brand.
    Returns: {retailer: count_of_unknown_brand_ads}
    """
    return _load().get("unknown_ad_counts", {})


def unknown_ad_counts_by_client() -> Dict[str, Dict[str, int]]:
    """Get count of unknown-brand ads by retailer and client.

    Returns: {retailer: {client: count_of_unknown_brand_ads}}
    """
    return _load().get("unknown_ad_counts_by_client", {})


def creative_fingerprints() -> Dict[str, str]:
    """Get creative fingerprint index for brand propagation.

    Maps fingerprint keys (logo UUID, image UUID, normalized href) to the
    canonical brand name identified for that creative asset.  Used by the
    server to recover the brand for null-brand ads that share a CDN asset or
    href with a previously-identified ad.

    Returns: {"logo:<uuid>": "BrandName", "img:<uuid>": "BrandName",
              "href:<path>": "BrandName", ...}
    """
    return _load().get("creative_fingerprints", {})


def built_at() -> str | None:
    """Get manifest build timestamp."""
    return _load().get("built_at")
