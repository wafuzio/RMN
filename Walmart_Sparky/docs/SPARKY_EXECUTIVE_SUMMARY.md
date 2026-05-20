# Sparky AI Assistant - Executive Summary for SEO/Search Professionals

**Audience:** Search engine optimization and product search professionals  
**Focus:** How Walmart's conversational AI assistant routes and ranks product queries  
**Date:** Mar 17, 2026

---

## What is Sparky?

Walmart's conversational shopping assistant that processes natural language queries and returns product recommendations. Think of it as Walmart's answer to Amazon's Alexa shopping or Google Shopping Assistant - but with unique routing logic that significantly impacts product visibility.

---

## The Core Discovery: Binary Routing System

**Sparky doesn't blend results - it routes queries to one of two distinct paths:**

### Path 1: Walmart.com (1P) Route
- **Triggers:** Value terms ("cheap", "affordable"), generic categories ("shirts", "pants"), basic needs
- **Result:** 80-100% Walmart.com products
- **Brand visibility:** High Garanimals presence (20-40% of results)
- **Example:** "affordable clothing for toddlers" → 80% 1P, 20% Garanimals

### Path 2: Marketplace (3P) Route  
- **Triggers:** Seasonal terms ("back to school", "fall fashion"), gift context, novelty items
- **Result:** 100% third-party marketplace sellers
- **Brand visibility:** Zero Garanimals, zero Walmart brands
- **Example:** "back to school clothes for preschooler" → 100% 3P, 0% Garanimals

**SEO Implication:** There's no "ranking up" from position 6 to position 1 if you're on the wrong path. The routing decision determines whether Walmart brands appear at all.

---

## Routing Hierarchy (Critical for Query Optimization)

When queries contain multiple triggers, Sparky follows strict priority:

1. **Seasonal/Event terms** (highest priority) → Forces 3P route
2. **Gift/Novelty context** → Forces 3P route  
3. **Value/Price terms** (lowest priority) → Favors 1P route

**Real-world proof:**
- "Affordable everyday toddler clothes" → 80% 1P ✅
- "Affordable fall fashion for 4 year old" → 0% 1P ❌

**The word "fall" overrides "affordable"** - seasonal modifiers trump value terms.

---

## Query Reformulation Engine

Sparky doesn't search your exact words - it reformulates queries:

**What it does:**
- Strips question words: "What are some cheap shirts?" → "cheap shirts"
- Preserves modifiers: "affordable", "toddler", "back to school"
- Adds conversation context automatically

**SEO Impact:**
- Your product titles/descriptions should match reformulated queries, not natural language
- Focus on modifier combinations: "affordable toddler clothes" not "What are affordable options for toddler clothing?"

---

## Conversation Context is Sticky

**Critical finding:** Once a conversation is classified (e.g., as "gift shopping"), that context persists across follow-ups.

**Example conversation:**
1. User: "cute outfit for my niece" → Routes to 3P (gift context)
2. User: "I don't need it about our relation, just cute clothes" → **Still routes to 3P**
3. Sparky reformulates as: "cute toddler clothes, **gift**" ← Added from context

**Implication:** Users can't easily escape routing decisions mid-conversation. Starting a new conversation may be necessary to change paths.

---

## Product Visibility Patterns

### Garanimals Case Study (Walmart's Value Brand)

**Perfect correlation discovered:**
- **1P-dominant results:** Garanimals appears 20-40% of the time, always in top 3 positions
- **3P-dominant results:** Garanimals appears 0% of the time

**Position stability:**
- When Garanimals appears on value queries, it locks position #1 (100% stable across repeat queries)
- 80% product overlap on identical queries (minor shuffling in positions 2-5)

**What this means:**
- Garanimals visibility is binary: either prominently featured or completely absent
- Depends entirely on routing path, not on product ranking within path
- Value-oriented queries are the only path to visibility

---

## Response Modes & Data Sources

Sparky uses different response modes based on query type:

### 1. Product Carousel (Standard)
- 5 products shown
- Preamble + product cards + follow-up question
- Most common mode

