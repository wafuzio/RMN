# Amazon Ad Brand Extraction

## Goal

When we scrape Amazon search results, we capture all ad placements (Sponsored Brands, Sponsored Display, Sponsored Products, Sponsored Carousels). Each ad needs a **brand name** assigned so we can track which brands are advertising on which search terms. The brand name is used in:

- JSON data (`advertisers`, `brand`, `brand_canonical` fields)
- Image filenames (`amazon__{brand_slug}__Sponsored_Display__...`)
- The frontend dashboard for reporting

## What's Currently in Place

### At Capture Time (`amazon_search_and_capture.py`)
- **Sponsored Brands**: Brand name extracted from the ad's header text, brand logo alt text, or store URL. Generally reliable.
- **Sponsored Brand Video**: Same as above, plus video metadata.
- **Sponsored Products**: Brand extracted from product listing data. Generally reliable.
- **Sponsored Display**: These are the problem. Display ads are often rendered inside iframes with minimal accessible metadata. The capture code tries to extract brand info but frequently falls back to `"Unknown"`.
- **Sponsored Carousels**: Many are Amazon house ads ("Seen on social media", "Trending now") with no brand. Others have brand info in the carousel header.

### Post-Capture Brand Resolution

1. **Brand Lexicon** (`config/brands.json`): ~700+ brands with synonyms. Used to canonicalize brand names (e.g., `purito_seoul` → `Purito`).

2. **Brand Review Tool** (`brand_review_tool.py`): GUI for manually reviewing unknown/uncertain brands. Shows the ad screenshot and suggests brands from:
   - The ad's own `brand` and `advertisers` fields
   - Product titles in the ad JSON
   - TOA campaign codes
   - URL path segments
   - Message/header text
   - Companion HTML file (lexicon-verified brands only)

3. **Batch Fix Script** (`scripts/batch_fix_unknown_brands_from_html.py`): Automated script that matches unknown display ads to brands found in the companion HTML file's accessibility text, using the lexicon for verification. Matches by slot (one unknown per slot = confident match).

4. **Brand Name Verifier** (`tools/brand_name_verifier.py`): GUI for reviewing newly added brands in the lexicon. Brands saved via the review tool are now auto-marked `verified: true` to skip this step.

### HTML Companion Files
Each scrape saves the raw HTML alongside the JSON. The HTML contains accessibility text for Sponsored Display ads in `<span>` elements:

```
Sponsored Ad.\nBrand logo.\nProduct image.\n{PRODUCT_TITLE}\n{PRICE}\nShop now
```

Four variants exist:
- `Sponsored Ad.\nBranded image.\n{TITLE}`
- `Sponsored Ad.\nBrand logo.\nBranded image.\n{TITLE}`
- `Sponsored Ad.\nBrand logo.\nProduct image.\n{TITLE}`
- `Sponsored Ad.\nProduct image.\n{TITLE}`

Sponsored Products also appear in `aria-label` attributes:
```
aria-label="Sponsored Ad - {BRAND} - {PRODUCT_TITLE}"
```

## Obstacles

### 1. Sponsored Display Ads Have No Metadata
The biggest challenge. Display ads (left rail, bottom of page) are rendered in iframes with no accessible brand name, product title, or advertiser ID in the DOM. The JSON ends up with empty `advertisers`, empty `products`, no `message`, no `href`. The only data we have is the screenshot image and the companion HTML.

### 2. HTML Accessibility Text Covers the Whole Page
The companion HTML contains accessibility spans for ALL ads on the page, not just the one we're looking at. When suggesting brands in the review tool, we can't reliably determine which span belongs to which display ad because:
- No slot/position markers near the spans in the HTML
- No reliable DOM-order-to-JSON-order mapping
- Multiple display ads per page (left rail + bottom)

The batch script works around this by only making confident matches when there's exactly one unknown ad in a slot and one matching lexicon brand in the HTML.

### 3. Regex Escaping
The HTML files contain double-escaped text (`\\n` as literal backslash + n, not newline). Getting the regex right requires `r'\\\\n'` in raw Python strings, which has been a recurring source of bugs.

