# Sparky AI — Presentation Deck
## Walmart's Shopping Assistant & Garanimals Visibility

**Audience:** Search / RMN / Brand Strategy  
**Date:** May 2026  
**Investigation Period:** March–May 2026  
**Captures Analyzed:** 16

---

## Slide 1 — What Is Sparky?

**Walmart's conversational AI shopping assistant**

- Launched in Walmart iOS app
- Accepts natural language queries: "What are the best toddler clothes at Walmart?"
- Returns 5 product carousel + editorial commentary
- Think: Walmart's answer to Amazon Rufus / Google Shopping Chat

**Why it matters for brands:**
- New surface for product discovery
- Different rules than traditional search ranking
- Currently no paid placement — but ad infrastructure is built and ready

---

## Slide 2 — The Core Discovery: Binary Routing

> **Sparky doesn't rank products. It routes queries.**

### Two Paths:

| | Path A: 1P Route | Path B: 3P Route |
|---|---|---|
| **Trigger** | "cheap", "affordable", "everyday", generic categories | "back to school", "gift for", seasonal terms |
| **Results** | 80–100% Walmart.com brands | 100% marketplace sellers |
| **Garanimals** | ✅ 20–60% share | ❌ 0% always |

**Key insight:** There is no "ranking up" from position 6 to 1 if you're on the wrong path. **The routing decision determines whether Walmart brands appear at all.**

---

## Slide 3 — The Routing Hierarchy

When a query contains multiple signals, Sparky follows strict priority:

```
1. Seasonal/Event terms   →  Forces 3P  (HIGHEST priority)
2. Gift/Novelty context   →  Forces 3P
3. Value/Price terms      →  Favors 1P  (lowest priority)
```

### Proof (Capture #12):

| Query | 1P Share | Garanimals |
|-------|----------|------------|
| "affordable everyday toddler clothes" | 80% | ✅ 40% |
| "affordable fall fashion for 4 year old" | 0% | ❌ 0% |

**"Fall" overrides "affordable."** One word can erase all brand visibility.

---

## Slide 4 — Garanimals Is a Routing Indicator

Garanimals visibility perfectly tracks with 1P routing:

| 1P Share in Results | Garanimals Share |
|---------------------|-----------------|
| 100% | 40–60% |
| 80% | ~40% |
| 40% | ~20% |
| 0% | 0% |

**R² = 1.0 — perfect correlation, no exceptions in 16 captures.**

When you see Garanimals in Sparky results → the query took the 1P path.  
When you see Chinese marketplace sellers → the query took the 3P path.

---

## Slide 5 — What Queries Route Where

### ✅ 1P Route (Garanimals Visible)
| Query | Garanimals | 1P% |
|-------|-----------|-----|
| "cheap toddler shirts" | 3/5 (60%) | 100% |
| "affordable everyday toddler clothes" | 2/5 (40%) | 80% |
| "affordable clothing for toddlers" | 1/5 (20%) | 80% |
| "best kids clothing brands at walmart" | 2/5 (40%) | 100% |

### ❌ 3P Route (Garanimals Invisible)
| Query | Garanimals | Why |
|-------|-----------|-----|
| "back to school clothes for preschooler" | 0/5 | Seasonal modifier |
| "cute outfit for my toddler niece" | 0/5 | Gift context |
| "best selling toddler rompers" | 0/5 | "Best selling" = marketplace trigger |
| "affordable fall fashion for 4 year old" | 0/5 | "Fall" overrides "affordable" |

### ⚠️ Borderline
| Query | Garanimals | Note |
|-------|-----------|------|
| "mix and match kids clothes" | 1/5 (20%) | 40% 1P — unstable territory |

---

## Slide 6 — The Romper Gap (Critical Finding)

> **Rompers are Garanimals' core category. Sparky shows 0 Garanimals rompers.**

**Capture #4:** "what are the best selling toddlers rompers at walmart?"

| Position | Brand | Seller | Price |
|----------|-------|--------|-------|
| 1 | WRKEKC | shenzhenshixinyinbin... (3P) | $1.22 |
| 2 | Busydd | Shenzhenyoujiamaoyi... (3P) | $3.49 |
| 3 | John Deere | imagikids (3P) | $23.99 |
| 4 | Odeerbi | Shenzhen Weibaolai... (3P) | $4.99 |
| 5 | Girls Easter Romper | guangzhouhantian... (3P) | $8.92 |

**Garanimals rompers exist. They simply don't appear because "best selling" triggers 3P routing.**

**Untested:** Does "toddler rompers" (without "best selling") route to 1P and show Garanimals?

