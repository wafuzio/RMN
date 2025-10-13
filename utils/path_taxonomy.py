"""
Retailer-specific folder taxonomy.
Prevents Kroger folders from leaking into other retailers.
"""
from pathlib import Path
from typing import Iterable

TAXONOMY = {
    "kroger": {
        "Carousel",
        "Skyscraper",
        "TOA",
        "Main",
        "runs",
    },
    "instacart": {
        "Display_Ads",
        "Shoppable_Display_Ads",
        "Shoppable_Video_Ads",
        "Main",
        "runs",
    },
    "amazon": {
        "Sponsored_Brand_Video",
        "Sponsored_Product",
        "Featured_Brand",
        "Sponsored_Carousel",
        "Main",
        "runs",
    },
    "walmart": {
        "Top_Banner",
        "SBA",
        "Tile_Takeover",
        "SBV",
        "Main",
        "runs",
    },
}


def allowed_subdirs(retailer: str) -> set[str]:
    """Get the allowed subdirectories for a retailer."""
    try:
        return TAXONOMY[retailer.lower()]
    except KeyError:
        raise ValueError(f"Unknown retailer: {retailer!r}")


def ensure_subdir(retailer: str, root: Path, subdir: str) -> Path:
    """
    Create a subdirectory only if it's allowed for the retailer.
    Raises ValueError if the subdir is not in the retailer's taxonomy.
    """
    subs = allowed_subdirs(retailer)
    if subdir not in subs:
        raise ValueError(f"Subdir {subdir!r} not allowed for retailer {retailer!r}")
    p = root / subdir
    p.mkdir(parents=True, exist_ok=True)
    return p
