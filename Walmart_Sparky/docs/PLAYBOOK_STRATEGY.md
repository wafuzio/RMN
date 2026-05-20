# Sparky Playbook — Expanded Investigation Strategy

**Goal:** Build a consulting-grade playbook that any retail brand can use to diagnose and optimize their visibility in Walmart's Sparky AI assistant.

**Unifying question:** *How does a brand optimize for visibility in Walmart's Sparky AI shopping assistant?*

**How Garanimals fits:** It is Case Study 1. Every finding there is a hypothesis to validate across other verticals. The playbook is proven when the framework holds (or interestingly breaks) across multiple categories.

---

## The Master Framework

Everything in this investigation answers one of four questions:

```
┌─────────────────────────────────────────────────────────────┐
│  1. ROUTING    Can Sparky even reach your products?         │
│                (1P path vs 3P path determination)           │
├─────────────────────────────────────────────────────────────┤
│  2. RANKING    When you're on the right path, where do      │
│                you appear? (position, share of carousel)    │
├─────────────────────────────────────────────────────────────┤
│  3. EDITORIAL  What does Sparky say about your brand when   │
│                no products are shown? (perception, sources) │
├─────────────────────────────────────────────────────────────┤
│  4. ADS        What's the coming paid placement landscape   │
│                and how should brands prepare?               │
└─────────────────────────────────────────────────────────────┘
```

Every capture you do answers one or more of these. The playbook is organized around them.

---

## The Standard Probe Battery

**Run this 5-query sequence in every new vertical or brand test.**  
Same structure every time = data that correlates across all categories.

Substitute `[CATEGORY]` and `[BRAND]` for each new context.

| Probe | Query Template | What It Measures |
|-------|---------------|-----------------|
| P1 | `[CATEGORY] walmart` | Baseline routing — no modifiers |
| P2 | `affordable [CATEGORY] walmart` | Value modifier → 1P route test |
| P3 | `best selling [CATEGORY]` | "Best selling" trigger → 3P route test |
| P4 | `[BRAND] [CATEGORY]` | Branded query — forces brand into context |
| P5 | `are [BRAND] [CATEGORY] good quality` | Editorial grounding — what Sparky says about brand |

**These 5 probes give you:**
- P1: Unbiased baseline (what does Sparky do with no nudge?)
- P2 vs P1: Does value modifier shift routing toward 1P?
- P3 vs P1: Does "best selling" shift routing toward 3P?
- P4: Does brand name appear when explicitly referenced?
- P5: What narrative does Sparky construct around the brand?

**Record the same metrics every time:**
- `1P%` (seller_breakdown.1P / 5)
- `brand_share%` (target brand count / 5)
- `brand_position` (lowest position = best)
- `reformulated_query` (what Sparky actually searched)
- `editorial_sources` (domains in P5)

---

## The Four Research Tracks

Each track answers a different strategic question. Run them in parallel — you don't need to finish one before starting another.

---

### Track A — Vertical Routing Tests
**Strategic question:** Is the 1P/3P binary routing system a platform-level behavior or specific to kids clothing?

**Hypothesis:** The same routing triggers (value → 1P, seasonal/gift → 3P) apply in every category. If true, this is a universal platform insight.

**Verticals to test (priority order):**

| Priority | Vertical | Walmart Private Label | Probe Examples |
|----------|----------|----------------------|----------------|
| 1 | Kids Clothing | Garanimals | ✅ Already done — Case Study 1 |
| 2 | Grocery | Great Value | `pasta walmart`, `affordable pasta walmart`, `best selling pasta` |
| 3 | Home Goods | Mainstays | `throw pillows walmart`, `affordable throw pillows`, `best selling throw pillows` |
| 4 | Baby | Parent's Choice | `baby formula walmart`, `affordable baby formula`, `best selling baby formula` |
| 5 | Health/OTC | Equate | `allergy medicine walmart`, `affordable allergy medicine`, `best selling allergy medicine` |
| 6 | Electronics | onn. | `bluetooth speaker walmart`, `affordable bluetooth speaker`, `best selling bluetooth speaker` |
| 7 | Pet | Special Kitty / Pure Balance | `cat food walmart`, `affordable cat food`, `best selling cat food` |
| 8 | Toys | Play Day | `toddler toys walmart`, `affordable toddler toys`, `best selling toddler toys` |