### 4. Slug vs Display Name Mismatch
Brand names in the JSON are often stored as slugs (`purito_seoul`, `e_l_f`) while the lexicon has display names (`Purito`, `e.l.f.`). The normalization function now handles underscores, but edge cases remain (e.g., `e.l.f.` → `elf` vs `e_l_f` → `e l f`).

### 5. Corrupted Data from Previous Fix Scripts
A previous bulk rename script corrupted paths by replacing the substring `on` globally, turning `Sponsored` into `Spno_optimum_nutritinosored`. This affected 72 paths across 36 JSON files (now fixed).

### 6. Amazon House Ads
Many carousel ads are Amazon's own algorithmic recommendations ("Customers frequently viewed", "Seen on social media"). These have no brand and should be skipped, but some have generic labels like "Unknown Carousel" that we assigned ourselves, making them hard to auto-filter.

## Current State

- ~225 unknown Sponsored Display ads remain across all scrapes
- ~50 ads with slug-format brands now auto-resolve to lexicon entries (underscore fix)
- 26 ads were batch-fixed via HTML lexicon matching
- The review tool now shows proper display names and lexicon-verified suggestions
- Brands saved in the review tool are auto-verified in the lexicon

## Claude Opus 4.6 Recommendation

Brand Extraction: Path Forward
The Core Problem
~225 Sponsored Display ads end up with "Unknown" brand because display ads render inside iframes with no accessible metadata at capture time. The only reliable brand signal lives in the companion HTML's accessibility spans, but those spans cover the entire page with no positional anchors to map them back to specific ads.

Current Pipeline Gaps
Capture time (_extract_brand_and_message): Tries aria-label, img[alt], store URLs, product links — all of which are inside the iframe and inaccessible. Falls back to "Unknown".
Post-capture batch fix (batch_fix_unknown_brands_from_html.py): Only makes confident matches when there's exactly one unknown ad per slot and one lexicon-matched brand in the HTML. This is too conservative — it fixed only 26 out of 225.
Manual review (brand_review_tool.py): Shows the screenshot and suggestions, but requires human eyeballs for every remaining ad. This is the babysitting bottleneck.
Recommended Strategy: Extract Brand at Capture Time from the Page DOM (Not the Iframe)
The key insight is that the accessibility spans (Sponsored Ad.\nBrand logo.\nProduct image.\n{PRODUCT_TITLE}) exist in the outer page DOM, not inside the iframe. At capture time, you have the live page with positional information — you can correlate each display ad container's bounding box with the nearest accessibility span's position in the DOM.

Phase 1: Capture-Time Positional Matching (Highest Impact)
What to do: After finding each display ad container, before saving it as "Unknown", query the parent page (not the iframe) for nearby accessibility spans using DOM proximity or bounding-box proximity.

python
### Pseudocode for the new extraction step in amazon_search_and_capture.py
### After line ~1940 where _extract_brand_and_message returns no brand:
 
if not brand_txt:
    # Look for accessibility spans near this ad's position in the outer DOM
    # These spans have the pattern: "Sponsored Ad.\nBrand logo.\n...\n{TITLE}"
    try:
        ad_bbox = ad.bounding_box()
        if ad_bbox:
            # Find all accessibility spans on the page
            a11y_spans = page.locator('span.a-offscreen, span.aok-offscreen').all()
            for span in a11y_spans:
                span_text = span.inner_text()
                if 'Sponsored Ad' not in span_text:
                    continue
                span_bbox = span.bounding_box()
                if span_bbox and _is_near(ad_bbox, span_bbox):
                    # Extract product title from the span text
                    title = parse_a11y_title(span_text)
                    brand_txt = match_title_to_lexicon(title, lexicon)
    except Exception:
        pass
Why this works: At capture time you have both the ad element and the accessibility span on the same live page. You can use geometric proximity (bounding boxes) or DOM ancestry (find the nearest Sponsored Ad span that shares a common ancestor with the ad container) to make a positional match — the exact thing that's impossible post-capture.

Expected impact: Should resolve the majority of the ~225 unknowns automatically, with zero manual review.

Phase 2: Improve the Batch Fix Script (Medium Impact)
For the backlog and any ads that still slip through, improve batch_fix_unknown_brands_from_html.py:

