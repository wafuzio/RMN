# utils/path_taxonomy.py

from typing import Dict, Set, Tuple
from pathlib import Path

# Canonical allowed folders per retailer (documentation-aligned)
ALLOWED_FOLDERS: Dict[str, Set[str]] = {
    "kroger": {"TOA", "Skyscraper", "Carousel", "Display_Ads", "Main", "runs"},
    "walmart": {"SBA", "SBV", "Tile_Takeover", "Main", "runs"},  # No Top_Banner; legacy allowed to exist but not used
    "instacart": {"Shoppable_Display_Ads", "Shoppable_Video_Ads", "Shoppable_Recipe_Ads", "Display_Ads", "Main", "runs"},
    "amazon": {"Sponsored_Brand", "Sponsored_Product", "Sponsored_Display", "Main", "runs"},
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
