# Sparky System Mechanics

**Purpose:** Distilled knowledge about how Walmart's Sparky AI assistant works internally.

**Last Updated:** Mar 17, 2026

---

## Query Processing Pipeline

### 1. Query Reformulation Engine
**How it works:**
- Strips question words ("what are", "how do I", etc.)
- Preserves key modifiers (value terms, age indicators, category descriptors)
- Maintains conversation context across follow-ups
- Can add context from previous queries even when user tries to redirect

**Key behaviors:**
- "What are some cheap toddler shirts?" → "cheap toddler shirts"
- "Back to school clothes for preschooler" → "back to school clothes, preschooler"
- Follow-up inherits context: "I just want cute clothes" → "cute toddler clothes, **gift**" (gift added from previous query)

**Implication:** Once a conversation is classified (e.g., as "gift"), that context is sticky and hard to escape.

---

## Binary Routing System

### 2. 1P vs 3P Classification
**Core mechanism:** Sparky appears to use binary routing logic that classifies queries into two paths:

**Path A: 1P-Dominant Route**
- Triggers: Generic categories, value/price terms, basic needs
- Result: 80-100% Walmart.com (1P) products
- Examples: "cheap shirts", "affordable everyday", "best brands"

**Path B: 3P-Dominant Route**
- Triggers: Seasonal/event terms, gift context, novelty/personalized items, niche themes
- Result: 100% third-party marketplace sellers
- Examples: "back to school", "cute outfit for niece", "gift clothes"

**No middle ground observed:** Results are either 1P-heavy or 3P-exclusive. Mixed results (40-60% 1P) are rare and appear transitional.

### 3. Classification Triggers

**1P Route Triggers:**
- Value terms: "cheap", "affordable", "budget"
- Generic categories: "shirts", "pants", "clothes"
- Brand queries: "best brands at walmart"
- Basic modifiers: "everyday", "basic"

**3P Route Triggers:**
- Seasonal: "back to school", "halloween", "christmas"
- Gift context: "gift for niece", "cute outfit for"
- Novelty: Slogan tees, personalized items, relationship-specific
- Character-specific: (hypothesized, not yet tested)
- **"Best selling" modifier:** May trigger marketplace routing (anomaly observed)

**Edge case:** "Mix and match" appears to be a borderline category that gets mixed routing (40% 1P / 60% 3P).

---

## Response Mode System

### 4. Intent Classification
**Sparky uses different response modes based on detected intent:**

| Intent Type | Response Mode | Products? | Editorial? |
|-------------|---------------|-----------|------------|
| Product search | Product Carousel | Yes (5) | Minimal preamble/followup |
| Perception question | Editorial Only | No | Yes (Google-grounded) |
| Comparative brand | Deflection + Products | Yes (5) | Deflection message |
| Standard query | Product Carousel | Yes (5) | Standard template |

**Deflection mechanism:**
- Comparative queries ("which is better, X or Y?") trigger: "I can't make qualitative comparisons between brands..."
- But still shows products from both brands
- Protects Walmart from liability while maintaining utility

**Google-grounded responses:**
- "Why" questions about brand perception trigger external source lookup
- Uses reddit.com, thespruce.com, etc.
- Positions brands with specific framing (e.g., "affordable" vs "durable")

---

## Conversation Context Engine

### 5. Context Persistence
**How it works:**
- Each conversation has a unique `conversationId`
- Follow-up queries reference the same ID
- Query reformulation considers **all previous queries** in the conversation
- Context inheritance is automatic and difficult to override

**Observed behavior:**
- Query 1: "cute outfit for my niece" → Routes to 3P/gift path
- Query 2: "I don't need it about our relation, just cute clothes" → **Still routes to 3P/gift path**
- Reformulation: "cute toddler clothes, **gift**" ← "gift" added from context despite user clarification

**Implication:** Starting a new conversation may be necessary to escape unwanted routing.

---

## Technical Metadata

### 6. API Response Structure
**Consistent patterns observed:**

**Intent classification:**
- `open_dialog` - Standard product queries
- `client_uep_greeting_intent` - Initial greeting
- `informational_intent` - Editorial responses (hypothesized)
- `comparative_intent` - Brand comparisons (hypothesized)
- `out_of_domain_intent` - Content moderation trigger (conversation termination)

**Specificity:**
- All observed queries marked as `"specificity": "narrow"`
- Suggests Sparky considers these queries specific enough for targeted results

**Ads configuration:**
- `"max_ads": 4` across all queries
- Ads beacon present but no actual ads delivered in any observed capture
- Ads system appears inactive or suppressed in Sparky context

---

## API Schema & Key Fields

### 7. Request Schema (Important Fields)

