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
- **⚠️ CAPTCHA WARNING:** Walmart uses PerimeterX bot protection
- You will likely need to solve CAPTCHA on EVERY run (this is normal)
- Persistent profile helps but doesn't eliminate CAPTCHA
- **Headed mode (browser visible) is REQUIRED** for manual CAPTCHA solving
- Store/location may influence creatives. For deterministic tests, seed store via profile

## Why CAPTCHA Persists
PerimeterX tracks:
- Browser fingerprints
- Behavioral patterns  
- Session continuity
- Network patterns

Even with a saved profile, each new browser session triggers CAPTCHA because:
1. New browser instance = new fingerprint
2. Automated behavior patterns are detected
3. No mouse movements/human interaction before search

**This is expected behavior - just solve the CAPTCHA each time.**

## Setup Instructions

### 1. Create Authenticated Profile
```bash
./scripts/setup_walmart_profile.sh
```

This will:
1. Open browser to walmart.com
2. Prompt you to solve CAPTCHA if it appears
3. Let you browse naturally to establish trust
4. Save the session for future runs

### 2. Set Environment Variable
```bash
export WALMART_PROFILE_DIR="$HOME/Documents/Amazon_Scrape/profiles/walmart"
```

### 3. Run Scraper
The scraper will use the saved session and should bypass CAPTCHA.

## CAPTCHA Behavior

**If CAPTCHA is detected:**
- **Headed mode (headless=False):** Browser stays open for 60 seconds, waiting for you to solve it
- **Headless mode:** Returns error immediately (cannot solve CAPTCHA without display)

**Solution:** Always use a persistent profile with pre-solved CAPTCHA