Slot-aware matching: The HTML DOM has structural markers (s-left-ads-item, desktop-ad-*, cel_widget_id) near the accessibility spans. Parse the HTML with BeautifulSoup instead of regex, walk up from each Sponsored Ad span to find its containing slot, then match to the JSON ad's slot field.
Product description cross-reference: The capture script already extracts product_description for some display ads. Match this against the HTML accessibility span's product title for a second confirmation signal.
Relax the 1:1 constraint: When there are N unknowns in a slot and N brand matches in the HTML for that slot, assign them in DOM order (which corresponds to visual order top-to-bottom).
Phase 3: Auto-Grow the Lexicon (Low Effort, Compounding Returns)
When the batch fix or capture-time extraction finds a brand via the accessibility span's product title, and the title clearly starts with a brand name (e.g., "Purito Daily Go-To Sunscreen"), auto-add that brand to the lexicon if it's not already there.
This is partially implemented (add_brand in _extract_brand_and_message) but isn't triggered for display ads since they never get a brand at capture time.
Phase 4: Reduce Manual Review to Edge Cases Only
After Phases 1-3, the brand review tool should only show ads where:

No accessibility span was found (rare — page didn't fully load)
The product title doesn't start with a known brand (genuinely new brand)
Multiple conflicting brands in the same slot
This should reduce the manual queue from ~225 to perhaps 10-20 per batch.

What NOT to Do
OCR/Vision on screenshots: Tempting but fragile, slow, and adds a heavy dependency. The accessibility text already contains the same information in structured form.
Amazon Product API lookups: Adds external dependency, rate limits, and API key management. The data is already on the page.
LLM-based brand extraction: Overkill when the accessibility spans give you structured {BRAND} {PRODUCT_TITLE} text that the lexicon can match deterministically.
Implementation Priority
Phase	Effort	Impact	Unknowns Resolved
1. Capture-time positional matching	~2-3 hours	High	~80% of new scrapes
2. Improved batch fix	~2 hours	Medium	~60% of backlog
3. Auto-grow lexicon	~30 min	Compounding	Prevents future unknowns
4. Tighten review tool filters	~30 min	Quality of life	N/A
My recommendation: Start with Phase 1 — it's the highest-leverage change and eliminates the problem at the source. Want me to implement it?

## SWE-1.5 Recommendation

### Recommended Solution
Core Problem
Sponsored Display ads are rendered in iframes with no accessible metadata, leaving ~225 unknown brands that require manual intervention.

Optimal Strategy: Enhanced HTML-Driven Brand Resolution
1. Improve HTML Accessibility Text Matching

The current batch script only matches when there's exactly 1 unknown ad per slot
Enhancement: Implement positional mapping by correlating screenshot coordinates with HTML element positions
Use DOM order + visual layout patterns to reliably map HTML spans to specific display ads
2. Augment Real-Time Extraction During Capture Instead of post-processing, extract brand data during the initial scrape:

python
### Add to Sponsored Display detection in amazon_search_and_capture.py
def extract_display_ad_brand(ad_element, html_companion_path):
    # Method 1: Enhanced accessibility text parsing
    # Method 2: Screenshot OCR for brand logos  
    # Method 3: Iframe content extraction where possible
    # Method 4: Ad network creative ID analysis
3. Implement Confidence-Based Auto-Resolution

High confidence (auto-apply): Lexicon-verified brands + HTML positional match
Medium confidence (flag for review): Partial matches + visual similarity
Low confidence (manual review only): No clear matches
4. Add Visual Brand Recognition

Integrate with the existing brand_logo_database.py
Use image hashing to match unknown ads against known brand logos
Auto-resolve when visual confidence > 85%
Implementation Priority
Phase 1: Enhanced HTML Processing (Immediate - 2-3 days)

Modify scripts/batch_fix_unknown_brands_from_html.py to use positional mapping
Improve regex patterns for the 4 HTML accessibility variants
Add confidence scoring to matches
Phase 2: Real-Time Enhancement (1 week)

Update amazon_search_and_capture.py Sponsored Display section
Add HTML companion file processing during capture
Integrate with existing lexicon for immediate canonicalization
Phase 3: Visual Recognition (2 weeks)

Enhance brand_logo_database.py with logo matching
Add OCR fallback for text-based brand identification
Implement machine learning for unknown brand pattern recognition
Expected Results
Reduce manual review by 80% (from 225 to ~45 unknown ads)
Eliminate babysitting through confidence-based auto-resolution
Improve accuracy with multi-method validation
Scale efficiently as new ad formats emerge
Quick Win - Start Here
Run the enhanced batch script with positional mapping to immediately resolve ~100 of the 225 unknown ads, then implement the real-time enhancements to prevent future accumulation.

This approach leverages your existing infrastructure while adding intelligent automation that will scale with Amazon's evolving ad formats.

## GPT 5.2 Codex Recommendation

✅ Key Observations (Current State)
Sponsored Display ads are the primary failure point: no DOM metadata, only screenshot + companion HTML text. @docs/amazon_brand_extraction.md#56-65
The batch fixer already works when there’s a confident 1:1 match in HTML text. @scripts/batch_fix_unknown_brands_from_html.py#137-193
The review tool is already good, but manual review remains costly at ~225 unknowns. @docs/amazon_brand_extraction.md#81-84
✅ Best Path Forward (Minimal Babysitting)
1) Make HTML Matching Stronger & More Deterministic
Current batch script only uses simple title-to-lexicon matching and slot heuristics. Extend it so it:

