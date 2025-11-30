import { RequestHandler } from "express";

const FLASK_BASE_URL = process.env.FLASK_BASE_URL || "http://localhost:5006";

export const handleVideoProxy: RequestHandler = async (req, res) => {
  const { retailer, client, filename } = req.params;

  if (!retailer || !client || !filename) {
    console.warn("[video-proxy] Missing required parameters", {
      retailer,
      client,
      filename,
    });
    return res
      .status(400)
      .json({ error: "retailer, client, and filename are required" });
  }

  // Build Flask URL with query string if present
  let flaskUrl = `${FLASK_BASE_URL}/api/video/${retailer}/${client}/${filename}`;
  const queryString = new URLSearchParams(req.query as Record<string, string>).toString();
  if (queryString) {
    flaskUrl += `?${queryString}`;
  }

  try {
    console.debug("[video-proxy] Proxying request to Flask", {
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
      console.error("[video-proxy] Flask returned non-OK status", {
        flaskUrl,
        status: response.status,
        statusText: response.statusText,
        contentType: response.headers.get("content-type"),
      });
      return res
        .status(response.status)
        .json({ error: `Failed to fetch video: ${response.statusText}` });
    }

    const contentType = response.headers.get("content-type");
    if (!contentType || !contentType.startsWith("video/")) {
      console.error("[video-proxy] Response is not a video", {
        flaskUrl,
        contentType,
      });
      return res.status(400).json({ error: "Response is not a video" });
    }

    // Set appropriate headers for caching and CORS
    res.set("Content-Type", contentType);
    res.set("Cache-Control", "public, max-age=86400");
    res.set("Access-Control-Allow-Origin", "*");
    res.set("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS");
    res.set("Accept-Ranges", "bytes");

    // For videos, set Content-Length to support range requests
    const contentLength = response.headers.get("content-length");
    if (contentLength) {
      res.set("Content-Length", contentLength);
    }

    // Stream the video data
    const buffer = await response.arrayBuffer();
    console.debug("[video-proxy] Successfully proxied video", {
      flaskUrl,
      size: buffer.byteLength,
      contentType,
    });
    return res.send(Buffer.from(buffer));
  } catch (error) {
    console.error("[video-proxy] Error proxying request", {
      flaskUrl,
      message: error instanceof Error ? error.message : String(error),
      stack: error instanceof Error ? error.stack : undefined,
    });
    return res.status(500).json({ error: "Failed to proxy video from Flask backend" });
  }
};
