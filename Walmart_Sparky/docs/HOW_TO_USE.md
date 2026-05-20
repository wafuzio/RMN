# How To Use — Sparky Investigation Toolkit

Step-by-step guide for capturing Sparky responses and processing them into structured data.

---

## Overview: The Full Pipeline

```
iPhone (HTTP Catcher)
        ↓
  Export JSON/curl
        ↓
  Paste into new_capture_input.txt
        ↓
  Run: parse_har_curl.py         ← does steps 2-4 automatically
        ↓
  parse_sparky_capture.py        ← extracts structured metrics
        ↓
  add_to_log.py                  ← formats CAPTURE_LOG.md entry
        ↓
  analyze_latest_capture.py      ← prints analysis prompt
        ↓
  data/captures/TIMESTAMP_parsed.json   ← saved output
  docs/CAPTURE_LOG.md                   ← auto-appended
```

**The Python to use for everything:**
```
/Users/dan.maguire/Documents/Amazon_Scrape/.venv/bin/python3
```

---

## Part 1 — Capturing a Response (iPhone)

### What you need
- iPhone with **HTTP Catcher** app installed
- Walmart app installed and logged in
- Wi-Fi (HTTP Catcher works on same network)

### Step 1 — Set up HTTP Catcher

1. Open **HTTP Catcher** on iPhone
2. Tap **SSL** → enable **SSL Pinning Bypass**
3. Tap the record button (circle) to **start capture**
4. You should see traffic appearing in the list

### Step 2 — Submit a Sparky query

1. Open **Walmart app**
2. Tap the **Sparky icon** (bottom bar or search area)
3. Type your query from `queries/query_list.txt`
4. Wait for Sparky to fully respond (products + preamble visible)
5. **Do not tap anything else** — you want only this request in your capture

### Step 3 — Find the Sparky request in HTTP Catcher

1. In HTTP Catcher, look for a POST request to:
   ```
   www.walmart.com/api-proxy/service/iot/converse-adapter/v1/talk/sparky_assistant
   ```
2. Tap that request
3. Tap **Response** tab → you should see a large JSON blob starting with `{"intentName":`

### Step 4 — Export the capture

**Option A — Export as curl (recommended):**
1. Tap the share icon on the request
2. Select **Copy as curl**
3. AirDrop or email yourself the curl text

**Option B — Export response JSON only:**
1. On the Response tab, tap **Copy** or **Share**
2. Copy the raw JSON text

### Step 5 — Transfer to Mac

- AirDrop the text to your Mac
- Or email it to yourself
- Save/paste the content into:
  ```
  Walmart_Sparky/new_capture_input.txt
  ```

---

## Part 2 — Processing a Capture (Mac)

### All-in-one command (recommended)

From the `Walmart_Sparky/` directory:

```bash
cd /Users/dan.maguire/Documents/Amazon_Scrape/Walmart_Sparky
/Users/dan.maguire/Documents/Amazon_Scrape/.venv/bin/python3 scripts/parse_har_curl.py new_capture_input.txt
```

**This single command:**
1. Extracts query text and response JSON from your input
2. Archives the raw capture to `data/raw_captures/`
3. Parses the response into structured metrics
4. Saves parsed JSON to `data/captures/TIMESTAMP_parsed.json`
5. Generates and **auto-appends** a formatted entry to `docs/CAPTURE_LOG.md`
6. Clears `new_capture_input.txt` for the next capture
7. Prints an analysis prompt

**Example output:**
```
✅ Extracted query: affordable toddler clothes
✅ Extracted response JSON
📦 Archived raw capture to: data/raw_captures/20260516_143022_affordable_toddler_clothes.txt

📊 Summary:
   Response Mode: product_carousel
   Products: 5
   Garanimals: 2 (40.0%)
   Positions: [1, 3]
   Editorial Mention: Yes
   Google Sources: 0

✅ Auto-appended to docs/CAPTURE_LOG.md
🧹 Cleared new_capture_input.txt for next capture
```

### If the all-in-one fails (manual steps)

**Step 1 — Parse the response JSON:**
```bash
/Users/dan.maguire/Documents/Amazon_Scrape/.venv/bin/python3 scripts/parse_sparky_capture.py data/your_response.json
```

