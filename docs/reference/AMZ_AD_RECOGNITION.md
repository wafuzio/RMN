# Amazon Ad Recognition Patterns

## Overview
This document identifies common HTML patterns and selectors for recognizing different types of Amazon sponsored ads.

---

## 1. Sponsored Brand Video (SBV)

### Key Identifiers
- **Parent Container:** `div.s-result-item.AdHolder`
- **Widget ID Pattern:** `cel_widget_id="sb-video-product-collection-desktop_*"`
- **Data Attributes:**
  - `data-csa-c-painter="sb-video-product-collection-desktop-cards"`
  - `data-csa-c-type="widget"`
  - `data-cel-widget` contains `"sb-video-product-collection"`

### CSS Selectors
```css
/* Primary selector */
div.AdHolder[data-cel-widget*="sb-video-product-collection"]

/* Alternative selectors */
[cel_widget_id*="sb-video-product-collection"]
[data-csa-c-painter="sb-video-product-collection-desktop-cards"]
```

### Characteristics
- Contains `<video>` element
- Has carousel of product cards
- Video container class: `_c2Itd_videoContainer_*`
- Product carousel: `a-carousel-container`

---

## 2. Sponsored Product (Standard)

### Key Identifiers
- **Parent Container:** `div.s-result-item` with `data-asin` attribute
- **Sponsored Label:** 
  - `span.puis-label-popover-default` containing "Sponsored" text
  - `span.a-color-secondary` with "Sponsored" aria-label

### CSS Selectors
```css
/* Sponsored product with label */
div.s-result-item:has(.puis-sponsored-label-text)

/* Direct label selector */
.puis-label-popover.puis-sponsored-label-text
span[aria-label*="View Sponsored information"]
```

### Characteristics
- Has `data-asin` attribute (product ASIN)
- Contains sponsored label popover
- Info icon: `span.puis-sponsored-label-info-icon`

---

## 3. Featured from Amazon Brands

### Key Identifiers
- **Label Text:** "Featured from Amazon brands"
- **Similar structure to sponsored products** but different label

### CSS Selectors
```css
/* Featured brand label */
span.puis-label-popover-default:has-text("Featured from Amazon brands")
.puis-label-popover:has-text("Featured from Amazon brands")
```

---

## 4. Sponsored Carousel

### Key Identifiers
- **Parent Container:** `div.s-result-item.s-widget`
- **Widget Type:** `template=FEATURED_ASINS_LIST`
- **Widget ID Pattern:** `cel_widget_id="MAIN-FEATURED_ASINS_LIST-*"`
- **Data Attributes:**
  - `data-csa-c-type="widget"`
  - `data-cel-widget="MAIN-FEATURED_ASINS_LIST-*"`
  - Contains `widgetId` with `"loom-desktop-bottom-slot"` or similar

### CSS Selectors
```css
/* Carousel widget */
div[cel_widget_id*="FEATURED_ASINS_LIST"]
div[data-cel-widget*="FEATURED_ASINS_LIST"]

/* By slot ID */
[data-csa-c-slot-id="MAIN"][data-csa-c-type="widget"]
```

### Characteristics
- Contains multiple product cards in carousel format
- Has `s-widget-container` class
- Widget template: `FEATURED_ASINS_LIST`

---

## 5. Sponsored Footer

### Key Identifiers
- **Container Class:** `_c2Itd_footer_*`
- **Sponsored Label Container:** `_c2Itd_footerSponsoredLabel_*`
- **Category Link:** `_c2Itd_categoryLink_*`

### CSS Selectors
```css
/* Footer sponsored label */
[class*="_footerSponsoredLabel_"]
[class*="_footer_"]:has([class*="_sponsoredLabel_"])
```

---

## Universal Ad Detection Patterns

### Common Attributes Across All Ad Types
1. **"Sponsored" text presence**
   - Look for text content containing "Sponsored"
   - Check aria-labels for "Sponsored information"