**Conversation tracking:**
- `conversationId` - UUID tracking conversation thread across queries
  - Example: `"9256B492-477F-4C00-8144-AAA6A3CACF78"`
  - Persists across follow-ups, enables context inheritance
  - Reset on conversation termination

**Session tracking:**
- `sessionId` - UUID for user session
  - Example: `"A687FF02-B14E-42BD-A176-2406639DC523"`
  - Different from conversationId (session can contain multiple conversations)

**Query structure:**
- `message.query` - URL-encoded user input
  - Example: `"who%20sells%20affordable%20clothing%20for%20toddlers"`
- `message.type` - Always `"TEXT"` for typed queries

**Metadata flags:**
- `metadata.loginStatus` - `"LOGGED_IN"` or `"LOGGED_OUT"`
- `metadata.walmartPlusStatus` - `"EXPIRED"`, `"ACTIVE"`, or `"NONE"`
- `metadata.userInputType` - `"TEXT"` vs voice/other
- `metadata.greetingMessageGeneration` - `false` for queries, `true` for initial greeting
- `metadata.isAssociate` - Employee status flag
- `metadata.supportHtmlTags` - `true` enables rich editorial formatting

**Experiment flags:**
- `requestAttributes.experimentFlags.recipeAgent` - `"enabled"` (recipe search capability)
- `requestAttributes.experimentFlags.autoCareCenterAgent` - `"enabled"` (auto parts capability)
- `requestAttributes.experimentGroups.expKeyName` - `"events-shopping-planner"` (event planning feature)

**App context:**
- `appContextStack[].screen` - Current app screen (e.g., `"shop"`)
- `channelId` - Always `"SPARKY_ASSISTANT_IOS_APP"` for iOS app

### 8. Response Schema (Important Fields)

**Top-level classification:**
- `intentName` - Classified intent type
  - `"open_dialog"` - Standard product search
  - `"out_of_domain_intent"` - Inappropriate/unsupported query
- `responseType` - Response mode
  - `"TERMINAL"` - Conversation-ending response (can be normal or termination)
  - Other types not yet observed

**Response message structure:**
- `responseMessage.messageType` - Always `"SPARKY_ASSISTANT"`
- `responseMessage.rawResponse[]` - Array of product results
  - Empty array `[]` means no products (editorial-only or termination)
  - Each item contains `products[]` array with product details
- `responseMessage.preamble` - HTML-formatted editorial intro
- `responseMessage.shortText` - Plain text version of response

**Product data (within rawResponse[0]):**
- `products[]` - Array of product objects (typically 5 items)
- `products[].itemId` - Walmart item ID
- `products[].sellerId` - Seller identifier
  - `"0"` = Walmart.com (1P)
  - Other values = Third-party sellers (3P)
- `products[].badges[]` - Product badges
  - `"Best seller"`, `"Clearance"`, `"Rollback"`, etc.
- `products[].brand` - Brand name (e.g., `"Garanimals"`)
- `products[].position` - 1-indexed position in results

**Search metadata (within rawResponse[0]):**
- `searchQuery.query` - Reformulated search query
  - Shows how Sparky transformed user input
  - Example: `"cheap toddler shirts"` from `"what are some cheap toddler shirts?"`
- `searchQuery.cat_id` - Category ID assigned to query
- `searchQuery.specificity` - Query specificity (`"narrow"` observed)
- `totalProductCount` - Total products in result set (always 5 observed)

**Source attribution:**
- `responseMessage.sourcesResponse.itemPage` - Item page data used
- `responseMessage.sourcesResponse.google` - Google web search results
  - `google.text` - Generated response text
  - `google.sources[]` - Array of web sources (URLs, domains)
  - `google.searchSuggestions[]` - Related search suggestions
- `responseMessage.sourcesResponse.reviews` - Customer review data

**Interaction metadata:**
- `responseMessage.displayFeedback` - Whether to show thumbs up/down
- `responseMessage.interactionBar.sources[]` - Source attribution for UI
  - `type`: `"WALMART"`, `"OTHER_SOURCES"`
  - `name`: Domain name (e.g., `"reddit.com"`, `"babycenter.com"`)

**Conversation metadata:**
- `entities.converseConversationTitle[]` - Auto-generated conversation title
  - Example: `"Affordable Toddler Clothing"` → `"Toddler Clothing Gift Ideas"` → `"Toddler Clothing Reviews"`
  - Updates based on conversation evolution
- `entities.response[]` - Copy of main response text
- `entities.ItemPageResponse[]` - Item page sourced responses
- `entities.GoogleResponse[]` - Google web search sourced responses

**Fallback classification (content moderation):**
- `entities.fallbackCategory` - `"inappropriate"` for terminated conversations
- Triggers conversation reset when present