Scores each unknown ad against all HTML accessibility titles (e.g., fuzzy match on product title keywords).
Picks the highest confidence pairings per slot; only auto-apply above threshold.
This turns many “ambiguous” matches into confident auto-fixes.
Why: The HTML contains product titles for display ads already; we just need a better matching strategy. @docs/amazon_brand_extraction.md#36-47

Where to implement: scripts/batch_fix_unknown_brands_from_html.py
@ scripts/batch_fix_unknown_brands_from_html.py#37-193

2) Add an OCR fallback for hard cases
You already have OCR infrastructure. For the remaining ~100–150 display ads after better HTML matching:

Run OCR on the screenshot.
Match detected text against lexicon brands.
Only apply if there’s a clean single match.
Why: Display ads often have large brand logos or brand names visible, and screenshots are already saved.
Where: extractors/ocr_brand_detector.py (exists), but currently not integrated into the batch fixing flow.
@extractors/ocr_brand_detector.py

3) Make Manual Review Faster & Safer
The review tool is solid, but add two “fast-pass” improvements:

Auto-suggest top 3 lexicon matches from OCR + HTML.
Auto-advance on save + auto-apply to similar images, which is already partially implemented with imagehash.
@brand_review_tool.py#26-59
This cuts review time in half for the tail cases.

4) Introduce a “House Ad” Auto-Classifier
Many carousel ads are Amazon house ads; these should be skipped.
Add a small classifier that flags house ads if:

No brand in HTML and
Headline matches known house phrases.
Where: Capture-time or batch-fix stage.
@docs/amazon_brand_extraction.md#76-77

5) Lock in Canonicalization at Capture
Sponsored Display ads should still flow through lexicon canonicalization like Walmart/Kroger. Right now Amazon capture does some canonicalization but still relies on raw data. Tighten it so every brand string gets normalized immediately, even if from OCR/HTML.
@amazon_search_and_capture.py#306-317
@utils/brand_utils.py#12-60

✅ Recommended Execution Order
Upgrade batch HTML matcher (fastest wins, most impact).
Add OCR fallback to batch fixing (covers the rest).
Speed up the review tool for tail cases.
Add house-ad classifier to remove noise.
Enforce canonicalization everywhere.

## Gemini 3 Pro Recommendation

PROPOSAL_AMAZON_BRAND_EXTRACTION.md
new
+71
### Proposal: Robust Amazon Brand Extraction via Iframe Piercing & Network Capture
 
### Executive Summary
 
The current "Unknown Brand" issue stems from Sponsored Display ads being rendered inside **iframes**. The current capture script (`amazon_search_and_capture.py`) scans the main page DOM, which cannot see inside these iframes. As a result, it misses the accessibility text and metadata that exists within the ad's protected document context.
 