2. **Data attributes:**
   - `data-csa-c-type="widget"`
   - `data-cel-widget` (various values)
   - `cel_widget_id` (various values)

3. **Class patterns:**
   - `AdHolder` class
   - `puis-sponsored-label-*` classes
   - Widget-specific classes with `_c2Itd_*` prefix

### Recommended Detection Strategy

```python
# Playwright/Selenium detection approach
def is_amazon_ad(element):
    """
    Detect if an element is an Amazon sponsored ad
    """
    # Check for AdHolder class
    if 'AdHolder' in element.get_attribute('class'):
        return True
    
    # Check for sponsored label text
    if element.query_selector('.puis-sponsored-label-text'):
        return True
    
    # Check for sponsored video widget
    if element.get_attribute('cel_widget_id') and 'sb-video-product-collection' in element.get_attribute('cel_widget_id'):
        return True
    
    # Check for featured asins carousel
    if element.get_attribute('data-cel-widget') and 'FEATURED_ASINS_LIST' in element.get_attribute('data-cel-widget'):
        return True
    
    # Check for "Sponsored" text in aria-label
    sponsored_label = element.query_selector('[aria-label*="Sponsored"]')
    if sponsored_label:
        return True
    
    return False
```

---

## Ad Type Classification

### By Container Attributes

| Ad Type | Primary Identifier | Secondary Identifier |
|---------|-------------------|---------------------|
| **Sponsored Brand Video** | `cel_widget_id*="sb-video-product-collection"` | Contains `<video>` |
| **Sponsored Product** | `.puis-sponsored-label-text` | Has `data-asin` |
| **Featured Brand** | Text: "Featured from Amazon brands" | `.puis-label-popover` |
| **Sponsored Carousel** | `cel_widget_id*="FEATURED_ASINS_LIST"` | `template=FEATURED_ASINS_LIST` |

---

## URL Patterns

### Tracking URLs
Amazon ads use tracking URLs with these patterns:
- `aax-us-east-retail-direct.amazon.com/x/c/...`
- Contains encoded product URLs
- Includes tracking parameters: `pd_rd_*`, `pf_rd_*`

### Example Tracking URL Structure
```
https://aax-us-east-retail-direct.amazon.com/x/c/{TRACKING_ID}/https://www.amazon.com/dp/{ASIN}/?_encoding=UTF8&pd_rd_i={ASIN}&ref_=sbx_be_s_sparkle_ssd_img&...
```

---

## Best Practices for Ad Detection

1. **Use multiple signals:** Don't rely on a single attribute
2. **Check class prefixes:** Amazon uses dynamic class names with consistent prefixes
3. **Look for "Sponsored" text:** Most reliable indicator
4. **Verify widget types:** Check `data-cel-widget` and `cel_widget_id`
5. **Handle dynamic content:** Classes may change, use pattern matching

---

## Testing Selectors

### Quick Test Queries (Browser Console)
```javascript
// Find all sponsored products
document.querySelectorAll('.puis-sponsored-label-text')

// Find all ad containers
document.querySelectorAll('.AdHolder')

// Find sponsored brand videos
document.querySelectorAll('[cel_widget_id*="sb-video-product-collection"]')

// Find featured carousels
document.querySelectorAll('[data-cel-widget*="FEATURED_ASINS_LIST"]')
```

---

## Notes

- **Dynamic Classes:** Amazon uses CSS modules with hashed class names (e.g., `_c2Itd_*`). These may change but patterns remain consistent.
- **Multiple Ad Types:** A single search page may contain multiple ad types simultaneously.
- **Responsive Design:** Ad layouts change based on viewport size; selectors should be viewport-agnostic.
- **A/B Testing:** Amazon frequently tests new ad formats; monitor for new patterns.

---

## Related Documentation
- See `AMZ_ad_html.md` for full HTML examples
- See `ARTIFACT_TAXONOMY.md` for artifact classification
