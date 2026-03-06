# Retailer Profiler + Composer Runbook

**Auto-generate production-ready retailer adapters from site fingerprints**

## Overview

The Profiler + Composer system automatically scaffolds new retailer integrations by:
1. **Profiling** the target site to detect capabilities
2. **Composing** a production-ready adapter from proven patterns
3. **Enforcing** canonical schema, brand lexicon, and path taxonomy

**Time savings:** 2-3 hours of manual setup → 10 minutes automated

---

## Part 1: What We Detect (Capability Matrix)

The profiler runs a headed Playwright session and returns a JSON with:

### Identity
- `url_patterns` - Search URL shape (`?q=`, `?query=`, `/search/`)
- `spa_framework` - Next.js, React, Vue, Svelte, or undefined

### Authentication
- `requires_auth` - bool (gated content unless logged in)
- `persistent_profile_required` - bool (detects login-only ads, like Kroger)
- `store_selection_required` - bool

### Anti-Bot
- `anti_bot.vendor` - perimeterx | akamai | cloudflare | none | unknown
- `anti_bot.level` - low | medium | high
- `headless_allowed` - bool (quick headless vs headed probe)

### DOM & Selectors
- `data_testid_density` - high | medium | low (# of `[data-testid]` markers)
- `hashed_class_density` - high | medium | low (`sc-`, `k2-`, `css-*`)
- `has_lazy_loading` - bool (IntersectionObserver present; many `img[loading=lazy]`)

### Ad Surface Hints (Best-Effort)
- `sba_like` - bool (find containers that look like SBA)
- `tile_takeover_like` - bool
- `video_in_grid_like` - bool
- `curated_carousel_like` - bool
- `toa_like` - bool
- `skyscraper_like` - bool

---

## Part 2: Mapping Logic (Composer Rules)

### Rule 1: Kroger-Like Profile
**If:** `requires_auth` OR `persistent_profile_required`
**Then:** Include Kroger's persistent-profile auth and login handling

### Rule 2: Walmart-Like Navigation
**If:** `anti_bot.vendor` in {perimeterx, akamai} OR `headless_allowed == false`
**Then:** Include Walmart's "organic search" navigation + bot-avoidance scaffolding
- No direct `goto`
- Type search organically
- Additional waits
- Profile seeding

### Rule 3: Instacart-Like Scroller
**If:** `has_lazy_loading` OR `hashed_class_density == high`
**Then:** Include Instacart's lazy-load scroller + robust screenshot stabilization
- IntersectionObserver-friendly
- Multiple scroll passes

### Rule 4: Ad Type Registration
- `curated_carousel_like` → Register `CuratedCarousel` with folder mapping to `Carousel/`
- `sba_like/sbv_like/tile_takeover_like` → Register those ad types 1:1
- `toa_like/skyscraper_like` → Register `TOA/Skyscraper` and enable extractors

### Rule 5: Always Enforce
- ✅ Canonical schema
- ✅ Lexicon canonicalization
- ✅ Filename generator
- ✅ Path taxonomy

---

## Part 3: Step-by-Step Runbook

### Step 1: Create Profile Directory
```bash
mkdir -p ~/Documents/Amazon_Scrape/profiles/newretailer
```

### Step 2: Run Profiler
```bash
python3 tools/retailer_profiler.py \
  --url https://www.newretailer.com \
  --keyword "milk" \
  --profile-dir ~/Documents/Amazon_Scrape/profiles/newretailer \
  --out profiles/newretailer_profile.json
```

**What happens:**
- Opens headed browser with persistent profile
- Navigates to homepage
- Detects auth requirements
- Performs organic search
- Analyzes DOM structure
- Tests headless compatibility
- Sniffs anti-bot defenses
- Detects ad surface types
- Writes capability JSON

**Output:** `profiles/newretailer_profile.json`

### Step 3: Review Profile
```bash
cat profiles/newretailer_profile.json | jq
```

**Check:**
- Is `requires_auth` correct?
- Are ad types detected?
- Is anti-bot vendor identified?

### Step 4: Run Composer
```bash
python3 tools/compose_retailer.py \
  --profile profiles/newretailer_profile.json \
  --slug newretailer
```

**What happens:**
- Analyzes capability profile
- Recommends code patterns
- Generates adapter (`retailers/newretailer/adapter.py`)
- Generates search script (`newretailer_search_and_capture.py`)
- Generates `__init__.py`
- Updates `utils/path_taxonomy.py`
- Updates `keyword_input.py`
- Creates setup script (`scripts/setup_newretailer_profile.sh`)

**Files created:**
```
retailers/newretailer/
  __init__.py
  adapter.py
newretailer_search_and_capture.py
scripts/setup_newretailer_profile.sh
```

**Files modified:**
```
utils/path_taxonomy.py  (adds newretailer folders)
keyword_input.py        (imports adapter)
```

### Step 5: Setup Authentication
```bash
./scripts/setup_newretailer_profile.sh
```

**What happens:**
- Creates profile directory
- Runs `auth/retailer_auth.py`
- Opens browser for manual login
- Saves cookies to persistent profile

**Manual action:** Complete login in browser window

### Step 6: Add Environment Variables

**Option A: For GUI (launcher.env)**
```bash
echo "NEWRETAILER_PROFILE_DIR=~/Documents/Amazon_Scrape/profiles/newretailer" >> config/launcher.env
```

**Option B: For CLI (shell profile)**
```bash
echo "export NEWRETAILER_PROFILE_DIR=~/Documents/Amazon_Scrape/profiles/newretailer" >> ~/.zshrc
source ~/.zshrc
```

### Step 7: Add Ad Selectors

**Edit:** `newretailer_search_and_capture.py`

Find the `TODO: Extract ads from page` section and add selectors:

```python
# Example: Extract SBA-like ads
sba_containers = page.locator("[data-testid*='sponsored']").all()
for i, container in enumerate(sba_containers, 1):
    try:
        brand = container.locator("span.brand-name").inner_text()
        title = container.locator("h2").inner_text()
        href = container.locator("a").get_attribute("href")
        image_url = container.locator("img").get_attribute("src")
        
        # Download image
        filename = generate_ad_filename(
            retailer="newretailer",
            ad_type="SBA",
            client=os.path.basename(output_dir),
            search_term=keyword,
            timestamp=run_ts,
            index=i,
            extension="png",
            advertiser=brand or "unknown",
        )
        
        # Save image (add download logic here)
        image_path = f"SBA/{filename}"
        
        # Build ad object
        ad = build_ad_object(
            run_id=run_id,
            index=i,
            ad_type="SBA",
            brand=brand,
            image_path=image_path,
            title=title,
            href=href,
            image_url=image_url,
            slot=i-1,
        )
        ads_list.append(ad)
    except Exception as e:
        print(f"⚠️ Failed to extract SBA ad #{i}: {e}")
```

### Step 7.5: Wire Profile Health

**Edit:** `utils/profile_health.py`

Add block-detection patterns for your retailer:

```python
_BLOCK_PATTERNS = {
    # ... existing retailers ...
    "newretailer": [
        {"pattern": "access denied", "reason": "access_denied", "fixed": True},
        {"pattern": "verify you are human", "reason": "captcha", "fixed": True},
    ],
}
```

**Edit:** `newretailer_search_and_capture.py`

1. **Login detection** (after homepage loads, before search):
```python
try:
    # Replace with your retailer's not-logged-in selector
    not_logged_in = page.locator('#sign-in-link').first.is_visible(timeout=2000)
    if not_logged_in:
        from utils.profile_health import record_login_outcome
        record_login_outcome("newretailer", keyword, logged_in=False)
except Exception:
    pass
```

2. **Block detection** (after HTML save):
```python
try:
    from utils.profile_health import check_and_record
    check_and_record(html_content, "newretailer", keyword, alert=True)
except Exception:
    pass
```

**Selector reference:** See `docs/ADDING_NEW_RETAILER.md` → Step 4.5.3 for all existing login selectors.

### Step 8: Test Search Script
```bash
python3 newretailer_search_and_capture.py "test keyword" \
  --output-dir output/newretailer/test_client
```

**Verify:**
- ✅ HTML saved to `runs/`
- ✅ JSON saved to `runs/`
- ✅ Ads extracted (check `ads[]` array)
- ✅ Brand names are canonical

### Step 9: Test in GUI
```bash
python3 keyword_input.py
```

**Steps:**
1. Select "Newretailer" from dropdown
2. Enter client name
3. Enter keyword
4. Click "Run Scraper"

**Verify:**
- ✅ Scraper runs without errors
- ✅ Images saved to correct folders
- ✅ JSON has canonical structure

### Step 10: Run Audit
```bash
python3 tools/audit_adtype_mapping.py
```

**Expected output:**
```
- newretailer/SBA: JSON-type OK | Folder OK | Filename OK | Image exists
- newretailer/TOA: JSON-type OK | Folder OK | Filename OK | Image exists
```

**If failures:**
- `JSON-type FAIL` - Ad type doesn't match folder name
- `Folder FAIL` - Images in wrong folder or folder not in taxonomy
- `Filename FAIL` - Filename doesn't match canonical pattern
- `Image MISSING` - `image_path` set but file doesn't exist

### Step 11: Documentation

**Create:** `retailers/newretailer/README.md`

```markdown
# NewRetailer Integration

## Setup
```bash
./scripts/setup_newretailer_profile.sh
```

## Environment Variables
```bash
export NEWRETAILER_PROFILE_DIR=~/Documents/Amazon_Scrape/profiles/newretailer
```

## Ad Types
- SBA - Sponsored Brand Ads
- TOA - Targeted Onsite Ads

## Selectors
- SBA: `[data-testid*='sponsored']`
- TOA: `div[data-testid='StandardTOA']`

## Notes
- Requires authentication
- Anti-bot: PerimeterX (medium)
- Uses organic search navigation
```

**Update:** `docs/CONTEXT_SEED.md`

Add to Current Adapters section:
```markdown
- newretailer (new)
  - Persistent profile via NEWRETAILER_PROFILE_DIR
  - URL pattern: https://www.newretailer.com/search?q={keyword}
  - Ad types: SBA, TOA
  - Verified: X ads detected with authenticated session
```

### Step 12: Commit
```bash
git add retailers/newretailer/
git add newretailer_search_and_capture.py
git add scripts/setup_newretailer_profile.sh
git add utils/path_taxonomy.py
git add keyword_input.py
git add docs/
git commit -m "Add NewRetailer integration (auto-generated)"
```

---

## Part 4: Canonical Schema Enforcement

### All Generated Code Includes:

**1. Canonical Run JSON**
```python
canonical_json = {
    "retailer": "newretailer",
    "client": os.path.basename(output_dir),
    "keyword": keyword,
    "timestamp": now_iso_z(),  # ISO 8601 with Z
    "run_id": build_run_id(),  # 14-digit YYYYMMDDHHMMSS
    "ads": ads_list,           # Flat array
}
```

**2. Canonical Ad Objects**
```python
def build_ad_object(run_id, index, ad_type, brand, image_path, **kwargs):
    canon_brand = canonicalize(brand) if brand else None
    return {
        "id": f"newretailer-{run_id}-{index}",
        "type": ad_type,
        "brand": canon_brand or brand,  # Lexicon applied
        "brand_logo": None,
        "image_path": image_path,       # Relative path
        ...
    }
```

**3. Canonical Filenames**
```python
from filename_utils import generate_ad_filename

filename = generate_ad_filename(
    retailer="newretailer",
    ad_type="SBA",
    client=client,
    search_term=keyword,
    timestamp=run_ts,
    index=1,
    extension="png",
    advertiser=brand or "unknown",
)
```

**4. Path Taxonomy**
```python
# Auto-added to utils/path_taxonomy.py
"newretailer": {
    "SBA",
    "TOA",
    "Main",
    "runs",
},
```

---

## Part 5: Example Profile JSON

```json
{
  "retailer_hint": "newretailer.com",
  "base_url": "https://www.newretailer.com",
  "search_url_shape": "?q=",
  "requires_auth": true,
  "persistent_profile_required": true,
  "store_selection_required": false,
  "anti_bot_vendor": "perimeterx",
  "anti_bot_level": "medium",
  "headless_allowed": false,
  "data_testid_density": "high",
  "hashed_class_density": "low",
  "has_lazy_loading": true,
  "spa_framework": "nextjs",
  "ad_hints": {
    "sba_like": true,
    "tile_takeover_like": false,
    "video_in_grid_like": false,
    "curated_carousel_like": false,
    "toa_like": true,
    "skyscraper_like": false
  },
  "notes": []
}
```

**Composer recommendations:**
- ✅ Use Kroger-like profile (requires_auth)
- ✅ Use Walmart-like navigation (anti_bot: perimeterx)
- ✅ Use Instacart-like scroller (has_lazy_loading)
- ✅ Register ad types: SBA, TOA

---

## Part 6: Troubleshooting

### Profiler Issues

**Problem:** "Profile directory not found"
**Fix:** Create it first: `mkdir -p ~/Documents/Amazon_Scrape/profiles/newretailer`

**Problem:** "Timeout during profiling"
**Fix:** Increase timeout in profiler or check if site is accessible

**Problem:** "No ad types detected"
**Fix:** Ad hints are best-effort; manually add selectors in Step 7

### Composer Issues

**Problem:** "Retailer already in taxonomy"
**Fix:** Normal - composer skips if already present

**Problem:** "Could not find adapter import section"
**Fix:** Manually add `import retailers.newretailer.adapter  # noqa: F401` to `keyword_input.py`

### Runtime Issues

**Problem:** "PROFILE_DIR not set or invalid"
**Fix:** Run setup script and add to `config/launcher.env`

**Problem:** "ValueError: Unknown retailer"
**Fix:** Check `utils/path_taxonomy.py` has newretailer entry

**Problem:** "No ads extracted"
**Fix:** Add actual selectors in search script (Step 7)

---

## Part 7: Comparison to Manual Process

### Manual (Old Way)
1. ⏱️ 30 min - Research site structure
2. ⏱️ 45 min - Write adapter.py
3. ⏱️ 45 min - Write search_and_capture.py
4. ⏱️ 15 min - Update taxonomy
5. ⏱️ 15 min - Update keyword_input.py
6. ⏱️ 15 min - Create setup script
7. ⏱️ 15 min - Documentation

**Total: ~3 hours**

### Automated (New Way)
1. ⏱️ 5 min - Run profiler
2. ⏱️ 1 min - Run composer
3. ⏱️ 5 min - Add selectors
4. ⏱️ 5 min - Test

**Total: ~15 minutes**

**Time savings: 92%**

---

## Part 8: Files Reference

### Tools
- `tools/retailer_profiler.py` - Site fingerprinting
- `tools/compose_retailer.py` - Adapter scaffolding

### Generated Files
- `retailers/{slug}/adapter.py` - Retailer adapter class
- `retailers/{slug}/__init__.py` - Module exports
- `{slug}_search_and_capture.py` - Search script
- `scripts/setup_{slug}_profile.sh` - Auth setup

### Modified Files
- `utils/path_taxonomy.py` - Folder registration
- `keyword_input.py` - Adapter import

### Documentation
- `retailers/{slug}/README.md` - Integration docs
- `docs/CONTEXT_SEED.md` - Project context

---

## Part 9: Best Practices

### 1. Always Review Profile
Don't blindly trust auto-detection. Review the capability JSON before composing.

### 2. Test Incrementally
Test each step before moving to the next:
- Profile → Review JSON
- Compose → Review generated code
- Setup → Verify auth works
- Selectors → Test extraction
- GUI → End-to-end test

### 3. Start Simple
Begin with one ad type, verify it works, then add more.

### 4. Use Audit Tool
Run `audit_adtype_mapping.py` after every change to catch issues early.

### 5. Document Selectors
Add comments in search script explaining what each selector targets.

### 6. Version Control
Commit after each major step so you can roll back if needed.

---

## Part 10: Future Enhancements

### Planned Features
- [ ] Auto-detect selectors using ML
- [ ] Generate extractor classes automatically
- [ ] Support for multi-page pagination
- [ ] Auto-generate test cases
- [ ] Integration with brand logo enrichment
- [ ] Support for dynamic pricing extraction

### Community Contributions
- Share profiles for common retailers
- Build selector library
- Improve ad type detection heuristics

---

**Created:** 2025-10-27
**Last Updated:** 2025-10-27
**Maintainer:** Retail Ad Monitor Team
