"""
Ad Extractors Package

This package contains extractors for different types of ads found on Kroger.com.
Each extractor is responsible for parsing a specific ad type from HTML content.
"""

# Registry of available ad extractors
EXTRACTORS = {}

def register_extractor(ad_type, extractor_class):
    """Register an ad extractor class for a specific ad type"""
    EXTRACTORS[ad_type] = extractor_class

def get_extractor(ad_type):
    """Get the extractor class for a specific ad type"""
    return EXTRACTORS.get(ad_type)

def get_all_extractors():
    """Get all registered extractors"""
    return EXTRACTORS
