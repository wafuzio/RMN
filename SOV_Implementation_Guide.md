# Retail Media SOV-to-Spend Model
# Implementation Guide (Revised)

---

## Executive Summary

This document provides a complete implementation roadmap for building a retail media intelligence platform that correlates advertising spend with Share of Voice (SOV) metrics. The system enables CPG brands to understand competitive dynamics and optimize media spend across Amazon, Walmart, Kroger, and Instacart.

**Key Architecture Shift:** This guide builds a BI-first data foundation, not a bespoke dashboard. The primary deliverable is a semantic data model that supports ad-hoc analysis and monthly budget allocation decisions. The API exists for programmatic access, but the BI tool is the primary consumption layer.

---

## What We're Building

**Core Product:** A tool that shows CPG brands how much advertising spend is required to gain market share (measured as SOV) in retail media environments.

**Primary Value Proposition:** Move from reactive reporting ("here's what happened") to predictive planning ("here's what it will cost to achieve your target").

**Primary Use Case:** Monthly budget allocation across product groups and retailers, supported by flexible ad-hoc analysis for campaign optimization.

### System Components

- **Data Collection:** Automated scraping of search results pages (3x daily: morning, midday, evening) across four retailers, capturing all ad placements including those missed by platform reporting (Skai/Pacvue).

- **Semantic Data Model:** Fact and dimension tables at keyword × brand × retailer × date grain, enabling flexible querying through BI tools.

- **SOV Calculation:** Weighted share-of-voice metrics that account for ad placement quality (top-of-page vs bottom), ad type (sponsored search vs display), and search volume.

- **Competitive Intelligence:** Track competitor presence, identify budget-capped competitors, measure competitive density per keyword with trend analysis.

- **Spend Correlation Model:** Empirical model that maps advertising spend to SOV gains, segmented by competitive intensity, rolled up to product group × retailer level.

- **Efficiency Matrix:** Product group × retailer view showing marginal cost per SOV point, the primary artifact for budget allocation decisions.

---

## Why This Approach Works

- **You Control the Bids:** Since you're running campaigns through Skai/Pacvue, you have exact spend data, CPC, and impression metrics. This eliminates the inference problem—you're not guessing at competitor spend, you're measuring your own direct correlation.

- **Scraper as Ground Truth:** Platform metrics (impression share) don't capture organic placements, banner ads, or cross-keyword effects. Your scraper shows the actual shelf space captured.

- **Bounded Category Definition:** By defining SOV within a specific keyword set (5-10 core terms that represent 80% of category volume), you're measuring meaningful competitive space—the frozen aisle, not random brand mentions throughout the store.

- **Hierarchical Subcategories:** Ice cream pints, bars, and lactose-free can overlap. A brand can be measured simultaneously across multiple lenses (format, attribute, positioning), providing strategic flexibility.

- **BI-First Architecture:** The data model is designed to answer questions you haven't thought of yet, not just serve pre-built dashboards.

---

## Key Considerations & Design Decisions

### 1. Desktop-Only Scraping

**Constraint:** No separate bid structure for mobile vs desktop in retail media platforms.

**Solution:** Scrape desktop only, treat it as the benchmark. Apply blended calculation (desktop + mobile estimate) as the primary reported metric, with explicit transparency about methodology and ±15% accuracy band. This addresses the cognitive dissonance problem when clients compare your numbers to platform dashboards.

**Rationale:** Reporting desktop-only creates constant "why is this different from Skai?" questions. Blended SOV with documented methodology maintains credibility while being honest about what's measured vs estimated.

### 2. Scraping Frequency

**Current:** 3x daily (morning, midday, evening).

**Purpose:** Identify budget pacing patterns. Brands that disappear by evening are capping daily spend. This affects competitive intensity throughout the day.

**Future:** Can increase to hourly if needed, but not required for MVP.

### 3. Keyword Selection Strategy

**Principle:** The keyword set defines the category. Only include high-relevance, high-volume, commercially viable terms.

**Exclusions:** Ignore accidental broad-match spillover (e.g., ice cream brand showing on "keto chips"). That's wasted budget, not competitive space.

**Analogy:** You're measuring the frozen dessert aisle, not tracking down every random brand mention in the store.

### 4. Branded vs Category Keywords

**Decision:** Track separately. Branded keywords serve a different function (defense) than category keywords (offense).

- **Category SOV:** Competitive market share on terms like "ice cream bars," "low calorie ice cream."
- **Brand Defense:** SOV on own brand name. Should be 95%+. If not, competitors are conquesting you.

**Rationale:** Mixing branded and category keywords pollutes the spend-to-SOV model. Cost curves are completely different.

### 5. Subcategory Overlap

Subcategories can overlap. "Keto ice cream" might be 6% of total category. "Ice cream bars" might be 22%. A "keto ice cream bar" belongs to both. This is fine—you're providing multiple valid lenses on the same competitive space.

- **Format lens:** Pints, bars, pops
- **Attribute lens:** Keto, low-cal, lactose-free
- **Positioning lens:** Premium, value, organic

Each keyword gets tagged with all relevant classifications. SOV rollup filters by whichever dimension the client cares about.

### 6. Data Retention

**Current state:** Every scrape snapshot is stored permanently. Raw HTML, structured JSON, screenshots, videos. 66,000 ads across 974 brands since November.

**Why this matters:** SOV is computed on-demand from raw placement data. No pre-aggregation. This allows flexible querying (any date range, any keyword combination, any subcategory lens) but will require optimization (caching layer) once dataset grows beyond ~200k ads.

### 7. Cross-Retailer Comparability

**Critical Note:** Raw SOV is NOT directly comparable across retailers (different competitive sets, different ad inventories, different category sizes).

**The Right Comparison:** Marginal cost per SOV point IS comparable across retailers because it's denominated in dollars. "The next $10k on Amazon buys you X points vs Y points on Walmart" is a valid comparison.

**Implication:** Never build a "total SOV across all retailers" rollup. Always compare efficiency (cost per point), not absolute SOV percentages.

---

## Implementation Phases

The system is built in six sequential phases. Each phase produces a testable deliverable with clear approval gates. Do not proceed to the next phase until the current phase's approval gate is passed.

---

## PHASE 1: Positional Value Framework

### Objective

Create a weighted SOV multiplier table that assigns value to each ad placement based on position, type, and retailer. Establish keyword taxonomy with subcategory classifications.

### Why This Matters

Not all ad placements are equal. A top-of-search sponsored product has more value than a right-rail banner or page 2 placement. Weighted SOV accounts for this.

### Tasks

