# Instacart Builder.io Integration Guide

**Status**: ✅ API Tests Passing (Local + ngrok)
**Date**: October 27, 2025
**ngrok URL**: `https://foilable-ruthie-consultive.ngrok-free.dev`

---

## Pre-flight Verification (COMPLETED ✅)

- ✅ curl (local) returns cards → **PASS** (100 cards, total 112)
- ✅ curl (local) HEAD image → **PASS** (200 OK)
- ✅ curl (ngrok) HEAD image → **PASS** (200 OK)

---

## Step 1 — Define the API base once in Builder

In your Builder page, add a **Custom Code block (JS)** near the top of the page.

Paste this:

```html
<script>
  // Replace with your current ngrok HTTPS URL (must be https)
  window.AD_BASE = 'https://foilable-ruthie-consultive.ngrok-free.dev';
</script>
```

---

## Step 2 — Load Instacart cards into state

Add another **Custom Code block (JS)** anywhere on the page (top is fine).

Paste this exactly:

```html
<script>
  // Create a holder in Builder state
  if (!state.adCards) state.adCards = [];

  async function loadInstacartAds() {
    const base = window.AD_BASE;
    // Use client=all to load ALL Instacart clients (992 total ads)
    // Or use client=blue_bunny to load just one client
    const url = `${base}/api/ads/cards?retailer=instacart&client=all&page_size=100`;
    const res = await fetch(url, { headers: { 'ngrok-skip-browser-warning': 'true' } });
    if (!res.ok) {
      console.error('cards fetch failed', res.status, url);
      return;
    }
    const data = await res.json();
    state.adCards = Array.isArray(data.cards) ? data.cards : [];
    console.log(`Loaded ${state.adCards.length} of ${data.total_cards} total Instacart ads`);
  }

  // Run once
  loadInstacartAds();
</script>
```

---

## Step 3 — Create the grid in Builder

### 3.1 Insert a Repeat/List Component
1. Insert a **Repeat/List (For Each)** component
2. Set **Items** = `state.adCards`

### 3.2 Inside the repeat, add:

**An Image element:**
- Click the **fx** button next to `src`
- Enter: `window.AD_BASE + item.image_url`

**A Text element for brand/type (optional):**
- Text binding: `{{ item.brand }} • {{ item.ad_type }}`

**A Text element for timestamp (optional):**

First, add this formatter in a small **Custom Code (JS)** block anywhere:

```html
<script>
  window.formatLocal = function(iso) {
    try { return new Date(iso).toLocaleString(); } catch(e) { return iso || ''; }
  }
</script>
```

Then bind Text to:
```
{{ window.formatLocal(item.timestamp) }}
```

---

## Step 4 — Add a modal to show details (optional, recommended)

### 4.1 Create a Modal
Create a **Modal** (or a Box that you toggle with a condition).

### 4.2 Store the clicked card
On the outer grid item (container of the Image/Text):
- Set **onClick** action: `state.selectedCard = item`

### 4.3 Make the modal visible when selectedCard exists
- **Show condition**: `{{ !!state.selectedCard }}`

### 4.4 Inside the modal, add:

**Image (always):**
- src = `window.AD_BASE + state.selectedCard.image_url`

**Optional Video (only if video_url exists):**

Add a **Custom Code (HTML)** block in the modal and paste:

```html
<!-- Video shows only when present -->
{{ state.selectedCard && state.selectedCard.video_url ? `
  <video controls playsinline preload="metadata"
         poster="${window.AD_BASE + (state.selectedCard.poster_url || state.selectedCard.image_url)}"
         src="${window.AD_BASE + state.selectedCard.video_url}"
         style="width:100%;border-radius:12px;margin-top:12px;"></video>
` : '' }}
```

**Close button:**
- On click: `state.selectedCard = null`

---

## Step 5 — Verify in Browser (Network Tab)

1. Open your Builder page in the browser
2. Press **F12** → **Network** tab
3. You must see:
   - A GET to: `https://foilable-ruthie-consultive.ngrok-free.dev/api/ads/cards?retailer=instacart&client=blue_bunny&page_size=24`
   - Status **200**
   - Response JSON with `cards` array
   - One or more GETs to: `https://foilable-ruthie-consultive.ngrok-free.dev/api/image/instacart/blue_bunny/...`
   - Status **200**
   - Type **image/png**

---

## Troubleshooting

### If Builder shows 0 cards:
1. Confirm the fetch call is using `https://foilable-ruthie-consultive.ngrok-free.dev` (not localhost, not an old ngrok)
2. Confirm the Repeat/Items binding is exactly: `state.adCards`
3. Confirm the Data Action code sets `state.adCards` (spelled exactly)
4. Check browser console for errors

### If images don't load:
1. Verify Image src binding is exactly: `window.AD_BASE + item.image_url`
2. Check Network tab for 404s on image requests
3. Verify ngrok URL is correct and hasn't changed

### If you need more than 24 cards:
Change the fetch URL to include `page_size=100`:
```javascript
const url = `${base}/api/ads/cards?retailer=instacart&client=blue_bunny&page_size=100`;
```

---

## Available Data Fields

Each card in `state.adCards` has:

```javascript
{
  "retailer": "instacart",
  "client": "blue_bunny",
  "brand": "Blue Bunny",
  "ad_type": "Shoppable_Display_Ad",
  "advertisers": ["Blue Bunny"],
  "image_url": "/api/image/instacart/blue_bunny/...",
  "video_url": "/api/video/instacart/blue_bunny/..." // if exists
  "timestamp": "2025-10-26T10:13:00Z",
  "timestamp_ms": 1761491580000,
  "keyword": "ice cream bar",
  "message": "...",
  "featured": false,
  "run_file": "run_results_20251026101300.json"
}
```

---

## Quick Reference Commands

**Test API locally:**
```bash
curl -s "http://localhost:5006/api/ads/cards?retailer=instacart&client=blue_bunny&page_size=24" | jq '{cards: (.cards | length), total: .total_cards}'
```

**Test API through ngrok:**
```bash
curl -s "https://foilable-ruthie-consultive.ngrok-free.dev/api/ads/cards?retailer=instacart&client=blue_bunny&page_size=24" -H 'ngrok-skip-browser-warning: true' | jq '{cards: (.cards | length), total: .total_cards}'
```

**Test image through ngrok:**
```bash
curl -I "https://foilable-ruthie-consultive.ngrok-free.dev/api/image/instacart/blue_bunny/Shoppable_Display_Ads/instacart__shoppable_display_ad__blue_bunny__ice_cream_bar__D2025-10-26_T10-13.00_1.png" -H 'ngrok-skip-browser-warning: true'
```

---

## Success Checklist

- [ ] Step 1: `window.AD_BASE` defined in Custom Code (JS)
- [ ] Step 2: `loadInstacartBlueBunny()` function added and runs
- [ ] Step 3: Repeat component bound to `state.adCards`
- [ ] Step 3: Image src bound to `window.AD_BASE + item.image_url`
- [ ] Step 4: Modal created with selectedCard logic
- [ ] Step 5: Network tab shows successful API calls
- [ ] Step 5: Images render in grid
- [ ] Step 5: Modal opens and shows details

---

## Notes

- **Total blue_bunny ads**: 112
- **Canonical migration**: Complete (376 runs migrated, 448 legacy files backed up)
- **API endpoint**: Requires `retailer` and `client` parameters
- **Image resolution**: Working through both local and ngrok
- **CORS**: Configured and working
