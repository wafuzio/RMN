# Walmart Sparky Investigation Toolkit

Reverse-engineering Walmart's Sparky AI assistant to understand how it surfaces (or buries) Garanimals.

## 🗺️ Navigation

| What you need | Go here |
|---|---|
| **How to capture & process** | `docs/HOW_TO_USE.md` |
| **What we know (living knowledge base)** | `docs/WHAT_WE_KNOW.md` ← update after every session |
| **What to test and in what order** | `docs/ANALYSIS_STRATEGY.md` |
| **Full playbook strategy** | `docs/PLAYBOOK_STRATEGY.md` |
| **Presentation (Tuesday)** | `docs/PRESENTATION_DECK.md` |
| **Core findings reference** | `docs/SPARKY_FINDINGS.md` |
| **API schema & technical details** | `docs/API_SCHEMA.md` |
| **Raw capture log** | `docs/CAPTURE_LOG.md` |
| **Visual dashboard** | `investigation_board.html` |
| **Query list** | `queries/query_list.txt` |

## ⚡ Quick Start

## 📁 Project Structure

```
Walmart_Sparky/
├── README.md                          # This file
├── docs/
│   ├── PRESENTATION_DECK.md          # Tuesday presentation (slide-by-slide)
│   ├── SPARKY_FINDINGS.md            # Consolidated findings reference
│   ├── API_SCHEMA.md                 # Full API reverse-engineering docs
│   └── CAPTURE_LOG.md                # Raw facts log (all 16+ captures)
├── scripts/
│   ├── parse_sparky_capture.py       # HAR/JSON parser for Sparky responses
│   ├── index_catalog.py              # Catalog indexer & query generator
│   ├── probe_sparky.py               # Original probe script
│   ├── add_to_log.py                 # Log helper
│   ├── analyze_latest_capture.py     # Analyze most recent capture
│   └── parse_har_curl.py             # HAR/curl input parser
├── data/
│   ├── captures/                     # Parsed capture data (timestamped JSON)
│   └── sample_romper_query.json      # Example capture
├── queries/
│   ├── catalog_index.json            # Indexed catalog data
│   ├── generated_queries.json        # Query templates by investigation type
│   └── query_list.txt                # Simple text list for copy-paste
├── config/                           # Configuration files
└── investigation_board.html          # Visual progress dashboard
```

## 🚀 Quick Start

### 1. View the Dashboard

```bash
open investigation_board.html
```

### 2. Generate Query Templates from Catalog

```bash
/Users/dan.maguire/Documents/Amazon_Scrape/.venv/bin/python3 scripts/index_catalog.py
```

This will:
- Parse the Garanimals product catalog
- Extract 14 product types (Romper, Jean, Shirt, Short, Dress, etc.)
- Generate 80 query templates across 7 investigation categories
- Save to `queries/` folder

### 3. Capture Sparky Responses (Manual via HTTP Catcher)

**On iPhone:**
1. Open HTTP Catcher app
2. Enable SSL Pinning Bypass
3. Start capture
4. Open Walmart app → Sparky
5. Submit query from `queries/query_list.txt`
6. Export capture as JSON

**Transfer to Mac:**
- AirDrop the JSON file to Mac
- Save to `Walmart_Sparky/data/`

### 4. Parse Captured Response

```bash
/Users/dan.maguire/Documents/Amazon_Scrape/.venv/bin/python3 scripts/parse_sparky_capture.py data/your_capture.json
```

This extracts structured metrics:
- Response mode (product_carousel, editorial, deflection)
- Garanimals visibility (count, positions, share %)
- Product pricing, badges, sellers (1P vs 3P)
- Editorial mentions & Google source domains
- Ad infrastructure status

Output saved to `data/captures/YYYYMMDD_HHMMSS_*_parsed.json`

## 📊 Key Metrics Tracked

### Product Visibility Metrics
- **Garanimals appearance rate**: % of queries where Garanimals appears
- **Average position**: When appearing, what position (1-5 in carousel)
- **Share of voice**: % of total products shown
- **Category coverage**: % of product categories with visibility

### Editorial Perception Metrics
- **Mention rate**: % of editorial responses mentioning Garanimals
- **Sentiment**: Positive/neutral/negative framing
- **Quality positioning**: Premium/value/budget language
- **Competitor comparison frequency**: How often compared to Cat & Jack, TCP, etc.

### Competitive Benchmarking
- **Head-to-head win rate**: When both brands appear, which ranks higher
- **Price positioning**: Garanimals avg vs. competitor avg
- **1P vs 3P displacement**: Are 3P sellers outranking Garanimals

### Ad Infrastructure
- **Ad slot availability**: Tracking `max_ads` changes
- **Competitor ad presence**: When ads go live, who's buying

## 🔍 Investigation Roadmap

### Critical Priority (Do First)
1. **Category Keyword Gap Analysis** - Test all 14 product types from catalog
2. **Mix-and-Match Queries** - Garanimals' core differentiator
3. **Response Mode Trigger Mapping** - Understand what triggers Product vs Editorial
4. **Quality Perception Probing** - Address durability narrative