#### 1. Map All Ad Types and Positions

- Review existing scrape data to catalog every ad type across all four retailers.
- Document position numbering (e.g., Amazon position 1-20 in grid, top banner, right rail).
- Create taxonomy:
  - **Amazon:** Sponsored Brand (top), Sponsored Product (positions 1-20), Sponsored Display (right rail), Video ads
  - **Walmart:** Similar structure but different slot names
  - **Kroger:** Hybrid model with unique placement types
  - **Instacart:** Different layout entirely

#### 2. Assign Baseline Multipliers Using Industry CTR Benchmarks

- Start with published e-commerce CTR-by-position data.
- Initial multiplier framework (provisional, will be refined):
  - Position 1 (top of search): 1.0x baseline
  - Positions 2-4: 0.7x
  - Positions 5-8: 0.4x
  - Right rail/skyscraper: 0.3x
  - Below fold: 0.15x
  - Banner ads: 0.2-0.6x depending on size/position

**IMPORTANT:** These are starting points. They will be validated and adjusted in subsequent phases.

#### 3. Apply Retailer-Specific Adjustments

- Amazon's right rail is less valuable than Walmart's (further right, more cluttered).
- Instacart's grid is tighter, so position decay might be steeper.
- Document these differences in a retailer comparison table.

#### 4. Validate Against Client Conversion Data (if available)

- If you have position → click → conversion data from any existing clients, check if multipliers directionally match actual performance.
- Adjust outliers (e.g., if position 3 consistently outperforms position 2, swap multipliers).

#### 5. Build Keyword Taxonomy

Create classification system for keywords:

- **keyword_type:** "category" or "branded"
- **subcategory_tags:** ["pints", "keto", "premium"] (multiple allowed)
- **monthly_search_volume:** estimated searches per month
- **category_volume_share:** what % of total category this keyword represents

Tag each keyword in your tracking list with all relevant attributes.

#### 6. Implement Multiplier Versioning (Slowly Changing Dimension)

- Add `effective_date_start` and `effective_date_end` columns to multiplier table.
- When recalibrating multipliers, end-date old records and insert new rows.
- SOV calculations join to multipliers based on `scrape_date BETWEEN effective_date_start AND effective_date_end`.
- This preserves reproducibility while allowing restatement with updated multipliers.

#### 7. Establish Recalibration Trigger

**Explicit Rule:** When you've accumulated conversion-by-position data from at least 3 managed clients covering at least 50 keywords with 8+ weeks of history, re-derive multipliers from that proprietary data rather than continuing to rely on published CTR benchmarks.

Document current multiplier source (published benchmarks) and set calendar reminder to check data accumulation threshold quarterly.

### Deliverable

- **Multiplier Table:** Database table mapping (retailer × ad_type × position × effective_date_start × effective_date_end) to multiplier value.
- **Keyword Taxonomy Table:** Database table with all keywords tagged by type, subcategory, and volume metrics.
- **Retailer Comparison Documentation:** Markdown file explaining retailer-specific adjustments and reasoning.

### Approval Gate #1

**GO/NO-GO Decision:**

- Do the multipliers pass the smell test when applied to November-January scrape data?
- Pick 3-5 known brands. Calculate their weighted SOV using the multiplier table. Does it align with what you intuitively know about their market position?
- If weighted SOV for a dominant brand (e.g., Häagen-Dazs) comes out lower than a niche player, multipliers need adjustment.

**PASS:** Weighted SOV rankings directionally match known market hierarchy. Proceed to Phase 2.

**FAIL:** Recalibrate multipliers. Common issues: over-weighting banners, under-weighting top positions, retailer-specific quirks not captured.

### Checkpoint: Tactical Reassessment

If initial multipliers are wildly off, consider whether you need more granular data (e.g., separate multipliers for mobile vs desktop, or time-of-day adjustments). Document any major assumptions that might need revisiting later.

---

## PHASE 2: Semantic Data Model & SOV Calculation Engine

### Objective

Build the core data model (fact and dimension tables) that powers all downstream analysis. Implement the weighted SOV calculation engine with composable filtering and caching.

### Why This Matters

This is the foundation. The data model must support questions you haven't thought of yet, not just serve pre-built dashboards. Get this right and everything else becomes querying; get it wrong and you're constantly writing custom code.

### Tasks

#### 1. Design Semantic Data Model

**Fact Table: `fact_sov`**

Grain: keyword × brand × retailer × date × scrape_time