The post-processing attempts (HTML matching) are fragile because they rely on guessing which "accessibility span" in the global HTML corresponds to which "unknown iframe" in the list.
 
**The Solution**: Move the extraction "left" — capture the data accurately during the scrape by "piercing" the iframes using Playwright's Frame API, and supplement this with Network Interception to grab raw ad data.
 
---
 
### Recommended Path Forward
 
### Phase 1: Direct Iframe Extraction (High Impact, Low Effort)
 
Playwright has native support for accessing content inside iframes (`frame.locator(...)`), but the current script treats iframes as black boxes.
 
**Technical Change:**
Modify `amazon_search_and_capture.py` to:
1. Identify when an ad container hosts an iframe.
2. Get the Playwright `Frame` object associated with that element.
3. Query the *internal* DOM of that frame for:
   - `a[href]` (Store links, Product links)
   - `img[alt]` (Brand logos)
   - `div[aria-label]` or `span` containing "Sponsored ad" text.
 
**Why this wins:**
- **Zero Ambiguity**: We extract metadata from the *exact* iframe we are screenshotting. No need to map lists later.
- **Access to Hidden Data**: The "accessibility text" mentioned in the issue (`Sponsored Ad.\nBrand logo...`) is often actually *inside* the iframe's DOM, which we are currently ignoring.
 
### Phase 2: Network Response Interception (Robustness)
 
Amazon populates these ads via dynamic XHR/Fetch requests (often to endpoints like `/s/s-ad-ajax` or external DSP domains). These responses contain the structured JSON data (Brand Name, ASIN, Image URLs) used to render the ad.
 
**Technical Change:**
Add a Playwright network listener:
```python
page.on("response", handle_response)
```
- Capture JSON responses associated with ad loading.
- Map them to ad slots via `data-uuid` or `cel_widget_id`.
 
**Why this wins:**
- **Source of Truth**: Bypasses the DOM rendering entirely.
- **Resilient**: Even if Amazon changes the DOM structure/classes, the data payload often remains stable.
 
---
 
### Implementation Plan
 
### Step 1: Proof of Concept (Iframe Piercing)
Create a test script (or modify `amazon_search_and_capture.py`) to:
1. Iterate over all `iframe` elements in `page.frames`.
2. Print their URL and title.
3. Try to locate `text="Sponsored"` or `a[href*="/stores/"]` inside them.
 
### Step 2: Integrate into Capture Loop
Update `amazon_search_and_capture.py`'s `_extract_brand_and_message` function:
- If the container contains an iframe, switch context to the frame.
- Run the existing brand regex extractors *inside* the frame context.
 
### Step 3: Deprecate Post-Processing
Once capture is accurate, the `batch_fix_unknown_brands_from_html.py` script becomes a safety net rather than a primary tool.
 
### Time Estimate
- **Phase 1 (Iframe Logic)**: ~1-2 hours coding & testing.
- **Phase 2 (Network)**: ~2-3 hours (requires analyzing traffic patterns first).
 
This approach will likely reduce "Unknown" brands by >90% without requiring constant maintenance of the HTML matching script.
 

I've analyzed the codebase and the issue at docs/amazon_brand_extraction.md. The core problem is that the current extraction logic in amazon_search_and_capture.py scans the main page DOM but cannot "see" inside the <iframe> elements where Sponsored Display ads render their metadata and accessibility text. The current post-processing scripts are fragile because they attempt to match global HTML strings to ads based on loose list-position guessing.

I have created a detailed technical proposal at docs/PROPOSAL_AMAZON_BRAND_EXTRACTION.md.

Recommended Path Forward
The most efficient and "set-it-and-forget-it" solution is to move the extraction logic "left"—capturing the data accurately at scrape time rather than guessing later.

