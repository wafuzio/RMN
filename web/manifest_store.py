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


def built_at() -> str | None:
    """Get manifest build timestamp."""
    return _load().get("built_at")
