# Walmart Proxy Setup Guide

## Overview

Walmart uses PerimeterX bot protection which is extremely sophisticated. To avoid CAPTCHA challenges, use:

1. **Persistent Chrome** (channel=chrome) - Real Chrome browser, not Chromium
2. **Residential IPs** - Proxies that look like real users
3. **User-like timing** - Random delays, scrolling, mouse movements
4. **Profile reuse** - Authenticated sessions
5. **Stealth patches** - Anti-detection measures

## Environment Variables

### Proxy Configuration

```bash
# Required: Proxy server URL
export WALMART_PROXY_SERVER="http://proxy.example.com:8080"

# Optional: Proxy authentication
export WALMART_PROXY_USERNAME="your_username"
export WALMART_PROXY_PASSWORD="your_password"

# Required: Profile directory
export WALMART_PROFILE_DIR="$HOME/Documents/Amazon_Scrape/profiles/walmart"
```

### Recommended Proxy Providers

**Residential Proxies** (Best for avoiding detection):
- **Bright Data** (formerly Luminati) - Premium, expensive
- **Smartproxy** - Good balance of price/quality
- **Oxylabs** - Enterprise-grade
- **GeoSurf** - Residential IPs

**Datacenter Proxies** (Cheaper, higher detection risk):
- Use only as fallback
- Rotate frequently
- Expect more CAPTCHAs

## Setup Steps

### 1. Get Residential Proxy

Sign up with a provider and get:
- Proxy server URL (e.g., `http://proxy.smartproxy.com:10000`)
- Username
- Password

### 2. Configure Environment

Add to `~/.zshrc` or `~/.bash_profile`:

```bash
# Walmart Proxy Configuration
export WALMART_PROXY_SERVER="http://proxy.smartproxy.com:10000"
export WALMART_PROXY_USERNAME="your_username"
export WALMART_PROXY_PASSWORD="your_password"
export WALMART_PROFILE_DIR="$HOME/Documents/Amazon_Scrape/profiles/walmart"
```

Reload:
```bash
source ~/.zshrc
```

### 3. Create Authenticated Profile

```bash
python3 scripts/manual_walmart_setup.py
```

This will:
1. Open browser with proxy
2. Let you solve CAPTCHA (if any)
3. Let you log in to Walmart
4. Save authenticated session

### 4. Test Scraper

```bash
python3 keyword_input.py
```

Select Walmart, enter keyword, click "Start Scraping".

## Block Detection

The scraper automatically detects:

- **PerimeterX CAPTCHA** - `perimeterx_captcha`
- **Access Denied** - `access_denied`
- **Rate Limit** - `rate_limit`
- **Unusual Activity** - `unusual_activity`
- **Empty Response** - `empty_response`

When blocked, the scraper will:
1. Log the block reason
2. Suggest actions (rotate proxy, wait, change profile)
3. Return error (no data captured)

## Proxy Rotation Strategy

### Manual Rotation

If you get blocked:

1. **Change proxy server**:
   ```bash
   export WALMART_PROXY_SERVER="http://different-proxy.com:8080"
   ```

2. **Wait before retry**:
   ```bash
   sleep 300  # 5 minutes
   ```

3. **Use different profile**:
   ```bash
   export WALMART_PROFILE_DIR="$HOME/Documents/Amazon_Scrape/profiles/walmart2"
   python3 scripts/manual_walmart_setup.py
   ```

### Automated Rotation (Future)

For production, consider:
- Proxy pool with automatic rotation
- Backoff strategy (exponential delays)
- Multiple profiles with round-robin
- CAPTCHA solving service integration

## Stealth Features Implemented

✅ **Browser**:
- Persistent Chrome (channel=chrome)
- Real Chrome, not Chromium
- 30+ anti-detection flags
- navigator.webdriver override

✅ **Behavior**:
- Homepage visit first
- Random scrolling (300px down, then up)
- Mouse movements
- Human-like delays (1.5-4 seconds)
- networkidle wait strategy

✅ **Session**:
- Persistent profile reuse
- Authenticated sessions
- Cookies preserved

✅ **Network**:
- Residential proxy support
- Custom user agent
- Timezone configuration

## Troubleshooting

### Still Getting CAPTCHA

1. **Check proxy type**: Residential > Datacenter
2. **Verify profile**: Must be authenticated
3. **Check timing**: Delays should be random
4. **Rotate proxy**: Change IP if flagged
5. **Wait longer**: Add more delays between actions

### Proxy Not Working

```bash
# Test proxy manually
curl -x $WALMART_PROXY_SERVER \
  -U $WALMART_PROXY_USERNAME:$WALMART_PROXY_PASSWORD \
  https://www.walmart.com/
```

### Profile Issues

```bash
# Clear and recreate profile
rm -rf ~/Documents/Amazon_Scrape/profiles/walmart
python3 scripts/manual_walmart_setup.py
```

## Cost Considerations

**Residential Proxies**:
- ~$5-15 per GB
- Walmart search page ~500KB-1MB
- ~1000-2000 searches per GB
- Budget: $10-30/month for moderate use

**CAPTCHA Solving** (if needed):
- 2Captcha: ~$1-3 per 1000 CAPTCHAs
- Anti-Captcha: Similar pricing
- Budget: $5-20/month depending on volume

## Best Practices

1. **Always use residential proxies** for Walmart
2. **Maintain authenticated profiles** (log in manually once)
3. **Add random delays** between searches (30-60 seconds)
4. **Rotate proxies** if you see repeated CAPTCHAs
5. **Monitor block signals** and adjust strategy
6. **Run during off-peak hours** (less detection)
7. **Limit request rate** (max 1-2 searches per minute)

## See Also

- `docs/Walmart_ad_html.md` - Ad selectors and structure
- `scripts/manual_walmart_setup.py` - Profile setup script
- `walmart_search_and_capture.py` - Main scraper implementation