**Step 2 — Generate a log entry:**
```bash
/Users/dan.maguire/Documents/Amazon_Scrape/.venv/bin/python3 scripts/add_to_log.py data/captures/TIMESTAMP_parsed.json
```
Copy the output and paste it at the bottom of `docs/CAPTURE_LOG.md`.

**Step 3 — Run analysis prompt:**
```bash
/Users/dan.maguire/Documents/Amazon_Scrape/.venv/bin/python3 scripts/analyze_latest_capture.py
```

---

## Part 3 — After Processing

### Check the parsed output

Open the most recent file in `data/captures/` — it has this structure:
```json
{
  "query_metadata": { "query_text": "...", "timestamp": "..." },
  "response_classification": { "response_mode": "product_carousel", ... },
  "product_metrics": {
    "garanimals_count": 2,
    "garanimals_share": 40.0,
    "garanimals_positions": [1, 3],
    "seller_breakdown": { "1P": 4, "3P": 1 },
    ...
  },
  "editorial_metrics": { "garanimals_mentioned": true, ... },
  "ad_infrastructure": { "max_ads": 4, "ads_active": false, ... },
  "search_query_reformulation": { "original": "...", "reformulated": "..." }
}
```

### Key things to check after every capture

| Field | What to look for |
|-------|-----------------|
| `response_mode` | `product_carousel`, `editorial`, `deflection`, or `deflection` (termination) |
| `seller_breakdown` | If 1P=0, query took 3P route — Garanimals cannot appear |
| `garanimals_count` | 0 = invisible, 1-2 = visible but weak, 3+ = strong visibility |
| `garanimals_positions` | Position 1 = best; position 5 = worst |
| `reformulated` | What Sparky actually searched — tells you how it classified your query |
| `ads_active` | Still `false`? Note the date if it ever becomes `true` |
| `source_domains` | Which external sites grounded editorial responses |

### Update the findings docs if you learn something new

- New routing behavior → update `docs/SPARKY_FINDINGS.md` section 2 or 3
- New editorial source domain → update section 4
- Ad infrastructure change → update section 7
- New open question → add to section 9

---

## Part 4 — Running the Dashboard

```bash
open /Users/dan.maguire/Documents/Amazon_Scrape/Walmart_Sparky/investigation_board.html
```

The dashboard reads from `data/captures/` and shows:
- Investigation progress matrix
- Category coverage heatmap
- Query queue (what to test next)
- Recent activity

---

## Part 5 — Generating New Queries

If you want fresh query templates from the catalog:

```bash
cd /Users/dan.maguire/Documents/Amazon_Scrape/Walmart_Sparky
/Users/dan.maguire/Documents/Amazon_Scrape/.venv/bin/python3 scripts/index_catalog.py
```

Output:
- `queries/catalog_index.json` — full catalog taxonomy
- `queries/generated_queries.json` — 80 templates by investigation type
- `queries/query_list.txt` — plain text list for copy-paste into Sparky

The pre-built `queries/query_list.txt` already has 95 queries across 6 categories. Use that first before regenerating.

---

## Common Issues

**"Could not extract response JSON"**
- Make sure you exported the response body, not the request
- The response must start with `{"intentName":`
- Try exporting as curl command instead of raw JSON

**"Query text not found"**
- The script will ask you to type it manually
- Just type the query you submitted to Sparky

**"File not found: data/captures/..."**
- The parser saves to a path relative to where you run the script
- Always run from the `Walmart_Sparky/` directory

**parse_har_curl.py path errors after reorganization**
- The script has a hardcoded reference to `CAPTURE_LOG.md` (old location)
- If auto-append fails, manually paste the log entry into `docs/CAPTURE_LOG.md`
- This is a known issue from the scripts/ move — fix described below

### Fix for CAPTURE_LOG path (run once)

The scripts were moved to `scripts/` but `parse_har_curl.py` references `CAPTURE_LOG.md` at the old root level. Run this to patch it:

```bash
sed -i '' 's|parent / "CAPTURE_LOG.md"|parent.parent / "docs" / "CAPTURE_LOG.md"|g' \
  /Users/dan.maguire/Documents/Amazon_Scrape/Walmart_Sparky/scripts/parse_har_curl.py
```
