import { RequestHandler } from "express";
import { promises as fs } from "fs";
import path from "path";

export const handleBrandLogo: RequestHandler = async (req, res) => {
  const { brand } = req.params;

  if (!brand) {
    return res.status(400).json({ error: "Brand name is required" });
  }

  try {
    const brandLogoDir = path.join(process.cwd(), "..", "output", "brand_logos");

    const files = await fs.readdir(brandLogoDir).catch(() => []);

    // Normalize brand name: lowercase, replace spaces with underscores, remove special characters (including apostrophes)
    const normalizedBrand = brand
      .toLowerCase()
      .replace(/\s+/g, "_")
      .replace(/[^a-z0-9_-]/g, "");

    // Look for matching logo file with .png or .jpg extension
    const logoFile = files.find(f => {
      const fileNameWithoutExt = f.replace(/\.(png|jpg|jpeg)$/i, "");
      const normalizedFileName = fileNameWithoutExt
        .toLowerCase()
        .replace(/\s+/g, "_")
        .replace(/[^a-z0-9_-]/g, "");

      return normalizedFileName === normalizedBrand;
    });

    if (!logoFile) {
      return res.status(404).json({ error: "Logo not found for brand" });
    }

    const logoPath = path.join(brandLogoDir, logoFile);
    const fileContent = await fs.readFile(logoPath);

    const ext = path.extname(logoFile).toLowerCase();
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
    res.send(fileContent);
  } catch (error) {
    console.error("Error serving brand logo:", error);
    res.status(500).json({ error: "Failed to serve logo" });
  }
};
