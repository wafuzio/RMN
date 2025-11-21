# Amazon Sponsored Brand Video Brand Signals

This document summarizes **brand-related signals** found in existing Amazon HTML captures under `output/amazon/**/runs/*.html`, focusing on:

- **Aria-labels** matching the SBV pattern `Sponsored ad from <Brand>...`
- **`img[alt]` values** that pass the current brand heuristic in `_extract_brand_and_message` (short, non‑review, not mostly numeric).

Each section corresponds to a specific HTML capture.

---

## `output/amazon/tax_test_wmt/runs/search_results_amazon_tax_test_wmt_20251120_093736.html`

- **Matched aria-label patterns:**
  - *(none)*

- **`img alt` brand candidates (after filters):**
  - `Thumbs up feedback` ×1
  - `Thumbs down feedback` ×1
  - `Scroll` ×1
  - `Icon` ×2
  - `Amazon One Medical` ×1
  - `Amazon Pharmacy` ×1
  - `Kate Somerville` ×4
  - `DERMALOGY by NEOGENLAB` ×4
  - `Climate Pledge Friendly` ×1

---

## `output/amazon/test6/runs/search_results_amazon_test6_20251120_104427.html`

- **Matched aria-label patterns:**
  - `Sponsored ad from Murad. &quot;Clear + prevent acne for healthier-looking skin.&quot; Shop Murad.` → **brand:** `Murad`

- **`img alt` brand candidates (after filters):**
  - `TNF Bills vs Texans` ×1
  - `Thumbs up feedback` ×1
  - `Thumbs down feedback` ×1
  - `Scroll` ×1
  - `Icon` ×2
  - `Murad` ×5
  - `Amazon One Medical` ×1
  - `Amazon Pharmacy` ×1
  - `Kate Somerville` ×4
  - `Clinique` ×4
  - `Climate Pledge Friendly` ×1

---

## `output/amazon/test7/runs/search_results_amazon_test7_20251120_113320.html`

- **Matched aria-label patterns:**
  - `Sponsored ad from Murad. &quot;Clear + prevent acne for healthier-looking skin.&quot; Shop Murad.` → **brand:** `Murad`

- **`img alt` brand candidates (after filters):**
  - `TNF Bills vs Texans` ×1
  - `Thumbs up feedback` ×1
  - `Thumbs down feedback` ×1
  - `Scroll` ×1
  - `Icon` ×2
  - `Murad` ×5
  - `Amazon One Medical` ×1
  - `Amazon Pharmacy` ×1
  - `Kate Somerville` ×4
  - `DERMALOGY by NEOGENLAB` ×4
  - `Climate Pledge Friendly` ×1

---

## `output/amazon/test_3/runs/search_results_amazon_test_3_20251120_100033.html`

- **Matched aria-label patterns:**
  - *(none)*

- **`img alt` brand candidates (after filters):**
  - `Thumbs up feedback` ×1
  - `Thumbs down feedback` ×1
  - `Scroll` ×1
  - `Icon` ×2
  - `Amazon Basics` ×1
  - `Bath &amp; body` ×1
  - `Beauty` ×1
  - `Personal care` ×1
  - `Kate Somerville` ×4
  - `DERMALOGY by NEOGENLAB` ×4
  - `Medicube` ×4
  - `Climate Pledge Friendly` ×1

---

## `output/amazon/wmt/runs/search_results_amazon_wmt_20251120_064206.html`

- **Matched aria-label patterns:**
  - *(none)*

- **`img alt` brand candidates (after filters):**
  - `Thumbs up feedback` ×1
  - `Thumbs down feedback` ×1
  - `Scroll` ×1
  - `Icon` ×2
  - `One Medical Logo` ×2
  - `Amazon One Medical` ×1
  - `Amazon Pharmacy` ×1
  - `Kate Somerville` ×4
  - `The Ordinary` ×4
  - `DERMALOGY by NEOGENLAB` ×4
  - `Climate Pledge Friendly` ×1

---

### Notes

- This file reflects **current heuristic behavior** (after the latest `_extract_brand_and_message` changes).
- Values like `Thumbs up feedback`, `Scroll`, `Icon`, and `Climate Pledge Friendly` are technically passing the length/numeric filters, but they are **UI/badge alts**, not true brands. We can further refine the heuristic to exclude these patterns if needed.
- Real brand names appearing here (e.g. `Murad`, `Kate Somerville`, `Clinique`, `Medicube`, `The Ordinary`, `Amazon One Medical`) are good candidates for primary brand extraction when aria-labels are missing.
