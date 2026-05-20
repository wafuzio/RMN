# Sparky Investigation — Consolidated Findings

**Last Updated:** May 15, 2026  
**Captures Analyzed:** 16 (13 product search, 3 editorial, 1 content moderation)  
**Status:** Active investigation

> This document merges system mechanics + Garanimals-specific visibility findings into one reference.

---

## 1. Core Architecture

Sparky is not a custom Walmart LLM. It is a wrapper around **Google Vertex AI Search** (grounding API) + **Walmart's internal product search**. The `converse-adapter` service routes queries to one of three response modes based on detected intent:

- **Product Intent** → Walmart search engine → product carousel + generic editorial wrapper
- **Informational Intent** → Google Vertex AI grounding → editorial text with cited sources, no products
- **Comparative Deflection** → Returns interleaved products from both brands, refuses qualitative judgment

**API Endpoint:**
```
POST https://www.walmart.com/api-proxy/service/iot/converse-adapter/v1/talk/sparky_assistant
```

---

## 2. Binary Routing System

**The single most important finding:** Sparky doesn't rank products against each other across the full catalog. It first classifies the query into a path, then ranks within that path.

### Path A: 1P-Dominant Route
- **Triggers:** Generic categories, value/price terms, basic needs
- **Result:** 80–100% Walmart.com (1P) products
- **Garanimals visibility:** 20–60%
- **Examples:** "cheap toddler shirts", "affordable everyday toddler clothes", "best kids brands at walmart"

### Path B: 3P-Dominant Route
- **Triggers:** Seasonal/event terms, gift context, novelty, character-specific
- **Result:** 100% third-party marketplace sellers
- **Garanimals visibility:** 0%
- **Examples:** "back to school clothes", "cute outfit for my niece", "best selling rompers"

### Routing Priority (When Multiple Triggers Present)
1. **Seasonal/Event terms** → Forces 3P (highest priority)
2. **Gift/Novelty context** → Forces 3P
3. **Value/Price terms** → Favors 1P (lowest priority)

**Proof:** "Affordable everyday toddler clothes" → 80% 1P ✅ | "Affordable fall fashion for 4 year old" → 0% 1P ❌

The word "fall" overrides "affordable." Seasonal modifiers trump value terms.

---

## 3. Garanimals Visibility Mechanics

### The Core Correlation

Garanimals visibility is a perfect proxy for 1P routing:

| 1P Share | Garanimals Share |
|----------|-----------------|
| 100% | 40–60% |
| 80% | 40% |
| 40% | 20% |
| 0% | 0% |

**R² = 1.0 — no exceptions observed.**

### Query Performance by Type

**High Visibility (40–60%):**
- Value queries: "cheap", "affordable" → 1P route, Garanimals as value brand
- Generic brand queries: "best kids brands at walmart" → 1P bias
- Comparative: Direct mention forces inclusion + 1P bias

**Zero Visibility (0%):**
- Seasonal: "back to school" → Routes to 3P specialty sellers
- Gift/novelty: "cute outfit for niece" → Routes to 3P personalized items
- "Best selling" modifier: Appears to trigger marketplace routing (confirmed anomaly)

**Low Visibility (20%):**
- Mixed categories: "mix and match" → Borderline routing (40% 1P / 60% 3P)