### High Priority
5. **Branded Query Audit** - Direct Garanimals queries
6. **Editorial Source Mapping** - Which domains shape perception
7. **Durability/Quality Perception** - Cat & Jack comparison

### Medium Priority
8. **Seasonal & Promotional Visibility**
9. **Price Threshold Behavior**
10. **Ad Slot Monitoring** (ongoing)

See `sparky_api_schema.md` for full 16-investigation roadmap.

## 📈 Workflow

### Weekly Capture Session

1. **Select queries** from `queries/query_list.txt` (prioritize untested categories)
2. **Capture via HTTP Catcher** on iPhone
3. **Parse captures** with `parse_sparky_capture.py`
4. **Review dashboard** to identify gaps
5. **Document findings** in `sparky_api_schema.md`

### Longitudinal Tracking

Run the same **20-30 "sentinel queries"** weekly to track changes:
- Generic brand query: "best kids clothing brands walmart"
- Category queries: "toddler rompers", "kids pajamas walmart"
- Quality query: "are garanimals good quality"
- Comparative: "garanimals vs cat and jack"
- Mix-and-match: "mix and match kids clothes"

### Change Detection

Alert on:
- Garanimals drops from top 3 → top 5
- New competitor enters carousel
- Editorial sentiment shifts
- `showAds` flips to true
- New source domains appear in editorial

## 🛠️ Tools Reference

### parse_sparky_capture.py

**Usage:**
```bash
python3 scripts/parse_sparky_capture.py <response_json_file>
```

**Output:**
- Structured JSON with all metrics
- Console summary of key findings
- Saved to `data/captures/` with timestamp

**Import as module:**
```python
from parse_sparky_capture import parse_sparky_response

parsed = parse_sparky_response(response_data, query_text="your query")
```

### index_catalog.py

**Usage:**
```bash
python3 scripts/index_catalog.py
```

**Output:**
- `queries/catalog_index.json` - Indexed catalog (product types, colors, sizes, etc.)
- `queries/generated_queries.json` - 80 query templates by investigation type
- `queries/query_list.txt` - Simple text list for copy-paste

**Catalog Data Extracted:**
- 14 product types (Romper, Jean, Shirt, Short, Dress, Pajama, Swim, Legging, Outfit, Bodysuit, Jumpsuit, Overall, Pant, Skirt)
- 19 finelines
- 119 styles
- 6 genders
- 1,565 total products

### dashboard.html

**Features:**
- Investigation progress matrix
- Product category coverage heatmap
- Query queue (what to test next)
- Recent activity timeline
- Key metrics summary

**Auto-refresh:** Every 30 seconds (when page is open)

**Manual refresh:** Click "🔄 Refresh Data" button

## 📝 Current Status (Mar 16, 2026)

### Captures Completed: 4
1. ✅ "what are the best kids clothing brands at walmart?" - Product carousel, 2/5 Garanimals
2. ✅ "I noticed here that Garanimals didn't make the list of brands. How come?" - Editorial, negative durability framing
3. ✅ "which is better for toddlers, the children's place or garanimals" - Deflection, 3/5 Garanimals
4. ✅ "what are the best selling toddlers rompers at walmart?" - Product carousel, 0/5 Garanimals (CRITICAL GAP)

### Key Findings
- **Romper category gap**: 0/5 visibility despite being a core Garanimals category
- **3P seller dominance**: Chinese marketplace sellers outrank Garanimals in niche categories
- **Editorial perception issue**: Positioned as "affordable everyday" vs. Cat & Jack's "durable"
- **Comparative deflection**: Sparky refuses to make qualitative brand comparisons
- **Ad infrastructure ready**: `max_ads: 4-8`, `showAds: false` (not yet active)

### Next Steps
1. Test all 14 product types from catalog (13 remaining)
2. Run mix-and-match queries (Garanimals' differentiator)
3. Probe quality perception with different phrasings
4. Map editorial source domains

## 🔐 Data Privacy

- All captures contain personal auth tokens, session IDs, and cookies
- **Do not commit** `data/captures/*.json` to git
- Keep `.gitignore` updated to exclude sensitive files
- Use sample/anonymized data for sharing

## 📚 Additional Documentation

- **sparky_api_schema.md** - Full API reverse-engineering documentation
- **queries/catalog_index.json** - Complete catalog taxonomy
- **queries/generated_queries.json** - All query templates with metadata

## 🎯 Success Metrics

Track these over time:
1. **Garanimals visibility rate** increases from current baseline
2. **Average position** improves (closer to position 1)
3. **Category coverage** reaches 100% (visible in all 14 product types)
4. **Editorial mentions** increase and shift to positive framing
5. **3P displacement** decreases (Garanimals outranks marketplace sellers)

## 🤝 Contributing

When adding new captures:
1. Use descriptive filenames: `YYYYMMDD_query_description.json`
2. Run parser immediately after capture
3. Update dashboard manually if needed
4. Document significant findings in `sparky_api_schema.md`

---

**Last Updated:** March 16, 2026  
**Toolkit Version:** 1.0  
**Status:** Active Development
