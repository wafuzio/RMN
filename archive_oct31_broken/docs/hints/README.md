# Ad Type Hint Packs

This directory contains Ad Type Hint Packs - YAML files that define the single source of truth for each retailer's ad types, selectors, and extraction logic.

## Quick Start

### 1. Create a Hint Pack
```bash
# Copy template
cp HINT_PACK_TEMPLATE.yaml newretailer_ad_types.yaml

# Edit with your retailer's details
vim newretailer_ad_types.yaml
```

### 2. Collect HTML Samples
```bash
# Create samples directory
mkdir -p newretailer/samples/

# Add HTML samples (manually or via profiler)
# Save as: {AdType}_1.html, {AdType}_2.html, etc.
```

### 3. Validate Selectors
```bash
python3 ../tools/selector_smoke_test.py newretailer_ad_types.yaml
```

### 4. Compose Adapter
```bash
python3 ../tools/compose_retailer.py --hint-pack newretailer_ad_types.yaml
```

## Directory Structure

```
docs/hints/
├── README.md                        # This file
├── HINT_PACK_TEMPLATE.yaml          # Template for new retailers
├── kroger_ad_types.yaml             # Kroger hint pack
├── walmart_ad_types.yaml            # Walmart hint pack (TODO)
├── kroger/
│   └── samples/
│       ├── TOA_1.html
│       ├── TOA_2.html
│       ├── Skyscraper_1.html
│       └── CuratedCarousel_1.html
└── newretailer/
    └── samples/
        └── ...
```

## Hint Pack Benefits

✅ **Explicit ad type definitions** - No guessing
✅ **Tested selectors** - Validated before composition
✅ **Brand extraction strategies** - Defined upfront
✅ **Production-ready code** - Minimal manual fixes
✅ **Single source of truth** - All ad logic in one place

## Workflow

### Traditional (Profiler Only)
1. Run profiler → guesses ad types
2. Compose adapter → generic selectors
3. Fix selectors manually → trial and error
4. Test → iterate

**Time:** ~2-3 hours

### With Hint Pack
1. Collect HTML samples → 15 min
2. Create hint pack → 15 min
3. Validate selectors → 5 min
4. Compose adapter → 1 min
5. Test → works immediately

**Time:** ~30 minutes

## Priority Rules

When both hint pack and profiler are provided:

**Hint Pack Wins:**
- Ad types and selectors
- Folder mappings
- Brand extraction strategies
- Auth requirements

**Profiler Augments:**
- Confirms auth requirements
- Detects store selection UI
- Tests headless compatibility
- Validates selectors still work

## Example: Kroger

See `kroger_ad_types.yaml` for a complete example with:
- 3 ad types (TOA, Skyscraper, CuratedCarousel)
- Tested selectors
- Brand extraction strategies
- Auth and anti-bot hints

## Tools

### selector_smoke_test.py
Validates selectors against HTML samples.

```bash
python3 ../tools/selector_smoke_test.py kroger_ad_types.yaml
```

### compose_retailer.py
Generates adapter from hint pack.

```bash
# Hint pack only
python3 ../tools/compose_retailer.py --hint-pack kroger_ad_types.yaml

# Hint pack + profiler
python3 ../tools/compose_retailer.py \
  --hint-pack kroger_ad_types.yaml \
  --profile ../profiles/kroger_profile.json
```

## Best Practices

1. **Start with real HTML** - Don't guess selectors
2. **Test before composing** - Run smoke test until green
3. **Document edge cases** - Add notes about special behavior
4. **Version control** - Commit hint packs with code
5. **Keep samples updated** - Update when HTML changes

## Documentation

- **Full Guide:** `AD_TYPE_HINT_PACK_GUIDE.md`
- **Template:** `HINT_PACK_TEMPLATE.yaml`
- **Examples:** `kroger_ad_types.yaml`, `walmart_ad_types.yaml`

## Questions?

See `AD_TYPE_HINT_PACK_GUIDE.md` for comprehensive documentation.
