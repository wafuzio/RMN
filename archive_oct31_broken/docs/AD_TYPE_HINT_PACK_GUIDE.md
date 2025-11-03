# Ad Type Hint Pack Guide

**Single source of truth for retailer ad types, selectors, and extraction logic**

## Overview

The Ad Type Hint Pack is a YAML file that explicitly defines:
- Canonical ad types and folder mappings
- CSS selectors for containers and sub-elements
- Brand extraction strategies
- Image handling preferences
- Auth and anti-bot requirements

**Key Benefit:** Hint Pack takes priority over profiler heuristics, giving you full control over the generated adapter.

---

## Why Use Hint Packs?

### Without Hint Pack (Profiler Only)
- ❌ Guesses ad types from HTML patterns
- ❌ Generic selectors that may not match
- ❌ No brand extraction strategy
- ❌ Requires manual selector fixes after generation

### With Hint Pack
- ✅ Explicit ad type definitions
- ✅ Tested selectors from HTML samples
- ✅ Brand extraction strategies defined
- ✅ Generates production-ready code immediately
- ✅ Validated before composition

---

## File Structure

```
docs/hints/
  HINT_PACK_TEMPLATE.yaml          # Template for new retailers
  kroger_ad_types.yaml              # Kroger example
  walmart_ad_types.yaml             # Walmart example
  {retailer}_ad_types.yaml          # Your retailer
  {retailer}/
    samples/
      TOA_1.html                    # HTML examples
      TOA_2.html
      Skyscraper_1.html
      CuratedCarousel_1.html
```

---

## Hint Pack Anatomy

### Top-Level Fields

```yaml
retailer: newretailer                # Slug (lowercase, matches folder names)
display_name: NewRetailer            # Human-readable name
requires_auth: true                  # Persistent profile required?
store_selection_required: false      # Store picker required?
anti_bot_hint:
  vendor: perimeterx                 # perimeterx | akamai | cloudflare | none
  headless_allowed: false            # Can run headless?
```

### Ad Type Definition

```yaml
ad_types:
  - canonical: TOA                   # Canonical JSON ad.type
    folder: TOA                      # Folder name (must match taxonomy)
    priority: 100                    # Higher = more important (for dedupe)
    selectors:                       # Container-level CSS selectors
      - "div[data-testid='StandardTOA']"
      - "div.StandardTOA"
    image:
      element: "img.espot-image"     # Image element selector
      crop_preferred: true           # Prefer crop over full screenshot
    href: "a.espot-link"             # Link element
    title: "h2.espot-header"         # Title element
    description: ".espot-subText"    # Description element
    cta: ".espot-linkText"           # CTA button text
    brand:
      strategy:                      # Brand extraction strategies (in order)
        - from_href_param: "brand"   # Extract from URL param
        - from_text_sources: ["title", "description"]
      lexicon: true                  # Apply brand canonicalization
```

### Brand Extraction Strategies

**Available strategies:**

1. `from_href_param: "brand"` - Extract from URL parameter
   ```
   https://example.com?brand=lays → "Lay's"
   ```

2. `from_href_brand_path: "/brand/"` - Extract from URL path
   ```
   https://example.com/brand/kraft/products → "Kraft"
   ```

3. `from_text_sources: ["title", "description"]` - Extract from text fields
   ```
   title: "Lay's Potato Chips" → "Lay's"
   ```

4. `from_attribute: "data-brand-name"` - Extract from HTML attribute
   ```html
   <div data-brand-name="Lay's"> → "Lay's"
   ```

5. `from_first_product_title: true` - Extract from first product in carousel
   ```
   First product: "Lay's Classic" → "Lay's"
   ```

6. `from_product_tiles: true` - Extract from associated product tiles (SBV)
   ```
   Product tiles below video → extract brand from first tile
   ```

**Lexicon canonicalization:**
- `lexicon: true` - Always apply `core/brands.canonicalize()`
- Maps synonyms to canonical names
- Example: "lays" → "Lay's", "Band Aid" → "Band-Aid"

---

