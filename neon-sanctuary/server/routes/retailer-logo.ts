import { RequestHandler } from "express";
import { promises as fs } from "fs";
import path from "path";

const RETAILER_LOGO_MAP: Record<string, string> = {
  amazon: "AMZ.png",
  walmart: "WMT.png",
  kroger: "Kroger.png",
  instacart: "Instacart Long.png",
};

export const handleRetailerLogo: RequestHandler = async (req, res) => {
  const { retailer } = req.params;

  if (!retailer) {
    return res.status(400).json({ error: "Retailer name is required" });
  }

  const retailerLower = retailer.toLowerCase();
  const logoFileName = RETAILER_LOGO_MAP[retailerLower];

  if (!logoFileName) {
    return res.status(404).json({ error: `Logo not found for retailer: ${retailer}` });
  }

  try {
    const logoPath = path.join(process.cwd(), "..", "web", "assets", "logos", logoFileName);
    const fileContent = await fs.readFile(logoPath);

    const ext = path.extname(logoFileName).toLowerCase();
    const mimeTypes: Record<string, string> = {
      ".png": "image/png",
      ".jpg": "image/jpeg",
      ".jpeg": "image/jpeg",
      ".gif": "image/gif",
      ".webp": "image/webp",
      ".svg": "image/svg+xml",
    };

    res.set("Content-Type", mimeTypes[ext] || "application/octet-stream");
    res.set("Cache-Control", "public, max-age=86400");
    res.set("Access-Control-Allow-Origin", "*");
    res.set("Access-Control-Allow-Methods", "GET");
    res.send(fileContent);
  } catch (error) {
    console.error(`[retailer-logo] Error serving logo for ${retailer}:`, error);
    res.status(500).json({ error: "Failed to serve retailer logo" });
  }
};
