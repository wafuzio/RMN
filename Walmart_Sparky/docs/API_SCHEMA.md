# Walmart Sparky API Schema — Reverse-Engineered from HTTP Catcher

**Date:** March 16, 2026
**Capture Method:** HTTP Catcher (iOS on-device proxy) via Walmart iOS app v26.6.1
**Endpoint:** `POST https://www.walmart.com/api-proxy/service/iot/converse-adapter/v1/talk/sparky_assistant`

---

## Key Discovery: Sparky's Architecture

Sparky is not a custom Walmart LLM. It is a wrapper around **Google Vertex AI Search** (grounding API) combined with **Walmart's internal product search**. The converse-adapter service routes queries to one of three response modes based on detected intent:

- **Product Intent** → Walmart search engine → product carousel + generic editorial wrapper (no Google grounding)
- **Informational Intent** → Google Vertex AI grounding → editorial text with cited sources (no products)
- **Comparative Deflection** → When asked to compare brands head-to-head, Sparky treats it as product intent, returns interleaved products from both brands, and refuses to make qualitative editorial judgments

This means Sparky's editorial responses are influenced by the same web content that Google's search indexes, while product responses are driven by Walmart's catalog ranking. Critically, Sparky avoids making brand-vs-brand qualitative comparisons — it deflects to showing products side by side instead.

---

## Request Schema

### Endpoint
```
POST https://www.walmart.com/api-proxy/service/iot/converse-adapter/v1/talk/sparky_assistant
Content-Type: application/json
```

### Request Body
```json
{
  "channelId": "SPARKY_ASSISTANT_IOS_APP",
  "verticalId": "sparky_assistant",
  "conversationId": "<UUID — persistent across turns, new UUID for new conversation>",
  "message": {
    "query": "<URL-encoded query text>",
    "type": "TEXT"
  },
  "metadata": {
    "client": "IOS",
    "sessionId": "<UUID>",
    "loginStatus": "LOGGED_IN",
    "walmartPlusStatus": "EXPIRED",
    "isAssociate": false,
    "greetingMessageGeneration": false,
    "userInputType": "TEXT",
    "showAds": false,
    "isUEPClick": false,
    "supportHtmlTags": true
  },
  "appContextStack": [
    { "screen": "shop" }
  ],
  "requestAttributes": {
    "saveQuery": true,
    "experimentFlags": {
      "autoCareCenterAgent": "enabled",
      "recipeAgent": "enabled"
    },
    "experimentGroups": {
      "expName": "enabled",
      "expKeyName": "events-shopping-planner"
    }
  }
}
```

### Critical Request Headers
| Header | Value | Notes |
|--------|-------|-------|
| `CHANNEL_ID` | `SPARKY_ASSISTANT_IOS_APP` | Identifies Sparky channel |
| `WM_SVC.NAME` | `IOT-CONVERSE-ADAPTER` | Backend service name |
| `tenant-id` | `elh9ie` | Fixed tenant identifier |
| `WM_CONSUMER.ID` | `d37f3820-d41b-4106-9028-43141ec13b11` | Consumer app ID |
| `x-o-platform` | `ios` | Platform identifier |
| `x-o-mart` | `B2C` | Business channel |
| `X-PX-AUTHORIZATION` | `<rotating token>` | PerimeterX bot detection — rotates per request |
| `X-PX-DEVICE-FP` | `<device fingerprint>` | PerimeterX device fingerprint |
| `X-PX-UUID` | `<UUID>` | PerimeterX session UUID |
| `X-PX-VID` | `<visitor ID>` | PerimeterX visitor ID |
| `SPID` | `<session token>` | Session/auth token |
| `auth` | `<auth cookie>` | Authentication cookie (URL-encoded) |

**Bot Detection:** PerimeterX v3 with mobile SDK (v3.2.6). The `X-PX-AUTHORIZATION` header rotates per request, making direct API replay non-trivial without the PX mobile SDK token generation.

---

## Response Schema

### Response Mode 1: Product Intent (Product Carousel)

Triggered by shopping/product queries (e.g., "what are the best kids clothing brands at Walmart").

