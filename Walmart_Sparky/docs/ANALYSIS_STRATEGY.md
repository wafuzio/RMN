# Sparky Analysis Strategy — Complete Investigation Plan

**Goal:** Build a complete, defensible picture of how Sparky routes queries, surfaces products, and treats Garanimals — with enough data to drive actionable recommendations.

---

## The Core Research Questions

Everything maps back to these 5 questions:

1. **What query types guarantee Garanimals visibility? What types guarantee invisibility?**
2. **Is "best selling" always a 3P trigger, or is it query-dependent?**
3. **Can any query modifier force the 1P path even when other signals suggest 3P?**
4. **Does Garanimals' editorial perception (durability narrative) come from fixable sources?**
5. **When Sparky ads launch, which query types will matter most?**

---

## The Five Investigation Waves

Run these in order. Each wave builds on the last.

---

### Wave 1 — Routing Baseline (PRIORITY: COMPLETE BEFORE TUESDAY)
**Purpose:** Confirm and extend the routing map with controlled tests.  
**Captures needed:** 10–12  
**Time per capture:** ~5 minutes

These are the highest-ROI tests. They either confirm or break the core routing theory.

| # | Query | What You're Testing | Expected Result |
|---|-------|---------------------|-----------------|
| W1-1 | `toddler rompers` | "Best selling" removed — does Garanimals appear? | **Unknown** — critical test |
| W1-2 | `cheap toddler rompers` | Value modifier + rompers | Hypothesis: 1P route, Garanimals appears |
| W1-3 | `walmart brand toddler clothes` | Explicit 1P request | Hypothesis: Forces 1P route |
| W1-4 | `toddler jeans walmart` | Generic category, no modifiers | Baseline 1P test |
| W1-5 | `toddler dresses walmart` | Generic category | Baseline 1P test |
| W1-6 | `best toddler jeans` | "Best" modifier | Does "best" = 3P trigger like "best selling"? |
| W1-7 | `cute toddler clothes` | "Cute" without gift context | Is "cute" itself a 3P trigger? |
| W1-8 | `toddler outfits under $10` | Price ceiling query | 1P or 3P? |
| W1-9 | `mix and match toddler clothes` | Garanimals core differentiator | Confirm borderline routing |
| W1-10 | `garanimals mix and match` | Branded + product feature | Does brand name force 1P? |
| W1-11 | `kids clothes for preschooler` | Generic no modifiers | Pure baseline |
| W1-12 | `affordable back to school toddler clothes` | Value + seasonal combined | Does "affordable" override "back to school"? |

**How to read results:**
- `seller_breakdown.1P == 5` → full 1P route → Garanimals should appear
- `seller_breakdown.3P == 5` → full 3P route → Garanimals invisible
- `garanimals_count > 0` but `1P < 5` → Garanimals visible in mixed route (unusual)

---

### Wave 2 — Category Coverage (PRIORITY: HIGH)
**Purpose:** Test all 14 Garanimals product categories. Find every gap.  
**Captures needed:** 28 (2 per category: with and without "best selling")  
**Time estimate:** 2–3 capture sessions

For each category below, run **both** query variants:
- `toddler [category] walmart` ← generic (expected: 1P route)
- `best selling toddler [category]` ← "best selling" modifier (expected: 3P route)

| Category | Generic Query | Best Selling Query | Status |
|----------|--------------|-------------------|--------|
| Romper | `toddler rompers walmart` | `best selling toddler rompers` | ⚠️ 3P confirmed, generic untested |
| Jean | `toddler jeans walmart` | `best selling toddler jeans` | ⬜ Untested |
| Shirt | `toddler shirts walmart` | `best selling toddler shirts` | ⚠️ "cheap shirts" tested (1P), generic untested |
| Short | `toddler shorts walmart` | `best selling toddler shorts` | ⬜ Untested |
| Dress | `toddler dresses walmart` | `best selling toddler dresses` | ⬜ Untested |
| Pajama | `toddler pajamas walmart` | `best selling toddler pajamas` | ⬜ Untested |
| Swim | `toddler swimwear walmart` | `best selling toddler swimwear` | ⬜ Untested |
| Legging | `toddler leggings walmart` | `best selling toddler leggings` | ⬜ Untested |
| Outfit | `toddler outfits walmart` | `best selling toddler outfits` | ⬜ Untested |
| Bodysuit | `toddler bodysuits walmart` | `best selling toddler bodysuits` | ⬜ Untested |
| Jumpsuit | `toddler jumpsuits walmart` | `best selling toddler jumpsuits` | ⬜ Untested |
| Overall | `toddler overalls walmart` | `best selling toddler overalls` | ⬜ Untested |
| Pant | `toddler pants walmart` | `best selling toddler pants` | ⬜ Untested |
| Skirt | `toddler skirts walmart` | `best selling toddler skirts` | ⬜ Untested |

