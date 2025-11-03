import "dotenv/config";
import express from "express";
import cors from "cors";
import { RequestHandler } from "express";
import { handleDemo } from "./routes/demo";
import { handleBrandLogo } from "./routes/logo";
import { handleRetailerLogo } from "./routes/retailer-logo";
import { handleRetailers } from "./routes/retailers";
import { handleClients } from "./routes/clients";
import { handleAdsProxy } from "./routes/ads-proxy";
import { handleProxyImage } from "./routes/proxy-image";
import { handlePlaceholderAd } from "./routes/placeholder";
import { handleImageProxy } from "./routes/image";
import { handleVideoProxy } from "./routes/video";
import { handleAdsBatch } from "./routes/ads-batch";
import { handleAdsStats } from "./routes/ads-stats";

// Wrapper for regex route to extract ID from path
const handlePlaceholderAdRegex: RequestHandler = (req, res, next) => {
  // Extract ID from URL path using regex
  const match = req.path.match(/^\/api\/placeholder-ad-(\d+)\.jpg$/);
  if (!match || !match[1]) {
    return res.status(400).json({ error: "Invalid URL format" });
  }

  // Create a params object to mimic Express's req.params
  req.params.id = match[1];

  // Call the handler
  return handlePlaceholderAd(req, res, next);
};

export function createServer() {
  const app = express();

  // Middleware
  app.use(cors());
  app.use(express.json());
  app.use(express.urlencoded({ extended: true }));

  // Trace 401 senders (diagnostic)
  app.use((req, res, next) => {
    const t0 = Date.now();
    const _status = res.status;
    const _send = res.send;

    res.status = function (code) {
      if (code === 401) {
        console.warn('[401] %s %s', req.method, req.originalUrl);
        const stack = new Error('401 stack').stack;
        if (stack) {
          console.warn(stack.split('\n').slice(0, 8).join('\n'));
        }
      }
      return _status.apply(this, arguments);
    };

    res.send = function (body) {
      const ms = Date.now() - t0;
      console.log('[%s] %s %s (%dms)', res.statusCode, req.method, req.originalUrl, ms);
      return _send.call(this, body);
    };

    next();
  });

  // Example API routes
  app.get("/api/ping", (_req, res) => {
    const ping = process.env.PING_MESSAGE ?? "ping";
    res.json({ message: ping });
  });

  app.get("/api/demo", handleDemo);
  app.get("/api/brand_logo/:brand", handleBrandLogo);
  app.get("/api/logo/brand/:brand", handleBrandLogo);
  app.get("/api/logo/:retailer", handleRetailerLogo);
  app.get("/api/proxy-image", handleProxyImage);
  // Match URLs like /api/placeholder-ad-1.jpg, /api/placeholder-ad-2.jpg, etc.
  app.get(/^\/api\/placeholder-ad-(\d+)\.jpg$/, handlePlaceholderAdRegex);
  // Match /api/image/:retailer/:client/* to proxy to Flask backend
  app.get(/^\/api\/image\/([^/]+)\/([^/]+)\/(.+)$/, (req, res, next) => {
    req.params.retailer = req.params[0];
    req.params.client = req.params[1];
    req.params.filename = req.params[2];
    return handleImageProxy(req, res, next);
  });

  // Match /api/video/:retailer/:client/* to proxy to Flask backend
  app.get(/^\/api\/video\/([^/]+)\/([^/]+)\/(.+)$/, (req, res, next) => {
    req.params.retailer = req.params[0];
    req.params.client = req.params[1];
    req.params.filename = req.params[2];
    return handleVideoProxy(req, res, next);
  });

  // Placeholder image endpoint - proxy to Flask
  app.get("/api/image/placeholder", async (req, res) => {
    const FLASK_BASE_URL = process.env.FLASK_BASE_URL || "http://localhost:5006";
    const text = req.query.text || "MISSING";
    const w = req.query.w || "640";
    const h = req.query.h || "360";

    const flaskUrl = `${FLASK_BASE_URL}/api/image/placeholder?text=${text}&w=${w}&h=${h}`;

    try {
      console.debug("[placeholder-proxy] Proxying to Flask", { flaskUrl });

      const response = await fetch(flaskUrl, {
        headers: {
          "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
          "ngrok-skip-browser-warning": "true",
        },
      });

      if (!response.ok) {
        console.error("[placeholder-proxy] Flask returned non-OK status", {
          flaskUrl,
          status: response.status,
          statusText: response.statusText,
        });
        return res
          .status(response.status)
          .json({ error: `Failed to fetch placeholder: ${response.statusText}` });
      }

      const contentType = response.headers.get("content-type");
      res.set("Content-Type", contentType || "image/png");
      res.set("Cache-Control", "public, max-age=3600");
      res.set("Access-Control-Allow-Origin", "*");

      const buffer = await response.arrayBuffer();
      console.debug("[placeholder-proxy] Successfully proxied placeholder", {
        flaskUrl,
        size: buffer.byteLength,
      });
      res.send(Buffer.from(buffer));
    } catch (error) {
      console.error("[placeholder-proxy] Error proxying request", {
        flaskUrl,
        message: error instanceof Error ? error.message : String(error),
      });
      res.status(500).json({ error: "Failed to generate placeholder image" });
    }
  });

  // Dashboard API routes
  app.get("/api/retailers", handleRetailers);
  app.get("/api/clients", handleClients);
  app.get("/api/ads/cards", handleAdsProxy);
  app.get("/api/ads/batch", handleAdsBatch);
  app.get("/api/ads/stats", handleAdsStats);

  // Dump routes for debugging
  function dumpRoutes(app: express.Application) {
    const seen = new Set<string>();
    function walk(stack: any[], prefix = '') {
      for (const layer of stack) {
        if (layer.route) {
          const route = layer.route;
          const methods = Object.keys(route.methods)
            .filter(Boolean)
            .map((m) => m.toUpperCase())
            .join(',');
          const routePath = prefix + route.path;
          if (!seen.has(routePath)) {
            seen.add(routePath);
            console.log('[route] %s %s', methods, routePath);
          }
        } else if (layer.name === 'router' && layer.handle?.stack) {
          const regexp = layer.regexp?.source || '';
          walk(layer.handle.stack, regexp.includes('^') ? '' : prefix);
        }
      }
    }
    if (app._router) {
      console.log('\n=== Registered Routes ===');
      walk(app._router.stack);
      console.log('========================\n');
    }
  }
  dumpRoutes(app);

  return app;
}