```json
{
  "intentName": "open_dialog",
  "responseType": "TERMINAL",
  "entities": {
    "preamble": ["<intro text>"],
    "followup": ["<follow-up text with clarifying question>"],
    "response": ["<full response including product list as text>"],
    "searchQuery": ["<reformulated search query>"],
    "products": ["<JSON-encoded product objects>"],
    "adsBeacon": ["<JSON-encoded ad targeting data>"],
    "converseConversationTitle": ["<generated conversation title>"]
  },
  "responseMessage": {
    "messageType": "SPARKY_ASSISTANT",
    "shortText": "<full text including product names, prices, ratings>",
    "preamble": "<HTML intro>",
    "followup": "<HTML follow-up>",
    "rawResponse": [{
      "title": "<query title>",
      "query": "<original query>",
      "products": [
        {
          "name": "<product name>",
          "id": "<product ID>",
          "usItemId": "<Walmart item ID>",
          "offerId": "<offer ID>",
          "image": "<image URL>",
          "sellerName": "Walmart.com",
          "price": 6.98,
          "priceInfo": {
            "linePrice": "$6.98",
            "linePriceDisplay": "$6.98"
          },
          "rating": {
            "numberOfReviews": 214,
            "averageRating": 4.8
          },
          "showAtc": true,
          "badges": {
            "groupsV2": [{
              "name": "flags",
              "members": [{
                "content": [{ "value": "Best seller" }]
              }]
            }]
          },
          "messageType": "search",
          "isOutOfStock": false,
          "orderLimitV2": 58.0,
          "arEnabled": false
        }
      ],
      "hasAds": false,
      "additionalCards": [{
        "type": "VIEW_ALL",
        "link": {
          "url": "https://www.walmart.com/search?q=...",
          "label": "See more items"
        }
      }]
    }],
    "displayFeedback": true,
    "sourcesResponse": {
      "google": { "sources": [], "searchSuggestions": [] }
    }
  },
  "unifiedResponse": {
    "locale": "en",
    "responses": [
      { "messageType": "TEXT", "payload": { "message": { "text": "<preamble HTML>" } } },
      { "messageType": "PRODUCT_CAROUSEL", "payload": { "cards": ["<product cards>"] } },
      { "messageType": "TEXT", "payload": { "message": { "text": "<followup HTML>" } } }
    ]
  }
}
```

**Rendering Order:** `unifiedResponseOrderedList: ["preamble", "products", "followup"]`

### Response Mode 2: Informational Intent (Google-Grounded Editorial)

Triggered by informational/opinion queries (e.g., "How is Garanimals' reputation for quality?").

```json
{
  "intentName": "open_dialog",
  "responseType": "TERMINAL",
  "entities": {
    "response": ["<editorial text>"],
    "GoogleSource": ["<JSON-encoded source objects with text attribution indices>"],
    "GoogleSearchSuggestions": ["<follow-up query suggestions>"],
    "converseConversationTitle": ["<generated title>"]
  },
  "responseMessage": {
    "messageType": "SPARKY_ASSISTANT",
    "shortText": "<plain text response>",
    "preamble": "<HTML response>",
    "rawResponse": [],
    "displayFeedback": true,
    "sourcesResponse": {
      "google": {
        "sources": [
          {
            "url": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/...",
            "name": null,
            "type": null
          }
        ],
        "searchSuggestions": [
          "Garanimals brand reputation for quality children's clothing"
        ]
      }
    },
    "interactionBar": {
      "sources": [
        {
          "url": "<grounding redirect URL>",
          "name": "babycenter.com",
          "type": "OTHER_SOURCES",
          "logoUrl": "https://www.google.com/s2/favicons?domain=babycenter.com",
          "headline": "babycenter.com"
        }
      ]
    }
  },
  "unifiedResponse": {
    "locale": "en",
    "responses": [
      { "messageType": "TEXT", "payload": { "message": { "text": "<full HTML response>" } } }
    ]
  }
}
```

**Google Source Attribution Detail:**
Each `GoogleSource` entry contains `textIndices` mapping exact character ranges in the response to their grounding source:
```json
{
  "url": "<vertex AI redirect>",
  "title": "babycenter.com",
  "id": 5,
  "textIndices": [{"startIndex": 161, "endIndex": 510}],
  "domain": "babycenter.com"
}
```

