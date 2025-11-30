import { RequestHandler } from "express";

const FLASK_BASE_URL = process.env.FLASK_BASE_URL || "http://localhost:5006";

export const handleImageProxy: RequestHandler = async (req, res) => {
  const { retailer, client, filename } = req.params;

  if (!retailer || !client || !filename) {
    console.warn("[image-proxy] Missing required parameters", {
      retailer,
      client,
      filename,
    });
    return res
      .status(400)
      .json({ error: "retailer, client, and filename are required" });
  }

  // Build Flask URL with query string if present
  let flaskUrl = `${FLASK_BASE_URL}/api/image/${retailer}/${client}/${filename}`;
  const queryString = new URLSearchParams(req.query as Record<string, string>).toString();
  if (queryString) {
    flaskUrl += `?${queryString}`;
  }

  try {
    console.debug("[image-proxy] Proxying request to Flask", {
      flaskUrl,
      retailer,
      client,
      filename,
      queryString: queryString || "(none)",
    });

    // Forward the request to Flask backend
    const response = await fetch(flaskUrl, {
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "ngrok-skip-browser-warning": "true",
      },
    });

    if (!response.ok) {
      console.error("[image-proxy] Flask returned non-OK status", {
        flaskUrl,
        status: response.status,
        statusText: response.statusText,
        contentType: response.headers.get("content-type"),
      });
      return res
        .status(response.status)
        .json({ error: `Failed to fetch image: ${response.statusText}` });
    }

    const contentType = response.headers.get("content-type");
    if (!contentType || !contentType.startsWith("image/")) {
      console.error("[image-proxy] Response is not an image", {
        flaskUrl,
        contentType,
      });
      return res.status(400).json({ error: "Response is not an image" });
    }

    // Set appropriate headers for caching and CORS
    res.set("Content-Type", contentType);
    res.set("Cache-Control", "public, max-age=31536000, immutable"); // 1 year cache for images
    res.set("Access-Control-Allow-Origin", "*");
    res.set("Access-Control-Allow-Methods", "GET");
    res.set("Access-Control-Expose-Headers", "Server-Timing"); // Expose backend timing to frontend

    // Stream the image data
    const buffer = await response.arrayBuffer();
    console.debug("[image-proxy] Successfully proxied image", {
      flaskUrl,
      size: buffer.byteLength,
      contentType,
    });
    return res.send(Buffer.from(buffer));
  } catch (error) {
    console.error("[image-proxy] Error proxying request", {
      flaskUrl,
      message: error instanceof Error ? error.message : String(error),
      stack: error instanceof Error ? error.stack : undefined,
    });
    return res.status(500).json({ error: "Failed to proxy image from Flask backend" });
  }
};