## Creating a Hint Pack

### Step 1: Collect HTML Samples

**Manual collection:**
1. Navigate to retailer search page
2. Right-click ad container → "Inspect"
3. Right-click outer container → "Copy" → "Copy outerHTML"
4. Save to `docs/hints/{retailer}/samples/{AdType}_1.html`

**Automated collection:**
```bash
# Run profiler with --save-samples flag (if implemented)
python3 tools/retailer_profiler.py \
  --url https://www.newretailer.com \
  --keyword "milk" \
  --profile-dir ~/profiles/newretailer \
  --save-samples docs/hints/newretailer/samples/
```

**Best practices:**
- Collect 2-3 examples per ad type
- Include variations (different brands, products)
- Include edge cases (missing fields, long text)

### Step 2: Identify Selectors

**Using browser DevTools:**
1. Inspect ad container
2. Note `data-testid`, class names, or unique attributes
3. Test selector in console:
   ```javascript
   document.querySelectorAll('div[data-testid="StandardTOA"]')
   ```
4. Verify it matches only the ad container

**Selector priority:**
1. `data-testid` attributes (most stable)
2. Semantic class names (`.StandardTOA`)
3. Structural selectors (last resort)

**Avoid:**
- ❌ Hashed classes (`sc-abc123`, `css-xyz789`)
- ❌ Index-based selectors (`:nth-child(3)`)
- ❌ Overly specific paths (`div > div > div > div`)

### Step 3: Write Hint Pack

**Copy template:**
```bash
cp docs/hints/HINT_PACK_TEMPLATE.yaml docs/hints/newretailer_ad_types.yaml
```

**Fill in fields:**
1. Set `retailer` and `display_name`
2. Set auth requirements
3. Add ad types with selectors
4. Define brand extraction strategies
5. Add notes for profiler/composer

### Step 4: Validate Selectors

**Run smoke test:**
```bash
python3 tools/selector_smoke_test.py docs/hints/newretailer_ad_types.yaml
```

**Expected output:**
```
✅ TOA: OK (total_hits=3)
   📄 TOA_1.html: 1 container hits
      ✓ div[data-testid='StandardTOA'] → 1
      Sub-elements:
         ✓ image: img.espot-image → 1
         ✓ href: a.espot-link → 1
         ✓ title: h2.espot-header → 1
```

**If failures:**
- Update selectors in hint pack
- Re-run smoke test
- Repeat until all green

### Step 5: Compose Adapter

**With hint pack only:**
```bash
python3 tools/compose_retailer.py \
  --hint-pack docs/hints/newretailer_ad_types.yaml
```

**With hint pack + profiler:**
```bash
# Run profiler first
python3 tools/retailer_profiler.py \
  --url https://www.newretailer.com \
  --keyword "milk" \
  --profile-dir ~/profiles/newretailer \
  --out profiles/newretailer_profile.json

# Compose with both (hint pack takes priority)
python3 tools/compose_retailer.py \
  --hint-pack docs/hints/newretailer_ad_types.yaml \
  --profile profiles/newretailer_profile.json
```

---

## Priority Rules

When both hint pack and profiler are provided:

### Hint Pack Wins
- ✅ Ad types and selectors
- ✅ Folder mappings
- ✅ Brand extraction strategies
- ✅ Auth requirements
- ✅ Anti-bot vendor

### Profiler Augments
- ✅ Confirms auth requirements
- ✅ Detects store selection UI
- ✅ Tests headless compatibility
- ✅ Validates selectors still work

---

## Example: Kroger Hint Pack

