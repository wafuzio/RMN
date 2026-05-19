# utils/path_taxonomy.py

from typing import Dict, Set, Tuple
from pathlib import Path

# Canonical label → folder name mapping for Walmart ad types.
# This is the single source of truth: add a new ad type here and
# both the save path and the allowed-folder check stay in sync.
WALMART_LABEL_TO_FOLDER: Dict[str, str] = {
    "skyline":       "Skyline",
    "marquee_banner":"Marquee_Banner",
    "sba":           "SBA",
    "sbv":           "SBV",
    "tile_takeover": "Tile_Takeover",
    "gallery_cards": "Gallery_Cards",
}

# Canonical allowed folders per retailer — Walmart's set is derived from
# WALMART_LABEL_TO_FOLDER so the two can never drift apart.
ALLOWED_FOLDERS: Dict[str, Set[str]] = {
    "kroger": {"TOA", "Skyscraper", "Carousel", "Display_Ads", "Main", "runs"},
    "walmart": set(WALMART_LABEL_TO_FOLDER.values()) | {"Main", "runs"},
    "instacart": {"Shoppable_Display_Ads", "Shoppable_Video_Ads", "Shoppable_Display_Ad", "Shoppable_Video_Ad", "Shoppable_Recipe_Ads", "Display_Ads", "Main", "runs"},
    "amazon": {"Sponsored_Brand", "Sponsored_Product", "Sponsored_Display", "Main", "runs"},
    # Target taxonomy aligned to actual ad types: Listing page banners + Sponsored Logo
    "target": {"ListingPageBannerAd", "Sponsored_Logo", "Main", "runs"},
    # TikTok Shop - product catalog scraper (not traditional ads)
    "tiktokshop": {"Products", "Featured_Brands", "Main", "runs"},
}

# JSON ad.type → folder mapping only where they differ
# Kroger JSON uses CuratedCarousel; images go to Carousel folder
ADTYPE_TO_FOLDER: Dict[Tuple[str, str], str] = {
    ("kroger", "CuratedCarousel"): "Carousel",
    # For all others, folder name == JSON ad.type (1:1)
}

def folder_for_adtype(retailer: str, ad_type: str) -> str:
    """Return the output folder name for a given retailer and ad_type, honoring mapping."""
    key = (retailer, ad_type)
    return ADTYPE_TO_FOLDER.get(key, ad_type)

def validate_folder(retailer: str, folder_name: str) -> bool:
    """True if folder_name is allowed for retailer."""
    allowed = ALLOWED_FOLDERS.get(retailer, set())
    return folder_name in allowed

# Legacy compatibility functions
TAXONOMY = ALLOWED_FOLDERS

def allowed_subdirs(retailer: str) -> set[str]:
    """Get the allowed subdirectories for a retailer."""
    try:
        return ALLOWED_FOLDERS[retailer.lower()]
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
