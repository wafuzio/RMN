# Retailer House Ads - System Behavior

## What Are Retailer House Ads?

**Retailer house ads** are marketing materials from the retailer itself (not actual brand advertisements). They promote the retailer's own products, services, or general promotions.

Supported retailers:
- **Kroger** - Kroger house ads
- **Walmart** - Walmart house ads  
- **Instacart** - Instacart house ads

Examples:
- "Delicious looking glazed ham on a holiday platter..."
- "Spend $25, Save $5"
- "Save $1 on Snacks"
- "Bakery Fresh Bite Sized Treats. Shop Now."

## How They're Identified

### 1. Message Text Matching (Primary Method)
- Retailer house ads have **exact, repeating message text**
- These messages are stored in `config/brands.json` with `MSG:` prefix
- Example: `"MSG:Delicious looking glazed ham on a holiday platter. Shown on a red background with a string of lights."`

### 2. Brand Assignment
- When matched, these ads are automatically assigned the retailer name as brand:
  - Kroger ads → `"Kroger"`
  - Walmart ads → `"Walmart"`
  - Instacart ads → `"Instacart"`
- This happens in two places:
  - **During scraping**: `canonicalize()` function in `core/brands.py`
  - **In brand review tool**: `match_message_to_lexicon()` in `brand_review_tool.py`

## System Behavior

### ✅ What DOES Happen:
1. **Auto-skip in Brand Review Tool**
   - Ads with matching message text are automatically skipped
   - No manual review needed
   - Prints: `"✓ Auto-skipping ad with known message: '...' -> [Retailer]"`
   - Dynamic button shows "Mark as Kroger House Ad" or "Mark as Walmart House Ad" based on retailer

2. **Filtered from API/Frontend**
   - `BLOCKED_BRANDS` list includes `"kroger"`, `"walmart"`, `"instacart"`
   - API removes these from advertiser arrays
   - Frontend never displays them

3. **Excluded from Analysis**
   - Not counted in brand performance metrics
   - Not included in ad counts
   - Not shown in brand lists

### ❌ What DOES NOT Happen:
- These are **NOT** used for brand extraction
- They do **NOT** appear in the frontend
- They do **NOT** count toward advertiser metrics

## Key Distinction

### Kroger House Ads (Message Matching)
- **Purpose**: Identify retailer marketing to exclude
- **Method**: Exact message text matching
- **Result**: Auto-skip, filter out, don't count
- **Example**: "Spend $25, Save $5" → Kroger → Excluded

### Real Brand Ads (Brand Extraction)
- **Purpose**: Identify actual advertisers
- **Method**: Brand name extraction (canonicalize)
- **Result**: Keep for analysis, count metrics
- **Example**: "Shop Muscle Milk Now" → Muscle Milk → Included

## Code Locations

### Brand Review Tool
- **File**: `brand_review_tool.py`
- **Function**: `match_message_to_lexicon()` (lines 282-309)
- **Behavior**: Auto-skips ads with matching message text

### API Filtering
- **File**: `web/builder_server_v2.py`
- **Constant**: `BLOCKED_BRANDS` (line 245)
- **Function**: `is_blocked_brand()` (lines 294-302)
- **Behavior**: Filters out from advertiser arrays

### Brand Extraction
- **File**: `core/brands.py`
- **Function**: `canonicalize()` (lines 40-80)
- **Behavior**: Extracts brand names from text

## Adding New Kroger House Ads

When you find a new repeating Kroger house ad message:

1. Open `config/brands.json`
2. Find the "Kroger" brand entry
3. Add the message to synonyms with `MSG:` prefix:
   ```json
   {
     "name": "Kroger",
     "synonyms": [
       "MSG:Your new message here"
     ]
   }
   ```
4. The system will automatically:
   - Skip it in brand review tool
   - Filter it from API
   - Exclude it from counts

## Testing

To verify a message will be auto-skipped:

```python
from core.brands import canonicalize

message = "Your test message here"
result = canonicalize(message)
print(f"Matched: {result}")  # Should print "Kroger" if in lexicon
```