```yaml
retailer: kroger
display_name: Kroger
requires_auth: true
store_selection_required: false
anti_bot_hint:
  vendor: perimeterx
  headless_allowed: false

ad_types:
  - canonical: TOA
    folder: TOA
    priority: 100
    selectors:
      - "div[data-testid='StandardTOA']"
    image:
      element: "img.espot-image"
      crop_preferred: true
    href: "a.espot-link"
    title: "h2.espot-header"
    brand:
      strategy:
        - from_href_param: "brand"
        - from_text_sources: ["title"]
      lexicon: true

  - canonical: Skyscraper
    folder: Skyscraper
    priority: 90
    selectors:
      - "div[data-testid='SkyscraperTOA']"
    image:
      element: "img"
      crop_preferred: false
    brand:
      strategy:
        - from_href_brand_path: "/brand/"
      lexicon: true

  - canonical: CuratedCarousel
    folder: Carousel
    priority: 80
    selectors:
      - "div.CuratedCarousel"
    featured_only: true
    image:
      capture_screenshot: true
    brand:
      strategy:
        - from_first_product_title: true
      lexicon: true
```

---

## Workflow Integration

### Updated New Retailer Process

**Old way (profiler only):**
1. Run profiler
2. Compose adapter
3. Fix selectors manually
4. Test and iterate

**New way (hint pack first):**
1. ✅ Collect HTML samples
2. ✅ Create hint pack
3. ✅ Validate selectors
4. ✅ Compose adapter (production-ready)
5. ✅ Test once

**Time savings:** ~60% reduction in manual fixes

---

## Best Practices

### 1. Start with Real HTML
Don't guess selectors - always work from actual HTML samples.

### 2. Test Before Composing
Run `selector_smoke_test.py` until all selectors pass.

### 3. Document Edge Cases
Add notes about:
- Ads that appear only when logged in
- Seasonal/promotional ad types
- Regional variations

### 4. Version Control
Commit hint packs alongside code:
```bash
git add docs/hints/newretailer_ad_types.yaml
git add docs/hints/newretailer/samples/
git commit -m "Add NewRetailer hint pack"
```

### 5. Keep Samples Updated
When retailer changes HTML structure:
1. Collect new samples
2. Update selectors in hint pack
3. Re-validate
4. Re-compose if needed

---

## Troubleshooting

### Smoke Test Failures

**Problem:** `NO_SAMPLES`
**Fix:** Add HTML samples to `docs/hints/{retailer}/samples/`

**Problem:** `FAIL` with 0 hits
**Fix:** Selector doesn't match HTML - inspect samples and update selector

**Problem:** Sub-element selector fails
**Fix:** Element may be optional or have different structure - make selector more flexible

### Composition Issues

**Problem:** "Could not determine retailer slug"
**Fix:** Set `retailer` field in hint pack YAML

**Problem:** "Ad type not in taxonomy"
**Fix:** Ensure `folder` field matches canonical ad type or add mapping

### Runtime Issues

**Problem:** No ads extracted
**Fix:** Selectors may have changed - collect new samples and update hint pack

**Problem:** Brand extraction fails
**Fix:** Try different brand strategy or add fallback strategies

---

## Tools Reference

### selector_smoke_test.py
**Purpose:** Validate selectors against HTML samples
**Usage:**
```bash
python3 tools/selector_smoke_test.py docs/hints/{retailer}_ad_types.yaml
```

### compose_retailer.py
**Purpose:** Generate adapter from hint pack
**Usage:**
```bash
# Hint pack only
python3 tools/compose_retailer.py --hint-pack docs/hints/{retailer}_ad_types.yaml

# Hint pack + profiler
python3 tools/compose_retailer.py \
  --hint-pack docs/hints/{retailer}_ad_types.yaml \
  --profile profiles/{retailer}_profile.json
```

### retailer_profiler.py
**Purpose:** Fingerprint site capabilities
**Usage:**
```bash
python3 tools/retailer_profiler.py \
  --url https://www.retailer.com \
  --keyword "milk" \
  --profile-dir ~/profiles/retailer \
  --out profiles/retailer_profile.json
```

---

## Future Enhancements

- [ ] Auto-generate hint pack from profiler + samples
- [ ] ML-based selector suggestion
- [ ] Selector stability scoring
- [ ] Auto-update hint packs when HTML changes
- [ ] Hint pack versioning and migration

---

**Created:** 2025-10-27
**Last Updated:** 2025-10-27
**Maintainer:** Retail Ad Monitor Team