Phase 1: Iframe Piercing (High Impact)
Current State: The script sees <iframe id="ad-..." ...></iframe> and stops.
Proposed Fix: Update amazon_search_and_capture.py to use Playwright's frame API. When an ad container is an iframe, we switch contexts into that frame. The "missing" accessibility text (Sponsored Ad...) is often fully accessible inside that child frame's DOM.
Benefit: 100% accurate mapping between the screenshot and the metadata. No more guessing which "unknown" ad belongs to which "brand string" in the HTML.
Phase 2: Network Interception (Robustness)
Proposed Fix: Add a listener for Amazon's ad-load XHR/JSON responses (page.on("response", ...)) during the search.
Benefit: Captures the raw structured data (Brand, ASIN, Image URL) directly from the wire, bypassing DOM rendering issues entirely.
Next Steps
I recommend starting with Phase 1. It requires modifying _extract_brand_and_message in amazon_search_and_capture.py to detect iframes and query their internal content. This should resolve >90% of "Unknown" cases immediately.

Would you like me to proceed with implementing the Iframe Piercing logic in amazon_search_and_capture.py?

## Claude Sonnet 4.5 Recommendation

Recommended Path Forward for Minimal-Babysitting Brand Extraction
Based on my analysis of your codebase and the documented issues, here's the most efficient approach:

Immediate High-Impact Solutions
1. AI-Powered Visual Brand Recognition (Highest ROI)
The ~225 unknown Sponsored Display ads have screenshots but no metadata. Implement automated visual brand recognition:

Implementation:

Use OpenAI Vision API or similar to analyze ad screenshots
Extract brand names directly from logos/text in images
Cross-reference against your 700+ brand lexicon for validation
Auto-update JSON + rename files
Why this works:

You already have the screenshots
Display ads are designed to show brand prominently
One-time processing eliminates manual review
Can batch process all unknowns overnight
2. Enhanced HTML Parsing with Position Mapping
Your HTML companion files contain the data but lack position markers. Fix this:

At capture time (amazon_search_and_capture.py):

Inject unique data attributes into display ad containers before screenshot
Save position metadata (slot, DOM index, bbox) to JSON
This creates reliable HTML-to-JSON mapping
Benefits:

Batch script can confidently match HTML spans to specific ads
Eliminates the "one unknown per slot" limitation
Reduces unknowns by ~80% automatically
3. Lexicon Auto-Expansion from Product Titles
Your HTML has product titles in accessibility text. Automate brand extraction:

python
###   Extract first 1-2 capitalized words from product titles
### Cross-check against Amazon brand registry API or web search
### Auto-add to lexicon with confidence scores
Architecture Improvements
4. Confidence Scoring System
Replace binary unknown/known with confidence levels:

high (90%+): Auto-accept, no review needed
medium (60-90%): Flag for quick review
low (<60%): Manual review required
5. Brand Logo Database Enhancement
You have BrandLogoDatabase - expand it:

Scrape brand logos from verified ads
Use perceptual hashing for matching
Auto-match new display ads to known logo signatures
Recommended Implementation Order
Week 1: Add position metadata to capture script + AI vision for current unknowns
Week 2: Enhanced HTML parsing with new position data
Week 3: Lexicon auto-expansion + confidence scoring
Week 4: Logo database expansion for ongoing automation
Expected Outcome
95%+ automation for new scrapes
Zero manual review for high-confidence matches
~5% edge cases requiring quick human verification
One-time cleanup of existing 225 unknowns via AI vision

## Evaluations and Top 2 Rankings

### Gemini's:

1. Gemini 3 Pro (Iframe Piercing & Network Interception)
Rank: ⭐⭐⭐⭐⭐ (Best) Qualification: This approach correctly identifies the root cause: the data exists but is encapsulated within <iframe> boundaries or network responses that the current scraper ignores.

