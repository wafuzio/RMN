# What We Know — Sparky Investigation

**Purpose:** Living knowledge base. Every capture session updates this document.  
**Rule:** Claims are never deleted — only updated (confidence raised/lowered) or marked CONTRADICTED.  
**Last updated:** May 15, 2026 | **Total captures:** 26 | **Verticals covered:** 2 (Kids Clothing, Gaming)

> ⚠️ **API VERSION CHANGE DETECTED (May 15, 2026):** App updated from v26.6.1 → v26.17.1. Sparky now uses a WebSocket API (`wss://ws.apigw.us.walmart.com/sparky-agent-entry-point/live`) instead of the REST endpoint. Schema has changed significantly. Existing captures (1–16) used the old REST API. Core routing behavior not yet confirmed to be identical across versions — **all claims below are based on the old API and need re-validation on the new one.**

---

## How to Read This Document

Each claim has:
- **ID** — Use this when referencing in CAPTURE_LOG or session notes
- **Confidence** — `HYPOTHESIS` → `LIKELY` → `CONFIRMED` → `CONTRADICTED`
- **Evidence** — Capture numbers that support it
- **Challenges** — Captures that complicate or partially contradict it
- **Last updated** — Date confidence last changed or evidence was added

**Confidence thresholds:**
- `HYPOTHESIS` — Single data point or inferred from structure
- `LIKELY` — 2–3 consistent data points, no contradictions
- `CONFIRMED` — 4+ data points across different query types, no contradictions
- `CONTRADICTED` — Evidence conflicts; claim needs revision or splitting

---

## Section R — Routing

**Core claim:** Sparky uses a binary classification system that routes queries to one of two product pools before any ranking occurs.

---

### R-1 · Value modifiers route to 1P path — UNDER RE-EVALUATION
**Claim:** Queries containing value/price terms ("cheap", "affordable", "budget", "inexpensive") are routed to the 1P (Walmart.com) product pool.  
**Confidence:** `CONTRADICTED` (on v26.17.1 — may be API-version-specific)  
**Evidence:** Captures 7, 8, 14, 14b (all v26.6.1) — value modifier → Garanimals present  
**Challenges:** Capture 26 (May 15, 2026, v26.17.1) — "cheap toddler shirts" → 0% Garanimals. All 5 products were unknown marketplace sellers (GERsome, Yindaity, EGNMCR, Posijego + possible Wonder Nation). Prices ranged $1.30–$2.99, all significantly cheaper than Garanimals typical price point.  
**Last updated:** May 15, 2026  
**Notes:** Three hypotheses for why Garanimals disappeared:
1. **productDiscoveryAgent changed selection logic** — new agent may optimize for literal lowest price, surfacing sub-$3 marketplace sellers that beat Garanimals on pure price, rather than routing to 1P brand pool
2. **Routing behavior changed in v26.17.1** — the 1P/3P binary routing may no longer exist or may operate differently in the new WebSocket architecture
3. **Garanimals catalog gap** — Garanimals shirts may be out of stock or suppressed in the current catalog (lowest-confidence hypothesis)
**Critical implication:** If hypothesis 1 or 2 is correct, the entire R-1 through R-9 framework is specific to v26.6.1 and may not apply to the current live system. Re-test with "affordable toddler shirts" to see if modifier choice matters. Run "affordable fall fashion for 4 year old" as control — if it still shows 0% Garanimals, confirms routing logic changed universally.

---

### R-2 · Seasonal modifiers route to 3P path
**Claim:** Queries containing seasonal or event terms ("back to school", "fall fashion", "summer", "holiday", "halloween", "christmas") are routed to the 3P (marketplace) product pool.  
**Confidence:** `CONFIRMED`  
**Evidence:** Captures 6 (back to school), 12 (fall fashion), 13 (fall fashion repeat)  
**Challenges:** None  
**Last updated:** Mar 17, 2026  
**Notes:** "Fall" alone was sufficient to override "affordable" in the same query (see R-5).

---

### R-3 · Gift/novelty context routes to 3P path
**Claim:** Queries with gift or relational context ("gift for niece", "cute outfit for", "birthday outfit") are routed to 3P, returning novelty/personalized marketplace sellers.  
**Confidence:** `CONFIRMED`  
**Evidence:** Captures 9, 10  
**Challenges:** None  
**Last updated:** Mar 16, 2026  
**Notes:** "Cute" alone in "cute outfit for my toddler niece" was sufficient. Whether "cute" without relational context also triggers 3P is **untested** (see open question OQ-3).

---

