import { RequestHandler } from "express";
import { promises as fs } from "fs";
import path from "path";

// Map common retailer slugs to specific filenames when the slug
// doesn't directly match the logo's base filename.
const RETAILER_LOGO_ALIASES: Record<string, string> = {
  amazon: "AMZ.png",
  walmart: "WMT.png",
  instacart: "Instacart_Carrot.png",
  kroger: "Kroger_Cart.png",
  target: "Target.png",
  amazon_fresh: "AMZFresh.png",
  amzfresh: "AMZFresh.png",
  albertsons: "Albertsons_(logo).svg.png",
};

function normalizeRetailerName(name: string): string {
  return name
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/["'.]/g, "")
    .replace(/\s+/g, "_")
    .replace(/[^a-z0-9_-]/g, "");
}

export const handleRetailerLogo: RequestHandler = async (req, res) => {
  const { retailer } = req.params;

  if (!retailer) {
    return res.status(400).json({ error: "Retailer name is required" });
  }

  try {
    const logosDir = path.join(process.cwd(), "..", "web", "assets", "logos");
    const files = await fs.readdir(logosDir);

    const requestedKey = normalizeRetailerName(retailer);

    // First try explicit aliases for non-obvious filenames
    let logoFileName = RETAILER_LOGO_ALIASES[requestedKey] || null;
    if (logoFileName && !files.includes(logoFileName)) {
      // Alias points to a missing file; fall back to discovery
      logoFileName = null;
    }

    // If no alias match, scan all files in web/assets/logos and
    // pick the one whose normalized base name matches the retailer.
    if (!logoFileName) {
      logoFileName =
        files.find((f) => {
          const base = path.basename(f, path.extname(f));
          const normalizedBase = normalizeRetailerName(base);
          return normalizedBase === requestedKey;
        }) || null;
    }

    if (!logoFileName) {
      return res.status(404).json({ error: `Logo not found for retailer: ${retailer}` });
    }

    const logoPath = path.join(logosDir, logoFileName);
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