### 2. Editorial Only (Follow-ups)
- No new products shown
- References products from earlier in conversation
- Uses multiple data sources:
  - **Item page data:** Product specs, descriptions
  - **Google web search:** External reviews (reddit, babycenter, etc.)
  - **Customer reviews:** Walmart review data

### 3. Deflection + Products
- Comparative queries: "Which is better, X or Y?"
- Shows products but adds disclaimer: "I can't make qualitative comparisons between brands..."
- Protects Walmart from liability while maintaining utility

### 4. Content Moderation
- Inappropriate queries trigger conversation termination
- Conversation forcibly reset, must start fresh
- No warning system - immediate termination

---

## Technical Metadata (For API/Data Analysis)

**Key schema fields to track:**

**Request side:**
- `conversationId` - Tracks conversation thread (enables context persistence)
- `message.query` - URL-encoded user input
- `metadata.loginStatus` - Logged in vs. guest (may affect personalization)

**Response side:**
- `sellerId: "0"` = Walmart.com (1P)
- `sellerId: [other]` = Third-party (3P)
- `rawResponse: []` = No products (editorial-only or termination)
- `searchQuery.query` - Shows reformulated query
- `entities.converseConversationTitle` - Auto-generated conversation title (shows evolution)

**Response patterns:**
- `intentName: "open_dialog"` + `rawResponse: [...]` = Product search
- `intentName: "open_dialog"` + `rawResponse: []` = Editorial follow-up
- `intentName: "out_of_domain_intent"` = Content moderation trigger

---

## Optimization Strategies

### For Walmart Brands (1P Products):

**✅ DO:**
- Target value-oriented queries: "affordable", "cheap", "budget", "best value"
- Use generic category terms: "toddler clothes", "kids shirts", "everyday basics"
- Avoid seasonal modifiers that trigger 3P routing
- Optimize for reformulated queries (stripped of question words)

**❌ AVOID:**
- Seasonal terms: "back to school", "fall fashion", "halloween", "christmas"
- Gift context: "gift for niece", "present ideas"
- Novelty positioning: "cute outfit for", "special occasion"
- "Best selling" modifier (may trigger marketplace routing)

### For Marketplace Sellers (3P):

**✅ DO:**
- Target seasonal/event queries: "back to school", "holiday outfits"
- Use gift context: "gift for toddler", "birthday outfit"
- Emphasize novelty/uniqueness: "personalized", "custom", "unique designs"
- Leverage character/theme associations (hypothesized)

**❌ AVOID:**
- Generic value positioning (will route to 1P)
- Competing on "affordable" or "cheap" (1P territory)

---

## Open Questions & Testing Opportunities

1. **Does login status affect routing?** (Logged in vs. guest)
2. **Is there personalization based on purchase history?**
3. **What's the exact threshold between 1P and 3P routing?**
4. **Does "best selling" always trigger 3P route?** (Anomaly observed)
5. **Can explicit "Walmart brand" requests override 3P routing?**
6. **How long does conversation context persist?**
7. **Are there keywords that force context reset mid-conversation?**

---

## Dataset Summary

**16 captures analyzed:**
- 13 product search queries
- 3 editorial-only follow-ups
- 1 content moderation termination
- Multiple repeat queries to test consistency

**Key queries tested:**
- Value terms: "cheap", "affordable", "budget"
- Seasonal: "back to school", "fall fashion"
- Gift context: "gift for niece", "cute outfit for"
- Generic: "toddler clothes", "rompers", "shirts"
- Comparative: "Garanimals vs Carter's"

---

## Bottom Line for SEO/Search Professionals

**Traditional search ranking doesn't apply here.** Sparky uses a binary routing system where:

1. **Query classification determines product pool** (1P vs 3P)
2. **Ranking happens within the selected pool** (not across all products)
3. **Conversation context is sticky** (hard to escape initial classification)
4. **Modifier hierarchy matters** (seasonal > gift > value)

**For product visibility:** Being in the right routing path matters more than ranking position. A #1 position in the wrong path = 0 visibility.

**For query optimization:** Focus on trigger words that route to your desired path, not just relevance scoring.

**For competitive analysis:** Track which queries route to 1P vs 3P, not just which products rank where.