---

## Ad Infrastructure

Sparky has a built-in advertising layer. The `adsBeacon` entity contains:

```json
{
  "adUuid": "<UUID>",
  "moduleInfo": {
    "sparky": true,
    "specificity": "narrow",
    "engagementTraffic": "tail",
    "sessionTraffic": "tail",
    "brands": ["Walmart"],
    "rqs": ["T-Shirts best kids clothing brands,"],
    "dc": "eus2"
  },
  "max_ads": 4,
  "adSlots": []
}
```

In captured queries, `max_ads: 4` with empty `adSlots` — ads are plumbed but not yet serving on these queries. This is a significant finding: **Walmart is preparing (or already running) sponsored placements inside Sparky responses.**

---

## Captured Query Results

### Query 1: "what are the best kids clothing brands at Walmart?" (Cold Start, Product Intent)

**Response Mode:** Product Carousel
**Products Returned (5):**

| Position | Product | Brand | Price | Rating | Badge |
|----------|---------|-------|-------|--------|-------|
| 1 | St. Patrick's Day Lucky Charms Graphic Tee | Licensed/Seasonal | $6.98 | 4.8 (214 reviews) | Best seller |
| 2 | Baby & Toddler Girl Cotton 6-Piece Outfit Sets | **Garanimals** | $16.79 | 4.6 (0 reviews*) | Best seller |
| 3 | Spiderman Short Sleeve Hoodie & Shorts 2pc Set | Marvel/Licensed | $17.48 | 5.0 (null) | Best seller |
| 4 | Toddler Graphic Tee with Short Sleeves | Snoop Dogg/Licensed | $7.98 | 4.8 (null) | Best seller |
| 5 | Baby & Toddler Girl Cotton 2-Piece Set | **Garanimals** | $7.98 | 4.8 (null) | Best seller |

*New listing — rating display shows 0/null

**Editorial Content:** Generic wrapper only ("These options feature popular characters and versatile sets for kids"). No brand-level editorial or differentiation. No Google grounding sources.

**Key Insight:** Garanimals captures 40% of product slots (2/5) but receives zero editorial brand mention. The editorial text doesn't discuss brands at all — just generic product attributes.

### Query 2: "I noticed here that Garanimals didn't make the list of brands. How come?" (Follow-up, Informational Intent)

**Response Mode:** Google-Grounded Editorial
**Products Returned:** None

**Editorial Response:** "Garanimals is a brand known for its affordability and its mix-and-match designs... often compared to other value-oriented brands like Cat & Jack from Target, rather than being highlighted for exceptional, long-lasting durability..."

**Sources Cited (7):**

| Domain | Role in Response |
|--------|-----------------|
| thepennywisemama.com | Brand positioning, mix-and-match mention |
| garanimals.com | Brand description |
| worthpoint.com | Brand description |
| walmart.com | Quality/durability comparison |
| babycenter.com | Quality/durability comparison |
| reddit.com | Quality/durability comparison |
| vivaveltoro.com | Everyday wear positioning |

**Key Insight:** When pushed for editorial brand evaluation, Sparky positions Garanimals as "affordable everyday wear" and compares unfavorably to Cat & Jack on durability. The conversation title reveals prior context: "the brands I listed previously are often highlighted for exceptional durability and longevity, sometimes at a higher price point."

### Query 3: "which is better for toddlers, the children's place or garanimals" (Comparative, Product Intent — Deflection)

**Response Mode:** Product Carousel (comparative deflection — no editorial comparison made)
**Products Returned (5):**

| Position | Brand | Product | Price | Badge |
|----------|-------|---------|-------|-------|
| 1 | **Garanimals** | Cotton Short-Sleeve Solid T-Shirts, 3-Pack | $11.98 | Best seller |
| 2 | The Children's Place | Bunny Bow Flutter Dress | $21.48 (was $42.95) | Best seller |
| 3 | **Garanimals** | Lightweight Active Shorts, 4-Pack | $14.98 | Best seller |
| 4 | The Children's Place | Easter Print V-Waist Dress | $11.48 (was $22.95) | Best seller |
| 5 | **Garanimals** | Cotton Graphic Tank Tops, 4-Pack | $10.48 (was $14.98) | Best seller |

