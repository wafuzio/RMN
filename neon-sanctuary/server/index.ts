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
import { handleAdsCount } from "./routes/ads-count";
import { handleBrands } from "./routes/brands";
import { handleBrandDetails } from "./routes/brand-details";
import { handleTimeline } from "./routes/timeline";
import { handleProxyImage } from "./routes/proxy-image";
import { handlePlaceholderAd } from "./routes/placeholder";
import { handleImageProxy } from "./routes/image";
import { handleVideoProxy } from "./routes/video";

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

  // Performance monitoring: Server-Timing header
  app.use((req, res, next) => {
    const t0 = process.hrtime.bigint();
    const originalSend = res.send;
    res.send = function(data) {
      const t1 = process.hrtime.bigint();
      const ms = Number(t1 - t0) / 1e6;
      res.setHeader('Server-Timing', `nodeTotal;dur=${ms.toFixed(1)}`);
      return originalSend.call(this, data);
    };
    next();
  });

  // Example API routes
  app.get("/api/ping", (_req, res) => {
    const ping = process.env.PING_MESSAGE ?? "ping";
    res.json({ message: ping });
  });

  app.get("/api/demo", handleDemo);
  app.get("/api/logo/brand/:brand", handleBrandLogo);
  app.get("/api/logo/:retailer", handleRetailerLogo);
  app.get("/proxy-image", handleProxyImage);
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

  // Dashboard API routes
  app.get("/api/retailers", handleRetailers);
  app.get("/api/clients", handleClients);
  app.get("/api/ads/cards", handleAdsProxy);
  app.get("/api/ads/count", handleAdsCount);
  app.get("/api/brands", handleBrands);
  app.get("/api/brand-details", handleBrandDetails);
  app.get("/api/timeline", handleTimeline);

  return app;
}
