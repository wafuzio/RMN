# Architecture: Why We Use an Express Proxy (and When Builder's Dev Proxy Appears)

## What Runs Where

1. **Flask API (port 5006)**: Serves JSON and files (images/videos) from the `output/` tree.
2. **Vite + Express (port 3000)**: Serves the React dashboard and proxies certain `/api/*` paths to Flask, so the browser sees a single origin during local dev.
3. **Builder dev-tools proxy (ephemeral, e.g., localhost:48752)**: A Builder-run proxy created by `npx builder …` for local preview. It's not our server and can 401 `/?_isCreator=true` if its handshake isn't satisfied.
4. **ngrok (public URL)**: Exposes the Flask API (and/or the dashboard) to Builder Cloud so you can preview/edit without any local proxy at all.

## Why We Keep Our Own Express Proxy

1. **Single origin during dev**: From the browser's perspective, all UI and API requests come from the same host (`http://localhost:3000`), so CORS is a non-issue for the app UI.

2. **Image and media bridging**: Images are stored on disk behind Flask. The Express proxy streams those files to the browser and can add headers, cache control, or guardrails without exposing your file layout.

3. **Flexibility**: You can normalize headers (e.g., `ngrok-skip-browser-warning`), set timeouts, and defend against SSRF on "proxy" routes.

## Typical Routes We Proxy

- **JSON passthrough (optional)**: `/api/*` → `http://localhost:5006/api/*`
- **Images/videos**: `/api/image/:retailer/:client/*` → `http://localhost:5006/api/image/:retailer/:client/*`
- **CDN fallbacks**: `/api/proxy-image?url=…` (Flask already supports this, but you can offer the same behavior in Node if needed)

## Reference Express Snippets

### Image Proxy (streams, preserves content-type, small guardrails)

```typescript
import express from 'express';
import { pipeline } from 'stream';
import fetch from 'node-fetch';

const app = express();

function isSafePath(path: string) {
  // Prevent climbing out of /api/image namespace
  return /^\/api\/image\/[^/]+\/[^/]+\/.+$/.test(path);
}

app.get(/^\/api\/image\/([^/]+)\/([^/]+)\/(.+)$/, async (req, res) => {
  if (!isSafePath(req.path)) return res.status(400).send('Bad path');
  const upstream = `http://localhost:5006${req.path}`;
  try {
    const r = await fetch(upstream, { timeout: 15000 });
    if (!r.ok) return res.status(r.status).send(await r.text());
    const ct = r.headers.get('content-type') || 'application/octet-stream';
    res.setHeader('Content-Type', ct);
    res.setHeader('Cache-Control', 'public, max-age=3600, must-revalidate');
    // Stream to avoid buffering large files in memory
    pipeline(r.body as any, res, (err) => { if (err) res.destroy(err); });
  } catch (e: any) {
    res.status(502).send('Upstream error');
  }
});
```

### JSON Proxy (only to your own API, avoids SSRF)

```typescript
app.get('/api/proxy-json', async (req, res) => {
  const path = String(req.query.path || '');
  if (!path.startsWith('/api/')) return res.status(400).json({ error: 'invalid path' });
  const upstream = `http://localhost:5006${path}`;
  try {
    const r = await fetch(upstream, {
      headers: { 'ngrok-skip-browser-warning': 'true' },
      timeout: 15000
    });
    const body = await r.text();
    res.status(r.status);
    res.setHeader('Content-Type', r.headers.get('content-type') || 'application/json');
    res.setHeader('Access-Control-Allow-Origin', '*'); // dev-friendly
    res.send(body);
  } catch (e: any) {
    res.status(502).json({ error: 'upstream request failed' });
  }
});
```

## How Images Flow

### Dev (single-origin via Vite/Express)

1. React → `GET /api/image/kroger/client/…` (origin: `localhost:3000`)
2. Express (3000) → proxies to Flask (5006)
3. Flask → finds file in `output/{retailer}/{client}/…` and streams
4. Express → streams back with content-type + cache headers
5. Browser → renders image, no CORS involved

### Builder Cloud Preview (recommended for editing)

1. Builder preview uses your ngrok URL (Proxy previews ON)
2. React/Builder code fetches `https://<your-id>.ngrok-free.dev/api/*` (`credentials: 'omit'`)
3. Flask CORS whitelists `*.builder.io` and your ngrok domain (`ALLOWED_ORIGINS`), so CORS succeeds
4. No `localhost:48752` path is involved, so no 401 from the dev-tools proxy

## When the Builder Dev-Tools Proxy (48752) Appears (and Why It 401s)

Running `npx builder dev` spawns a Builder-owned proxy on an ephemeral port (e.g., 48752). The editor often loads `/?_isCreator=true` through that proxy. If the expected handshake/header isn't present, it returns **401 Unauthorized**.

**If you want to avoid this entirely**, point Builder preview directly at your ngrok base and keep "Proxy previews" ON. This bypasses the local proxy and is usually the least-friction setup.

## Alternatives and Tradeoffs

- **Only Flask CORS (no Express proxy)**: Possible because your Flask `after_request` already handles CORS. But you'll still want a proxy for images if you need stricter headers, streaming, or to avoid exposing filesystem paths. Express also keeps the UI single-origin during dev, which is nice.

- **Express proxy everywhere**: Cleanest local DX, plus you can mirror the same proxy rules behind Nginx/CloudFront in prod if you want.

## Security and Caching Notes

1. **Do not build an open proxy**. Only forward to your own Flask API; validate paths/hosts.
2. **Stream large files** (`pipeline()` above) to keep memory stable.
3. **Add conservative caching** for images (e.g., `public, max-age=3600, must-revalidate`). For published builds/CDN you can go longer with immutable file names.
4. **For JSON proxy**, never forward arbitrary URLs. Use a whitelisted `/api/*` path and normalize query params.

## Common Failure Modes (and Quick Fixes)

### Preview shows "Not authorized" at `http://localhost:48752/?_isCreator=true`

That is Builder's dev-tools proxy, not your app. Bypass it by previewing the ngrok URL (Proxy previews ON) or start/authorize the dev-tools process properly.

### CORS error from Builder Cloud

Ensure `ALLOWED_ORIGINS` includes `https://app.builder.io`, `https://*.builder.io`, and your ngrok origin, then `./restart_servers.sh`.

In Builder "Run code" fetches, add `credentials: 'omit'` and the `ngrok-skip-browser-warning` header.

### Mixed content

Remove any `http://localhost:*` references in Builder content. Use `https://<your-ngrok>/…` everywhere.

### "ngrok browser warning" content instead of JSON

Add header `ngrok-skip-browser-warning: true` in both Data Source and `fetch()`. Or call your `/api/proxy-json`.

## Smoke Tests (copy/paste)

### Local (dev, single origin)

```bash
curl -I http://localhost:3000/api/image/kroger/client/TOA/foo.png
curl -i http://localhost:3000/api/proxy-json?path=/api/retailers
```

### Via ngrok (what Builder uses)

```bash
curl -i https://<your-ngrok>.ngrok-free.dev/api/retailers -H 'ngrok-skip-browser-warning: true'
curl -I https://<your-ngrok>.ngrok-free.dev/ -H 'ngrok-skip-browser-warning: true'
```

## Key Takeaway

**localhost:48752 is Builder's own dev-tools proxy** (spawned by `npx builder …`), not your app's Express. **Your app's Express lives with Vite on port 3000** (and possibly any custom server you run), and that is the proxy you control.

The rationale for an app-owned Express proxy is still solid, especially for images and CDNs. This architecture gives you full control over headers, caching, security, and streaming while maintaining a clean single-origin dev experience.