### 9. Key Schema Patterns

**Product search response:**
```
intentName: "open_dialog"
responseType: "TERMINAL"
rawResponse: [{ products: [...5 items...], searchQuery: {...} }]
preamble: "<p>Here are a few...</p>"
```

**Editorial-only response (item page):**
```
intentName: "open_dialog"
responseType: "TERMINAL"
rawResponse: []
sourcesResponse.itemPage.text: "According to the item page..."
```

**Editorial-only response (Google):**
```
intentName: "open_dialog"
responseType: "TERMINAL"
rawResponse: []
sourcesResponse.google.text: "..."
sourcesResponse.google.sources: [{url, name, type}...]
```

**Content moderation termination:**
```
intentName: "out_of_domain_intent"
responseType: "TERMINAL"
rawResponse: []
entities.fallbackCategory: "inappropriate"
shortText: "I can't help with that..."
```

---

## Product Selection Logic

### 7. Ranking & Positioning
**Observed patterns:**

**Badge distribution:**
- 1P-dominant results: High "Best Seller" badge frequency
- 3P-dominant results: Mixed badges (Best Seller, Clearance, or none)
- Badges appear to reflect actual marketplace data, not promotional placement

**Position patterns:**
- Products appear in consistent 5-item carousels
- No variation in result count observed
- Top positions (1-3) appear to be algorithmically ranked
- No evidence of manual curation

**Seller diversity:**
- 3P results often show multiple sellers (not dominated by single seller)
- Chinese marketplace sellers common in 3P routes
- Brand sellers (PatPat, Inktastic) appear in novelty/gift categories

---

## Editorial Content System

### 8. Template Patterns
**Standard preamble:**
> "Here are a few [product type] that you might like. Keep in mind that the product info here comes from manufacturers and suppliers and I can't necessarily verify it:"

**Follow-up questions:**
- Always asks clarifying questions
- Common patterns: "Are you looking for specific sizes or colors?", "specific season or activity?"
- Appears to be template-based, not contextually generated

**Brand mentions:**
- Inconsistent - sometimes brands mentioned in editorial, sometimes not
- No clear pattern for when brands appear in preamble vs. just in products

---

## Content Moderation System

### 9. Conversation Termination
**Sparky has a safety system that terminates conversations deemed inappropriate.**

**Trigger mechanism:**
- Intent classification: `out_of_domain_intent`
- Fallback category: `inappropriate`
- Response type: `TERMINAL`

**Termination behavior:**
- Conversation forcibly reset (conversationId invalidated)
- No products shown (`rawResponse: []`)
- Standard message: "I can't help with that, but I can answer most shopping-related questions. I'm clearing our conversation so that we can start over."

**Observed trigger:**
- Query: "that looks like cheap chinese crap"
- Context: Follow-up in ongoing conversation about gift clothes
- Likely flagged for: Racial/ethnic language + negative sentiment

**Implications:**
- Sparky monitors for inappropriate content throughout conversation
- Termination is immediate and non-negotiable
- User must start fresh conversation (cannot continue)
- No warning system - straight to termination

**Unknown boundaries:**
- What other terms/phrases trigger termination?
- Is context considered (e.g., "chinese food" vs "chinese crap")?
- Are there warning levels before termination?
- Does user history affect sensitivity threshold?

---

## Key Unknowns & Hypotheses

### 10. Open Questions

**Routing logic:**
- What's the exact threshold between 1P and 3P routing?
- Is "best selling" a special modifier that always triggers 3P?
- Can explicit "walmart brand" requests override 3P routing?

**Context management:**
- Can conversation context be reset mid-conversation?
- How long does context persist?
- Are there keywords that force context reset?

**Product selection:**
- How are the specific 5 products chosen within each route?
- Is there personalization based on user history?
- What determines product ranking within results?

**Anomalies to investigate:**
- Why did "best selling rompers" route to 100% 3P when rompers is a generic category?
- Is "rompers" actually a specialty category in Walmart's taxonomy?
- Does "best selling" always mean "show actual marketplace leaders" (which may be 3P)?

## Routing Hierarchy (Priority Order)

**Critical finding (Capture #12):** When queries contain multiple triggers, Sparky follows strict priority:

1. **Seasonal/Event terms** → Forces 3P route (highest priority)
2. **Gift/Novelty context** → Forces 3P route
3. **Value/Price terms** → Favors 1P route (lowest priority)

**Proof:**
- "Affordable everyday toddler clothes" → 80% 1P, 40% Garanimals ✅
- "Affordable fall fashion for 4 year old" → 0% 1P, 0% Garanimals ❌

**Implication:** Seasonal modifiers override value terms. "Affordable" cannot rescue a "fall fashion" query from 3P routing.