---

## Slide 7 — Conversation Context Is Sticky

Once classified, routing is very hard to change mid-conversation. Here's the full thread from captures 9–11:

**Thread 1 (Terminated):**
1. *"cute outfit for my toddler niece"* → Gift context → 100% 3P
2. *"I don't need it about our relation, just cute clothes"* → Reformulated as `"cute toddler clothes, gift"` → **still 100% 3P**
3. *"that looks like cheap chinese crap"* → **Conversation TERMINATED** (`out_of_domain_intent`)

**Thread 2 (Positive arc — captures 14–16):**
1. *"who sells affordable clothing for toddlers"* → 1P route, Garanimals #1
2. *"would any of these make a good gift for my niece?"* → Editorial, Garanimals **recommended as gift** (context stayed 1P)
3. *"any negatives?"* → Google-grounded, Garanimals sizing noted (runs small)

**Key insight:** Starting from 1P then adding gift context = still Garanimals visible. Starting from gift context = locked into 3P. The **first query sets the path**.

---

## Slide 8 — Editorial Perception Issue

Sparky uses **Google Vertex AI grounding** for editorial responses (no product results). External web content shapes how Sparky describes brands.

**Current narrative from external sources:**
- Garanimals: *"affordable everyday"*, *"budget-friendly"*, *"good for basics"*
- Cat & Jack: *"durable"*, *"holds up better"*, *"worth the extra cost"*

**Sources observed:** reddit.com, thespruce.com, babycenter.com

**Implication:** Garanimals' SEO/content strategy needs to address durability and quality narratives on external sites — those sites feed directly into Sparky's editorial responses.

---

## Slide 9 — Ad Infrastructure (Watch This Space)

Current ad status: **Built but inactive**

| Field | Value |
|-------|-------|
| `max_ads` | 4–8 (in all captures) |
| `showAds` | `false` (every capture) |
| Actual ads served | 0 |

**What this means:**
- Walmart has built ad slots into Sparky's response structure
- They're not turned on yet for the Sparky channel
- When `showAds` flips to `true`, this becomes a paid placement surface
- First movers will have a major advantage

**Recommendation:** Monitor `showAds` flag closely. Have creative/budget ready.

---

## Slide 10 — Testing Roadmap

### Priority 1 (Before Next Presentation)
- [ ] "toddler rompers" without "best selling" — does Garanimals appear?
- [ ] All 14 product types from catalog (13 untested)
- [ ] Mix-and-match queries ("mix and match kids clothes")
- [ ] "walmart brand clothes for toddlers" — can explicit 1P request override?

### Priority 2
- [ ] Quality/durability perception queries ("are garanimals durable?")
- [ ] Size-specific queries ("2T romper", "4T shirt")
- [ ] Character queries ("paw patrol clothes for toddlers")
- [ ] Repeat capture of key queries to test stability over time

### Priority 3 (Ongoing)
- [ ] Monitor `showAds` flag weekly
- [ ] Track editorial source domains for new entries
- [ ] Sentinel query set (20 queries, run weekly for longitudinal data)

---

## Slide 11 — Key Takeaways

1. **Routing > Ranking** — Getting on the 1P path is prerequisite to any visibility
2. **Avoid seasonal/gift modifiers** — One wrong word eliminates all Garanimals results
3. **"Best selling" is a 3P trigger** — Counter-intuitive but confirmed
4. **Editorial narrative needs work** — External web content positions Garanimals as inferior quality
5. **Ad slots are ready** — When Sparky ads launch, early investment will matter
6. **13 product categories still untested** — Romper gap may not be unique

---

## Slide 12 — Methodology

**Capture method:** HTTP Catcher (iOS proxy app) intercepting Walmart app traffic  
**Analysis:** Custom Python parser extracting product data, seller IDs, routing signals  
**Endpoint:** `POST walmart.com/api-proxy/service/iot/converse-adapter/v1/talk/sparky_assistant`  
**Bot detection:** PerimeterX v3 (requires iOS app — cannot replay from desktop)  
**Captures:** 16 queries, March 16–17, 2026  
**Consistency check:** 2 identical queries run back-to-back confirmed deterministic routing

**Tools:** `scripts/parse_sparky_capture.py` — parses captured JSON into structured metrics  
**Data:** `data/captures/` — 13 parsed capture files (timestamped JSON)

---

*For full technical details: `docs/API_SCHEMA.md`*  
*For raw capture data: `docs/CAPTURE_LOG.md`*  
*For findings reference: `docs/SPARKY_FINDINGS.md`*