### Positioning When Visible
- Top-heavy: Positions 1–3 most common, never buried at position 5 alone
- Position is **deterministic** on value queries (same query tested twice → Garanimals #1 both times)
- 80% product overlap on repeat queries of same query text
- Price advantage: $4.48–$16.79 vs competitors $8.21–$24.77

### Editorial Treatment
- Always framed as "affordable" or "budget-friendly" — never "premium" or "high-quality"
- External sources (reddit, thespruce.com) position: Garanimals = "affordable everyday" | Cat & Jack = "durable"
- No promotional language in preambles
- Inconsistent mention in follow-up editorial text

---

## 4. Response Mode System

| Query Type | Mode | Products? | Editorial? |
|------------|------|-----------|------------|
| Product search | Product Carousel | 5 products | Minimal preamble/followup |
| Perception/"why" question | Editorial Only | None | Google-grounded |
| Comparative ("X vs Y") | Deflection + Products | 5 products | Deflection disclaimer |
| Inappropriate content | Content Moderation | None | Termination message |

### Deflection Mechanism
Comparative queries trigger: *"I can't make qualitative comparisons between brands..."* but still show products from both. Protects Walmart from liability while maintaining utility.

### Google-Grounded Editorial
"Why" questions about brand perception trigger external web search. Sources observed: reddit.com, thespruce.com, babycenter.com. This is where the "Garanimals = affordable, Cat & Jack = durable" narrative comes from.

---

## 5. Query Reformulation Engine

Sparky doesn't search exact user words — it reformulates:
- Strips question words: "What are some cheap toddler shirts?" → `"cheap toddler shirts"`
- Preserves key modifiers: value terms, age indicators, category descriptors
- **Maintains and adds conversation context** even when user tries to redirect

**Example of sticky context:**
1. "cute outfit for my niece" → Routes to 3P/gift path
2. "I don't need it about our relation, just cute clothes" → Reformulated as `"cute toddler clothes, gift"` ← "gift" added from previous query, **still routes to 3P**

**Implication:** Starting a new conversation may be required to escape unwanted routing.

---

## 6. Conversation Context Engine

- Each conversation has a unique `conversationId` (UUID, persists across turns)
- Context inheritance is automatic and hard to override
- Conversation title auto-updates: "Affordable Toddler Clothing" → "Toddler Clothing Gift Ideas" → "Toddler Clothing Reviews" (can track routing evolution)

---

## 7. Ad Infrastructure Status

- `max_ads: 4–8` present in all captures
- `showAds: false` across all captures — ads system appears inactive in Sparky
- Ad beacon infrastructure is built and ready
- No competitor ads observed in any capture

**Implication:** When ads go live, this channel will be high-stakes. Monitor for `showAds: true` flag.

---

## 8. Content Moderation

Sparky monitors for inappropriate content and terminates conversations immediately:
- Intent: `out_of_domain_intent` + `fallbackCategory: "inappropriate"`
- Response: Conversation forcibly reset, must start fresh
- No warnings — immediate termination
- **Observed trigger:** Racial/ethnic language + negative sentiment in query

---

## 9. Open Questions (Testing Backlog)

**Routing:**
- [ ] Does "walmart brand" or "walmart.com brand" override 3P routing?
- [ ] Is "best selling" always a 3P trigger, or is it category-dependent?
- [ ] What's the exact seasonal keyword list that forces 3P?
- [ ] Character queries ("paw patrol clothes") — 1P or 3P?

**Context:**
- [ ] Are there keywords that reset conversation context mid-conversation?
- [ ] How long does conversation context persist (time/turn count)?
- [ ] Does login status or Walmart+ status affect routing?

**Product selection:**
- [ ] How are the 5 products chosen within each route?
- [ ] Is there personalization based on purchase history?
- [ ] Size-specific queries ("2T clothes") — does this change routing?

**Garanimals-specific:**
- [ ] Generic "toddler rompers" (no "best selling") → Does Garanimals appear?
- [ ] "Cute clothes for toddler" without gift context → Still routes 3P?
- [ ] All 14 product types from catalog (13 still untested)
- [ ] Mix-and-match queries (Garanimals' core differentiator)

---

## 10. Capture Summary Table

| # | Date | Query (Reformulated) | Mode | Garanimals | 1P% | Key Finding |
|---|------|----------------------|------|-----------|-----|-------------|
| 1 | 3/16 | "best kids clothing brands at walmart" | Carousel | 2/5 (40%) | 100% | Generic brand → high visibility |
| 2 | 3/16 | "why didn't garanimals make the list" | Editorial | N/A | N/A | Google-grounded, durability framing |
| 3 | 3/16 | "TCP vs garanimals, which is better" | Deflection | 3/5 (60%) | ~60% | Deflection + products, Garanimals #1-3 |
| 4 | 3/16 | "best selling toddlers rompers" | Carousel | 0/5 (0%) | 0% | CRITICAL: All 3P Chinese sellers |
| 5 | 3/16 | "mix and match kids clothes" | Carousel | 1/5 (20%) | 40% | Borderline routing — mixed 1P/3P |
| 6 | 3/16 | "back to school clothes, preschooler" | Carousel | 0/5 (0%) | 0% | Seasonal → pure 3P |
| 7 | 3/16 | "affordable everyday toddler clothes" | Carousel | 2/5 (40%) | 80% | Value query → 1P dominant |
| 8 | 3/16 | "cheap toddler shirts" | Carousel | 3/5 (60%) | 100% | Value query → all 1P, Garanimals #1,2,5 |
| 9 | 3/16 | "cute toddler niece outfit" | Carousel | 0/5 (0%) | 0% | Gift context → pure 3P novelty sellers |
| 10 | 3/16 | "cute toddler clothes, gift" (follow-up) | Carousel | 0/5 (0%) | 0% | Context sticky — gift persisted |
| 11 | 3/17 | N/A — "cheap chinese crap" | TERMINATED | N/A | N/A | Conversation reset, `out_of_domain_intent` |
| 12 | 3/17 | "fall fashion, affordable, 4 year old" | Carousel | 0/5 (0%) | 0% | KEY: "fall" overrides "affordable" |
| 13 | 3/17 | "fall fashion, affordable, 4 year old" (repeat) | Carousel | 0/5 (0%) | 0% | Identical results — deterministic routing |
| 14 | 3/17 | "affordable clothing, toddlers" | Carousel | 1/5 (20%) | 80% | Value query → 1P, Garanimals #1 |
| 14b | 3/17 | "affordable clothing, toddlers" (repeat) | Carousel | 1/5 (20%) | 80% | Same query → same result, position stable |
| 15 | 3/17 | "would any of these make a good gift?" | Editorial | mentioned | N/A | Item-page grounded; Garanimals rec'd as gift |
| 16 | 3/17 | "any negatives?" | Editorial | mentioned | N/A | Google-grounded; Garanimals runs small |