**Editorial Content:** "Every product has its pros and cons" ... "Each brand provides comfortable and durable clothing suitable for everyday wear." Complete refusal to differentiate. No Google grounding sources.

**Ad Infrastructure:** `max_ads: 8` (doubled from generic queries). `brands: ["Garanimals", "The Children's Place"]`. `specificity: "broad"`. Comparative queries are higher-value ad real estate to Walmart.

**Key Insights:**
- Sparky refuses to make qualitative brand comparisons — it interleaves products instead
- Garanimals takes 3/5 positions (60% share), all multi-pack value offerings
- TCP products show markdown pricing ("was $42.95"), Garanimals prices appear more stable
- The `searchQuery` reformulation was "The Children's Place vs Garanimals, toddlers" — Sparky reordered the brands alphabetically
- Walmart doubles the ad slot allocation for comparative queries (8 vs 4)

### Query 4: "what are the best selling toddlers rompers at walmart?" (Category-Specific Product Intent)

**Response Mode:** Product Carousel
**Products Returned (5):**

| Position | Brand | Product | Price | Seller | Badge |
|----------|-------|---------|-------|--------|-------|
| 1 | WRKEKC | Baby Girls Romper | $1.22 | Shenzhen 3P seller | Best seller |
| 2 | Busydd | Newborn Rompers | $3.49 | Shenzhen 3P seller | Clearance |
| 3 | John Deere | Henley Romper | $23.99 | imagikids (3P) | None |
| 4 | Odeerbi | Floral Jumpsuit | $4.99 | Shenzhen 3P seller | None |
| 5 | Girls Easter | Casual Rompers | $8.92 | Guangzhou 3P seller | None |

**Garanimals Presence: ZERO.** Not a single Garanimals product in a category (toddler rompers) where the brand should have strong representation. All 5 results are 3P marketplace sellers, 4 of which are from Chinese sellers.

**Key Insights:**
- Garanimals is completely absent from category-specific romper searches — a critical gap
- Sparky's product search heavily favors keyword-title matching; if Garanimals lists romper-equivalent products under different terminology ("one-piece," "jumpsuit," "outfit set"), they won't surface
- 3P marketplace products with SEO-stuffed titles dominate over 1P brands in niche category queries
- The `sellerName` field reveals seller origin (e.g., "shenzhenshixinyinbindianzishangwuyouxiangongsi") — useful for distinguishing 1P vs 3P results
- No "Best seller" badges on 3 of 5 products, yet they outrank Garanimals entirely

---

## Implications for Garanimals Strategy

1. **Product visibility is strong on generic queries** — 2/5 carousel slots on "best kids clothing brands," 3/5 on the TCP comparison. The product-level catalog presence is working for broad queries.

2. **Product visibility collapses on category-specific queries** — 0/5 on "toddler rompers." This suggests Garanimals' product titles and taxonomy don't match how customers search for specific product categories. Immediate PDP action: audit category keywords (romper, jumpsuit, one-piece, bodysuit, onesie) across all Garanimals product titles and descriptions.

3. **Editorial visibility is problematic** — Sparky's Google-grounded editorial never mentions Garanimals positively by name. When asked directly, it positions the brand as budget/everyday, not quality/durable.

4. **The durability perception gap is the #1 actionable issue.** Sparky's editorial (powered by Vertex AI) draws from web content where Garanimals is discussed in terms of affordability, not durability. The sources (babycenter, reddit, mommy blogs) frame it as a budget option compared to Cat & Jack.

5. **PDP optimization has two separate paths:**
   - Product carousel ranking: Optimize Walmart catalog fields (title, description, ratings, inventory signals, category taxonomy)
   - Editorial perception: Influence the web content that Google Vertex AI grounds on (garanimals.com content, earned media, review sites)

6. **3P marketplace sellers are cannibalizing Garanimals in niche categories.** Chinese 3P sellers with SEO-stuffed titles are outranking Garanimals in category-specific Sparky results. This is a Walmart catalog/search issue, not just an LLM issue — but it directly affects Sparky visibility.

