/**
 * Common ad type keywords that indicate this is NOT a real brand
 */
const AD_TYPE_KEYWORDS = [
  "ad", "ads", "display", "video", "carousel", "product", "sponsored", 
  "banner", "takeover", "tile", "shoppable", "sba", "sbv", "toa",
  "native", "skyscraper", "featured", "top"
];

/**
 * Known ad type patterns that should never have brand logos
 */
const AD_TYPE_PATTERNS = [
  /Shoppable Display Ad/i,
  /Shoppable Video Ad/i,
  /Display Ads/i,
  /Video Ads/i,
  /Sponsored Product/i,
  /Sponsored Brand/i,
  /Sponsored Carousel/i,
  /Top Banner/i,
  /Tile Takeover/i,
];

/**
 * Checks if a string is likely an ad type rather than a brand name
 * Returns true if it should NOT load a logo
 */
export function isAdTypeNotBrand(value: string | undefined): boolean {
  if (!value) return true;

  const normalized = value.toLowerCase().trim();

  // Check against known patterns
  for (const pattern of AD_TYPE_PATTERNS) {
    if (pattern.test(value)) {
      return true;
    }
  }

  // Check if it contains multiple ad type keywords (whole words only)
  const keywordMatches = AD_TYPE_KEYWORDS.filter(kw => {
    const regex = new RegExp(`\\b${kw.toLowerCase()}\\b`);
    return regex.test(normalized);
  }).length;
  
  if (keywordMatches >= 2) {
    return true;
  }

  // Check if it's a known single-word ad type
  if (AD_TYPE_KEYWORDS.some(kw => normalized === kw)) {
    return true;
  }

  // Additional heuristics: real brand names are usually shorter and simpler
  // Ad types are usually longer phrases with spaces
  // If it has 3+ words and contains ad type keywords, it's probably not a brand
  const words = value.trim().split(/\s+/).length;
  if (words >= 3 && keywordMatches >= 1) {
    return true;
  }

  return false;
}