**What you're building:** A category visibility matrix — which product types Garanimals wins, which it loses, and whether the loss is routing-caused or ranking-caused.

---

### Wave 3 — Modifier Testing (PRIORITY: MEDIUM)
**Purpose:** Map every trigger word. Build the complete routing decision tree.  
**Captures needed:** 15–20  
**Run after Wave 1 & 2**

Pick one control query (e.g., `toddler clothes walmart`) and add one modifier at a time:

**Value modifiers (hypothesis: 1P triggers):**
- `cheap toddler clothes walmart`
- `affordable toddler clothes walmart`
- `budget toddler clothes walmart`
- `inexpensive toddler clothes walmart`
- `toddler clothes under $15`

**Seasonal modifiers (hypothesis: 3P triggers):**
- `summer toddler clothes walmart`
- `winter toddler clothes walmart`
- `spring toddler clothes walmart`
- `fall toddler clothes walmart`
- `holiday toddler outfits`

**Context modifiers (hypothesis: test each):**
- `cute toddler clothes walmart` — is "cute" a trigger?
- `trendy toddler clothes walmart` — is "trendy" a trigger?
- `best toddler clothes walmart` — is "best" alone a trigger?
- `popular toddler clothes walmart` — is "popular" a trigger?
- `toddler clothes for a 2 year old` — does age specificity change routing?
- `2T toddler clothes walmart` — does size specificity change routing?

**What you're building:** A modifier taxonomy — safe words vs. dangerous words for 1P routing.

---

### Wave 4 — Editorial & Perception (PRIORITY: MEDIUM)
**Purpose:** Map what sources drive Sparky's editorial narrative about Garanimals.  
**Captures needed:** 8–10  
**Run in multi-turn conversations**

These queries trigger Google-grounded editorial responses. Record every source domain.

| Query | What It Tests |
|-------|--------------|
| `are garanimals clothes good quality` | Core quality perception |
| `how durable are garanimals clothes` | Durability narrative specifically |
| `garanimals vs cat and jack quality` | Direct comparison grounding |
| `do garanimals clothes hold up in the wash` | Practical durability |
| `garanimals clothes reviews` | Review aggregation sources |
| `is garanimals worth buying` | Value proposition framing |
| `what do parents think of garanimals` | Community opinion sources |
| `why is cat and jack more popular than garanimals` | Competitive framing |

**For each editorial capture, record:**
1. Every source domain in `source_domains` array
2. The exact language used (copy full `editorial_metrics.full_response`)
3. Whether Garanimals is mentioned positively, neutrally, or negatively
4. Whether Cat & Jack is mentioned and how it's framed comparatively

**What you're building:** A source map — which websites feed Sparky's editorial. These are the sites where content changes would affect Sparky's responses.

---

### Wave 5 — Longitudinal Sentinel Tracking (PRIORITY: ONGOING)
**Purpose:** Detect changes over time. Track whether routing shifts, products change, or ads go live.  
**Captures needed:** 5 queries, run weekly  
**This wave never ends**

Pick these **5 sentinel queries** and run them every week on the same day:

| Sentinel | Query | What It Tracks |
|----------|-------|----------------|
| S1 | `cheap toddler clothes walmart` | Core 1P baseline — Garanimals share + position |
| S2 | `best kids clothing brands at walmart` | Brand query routing stability |
| S3 | `back to school toddler clothes` | Seasonal 3P routing stability |
| S4 | `toddler rompers walmart` | Romper gap — does it ever resolve? |
| S5 | `are garanimals good quality` | Editorial sentiment + source domains |

**Alert conditions (check after each weekly run):**
- `ads_active` becomes `true` on any sentinel → **IMMEDIATE ACTION**
- `garanimals_positions` shifts by 2+ positions on S1 or S2
- S2 or S4 routing changes (1P% shifts by 20%+)
- New domain appears in `source_domains` on S5
- `max_ads` value changes from current baseline of 4–8

---

## How to Interpret Results

### Routing diagnosis flowchart

```
Look at seller_breakdown in parsed JSON:
│
├─ 1P = 4-5, 3P = 0-1 → FULL 1P ROUTE
│   └─ Garanimals should appear; if not, it's a RANKING problem not routing
│
├─ 1P = 0, 3P = 5 → FULL 3P ROUTE
│   └─ Garanimals cannot appear regardless of rank — ROUTING problem
│
└─ 1P = 2-3, 3P = 2-3 → BORDERLINE ROUTE
    └─ Rare; document query and test again
```

### What the reformulated query tells you

```
reformulated: "toddler clothes"          → clean generic → 1P expected
reformulated: "toddler clothes, gift"    → gift context injected → 3P expected
reformulated: "back to school clothes"   → seasonal preserved → 3P expected
reformulated: "cheap toddler clothes"    → value term preserved → 1P expected
```

If the reformulated query contains words you didn't type (like "gift"), that's context injection from earlier in the conversation.

### Scoring Garanimals performance per query