7. **Ad placements are coming.** The `adsBeacon` infrastructure with `"sparky": true` means sponsored placements in Sparky responses are imminent or already testing. Comparative queries get 2x the ad slots (8 vs 4). The client should be monitoring this channel for competitor ad activity.

8. **Sparky refuses to make qualitative brand comparisons.** When asked "which is better," it deflects to product carousel. This means brand perception in Sparky is shaped almost entirely by (a) which products show up and in what order, and (b) follow-up informational queries that trigger Google grounding. There is no in-Sparky editorial differentiation on comparative queries.

9. **Cat & Jack (Target) is the primary competitive frame.** Sparky explicitly names them as the comparison brand for Garanimals in editorial responses. Any perception strategy needs to address this head-to-head.

10. **Price positioning is actually a strength in Sparky.** In the comparative query, Garanimals' multi-pack value pricing ($10-15 for 3-4 pieces) vs. TCP's marked-down single items ($11-21, with "was" prices showing 50% discounts) tells a visual story of stable value vs. perpetual markdowns. This framing could be leveraged.

---

## Technical Notes for Automation

**Feasibility of Direct API Replay:** Low without significant effort. The PerimeterX `X-PX-AUTHORIZATION` header rotates per request and requires the PX mobile SDK to generate valid tokens. Session cookies also rotate. Direct `curl` replay of captured requests will work for a limited window (minutes to hours) before tokens expire.

**Recommended Approach:** Continue using HTTP Catcher on-device for manual capture sessions. Export captures as HAR files for automated parsing. For systematic longitudinal testing, consider:
- Scheduled manual capture sessions (weekly, using the Phase 0 probe template)
- HAR file parsing pipeline to extract and normalize response data
- Potential investigation of PX token generation for automated replay (significant reverse-engineering effort)

**Conversation Management:** Each conversation uses a UUID (`conversationId`). New conversation = new UUID. Follow-up queries within the same `conversationId` maintain context. For systematic testing, always use fresh `conversationId` per query to avoid context contamination.

---

## Investigation Roadmap

### Garanimals-Specific Investigations

**1. Branded Query Audit**
Test how Sparky responds to direct branded queries: "show me Garanimals toddler clothes," "Garanimals summer collection," "Garanimals mix and match sets." We only have data for queries where Garanimals is one of several possible answers. Need to understand what happens when Garanimals *is* the query — does it get product carousel, editorial, or both? Does the editorial frame it positively when the user is already expressing purchase intent for the brand?

**2. Category Keyword Gap Analysis**
The romper query exposed a critical gap. Systematically test every product category Garanimals sells in: pajamas, swimwear, shorts, leggings, dresses, outfits, sets, bodysuits, onesies, jumpsuits, overalls. For each, test both the generic term and common synonyms/variants customers actually search. Map which categories Garanimals surfaces in and which it's invisible. This directly informs PDP title and taxonomy fixes.

**3. Durability/Quality Perception Probing**
Push harder on the editorial perception vector. Queries like "are Garanimals clothes good quality," "do Garanimals clothes hold up in the wash," "Garanimals reviews." The single editorial capture we have frames Garanimals unfavorably on durability vs. Cat & Jack. Need to know if that's consistent or if different phrasings trigger different source material from the Vertex AI grounding layer.

**4. Seasonal and Promotional Visibility**
Test time-sensitive queries: "back to school toddler clothes walmart," "Easter toddler outfits," "summer clothes for kids." Garanimals has strong seasonal collections — do they surface when shoppers are looking for seasonal products, or do higher-priced brands dominate seasonal intent?

**5. Mix-and-Match Specific Queries**
Mix-and-match is Garanimals' core brand differentiator. Test "mix and match kids clothes," "coordinating toddler outfits," "kids clothes that go together." If Sparky doesn't surface Garanimals for these queries, that's a significant missed opportunity and a clear content/SEO gap to fix.

**6. Editorial Source Influence Mapping**
Across all editorial responses, catalog which web domains Sparky's Vertex AI grounding cites as sources. Build a map of which sites shape Garanimals' brand narrative in Sparky. This becomes the target list for earned media and content strategy — if babycenter and reddit are driving the "cheap but not durable" narrative, that's where perception needs to shift.