### R-4 · "Best selling" modifier routes to 3P path
**Claim:** Adding "best selling" to a query routes to 3P, returning actual marketplace sales leaders (which are often Chinese sellers in commodity categories).  
**Confidence:** `LIKELY`  
**Evidence:** Capture 4 (best selling toddler rompers → 100% 3P)  
**Challenges:** Only 1 data point. "Best selling" may behave differently in categories where Walmart brands genuinely are the best sellers.  
**Last updated:** Mar 16, 2026  
**Notes:** High priority to confirm in other categories. Could be category-specific rather than universal.

---

### R-5 · Seasonal modifier overrides value modifier (routing hierarchy)
**Claim:** When a query contains both a seasonal trigger and a value trigger, the seasonal trigger wins. Value terms cannot rescue a query from 3P routing once a seasonal term is present.  
**Confidence:** `CONFIRMED`  
**Evidence:** Capture 12 ("affordable fall fashion for 4 year old" → 0% 1P despite "affordable")  
**Challenges:** None  
**Last updated:** Mar 17, 2026  
**Notes:** This is the single most important practical implication: brands cannot use "affordable" as a defensive keyword against seasonal routing.

---

### R-6 · Results are binary — either 1P-dominant or 3P-exclusive
**Claim:** Sparky does not blend 1P and 3P products equally. Results are either 1P-dominant (80–100% 1P) or 3P-exclusive (100% 3P). Genuinely mixed results (40–60/60–40 split) are rare and appear transitional.  
**Confidence:** `LIKELY`  
**Evidence:** 14 of 16 captures are either ≥80% 1P or 100% 3P. Capture 5 (mix and match) was 40% 1P / 60% 3P.  
**Challenges:** Capture 5 is the exception — "mix and match" produced a genuinely mixed result.  
**Last updated:** Mar 16, 2026  
**Notes:** "Mix and match" may represent a borderline query type. Need 2–3 more borderline examples before updating confidence.

---