| Garanimals Count | 1P% | Score | Interpretation |
|-----------------|-----|-------|----------------|
| 3–5 | 80–100% | ⭐⭐⭐ Excellent | Dominant on this query |
| 2 | 80–100% | ⭐⭐ Good | Visible, not dominant |
| 1 | 60–80% | ⭐ Weak | Present but easily displaced |
| 0 | 80–100% | ⚠️ Ranking gap | Right path, wrong rank |
| 0 | 0–20% | ❌ Routing gap | Wrong path — fix the query |

---

## Building the Deliverable: Query Optimization Matrix

By the end of Waves 1–3, you'll be able to produce this matrix for the client:

```
QUERY TYPE         | ROUTE | GARANIMALS | RECOMMENDATION
──────────────────────────────────────────────────────────
Generic category   | 1P    | High       | Target these — safe territory
+ "walmart"        | 1P    | High       | Include "walmart" in product titles/desc
+ "affordable"     | 1P    | High       | "Affordable" is a safe modifier
+ "cheap"          | 1P    | High       | "Cheap" drives strong 1P routing
+ "best selling"   | 3P    | ZERO       | AVOID — guaranteed invisibility
+ "back to school" | 3P    | ZERO       | AVOID — seasonal = 3P
+ "cute"           | ?     | TBD        | Test needed
+ "best"           | ?     | TBD        | Test needed
```

This matrix is the primary output of the investigation. It tells a brand manager exactly which words to use and avoid in product titles, descriptions, and content.

---

## Practical Session Planning

### Before Tuesday (5–6 captures)
Run Wave 1 priority tests: W1-1, W1-2, W1-7, W1-10, W1-12
- `toddler rompers` — closes the biggest open question
- `cheap toddler rompers` — confirms value + category
- `cute toddler clothes` — tests "cute" trigger
- `garanimals mix and match` — branded query behavior
- `affordable back to school toddler clothes` — does "affordable" override "back to school"?

### Session structure (20–30 minutes each)
1. Open `queries/query_list.txt` — pick 5 queries from highest-priority wave
2. For each query:
   a. Open new Sparky conversation (important — don't chain unrelated queries)
   b. Submit query, wait for full response
   c. Export from HTTP Catcher
   d. Paste into `new_capture_input.txt`
   e. Run `parse_har_curl.py`
   f. Note if result is expected or surprising
3. After session, review `docs/CAPTURE_LOG.md` — add context notes

### When to chain queries (multi-turn captures)
Use multi-turn conversations intentionally for:
- Editorial follow-ups: First query gets products, second asks "why" questions
- Context persistence tests: Does gift/seasonal context stick?
- Gift-path editorial: Do products recommended via 1P path get endorsed as gifts?

For multi-turn, you need a separate capture for each turn — export each request individually from HTTP Catcher.

---

## Progress Tracking

Use this checklist to track completion:

### Wave 1 — Routing Baseline
- [ ] W1-1: `toddler rompers` (no modifier)
- [ ] W1-2: `cheap toddler rompers`
- [ ] W1-3: `walmart brand toddler clothes`
- [ ] W1-4: `toddler jeans walmart`
- [ ] W1-7: `cute toddler clothes`
- [ ] W1-10: `garanimals mix and match`
- [ ] W1-12: `affordable back to school toddler clothes`

### Wave 2 — Category Coverage (13 untested)
- [ ] Jean (×2)
- [ ] Shirt generic (×2)
- [ ] Short (×2)
- [ ] Dress (×2)
- [ ] Pajama (×2)
- [ ] Swim (×2)
- [ ] Legging (×2)
- [ ] Outfit (×2)
- [ ] Bodysuit (×2)
- [ ] Jumpsuit (×2)
- [ ] Overall (×2)
- [ ] Pant (×2)
- [ ] Skirt (×2)

### Wave 3 — Modifier Testing
- [ ] Value modifiers (5 queries)
- [ ] Seasonal modifiers (5 queries)
- [ ] Context modifiers (6 queries)

### Wave 4 — Editorial
- [ ] Quality perception (4 queries)
- [ ] Durability perception (2 queries)
- [ ] Comparative (2 queries)

### Wave 5 — Sentinel Setup
- [ ] Week 1 baseline for all 5 sentinel queries
- [ ] Week 2 repeat
- [ ] (ongoing)

---

## Total Capture Count to "Complete" Analysis

| Wave | Captures | Status |
|------|----------|--------|
| Wave 1 (baseline) | 12 | 4 done, 8 remaining |
| Wave 2 (categories) | 28 | 2 done (romper 3P), 26 remaining |
| Wave 3 (modifiers) | 16 | 3 done (fall, affordable, back-to-school) |
| Wave 4 (editorial) | 8 | 2 done, 6 remaining |
| Wave 5 (sentinel) | 5/week | Not started |
| **Total to complete** | **~57 new captures** | |

At 5–6 captures per session, that's approximately **10–12 sessions** to complete Waves 1–4.
