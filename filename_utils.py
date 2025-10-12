#!/usr/bin/env python3
"""
Standardized Filename Generation Utility

Provides consistent filename formatting across all retailers:
[retailer]__[ad_type]__[client]__[search_term]__D[YYYYMMDD]_T[HHMMSS]_[index].[ext]

Example: kroger__skyscraper__blue_bunny__ice_cream_cones__D20251009_T085621_1.png
"""

import re
from datetime import datetime
from typing import Optional


def sanitize_component(text: str, max_length: int = 50) -> str:
    """
    Sanitize a filename component:
    - Convert to lowercase
    - Replace spaces and special chars with underscores
    - Remove consecutive underscores
    - Trim to max_length
    """
    if not text:
        return "unknown"
    
    # Convert to lowercase and replace spaces/special chars
    sanitized = re.sub(r'[^a-z0-9]+', '_', text.lower())
    
    # Remove leading/trailing underscores and consecutive underscores
    sanitized = re.sub(r'_+', '_', sanitized).strip('_')
    
    # Trim to max length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length].rstrip('_')
    
    return sanitized or "unknown"


def parse_timestamp(timestamp) -> tuple[str, str]:
    """
    Parse timestamp into (date, time) tuple in format (YYYY-MM-DD, HH-MM.SS).
    
    Args:
        timestamp: Can be:
            - datetime object
            - 'YYYY-MM-DD_HH-MM-SS' string
            - 'YYYYMMDD_HHMMSS' string
            - 'YYYYMMDDTHHMMSS' or 'YYYYMMDDHHMMSS' string
    
    Returns:
        (date_str, time_str) tuple: ('2025-10-09', '08-56.21')
    """
    if isinstance(timestamp, datetime):
        return timestamp.strftime('%Y-%m-%d'), timestamp.strftime('%H-%M.%S')
    
    if isinstance(timestamp, str):
        # Try to parse various formats
        # Format: YYYY-MM-DD_HH-MM-SS
        match = re.match(r'(\d{4})-(\d{2})-(\d{2})[_T](\d{2})-(\d{2})-(\d{2})', timestamp)
        if match:
            y, m, d, h, min, s = match.groups()
            return f"{y}-{m}-{d}", f"{h}-{min}.{s}"
        
        # Format: YYYYMMDD_HHMMSS or YYYYMMDDTHHMMSS or YYYYMMDDHHMMSS
        match = re.match(r'(\d{4})(\d{2})(\d{2})[_T]?(\d{2})(\d{2})(\d{2})', timestamp)
        if match:
            y, m, d, h, min, s = match.groups()
            return f"{y}-{m}-{d}", f"{h}-{min}.{s}"
        
        # Format: YYYYMMDD (date only)
        match = re.match(r'(\d{4})(\d{2})(\d{2})', timestamp)
        if match:
            y, m, d = match.groups()
            return f"{y}-{m}-{d}", '00-00.00'
    
    # Fallback to current time
    now = datetime.now()
    return now.strftime('%Y-%m-%d'), now.strftime('%H-%M.%S')


def generate_ad_filename(
    retailer: str,
    ad_type: str,
    client: str,
    search_term: str,
    timestamp,
    index: int = 1,
    extension: str = 'png',
    advertiser: str = None
) -> str:
    """
    Generate standardized ad filename.
    
    Format: [retailer]__[advertiser]__[ad_type]__[client]__[search_term]__D[YYYY-MM-DD]_T[HH-MM.SS]_[index].[ext]
    
    Note: Double underscores (__) separate major fields, single underscores (_) within fields.
    
    Args:
        retailer: 'kroger', 'walmart', 'instacart', 'amazon'
        ad_type: 'skyscraper', 'toa', 'carousel', 'tile_takeover', 'sba', 'sbv', etc.
        client: client name (e.g., 'blue_bunny', 'taxonomy_test')
        search_term: search keyword (e.g., 'ice_cream_cones', 'light_potato_chips')
        timestamp: datetime object or timestamp string
        index: ad index (1, 2, 3, etc.)
        extension: file extension without dot ('png', 'jpg', 'mp4')
        advertiser: advertiser/brand name (e.g., 'popsicle', 'unilever') - optional
    
    Returns:
        Standardized filename string
    
    Example:
        >>> generate_ad_filename('walmart', 'sba', 'taxonomy_test', 'ice pop', 
        ...                      '2025-10-12_12-34-56', 1, 'png', 'popsicle')
        'walmart__popsicle__sba__taxonomy_test__ice_pop__D2025-10-12_T12-34.56_1.png'
    """
    # Sanitize components
    retailer_clean = sanitize_component(retailer, max_length=20)
    ad_type_clean = sanitize_component(ad_type, max_length=30)
    client_clean = sanitize_component(client, max_length=30)
    search_term_clean = sanitize_component(search_term, max_length=50)
    
    # Sanitize advertiser if provided
    advertiser_clean = sanitize_component(advertiser, max_length=30) if advertiser else None
    
    # Parse timestamp
    date_str, time_str = parse_timestamp(timestamp)
    
    # Remove dot from extension if present
    extension_clean = extension.lstrip('.')
    
    # Build filename with double underscores between major fields
    # Include advertiser after retailer if provided
    if advertiser_clean:
        filename = (
            f"{retailer_clean}__{advertiser_clean}__{ad_type_clean}__{client_clean}__{search_term_clean}__"
            f"D{date_str}_T{time_str}_{index}.{extension_clean}"
        )
    else:
        filename = (
            f"{retailer_clean}__{ad_type_clean}__{client_clean}__{search_term_clean}__"
            f"D{date_str}_T{time_str}_{index}.{extension_clean}"
        )
    
    return filename
