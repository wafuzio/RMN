# ngrok IPv6 Connection Issue - Fixed

## Problem

ngrok was returning "Client not found" errors when trying to reach the Flask API. The root cause was an IPv6 vs IPv4 mismatch:

```
dial tcp [::1]:5006: connect: connection refused
```

This error meant ngrok was trying to reach Flask via IPv6 (`[::1]`) but Flask was only accessible via IPv4 (`127.0.0.1`).

## Root Cause

When ngrok is configured with just a port number:
```bash
ngrok http 5006
```

On macOS, `localhost` can resolve to IPv6 `[::1]` first, causing ngrok to attempt an IPv6 connection. However, Flask bound to `0.0.0.0:5006` may not be properly listening on the IPv6 loopback interface.

## Solution

Explicitly tell ngrok to use the IPv4 loopback address:

```bash
ngrok http 127.0.0.1:5006
```

This forces ngrok to connect via IPv4, which Flask is guaranteed to be listening on.

## Implementation

### File: `restart_servers.sh`

**Before:**
```bash
nohup ngrok http 5006 > logs/ngrok.log 2>&1 &
```

**After:**
```bash
nohup ngrok http 127.0.0.1:5006 > logs/ngrok.log 2>&1 &
```

## Verification

After the fix, verify ngrok is using IPv4:

```bash
# Check ngrok configuration
curl -s http://localhost:4040/api/tunnels | jq '.tunnels[] | {name, public_url, config}'
```

Expected output:
```json
{
  "name": "command_line",
  "public_url": "https://your-subdomain.ngrok-free.dev",
  "config": {
    "addr": "http://127.0.0.1:5006",
    "inspect": true
  }
}
```

Note the `addr` field now shows `127.0.0.1:5006` instead of just `5006`.

## Testing

Test that ngrok can reach Flask:

```bash
curl -s -H "ngrok-skip-browser-warning: true" "https://your-subdomain.ngrok-free.dev/api/retailers" | jq
```

Expected: JSON response with list of retailers (no "Client not found" error).

## Why This Happens on macOS

macOS has dual-stack networking enabled by default, and `localhost` can resolve to either:
- IPv6: `::1`
- IPv4: `127.0.0.1`

The system may prefer IPv6 when both are available. By explicitly specifying `127.0.0.1`, we bypass DNS resolution and force IPv4 connectivity.

## Alternative Solutions (Not Recommended)

1. **Disable IPv6 system-wide** - Too invasive, affects all applications
2. **Configure Flask to listen on IPv6** - More complex, unnecessary for local dev
3. **Use ngrok config file** - Adds complexity when command-line flag works fine

## Related Issues

This same issue can affect:
- Docker containers with improper network configuration
- Other tunneling services (localtunnel, serveo, etc.)
- Any service that resolves `localhost` without explicit IP version

## Commit

Fixed in commit: `e604050` on branch `builder-errors`
