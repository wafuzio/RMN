import { RequestHandler } from "express";
import { promises as fs } from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function brandSlug(name: string): string {
  return (name || "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
}

export const handleBrandLogo: RequestHandler = async (req, res) => {
  const { brand } = req.params;

  if (!brand) {
    return res.status(400).json({ error: "Brand name is required" });
  }

  try {
    // Read the brand logo database - path is relative to server/routes directory
    const dbPath = path.resolve(__dirname, "../../..", "output", "brand_logos", "brand_logo_database.json");
    const dbContent = await fs.readFile(dbPath, "utf-8");
    const database = JSON.parse(dbContent);

    // Get the brand slug
    const slug = brandSlug(brand);

    // Look up the brand in the database
    const brands = database.brands || {};
    const brandRecord = brands[slug];

    if (!brandRecord || !brandRecord.logo_file) {
      return res.status(404).json({ error: "Logo not found for brand" });
    }

    // Get the filename from the logo_file field
    let filename = brandRecord.logo_file;
    // Strip "brand_logos/" prefix if present
    if (filename.startsWith("brand_logos/")) {
      filename = filename.substring("brand_logos/".length);
    }

    // Construct the path to the logo file
    const logoPath = path.resolve(__dirname, "../../..", "output", "brand_logos", filename);

    // Verify the file exists and is within the allowed directory
    const resolvedPath = path.resolve(logoPath);
    const allowedDir = path.resolve(path.resolve(__dirname, "../../..", "output", "brand_logos"));

    if (!resolvedPath.startsWith(allowedDir)) {
      return res.status(403).json({ error: "Access denied" });
    }

    const fileContent = await fs.readFile(logoPath);

    const ext = path.extname(filename).toLowerCase();
    const mimeTypes: Record<string, string> = {
      ".png": "image/png",
      ".jpg": "image/jpeg",
      ".jpeg": "image/jpeg",
      ".gif": "image/gif",
      ".webp": "image/webp",
      ".svg": "image/svg+xml",
    };

    res.set("Content-Type", mimeTypes[ext] || "application/octet-stream");
    res.set("Cache-Control", "public, max-age=3600");
    res.set("Access-Control-Allow-Origin", "*");
    res.set("Access-Control-Allow-Methods", "GET");
    res.send(fileContent);
  } catch (error) {
    console.error("Error serving brand logo:", {
      brand,
      message: error instanceof Error ? error.message : String(error),
      stack: error instanceof Error ? error.stack : undefined,
    });
    res.status(500).json({ error: "Failed to serve logo" });
  }
};