Why it wins: It proposes a deterministic solution (reading the actual ad content via Playwright's Frame API) rather than relying on probabilistic "fuzzy matching" or expensive external APIs. It moves the data extraction to the source (capture time), ensuring 100% accuracy in mapping metadata to screenshots.
Feasibility: High. Playwright native support for frames (frame.locator) and network interception (page.on('response')) makes this a code-only change with no new infrastructure.
2. Claude Opus 4.6 (Capture-Time Positional Matching)
Rank: ⭐⭐⭐⭐ Qualification: This model effectively argues for solving the problem at capture time rather than post-processing.

Why it's good: The insight to use geometric proximity (bounding boxes) to link "offscreen" accessibility spans to ad containers is clever. It attempts to use the DOM structure that is already there.
The Risk: It relies on the assumption that Amazon's "offscreen" accessibility spans have valid geometric coordinates near the ad. If Amazon implements them as position: absolute; top: 0; left: 0 (common for screen reader text), this geometric linking will fail.

### Claude Opus's:

1. Gemini 3 Pro — Best
Key insight: Iframe piercing via Playwright's Frame API.

This is the only response that correctly identifies the root technical cause — the capture script treats iframes as opaque boxes, but Playwright natively supports frame.locator() to query inside them. Every other model either assumed the accessibility text is in the outer DOM (unverified) or punted to post-processing.

Strengths:

Technically precise: The iframe piercing approach gives you a 1:1 mapping between the ad you're screenshotting and the metadata you extract. Zero ambiguity.
Network interception (Phase 2) is a genuinely novel idea none of the others mentioned. Amazon's ad payloads contain structured brand/ASIN data that bypasses DOM fragility entirely.
Realistic scope: 1-2 hours for Phase 1, 2-3 hours for Phase 2. No multi-week roadmaps.
Correctly deprecates post-processing: Recognizes that fixing the source eliminates the need for batch fix scripts.
Weaknesses:

Assumes the accessibility text is inside the iframe DOM. This needs verification — Amazon's ad iframes are often cross-origin, which would block frame.locator() even in Playwright. The response doesn't acknowledge this risk.
The network interception idea is good but underspecified — Amazon's ad endpoints are obfuscated and change frequently.
2. Claude Opus 4.6 (my earlier response) — Second
Key insight: Bounding-box proximity matching between display ad containers and accessibility spans at capture time.

Strengths:

Correctly identified that capture time is the right moment — you have positional data that's lost post-capture.
Phased approach is practical: Phase 1 (capture-time matching) → Phase 2 (improved batch fix) → Phase 3 (auto-grow lexicon) → Phase 4 (tighten review).
"What NOT to do" section is valuable — explicitly rules out OCR, API lookups, and LLMs with clear reasoning.
Addresses the backlog (Phase 2 with BeautifulSoup slot-aware parsing), not just future scrapes.
Weaknesses:

The bounding-box proximity approach assumes the accessibility spans are in the outer page DOM near the iframe. This is plausible but unverified — if the spans are actually inside the iframe, this approach fails for the same reason the current code does.
Didn't consider iframe piercing, which is a more direct solution if feasible.
The pseudocode uses span.a-offscreen, span.aok-offscreen selectors that are assumed, not confirmed from the actual HTML.

### SWE's:

1. Claude Opus 4.6 - Best
Why it's best:

Deep technical understanding of the root cause (iframe accessibility vs page DOM)
Pragmatic, phased approach with clear effort/impact matrix
Specific implementation details with actual code patterns
Avoids over-engineering while leveraging existing infrastructure
2. SWE-1.5 - Second Best
Why it's strong:

Very practical and implementation-focused with realistic timelines
Enhanced HTML processing is the right technical approach
Confidence-based auto-resolution is smart for risk management
Visual brand recognition leverages existing brand_logo_database.py
Clear phased approach with immediate wins (2-3 days) vs longer-term improvements
Why not #1:

Less technical depth than Opus - doesn't explain the "why" as thoroughly
OCR/visual recognition adds complexity that might not be necessary
Doesn't fully leverage the capture-time positional matching opportunity

### GPT's:

1) Claude Opus 4.6
Why best:

Most aligned with your actual constraints and signals: recognizes accessibility spans in outer DOM and proposes capture-time positional matching, which directly solves the “no mapping” issue.
Clear phased plan, avoids unnecessary dependencies, and explicitly rejects heavy OCR/LLM/API paths.
Targets highest-leverage fix first.
2) GPT 5.2 Codex
Why:

Pragmatic and grounded in your current tooling; improves batch matching + suggests OCR fallback + review-tool optimization.
Less bold than Opus (still post-capture focused), but it’s a safe incremental path with real ROI.
Slightly weaker because it doesn’t address the core mapping limitation at capture time.
