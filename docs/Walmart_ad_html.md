# Walmart Ad HTML – Reference

## Search URL
```
https://www.walmart.com/search?q={keyword}
```

## Ad Modules + Selectors

### Programmatic Banner (top/bottom)
**CSS:** `a.ad, a.adctr`

### Sponsored Brand (SBA)
**CSS:** `[data-testid="sba-container"]`

### Tile Takeover
**CSS:** `[data-testid="tile-take-over"]`

### Sponsored Brand Video (SBV)
**CSS:** `[data-testid="search-video-in-grid"]` (contains `<video>`)

## Redirect URLs
- `sp/track?…&rd=<encoded_url>` → decode "rd" param
- `dad/trk` (encrypted) → keep original URL

## Notes
- No login required for basic capture; persistent profile recommended
- Store/location may influence creatives. For deterministic tests, seed store via profile