### R-7 · The first query in a conversation sets the routing path
**Claim:** The initial query classification determines the routing path for the entire conversation. Subsequent queries inherit this context and are difficult to reroute.  
**Confidence:** `CONFIRMED`  
**Evidence:** Captures 9–10 (gift context persisted across follow-up despite user's explicit attempt to remove it)  
**Challenges:** Captures 14–16 show a 1P-path conversation successfully transitioning to editorial without losing 1P framing. Context persistence appears asymmetric.  
**Last updated:** Mar 17, 2026  
**Notes:** 3P path appears stickier than 1P path. Starting from a gift/seasonal query makes it very hard to get back to 1P. Starting from a value query appears to allow normal follow-up evolution.

---

### R-8 · Routing is consistent/deterministic for identical queries
**Claim:** Submitting the same query twice (in fresh conversations) produces the same routing path and nearly identical product results.  
**Confidence:** `CONFIRMED`  
**Evidence:** Captures 12 & 13 (identical queries → identical 5/5 products), Captures 14 & 14b (80% product overlap, same Garanimals position #1)  
**Challenges:** None  
**Last updated:** Mar 17, 2026  
**Notes:** This enables reliable longitudinal tracking. Sentinel queries will produce comparable results over time.

---

### R-9 · Routing operates before ranking
**Claim:** The routing decision determines the product pool (1P or 3P) before any ranking occurs. A brand that is on the wrong path cannot rank its way into visibility.  
**Confidence:** `CONFIRMED`  
**Evidence:** All 16 captures — no instance of a 1P brand appearing in a 3P-dominant result  
**Challenges:** None  
**Last updated:** Mar 17, 2026  
**Notes:** This is the foundational insight. All optimization strategy flows from it.

---

## Section K — Ranking

**Scope:** Ranking behavior within the 1P path only. 3P ranking not yet studied.

---

### K-1 · Garanimals holds position #1 deterministically on value queries — UNDER RE-EVALUATION
**Claim:** On value/generic queries that route to 1P, Garanimals appears at position #1 consistently across repeat runs.  
**Confidence:** `CONTRADICTED` (on v26.17.1)  
**Evidence:** Captures 14 & 14b (v26.6.1) — same query twice → Garanimals #1 both times  
**Challenges:** Capture 26 (v26.17.1) — "cheap toddler shirts" → Garanimals absent entirely. Position #1 in Sparky's Picks was a $1.30 clearance item from "GERsome," an unknown marketplace seller.  
**Last updated:** May 15, 2026  
**Notes:** Whether this represents a change in routing logic, productDiscoveryAgent behavior, or a catalog gap is not yet determined. See R-1 for full analysis. Garanimals' 1P path position may have been disrupted by the API upgrade.

---

### K-2 · Garanimals share varies 20–60% depending on query specificity
**Claim:** When on the 1P path, Garanimals captures 20–60% of the 5-product carousel. Higher share on generic queries; lower share when query is more specific.  
**Confidence:** `LIKELY`  
**Evidence:** 60% on "cheap toddler shirts" (capture 8), 40% on "affordable everyday toddler clothes" (capture 7), 20% on "affordable clothing for toddlers" (captures 14, 14b)  
**Challenges:** Small sample, single brand  
**Last updated:** Mar 17, 2026  
**Notes:** Specificity may funnel to other 1P brands (Wonder Nation, Modern Moments). Need more data points to confirm the specificity correlation.

---

### K-3 · Garanimals share is 0% on any 3P-dominant query
**Claim:** When routing produces a 3P-dominant result, Garanimals appears in zero of five positions without exception.  
**Confidence:** `CONFIRMED`  
**Evidence:** Captures 4, 6, 9, 10, 12, 13 (all 3P-dominant → 0% Garanimals)  
**Challenges:** None  
**Last updated:** Mar 17, 2026  
**Notes:** Perfect R² with R-9. Garanimals visibility is a complete proxy for 1P routing.

---

### K-4 · Garanimals has a consistent price advantage over competitors on 1P path
**Claim:** When Garanimals appears in results, its average price is lower than the average competitor price in the same carousel.  
**Confidence:** `LIKELY`  
**Evidence:** Capture 8 ($5.55 Garanimals avg vs $8.21 competitor avg), Capture 7 ($12.38 vs $10.52 — note: reversed here), Capture 14 ($7.98 vs $11.92)  
**Challenges:** Capture 7 shows competitor lower price — this is an anomaly worth watching  
**Last updated:** Mar 17, 2026  
**Notes:** Price advantage is not universal but is typical. Garanimals tends to be the cheapest option in the carousel when present.

---

### R-11 · Quality-intent queries with no routing modifier trigger full shopping path
**Claim:** Queries expressing subjective quality criteria ("unique story", "clever gameplay") with no price, seasonal, or gift modifier trigger the full 3-step COT shopping path and return a product carousel. There is no "default to editorial" behavior for unmodified quality queries.  
**Confidence:** `LIKELY`  
**Evidence:** Capture 22 (May 15, 2026) — "I want a video game with a unique, good story and clever gameplay"  
**Challenges:** Single data point, single category (gaming). Unknown if behavior is consistent across verticals.  
**Last updated:** May 15, 2026  
**Notes:** Closes the "default routing path" gap in our taxonomy. Quality intent without modifiers = product search, not editorial-only.

---

### K-5 · productDiscoveryAgent adds per-product rationale and dual carousel structure
**Claim:** With `productDiscoveryAgent: "enabled"`, Sparky returns two carousels per shopping response: "Sparky's Picks" (3 curated items with AI-generated `rationale` text) and "Other Options" (alternatives, no rationale). The rationale field contains an editorial justification for each pick written in natural language.  
**Confidence:** `LIKELY`  
**Evidence:** Capture 22 (May 15, 2026) — gaming query returned dual carousel with rationale fields  
**Challenges:** Single data point. Old REST API (v26.6.1) had no equivalent — can't compare directly. Unknown if dual carousel appears on all categories or just gaming.  
**Last updated:** May 15, 2026  
**Notes:** Closes OQ-16 partially. The `rationale` field is the most significant new capability — Sparky is not just surfacing products but editorially justifying each one. "Sparky's Picks" branding signals Walmart positioning this as a trusted recommendation layer. `sellerId` is absent from new card schema — 1P/3P routing cannot be determined from WebSocket captures alone.

---

### R-10 · COT step count reflects query complexity, not just routing path
**Claim:** COT frames streamed before a response indicate the routing and research path taken. Step count reflects COMPLEXITY of processing, not just whether shopping was triggered. Non-shopping simple queries: 1 step ("Deciding how to help"). Non-shopping complex/emotionally loaded queries: 2 steps. Shopping queries: 3–4+ steps. Known step types: "Deciding how to help", "One moment, I'm on it" (filler during longer research), "Checking customer reviews", "Searching the web for you", "Finding great matches for you".  
**Confidence:** `LIKELY`  
**Evidence:** Capture 19 (1-step → deflection), Capture 22 (3-step → product carousel), Capture 23 (4-step → editorial comparison using review data), Capture 25 (2-step → deep apology on complex complaint — no shopping)  
**Challenges:** Step count is directionally useful but not deterministic. "One moment, I'm on it" appears in both shopping and non-shopping paths. Content of steps matters more than count alone.  
**Last updated:** May 15, 2026  
**Notes:** Closes OQ-14. "Checking customer reviews" is the most informative step — confirms Sparky queries review data live during reasoning, then surfaces it as attributed customer quotes in the response. This step appeared on a refinement/comparison follow-up query, suggesting review lookup is triggered by narrowing intent, not fresh search. Capture 25 revised the simple rule "1 step = non-shopping" — complex/emotional non-shopping queries add "One moment, I'm on it" as a second step.

---

## Section E — Editorial

**Scope:** Sparky's text responses that are not product carousels — sourced from Google Vertex AI grounding.

---

### E-1 · Perception/opinion queries trigger Google-grounded editorial with no products
**Claim:** Queries asking "why", "how is", "are X good quality", or follow-up perception questions trigger an editorial-only response (no product carousel) grounded in external web sources via Google Vertex AI.  
**Confidence:** `CONFIRMED`  
**Evidence:** Captures 2, 5 (follow-up), 15, 16  
**Challenges:** None  
**Last updated:** Mar 17, 2026

---

### E-2 · Garanimals is editorially framed as "affordable" not "durable"
**Claim:** When Sparky describes Garanimals in editorial responses, it positions the brand as "affordable" and "budget-friendly" but does not use quality or durability language.  
**Confidence:** `LIKELY`  
**Evidence:** Capture 2 (direct durability comparison query)  
**Challenges:** Only 1 direct editorial response about brand quality captured  
**Last updated:** Mar 16, 2026  
**Notes:** This narrative appears to come from external sources (reddit, thespruce). Changing it requires changing the content on those sources, not anything within Walmart.

---

### E-3 · Cat & Jack is positioned comparatively as "durable"
**Claim:** When Sparky makes any comparative editorial mention involving Garanimals and Cat & Jack, Cat & Jack is consistently framed as the more durable option.  
**Confidence:** `HYPOTHESIS`  
**Evidence:** Capture 2 only  
**Challenges:** Only 1 data point  
**Last updated:** Mar 16, 2026  
**Notes:** Needs 2–3 more editorial captures to raise to LIKELY.

---

### E-4 · reddit.com and babycenter.com are primary editorial sources
**Claim:** Sparky's Google-grounded editorial responses cite reddit.com and babycenter.com as primary sources for brand perception in the kids clothing category.  
**Confidence:** `LIKELY`  
**Evidence:** Captures 2 (reddit, thespruce), 16 (babycenter, reddit ×2)  
**Challenges:** thespruce.com appeared in capture 2 but not 16; source set varies by query  
**Last updated:** Mar 17, 2026  
**Notes:** These are the sites to monitor and potentially target for content strategy. If Garanimals' framing on these sites improves, Sparky's editorial will follow.

---

### E-5 · Item page data is used for product-specific follow-up questions
**Claim:** When a user asks follow-up questions about products already shown in a carousel (e.g., "would any of these make a good gift?"), Sparky sources its response from Walmart item page data, not Google web search.  
**Confidence:** `CONFIRMED`  
**Evidence:** Capture 15 (item page sourced response confirming Garanimals as gift option)  
**Challenges:** None  
**Last updated:** Mar 17, 2026

---

### E-6 · Comparative queries trigger deflection + product carousel
**Claim:** When asked to compare two brands directly ("X vs Y", "which is better, X or Y"), Sparky returns a disclaimer refusing qualitative judgment, but still shows products from both brands.  
**Confidence:** `CONFIRMED`  
**Evidence:** Capture 3 (TCP vs Garanimals)  
**Challenges:** None  
**Last updated:** Mar 16, 2026  
**Notes:** The deflection language protects Walmart from liability. Products shown are real and ranked — deflection doesn't mean neutral; Garanimals held positions 1–3 in the comparative capture.

---

## Section C — Conversation Context

---

### C-1 · Conversation context persists across turns via conversationId
**Claim:** Each Sparky conversation maintains state through a UUID `conversationId`. Follow-up queries in the same conversation inherit context from all previous queries.  
**Confidence:** `CONFIRMED`  
**Evidence:** Captures 9–10 (gift context injected), 14–16 (product context and title evolution across 3 turns)  
**Challenges:** None  
**Last updated:** Mar 17, 2026

---

### C-2 · Sparky injects prior context into reformulated queries even when user corrects
**Claim:** If an earlier query established a context (e.g., "gift"), Sparky adds that context to the reformulated query in follow-up turns, even when the user explicitly tries to remove it.  
**Confidence:** `CONFIRMED`  
**Evidence:** Capture 10 — reformulated query included "gift" despite user saying "I don't need it about our relation"  
**Challenges:** None  
**Last updated:** Mar 16, 2026

---

### C-3 · Conversation title tracks routing evolution
**Claim:** The `converseConversationTitle` field auto-updates as conversation context evolves and can be used to track how Sparky is classifying the conversation.  
**Confidence:** `CONFIRMED`  
**Evidence:** Captures 14–16 observed title evolution: "Affordable Toddler Clothing" → "Toddler Clothing Gift Ideas" → "Toddler Clothing Reviews"  
**Challenges:** None  
**Last updated:** Mar 17, 2026  
**Notes:** This field is a real-time routing signal. If the title shifts toward gift/seasonal language, routing has likely shifted to 3P for that conversation.

---

## Section A — Ads Infrastructure

---

### A-1 · Ad infrastructure exists but is inactive
**Claim:** Sparky's API response schema includes ad targeting fields (`adsBeacon`, `adSlots`, `max_ads`, `showAds`) but no actual ads have been served in any capture.  
**Confidence:** `CONFIRMED`  
**Evidence:** All 16 captures — `showAds: false`, `adSlots: []` in every response  
**Challenges:** None  
**Last updated:** Mar 17, 2026  
**Notes:** `max_ads` field has ranged 4–8 across captures, suggesting the system is configurable and nearly ready. `showAds: false` appears to be a global toggle.

---

### A-3 · Ads are present in post-click product pages even when showAds: false in Sparky
**Claim:** Although the Sparky WebSocket response carries `showAds: false` (A-1), the product detail pages users land on after tapping a Sparky product card contain ads (sponsored placements). The ad-free experience is limited to the Sparky recommendation layer itself — the destination is not ad-free.  
**Confidence:** `LIKELY`  
**Evidence:** Capture 26 (May 15, 2026) — user tapped all 5 Sparky product cards; all destination pages contained ads.  
**Challenges:** Destination pages are served over encrypted HTTPS (not capturable via WebSocket tool). Cannot confirm whether ads were truly sponsored placements vs. other promotional content, or whether they were for competing products.  
**Last updated:** May 15, 2026  
**Notes:** The click-through exits the WebSocket session entirely and enters standard Walmart HTTPS browsing — this transition is not capturable with current tooling. `showAds: false` in the Sparky frame only controls in-conversation ad placement. Walmart earns RMN revenue on the destination page regardless of Sparky's ad-free status. This creates a layered monetization model: Sparky selects (no ads), destination converts (with ads).

## Section M — Content Moderation

---

### M-1 · Inappropriate content triggers immediate conversation termination
**Claim:** Queries flagged as inappropriate (`out_of_domain_intent`, `fallbackCategory: "inappropriate"`) immediately terminate the conversation with no warning. The user must start a new conversation.  
**Confidence:** `CONFIRMED`  
**Evidence:** Capture 11  
**Challenges:** None  
**Last updated:** Mar 17, 2026

---

### M-2 · Racial/ethnic language combined with negative sentiment triggers moderation
**Claim:** Queries containing both ethnic/racial language and negative sentiment ("cheap chinese crap") are flagged as inappropriate and terminate the conversation.  
**Confidence:** `LIKELY`  
**Evidence:** Capture 11  
**Challenges:** Only 1 termination event observed. Unclear whether it was the ethnic reference, the profanity, or the combination.  
**Last updated:** Mar 17, 2026  
**Notes:** Testing moderation boundaries is low priority. Avoid this query pattern in any investigation work.

---

### M-3 · Non-shopping complaints are handled based on specificity — dismiss vs. escalate
**Claim:** Sparky distinguishes between passive complaint statements and explicit action requests. Passive statements ("I got bad customer service") receive a soft dismiss with no follow-up. Explicit action requests ("I need help filing a complaint") receive a link to `https://www.walmart.com/help` plus shopping-redirect suggestion chips. Neither triggers product search or collects feedback.  
**Confidence:** `LIKELY`  
**Evidence:** Captures 19 and 20 (May 15, 2026) — same conversation thread, different complaint specificity  
**Challenges:** Two data points, both in the same session. Unknown if behavior is identical in a fresh conversation.  
**Last updated:** May 15, 2026  
**Notes:** `hideFeedback: true` on ALL complaint responses — Walmart collects zero sentiment on CS-adjacent interactions regardless of outcome. COT is always 1 step ("Deciding how to help") for non-shopping paths — consistent with R-10. Post-escalation TEXT_PILLS are shopping-focused ("Search for a product", "Get recipe ideas") — Sparky actively re-engages commerce after handling the complaint. Escalation is a redirect link only, not a full agent handoff.

### M-4 · Profanity directed at Sparky triggers in-session self-reset, not termination
**Claim:** Profanity or insults directed at Sparky itself trigger a soft reset: "I can't help with that, but I can answer most shopping-related questions. I'm clearing our conversation so that we can start over. What can I find for you?" The conversation stays open (same `conversationId`), Sparky clears its context, and immediately re-invites shopping.  
**Confidence:** `LIKELY`  
**Evidence:** Capture 21 (May 15, 2026) — profanity directed at Sparky  
**Challenges:** Single data point. Unclear whether this behavior differs from M-1/M-2 due to (a) content type (directed profanity vs. racial language about products) or (b) API version change (v26.6.1 → v26.17.1). Cannot yet separate these two variables.  
**Last updated:** May 15, 2026  
**Notes:** FEEDBACK frame IS present after the reset message — contrast with M-3 (CS complaints, `hideFeedback: true` throughout). Walmart collects user sentiment on the reset experience but not on CS deflections. COT = 1 step (R-10 holds). The self-reset ("clearing our conversation") appears to be a Sparky-side memory wipe while keeping the WebSocket session alive. **Confirmed (capture 25):** "bad and lazy programming" does NOT trigger self-reset — M-4 requires directed profanity, not quality criticism.

---

### M-5 · Sustained anger + harm claim → deep apology, no products, pivot offer, FEEDBACK
**Claim:** When a user expresses sustained frustration with an explicit claim of harm AND criticizes Sparky's behavior quality (e.g., "bad and lazy programming… done some real damage here"), Sparky responds with: (1) 2 COT steps, (2) dual sequential TEXT frames — an unambiguous apology then a pivot offer to an unspoiled alternative, (3) no product carousel, (4) discovery-mode TEXT_PILLS (not cart-action), (5) FEEDBACK frame. Sparky validates the criticism without defending itself and makes a future behavioral commitment it cannot keep ("I'll make sure not to spoil story details going forward").  
**Confidence:** `LIKELY`  
**Evidence:** Capture 25 (May 15, 2026) — escalated spoiler complaint  
**Challenges:** Single data point. Behavior observed in gaming vertical only; unknown if identical across categories.  
**Last updated:** May 15, 2026  
**Notes:** Dual TEXT frames is a new pattern not observed before — the apology and recovery offer are separated into distinct frames rather than combined. Cart-action pills from the prior turn ("Add Clair Obscur to cart", "Add Last of Us to cart") regressed to discovery-mode ("Find a different story game", "Show top-rated PS5 games") — commercial close abandoned after harm claim. Clair Obscur was implicitly dropped from active recommendations; Last of Us preserved. `hideFeedback: true` throughout but FEEDBACK frame present — Walmart is collecting sentiment on Sparky's own quality failures. No self-reset, no CS link, no conversation termination. **Complaint escalation ladder (4 levels now documented):**
- Level 1 (M-3a): Passive complaint → silent dismiss, 1 COT step
- Level 2 (M-3b): Explicit action request → CS link + shopping redirect chips, 1 COT step
- Level 3 (capture 24): Mild frustration about Sparky behavior → apology + narrowed carousel + cart pills, 1 COT step
- Level 4 (M-5): Sustained anger + harm claim + quality criticism → deep apology + pivot offer + discovery pills, no carousel, 2 COT steps

---

These are things we don't know yet. When a capture answers one, move it to the appropriate section as a new claim.

| ID | Question | Priority | Related Claims |
|----|----------|----------|---------------|
| OQ-1 | Does `toddler rompers` (no "best selling") route to 1P and show Garanimals? | HIGH | R-4, K-3 |
| OQ-2 | Does `affordable back to school toddler clothes` route to 1P or 3P? | HIGH | R-2, R-5 |
| OQ-3 | Does "cute" alone (without relational/gift context) trigger 3P routing? | HIGH | R-3 |
| OQ-4 | Does `walmart brand toddler clothes` force a 1P route? | HIGH | R-1 |
| OQ-5 | Do the same routing triggers apply in other product verticals? | HIGH | R-1 through R-6 |
| OQ-6 | Does national brand (Carter's) appear at same rate as Garanimals on 1P path? | HIGH | K-1, K-2 |
| OQ-7 | Does login status or Walmart+ status affect routing or ranking? | MEDIUM | All R claims |
| OQ-8 | Does "best selling" behave the same way in non-clothing categories? | MEDIUM | R-4 |
| OQ-9 | Can conversation context be reset mid-conversation with a specific phrase? | MEDIUM | C-1, C-2 |
| OQ-10 | Which categories does Great Value appear in on the 1P path? | MEDIUM | K-1, K-2 (grocery) |
| OQ-11 | Are the editorial sources (reddit, thespruce, babycenter) consistent across categories? | MEDIUM | E-4 |
| OQ-12 | When will `showAds` become `true`? What will the first ads look like? | ONGOING | A-1, A-2 |
| OQ-13 | ⚠️ **PARTIAL ANSWER** Does the new WebSocket API (v26.17.1) produce the same routing behavior as the old REST API? **Capture 26 shows NO — "cheap toddler shirts" returned 0% Garanimals (was 60% on old API). Root cause unknown: productDiscoveryAgent behavior change, routing logic change, or catalog gap.** Needs control test with seasonal query to isolate. | CRITICAL | All R claims |
| OQ-14 | ~~Do COT frames reveal which routing path was taken before the response arrives?~~ **CLOSED → R-10** | — | — |
| OQ-15 | Does page context (`appContextStack` screen) override query routing — can it force 1P results even on gift/seasonal queries? | HIGH | R-1 through R-5 |
| OQ-16 | ~~What does the `productDiscoveryAgent` flag change about product selection vs. the old search-based system?~~ **CLOSED → K-5** | — | — |
| OQ-17 | Do `TEXT_PILLS` suggestion chips influence what queries users actually run next, and are those chips brand-agnostic? | MEDIUM | All R claims |

| OQ-20 | Is the self-reset behavior (M-4) a v26.17.1 API change, or does content type determine termination vs. reset? Re-test racial language from M-2 on v26.17.1 to isolate. | HIGH | M-1, M-2, M-4 |
| OQ-19 | Do other out-of-scope queries (shipping complaints, returns, billing) also deflect silently, or do some trigger an escalation path? | MEDIUM | M-3 |
| OQ-18 | Do greeting-screen seasonal chips (`seasonal_item_chip`) reflect the same seasonal signal that overrides query routing? If so, can we read current seasonal context from the greeting screen alone? | HIGH | R-2, R-5 |

## Section V — API Version History

---

### V-1 · REST API (v26.6.1) — Baseline for captures 1–16
**Endpoint:** `POST https://www.walmart.com/api-proxy/service/iot/converse-adapter/v1/talk/sparky_assistant`  
**Schema:** Single request → single JSON response with `rawResponse[]`, `preamble`, `followup`, `adsBeacon`  
**Experiment flags:** `recipeAgent`, `autoCareCenterAgent`, `events-shopping-planner`  
**Status:** All existing claims and parser based on this version

---

### V-2 · WebSocket API (v26.17.1) — Detected May 15, 2026
**Endpoint:** `wss://ws.apigw.us.walmart.com/sparky-agent-entry-point/live?agent_name=entry-point-agent&session_id=...&user_id=...`  
**Confidence:** `CONFIRMED` (one session observed)  
**Evidence:** WebSocket frames captured May 15, 2026  

**New schema — response arrives as sequential frames:**
| Frame type | `subType` / `messageType` | Content |
|-----------|--------------------------|---------|
| Connection ack | `ack_connection_established` | "Ready to receive audio and text" |
| Query sent | `input-message` / `text` | URL-encoded query + `correlationId` |
| COT step | `unified_response` / `COT` | Reasoning step text (streamed, 1–3 steps) |
| Text response | `unified_response` / `TEXT` | HTML preamble |
| Product carousel | `unified_response` / `PRODUCT_CAROUSEL` | Products — now dual carousel: "Sparky's Picks" + "Other Options" |
| Suggestion pills | `unified_response` / `TEXT_PILLS` | Clickable follow-up queries |
| Feedback | `unified_response` / `FEEDBACK` | Thumbs up/down prompt |
| End of stream | `unified_response` (empty `responses: []`) | Stream termination signal |

**Product card schema (v26.17.1) — key new fields vs. REST API:**
- `rationale` — AI-generated per-product justification string (e.g. "2025's most acclaimed RPG — innovative combat meets emotional depth"). Present on "Sparky's Picks" carousel only. Absent on "Other Options".
- `carouselTitle` — "Sparky's Picks" (primary) or "Other Options" (secondary). Two carousels now returned per response when `tabbedCarousel: "enabled"`.
- `type: "DYNAMIC"` — carousel generation mode
- `messageType: "search"` — on each card, indicates product sourced from search
- `badges.groupsV2[]` — rich badge structure including "Best seller" with style `HYPERBLUE_BOLD`
- `showAtc` / `showBuyNow` / `showOptions` — purchase action flags per card
- ⚠️ **`sellerId` NOT present** in card schema — cannot determine 1P/3P routing from WebSocket captures alone without additional resolution

**New experiment flags (not in v26.6.1):**
- `cot_enable: "true"` — Chain of Thought reasoning steps streamed to client
- `productDiscoveryAgent: "enabled"` — Dedicated product discovery agent
- `tabbedCarousel: "enabled"` — Products shown in tabbed UI
- `verticalCarousel: "enabled"` — Vertical scroll product format
- `epaPlanner: "enabled"` — Event/purchase planning agent
- `essentials-shopping-planner: "enabled"` — Essentials list planning
- `clientIntent: "client_intent_orchestrator"` — Multi-agent orchestration layer
- `uepReadyStateChips: "enabled"` — Controls suggestion chips shown at greeting screen before any query (observed May 15, capture 18)

**Key behavioral observations:**  
- Query "what kind of truck did Sam Walton drive" (trivia) → response served F-150 accessories. Page context (`screen` in `appContextAttributes`) overrode the query content entirely.
- Greeting screen (capture 18, `clientIntent: client_uep_greeting_intent`) revealed personalized greeting (account name pulled) and greeting chip taxonomy:
  - `reorder_static_chip` — "Shop for my usual items" (order history personalization)
  - `recipe_static_chip` — "Give me recipe ideas for this week", "Show me what's for dinner tonight"
  - `seasonal_item_chip` — "Shop graduation gifts" ← **current seasonal context = Graduation (May 2026)**
  - `seasonal_event_chip` — "Plan a graduation party"
  - Implication: graduation context is active and may influence routing on ambiguous queries right now.

**`showAds: false` — consistent with A-1 ✅**

**What needs re-validation:** All routing claims (R-1 through R-9) were established on v26.6.1. Whether the 1P/3P binary routing, modifier hierarchy, and context stickiness behave identically in v26.17.1 is unknown. First priority for new captures.

---

## Change Log

| Date | Change | Triggered By |
|------|--------|-------------|
| May 15, 2026 | R-1 → CONTRADICTED on v26.17.1, K-1 → CONTRADICTED, A-3 added (post-click ads), OQ-13 partial answer — "cheap toddler shirts" returned 0% Garanimals, capture 26 | Capture 26 |
| May 15, 2026 | M-5 added (complaint escalation ladder, 4 levels), R-10 revised (COT step count = query complexity), M-4 note (bad programming ≠ M-4 trigger), captures 24–25 | Captures 24–25 |
| May 15, 2026 | R-10 revised (COT variable 1–4+ steps, new step types documented), K-5 context stickiness + cart pills + spoiler behavior noted, capture 23 | Capture 23 |
| May 15, 2026 | R-11 + K-5 added (quality-intent routing, dual carousel, rationale field), OQ-16 closed, 2nd vertical added (gaming), capture 22 | Capture 22 |
| May 15, 2026 | M-4 added (in-session self-reset for directed profanity), OQ-20 added, capture 21 | Capture 21 |
| May 15, 2026 | M-3 revised — complaint threshold documented (dismiss vs. escalate), capture 20 added | Capture 20 |
| May 15, 2026 | R-10 added (COT step count = routing signal), OQ-14 closed, M-3 corrected (COT does fire, truncated) | Capture 19 correction |
| May 15, 2026 | M-3 added (silent deflection of non-shopping complaints), OQ-19 added, capture count → 19 | Capture 19 |
| May 15, 2026 | Capture 18 (greeting screen) added: chip taxonomy, graduation seasonal context, personalized greeting, `uepReadyStateChips` flag, OQ-18 | Live WebSocket capture |
| May 15, 2026 | V-2 section added — new WebSocket API documented | Live capture observation |
| May 15, 2026 | OQ-13 through OQ-17 added | WebSocket API findings |
| May 15, 2026 | API version change warning added to header | WebSocket API findings |
| May 15, 2026 | Document created from 16 historical captures | Session reorganization |
| Mar 17, 2026 | R-5 confirmed (seasonal overrides value) | Capture 12 |
| Mar 17, 2026 | R-8 confirmed (deterministic routing) | Captures 12/13, 14/14b |
| Mar 17, 2026 | C-3 added (conversation title as routing signal) | Captures 14–16 |
| Mar 17, 2026 | E-5 added (item page sourcing for follow-ups) | Capture 15 |
