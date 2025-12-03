import { RequestHandler } from "express";
import { promises as fs } from "fs";
import path from "path";
import crypto from "crypto";
import sharp from "sharp";

export const handleBrandLogo: RequestHandler = async (req, res) => {
  const { brand } = req.params;
  const width = req.query.w ? parseInt(req.query.w as string) : null;

  if (!brand) {
    return res.status(400).json({ error: "Brand name is required" });
  }

  try {
    const brandLogoDir = path.join(process.cwd(), "..", "output", "brand_logos", "Verified");

    const files = await fs.readdir(brandLogoDir).catch(() => []);

    // Normalize brand name to match logo_scout.py normalization
    // Strip diacritics (ö→o, ä→a, etc), replace & with "and", remove apostrophes/periods, replace spaces with underscores
    const normalizedBrand = brand
      .normalize("NFD") // Decompose unicode (ö → o + ¨)
      .replace(/[\u0300-\u036f]/g, "") // Remove diacritical marks
      .toLowerCase()
      .replace(/&/g, "and")
      .replace(/['.]/g, "")
      .replace(/\s+/g, "_")
      .replace(/[^a-z0-9_-]/g, "");

    // Look for matching logo file with any supported image extension
    const logoFile = files.find(f => {
      const fileNameWithoutExt = f.replace(/\.(png|jpg|jpeg|svg|gif|webp)$/i, "");
      // Apply same normalization as brand name for consistent matching
      const normalizedFileName = fileNameWithoutExt
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLowerCase()
        .replace(/&/g, "and")
        .replace(/['.]/g, "")
        .replace(/\s+/g, "_")
        .replace(/[^a-z0-9_-]/g, "");

      return normalizedFileName === normalizedBrand;
    });

    if (!logoFile) {
      return res.status(404).json({ error: "Logo not found for brand" });
    }

    const logoPath = path.join(brandLogoDir, logoFile);
    const ext = path.extname(logoFile).toLowerCase();
    
    // SVGs don't need resizing, serve as-is
    if (ext === ".svg") {
      const fileStats = await fs.stat(logoPath);
      const fileContent = await fs.readFile(logoPath);
      const hash = crypto.createHash('md5').update(fileContent).digest('hex');
      const etag = `"${hash}"`;

      if (req.headers['if-none-match'] === etag) {
        return res.status(304).end();
      }

      res.set("Content-Type", "image/svg+xml");
      res.set("Cache-Control", "public, max-age=31536000, immutable");
      res.set("ETag", etag);
      res.set("Last-Modified", fileStats.mtime.toUTCString());
      res.set("Access-Control-Allow-Origin", "*");
      return res.send(fileContent);
    }

    // For raster images, resize if width parameter provided
    let imageBuffer = await fs.readFile(logoPath);
    const fileStats = await fs.stat(logoPath);
    const mtime = fileStats.mtime.getTime(); // Include mtime in hash for cache busting on file changes
    
    if (width && width > 0 && width <= 1000) {
      // Resize image using sharp
      imageBuffer = await sharp(imageBuffer)
        .resize(width, width, {
          fit: 'inside',
          withoutEnlargement: true
        })
        .webp({ quality: 85 }) // Convert to WebP for better compression
        .toBuffer();
      
      // Generate ETag from resized content + mtime for cache busting
      const hash = crypto.createHash('md5').update(imageBuffer).digest('hex');
      const etag = `"${hash}-${width}-${mtime}"`;

      if (req.headers['if-none-match'] === etag) {
        return res.status(304).end();
      }

      res.set("Content-Type", "image/webp");
      res.set("Cache-Control", "public, max-age=86400"); // 1 day, not immutable
      res.set("ETag", etag);
      res.set("Vary", "Accept");
      res.set("Access-Control-Allow-Origin", "*");
      return res.send(imageBuffer);
    }

    // No resize requested, serve original
    const hash = crypto.createHash('md5').update(imageBuffer).digest('hex');
    const etag = `"${hash}-${mtime}"`;

    if (req.headers['if-none-match'] === etag) {
      return res.status(304).end();
    }

    const mimeTypes: Record<string, string> = {
      ".png": "image/png",
      ".jpg": "image/jpeg",
      ".jpeg": "image/jpeg",
      ".gif": "image/gif",
      ".webp": "image/webp",
    };

    res.set("Content-Type", mimeTypes[ext] || "application/octet-stream");
    res.set("Cache-Control", "public, max-age=86400"); // 1 day, not immutable
    res.set("ETag", etag);
    res.set("Last-Modified", new Date(mtime).toUTCString());
    res.set("Access-Control-Allow-Origin", "*");
    res.send(imageBuffer);
  } catch (error) {
    console.error("Error serving brand logo:", error);
    res.status(500).json({ error: "Failed to serve logo" });
  }
};