**7. Price Threshold Behavior**
Test queries with explicit price constraints: "toddler clothes under $10," "cheap kids clothing walmart," "affordable toddler outfits." Garanimals should own budget-intent queries. If it doesn't, that's a ranking problem. If it does, document the framing to understand whether budget positioning helps or hurts in Sparky's editorial layer.

### General Sparky Datamining Investigations

**8. Response Mode Trigger Mapping**
We've identified three response modes but don't have a reliable model for what triggers each one. Systematically vary query phrasing across the same underlying intent to isolate triggers. "Best kids clothes at walmart" (product) vs. "what are the best kids clothing brands at walmart" (editorial) vs. "which kids clothing brand is best" (deflection?) — find the grammar/syntax patterns that push Sparky into each mode. This is foundational for anyone trying to optimize for Sparky visibility.

**9. `searchQuery` Reformulation Patterns**
Sparky reformulates user queries before passing them to Walmart's search engine (e.g., "which is better for toddlers, the children's place or garanimals" becomes "The Children's Place vs Garanimals, toddlers"). Capture enough examples to understand the reformulation logic. This reveals what Sparky actually searches for vs. what the user typed — critical for PDP keyword optimization.

**10. Conversation Context Influence**
Test multi-turn conversations where the first query establishes context and the second asks for recommendations. Does "I'm shopping for my 3-year-old daughter" followed by "what clothes should I get" produce different results than the cold query "toddler girl clothes walmart"? If conversation history influences product ranking, that changes the optimization model entirely.

**11. `experimentFlags` and A/B Testing Detection**
The captured requests include an empty `experimentFlags` array in the metadata. Monitor this across sessions — when Walmart runs A/B tests on Sparky (new response formats, different ad placements, model changes), these flags likely light up. Detecting when experiments are active is critical for avoiding noisy data in longitudinal studies.

**12. Logged-In vs. Logged-Out Behavior**
Current captures are all `loginStatus: "LOGGED_IN"` with `walmartPlusStatus: "EXPIRED"`. Test with a logged-out session, a fresh account with no purchase history, and an active Walmart+ account. If Sparky personalizes recommendations based on purchase history or membership status, the same query will produce different results for different user profiles — and optimization strategies need to account for that.

**13. Ad Slot Activation Monitoring**
The `adsBeacon` with `"sparky": true` and `showAds: false` in our captures suggests the ad system exists but wasn't active during our session. Need to monitor this over time — when `showAds` flips to `true`, what changes in the response? Do sponsored products get injected into the carousel? Do they get a distinct badge? Does the editorial content shift? This is the single biggest commercial signal to watch.

**14. Geographic and Store-Level Variation**
Sparky likely incorporates store inventory and regional product availability. Test from different zip codes (or with different store selections in the Walmart app) to see if product carousel results change based on local inventory. If they do, Garanimals' visibility is partly a supply chain and distribution question, not just a content optimization one.

**15. Time-Based Variation**
Run the same set of queries at different times of day and different days of the week. Product carousels may be influenced by real-time inventory signals, trending searches, or Walmart's demand forecasting. Establishing a baseline for temporal variation is necessary before any before/after measurement of optimization efforts can be meaningful.

**16. Response Token and Latency Profiling**
Measure response times and payload sizes across query types. Editorial responses (Vertex AI grounding) likely have different latency profiles than product carousels (Walmart search). Understanding the performance characteristics helps predict which response mode Sparky is using before parsing the full response, and may reveal rate limiting or throttling patterns relevant to systematic testing.

---

## Capture Protocol (HTTP Catcher)

For repeatable data collection sessions:

1. Force-close the Walmart app before each session
2. Open HTTP Catcher, enable capture with SSL Pinning Bypass
3. Launch Walmart app, wait for startup traffic to settle
4. Navigate to Sparky, ensure fresh `conversationId` per query
5. Submit query, wait for full response
6. Export capture (HAR format preferred) before moving to next query
7. If SSL capture drops to `443 CONNECT` only, force-close Walmart app and repeat from step 3

**Known Issue:** Intermittent SSL capture loss — Walmart app sometimes reverts to opaque CONNECT tunnels. Force-closing and relaunching the app resolves it, but the trigger is not consistently reproducible. May be related to app-level certificate rotation or PerimeterX SDK re-initialization.
