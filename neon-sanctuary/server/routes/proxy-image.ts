import { RequestHandler } from "express";

export const handleProxyImage: RequestHandler = async (req, res) => {
  const { url } = req.query;

  if (!url || typeof url !== "string") {
    console.warn("[proxy-image] Missing url parameter");
    return res.status(400).json({ error: "url parameter is required" });
  }

  try {
    console.debug("[proxy-image] Proxying request for:", url);
    const parsedUrl = new URL(url);

    // Fetch the resource
    const response = await fetch(url, {
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        Accept: "image/*,video/*,*/*",
        Referer: "https://www.kroger.com/",
      },
    });

    if (!response.ok) {
      console.error("[proxy-image] Failed to fetch from upstream:", {
        url,
        status: response.status,
        statusText: response.statusText,
      });
      return res
        .status(response.status)
        .json({ error: `Failed to fetch resource: ${response.statusText}` });
    }

    const contentType = response.headers.get("content-type");
    if (!contentType || (!contentType.startsWith("image/") && !contentType.startsWith("video/"))) {
      console.warn("[proxy-image] Response is not an image or video:", {
        url,
        contentType,
      });
      return res.status(400).json({ error: "Response is not an image or video" });
    }

    // Set appropriate headers for caching and CORS
    res.set("Content-Type", contentType);
    res.set("Cache-Control", "public, max-age=86400");
    res.set("Access-Control-Allow-Origin", "*");
    res.set("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS");
    res.set("Accept-Ranges", "bytes");

    // For videos, we need to support range requests for proper streaming
    const contentLength = response.headers.get("content-length");
    if (contentLength) {
      res.set("Content-Length", contentLength);
    }

    const buffer = await response.arrayBuffer();
    console.debug("[proxy-image] Successfully proxied resource:", {
      url,
      type: contentType.startsWith("video/") ? "video" : "image",
      size: buffer.byteLength,
    });
    return res.send(Buffer.from(buffer));
  } catch (error) {
    console.error("[proxy-image] Error:", {
      url,
      message: error instanceof Error ? error.message : String(error),
      stack: error instanceof Error ? error.stack : undefined,
    });
    return res.status(500).json({ error: "Failed to proxy resource" });
  }
};