**Why these verticals:**
- Each has a clear Walmart private label (1P brand) to track
- Each has obvious seasonal/gift dimensions to test (holiday toys, back-to-school, etc.)
- Grocery/home are high-frequency query categories — lots of natural search data

**What confirms the hypothesis:** If `best selling [x]` routes to 3P and `affordable [x]` routes to 1P in 5+ categories, the routing logic is platform-level, not category-specific.

**What breaks the hypothesis (also valuable):** If grocery or electronics routes differently, that tells you routing is category-aware — Sparky may have different logic for commodity vs. considered purchases.

---

### Track B — Brand Type Comparison
**Strategic question:** Does Sparky systematically favor Walmart's own private labels on the 1P path, or does any 1P seller benefit equally?

**What to test:** Run the same P1 (baseline) and P2 (value) probes for three brand types in the same category:

```
Example: Kids Clothing baseline query "toddler shirts walmart"

Test 1: Track Garanimals (Walmart private label 1P)
Test 2: Track Carter's (national brand, sold 1P at Walmart)  
Test 3: Track a 3P marketplace brand
```

| Brand Type | What You Expect | What Confirms It |
|-----------|----------------|-----------------|
| Walmart private label (Garanimals, Great Value) | Highest share on 1P path | Appears in 2-4/5 positions |
| National brand 1P (Carter's, Fisher-Price) | Present on 1P path, lower share | Appears in 1-2/5 positions |
| Marketplace-only (Chinese sellers) | Zero on 1P path, dominant on 3P | Appears only on 3P queries |

**Key test: Run both `Carter's toddler shirts` and `Garanimals toddler shirts` branded queries.**
- If Garanimals outranks Carter's on unbranded value queries → Walmart is preferencing its own label
- If they appear equally → 1P routing is about seller type, not brand ownership

**This is the highest-value finding for the playbook.** It tells brands whether 1P listing (being on Walmart.com) is enough, or whether Walmart private labels get structural preference.

---

### Track C — Query Intent Matrix
**Strategic question:** Does Sparky use the same intent taxonomy across all categories, or does intent classification vary by vertical?

**Run this for 3+ verticals:** Map how each intent type routes in that category.

| Intent Type | Query Pattern | Expected Route | Test In |
|------------|--------------|---------------|---------|
| Generic shopping | `[category] walmart` | 1P | All verticals |
| Value shopping | `affordable [category]` | 1P | All verticals |
| Best-selling | `best selling [category]` | 3P | All verticals |
| Seasonal | `[season] [category]` | 3P | All verticals |
| Gift | `[category] gift for [person]` | 3P | All verticals |
| Branded | `[brand] [category]` | 1P (brand forced) | All verticals |
| Quality/perception | `are [brand] good quality` | Editorial | All verticals |
| Comparative | `[brand] vs [brand]` | Deflection + products | All verticals |

**The deliverable from this track:** An intent classification guide that works for any brand in any category:

```
"If your customer searches [intent type], Sparky will route to [path]. 
Your brand will [appear/not appear]. To optimize: [action]."
```

---

### Track D — Editorial Source Audit
**Strategic question:** Which external content sources feed Sparky's brand perception across categories, and can those sources be influenced?

**What to capture for each brand/category P5 probe:**
1. Every domain in `source_domains` array
2. The exact narrative Sparky produces (copy `editorial_metrics.full_response`)
3. Specific language used (positive/neutral/negative framing)
4. Whether a competitor is mentioned comparatively

**Build a source map across all verticals:**

| Category | Brand | Sources Observed | Narrative Theme |
|----------|-------|-----------------|-----------------|
| Kids clothing | Garanimals | reddit, thespruce, babycenter | "affordable but less durable than Cat & Jack" |
| Grocery | Great Value | ? | TBD |
| Home | Mainstays | ? | TBD |
| ... | ... | ... | ... |

**Why this matters for the playbook:** If you find that reddit.com and thespruce.com appear consistently across multiple categories as Sparky's editorial sources, those are **universal content targets**. A brand that improves its perception on those sites improves its Sparky editorial treatment across all query types. That's a concrete, actionable recommendation.

---

## How the Tracks Correlate as a Body of Work

The unifying structure is a **2×2 diagnostics framework** every brand can apply to themselves:

```
                    ROUTING
                 1P Path    3P Path
            ┌──────────────────────────┐
     HIGH   │  ⭐ WINNING    │  Gap A:  │
RANKING     │  Visible &    │  Wrong   │
WITHIN      │  well-ranked  │  path    │
PATH        ├──────────────────────────┤
     LOW    │  Gap B:       │  ❌ LOST  │
            │  Right path,  │  Routing │
            │  wrong rank   │  & rank  │
            └──────────────────────────┘
```

- **Winning:** On 1P path, ranking well → brand is Sparky-optimized
- **Gap A (Routing):** On 3P path despite being a 1P brand → fix the query footprint
- **Gap B (Ranking):** On 1P path but buried → fix content/catalog optimization
- **Lost:** 3P path and not ranking → requires fundamental rethink

Every brand that picks up this playbook starts by running the 5-probe battery and placing themselves in this matrix. That's the diagnostic tool.

---

## The Playbook Structure (Final Deliverable)

The output of this research is a structured guide organized as follows:

### Section 1 — Sparky Architecture (platform overview)
- What Sparky is and isn't (Google Vertex AI + Walmart catalog, not a pure LLM)
- The binary routing system explained
- Response mode taxonomy
- Conversation context stickiness
- Ad infrastructure status

### Section 2 — The Routing Playbook
- Universal modifier taxonomy (safe vs. dangerous words — validated across verticals)
- Routing trigger hierarchy (seasonal > gift > value — confirmed or updated)
- Category-specific routing differences (if any found in Track A)
- "First query is everything" principle

### Section 3 — The Ranking Playbook
- What determines position within the 1P path
- Role of seller type, badges, price positioning
- Product title/description optimization for reformulated queries
- 1P vs. private label preference (from Track B findings)

### Section 4 — The Editorial Playbook
- Which external content sources feed Sparky perception
- Sentiment patterns by category (Track D audit)
- Content strategy: which sites to target for SEO that feeds Sparky
- Durability/quality narrative patterns across categories

### Section 5 — The Ads Playbook
- Current ad infrastructure status (max_ads, showAds fields)
- Predicted ad format based on schema (`adSlots`, `adsBeacon` structure)
- Query types that will likely be monetized first (high-volume 1P path queries)
- First-mover recommendations

### Section 6 — Brand Diagnostic Toolkit
- The 5-probe battery (how any brand runs their own diagnosis)
- The routing/ranking 2×2 matrix
- Metric definitions + benchmarks from case studies
- Red flags to monitor (showAds going live, routing shifts)

### Case Studies (appendix)
- **Case Study 1:** Garanimals / Kids Clothing (complete)
- **Case Study 2–N:** Additional verticals (in progress)

---

## Session Planning for Maximum Breadth + Correlation

### The rule: anchor + expand
Every capture session should include:
- **1 anchor query** — a query type you've already run (confirms stability, builds longitudinal data)
- **3–4 expansion queries** — new vertical or new modifier tests

This keeps every session grounded while pushing breadth.

### Recommended session sequence

**Session A (before Tuesday — 5 captures)**
Focus: Close the most critical open questions in Garanimals, get one new vertical started
1. `toddler rompers` — closes Garanimals romper gap
2. `cute toddler clothes` — tests "cute" as 3P trigger
3. `affordable back to school toddler clothes` — value vs seasonal
4. `pasta walmart` — Track A, first grocery baseline (P1)
5. `affordable pasta walmart` — Track A, grocery P2

**Session B (post-Tuesday — 6 captures)**
Focus: Complete grocery Track A, start home goods
1. `best selling pasta` — grocery P3
2. `Great Value pasta` — grocery P4
3. `is Great Value pasta good quality` — grocery P5 (editorial)
4. `throw pillows walmart` — home goods P1
5. `affordable throw pillows` — home goods P2
6. `best selling throw pillows` — home goods P3

**Session C (one week out)**
Focus: Complete home goods, start Track B brand comparison
1. Home goods P4–P5 (Mainstays branded + editorial)
2. `Carter's toddler shirts walmart` — Track B national brand baseline
3. `Carter's vs Garanimals toddler shirts` — Track B comparative
4. Baby vertical P1–P2

**Sessions D–H**
Continue expanding verticals + completing Track B and C matrices.

### How to prioritize within sessions

```
Priority 1: Any P1 + P2 + P3 in a new vertical (3 captures → confirms routing in that vertical)
Priority 2: P5 (editorial) for any brand already probed in Tracks A/B
Priority 3: Track C intent matrix queries (gift, seasonal, branded variants)
Priority 4: Track D editorial source confirmations (repeat P5 in same vertical)
```

---

## What Makes This "Correlate as a Body of Work"

The through-line is consistent measurement, not consistent subject matter. Each capture contributes to one or more of these cross-cutting datasets:

| Dataset | What It Tracks | How It's Built |
|---------|---------------|----------------|
| Routing Map | Which modifier types route to 1P vs 3P by category | P1/P2/P3 across all verticals |
| Brand Visibility Index | 1P share % for private label vs national vs 3P by category | P1/P4 across verticals |
| Editorial Source Registry | All domains feeding Sparky editorial by category | P5 across all verticals |
| Intent Classification Guide | How each query intent type routes in each vertical | Track C matrix |
| Ad Infrastructure Log | max_ads, showAds values over time | Every capture, every session |

When you have 50+ captures across 5–6 verticals, these datasets tell a story that no single-category investigation can: **Sparky is systematically structured in a way that rewards specific behaviors and penalizes others — and that structure is consistent enough to be optimized.**

---

## Scope Management: What NOT to Test

To keep the body of work coherent, avoid these without a specific reason:

- **Hyper-niche queries** (specific SKUs, style numbers) — too specific to generalize
- **Voice/conversational queries** — different input path, not comparable
- **Location-specific queries** ("near me", "in stock at my store") — introduces geo variables
- **Logged-out captures** — mixing login states pollutes the dataset (stay logged in consistently)
- **Consecutive queries in the same conversation** unless intentionally testing context — keep probes in fresh conversations for clean results

---

## Total Research Scope

| Track | Captures | Status |
|-------|----------|--------|
| Garanimals deep dive (current) | 16 done | Case Study 1 complete |
| Track A: 7 new verticals × 5 probes | 35 | Not started |
| Track B: Brand comparison (3 verticals × 3 brands × 2 probes) | 18 | Not started |
| Track C: Intent matrix (5 intent types × 4 verticals) | 20 | Partial (from Garanimals) |
| Track D: Editorial source audit (all verticals P5 + follow-ups) | 15 | 2 done |
| Sentinel tracking (5 queries/week, ongoing) | ∞ | Not started |
| **Total new captures needed** | **~90** | |

At 5–6 captures per session: **15–18 sessions** to complete Tracks A–D.  
The playbook becomes publishable after Tracks A and B are complete (~10 sessions).