Columns:
- `keyword_id` (FK to dim_keywords)
- `brand_id` (FK to dim_brands)
- `retailer_id` (FK to dim_retailers)
- `date` (FK to dim_dates)
- `scrape_time` (morning/midday/evening)
- `weighted_sov` (decimal, primary metric)
- `raw_sov` (decimal, unweighted count-based)
- `ad_count` (integer, total ads for this brand)
- `weighted_impression_value` (decimal, sum of multipliers for brand's ads)
- `total_weighted_impressions` (decimal, sum of multipliers for all ads in scrape)

**Dimension Tables:**

**`dim_keywords`**
- `keyword_id` (PK)
- `keyword_text`
- `keyword_type` (category/branded)
- `subcategory_tags` (JSONB or bridge table to dim_subcategories)
- `monthly_search_volume`
- `category_volume_share`

**`dim_brands`**
- `brand_id` (PK)
- `brand_name`
- `parent_company`

**`dim_retailers`**
- `retailer_id` (PK)
- `retailer_name`

**`dim_dates`**
- Standard date dimension (date, year, month, quarter, day_of_week, is_weekend, etc.)

**`dim_ad_metadata`** (optional, for drill-down analysis)
- Links to raw ad data: ad_type, position, image_url, etc.
- Allows filtering by placement characteristics

#### 2. Implement ETL Pipeline

Daily ETL process:
1. Read new scrape runs from `/mnt/user-data/uploads/<retailer>/<client>/runs/<timestamp>.json`
2. For each ad in each scrape:
   - Look up multiplier (join on retailer, ad_type, position, effective_date)
   - Aggregate by keyword × brand × retailer × date × scrape_time
   - Calculate weighted_sov, raw_sov, ad_count
3. Write to `fact_sov` table
4. Log to `etl_run_log` for monitoring

#### 3. Build Composable Filter API

Replace hard-coded endpoint parameters with flexible filtering:

**API Endpoint:**
```
GET /api/sov?filters={JSON}&aggregation={string}&date_start={ISO}&date_end={ISO}
```

**Example Queries:**
```json
// Basic: Amazon ice cream bars
GET /api/sov?filters={"retailer":"amazon","subcategory":"bars"}&date_start=2025-01-01

// Advanced: Top-of-page sponsored products only
GET /api/sov?filters={"retailer":"amazon","ad_type":"sponsored_product","position_bucket":"1-4"}

// Brand defense check
GET /api/sov?filters={"keyword_type":"branded","brand":"Blue Bunny"}
```

**Implementation:** Use a query builder library (e.g., SQLAlchemy in Python) that dynamically constructs WHERE clauses from the filters JSON. Validate filter keys against allowed schema fields to prevent SQL injection.

#### 4. Add Caching/Memoization Layer

- Cache query results keyed by (filters + date_range + aggregation).
- Set TTL = 24 hours or invalidate when new scrape data lands.
- Use Redis or in-memory LRU cache for fast access.
- This preserves flexibility (still computing on-demand) while preventing performance degradation past 200k ads.

#### 5. Implement Data Quality Monitoring

**Daily Check (runs after ETL):**

```python
def check_data_quality(retailer, date):
    # Count total ads for this retailer on this date
    current_count = query("SELECT COUNT(*) FROM fact_sov WHERE retailer = ? AND date = ?", retailer, date)
    
    # Get 30-day rolling average and std dev
    avg, stddev = query("SELECT AVG(count), STDDEV(count) FROM daily_ad_counts WHERE retailer = ? AND date >= ?", 
                        retailer, date - 30 days)
    
    # Alert if outside ±2 standard deviations
    if current_count < (avg - 2*stddev) or current_count > (avg + 2*stddev):
        alert(f"Data quality issue: {retailer} on {date} has {current_count} ads (expected {avg}±{2*stddev})")
        log_to_data_quality_log(retailer, date, current_count, avg, stddev)
```

This catches catastrophic scraper failures, DOM changes, or partial data corruption without false positives from normal variance.

#### 6. Add Search Volume Weighting for Category Rollup

Category-level SOV (rolling up multiple keywords):

```
Category_SOV = Σ(keyword_SOV × keyword_search_volume) / Σ(keyword_search_volume)
```

Implement as a database view or API aggregation option:
```sql
CREATE VIEW vw_category_sov AS
SELECT 
    brand_id,
    retailer_id,
    date,
    SUM(weighted_sov * k.monthly_search_volume) / SUM(k.monthly_search_volume) as category_sov
FROM fact_sov f
JOIN dim_keywords k ON f.keyword_id = k.keyword_id
WHERE k.keyword_type = 'category'  -- exclude branded keywords
GROUP BY brand_id, retailer_id, date;
```

### Deliverable

- **Database Schema:** Implemented fact and dimension tables with proper indexes.
- **ETL Pipeline:** Automated daily data loading with logging.
- **API Endpoint:** Working `/api/sov` with composable filters.
- **Caching Layer:** Redis or in-memory cache with invalidation logic.
- **Data Quality Monitor:** Daily check script with alerting.
- **Documentation:** Schema diagram and API usage examples.

### Approval Gate #2

**GO/NO-GO Decision:**

- Manually verify weighted SOV for 3-5 known brands across different keywords.
- Cross-reference with your existing ad activity charts (like the Blue Bunny example). Do the SOV trends match ad volume trends?
- Test edge cases: single keyword vs category rollup, short date range vs full history.
- Test composable filters: Can you query by ad_type, position_bucket, time-of-day without writing new code?
- Performance check: Does a complex query (3 months, 10 keywords, 5 brands) return in <3 seconds?

**PASS:** Weighted SOV numbers are defensible, API supports flexible filtering, performance is acceptable. Proceed to Phase 3.

**FAIL:** SOV calculation is broken. Common issues: multiplier table not loading correctly, search volume weights missing, date filtering off by one day, double-counting ads from multiple scrapes on same day, cache not invalidating properly.

### Checkpoint: Tactical Reassessment

If SOV numbers seem right but API performance is slow (>3 seconds for queries), add database indexes on foreign keys and filter columns. If performance is still poor, consider pre-aggregating to weekly grain for long-term trend queries.

---

## PHASE 3: Competitive Landscape Metrics

### Objective

Categorize keywords by competitive intensity and track trend deltas. Store competitive metrics as queryable dimensions in the data model.

### Why This Matters

The cost to gain 1% SOV varies wildly depending on how many competitors are fighting for the same keyword. A keyword with 10 active bidders costs more per point than a keyword with 3. Directional changes in competitive intensity drive reallocation decisions.

### Tasks

#### 1. Calculate Competitive Breadth

For each keyword, per day:
- Count unique brands appearing in paid placements.
- Average over the past 30 days to smooth out daily variance.
- Result: "ice cream bars" has avg 8.2 unique brands/day.

#### 2. Calculate Competitive Concentration (Herfindahl-Hirschman Index)

HHI measures market concentration:
- Formula: HHI = Σ(brand_SOV²)
- Higher HHI = one or two brands dominate (concentrated market)
- Lower HHI = many brands splitting share evenly (fragmented market)
- Calculate per keyword, averaged over 30 days.

#### 3. Identify Budget-Capped Competitors

Flag any brand that:
- Appears in morning scrape but not evening scrape (or vice versa)
- Consistently over 7+ days

This indicates they're capping daily budget and running out of funds partway through the day.

Count per keyword: how many budget-capped competitors exist?

#### 4. Assign Competition Tier

Rules-based segmentation (initial thresholds, adjust after testing):
- **High competition:** >8 unique brands AND HHI < 0.25
- **Low competition:** <4 unique brands OR HHI > 0.5
- **Medium competition:** everything else

Document distribution: How many keywords fall into each tier?

#### 5. Calculate Trend Deltas

For each keyword, compare current period (last 30 days) to prior period (previous 30 days):
- `tier_delta`: Did competition tier change? (e.g., "medium → high")
- `hhi_delta`: Change in concentration
- `brand_count_delta`: Net change in unique brands

Flag keywords where competitive intensity shifted meaningfully (tier change or brand_count_delta > 2).

#### 6. Store as Database Dimension

Create `dim_competition` table:

```sql
CREATE TABLE dim_competition (
    keyword_id INT,
    date DATE,
    competition_tier VARCHAR(10),  -- low/medium/high
    avg_unique_brands DECIMAL,
    avg_hhi DECIMAL,
    budget_capped_count INT,
    tier_delta VARCHAR(20),  -- e.g., "medium → high", "stable"
    hhi_delta DECIMAL,
    brand_count_delta INT,
    PRIMARY KEY (keyword_id, date)
);
```

This becomes queryable alongside SOV in the BI tool. Users can filter/group by competition tier or find keywords where tier changed.

### Deliverable

- **`dim_competition` Table:** Populated daily with competitive metrics and trend deltas.
- **Competition Analysis View:** SQL view or BI dashboard showing keywords by tier with delta flags.

### Approval Gate #3

**GO/NO-GO Decision:**

- Do the competition tiers make intuitive sense?
  - Are high-volume generic keywords ("ice cream") flagged as high competition?
  - Are niche keywords ("lactose-free ice cream bars") flagged as low/medium competition?
- Review a few keywords where you personally run campaigns. Does the tier match your experience of auction difficulty?
- Check tier distribution: Are keywords reasonably spread across tiers, or is everything "medium"?

**PASS:** Competition tiers align with campaign experience. Tier deltas capture meaningful changes. Proceed to Phase 4.

**FAIL:** Thresholds are wrong. Adjust the tier definitions. Maybe high competition should be >10 brands, or HHI cutoff needs tweaking.

### Checkpoint: Tactical Reassessment

If most keywords cluster into one tier (e.g., 80% are "medium"), the segmentation isn't useful. Consider alternative metrics: average CPC from platform data, SOV volatility (how much SOV swings day-to-day), or competitor response time (how fast they adjust bids when you change yours).

---

## PHASE 4: Spend-to-SOV Correlation Model

### Objective

Build the regression model that predicts how much spend is required to gain SOV, segmented by competition tier. Roll up keyword-level curves to product group × retailer efficiency rankings. Store model outputs as queryable data.

### Why This Matters

This is the monetizable insight. Clients don't just want to know their current SOV—they want to know what it costs to improve it and where to allocate budget for maximum impact.

### Prerequisites (HARD STOP)

Before starting Phase 4, you MUST have:
- **At least 3 managed brands** with complete platform spend data
- **At least 8 weeks of data** per brand (more is better)
- **At least 15 tracked keywords** spread across competition tiers (low/medium/high)
- **At least 2 deliberate bid changes per keyword** to establish response curves

Without this, the regression will produce garbage. If you don't meet these thresholds, continue running campaigns and accumulating data. Revisit Phase 4 when prerequisites are met.

### Tasks

#### 1. Collect Platform Spend Data

Export from Skai/Pacvue for all managed campaigns:
- Daily spend per keyword
- Daily impressions per keyword
- Average CPC per keyword
- Impression share (if available)

#### 2. Match Platform Data to Scrape Data

Align by keyword + date.

Create training dataset:

```sql
CREATE TABLE model_training_data AS
SELECT 
    k.keyword_text,
    k.keyword_id,
    f.brand_id,
    f.retailer_id,
    f.date,
    f.weighted_sov,
    p.daily_spend,
    c.competition_tier,
    c.avg_unique_brands,
    c.avg_hhi
FROM fact_sov f
JOIN dim_keywords k ON f.keyword_id = k.keyword_id
JOIN platform_spend p ON f.keyword_id = p.keyword_id AND f.date = p.date AND f.brand_id = p.brand_id
JOIN dim_competition c ON f.keyword_id = c.keyword_id AND f.date = c.date
WHERE k.keyword_type = 'category'  -- exclude branded keywords
  AND p.daily_spend > 0;
```

#### 3. Run Regression Analysis Per Competition Tier

For each tier (low, medium, high):
1. Plot spend vs SOV
2. Expected curve shape: logarithmic (early SOV points are cheap, marginal points get expensive)
3. Fit logarithmic model: `SOV = a × ln(spend) + b`
4. Calculate R² to validate model fit

**Decision Tree for Failed Regression (R² < 0.5):**

If initial regression fails:
1. **Add day-of-week as control variable:** Weekend behavior may differ from weekday
2. **Add 2-day lag on spend:** SOV response to bid changes isn't instantaneous
3. **Try piecewise linear model:** Break at median spend, fit separate slopes for low/high spend ranges
4. **Add competitor count as variable:** More competitors = flatter response curve

If R² is still <0.5 after all these attempts, you need more data (longer time period or more bid variation). Document what you tried and revisit in 4 weeks.

You should see different curves per tier:
- **Low competition:** steeper slope (cheaper SOV gains)
- **High competition:** flatter slope (expensive SOV gains)

#### 4. Calculate Marginal Cost Per SOV Point

For SOV = a × ln(spend) + b:
- Derivative: dSOV/dspend = a / spend
- Marginal cost per point: cost_per_point = 1 / (dSOV/dspend) = spend / a

This varies by current spend level (early points are cheaper).

#### 5. Build Portfolio-Level Rollup

Aggregate keyword-level curves to product group × retailer:

**Logic:**
1. For each product group (defined by subcategory tags), identify all constituent keywords
2. Sum current spend across those keywords
3. Calculate weighted average of keyword-level marginal costs (weighted by spend)
4. Output table: `vw_portfolio_efficiency`

```sql
CREATE VIEW vw_portfolio_efficiency AS
SELECT 
    pg.product_group,
    f.retailer_id,
    SUM(p.daily_spend) as current_weekly_spend,
    AVG(f.weighted_sov) as current_sov,
    -- Weighted avg of marginal costs
    SUM(m.marginal_cost_per_point * p.daily_spend) / SUM(p.daily_spend) as marginal_cost_per_point,
    RANK() OVER (ORDER BY SUM(m.marginal_cost_per_point * p.daily_spend) / SUM(p.daily_spend)) as efficiency_rank
FROM fact_sov f
JOIN dim_keywords k ON f.keyword_id = k.keyword_id
JOIN platform_spend p ON f.keyword_id = p.keyword_id AND f.date = p.date
JOIN model_marginal_costs m ON f.keyword_id = m.keyword_id
CROSS JOIN LATERAL unnest(k.subcategory_tags) as pg(product_group)
GROUP BY pg.product_group, f.retailer_id;
```

This becomes the primary artifact for budget allocation: "Ice cream bars on Amazon costs $X per SOV point, pints on Walmart costs $Y per point."

#### 6. Store Model Outputs as Queryable Data

Create tables to store regression results:

**`model_parameters`**
- `competition_tier` (low/medium/high)
- `coefficient_a`
- `coefficient_b`
- `r_squared`
- `model_type` (logarithmic/piecewise/etc)
- `trained_date`
- `n_observations`

**`model_marginal_costs`**
- `keyword_id`
- `retailer_id`
- `spend_level` (e.g., $1000, $2000, $5000)
- `marginal_cost_per_point`
- `updated_date`

This allows the BI tool to visualize cost curves directly without running Python code.

#### 7. Build Recommendation Function

Function signature:
```python
def estimate_cost_for_sov_gain(keyword_id, retailer_id, current_spend, target_SOV_increase):
    # Look up keyword's competition tier
    tier = get_competition_tier(keyword_id)
    
    # Get model parameters for this tier
    a, b = get_model_params(tier)
    
    # Calculate current SOV from current spend
    current_sov = a * log(current_spend) + b
    
    # Solve for spend needed to reach (current_SOV + target_increase)
    target_sov = current_sov + target_SOV_increase
    new_spend = exp((target_sov - b) / a)
    
    # Return range with confidence intervals
    return {
        'optimistic': new_spend * 0.8,      # assumes budget-capped competitors stay capped
        'realistic': new_spend,
        'pessimistic': new_spend * 1.5      # assumes competitors respond aggressively
    }
```

Store this as a callable API endpoint:
```
POST /api/sov/estimate
{
    "keyword_id": 123,
    "retailer_id": 1,
    "current_spend": 5000,
    "target_sov_increase": 5
}

Response:
{
    "current_sov": 18.2,
    "target_sov": 23.2,
    "estimated_additional_spend": {
        "optimistic": "$3200/week",
        "realistic": "$4000/week",
        "pessimistic": "$6000/week"
    }
}
```

### Deliverable

- **Regression Model Parameters:** `model_parameters` table populated with coefficients and R² for each tier.
- **Marginal Cost Curves:** `model_marginal_costs` table showing cost per point at different spend levels.
- **Portfolio Efficiency View:** `vw_portfolio_efficiency` showing product group × retailer rankings.
- **Recommendation API:** `/api/sov/estimate` endpoint for cost projections.
- **Model Documentation:** Markdown file explaining model assumptions, limitations, and confidence intervals.

### Approval Gate #4

**GO/NO-GO Decision:**

- Do the directional recommendations align with your campaign experience?
- Test 3-5 keywords where you've actually adjusted bids:
  - Pick a keyword where you increased spend by $X last month. What SOV gain did you actually see?
  - Plug that into your model. Does it predict a similar SOV gain for $X spend increase?
- If model predictions are within ±30% of actual outcomes, that's good enough for directional guidance.
- Check R² values: Are they >0.5 for at least 2 of 3 tiers?

**PASS:** Model is directionally accurate, portfolio rollup makes sense, efficiency rankings align with intuition. Proceed to Phase 5.

**FAIL:** Model is wildly off. Common issues: insufficient data (need more bid variation over time), wrong functional form (try decision tree suggestions above), or tier segmentation is masking important variance (maybe you need 5 tiers instead of 3).

### Checkpoint: Tactical Reassessment

If R² is consistently low (<0.5) across all tiers even after trying control variables, the problem might be that other factors dominate beyond just spend—seasonality, competitor creative quality, organic ranking changes. Consider adding more control variables: day-of-week, month, competitor count as time-series variable. Or acknowledge that the model needs more data and revisit in 8 weeks.

---

## PHASE 5: Desktop → Blended SOV Adjustment

### Objective

Derive mobile correction factors so desktop-only SOV can be translated to blended (desktop + mobile) SOV. Report blended SOV as the primary metric with explicit methodology transparency.

### Why This Matters

You're only scraping desktop, but clients care about total performance. Reporting desktop-only creates constant "why is this different from my Skai dashboard?" questions. Blended SOV with documented methodology maintains credibility while being honest about what's measured vs estimated.

### Tasks

#### 1. Pull Device Split Data from Platforms

For your managed clients, export from Skai/Pacvue:
- Desktop impression share %
- Mobile impression share %
- Desktop conversion rate
- Mobile conversion rate

Aggregate across multiple clients to get average device splits per retailer.

#### 2. Derive Mobile Ad Load Multiplier

**Hypothesis:** Mobile has more ad units per page (more scrolling = more ad inventory).

**Initial assumption:** `mobile_SOV ≈ desktop_SOV × 1.2` (20% more ad load).

**Validation method:**
1. Calculate your desktop-only weighted SOV for a client
2. Compare to platform's total (blended desktop + mobile) impression share
3. Adjust multiplier until they align

**Formula:**
```
Blended_SOV = (desktop_SOV × desktop_share) + (desktop_SOV × mobile_multiplier × mobile_share)
```

Solve for mobile_multiplier using known blended_SOV from platform.

#### 3. Apply Retailer-Specific Factors

Amazon mobile is much more ad-heavy than Kroger mobile.

Build separate mobile_multiplier per retailer.

**Initial estimates (refine with data):**
- Amazon: 1.3x
- Walmart: 1.2x
- Kroger: 1.1x
- Instacart: 1.25x

#### 4. Store Correction Factors

Create `mobile_correction_factors` table:

```sql
CREATE TABLE mobile_correction_factors (
    retailer_id INT,
    mobile_multiplier DECIMAL,
    avg_desktop_share DECIMAL,
    avg_mobile_share DECIMAL,
    effective_date_start DATE,
    effective_date_end DATE,
    PRIMARY KEY (retailer_id, effective_date_start)
);
```

Use slowly-changing dimension pattern for versioning.

#### 5. Update SOV Calculation to Include Blended Mode

Add computed column to `fact_sov`:

```sql
ALTER TABLE fact_sov ADD COLUMN blended_sov DECIMAL;

UPDATE fact_sov f
SET blended_sov = (
    f.weighted_sov * m.avg_desktop_share + 
    f.weighted_sov * m.mobile_multiplier * m.avg_mobile_share
)
FROM mobile_correction_factors m
WHERE f.retailer_id = m.retailer_id
  AND f.date BETWEEN m.effective_date_start AND m.effective_date_end;
```

#### 6. Add Methodology Documentation to Reports

Every report showing blended SOV must include this note:

> **Methodology Note:** Blended SOV combines measured desktop SOV with estimated mobile SOV. Mobile SOV is calculated by applying a retailer-specific correction factor (1.1x - 1.3x) to desktop SOV, weighted by platform device impression shares. Mobile SOV is not directly measured; accuracy is estimated at ±15%. Desktop SOV is measured directly and has higher precision.

This transparency maintains credibility while addressing the comparison problem.

### Deliverable

- **Mobile Correction Table:** `mobile_correction_factors` populated with retailer-specific multipliers.
- **Blended SOV Column:** Added to `fact_sov` with daily ETL updates.
- **Methodology Documentation:** Added to report templates and API documentation.

### Approval Gate #5

**GO/NO-GO Decision:**

- Does blended SOV estimate align with client's actual platform metrics within ±15%?
- Pick 2-3 clients where you have full platform data. Compare:
  - Your desktop-only weighted SOV (from scraper)
  - Your blended SOV (desktop + mobile correction)
  - Platform's total impression share (desktop + mobile combined)
- If blended SOV is within ±15% of platform metrics, correction is working.

**PASS:** Blended SOV aligns with platform data, methodology documentation is clear. Proceed to Phase 6.

**FAIL:** Mobile multiplier is off. Adjust per-retailer multipliers until convergence.

### Checkpoint: Tactical Reassessment

If blended SOV never converges with platform data regardless of multiplier adjustments, the issue might be that desktop and mobile have fundamentally different competitive landscapes (different brands dominating each). At that point, you'd need to actually scrape mobile to get accurate data—but that's a future enhancement, not MVP blocker. Document the limitation and proceed with desktop-only as primary metric if needed.

---

## PHASE 6: BI Onboarding & Reporting Infrastructure

### Objective

Document the semantic data model, create starter views/queries for key use cases, build narrative report template, and establish the SOV efficiency matrix as the primary budget allocation tool.

### Why This Matters

This is what you sell. The data model works, now make it accessible to your team and clients. Success means anyone can build a new view in 30 minutes without custom engineering.

### Tasks

#### 1. Document the Semantic Data Model

Create comprehensive documentation:

**Schema Diagram:**
- Visual ERD showing fact_sov and all dimension tables
- Document grain of fact table
- List all foreign key relationships

**Data Dictionary:**
- Every table and column with description, data type, sample values
- Document calculated columns (weighted_sov, blended_sov, etc.)
- Explain slowly-changing dimensions (multipliers, mobile correction factors)

**Important Notes Section:**
- Cross-retailer SOV is NOT directly comparable (different competitive sets)
- Marginal cost per SOV point IS comparable (denominated in dollars)
- Blended SOV methodology and accuracy bounds (±15%)
- Branded vs category keyword distinction
- Competition tier calculation logic

**Example Queries:**
```sql
-- SOV trend for a brand on specific keyword
SELECT date, weighted_sov, blended_sov
FROM fact_sov
WHERE brand_id = 123 AND keyword_id = 456
ORDER BY date;

-- Category-level SOV (search volume weighted)
SELECT 
    b.brand_name,
    SUM(f.weighted_sov * k.monthly_search_volume) / SUM(k.monthly_search_volume) as category_sov
FROM fact_sov f
JOIN dim_brands b ON f.brand_id = b.brand_id
JOIN dim_keywords k ON f.keyword_id = k.keyword_id
WHERE k.keyword_type = 'category'
GROUP BY b.brand_name;

-- Competitive landscape for a keyword
SELECT 
    b.brand_name,
    AVG(f.weighted_sov) as avg_sov,
    COUNT(*) as days_present
FROM fact_sov f
JOIN dim_brands b ON f.brand_id = b.brand_id
WHERE f.keyword_id = 789
  AND f.date >= CURRENT_DATE - 30
GROUP BY b.brand_name
ORDER BY avg_sov DESC;
```

#### 2. Build Starter Views in BI Tool

Connect BI tool (Tableau, Looker, Power BI, Metabase, etc.) to the database.

Create these foundational views:

**SOV Trend View:**
- Line chart: brand SOV over time (daily or weekly)
- Filters: retailer, keyword/subcategory, date range, SOV type (desktop/blended)
- Overlay: competitor SOV (top 5 by market share)

**Competitive Landscape View:**
- Table: brands ranked by SOV on selected keyword/category
- Columns: Brand, Weighted SOV %, Ad Count, Budget Pacing Pattern
- Filters: retailer, keyword, date range
- Highlight: budget-capped competitors

**Spend Efficiency View:**
- Scatter plot: X-axis = weekly spend, Y-axis = weighted SOV
- Show: client's historical data points + predicted curve from regression model
- Highlight: current position
- Purpose: "Are we on the steep or flat part of the cost curve?"

**Brand Defense Dashboard:**
- Separate tab for branded keywords only
- Show: Client's SOV on own brand terms (should be 95%+)
- Flag: Conquest threats (competitors bidding on client's brand)
- Alert: If brand SOV < 95%, recommend budget increase

#### 3. Build SOV Efficiency Matrix (Primary Budget Allocation Tool)

This is the hero view for monthly budget allocation conversations.

**Format:** Heatmap table

**Rows:** Product groups (e.g., Ice Cream Pints, Ice Cream Bars, Frozen Yogurt)

**Columns:** Retailers (Amazon, Walmart, Kroger, Instacart)

**Cell Values:** Marginal cost per SOV point

**Color Coding:**
- **Green:** Low cost per point (cheap gains available)
- **Yellow:** Medium cost
- **Red:** High cost (diminishing returns)

**Data Source:** `vw_portfolio_efficiency` from Phase 4

**Additional Columns (optional):**
- Current weekly spend
- Current SOV %
- Efficiency rank (1 = best)

**Purpose:** At a glance, show where incremental budget has highest ROI.

**Implementation:**
```sql
-- Efficiency matrix query
SELECT 
    product_group,
    retailer_name,
    current_weekly_spend,
    current_sov,
    marginal_cost_per_point,
    efficiency_rank,
    CASE 
        WHEN marginal_cost_per_point < 50 THEN 'green'
        WHEN marginal_cost_per_point < 150 THEN 'yellow'
        ELSE 'red'
    END as color_code
FROM vw_portfolio_efficiency
ORDER BY efficiency_rank;
```

Configure BI tool to apply color coding based on `color_code` column.

#### 4. Create Narrative Report Template

Monthly reports need consistent structure. Build template with these sections:

**Executive Summary**
- Current period SOV vs prior period (by product group × retailer)
- Top 3 SOV gainers with attribution (e.g., "Ice Cream Bars on Amazon: +4.2% SOV due to 30% spend increase")
- Top 3 SOV losers with attribution (e.g., "Pints on Walmart: -2.1% SOV due to new competitor entry")

**Competitive Landscape**
- Biggest competitive shifts:
  - New entrants (brands that appeared in last 30 days)
  - Tier changes (keywords that moved between low/medium/high competition)
  - Conquest behavior (competitors bidding on client's branded terms)
- Budget pacing patterns:
  - Which competitors are capping daily budgets (and when)
  - Opportunity windows (times when competition is lower)

**Efficiency Analysis**
- Product group × retailer efficiency matrix (the hero chart)
- Underperforming segments: high spend, low SOV
- High-opportunity segments: low competition, cheap gains available

**Recommendations**
- Proposed budget reallocation with estimated impact
- Format: "Shift $X from [segment A] to [segment B], estimated SOV gain: +Y%, confidence: medium/high"
- Include 3 scenarios: conservative, moderate, aggressive

**Appendix (optional)**
- Detailed SOV trends by keyword
- Competitive landscape details
- Model parameters and assumptions

**Template Variables:**
- Client name
- Report period (e.g., "January 2026")
- Data cut-off date
- Analyst name

This ensures every monthly report tells the same story shape, making it easier to automate later.

#### 5. Write BI User Guide

Short guide (5-10 pages) explaining:

**How to Use the Data Model:**
- What questions can you answer with this data?
- How to navigate the schema (start with fact_sov, join to dimensions)
- Common pitfalls (don't compare raw SOV across retailers, always use competition context)

**How to Build New Views:**
- Step-by-step: connect to database, select tables, create calculated field, build visualization
- Examples: "Show me SOV for a specific brand on weekends only" or "Compare top-of-page vs below-fold performance"

**How to Export Data:**
- For presentations, ad-hoc analysis, or sharing with clients

**Who to Contact:**
- Data issues, new feature requests, questions

#### 6. Cross-Retailer Comparability Note

Add explicit section to data model documentation:

> **Critical Note on Cross-Retailer Comparability**
> 
> Raw SOV percentages are NOT directly comparable across retailers due to:
> - Different competitive sets (different brands compete on each platform)
> - Different ad inventories (Amazon has video ads, Kroger doesn't)
> - Different category sizes (ice cream might be 3x bigger on Amazon than Kroger)
> 
> **The Right Comparison:** Marginal cost per SOV point IS comparable across retailers because it's denominated in dollars. Example:
> - Amazon: Next $10k buys you +2.5% SOV → $4000 per point
> - Walmart: Next $10k buys you +4% SOV → $2500 per point
> - **Conclusion:** Walmart is more efficient; allocate budget there
> 
> **Never Build:**
> - "Total SOV across all retailers" rollup
> - Direct comparison of 18% SOV on Amazon vs 18% SOV on Walmart
> 
> **Always Compare:**
> - Marginal cost per SOV point (efficiency)
> - Absolute spend vs absolute SOV gain (dollars in, points out)

This prevents misuse of the data model.

### Deliverable

- **Data Model Documentation:** Comprehensive guide with schema diagram, data dictionary, example queries, and cross-retailer comparability note.
- **Starter Views:** 5-7 foundational dashboards/reports in BI tool covering SOV trends, competitive landscape, spend efficiency, brand defense.
- **SOV Efficiency Matrix:** Product group × retailer heatmap showing marginal cost per SOV point.
- **Narrative Report Template:** Structured template for monthly reports and post-campaign wraps.
- **BI User Guide:** Short guide explaining how to use the data model and build new views.

### Approval Gate #6 (FINAL)

**GO/NO-GO Decision:**

Test with 1-2 friendly clients or internal stakeholders:

**Test A: Data Model Usability**
- Can an analyst create a new view (e.g., "SOV for lactose-free products on weekends only") in under 30 minutes without custom engineering?
- Does the schema make sense? Are joins intuitive?

**Test B: Narrative Report Quality**
- Using the template, generate a monthly report for 2 test clients
- Does the report produce a coherent narrative?
- Do the recommendations make sense given the efficiency matrix?

**Test C: Client Comprehension**
- Show a non-technical client the efficiency matrix and one sample report
- Ask: "What insights did you gain? What's confusing?"
- Key success metrics:
  - They can identify which product group × retailer combinations are most/least efficient
  - They understand the recommended reallocation and why
  - They find at least one actionable insight

**PASS:** Data model is queryable and flexible, reports are coherent, clients understand the insights. Ready for broader rollout.

**FAIL:** Common fixes:
- Too much jargon (replace "weighted SOV" with "market share", add tooltips)
- Charts too complex (simplify, focus on key metrics)
- Recommendations unclear (add more context, show estimated impact in dollars/SOV points)
- Schema too complicated (create simplified views for common queries)

### Checkpoint: Tactical Reassessment

If clients struggle to understand efficiency matrix or narrative reports, the issue is likely presentation not data. Invest in better visualization, clearer labeling, and simplified language. If analysts struggle to build new views, the data model may be over-normalized—consider creating denormalized views for common use cases.

---

## Summary of Approval Gates

| Phase | Pass Criteria | Common Failure Modes |
|-------|---------------|---------------------|
| **Phase 1** | Multipliers produce SOV rankings that match known market hierarchy | Over-weighting banners, under-weighting top positions, missing retailer-specific quirks |
| **Phase 2** | Weighted SOV calculations correct, API supports flexible filtering, performance acceptable | Multiplier table not loading, search volume weights missing, date filtering errors, double-counting ads, cache not invalidating |
| **Phase 3** | Competition tiers align with campaign experience, tier deltas capture meaningful changes | Thresholds too strict/loose, most keywords in one tier, segmentation not useful |
| **Phase 4** | Model predictions within ±30% of actual outcomes, R² > 0.5 for at least 2 tiers, portfolio rollup makes sense | Insufficient data, wrong functional form, low R², tier segmentation masking variance |
| **Phase 5** | Blended SOV within ±15% of platform metrics, methodology documentation clear | Mobile multiplier incorrect, fundamentally different competitive landscapes desktop vs mobile |
| **Phase 6** | Data model supports key use cases, new view buildable in <30 minutes, narrative reports coherent | Too much jargon, charts too complex, unclear recommendations, schema too complicated |

---

## Critical Success Factors

- **Data Quality:** The model is only as good as the input data. Ensure scraping is consistent (no missed runs), platform exports are complete (no missing days of spend data), and keyword tagging is accurate. Data quality monitoring (Phase 2) catches catastrophic failures.

- **Iterative Refinement:** Initial multipliers and regression parameters are educated guesses. Plan to revisit Phase 1 (when proprietary conversion data accumulates) and Phase 4 (quarterly as more spend variation is observed).

- **Honest Communication:** When presenting to clients, be transparent about confidence intervals and model limitations. Blended SOV has ±15% accuracy. Spend-to-SOV predictions are directional, not guarantees. This is a decision support tool, not a crystal ball.

- **Focus on Actionability:** Every metric should answer "What should I do differently?" The efficiency matrix is actionable (reallocate budget here). SOV trends are actionable (we're losing share, increase bids). If a chart doesn't drive action, cut it.

- **BI-First Mindset:** The data model is the product. Dashboards are just one way to query it. Design for flexibility—questions you haven't thought of yet—not just today's reporting needs.

---

## What Could Go Wrong (Risk Mitigation)

- **Insufficient Bid Variation:** If you're only running stable campaigns, you won't have the spend fluctuations needed to build a regression model. **Solution:** Deliberately test bid changes on 3-5 keywords per week to generate training data.

- **Competitive Response Lag:** If competitors respond to your bid changes within hours, the correlation gets muddy. **Solution:** Track competitor response time as a separate metric; adjust model to account for lag effects (2-day lag in Phase 4 debugging).

- **Seasonal Volatility:** November-December data might not predict February behavior. **Solution:** Flag seasonal keywords, build separate models for high-season vs low-season if needed. Document seasonality in data model.

- **Platform Changes:** Retailers change their ad layouts (Amazon does this constantly). **Solution:** Version your scraper data and multipliers. When you detect a major layout change, flag it and potentially rebuild multipliers for post-change period (slowly-changing dimension pattern).

- **Data Quality Failures:** Scraper breaks, DOM changes, partial data corruption. **Solution:** Daily monitoring (Phase 2) with alerting. Keep 7-day rolling backup of scrape data for recovery.

- **Model Overfitting:** Regression fits historical data perfectly but fails to predict future. **Solution:** Use train/test split (80/20), validate on holdout data. If predictions degrade over time, retrain quarterly.

---

## Next Steps After MVP

Once Phase 6 is complete and validated, consider these enhancements:

- **Mobile Scraping:** Add actual mobile data collection to eliminate the correction factor guesswork and improve blended SOV accuracy.

- **Creative Intelligence Layer:** You're already storing ad screenshots. Build a module that tracks creative rotation patterns, identifies winning creative themes, measures creative wear-out.

- **Automated Alerting:** Email clients when: (a) competitor launches aggressive bid war, (b) their SOV drops >10% week-over-week, (c) new competitor enters their category, (d) high-opportunity keyword (low competition + high volume) is identified.

- **Predictive Bidding:** Use the model to automatically suggest bid adjustments: "Increase bids on keyword X by 15% to reach your target SOV." Eventually, auto-execute approved bid changes via Skai/Pacvue API.

- **Retailer Expansion:** Add Target, Albertsons, other regional grocers. Apply same framework.

- **Attribution Modeling:** Link SOV changes to downstream sales impact. Requires integration with client's sales data (Circana, retailer POS reports).

- **Competitive Response Modeling:** Predict how competitors will react to your bid changes. Uses historical response patterns to forecast counter-bidding behavior.

---

## Conclusion

This implementation plan provides a structured path from raw scraping data to a BI-powered budget optimization tool. The system is defensible because:

- It's grounded in actual spend data (you control the bids, not inferring competitor behavior)
- It accounts for placement quality (weighted SOV, not just ad counts)
- It segments by competitive dynamics (cost curves differ by keyword intensity)
- It provides ranges, not false precision (acknowledges uncertainty in competitive response)
- It's built on a flexible data model that supports questions you haven't thought of yet
- It produces a concrete decision artifact (efficiency matrix) for budget allocation

The approval gates ensure you catch problems early rather than building on faulty assumptions. Each phase produces something testable. If a phase fails its approval gate, the checkpoint forces you to fix it before compounding the error.

**The Phased Approach:**
- **Phase 1:** Foundation (multipliers + keyword taxonomy)
- **Phase 2:** Infrastructure (data model + API + caching + monitoring)
- **Phase 3:** Context (competitive metrics + trend analysis)
- **Phase 4:** Intelligence (spend-to-SOV model + portfolio efficiency)
- **Phase 5:** Completeness (mobile correction + blended SOV)
- **Phase 6:** Usability (BI onboarding + reports + efficiency matrix)

This plan is ambitious but executable. The key is discipline: don't skip phases, don't ignore failing approval gates, and don't over-promise precision that the model can't deliver. Build it methodically, validate rigorously, and you'll have a tool that genuinely helps CPG brands make better media spend decisions.

**Final Note on Data Model Philosophy:**

The data model is designed to be composable, not comprehensive. You can't predict every question a client will ask, so don't try. Instead, build clean fact/dimension tables at the right grain, document them well, and make the BI tool the query interface. When someone asks a new question, they compose it from existing tables rather than waiting for you to build a new dashboard. This is the difference between a tool and a data foundation.

---

## Appendix: Technical Stack Recommendations

**Database:** PostgreSQL (supports JSONB for subcategory tags, good BI tool integration, handles 1M+ row fact tables easily)

**ETL/Orchestration:** Airflow or Prefect (Python-based, handles daily scrape → database pipeline)

**Caching:** Redis (fast, supports TTL, easy Python integration)

**BI Tool:** 
- **Budget option:** Metabase (open source, good for MVP)
- **Mid-tier:** Looker or Mode (better for team collaboration)
- **Enterprise:** Tableau or Power BI (if client already uses it)

**API Framework:** Flask or FastAPI (Python, simple, well-documented)

**Regression/Modeling:** scikit-learn (Python, standard for log regression), statsmodels (better for R² and diagnostics)

**Version Control:** Git + GitHub (for code, data model schema, documentation)

**Monitoring/Alerting:** PagerDuty or Slack webhooks (for data quality alerts)

---

## Appendix: Glossary

**SOV (Share of Voice):** Percentage of total ad impressions captured by a brand on a specific keyword/category.

**Weighted SOV:** SOV calculation that accounts for placement quality (top-of-page ads worth more than bottom).

**Blended SOV:** Combined desktop + mobile SOV (mobile is estimated via correction factor).

**Competition Tier:** Classification of keywords by competitive intensity (low/medium/high based on brand count and HHI).

**HHI (Herfindahl-Hirschman Index):** Measure of market concentration. Higher = more concentrated (one brand dominates). Lower = more fragmented (many brands splitting share).

**Marginal Cost per SOV Point:** How much spend is required to gain 1% SOV at current spend level. Derived from regression model.

**Efficiency Matrix:** Product group × retailer heatmap showing marginal cost per SOV point. Primary tool for budget allocation.

**Budget-Capped Competitor:** Brand that appears in morning scrape but not evening (or vice versa), indicating they've exhausted daily budget.

**Semantic Data Model:** Database schema designed for flexible querying (fact/dimension tables) rather than specific use cases.

**Slowly Changing Dimension:** Dimension table that tracks historical changes (e.g., multipliers over time) by end-dating old records and inserting new ones.

---

**Document Version:** 2.0 (Revised - BI-First Architecture)  
**Last Updated:** February 2026  
**Authors:** Implementation team  
**Status:** Final - Ready for execution
